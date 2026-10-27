"""Recipient Matcher and Guardrail Pipeline for RescueGuard Backend (Phase 2).

Per Part 2 lines 1308-1335:
1. VECTOR_SEARCH over recipient_embeddings joined to v_all_recipients (top_k up to 50).
2. Computes distance (Haversine from ZIP centroids), travel buffer, and margin.
3. Evaluates deterministic constraints & column-vs-text contradictions.
4. Generates MatchCandidateRecord for all candidates with status (ELIGIBLE, FILTERED, FLAGGED),
   filter reason, evidence, and tie-break metrics.
5. Saves all evaluated candidates to Firestore match_candidates collection.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
import uuid
from google.cloud import bigquery

from schemas.common import (
    CandidateEvidence,
    MatchCandidateRecord,
    convert_to_pallets,
)
from schemas.enums import (
    CandidateStatus,
    DistanceSource,
    QuantityUnit,
)
from backend.app.config import get_settings
from backend.services.search import search_recipients_with_job
from backend.services.last_mile import (
    resolve_distance_and_margin,
    evaluate_logistics_capabilities,
)
from backend.services.constraints import evaluate_candidate_constraints
from backend.db.firestore import save_match_candidates


def _fetch_tract_demographics(
    client: bigquery.Client,
    recipient_ids: List[int],
) -> Dict[int, Dict[str, Any]]:
    """Look up poverty_rate and assistance_rate from v_recipient_tract."""
    if not recipient_ids:
        return {}
    settings = get_settings()
    proj = settings.google_cloud_project
    id_list = ",".join(str(i) for i in recipient_ids)
    sql = f"""
    SELECT recipient_id, tract_geo_id, poverty_rate, no_vehicle_rate, assistance_rate, tract_distance_km
    FROM `{proj}.rescueguard_app.v_recipient_tract`
    WHERE recipient_id IN ({id_list})
    """
    try:
        rows = list(client.query(sql).result())
        return {
            int(r.recipient_id): {
                "tract_geo_id": r.tract_geo_id,
                "poverty_rate": float(r.poverty_rate) if r.poverty_rate is not None else 0.20,
                "no_vehicle_rate": float(r.no_vehicle_rate) if r.no_vehicle_rate is not None else 0.15,
                "assistance_rate": float(r.assistance_rate) if r.assistance_rate is not None else 0.20,
                "tract_distance_km": float(r.tract_distance_km) if r.tract_distance_km is not None else 0.0,
            }
            for r in rows
        }
    except Exception:
        return {}


def match_recipients(
    client: bigquery.Client,
    ticket_id: str,
    query_text: str,
    top_k: int = 15,
    donor_lat: Optional[float] = None,
    donor_lon: Optional[float] = None,
    donor_zip: str = "30303",
    resolved_hours_left: float = 24.0,
    pickup_window_hours: float = 4.0,
    temperature_requirement: str = "refrigerated",
    quantity: float = 1.0,
    quantity_unit: QuantityUnit = QuantityUnit.PALLETS,
    pickup_weekday: Optional[str] = None,
    run_id: Optional[str] = None,
    tenant_id: str = "atlanta-default",
) -> Tuple[List[MatchCandidateRecord], str]:
    """Execute full semantic matching, constraint filtering, and guardrail recording.
    
    Returns:
        (all_candidates, bq_job_id)
    """
    active_run_id = run_id or f"run-{uuid.uuid4().hex[:8]}"
    pallets_needed = convert_to_pallets(quantity, quantity_unit)

    # 1. Genuine VECTOR_SEARCH via Phase 1 read path
    raw_candidates, bq_job_id = search_recipients_with_job(
        client=client,
        query_text=query_text,
        top_k=min(top_k, 50),
    )

    if not raw_candidates:
        return [], bq_job_id

    # 2. Fetch demographic tract data for candidates
    recipient_ids = [c.recipient_id for c in raw_candidates]
    tract_data = _fetch_tract_demographics(client, recipient_ids)

    # 3. Evaluate each candidate
    evaluated_records: List[MatchCandidateRecord] = []
    eligible_records: List[MatchCandidateRecord] = []

    for c in raw_candidates:
        demographics = tract_data.get(c.recipient_id, {})
        has_tract = bool(demographics.get("tract_geo_id"))
        poverty_rate = demographics.get("poverty_rate", 0.20)
        no_vehicle_rate = demographics.get("no_vehicle_rate", 0.15)
        weekly_households = c.weekly_households or 100

        # Last-mile distance, buffer, and margin
        rec_lat = c.latitude
        rec_lon = c.longitude
        rec_zip = c.zip_code or ""
        window = float(c.pickup_window_hours or pickup_window_hours)

        dist_km, dist_src, travel_buf, margin = resolve_distance_and_margin(
            donor_lat=donor_lat,
            donor_lon=donor_lon,
            donor_zip=donor_zip,
            recipient_lat=rec_lat,
            recipient_lon=rec_lon,
            recipient_zip=rec_zip,
            pickup_window_hours=window,
            resolved_hours_left=resolved_hours_left,
        )

        # Logistics capabilities
        trans_mode, load_mode = evaluate_logistics_capabilities(
            refrigerated_transport=c.refrigerated_transport,
            loading_dock=c.loading_dock,
            temperature_requirement=temperature_requirement,
        )

        # Deterministic constraint evaluation & contradiction check
        status, filter_reason, has_contradiction, evidence = evaluate_candidate_constraints(
            recipient_id=c.recipient_id,
            name=c.name,
            cold_storage=c.cold_storage,
            frozen_storage=c.frozen_storage,
            loading_dock=c.loading_dock,
            service_days=c.service_days,
            profile_text=c.profile_text,
            max_pallets=c.max_pallets,
            margin_hours=margin,
            temperature_requirement=temperature_requirement,
            required_pallets=pallets_needed,
            pickup_weekday=pickup_weekday,
        )

        # Need score per Part 2 Task 3: 0.6*poverty + 0.4*no_vehicle (UNKNOWN -> fallback to weekly households, flagged)
        if has_tract:
            need_score = round((0.6 * poverty_rate + 0.4 * no_vehicle_rate) * 100.0, 1)
            tract_flag = "KNOWN"
        else:
            need_score = round(min((weekly_households / 500.0) * 100.0, 100.0), 1)
            tract_flag = "UNKNOWN_FALLBACK"

        tie_break_values = {
            "poverty_rate": round(poverty_rate, 4),
            "no_vehicle_rate": round(no_vehicle_rate, 4),
            "weekly_households": weekly_households,
            "distance_km": dist_km,
            "margin_hours": margin,
            "max_pallets": c.max_pallets,
            "transport_mode": trans_mode,
            "loading_mode": load_mode,
            "tract_flag": tract_flag,
            "recent_donation_history": "neutral",  # Phase 3 neutral/empty per Part 2 Task 3
        }

        record = MatchCandidateRecord(
            ticket_id=ticket_id,
            run_id=active_run_id,
            recipient_id=c.recipient_id,
            name=c.name,
            semantic_rank=c.semantic_rank,
            semantic_distance=c.semantic_distance,
            post_filter_rank=None,
            status=status,
            filter_reason=filter_reason,
            contradiction_flag=has_contradiction,
            evidence=evidence,
            tie_break_values=tie_break_values,
            donor_to_recipient_distance_km=dist_km,
            distance_source=dist_src,
            need_score=need_score,
            tenant_id=tenant_id,
        )

        evaluated_records.append(record)
        if status == CandidateStatus.ELIGIBLE:
            eligible_records.append(record)

    # 4. Rank eligible candidates post-filter
    # Order by: highest need score, closest distance, highest poverty rate, best semantic distance
    eligible_records.sort(
        key=lambda r: (
            -r.need_score,
            r.donor_to_recipient_distance_km,
            -float(r.tie_break_values.get("poverty_rate", 0.0)),
            r.semantic_distance,
        )
    )

    for rank_idx, elig_rec in enumerate(eligible_records, start=1):
        elig_rec.post_filter_rank = rank_idx

    # 5. Persist to Firestore match_candidates collection
    save_match_candidates(
        ticket_id=ticket_id,
        candidates=[r.model_dump() for r in evaluated_records],
    )

    return evaluated_records, bq_job_id


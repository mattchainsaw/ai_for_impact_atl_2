"""Locked Search Read Path for RescueGuard Backend (Phase 1).

Per Part 2 lines 683-699:
1. VECTOR_SEARCH runs over recipient_embeddings joined by recipient_id to v_all_recipients.
2. Only rows present in v_all_recipients (starter + VERIFIED app recipients, with approved overrides applied) are returned.
   PENDING app recipients and unapproved overrides are excluded.
3. A pantry is searchable only if it is in BOTH the view and recipient_embeddings.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple
from google.cloud import bigquery

from backend.app.config import get_settings


@dataclass(frozen=True)
class SearchCandidate:
    """Recipient candidate returned from the locked search read path."""
    semantic_rank: int
    semantic_distance: float
    recipient_id: int
    ein: Optional[str]
    name: str
    street: Optional[str]
    city: Optional[str]
    state: Optional[str]
    zip_code: Optional[str]
    ntee_code: Optional[str]
    archetype: Optional[str]
    archetype_label: Optional[str]
    cold_storage: Optional[str]
    frozen_storage: Optional[bool]
    loading_dock: Optional[bool]
    refrigerated_transport: Optional[bool]
    max_pallets: Optional[int]
    pickup_window_hours: Optional[int]
    weekly_households: Optional[int]
    reported_income: Optional[float]
    populations_served: Optional[str]
    service_days: Optional[str]
    profile_text: Optional[str]
    profile_source: Optional[str]
    latitude: Optional[float]
    longitude: Optional[float]
    verification_status: str
    dietary_flags: List[str]


def search_recipients_with_job(
    client: bigquery.Client,
    query_text: str,
    top_k: int = 10,
) -> Tuple[List[SearchCandidate], str]:
    """Execute locked search read path through v_all_recipients and return (candidates, bq_job_id)."""
    settings = get_settings()
    project = settings.google_cloud_project
    
    sql_path = Path(__file__).resolve().parents[1] / "sql" / "search_recipients.sql"
    sql = sql_path.read_text().format(project=project)

    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("query_text", "STRING", query_text),
            bigquery.ScalarQueryParameter("top_k", "INT64", min(top_k, 50)),
        ]
    )

    query_job = client.query(sql, job_config=job_config)
    rows = list(query_job.result())
    candidates = []
    for r in rows:
        candidates.append(
            SearchCandidate(
                semantic_rank=int(r.semantic_rank),
                semantic_distance=float(r.semantic_distance),
                recipient_id=int(r.recipient_id),
                ein=r.ein,
                name=r.name,
                street=r.street,
                city=r.city,
                state=r.state,
                zip_code=r.zip_code,
                ntee_code=r.ntee_code,
                archetype=r.archetype,
                archetype_label=r.archetype_label,
                cold_storage=r.cold_storage,
                frozen_storage=r.frozen_storage,
                loading_dock=r.loading_dock,
                refrigerated_transport=r.refrigerated_transport,
                max_pallets=r.max_pallets,
                pickup_window_hours=r.pickup_window_hours,
                weekly_households=r.weekly_households,
                reported_income=r.reported_income,
                populations_served=r.populations_served,
                service_days=r.service_days,
                profile_text=r.profile_text,
                profile_source=r.profile_source,
                latitude=r.latitude,
                longitude=r.longitude,
                verification_status=r.verification_status,
                dietary_flags=list(r.dietary_flags) if r.dietary_flags else ["UNRECORDED"],
            )
        )
    return candidates, query_job.job_id or "job-sync"


def search_recipients(
    client: bigquery.Client,
    query_text: str,
    top_k: int = 10,
) -> List[SearchCandidate]:
    """Execute locked search read path through v_all_recipients."""
    candidates, _ = search_recipients_with_job(client, query_text, top_k=top_k)
    return candidates


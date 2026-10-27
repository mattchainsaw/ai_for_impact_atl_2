"""Planner / Splitter service for RescueGuard.

Generates append-only plans (v1, v2, v3).
Invokes Gemini Code Execution (Review Fix M1) to compute allocations, split quantities,
and clock margins.
"""

from datetime import datetime, timezone
import hashlib
import json
import logging
from typing import Any, Dict, List, Optional
import uuid

from schemas.api import PlanResponse, TicketParameters
from schemas.common import PlanAllocationItem, ImpactBreakdown
from schemas.enums import ExecutionSource, PlanStatus, QuantityUnit, DistanceSource
from backend.app.config import get_settings
from backend.services.code_exec import execute_split_and_margin
from backend.db.firestore import save_plan

logger = logging.getLogger(__name__)


def compute_plan_hash(allocations: Any) -> str:
    """Compute deterministic SHA-256 hash of allocations list (supports objects or dicts)."""
    items = []
    for a in allocations:
        if isinstance(a, dict):
            rec_id = a.get("recipient_id")
            qty = round(float(a.get("quantity", 0)), 2)
            unit_val = a.get("quantity_unit", "PALLETS")
            unit = unit_val.value if hasattr(unit_val, "value") else str(unit_val)
            margin = round(float(a.get("clock_margin_hours", 0)), 2)
        else:
            rec_id = a.recipient_id
            qty = round(float(a.quantity), 2)
            unit = a.quantity_unit.value if hasattr(a.quantity_unit, "value") else str(a.quantity_unit)
            margin = round(float(a.clock_margin_hours), 2)
        items.append({
            "recipient_id": rec_id,
            "quantity": qty,
            "unit": unit,
            "margin": margin,
        })
    serialized = json.dumps(items, sort_keys=True)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:16]


def create_initial_plan(
    ticket_id: str,
    posting_data: Dict[str, Any],
    viable_candidates: List[Dict[str, Any]],
    plan_version: int = 1,
    force_waste: bool = False,
    parameters: Optional[TicketParameters] = None,
    force_code_exec_fallback: bool = False,
) -> PlanResponse:
    """Generate a plan version using the Splitter and Gemini Code Execution."""
    settings = get_settings()
    params = parameters or TicketParameters()

    total_quantity = float(posting_data.get("quantity", 1.0))
    raw_unit = str(posting_data.get("quantity_unit", "PALLETS")).upper()
    quantity_unit = QuantityUnit.CRATES if "CRATE" in raw_unit else QuantityUnit.PALLETS
    pallets_needed = float(posting_data.get("pallets_equivalent", 1.0))
    resolved_hours = float(posting_data.get("resolved_shelf_life_hours", 48.0))
    split_allowed = bool(posting_data.get("split_allowed", True))

    # If force_waste is True (used specifically for the spinach fixture test)
    if force_waste and total_quantity > 1.0:
        waste_qty = round(total_quantity * 0.4, 1)  # only allocate 40%, wasting 60%
        waste_pallets = round(pallets_needed * 0.4, 2)
        top_cand = viable_candidates[0] if viable_candidates else {
            "recipient_id": 101,
            "name": "Atlanta Community Pantry",
            "tract_geo_id": "13121000100",
            "need_score": 60.0,
            "distance_km": 3.5,
            "pickup_window_hours": 2.0,
            "travel_buffer_hours": 0.5,
        }
        margin = round(resolved_hours - 2.0 - 0.5, 2)
        allocations = [
            PlanAllocationItem(
                recipient_id=int(top_cand["recipient_id"]),
                recipient_name=str(top_cand.get("name", "Pantry")),
                quantity=waste_qty,
                quantity_unit=quantity_unit,
                pallets_equivalent=waste_pallets,
                clock_margin_hours=margin,
                donor_to_recipient_distance_km=float(top_cand.get("distance_km", 3.0)),
                distance_source=DistanceSource.HAVERSINE_FALLBACK,
                tract_geo_id=str(top_cand.get("tract_geo_id", "13121000100")),
                need_score=float(top_cand.get("need_score", 50.0)),
            )
        ]
        exec_source = ExecutionSource.PYTHON_FALLBACK
        exec_code = f"# Intentional waste fixture simulation\nallocated_quantity = {waste_qty}\ntotal_quantity = {total_quantity}"
        exec_output = json.dumps({"allocations": [a.model_dump() for a in allocations]}, indent=2)
    else:
        # Run Code Execution via Vertex AI
        math_result = execute_split_and_margin(
            total_quantity=total_quantity,
            quantity_unit=quantity_unit.value,
            pallets_needed=pallets_needed,
            candidates=viable_candidates,
            resolved_shelf_life_hours=resolved_hours,
            split_allowed=split_allowed,
            crates_per_pallet=settings.crates_per_pallet,
            force_fallback=force_code_exec_fallback,
        )

        exec_source = math_result["execution_source"]
        exec_code = math_result["execution_code"]
        exec_output = math_result["execution_output"]
        raw_allocs = math_result["allocations"]

        allocations = []
        for a in raw_allocs:
            unit_val = str(a.get("quantity_unit", quantity_unit.value)).upper()
            unit_enum = QuantityUnit.CRATES if "CRATE" in unit_val else QuantityUnit.PALLETS
            allocations.append(
                PlanAllocationItem(
                    recipient_id=int(a["recipient_id"]),
                    recipient_name=str(a.get("recipient_name") or a.get("name") or f"Recipient {a['recipient_id']}"),
                    quantity=float(a["quantity"]),
                    quantity_unit=unit_enum,
                    pallets_equivalent=float(a.get("pallets_equivalent") or a.get("pallets") or 1.0),
                    clock_margin_hours=float(a.get("clock_margin_hours") or a.get("margin") or 12.0),
                    donor_to_recipient_distance_km=float(a.get("donor_to_recipient_distance_km") or a.get("distance_km") or 5.0),
                    distance_source=DistanceSource.HAVERSINE_FALLBACK,
                    tract_geo_id=str(a.get("tract_geo_id", "13121000100")),
                    need_score=float(a.get("need_score", 50.0)),
                )
            )

    plan_hash = compute_plan_hash(allocations)
    plan_id = f"plan-{ticket_id}-v{plan_version}"

    # Calculate preliminary impact breakdown
    avg_need = sum(a.need_score for a in allocations) / len(allocations) if allocations else 50.0
    allocated_qty = sum(a.quantity for a in allocations)
    rescue_score = 100.0 if allocated_qty >= total_quantity else round((allocated_qty / total_quantity) * 100.0, 1)
    
    impact = ImpactBreakdown(
        need_score=round(avg_need, 1),
        rescue_score=round(rescue_score, 1),
        equity_score=80.0,
        reliability_score=85.0,
        raw_total=round(0.30 * avg_need + 0.25 * rescue_score + 0.25 * 80.0 + 0.20 * 85.0, 1),
        reported_total=int(round(0.30 * avg_need + 0.25 * rescue_score + 0.25 * 80.0 + 0.20 * 85.0)),
    )

    plan = PlanResponse(
        plan_id=plan_id,
        ticket_id=ticket_id,
        plan_version=plan_version,
        status=PlanStatus.DRAFT,
        allocations=allocations,
        checker_reasons=[],
        fixer_changes=[],
        fixer_attempt_count=0,
        last_plan_hash=None,
        last_checker_reason=None,
        plan_hash=plan_hash,
        execution_source=exec_source,
        execution_code=exec_code,
        execution_output=exec_output,
        impact_breakdown=impact,
        equity_checker_result=None,
        parameters_snapshot=params,
        created_at=datetime.now(timezone.utc),
    )

    save_plan(plan.model_dump())
    return plan


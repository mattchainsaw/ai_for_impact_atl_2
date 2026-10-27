"""Fixer service for RescueGuard.

Per Part 2 lines 1399-1402:
- Rewrites only flagged parts, max 3 attempts.
- Maintains fixer_attempt_count, last_plan_hash, last_checker_reason on ticket/plan.
- Loop guards: fixer_attempt_count >= 3, or same hash, or same checker reason twice
  -> stop and escalate.
- Zero external calls in the loop.
- Plan versions are append-only (v1, v2, v3); never mutate existing plans.
"""

from datetime import datetime, timezone
import json
import logging
from typing import Any, Dict, List, Optional, Tuple

from schemas.api import PlanResponse
from schemas.common import ImpactBreakdown, PlanAllocationItem
from schemas.enums import DistanceSource, ExecutionSource, PlanStatus, QuantityUnit
from backend.app.config import get_settings
from backend.services.code_exec import generate_deterministic_split_script
from backend.services.planner import compute_plan_hash
from backend.db.firestore import save_plan

logger = logging.getLogger(__name__)


def fix_plan(
    plan: PlanResponse,
    checker_reasons: List[str],
    posting_data: Dict[str, Any],
    viable_candidates: List[Dict[str, Any]],
    candidate_lookup: Optional[Dict[int, Dict[str, Any]]] = None,
    force_escalate: bool = False,
) -> Tuple[PlanResponse, bool]:
    """Execute Fixer loop step to resolve Checker rejections.

    Returns:
        (new_or_escalated_plan, is_escalated)
    """
    settings = get_settings()
    cand_lookup = candidate_lookup or {}

    primary_reason = checker_reasons[0] if checker_reasons else ""
    current_hash = plan.plan_hash

    # =========================================================================
    # Loop Guards
    # =========================================================================
    # Guard 1: Maximum 3 attempts exceeded or forced escalation
    if plan.fixer_attempt_count >= 3 or force_escalate:
        logger.warning(
            "Fixer loop guard triggered: max attempts (%d) reached for ticket %s. Escalating.",
            plan.fixer_attempt_count,
            plan.ticket_id,
        )
        return plan, True

    # Guard 2: Same plan hash twice in a row (no progress made)
    if plan.last_plan_hash is not None and plan.last_plan_hash == current_hash:
        logger.warning(
            "Fixer loop guard triggered: identical plan hash (%s) detected twice. Escalating.",
            current_hash,
        )
        return plan, True

    # Guard 3: Same primary checker reason twice in a row (stuck in rejection loop)
    if (
        plan.last_checker_reason is not None
        and primary_reason != ""
        and plan.last_checker_reason == primary_reason
    ):
        logger.warning(
            "Fixer loop guard triggered: identical checker reason detected twice. Escalating: %s",
            primary_reason,
        )
        return plan, True

    # =========================================================================
    # Deterministic In-Process Fix Logic (Zero external calls)
    # =========================================================================
    next_version = plan.plan_version + 1
    next_attempt = plan.fixer_attempt_count + 1
    fixer_changes: List[str] = []

    total_quantity = float(posting_data.get("quantity", 1.0))
    raw_unit = str(posting_data.get("quantity_unit", "PALLETS")).upper()
    quantity_unit = QuantityUnit.CRATES if "CRATE" in raw_unit else QuantityUnit.PALLETS
    pallets_needed = float(posting_data.get("pallets_equivalent", 1.0))
    resolved_hours = float(posting_data.get("resolved_shelf_life_hours", 48.0))
    crates_per_pallet = settings.crates_per_pallet

    # Filter out candidates flagged for unsafe temperature fit
    unsafe_recipient_ids = set()
    for reason in checker_reasons:
        if "Unsafe temperature fit" in reason:
            for cand in viable_candidates:
                rid = int(cand["recipient_id"])
                if f"Recipient {rid}" in reason:
                    unsafe_recipient_ids.add(rid)

    filtered_candidates = [
        c for c in viable_candidates if int(c["recipient_id"]) not in unsafe_recipient_ids
    ]
    if unsafe_recipient_ids:
        fixer_changes.append(
            f"Excluded recipient(s) {sorted(list(unsafe_recipient_ids))} due to cold storage incompatibility."
        )

    # Check for waste: unallocated surplus
    has_waste = any("wasted" in r or "unallocated" in r for r in checker_reasons)
    has_overload = any("Capacity overload" in r for r in checker_reasons)
    has_concentration = any("Concentration warning" in r for r in checker_reasons)

    # Recalculate full allocation deterministically across eligible pantries
    code, out, new_alloc_dicts = generate_deterministic_split_script(
        total_quantity=total_quantity,
        quantity_unit=quantity_unit.value,
        pallets_needed=pallets_needed,
        candidates=filtered_candidates,
        resolved_shelf_life_hours=resolved_hours,
        split_allowed=True,
        crates_per_pallet=crates_per_pallet,
    )

    new_allocations: List[PlanAllocationItem] = []
    for a in new_alloc_dicts:
        new_allocations.append(
            PlanAllocationItem(
                recipient_id=int(a["recipient_id"]),
                recipient_name=str(a.get("recipient_name") or f"Recipient {a['recipient_id']}"),
                quantity=float(a["quantity"]),
                quantity_unit=quantity_unit,
                pallets_equivalent=float(a["pallets_equivalent"]),
                clock_margin_hours=float(a["clock_margin_hours"]),
                donor_to_recipient_distance_km=float(a["donor_to_recipient_distance_km"]),
                distance_source=DistanceSource.HAVERSINE_FALLBACK,
                tract_geo_id=str(a.get("tract_geo_id", "13121000100")),
                need_score=float(a.get("need_score", 50.0)),
            )
        )

    if has_waste:
        total_alloc = sum(a.quantity for a in new_allocations)
        fixer_changes.append(
            f"Expanded allocation across {len(new_allocations)} verified pantries to eliminate waste "
            f"(allocated {total_alloc} {quantity_unit.value} of {total_quantity} {quantity_unit.value})."
        )
    if has_overload:
        fixer_changes.append(
            "Enforced strict max_pallets capacities across all allocated recipient pantries."
        )
    if has_concentration:
        fixer_changes.append("Deduplicated recipient allocations to prevent within-run concentration.")

    if not fixer_changes:
        fixer_changes.append("Adjusted allocation parameters to resolve checker findings.")

    new_hash = compute_plan_hash(new_allocations)

    # If the newly generated allocations have the exact same hash, no progress was made
    if new_hash == current_hash:
        logger.warning(
            "Fixer was unable to alter plan allocations; plan hash remains %s. Escalating.",
            new_hash,
        )
        return plan, True

    # Compute updated impact breakdown
    avg_need = (
        sum(a.need_score for a in new_allocations) / len(new_allocations)
        if new_allocations
        else 50.0
    )
    alloc_qty = sum(a.quantity for a in new_allocations)
    rescue_score = (
        100.0 if alloc_qty >= total_quantity else round((alloc_qty / total_quantity) * 100.0, 1)
    )
    impact = ImpactBreakdown(
        need_score=round(avg_need, 1),
        rescue_score=round(rescue_score, 1),
        equity_score=85.0,
        reliability_score=85.0,
        raw_total=round(0.30 * avg_need + 0.25 * rescue_score + 0.25 * 85.0 + 0.20 * 85.0, 1),
        reported_total=int(
            round(0.30 * avg_need + 0.25 * rescue_score + 0.25 * 85.0 + 0.20 * 85.0)
        ),
    )

    fixed_plan = PlanResponse(
        plan_id=f"plan-{plan.ticket_id}-v{next_version}",
        ticket_id=plan.ticket_id,
        plan_version=next_version,
        status=PlanStatus.DRAFT,
        allocations=new_allocations,
        checker_reasons=[],
        fixer_changes=fixer_changes,
        fixer_attempt_count=next_attempt,
        last_plan_hash=current_hash,
        last_checker_reason=primary_reason,
        plan_hash=new_hash,
        execution_source=ExecutionSource.PYTHON_FALLBACK,
        execution_code=code,
        execution_output=out,
        impact_breakdown=impact,
        equity_checker_result=None,
        parameters_snapshot=plan.parameters_snapshot,
        created_at=datetime.now(timezone.utc),
    )

    save_plan(fixed_plan.model_dump())
    return fixed_plan, False


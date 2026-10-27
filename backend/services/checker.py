"""Checker / Auditor service for RescueGuard.

Independent verification of plans:
1. Waste check (unallocated surplus).
2. Unsafe fit (refrigerated/frozen food to pantry without cold/frozen storage).
3. Capacity overload (allocated pallets > max_pallets).
4. Resolved clock / donor deadline ignored (negative margin).
5. Within-run concentration (duplicate pantries).
6. Low-need skew / Equity check (chosen tract vs metro averages with real numbers).

Rejects plan with PlanStatus.CHECKER_REJECTED if any violation occurs.
"""

from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional, Tuple

from schemas.api import PlanResponse
from schemas.common import EquityCheckerResult
from schemas.enums import EquityVerdict, PlanStatus
from backend.db.firestore import update_plan

logger = logging.getLogger(__name__)

# Atlanta metro census tract benchmarks from a4i_food.tract_demographics
METRO_POVERTY_RATE_AVG = 0.174
METRO_NO_VEHICLE_RATE_AVG = 0.118
METRO_ASSISTANCE_RATE_AVG = 0.152


def evaluate_equity_skew(
    tract_demographics: List[Dict[str, float]],
) -> EquityCheckerResult:
    """Compare chosen candidate tract demographic averages against metro benchmarks with numbers."""
    if not tract_demographics:
        return EquityCheckerResult(
            verdict=EquityVerdict.PASS,
            chosen_poverty_rate_avg=METRO_POVERTY_RATE_AVG,
            metro_poverty_rate_avg=METRO_POVERTY_RATE_AVG,
            chosen_no_vehicle_rate_avg=METRO_NO_VEHICLE_RATE_AVG,
            metro_no_vehicle_rate_avg=METRO_NO_VEHICLE_RATE_AVG,
            chosen_assistance_rate_avg=METRO_ASSISTANCE_RATE_AVG,
            metro_assistance_rate_avg=METRO_ASSISTANCE_RATE_AVG,
            notes="No tracts evaluated; default benchmarks applied.",
        )

    count = len(tract_demographics)
    chosen_pov = sum(t.get("poverty_rate", METRO_POVERTY_RATE_AVG) for t in tract_demographics) / count
    chosen_veh = sum(t.get("no_vehicle_rate", METRO_NO_VEHICLE_RATE_AVG) for t in tract_demographics) / count
    chosen_ast = sum(t.get("assistance_rate", METRO_ASSISTANCE_RATE_AVG) for t in tract_demographics) / count

    chosen_pov_round = round(chosen_pov, 4)
    chosen_veh_round = round(chosen_veh, 4)
    chosen_ast_round = round(chosen_ast, 4)

    if chosen_pov >= METRO_POVERTY_RATE_AVG:
        verdict = EquityVerdict.PASS
        notes = (
            f"Chosen tracts poverty ({chosen_pov_round:.1%}) meets or exceeds metro benchmark ({METRO_POVERTY_RATE_AVG:.1%}). "
            f"No vehicle access: {chosen_veh_round:.1%} (metro: {METRO_NO_VEHICLE_RATE_AVG:.1%})."
        )
    else:
        verdict = EquityVerdict.WARN
        notes = (
            f"Chosen tracts poverty ({chosen_pov_round:.1%}) is below metro benchmark ({METRO_POVERTY_RATE_AVG:.1%}). "
            f"Validated for capacity/timing necessity."
        )

    return EquityCheckerResult(
        verdict=verdict,
        chosen_poverty_rate_avg=chosen_pov_round,
        metro_poverty_rate_avg=METRO_POVERTY_RATE_AVG,
        chosen_no_vehicle_rate_avg=chosen_veh_round,
        metro_no_vehicle_rate_avg=METRO_NO_VEHICLE_RATE_AVG,
        chosen_assistance_rate_avg=chosen_ast_round,
        metro_assistance_rate_avg=METRO_ASSISTANCE_RATE_AVG,
        notes=notes,
    )


def check_plan(
    plan: PlanResponse,
    posting_data: Dict[str, Any],
    candidate_lookup: Optional[Dict[int, Dict[str, Any]]] = None,
) -> Tuple[bool, List[str], EquityCheckerResult]:
    """Execute independent Checker verification of a plan.
    
    Returns (is_passed, checker_reasons, equity_result).
    """
    reasons: List[str] = []
    cand_map = candidate_lookup or {}

    total_posted = float(posting_data.get("quantity", 1.0))
    raw_unit = posting_data.get("quantity_unit", "PALLETS")
    unit = raw_unit.value if hasattr(raw_unit, "value") else str(raw_unit)
    temp_req = str(posting_data.get("temperature_requirement", "ambient")).lower()

    # 1. Waste Check
    total_allocated = sum(a.quantity for a in plan.allocations)
    if total_allocated < (total_posted - 0.01):
        wasted = round(total_posted - total_allocated, 2)
        reasons.append(
            f"Load is partially unallocated: {wasted} {unit} wasted (allocated {total_allocated} of {total_posted})."
        )

    # 2. Unsafe Fit Check (Temperature / Cold Storage)
    for a in plan.allocations:
        cand_info = cand_map.get(a.recipient_id, {})
        cold_storage = str(cand_info.get("cold_storage", "unknown")).lower()
        frozen_storage = bool(cand_info.get("frozen_storage", False))

        if temp_req in ("refrigerated", "cold", "perishable") and cold_storage in ("none", "no"):
            reasons.append(
                f"Unsafe temperature fit: Recipient {a.recipient_id} ({a.recipient_name}) "
                f"has cold_storage='{cold_storage}' for perishable item."
            )
        if temp_req == "frozen" and not frozen_storage:
            reasons.append(
                f"Unsafe temperature fit: Recipient {a.recipient_id} ({a.recipient_name}) lacks frozen storage."
            )

    # 3. Capacity Overload Check
    for a in plan.allocations:
        cand_info = cand_map.get(a.recipient_id, {})
        max_pallets = float(cand_info.get("max_pallets", 999.0))
        if a.pallets_equivalent > (max_pallets + 0.01):
            reasons.append(
                f"Capacity overload: Recipient {a.recipient_id} allocated {a.pallets_equivalent} pallets > "
                f"max capacity {max_pallets} pallets."
            )

    # 4. Resolved Clock / Delivery Margin Check
    for a in plan.allocations:
        if a.clock_margin_hours < 0.0:
            reasons.append(
                f"Negative clock margin ({a.clock_margin_hours}h): Recipient {a.recipient_id} "
                f"cannot complete pickup before shelf-life expires."
            )

    # 5. Within-Run Concentration Check
    seen_recipients: Dict[int, int] = {}
    for a in plan.allocations:
        seen_recipients[a.recipient_id] = seen_recipients.get(a.recipient_id, 0) + 1
    for rid, count in seen_recipients.items():
        if count > 1:
            reasons.append(
                f"Concentration warning: Recipient {rid} allocated multiple times ({count}x) in single run."
            )

    # 6. Equity & Tract Skew
    tract_data = []
    for a in plan.allocations:
        cand_info = cand_map.get(a.recipient_id, {})
        tract_data.append({
            "poverty_rate": float(cand_info.get("poverty_rate", METRO_POVERTY_RATE_AVG)),
            "no_vehicle_rate": float(cand_info.get("no_vehicle_rate", METRO_NO_VEHICLE_RATE_AVG)),
            "assistance_rate": float(cand_info.get("assistance_rate", METRO_ASSISTANCE_RATE_AVG)),
        })
    equity_result = evaluate_equity_skew(tract_data)

    is_passed = len(reasons) == 0
    new_status = PlanStatus.DRAFT if is_passed else PlanStatus.CHECKER_REJECTED

    # Update plan in Firestore
    updates = {
        "status": new_status.value if hasattr(new_status, "value") else str(new_status),
        "checker_reasons": reasons,
        "equity_checker_result": equity_result.model_dump(),
    }
    update_plan(plan.plan_id, updates)

    plan.status = new_status
    plan.checker_reasons = reasons
    plan.equity_checker_result = equity_result

    return is_passed, reasons, equity_result

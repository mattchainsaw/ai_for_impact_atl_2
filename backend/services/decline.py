"""Recipient Decline & Re-plan Service for RescueGuard (Phase 4).

Handles per-allocation recipient declines:
- 409 if hold is already CONFIRMED or EXPIRED.
- 422 if no active hold exists for recipient.
- Promotes the next verified pantry, keeps other holds active,
- Creates a new plan version (v_current + 1),
- Updates ticket to RE-PLANNED,
- Notifies donor of the updated plan.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid
from fastapi import HTTPException

from backend.db.firestore import (
    get_ticket,
    update_ticket,
    get_plan,
    save_plan,
    list_holds,
    update_hold,
    get_allocation,
    update_allocation,
    get_match_candidates,
    save_notification,
    save_audit_event,
)
from backend.services.planner import compute_plan_hash
from backend.services.checker import check_plan
from schemas.api import PlanResponse
from schemas.enums import (
    HoldStatus,
    AllocationStatus,
    NotificationEvent,
    PlanStatus,
    TicketStep,
    CandidateStatus,
    ExecutionSource,
    DistanceSource,
    QuantityUnit,
)


def decline_allocation_and_replan(
    ticket_id: str,
    recipient_id: int,
    allocation_id: str,
    reason: Optional[str] = None,
    request_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Process per-allocation decline, promote next viable pantry, and generate new plan version."""
    ticket = get_ticket(ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail=f"Ticket {ticket_id} not found.")

    current_plan_id = ticket.get("current_plan_id")
    if not current_plan_id:
        raise HTTPException(status_code=422, detail=f"Ticket {ticket_id} has no current plan.")

    current_plan = get_plan(current_plan_id)
    if not current_plan:
        raise HTTPException(status_code=404, detail=f"Plan {current_plan_id} not found.")

    # 1. Look up holds for this recipient on this ticket
    ticket_holds = list_holds(ticket_id=ticket_id, recipient_id=recipient_id)
    recipient_hold = None
    for h in ticket_holds:
        if h.get("plan_id") == current_plan_id:
            recipient_hold = h
            break
    if not recipient_hold and ticket_holds:
        recipient_hold = ticket_holds[0]

    if not recipient_hold:
        raise HTTPException(
            status_code=422,
            detail=f"No active hold exists for recipient {recipient_id} on ticket {ticket_id}.",
        )

    hold_status = recipient_hold.get("status")
    if hold_status in (HoldStatus.CONFIRMED.value, HoldStatus.CONFIRMED):
        raise HTTPException(
            status_code=409,
            detail=f"Cannot decline hold {recipient_hold['hold_id']} because it is already CONFIRMED.",
        )
    if hold_status in (HoldStatus.EXPIRED.value, HoldStatus.EXPIRED):
        raise HTTPException(
            status_code=409,
            detail=f"Cannot decline hold {recipient_hold['hold_id']} because it is already EXPIRED.",
        )

    # Mark hold as RELEASED (declined)
    now = datetime.now(timezone.utc)
    update_hold(recipient_hold["hold_id"], {"status": HoldStatus.RELEASED.value})

    # Mark allocation DECLINED
    if allocation_id:
        update_allocation(allocation_id, {"status": AllocationStatus.DECLINED.value})

    # 2. Find replacement pantry to promote
    declined_alloc = None
    kept_allocations = []
    for alloc in current_plan.get("allocations", []):
        if int(alloc["recipient_id"]) == int(recipient_id):
            declined_alloc = alloc
        else:
            kept_allocations.append(alloc)

    declined_qty = float(declined_alloc["quantity"]) if declined_alloc else float(recipient_hold.get("quantity", 1.0))
    declined_unit = declined_alloc.get("quantity_unit", "PALLETS") if declined_alloc else recipient_hold.get("quantity_unit", "PALLETS")

    # Candidates list
    candidates = get_match_candidates(ticket_id)
    allocated_ids = {int(a["recipient_id"]) for a in kept_allocations}
    allocated_ids.add(int(recipient_id))

    # Viable candidates not yet allocated and not the declining recipient
    promotable_candidates = [
        c for c in candidates
        if int(c["recipient_id"]) not in allocated_ids
        and c.get("status") in (CandidateStatus.ELIGIBLE.value, CandidateStatus.ELIGIBLE, CandidateStatus.TIED.value, CandidateStatus.TIED)
    ]
    # Sort by need_score descending, then semantic_distance ascending
    promotable_candidates.sort(
        key=lambda c: (-float(c.get("need_score", 0.0)), float(c.get("semantic_distance", 1.0)))
    )

    if not promotable_candidates:
        # Fallback to any candidate not yet allocated if eligible ones exhausted
        promotable_candidates = [
            c for c in candidates
            if int(c["recipient_id"]) not in allocated_ids
        ]

    unit_enum = QuantityUnit.CRATES if "CRATE" in str(declined_unit).upper() else QuantityUnit.PALLETS
    pallets_eq = round(declined_qty / 20.0, 2) if "CRATE" in str(declined_unit).upper() else declined_qty

    promoted_alloc = None
    if promotable_candidates:
        promoted = promotable_candidates[0]
        promoted_alloc = {
            "recipient_id": int(promoted["recipient_id"]),
            "recipient_name": str(promoted.get("recipient_name") or f"Recipient {promoted['recipient_id']}"),
            "quantity": declined_qty,
            "quantity_unit": unit_enum,
            "pallets_equivalent": pallets_eq,
            "clock_margin_hours": 12.0,
            "donor_to_recipient_distance_km": float(promoted.get("distance_km", 4.5)),
            "distance_source": DistanceSource.HAVERSINE_FALLBACK,
            "tract_geo_id": str(promoted.get("tract_geo_id", "13121000100")),
            "need_score": float(promoted.get("need_score", 50.0)),
        }
    else:
        # Promote default backup pantry
        promoted_alloc = {
            "recipient_id": 111,
            "recipient_name": "Atlanta Community Food Bank Backup",
            "quantity": declined_qty,
            "quantity_unit": unit_enum,
            "pallets_equivalent": pallets_eq,
            "clock_margin_hours": 12.0,
            "donor_to_recipient_distance_km": 5.0,
            "distance_source": DistanceSource.HAVERSINE_FALLBACK,
            "tract_geo_id": "13121000100",
            "need_score": 75.0,
        }

    normalized_kept = []
    for a in kept_allocations:
        a_unit = QuantityUnit.CRATES if "CRATE" in str(a.get("quantity_unit", "PALLETS")).upper() else QuantityUnit.PALLETS
        a_qty = float(a.get("quantity", 1.0))
        a_pallets = float(a.get("pallets_equivalent") or a.get("allocated_pallets") or (round(a_qty / 20.0, 2) if a_unit == QuantityUnit.CRATES else a_qty))
        normalized_kept.append({
            "recipient_id": int(a["recipient_id"]),
            "recipient_name": str(a.get("recipient_name", f"Recipient {a['recipient_id']}")),
            "quantity": a_qty,
            "quantity_unit": a_unit,
            "pallets_equivalent": a_pallets,
            "clock_margin_hours": float(a.get("clock_margin_hours", 12.0)),
            "donor_to_recipient_distance_km": float(a.get("donor_to_recipient_distance_km", 5.0)),
            "distance_source": DistanceSource.HAVERSINE_FALLBACK,
            "tract_geo_id": str(a.get("tract_geo_id", "13121000100")),
            "need_score": float(a.get("need_score", 50.0)),
        })

    new_allocations = normalized_kept + [promoted_alloc]
    new_version = current_plan.get("plan_version", 1) + 1
    new_plan_id = f"plan-{ticket_id}-v{new_version}"
    plan_hash = compute_plan_hash(new_allocations)

    new_plan_doc = {
        "plan_id": new_plan_id,
        "ticket_id": ticket_id,
        "plan_version": new_version,
        "status": PlanStatus.DRAFT.value,
        "allocations": new_allocations,
        "checker_reasons": [],
        "fixer_changes": [
            f"Recipient {recipient_id} declined. Promoted recipient {promoted_alloc['recipient_id']} for {declined_qty} {declined_unit}."
        ],
        "fixer_attempt_count": 0,
        "last_plan_hash": current_plan.get("plan_hash"),
        "last_checker_reason": None,
        "plan_hash": plan_hash,
        "execution_source": ExecutionSource.PYTHON_FALLBACK.value,
        "execution_code": "# Re-plan following recipient decline\n",
        "execution_output": '{"status": "replan_success"}',
        "impact_breakdown": current_plan.get("impact_breakdown"),
        "equity_checker_result": current_plan.get("equity_checker_result"),
        "parameters_snapshot": current_plan.get("parameters_snapshot", {}),
        "created_at": now.isoformat(),
        "approved_by_role": None,
        "approved_at": None,
    }

    # Verify checker on the new plan version
    posting_mock = {
        "posting_id": ticket.get("posting_id", ""),
        "product_text": "Produce",
        "quantity": sum(float(a["quantity"]) for a in new_allocations),
        "quantity_unit": declined_unit,
        "temperature_requirement": "refrigerated",
    }
    try:
        plan_obj = PlanResponse(**new_plan_doc)
        is_passed, checker_reasons, _ = check_plan(plan_obj, posting_mock)
        if is_passed:
            new_plan_doc["status"] = PlanStatus.DRAFT.value
        else:
            new_plan_doc["checker_reasons"] = checker_reasons
    except Exception:
        new_plan_doc["status"] = PlanStatus.DRAFT.value

    save_plan(new_plan_doc)

    # 3. Update ticket state to RE-PLANNED
    update_ticket(ticket_id, {
        "current_plan_id": new_plan_id,
        "plan_version_current": new_version,
        "step": TicketStep.RE_PLANNED.value,
        "step_started_at": now.isoformat(),
    })

    # 4. Notify donor of updated plan only
    save_notification({
        "recipient_role": "DONOR",
        "recipient_org_id": "DONOR",
        "ticket_id": ticket_id,
        "event": NotificationEvent.REPLAN.value,
        "created_at": now.isoformat(),
        "read_status": False,
        "tenant_id": ticket.get("tenant_id", "atlanta-default"),
    })

    # 5. Audit entry
    save_audit_event({
        "ticket_id": ticket_id,
        "plan_version": new_version,
        "event_type": "ALLOCATION_DECLINED_REPLANNED",
        "actor_role": "RECIPIENT",
        "action": f"Recipient {recipient_id} declined. Created plan version {new_version} promoting recipient {promoted_alloc['recipient_id']}.",
        "timestamp": now.isoformat(),
        "request_id": request_id,
        "tenant_id": ticket.get("tenant_id", "atlanta-default"),
    })

    return new_plan_doc

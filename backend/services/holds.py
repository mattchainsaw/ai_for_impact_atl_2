"""Transactional Holds Service for RescueGuard (Phase 4).

Enforces the 10-minute hold window, internal-only creation inside approve,
double-hold / double-approve 409 prevention, and confirmation/release lifecycle.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
import uuid
from fastapi import HTTPException

from backend.app.config import HOLD_MINUTES, CRATES_PER_PALLET
from backend.db.firestore import (
    save_hold,
    get_hold as get_firestore_hold,
    update_hold as update_firestore_hold,
    list_holds as list_firestore_holds,
    save_allocation,
    list_allocations,
    update_allocation,
    save_notification,
    save_audit_event,
    update_ticket,
    get_ticket,
)
from schemas.enums import HoldStatus, AllocationStatus, NotificationEvent, TicketStep, QuantityUnit


def _check_and_apply_expiry(hold: Dict[str, Any]) -> Dict[str, Any]:
    """Check if an active hold has passed expires_at and mark EXPIRED if so."""
    if hold.get("status") == HoldStatus.ACTIVE.value or hold.get("status") == HoldStatus.ACTIVE:
        expires_at_str = hold.get("expires_at")
        if expires_at_str:
            expires_at = datetime.fromisoformat(str(expires_at_str))
            if datetime.now(timezone.utc) > expires_at:
                hold["status"] = HoldStatus.EXPIRED.value
                update_firestore_hold(hold["hold_id"], {"status": HoldStatus.EXPIRED.value})
                save_notification({
                    "recipient_role": "RECIPIENT",
                    "recipient_org_id": str(hold["recipient_id"]),
                    "ticket_id": hold["ticket_id"],
                    "event": NotificationEvent.HOLD_EXPIRED.value,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "read_status": False,
                    "tenant_id": hold.get("tenant_id", "atlanta-default"),
                })
                save_audit_event({
                    "ticket_id": hold["ticket_id"],
                    "event_type": "HOLD_EXPIRED",
                    "actor_role": "SYSTEM",
                    "action": f"Hold {hold['hold_id']} expired after {HOLD_MINUTES} minutes.",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "tenant_id": hold.get("tenant_id", "atlanta-default"),
                })
    return hold


def create_holds_for_plan(
    plan: Dict[str, Any],
    ticket: Dict[str, Any],
    approver_role: str = "COORDINATOR",
    request_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Create transactional 10-minute holds for all allocations on an approved plan.

    Raises HTTP 409 Conflict on double-approve or duplicate holds.
    """
    ticket_id = ticket["ticket_id"]
    plan_id = plan["plan_id"]
    tenant_id = ticket.get("tenant_id", "atlanta-default")

    # Double-hold / Double-approve guard:
    # Check if ticket already has active holds or if plan is already approved/held
    existing_holds = list_firestore_holds(ticket_id=ticket_id)
    # Check if holds for this specific plan were already created
    if any(h.get("plan_id") == plan_id for h in existing_holds):
        raise HTTPException(
            status_code=409,
            detail=f"Holds for plan {plan_id} on ticket {ticket_id} have already been created. Double-hold / double-approve not permitted.",
        )

    # Active holds already on the ticket (e.g. non-declined pantries carried forward during a replan)
    existing_active_by_rec = {
        int(h["recipient_id"]): h
        for h in existing_holds
        if h.get("status") in (HoldStatus.ACTIVE.value, HoldStatus.CONFIRMED.value)
    }

    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=HOLD_MINUTES)
    created_holds = []
    hold_ids = []

    allocations = plan.get("allocations", [])
    for alloc in allocations:
        rec_id = int(alloc["recipient_id"])
        qty = float(alloc["quantity"])
        raw_unit = alloc.get("quantity_unit", "PALLETS")
        unit = raw_unit.value if hasattr(raw_unit, "value") else str(raw_unit)

        if unit == QuantityUnit.CRATES.value:
            pallets_eq = round(qty / CRATES_PER_PALLET, 2)
        else:
            pallets_eq = round(qty, 2)

        if rec_id in existing_active_by_rec:
            # Kept pantry from prior plan version — carry forward and associate with new plan_id
            existing_hold = existing_active_by_rec[rec_id]
            update_firestore_hold(existing_hold["hold_id"], {"plan_id": plan_id})
            update_allocation(f"alloc-{existing_hold['hold_id']}", {"plan_id": plan_id})
            created_holds.append(existing_hold)
            hold_ids.append(existing_hold["hold_id"])
        else:
            # Newly allocated / promoted pantry — create new 10-minute hold
            hold_id = f"hold-{ticket_id}-{rec_id}-{uuid.uuid4().hex[:6]}"
            alloc_id = f"alloc-{hold_id}"

            hold_doc = {
                "hold_id": hold_id,
                "ticket_id": ticket_id,
                "plan_id": plan_id,
                "recipient_id": int(rec_id),
                "quantity": qty,
                "quantity_unit": unit,
                "pallets_equivalent": pallets_eq,
                "status": HoldStatus.ACTIVE.value,
                "started_at": now.isoformat(),
                "expires_at": expires_at.isoformat(),
                "confirmed_at": None,
                "request_id": request_id or hold_id,
                "tenant_id": tenant_id,
            }
            save_hold(hold_doc)
            created_holds.append(hold_doc)
            hold_ids.append(hold_id)

            # Create corresponding allocation in allocations collection (assignment + fairness ledger record)
            alloc_doc = {
                "allocation_id": alloc_id,
                "hold_id": hold_id,
                "recipient_id": int(rec_id),
                "ticket_id": ticket_id,
                "plan_id": plan_id,
                "quantity": qty,
                "quantity_unit": unit,
                "pallets_equivalent": pallets_eq,
                "status": AllocationStatus.CONFIRMED.value,  # assigned on approval
                "allocated_at": now.isoformat(),
                "confirmed_at": None,
                "completed_at": None,
                "tract_geo_id": str(alloc.get("tract_geo_id", "UNKNOWN")),
                "need_score_at_allocation": float(alloc.get("need_score", 50.0)),
                "tenant_id": tenant_id,
            }
            save_allocation(alloc_doc)

            # Notify recipient
            save_notification({
                "recipient_role": "RECIPIENT",
                "recipient_org_id": str(rec_id),
                "ticket_id": ticket_id,
                "event": NotificationEvent.OFFER_MADE.value,
                "created_at": now.isoformat(),
                "read_status": False,
                "tenant_id": tenant_id,
            })

            # Audit entry
            save_audit_event({
                "ticket_id": ticket_id,
                "plan_version": plan.get("plan_version", 1),
                "event_type": "HOLD_CREATED",
                "actor_role": approver_role,
                "action": f"Created 10-minute hold {hold_id} for recipient {rec_id} ({qty} {unit}).",
                "timestamp": now.isoformat(),
                "request_id": request_id,
                "tenant_id": tenant_id,
            })

    # Update ticket checkpoint fields
    update_ticket(ticket_id, {
        "step": TicketStep.HELD.value,
        "holds_already_started": hold_ids,
        "step_started_at": now.isoformat(),
    })

    return created_holds


def get_holds_for_ticket(ticket_id: str) -> List[Dict[str, Any]]:
    """Retrieve all holds for a ticket, updating expired records if needed."""
    raw_holds = list_firestore_holds(ticket_id=ticket_id)
    return [_check_and_apply_expiry(h) for h in raw_holds]


def get_hold(hold_id: str) -> Dict[str, Any]:
    """Retrieve a single hold record by hold_id."""
    hold = get_firestore_hold(hold_id)
    if not hold:
        raise HTTPException(status_code=404, detail=f"Hold {hold_id} not found.")
    return _check_and_apply_expiry(hold)


def confirm_hold(hold_id: str, recipient_id: int) -> Dict[str, Any]:
    """Recipient accepts/confirms an active hold (ACTIVE -> CONFIRMED)."""
    hold = get_hold(hold_id)
    if int(hold["recipient_id"]) != int(recipient_id):
        raise HTTPException(
            status_code=404,
            detail="Hold does not belong to specified recipient.",
        )

    current_status = hold.get("status")
    if current_status != HoldStatus.ACTIVE.value and current_status != HoldStatus.ACTIVE:
        raise HTTPException(
            status_code=409,
            detail=f"Hold {hold_id} cannot be confirmed because status is '{current_status}'.",
        )

    now = datetime.now(timezone.utc)
    update_firestore_hold(hold_id, {
        "status": HoldStatus.CONFIRMED.value,
        "confirmed_at": now.isoformat(),
    })
    hold["status"] = HoldStatus.CONFIRMED.value
    hold["confirmed_at"] = now.isoformat()

    # Update matching allocation confirmed_at
    alloc_id = f"alloc-{hold_id}"
    update_allocation(alloc_id, {
        "status": AllocationStatus.CONFIRMED.value,
        "confirmed_at": now.isoformat(),
    })

    # Notifications & Audit
    ticket_id = hold["ticket_id"]
    save_notification({
        "recipient_role": "COORDINATOR",
        "recipient_org_id": "COORDINATOR",
        "ticket_id": ticket_id,
        "event": NotificationEvent.CONFIRMED.value,
        "created_at": now.isoformat(),
        "read_status": False,
        "tenant_id": hold.get("tenant_id", "atlanta-default"),
    })
    save_audit_event({
        "ticket_id": ticket_id,
        "event_type": "HOLD_CONFIRMED",
        "actor_role": "RECIPIENT",
        "action": f"Recipient {recipient_id} confirmed hold {hold_id}.",
        "timestamp": now.isoformat(),
        "tenant_id": hold.get("tenant_id", "atlanta-default"),
    })

    # Check if all holds for ticket are confirmed; if so, advance ticket step to CONFIRMED
    all_ticket_holds = get_holds_for_ticket(ticket_id)
    if all(h.get("status") == HoldStatus.CONFIRMED.value for h in all_ticket_holds):
        update_ticket(ticket_id, {
            "step": TicketStep.CONFIRMED.value,
            "step_started_at": now.isoformat(),
        })

    return hold


def release_hold(hold_id: str, reason: str) -> Dict[str, Any]:
    """Release an active hold (ACTIVE -> RELEASED), freeing capacity."""
    hold = get_hold(hold_id)
    update_firestore_hold(hold_id, {"status": HoldStatus.RELEASED.value})
    hold["status"] = HoldStatus.RELEASED.value

    now = datetime.now(timezone.utc)
    save_audit_event({
        "ticket_id": hold["ticket_id"],
        "event_type": "HOLD_RELEASED",
        "actor_role": "SYSTEM",
        "action": f"Hold {hold_id} released. Reason: {reason}",
        "timestamp": now.isoformat(),
        "tenant_id": hold.get("tenant_id", "atlanta-default"),
    })
    return hold


def release_all_holds_for_ticket(ticket_id: str, reason: str) -> None:
    """Release all active/held holds when a ticket is cancelled."""
    holds = get_holds_for_ticket(ticket_id)
    now = datetime.now(timezone.utc)
    for h in holds:
        if h.get("status") in (HoldStatus.ACTIVE.value, HoldStatus.CONFIRMED.value):
            update_firestore_hold(h["hold_id"], {"status": HoldStatus.RELEASED.value})
            save_notification({
                "recipient_role": "RECIPIENT",
                "recipient_org_id": str(h["recipient_id"]),
                "ticket_id": ticket_id,
                "event": NotificationEvent.CANCEL.value,
                "created_at": now.isoformat(),
                "read_status": False,
                "tenant_id": h.get("tenant_id", "atlanta-default"),
            })
    save_audit_event({
        "ticket_id": ticket_id,
        "event_type": "ALL_HOLDS_RELEASED",
        "actor_role": "COORDINATOR",
        "action": f"All holds released for ticket {ticket_id}. Reason: {reason}",
        "timestamp": now.isoformat(),
        "tenant_id": "atlanta-default",
    })

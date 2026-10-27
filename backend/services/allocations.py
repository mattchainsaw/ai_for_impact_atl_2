"""Allocations Service for RescueGuard (Phase 4).

NOTE ON HOLD VS ALLOCATION MAPPING (Part 2, line 710):
- A `hold` drives the recipient inbox lock state (transactional 10-minute hold window).
- An `allocation` drives donor status and the persistent fairness ledger (tracks completed,
  declined, expired, and no-show outcomes for rotation and equity).
Do not merge the two stores.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from fastapi import HTTPException

from backend.db.firestore import (
    get_allocation as get_firestore_allocation,
    update_allocation as update_firestore_allocation,
    list_allocations as list_firestore_allocations,
    get_ticket,
    update_ticket,
    save_notification,
    save_audit_event,
)
from schemas.enums import AllocationStatus, NotificationEvent, TicketStep, TicketStatus


def get_allocation(allocation_id: str) -> Dict[str, Any]:
    """Retrieve an allocation by ID."""
    alloc = get_firestore_allocation(allocation_id)
    if not alloc:
        raise HTTPException(status_code=404, detail=f"Allocation {allocation_id} not found.")
    return alloc


def complete_allocation(allocation_id: str, notes: Optional[str] = None) -> Dict[str, Any]:
    """Mark an allocation complete (pickup actually took place).

    Updates ticket status to COMPLETED when all allocations for that ticket are completed.
    """
    alloc = get_allocation(allocation_id)
    now = datetime.now(timezone.utc)

    update_firestore_allocation(allocation_id, {
        "status": AllocationStatus.COMPLETED.value,
        "completed_at": now.isoformat(),
    })
    alloc["status"] = AllocationStatus.COMPLETED.value
    alloc["completed_at"] = now.isoformat()

    ticket_id = alloc["ticket_id"]
    save_audit_event({
        "ticket_id": ticket_id,
        "event_type": "ALLOCATION_COMPLETED",
        "actor_role": "COORDINATOR",
        "action": f"Allocation {allocation_id} marked completed. Notes: {notes or 'N/A'}",
        "timestamp": now.isoformat(),
        "tenant_id": alloc.get("tenant_id", "atlanta-default"),
    })
    save_notification({
        "recipient_role": "DONOR",
        "recipient_org_id": "DONOR",
        "ticket_id": ticket_id,
        "event": NotificationEvent.COMPLETED.value,
        "created_at": now.isoformat(),
        "read_status": False,
        "tenant_id": alloc.get("tenant_id", "atlanta-default"),
    })

    # Check if all allocations for this ticket are completed
    ticket_allocs = list_firestore_allocations(ticket_id=ticket_id)
    if all(a.get("status") == AllocationStatus.COMPLETED.value for a in ticket_allocs):
        update_ticket(ticket_id, {
            "step": TicketStep.COMPLETED.value,
            "status": TicketStatus.COMPLETED.value,
            "step_started_at": now.isoformat(),
        })

    return alloc


def no_show_allocation(allocation_id: str, reason: str) -> Dict[str, Any]:
    """Record a recipient no-show in the allocations fairness ledger."""
    alloc = get_allocation(allocation_id)
    now = datetime.now(timezone.utc)

    update_firestore_allocation(allocation_id, {
        "status": AllocationStatus.NO_SHOW.value,
    })
    alloc["status"] = AllocationStatus.NO_SHOW.value

    ticket_id = alloc["ticket_id"]
    save_audit_event({
        "ticket_id": ticket_id,
        "event_type": "ALLOCATION_NO_SHOW",
        "actor_role": "COORDINATOR",
        "action": f"Recipient {alloc['recipient_id']} marked NO_SHOW for allocation {allocation_id}. Reason: {reason}",
        "timestamp": now.isoformat(),
        "tenant_id": alloc.get("tenant_id", "atlanta-default"),
    })

    return alloc


def list_allocations(
    ticket_id: Optional[str] = None,
    recipient_id: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """List allocations filtered by ticket_id or recipient_id."""
    return list_firestore_allocations(ticket_id=ticket_id, recipient_id=recipient_id)

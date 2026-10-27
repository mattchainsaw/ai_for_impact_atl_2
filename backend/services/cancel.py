"""Ticket Cancellation Service for RescueGuard (Phase 4).

Releases all active holds internally, notifies all allocated recipients
with 'offer withdrawn' notifications, and transitions ticket to CANCELLED.
"""

from datetime import datetime, timezone
from typing import Any, Dict, Optional
from fastapi import HTTPException

from backend.db.firestore import (
    get_ticket,
    update_ticket,
    get_posting,
    save_audit_event,
)
from backend.services.holds import release_all_holds_for_ticket
from schemas.enums import Role, TicketStep, TicketStatus


def cancel_ticket(
    ticket_id: str,
    reason: str,
    role: Role = Role.COORDINATOR,
    current_org_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Cancel a rescue ticket, releasing all holds and notifying recipients."""
    ticket = get_ticket(ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail=f"Ticket {ticket_id} not found.")

    # Persona check: If donor, must own the posting
    if role == Role.DONOR:
        posting = get_posting(ticket.get("posting_id", ""))
        if not posting or (current_org_id and posting.get("donor_id") != current_org_id):
            raise HTTPException(
                status_code=404,
                detail="Ticket does not belong to current donor.",
            )

    # 1. Release all holds internally and notify recipients
    release_all_holds_for_ticket(ticket_id, reason=reason)

    # 2. Update ticket status
    now = datetime.now(timezone.utc)
    update_ticket(ticket_id, {
        "step": TicketStep.CANCELLED.value,
        "status": TicketStatus.CANCELLED.value,
        "step_started_at": now.isoformat(),
    })
    ticket["step"] = TicketStep.CANCELLED.value
    ticket["status"] = TicketStatus.CANCELLED.value
    ticket["step_started_at"] = now.isoformat()

    # 3. Audit log
    role_val = role.value if hasattr(role, "value") else str(role)
    save_audit_event({
        "ticket_id": ticket_id,
        "event_type": "TICKET_CANCELLED",
        "actor_role": role_val,
        "action": f"Ticket {ticket_id} cancelled. Reason: {reason}",
        "timestamp": now.isoformat(),
        "tenant_id": ticket.get("tenant_id", "atlanta-default"),
    })

    return ticket

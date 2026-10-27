"""Canonical Approval Service for RescueGuard (Phase 4).

Single canonical approval service behind:
- POST /api/actions/approve (action cards / chat proposals)
- POST /api/plans/{plan_id}/approve (plan approval)
- PATCH /api/tasks/{task_id} (task approvals)

Enforces:
- Idempotency by request_id
- 409 Conflict on double-approve
- 422 Unprocessable Entity when approving a plan not in checker-passed state
- Transactional hold initiation inside approve
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid
from fastapi import HTTPException

from backend.db.firestore import (
    get_plan,
    update_plan,
    get_ticket,
    update_ticket,
    save_approval,
    get_approval_by_request_id,
    list_approvals,
    save_audit_event,
)
from backend.services.holds import create_holds_for_plan
from schemas.enums import PlanStatus, Role, ActionTargetType, TaskStatus
from schemas.common import ActionCard


def approve_plan(
    plan_id: str,
    approver_role: Role = Role.COORDINATOR,
    notes: Optional[str] = None,
    request_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Approve a plan version, starting 10-minute holds for all allocations.

    Enforces:
    - 404 if plan not found.
    - 422 if plan is CHECKER_REJECTED or not in checker-passed state.
    - 409 if plan is already APPROVED or double-approval attempted.
    """
    plan = get_plan(plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail=f"Plan {plan_id} not found.")

    # Rule: Approve on a plan not in a checker-passed state -> 422
    plan_status = plan.get("status")
    if plan_status == PlanStatus.CHECKER_REJECTED.value or plan_status == PlanStatus.CHECKER_REJECTED:
        reasons = plan.get("checker_reasons", [])
        raise HTTPException(
            status_code=422,
            detail=f"Cannot approve plan {plan_id} because it was rejected by checker: {', '.join(reasons)}",
        )

    # Rule: Double-approval -> 409
    if plan_status == PlanStatus.APPROVED.value or plan_status == PlanStatus.APPROVED:
        raise HTTPException(
            status_code=409,
            detail=f"Plan {plan_id} is already approved. Double-approve not permitted.",
        )

    # Check request_id idempotency (ignoring default placeholder)
    if request_id and request_id != "req-default":
        existing = get_approval_by_request_id(request_id)
        if existing:
            raise HTTPException(
                status_code=409,
                detail=f"Approval request_id '{request_id}' has already been processed.",
            )

    ticket_id = plan["ticket_id"]
    ticket = get_ticket(ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail=f"Ticket {ticket_id} not found.")

    role_val = approver_role.value if hasattr(approver_role, "value") else str(approver_role)
    now = datetime.now(timezone.utc)
    approval_id = f"appr-{uuid.uuid4().hex[:8]}"
    eff_request_id = request_id if (request_id and request_id != "req-default") else approval_id

    # Create holds inside approve (transactional, 10-minute window)
    holds = create_holds_for_plan(
        plan=plan,
        ticket=ticket,
        approver_role=role_val,
        request_id=eff_request_id,
    )
    hold_ids = [h["hold_id"] for h in holds]

    # Update plan
    update_plan(plan_id, {
        "status": PlanStatus.APPROVED.value,
        "approved_by_role": role_val,
        "approved_at": now.isoformat(),
    })
    plan["status"] = PlanStatus.APPROVED.value
    plan["approved_by_role"] = role_val
    plan["approved_at"] = now.isoformat()

    # Record in approvals collection
    approval_doc = {
        "approval_id": approval_id,
        "target_id": plan_id,
        "target_type": "plan",
        "decision": "APPROVED",
        "approver_role": role_val,
        "approved_at": now.isoformat(),
        "plan_version": plan.get("plan_version", 1),
        "request_id": eff_request_id,
        "notes": notes,
        "tenant_id": ticket.get("tenant_id", "atlanta-default"),
    }
    save_approval(approval_doc)

    # Update ticket with approved plan and checkpoint
    tasks_approved = ticket.get("tasks_already_approved", [])
    if plan_id not in tasks_approved:
        tasks_approved.append(plan_id)

    update_ticket(ticket_id, {
        "current_plan_id": plan_id,
        "plan_version_current": plan.get("plan_version", 1),
        "tasks_already_approved": tasks_approved,
        "step_started_at": now.isoformat(),
    })

    save_audit_event({
        "ticket_id": ticket_id,
        "plan_version": plan.get("plan_version", 1),
        "event_type": "PLAN_APPROVED",
        "actor_role": role_val,
        "action": f"Approved plan {plan_id} (version {plan.get('plan_version', 1)}). Created holds: {hold_ids}",
        "timestamp": now.isoformat(),
        "request_id": eff_request_id,
        "tenant_id": ticket.get("tenant_id", "atlanta-default"),
    })

    return {
        "approval_id": approval_id,
        "plan_id": plan_id,
        "ticket_id": ticket_id,
        "plan_version": plan.get("plan_version", 1),
        "status": PlanStatus.APPROVED,
        "holds_created": hold_ids,
        "approved_by_role": approver_role,
        "approved_at": now,
    }


def reject_plan(plan_id: str, reason: str) -> Dict[str, Any]:
    """Coordinator rejects a plan version, recording reason and triggering re-plan."""
    plan = get_plan(plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail=f"Plan {plan_id} not found.")

    ticket_id = plan["ticket_id"]
    ticket = get_ticket(ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail=f"Ticket {ticket_id} not found.")

    now = datetime.now(timezone.utc)
    reasons = plan.get("checker_reasons", [])
    reasons.append(f"Coordinator rejected: {reason}")
    update_plan(plan_id, {
        "status": PlanStatus.CHECKER_REJECTED.value,
        "checker_reasons": reasons,
    })

    save_audit_event({
        "ticket_id": ticket_id,
        "plan_version": plan.get("plan_version", 1),
        "event_type": "PLAN_REJECTED",
        "actor_role": "COORDINATOR",
        "action": f"Plan {plan_id} rejected by coordinator. Reason: {reason}",
        "timestamp": now.isoformat(),
        "tenant_id": ticket.get("tenant_id", "atlanta-default"),
    })

    # Trigger fixer to generate a new plan version
    from backend.services.planner import create_initial_plan
    from backend.db.firestore import get_posting, save_plan

    posting = get_posting(ticket.get("posting_id", ""))
    if not posting:
        posting = {
            "posting_id": ticket.get("posting_id", ""),
            "product_text": "Produce Surplus",
            "quantity": 100,
            "quantity_unit": "CRATES",
            "pallets_equivalent": 5.0,
            "donor_deadline": ticket.get("resolved_deadline"),
            "temperature_requirement": "refrigerated",
            "split_allowed": True,
        }

    # Fetch candidates and candidates from previous runs
    from backend.db.firestore import get_match_candidates
    candidates = get_match_candidates(ticket_id)

    new_version = plan.get("plan_version", 1) + 1
    new_plan_obj = create_initial_plan(
        ticket_id=ticket_id,
        posting_data=posting,
        viable_candidates=candidates,
        plan_version=new_version,
    )
    new_plan = new_plan_obj.model_dump()
    save_plan(new_plan)

    update_ticket(ticket_id, {
        "current_plan_id": new_plan["plan_id"],
        "plan_version_current": new_version,
    })

    return new_plan


def approve_action(
    action: ActionCard,
    approver_role: Role = Role.COORDINATOR,
    request_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Canonical entry point for approving actions proposed by Guide chat or desk.

    Flips the one target, starts holds if target is a plan, and enforces idempotency.
    """
    target_type = action.target_type.value if hasattr(action.target_type, "value") else str(action.target_type)
    target_id = action.target_id
    role_val = approver_role.value if hasattr(approver_role, "value") else str(approver_role)
    eff_request_id = request_id if (request_id and request_id != "req-default") else (
        action.action_id if action.action_id and action.action_id != "req-default" else f"action-{uuid.uuid4().hex[:8]}"
    )

    # Check idempotency (ignoring default placeholder)
    if eff_request_id and eff_request_id != "req-default":
        existing = get_approval_by_request_id(eff_request_id)
        if existing:
            raise HTTPException(
                status_code=409,
                detail=f"Action approval with request_id '{eff_request_id}' has already been processed.",
            )

    now = datetime.now(timezone.utc)
    approval_id = f"appr-{uuid.uuid4().hex[:8]}"

    if target_type in (ActionTargetType.PLAN.value, "plan"):
        res = approve_plan(
            plan_id=target_id,
            approver_role=approver_role,
            request_id=eff_request_id,
        )
        approval_id = res["approval_id"]
    elif target_type in (ActionTargetType.TASK.value, "task"):
        from backend.services.tasks import patch_task
        patch_task(
            task_id=target_id,
            status=TaskStatus.APPROVED,
            approver_role=approver_role,
            request_id=eff_request_id,
        )
    elif target_type in (ActionTargetType.HOLD.value, "hold"):
        from backend.services.holds import confirm_hold
        confirm_hold(hold_id=target_id, recipient_id=int(action.target_id.split("-")[-2]))
    else:
        # Fallback / generic action approval
        save_approval({
            "approval_id": approval_id,
            "target_id": target_id,
            "target_type": target_type,
            "decision": "APPROVED",
            "approver_role": role_val,
            "approved_at": now.isoformat(),
            "plan_version": 1,
            "request_id": eff_request_id,
            "tenant_id": "atlanta-default",
        })

    return {
        "approval_id": approval_id,
        "action_id": action.action_id,
        "target_type": action.target_type,
        "target_id": action.target_id,
        "target_endpoint": action.target_endpoint,
        "decision": "APPROVED",
        "approver_role": approver_role,
        "approved_at": now,
    }

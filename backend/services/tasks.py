"""Tasks Service for RescueGuard (Phase 4).

Manages coordinator gap tasks and system tasks:
- APPROVE_PLAN, CONFIRM_PICKUP, UPDATE_PROFILE, CHECK_CONTRADICTION, etc.
- PATCH /api/tasks/{task_id} delegates to approval service with idempotency by request_id.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid
from fastapi import HTTPException

from backend.db.firestore import (
    save_task,
    get_task as get_firestore_task,
    update_task as update_firestore_task,
    list_tasks as list_firestore_tasks,
    save_approval,
    get_approval_by_request_id,
    save_audit_event,
)
from schemas.enums import TaskType, TaskStatus, Role


def create_task(
    ticket_id: str,
    task_type: TaskType,
    owner_role: Role = Role.COORDINATOR,
    description: str = "",
    plan_id: Optional[str] = None,
    tenant_id: str = "atlanta-default",
) -> Dict[str, Any]:
    """Create a new coordinator or system task."""
    task_id = f"task-{uuid.uuid4().hex[:8]}"
    now = datetime.now(timezone.utc)
    type_val = task_type.value if hasattr(task_type, "value") else str(task_type)
    role_val = owner_role.value if hasattr(owner_role, "value") else str(owner_role)

    task_doc = {
        "task_id": task_id,
        "ticket_id": ticket_id,
        "plan_id": plan_id,
        "task_type": type_val,
        "owner_role": role_val,
        "status": TaskStatus.OPEN.value,
        "description": description,
        "created_at": now.isoformat(),
        "tenant_id": tenant_id,
    }
    save_task(task_doc)

    save_audit_event({
        "ticket_id": ticket_id,
        "event_type": "TASK_CREATED",
        "actor_role": role_val,
        "action": f"Created task {task_id} ({type_val}): {description}",
        "timestamp": now.isoformat(),
        "tenant_id": tenant_id,
    })

    return task_doc


def get_task(task_id: str) -> Dict[str, Any]:
    """Retrieve a task by ID."""
    task = get_firestore_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found.")
    return task


def list_tasks(
    ticket_id: Optional[str] = None,
    owner_role: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """List tasks filtered by ticket_id or owner_role."""
    return list_firestore_tasks(ticket_id=ticket_id, owner_role=owner_role)


def patch_task(
    task_id: str,
    status: TaskStatus,
    approver_role: Role = Role.COORDINATOR,
    request_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Update task status, delegating to approval service if status is APPROVED."""
    task = get_task(task_id)
    now = datetime.now(timezone.utc)
    status_val = status.value if hasattr(status, "value") else str(status)
    role_val = approver_role.value if hasattr(approver_role, "value") else str(approver_role)

    if status_val == TaskStatus.APPROVED.value:
        eff_request_id = request_id if (request_id and request_id != "req-default") else f"req-task-{task_id}-{uuid.uuid4().hex[:6]}"
        # Idempotency check (ignoring default placeholder)
        if request_id and request_id != "req-default":
            existing = get_approval_by_request_id(eff_request_id)
            if existing:
                raise HTTPException(
                    status_code=409,
                    detail=f"Task approval with request_id '{eff_request_id}' has already been processed.",
                )

        # Record approval
        approval_id = f"appr-{uuid.uuid4().hex[:8]}"
        save_approval({
            "approval_id": approval_id,
            "target_id": task_id,
            "target_type": "task",
            "decision": "APPROVED",
            "approver_role": role_val,
            "approved_at": now.isoformat(),
            "plan_version": 1,
            "request_id": eff_request_id,
            "tenant_id": task.get("tenant_id", "atlanta-default"),
        })

        save_audit_event({
            "ticket_id": task["ticket_id"],
            "event_type": "TASK_APPROVED",
            "actor_role": role_val,
            "action": f"Task {task_id} marked APPROVED.",
            "timestamp": now.isoformat(),
            "request_id": eff_request_id,
            "tenant_id": task.get("tenant_id", "atlanta-default"),
        })

    update_firestore_task(task_id, {"status": status_val})
    task["status"] = status_val
    return task

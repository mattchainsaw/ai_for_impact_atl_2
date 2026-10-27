"""Firestore Native Client & Collection Helpers for RescueGuard.

Manages collections for live tickets, plans, holds, candidates, recall checks,
and distance caching.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter

from backend.app.config import get_settings


_firestore_client: Optional[firestore.Client] = None


def get_firestore_client() -> firestore.Client:
    """Return singleton Firestore Client for the configured project."""
    global _firestore_client
    if _firestore_client is None:
        settings = get_settings()
        _firestore_client = firestore.Client(project=settings.google_cloud_project)
    return _firestore_client


def save_match_candidates(ticket_id: str, candidates: List[Dict[str, Any]]) -> None:
    """Save match candidate records to Firestore match_candidates collection."""
    db = get_firestore_client()
    batch = db.batch()
    col = db.collection("match_candidates")
    for c in candidates:
        doc_id = f"{ticket_id}_{c['recipient_id']}"
        ref = col.document(doc_id)
        batch.set(ref, c)
    batch.commit()


def get_match_candidates(ticket_id: str) -> List[Dict[str, Any]]:
    """Retrieve match candidate records for a ticket."""
    db = get_firestore_client()
    docs = db.collection("match_candidates").where(filter=FieldFilter("ticket_id", "==", ticket_id)).stream()
    return [doc.to_dict() for doc in docs]


def save_recall_check(check: Dict[str, Any]) -> None:
    """Save a recall check record to Firestore recall_checks collection."""
    db = get_firestore_client()
    doc_id = check.get("check_id") or f"{check['ticket_id']}_{int(datetime.now(timezone.utc).timestamp())}"
    db.collection("recall_checks").document(doc_id).set(check)


def get_recall_checks(ticket_id: str) -> List[Dict[str, Any]]:
    """Retrieve all recall checks for a ticket, ordered by check time."""
    db = get_firestore_client()
    docs = db.collection("recall_checks").where(filter=FieldFilter("ticket_id", "==", ticket_id)).stream()
    checks = [doc.to_dict() for doc in docs]
    return sorted(checks, key=lambda x: str(x.get("checked_at", "")), reverse=True)


def get_cached_distance(origin_zip: str, dest_zip: str) -> Optional[float]:
    """Look up cached travel distance (km) between two ZIP codes in distance_pairs."""
    db = get_firestore_client()
    key = f"{origin_zip.strip()}_{dest_zip.strip()}"
    doc = db.collection("distance_pairs").document(key).get()
    if doc.exists:
        data = doc.to_dict()
        return float(data.get("distance_km", 0.0))
    return None


def cache_distance_pair(
    origin_zip: str,
    dest_zip: str,
    distance_km: float,
    source: str = "HAVERSINE_FALLBACK",
) -> None:
    """Save a distance pair cache record to Firestore distance_pairs collection."""
    db = get_firestore_client()
    key = f"{origin_zip.strip()}_{dest_zip.strip()}"
    db.collection("distance_pairs").document(key).set({
        "pair_key": key,
        "origin_zip": origin_zip.strip(),
        "dest_zip": dest_zip.strip(),
        "distance_km": round(float(distance_km), 2),
        "source": source,
        "approximate": True,
        "cached_at": datetime.now(timezone.utc).isoformat(),
    })


# ============================================================================
# Postings, Tickets, and Plans CRUD Helpers (Phase 3)
# ============================================================================


def save_posting(posting: Dict[str, Any]) -> None:
    """Save a live donor posting to Firestore postings collection."""
    db = get_firestore_client()
    doc_id = str(posting["posting_id"])
    db.collection("postings").document(doc_id).set(posting)


def get_posting(posting_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve a live donor posting from Firestore postings collection."""
    db = get_firestore_client()
    doc = db.collection("postings").document(str(posting_id)).get()
    if doc.exists:
        return doc.to_dict()
    return None


def list_postings() -> List[Dict[str, Any]]:
    """List all live donor postings from Firestore."""
    db = get_firestore_client()
    docs = db.collection("postings").stream()
    return [doc.to_dict() for doc in docs]


def save_ticket(ticket: Dict[str, Any]) -> None:
    """Save a ticket to Firestore tickets collection."""
    db = get_firestore_client()
    doc_id = str(ticket["ticket_id"])
    db.collection("tickets").document(doc_id).set(ticket)


def get_ticket(ticket_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve a ticket from Firestore tickets collection."""
    db = get_firestore_client()
    doc = db.collection("tickets").document(str(ticket_id)).get()
    if doc.exists:
        return doc.to_dict()
    return None


def update_ticket(ticket_id: str, updates: Dict[str, Any]) -> None:
    """Update fields on an existing ticket."""
    db = get_firestore_client()
    db.collection("tickets").document(str(ticket_id)).update(updates)


def list_tickets() -> List[Dict[str, Any]]:
    """List all tickets from Firestore."""
    db = get_firestore_client()
    docs = db.collection("tickets").stream()
    return [doc.to_dict() for doc in docs]


def save_plan(plan: Dict[str, Any]) -> None:
    """Save a plan to Firestore plans collection."""
    db = get_firestore_client()
    doc_id = str(plan["plan_id"])
    db.collection("plans").document(doc_id).set(plan)


def get_plan(plan_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve a plan from Firestore plans collection."""
    db = get_firestore_client()
    doc = db.collection("plans").document(str(plan_id)).get()
    if doc.exists:
        return doc.to_dict()
    return None


def update_plan(plan_id: str, updates: Dict[str, Any]) -> None:
    """Update fields on an existing plan."""
    db = get_firestore_client()
    db.collection("plans").document(str(plan_id)).update(updates)


def list_plans(ticket_id: str) -> List[Dict[str, Any]]:
    """List all plans for a ticket ordered by plan_version."""
    db = get_firestore_client()
    docs = db.collection("plans").where(filter=FieldFilter("ticket_id", "==", ticket_id)).stream()
    plans = [doc.to_dict() for doc in docs]
    return sorted(plans, key=lambda p: int(p.get("plan_version", 1)))


# ============================================================================
# Holds, Allocations, Tasks, Approvals, Chat & Audit CRUD (Phase 4)
# ============================================================================


def save_hold(hold: Dict[str, Any]) -> None:
    """Save a hold record to Firestore holds collection."""
    db = get_firestore_client()
    doc_id = str(hold["hold_id"])
    db.collection("holds").document(doc_id).set(hold)


def get_hold(hold_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve a hold record from Firestore holds collection."""
    db = get_firestore_client()
    doc = db.collection("holds").document(str(hold_id)).get()
    if doc.exists:
        return doc.to_dict()
    return None


def update_hold(hold_id: str, updates: Dict[str, Any]) -> None:
    """Update fields on an existing hold."""
    db = get_firestore_client()
    db.collection("holds").document(str(hold_id)).update(updates)


def list_holds(
    ticket_id: Optional[str] = None,
    recipient_id: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """List holds filtered by ticket_id or recipient_id."""
    db = get_firestore_client()
    query = db.collection("holds")
    if ticket_id is not None:
        query = query.where(filter=FieldFilter("ticket_id", "==", ticket_id))
    if recipient_id is not None:
        query = query.where(filter=FieldFilter("recipient_id", "==", int(recipient_id)))
    docs = query.stream()
    return [doc.to_dict() for doc in docs]


def save_allocation(allocation: Dict[str, Any]) -> None:
    """Save an allocation record to Firestore allocations collection."""
    db = get_firestore_client()
    doc_id = str(allocation["allocation_id"])
    db.collection("allocations").document(doc_id).set(allocation)


def get_allocation(allocation_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve an allocation record from Firestore allocations collection."""
    db = get_firestore_client()
    doc = db.collection("allocations").document(str(allocation_id)).get()
    if doc.exists:
        return doc.to_dict()
    return None


def update_allocation(allocation_id: str, updates: Dict[str, Any]) -> None:
    """Update fields on an existing allocation."""
    db = get_firestore_client()
    db.collection("allocations").document(str(allocation_id)).update(updates)


def list_allocations(
    ticket_id: Optional[str] = None,
    recipient_id: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """List allocations filtered by ticket_id or recipient_id."""
    db = get_firestore_client()
    query = db.collection("allocations")
    if ticket_id is not None:
        query = query.where(filter=FieldFilter("ticket_id", "==", ticket_id))
    if recipient_id is not None:
        query = query.where(filter=FieldFilter("recipient_id", "==", int(recipient_id)))
    docs = query.stream()
    return [doc.to_dict() for doc in docs]


def save_task(task: Dict[str, Any]) -> None:
    """Save a task record to Firestore tasks collection."""
    db = get_firestore_client()
    doc_id = str(task["task_id"])
    db.collection("tasks").document(doc_id).set(task)


def get_task(task_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve a task record from Firestore tasks collection."""
    db = get_firestore_client()
    doc = db.collection("tasks").document(str(task_id)).get()
    if doc.exists:
        return doc.to_dict()
    return None


def update_task(task_id: str, updates: Dict[str, Any]) -> None:
    """Update fields on an existing task."""
    db = get_firestore_client()
    db.collection("tasks").document(str(task_id)).update(updates)


def list_tasks(
    ticket_id: Optional[str] = None,
    owner_role: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """List tasks filtered by ticket_id or owner_role."""
    db = get_firestore_client()
    query = db.collection("tasks")
    if ticket_id is not None:
        query = query.where(filter=FieldFilter("ticket_id", "==", ticket_id))
    if owner_role is not None:
        query = query.where(filter=FieldFilter("owner_role", "==", owner_role))
    docs = query.stream()
    return [doc.to_dict() for doc in docs]


def save_approval(approval: Dict[str, Any]) -> None:
    """Save an approval record to Firestore approvals collection."""
    db = get_firestore_client()
    doc_id = str(approval["approval_id"])
    db.collection("approvals").document(doc_id).set(approval)


def get_approval(approval_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve an approval record by approval_id."""
    db = get_firestore_client()
    doc = db.collection("approvals").document(str(approval_id)).get()
    if doc.exists:
        return doc.to_dict()
    return None


def get_approval_by_request_id(request_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve an approval record by request_id (for idempotency checks)."""
    db = get_firestore_client()
    docs = db.collection("approvals").where(filter=FieldFilter("request_id", "==", request_id)).limit(1).stream()
    for doc in docs:
        return doc.to_dict()
    return None


def list_approvals(target_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """List approvals, optionally filtered by target_id / plan_id."""
    db = get_firestore_client()
    query = db.collection("approvals")
    if target_id is not None:
        query = query.where(filter=FieldFilter("target_id", "==", target_id))
    docs = query.stream()
    return [doc.to_dict() for doc in docs]


def save_conversation(conv: Dict[str, Any]) -> None:
    """Save or replace a conversation record in Firestore conversations collection."""
    db = get_firestore_client()
    doc_id = str(conv["session_id"])
    db.collection("conversations").document(doc_id).set(conv)


def get_conversation(session_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve a conversation record by session_id."""
    db = get_firestore_client()
    doc = db.collection("conversations").document(str(session_id)).get()
    if doc.exists:
        return doc.to_dict()
    return None


def update_conversation(session_id: str, updates: Dict[str, Any]) -> None:
    """Update fields on an existing conversation."""
    db = get_firestore_client()
    db.collection("conversations").document(str(session_id)).update(updates)


def save_notification(notification: Dict[str, Any]) -> None:
    """Save a notification record to Firestore notifications collection."""
    db = get_firestore_client()
    doc_id = str(notification.get("notification_id") or f"notif-{int(datetime.now(timezone.utc).timestamp()*1000)}")
    notification["notification_id"] = doc_id
    db.collection("notifications").document(doc_id).set(notification)


def list_notifications(
    recipient_role: Optional[str] = None,
    recipient_org_id: Optional[str] = None,
    ticket_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """List notifications filtered by recipient_role, recipient_org_id, or ticket_id."""
    db = get_firestore_client()
    query = db.collection("notifications")
    if recipient_role is not None:
        query = query.where(filter=FieldFilter("recipient_role", "==", recipient_role))
    if recipient_org_id is not None:
        query = query.where(filter=FieldFilter("recipient_org_id", "==", str(recipient_org_id)))
    if ticket_id is not None:
        query = query.where(filter=FieldFilter("ticket_id", "==", ticket_id))
    docs = query.stream()
    return [doc.to_dict() for doc in docs]


def save_audit_event(event: Dict[str, Any]) -> None:
    """Save an audit log entry to Firestore audit_log collection."""
    db = get_firestore_client()
    doc_id = str(event.get("audit_id") or f"audit-{int(datetime.now(timezone.utc).timestamp()*1000)}")
    event["audit_id"] = doc_id
    db.collection("audit_log").document(doc_id).set(event)


def list_audit_events(ticket_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """List audit log entries, optionally filtered by ticket_id."""
    db = get_firestore_client()
    query = db.collection("audit_log")
    if ticket_id is not None:
        query = query.where(filter=FieldFilter("ticket_id", "==", ticket_id))
    docs = query.stream()
    return [doc.to_dict() for doc in docs]


# ============================================================================
# Phase 5: Match Briefs Collection (`match_briefs`)
# ============================================================================


def save_match_brief(brief: Dict[str, Any]) -> None:
    """Save a match brief document to Firestore match_briefs collection."""
    db = get_firestore_client()
    plan_id = brief.get("plan_id")
    ticket_id = brief.get("ticket_id")
    doc_id = f"{ticket_id}_{plan_id}" if (ticket_id and plan_id) else (plan_id or f"brief-{uuid.uuid4().hex[:8]}")
    brief["brief_id"] = doc_id
    db.collection("match_briefs").document(doc_id).set(brief)


def get_match_brief(plan_id: str) -> Optional[Dict[str, Any]]:
    """Get single match brief for an approved plan version by plan_id."""
    db = get_firestore_client()
    docs = db.collection("match_briefs").where(filter=FieldFilter("plan_id", "==", plan_id)).limit(1).stream()
    for doc in docs:
        return doc.to_dict()
    return None


def get_match_brief_for_ticket(ticket_id: str) -> Optional[Dict[str, Any]]:
    """Get latest match brief for a ticket."""
    db = get_firestore_client()
    docs = list(db.collection("match_briefs").where(filter=FieldFilter("ticket_id", "==", ticket_id)).stream())
    if not docs:
        return None
    # Sort by created_at descending if multiple plan versions exist
    briefs = [d.to_dict() for d in docs]
    briefs.sort(key=lambda b: str(b.get("created_at", "")), reverse=True)
    return briefs[0]


def list_match_briefs(ticket_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """List match briefs, optionally filtered by ticket_id."""
    db = get_firestore_client()
    query = db.collection("match_briefs")
    if ticket_id is not None:
        query = query.where(filter=FieldFilter("ticket_id", "==", ticket_id))
    docs = query.stream()
    return [doc.to_dict() for doc in docs]





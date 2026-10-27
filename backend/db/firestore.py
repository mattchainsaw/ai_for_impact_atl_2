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


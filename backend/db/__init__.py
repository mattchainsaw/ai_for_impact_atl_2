"""RescueGuard BigQuery and Firestore database layer."""

from backend.db.firestore import (
    get_firestore_client,
    save_match_candidates,
    get_match_candidates,
    save_recall_check,
    get_recall_checks,
    get_cached_distance,
    cache_distance_pair,
)

__all__ = [
    "get_firestore_client",
    "save_match_candidates",
    "get_match_candidates",
    "save_recall_check",
    "get_recall_checks",
    "get_cached_distance",
    "cache_distance_pair",
]

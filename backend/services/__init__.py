"""RescueGuard Backend Services."""

from backend.services.shelf_life import (
    lookup_foodkeeper,
    resolve_clock,
    compute_margin_hours,
    FoodKeeperResult,
    ResolvedClock,
)
from backend.services.search import (
    search_recipients,
    search_recipients_with_job,
    SearchCandidate,
)
from backend.services.last_mile import (
    calculate_haversine_distance_km,
    compute_travel_buffer_hours,
    resolve_distance_and_margin,
    evaluate_logistics_capabilities,
)
from backend.services.constraints import (
    detect_profile_contradictions,
    evaluate_candidate_constraints,
)
from backend.services.recall import (
    check_recall,
    list_ticket_recall_checks,
)
from backend.services.matcher import (
    match_recipients,
)

__all__ = [
    "lookup_foodkeeper",
    "resolve_clock",
    "compute_margin_hours",
    "FoodKeeperResult",
    "ResolvedClock",
    "search_recipients",
    "search_recipients_with_job",
    "SearchCandidate",
    "calculate_haversine_distance_km",
    "compute_travel_buffer_hours",
    "resolve_distance_and_margin",
    "evaluate_logistics_capabilities",
    "detect_profile_contradictions",
    "evaluate_candidate_constraints",
    "check_recall",
    "list_ticket_recall_checks",
    "match_recipients",
]

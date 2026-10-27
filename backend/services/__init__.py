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
from backend.services.code_exec import (
    execute_split_and_margin,
    generate_deterministic_split_script,
)
from backend.services.planner import (
    create_initial_plan,
    compute_plan_hash,
)
from backend.services.checker import (
    check_plan,
    evaluate_equity_skew,
)
from backend.services.fixer import (
    fix_plan,
)
from backend.services.tickets import (
    create_ticket,
    get_ticket_service,
    list_tickets_service,
    get_ticket_parameters,
    update_ticket_parameters,
    execute_ticket_match,
    NoViableMatchException,
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
    "execute_split_and_margin",
    "generate_deterministic_split_script",
    "create_initial_plan",
    "compute_plan_hash",
    "check_plan",
    "evaluate_equity_skew",
    "fix_plan",
    "create_ticket",
    "get_ticket_service",
    "list_tickets_service",
    "get_ticket_parameters",
    "update_ticket_parameters",
    "execute_ticket_match",
    "NoViableMatchException",
]

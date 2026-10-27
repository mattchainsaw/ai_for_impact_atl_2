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
from backend.services.auth import (
    get_current_role,
    get_current_tenant,
    get_current_org_id,
    check_tenant_access,
    check_donor_access,
    check_recipient_access,
)
from backend.services.holds import (
    create_holds_for_plan,
    get_holds_for_ticket,
    get_hold,
    confirm_hold,
    release_hold,
    release_all_holds_for_ticket,
)
from backend.services.allocations import (
    complete_allocation,
    no_show_allocation,
    list_allocations,
    get_allocation,
)
from backend.services.approvals import (
    approve_plan,
    reject_plan,
    approve_action,
)
from backend.services.decline import (
    decline_allocation_and_replan,
)
from backend.services.cancel import (
    cancel_ticket,
)
from backend.services.tasks import (
    create_task,
    get_task,
    list_tasks,
    patch_task,
)
from backend.services.guide import (
    handle_assistant_chat,
    get_conversation_history,
    execute_guide_mcp_query,
    scrub_pii,
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
    "get_current_role",
    "get_current_tenant",
    "get_current_org_id",
    "check_tenant_access",
    "check_donor_access",
    "check_recipient_access",
    "create_holds_for_plan",
    "get_holds_for_ticket",
    "get_hold",
    "confirm_hold",
    "release_hold",
    "release_all_holds_for_ticket",
    "complete_allocation",
    "no_show_allocation",
    "list_allocations",
    "get_allocation",
    "approve_plan",
    "reject_plan",
    "approve_action",
    "decline_allocation_and_replan",
    "cancel_ticket",
    "create_task",
    "get_task",
    "list_tasks",
    "patch_task",
    "handle_assistant_chat",
    "get_conversation_history",
    "execute_guide_mcp_query",
    "scrub_pii",
]

"""Pydantic request/response contracts for all 52 RescueGuard API endpoints and 29 stores (Phase 0)."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple, Type
from pydantic import BaseModel, Field, model_validator

from schemas.common import (
    ActionCard,
    EquityCheckerResult,
    ImpactBreakdown,
    MatchCandidateRecord,
    PlanAllocationItem,
    convert_to_pallets,
    validate_donor_pickup_address,
)
from schemas.enums import (
    ActionTargetType,
    AddressType,
    AllocationStatus,
    ColdStorageType,
    DistanceSource,
    ExecutionSource,
    HoldStatus,
    PlanStatus,
    PostingSource,
    QuantityUnit,
    RecallSource,
    RecallVerdict,
    Role,
    ScrubStatus,
    ShelfLifeSource,
    TaskStatus,
    TaskType,
    TicketStatus,
    TicketStep,
    TractStatus,
    TriStateStatus,
    VerificationStatus,
)


# ============================================================================
# Shared Request/Path/Query Base Contracts
# ============================================================================


class BaseContractModel(BaseModel):
    """Base contract model with request_id and header-derived tenant_id."""

    request_id: str = Field(default="req-default", description="Idempotency and trace request ID")
    tenant_id: str = Field(default="atlanta-default", description="Header-derived tenant ID")


class PaginationQuery(BaseContractModel):
    """Standard list pagination query (`limit` default 50, max 200; `offset` >= 0)."""

    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


# ============================================================================
# Group 1: Health, Identity, Starter Reads (7 Endpoints)
# ============================================================================


class HealthQuery(BaseContractModel):
    """1. GET /api/health query contract."""


class HealthResponse(BaseModel):
    """1. GET /api/health response contract (`{status, project, dataset, model_id}`)."""

    status: str = "ok"
    project: str
    dataset: str
    model_id: str


class MeQuery(BaseContractModel):
    """2. GET /api/me query contract."""

    role: Role = Role.COORDINATOR
    org_id: str = "atlanta-coordinator-desk"


class MeResponse(BaseContractModel):
    """2. GET /api/me response contract (`{role, org_id, tenant_id}`)."""

    role: Role
    org_id: str


class StarterPostingItem(BaseModel):
    """Row from `a4i_food.surplus_postings`."""

    posting_id: str
    track: str
    posting_text: str
    foodkeeper_product: Optional[str] = None
    storage_state: str
    hours_available: float
    shelf_life_hours: Optional[float] = None
    hours_remaining: Optional[float] = None


class StarterPostingListResponse(BaseContractModel):
    """3. GET /api/starter-postings response contract."""

    items: List[StarterPostingItem]
    total_count: int


class ShelfLifeLookupPath(BaseContractModel):
    """4. GET /api/shelf-life/{product} path contract."""

    product: str


class ShelfLifeItem(BaseModel):
    """Row from `a4i_food.shelf_life`."""

    product_id: int
    product_name: str
    product_subtitle: Optional[str] = None
    keywords: Optional[str] = None
    category: Optional[str] = None
    refrigerated_hours: Optional[float] = None
    refrigerated_note: Optional[str] = None
    pantry_hours: Optional[float] = None
    pantry_note: Optional[str] = None


class ShelfLifeLookupResponse(BaseContractModel):
    """4. GET /api/shelf-life/{product} response contract."""

    query_product: str
    matches: List[ShelfLifeItem]


class TractLookupPath(BaseContractModel):
    """5. GET /api/tracts/{geo_id} path contract."""

    geo_id: str = Field(..., min_length=11, max_length=11, description="11-char FIPS STRING")


class TractLookupResponse(BaseContractModel):
    """5. GET /api/tracts/{geo_id} response contract."""

    geo_id: str
    tract_lat: float
    tract_lon: float
    total_pop: int
    median_income: Optional[float] = None
    poverty_rate: float
    no_vehicle_rate: float
    assistance_rate: float


class RecipientListQuery(PaginationQuery):
    """6. GET /api/recipients query contract."""

    cold_storage: Optional[ColdStorageType] = None
    verified_only: bool = True


class RecipientRecord(BaseModel):
    """Effective recipient row from `v_all_recipients`."""

    recipient_id: int
    ein: Optional[str] = None
    name: str
    street: str
    city: str
    state: str
    zip_code: str
    cold_storage: ColdStorageType
    frozen_storage: TriStateStatus = TriStateStatus.UNRECORDED
    loading_dock: TriStateStatus = TriStateStatus.UNRECORDED
    refrigerated_transport: TriStateStatus = TriStateStatus.UNRECORDED
    max_pallets: float
    pickup_window_hours: float
    weekly_households: int
    populations_served: Optional[str] = None
    dietary_flags: List[str] = Field(default_factory=list)
    service_days: str
    profile_text: str
    profile_source: str = "generated"
    latitude: float
    longitude: float
    verification_status: VerificationStatus = VerificationStatus.VERIFIED


class RecipientListResponse(BaseContractModel):
    """6. GET /api/recipients response contract."""

    recipients: List[RecipientRecord]
    total_count: int


class RecipientDetailPath(BaseContractModel):
    """7. GET /api/recipients/{recipient_id} path contract."""

    recipient_id: int


class RecipientDetailResponse(BaseContractModel):
    """7. GET /api/recipients/{recipient_id} response contract."""

    recipient: RecipientRecord
    tract_geo_id: Optional[str] = None
    tract_status: TractStatus = TractStatus.FOUND


# ============================================================================
# Group 2: Postings, Tickets, Matching, Plans (14 Endpoints)
# ============================================================================


class CreatePostingRequest(BaseContractModel):
    """8. POST /api/postings request contract with Review Fix M5 + Hard Gate 1 validation."""

    donor_id: str
    donor_org_name: str
    pickup_address: str
    address_type: AddressType
    coordinator_asserted_org_dock: bool
    asserted_by_role: Role = Role.COORDINATOR
    asserted_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    pickup_zip: str
    pickup_lat: Optional[float] = None
    pickup_lon: Optional[float] = None
    product_text: str
    track: str = "perishable"
    quantity: float = Field(..., gt=0)
    quantity_unit: QuantityUnit
    pallets_equivalent: Optional[float] = None
    split_allowed: bool = True
    delivery_available: bool = False
    dietary_flags: List[str] = Field(default_factory=list)
    temperature_requirement: str = "refrigerated"
    donor_deadline: datetime

    @model_validator(mode="after")
    def _enforce_m5_and_units(self) -> "CreatePostingRequest":
        validate_donor_pickup_address(
            donor_org_name=self.donor_org_name,
            pickup_address=self.pickup_address,
            address_type=self.address_type,
            coordinator_asserted_org_dock=self.coordinator_asserted_org_dock,
            asserted_by_role=self.asserted_by_role,
        )
        self.pallets_equivalent = convert_to_pallets(self.quantity, self.quantity_unit)
        return self


class PostingResponse(BaseContractModel):
    """8 & 10. POST /api/postings and GET /api/postings/{posting_id} response contract."""

    posting_id: str
    donor_id: str
    donor_org_name: str
    pickup_address: str
    address_type: AddressType
    coordinator_asserted_org_dock: bool
    asserted_by_role: Role
    asserted_at: datetime
    pickup_zip: str
    pickup_lat: Optional[float] = None
    pickup_lon: Optional[float] = None
    product_text: str
    track: str
    quantity: float
    quantity_unit: QuantityUnit
    pallets_equivalent: float
    split_allowed: bool
    delivery_available: bool
    dietary_flags: List[str] = Field(default_factory=list)
    temperature_requirement: str
    donor_deadline: datetime
    status: str = "OPEN"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PostingListResponse(BaseContractModel):
    """9. GET /api/postings response contract."""

    postings: List[PostingResponse]
    total_count: int


class PostingPath(BaseContractModel):
    """10. GET /api/postings/{posting_id} path contract."""

    posting_id: str


class CreateTicketRequest(BaseContractModel):
    """11. POST /api/tickets request contract (`posting_source` discriminator required)."""

    posting_id: str
    posting_source: PostingSource


class TicketParameters(BaseModel):
    """Ticket-scoped matching parameters (`tickets.parameters`)."""

    top_n: int = Field(default=10, ge=1, le=50)
    weights: Dict[str, float] = Field(
        default_factory=lambda: {"fit": 0.50, "need": 0.30, "fairness": 0.20}
    )
    split_allowed: bool = True


class TicketResponse(BaseContractModel):
    """11, 13, 17. Ticket state response contract (also canonical crash-resume response)."""

    ticket_id: str
    posting_id: str
    posting_source: PostingSource
    posting_ref: str
    metro: str = "atlanta"
    step: TicketStep = TicketStep.POSTED
    current_plan_id: Optional[str] = None
    plan_version_current: int = 0
    parameters: TicketParameters = Field(default_factory=TicketParameters)
    resolved_deadline: datetime
    resolved_shelf_life_hours: float
    shelf_life_source: ShelfLifeSource
    resolved_at: datetime
    holds_already_started: List[str] = Field(default_factory=list)
    tasks_already_approved: List[str] = Field(default_factory=list)
    step_started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    status: TicketStatus = TicketStatus.ACTIVE


class TicketListResponse(BaseContractModel):
    """12. GET /api/tickets response contract."""

    tickets: List[TicketResponse]
    total_count: int


class TicketPath(BaseContractModel):
    """13, 15, 18, 22, 40, 43, 47, 48. Path contract for `{ticket_id}` endpoints."""

    ticket_id: str


class RunTicketMatchRequest(BaseContractModel):
    """14. POST /api/tickets/{ticket_id}/match request contract."""

    ticket_id: str
    force_replan: bool = False


class TicketParametersResponse(BaseContractModel):
    """15 & 16. GET/POST /api/tickets/{ticket_id}/parameters response contract."""

    ticket_id: str
    parameters: TicketParameters


class UpdateTicketParametersRequest(BaseContractModel):
    """16. POST /api/tickets/{ticket_id}/parameters request contract."""

    ticket_id: str
    parameters: TicketParameters


class CancelTicketRequest(BaseContractModel):
    """17. POST /api/tickets/{ticket_id}/cancel request contract."""

    ticket_id: str
    reason: str


class PlanResponse(BaseContractModel):
    """14, 19, 21, 26. Plan version response contract (`plans`)."""

    plan_id: str
    ticket_id: str
    plan_version: int
    status: PlanStatus
    allocations: List[PlanAllocationItem]
    checker_reasons: List[str] = Field(default_factory=list)
    fixer_changes: List[str] = Field(default_factory=list)
    fixer_attempt_count: int = Field(default=0, ge=0, le=3)
    last_plan_hash: Optional[str] = None
    last_checker_reason: Optional[str] = None
    plan_hash: str
    execution_source: ExecutionSource = ExecutionSource.CODE_EXECUTION
    execution_code: str = ""
    execution_output: str = ""
    impact_breakdown: Optional[ImpactBreakdown] = None
    equity_checker_result: Optional[EquityCheckerResult] = None
    parameters_snapshot: TicketParameters = Field(default_factory=TicketParameters)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    approved_by_role: Optional[Role] = None
    approved_at: Optional[datetime] = None


class PlanListResponse(BaseContractModel):
    """18. GET /api/tickets/{ticket_id}/plans response contract."""

    ticket_id: str
    plans: List[PlanResponse]


class PlanPath(BaseContractModel):
    """19. GET /api/plans/{plan_id} path contract."""

    plan_id: str


class ApprovePlanRequest(BaseContractModel):
    """20. POST /api/plans/{plan_id}/approve request contract."""

    plan_id: str
    approver_role: Role = Role.COORDINATOR
    notes: Optional[str] = None


class PlanApprovalResponse(BaseContractModel):
    """20. POST /api/plans/{plan_id}/approve response contract."""

    approval_id: str
    plan_id: str
    ticket_id: str
    plan_version: int
    status: PlanStatus = PlanStatus.APPROVED
    holds_created: List[str] = Field(default_factory=list)
    approved_by_role: Role
    approved_at: datetime


class RejectPlanRequest(BaseContractModel):
    """21. POST /api/plans/{plan_id}/reject request contract."""

    plan_id: str
    reason: str


# ============================================================================
# Group 3: Holds, Allocations, Completion (8 Endpoints)
# ============================================================================


class HoldPath(BaseContractModel):
    """23. GET /api/holds/{hold_id} path contract."""

    hold_id: str


class HoldResponse(BaseContractModel):
    """23, 24, 25. Hold response contract (`holds`)."""

    hold_id: str
    ticket_id: str
    plan_id: str
    recipient_id: int
    quantity: float
    quantity_unit: QuantityUnit
    pallets_equivalent: float
    status: HoldStatus
    started_at: datetime
    expires_at: datetime
    confirmed_at: Optional[datetime] = None


class HoldListResponse(BaseContractModel):
    """22. GET /api/tickets/{ticket_id}/holds response contract."""

    ticket_id: str
    holds: List[HoldResponse]


class ConfirmHoldRequest(BaseContractModel):
    """24. POST /api/holds/{hold_id}/confirm request contract."""

    hold_id: str
    recipient_id: int


class ReleaseHoldRequest(BaseContractModel):
    """25. POST /api/holds/{hold_id}/release request contract."""

    hold_id: str
    reason: str


class DeclineAllocationRequest(BaseContractModel):
    """26. POST /api/tickets/{ticket_id}/decline request contract."""

    ticket_id: str
    recipient_id: int
    allocation_id: str
    reason: Optional[str] = None


class CompleteAllocationRequest(BaseContractModel):
    """27. POST /api/allocations/{allocation_id}/complete request contract."""

    allocation_id: str
    notes: Optional[str] = None


class NoShowAllocationRequest(BaseContractModel):
    """28. POST /api/allocations/{allocation_id}/no-show request contract."""

    allocation_id: str
    reason: str


class AllocationResponse(BaseContractModel):
    """27, 28. Allocation response contract (`allocations`)."""

    allocation_id: str
    hold_id: str
    recipient_id: int
    ticket_id: str
    plan_id: str
    quantity: float
    quantity_unit: QuantityUnit
    pallets_equivalent: float
    status: AllocationStatus
    allocated_at: datetime
    confirmed_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    tract_geo_id: str
    need_score_at_allocation: float


class AllocationListResponse(BaseContractModel):
    """29. GET /api/allocations response contract."""

    allocations: List[AllocationResponse]
    total_count: int


# ============================================================================
# Group 4: Recipients, Onboarding, Profile Updates (3 Endpoints)
# ============================================================================


class RecipientSemanticSearchRequest(BaseContractModel):
    """30. POST /api/recipients/search request contract."""

    query_text: str = Field(..., min_length=3)
    top_k: int = Field(default=15, ge=1, le=50)


class RecipientSemanticSearchResponse(BaseContractModel):
    """30. POST /api/recipients/search response contract."""

    query_text: str
    candidates: List[MatchCandidateRecord]
    bq_job_id: str


class OnboardRecipientRequest(BaseContractModel):
    """31. POST /api/recipients request contract (writes `app_recipients` + `recipient_embeddings`)."""

    name: str
    ein: Optional[str] = None
    street: str
    city: str = "Atlanta"
    state: str = "GA"
    zip_code: str
    cold_storage: ColdStorageType
    frozen_storage: TriStateStatus = TriStateStatus.UNRECORDED
    loading_dock: TriStateStatus = TriStateStatus.UNRECORDED
    refrigerated_transport: TriStateStatus = TriStateStatus.UNRECORDED
    max_pallets: float = Field(..., gt=0)
    pickup_window_hours: float = Field(..., gt=0)
    weekly_households: int = Field(..., ge=0)
    populations_served: str
    service_days: str
    profile_text: str
    latitude: float
    longitude: float
    verification_status: VerificationStatus = VerificationStatus.PENDING


class OnboardRecipientResponse(BaseContractModel):
    """31. POST /api/recipients response contract."""

    recipient_id: int
    name: str
    verification_status: VerificationStatus
    app_recipients_written: bool
    embeddings_written: bool
    searchable_in_v_all_recipients: bool
    embedding_job_id: str


class PatchRecipientRequest(BaseContractModel):
    """32. PATCH /api/recipients/{recipient_id} request contract (writes `recipient_overrides`)."""

    recipient_id: int
    changed_fields: Dict[str, Any]
    parsed_dietary_flags: Optional[List[str]] = None


# ============================================================================
# Group 5: Tasks, Actions, Guide Chat (7 Endpoints)
# ============================================================================


class CreateTaskRequest(BaseContractModel):
    """33. POST /api/tasks request contract."""

    ticket_id: str
    plan_id: Optional[str] = None
    task_type: TaskType
    owner_role: Role = Role.COORDINATOR
    description: str = ""


class TaskResponse(BaseContractModel):
    """33, 35, 36. Task response contract (`tasks`)."""

    task_id: str
    ticket_id: str
    plan_id: Optional[str] = None
    task_type: TaskType
    owner_role: Role
    status: TaskStatus
    description: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class TaskListResponse(BaseContractModel):
    """34. GET /api/tasks response contract."""

    tasks: List[TaskResponse]
    total_count: int


class TaskPath(BaseContractModel):
    """35. GET /api/tasks/{task_id} path contract."""

    task_id: str


class PatchTaskRequest(BaseContractModel):
    """36. PATCH /api/tasks/{task_id} request contract."""

    task_id: str
    status: TaskStatus
    approver_role: Role = Role.COORDINATOR


class ApproveActionRequest(BaseContractModel):
    """37. POST /api/actions/approve request contract (canonical approval entry)."""

    action: ActionCard
    approver_role: Role = Role.COORDINATOR


class ActionApprovalResponse(BaseContractModel):
    """37. POST /api/actions/approve response contract."""

    approval_id: str
    action_id: str
    target_type: ActionTargetType
    target_id: str
    target_endpoint: str
    decision: str = "APPROVED"
    approver_role: Role
    approved_at: datetime


class AssistantChatRequest(BaseContractModel):
    """38. POST /api/assistant/chat request contract (Vertex AI ADK Guide agent)."""

    session_id: str
    ticket_id: Optional[str] = None
    posting_id: Optional[str] = None
    plan_version: Optional[int] = None
    step: Optional[TicketStep] = None
    role: Role
    hold_status: Optional[HoldStatus] = None
    message: str = Field(..., min_length=1)


class AssistantChatResponse(BaseContractModel):
    """38. POST /api/assistant/chat response contract."""

    session_id: str
    answer: str
    citations: List[str] = Field(default_factory=list)
    action_cards: List[ActionCard] = Field(default_factory=list)
    state_update: Dict[str, Any] = Field(default_factory=dict)
    scrub_status: ScrubStatus = ScrubStatus.SCRUBBED
    disclaimer: str = (
        "This is a matching aid, not a food-safety guarantee — follow official "
        "food-safety guidance, coordinator approves."
    )


class ConversationPath(BaseContractModel):
    """39. GET /api/conversations/{session_id} path contract."""

    session_id: str


class ConversationResponse(BaseContractModel):
    """39. GET /api/conversations/{session_id} response contract (`conversations`)."""

    session_id: str
    ticket_id: Optional[str] = None
    role: Role
    messages: List[Dict[str, Any]] = Field(default_factory=list)
    action_cards: List[ActionCard] = Field(default_factory=list)
    model_version: str
    prompt_version: str = "v1"
    scrub_status: ScrubStatus = ScrubStatus.SCRUBBED


# ============================================================================
# Group 6: Impact, Equity, Deserts, Safety, Last-Mile (9 Endpoints)
# ============================================================================


class TicketImpactResponse(BaseContractModel):
    """40. GET /api/tickets/{ticket_id}/impact response contract."""

    ticket_id: str
    plan_id: str
    plan_version: int
    impact_breakdown: ImpactBreakdown
    v1_vs_current_delta: Dict[str, Any] = Field(default_factory=dict)
    do_nothing_baseline: Dict[str, Any] = Field(default_factory=dict)


class ImpactDashboardResponse(BaseContractModel):
    """41. GET /api/impact/dashboard response contract."""

    total_tickets_completed: int
    total_pallets_rescued: float
    average_impact_score: float
    estimated_households_note: str = "ESTIMATED_CAPACITY (never summed as unique individuals)"


class RunEquityAuditRequest(BaseContractModel):
    """42. POST /api/equity/audit request contract."""

    ticket_id: str
    plan_id: str


class EquityAuditResponse(BaseContractModel):
    """42 & 43. POST /api/equity/audit and GET /api/equity/{ticket_id} response contract."""

    ticket_id: str
    plan_id: str
    equity_checker_result: EquityCheckerResult


class DesertCellRecord(BaseModel):
    """Row from `rescueguard_app.v_rescue_deserts`."""

    tract_geo_id: str
    tract_lat: float
    tract_lon: float
    poverty_rate: float
    no_vehicle_rate: float
    assistance_rate: float
    cold_recipients_within_5km: int
    is_cold_chain_desert: bool


class DesertListResponse(BaseContractModel):
    """44. GET /api/deserts response contract."""

    deserts: List[DesertCellRecord]
    total_desert_tracts: int


class DesertPath(BaseContractModel):
    """45. GET /api/deserts/{tract_geo_id} path contract."""

    tract_geo_id: str


class DesertCellResponse(BaseContractModel):
    """45. GET /api/deserts/{tract_geo_id} response contract."""

    desert: DesertCellRecord


class RecallCheckRequest(BaseContractModel):
    """46. POST /api/recall/check request contract."""

    ticket_id: str
    product_text: str


class RecallCheckResponse(BaseContractModel):
    """46. POST /api/recall/check response contract (`recall_checks`)."""

    check_id: str
    ticket_id: str
    product_text: str
    fda_query: str
    verdict: RecallVerdict
    recall_id: Optional[str] = None
    checked_at: datetime
    source: RecallSource = RecallSource.LIVE_OPENFDA


class RecallCheckListResponse(BaseContractModel):
    """47. GET /api/tickets/{ticket_id}/recall response contract."""

    ticket_id: str
    checks: List[RecallCheckResponse]


class LastMileAllocationView(BaseModel):
    """Filtered view of current plan's allocations + candidates for last-mile logistics."""

    recipient_id: int
    recipient_name: str
    refrigerated_transport: TriStateStatus
    loading_dock: TriStateStatus
    pickup_window_hours: float
    clock_margin_hours: float
    distance_km: float
    distance_source: DistanceSource
    transport_mode: str


class LastMileResponse(BaseContractModel):
    """48. GET /api/tickets/{ticket_id}/last-mile response contract."""

    ticket_id: str
    plan_id: str
    options: List[LastMileAllocationView]


# ============================================================================
# Group 7: Maps (Bonus), Audit, Telemetry (4 Endpoints)
# ============================================================================


class GeocodeRequest(BaseContractModel):
    """49. POST /api/maps/geocode request contract."""

    address: str
    zip_code: str


class GeocodeResponse(BaseContractModel):
    """49. POST /api/maps/geocode response contract."""

    latitude: float
    longitude: float
    source: DistanceSource


class RouteRequest(BaseContractModel):
    """50. POST /api/maps/route request contract."""

    donor_pickup_ref: str
    recipient_id: int
    origin_lat: float
    origin_lon: float
    dest_lat: float
    dest_lon: float


class RouteResponse(BaseContractModel):
    """50. POST /api/maps/route response contract (`distance_pairs`)."""

    pair_key: str
    distance_km: float
    drive_time_minutes: float
    source: DistanceSource
    cached_at: datetime
    expires_at: datetime


class AuditExportQuery(PaginationQuery):
    """51. GET /api/audit/export query contract."""

    ticket_id: Optional[str] = None
    finished_runs_from_bq: bool = False


class AuditLogRecord(BaseModel):
    """Entry in Firestore `audit_log` / BigQuery `audit_history`."""

    audit_id: str
    ticket_id: str
    plan_version: int
    event_type: str
    actor_role: Role
    action: str
    timestamp: datetime
    request_id: str
    tenant_id: str


class AuditExportResponse(BaseContractModel):
    """51. GET /api/audit/export response contract."""

    source_store: str = "firestore.audit_log"
    entries: List[AuditLogRecord]


class TelemetryQuery(PaginationQuery):
    """52. GET /api/telemetry query contract."""


class TelemetryResponse(BaseContractModel):
    """52. GET /api/telemetry response contract (aggregates only from `telemetry_events`)."""

    total_requests: int
    avg_latency_ms: float
    maps_fallback_rate: float
    checker_loop_avg: float
    hold_expiry_rate: float
    escalation_rate: float


# ============================================================================
# Registries of All 29 Locked Stores and All 52 Locked Endpoints
# ============================================================================

STARTER_BQ_TABLES: Tuple[str, ...] = (
    "a4i_food.recipients",
    "a4i_food.surplus_postings",
    "a4i_food.shelf_life",
    "a4i_food.tract_demographics",
)

TEAM_BQ_TABLES_AND_VIEWS: Tuple[str, ...] = (
    "rescueguard_app.recipient_embeddings",
    "rescueguard_app.app_recipients",
    "rescueguard_app.recipient_overrides",
    "rescueguard_app.v_all_recipients",
    "rescueguard_app.v_recipient_tract",
    "rescueguard_app.v_rescue_deserts",
)

FIRESTORE_TICKET_COLLECTIONS: Tuple[str, ...] = (
    "postings",
    "tickets",
    "plans",
    "match_candidates",
    "match_briefs",
    "holds",
    "allocations",
    "tasks",
    "approvals",
)

FIRESTORE_PEOPLE_SAFETY_AUDIT_COLLECTIONS: Tuple[str, ...] = (
    "conversations",
    "recall_checks",
    "notifications",
    "audit_log",
    "telemetry_events",
    "distance_pairs",
    "users_roles",
)

BQ_HISTORY_SINKS: Tuple[str, ...] = (
    "rescueguard_app.audit_history",
    "rescueguard_app.impact_snapshots",
    "rescueguard_app.equity_audit_results",
)

ALL_29_CONTRACT_STORES: Tuple[str, ...] = (
    STARTER_BQ_TABLES
    + TEAM_BQ_TABLES_AND_VIEWS
    + FIRESTORE_TICKET_COLLECTIONS
    + FIRESTORE_PEOPLE_SAFETY_AUDIT_COLLECTIONS
    + BQ_HISTORY_SINKS
)

ENDPOINT_CONTRACT_REGISTRY: Dict[Tuple[str, str], Tuple[Type[BaseModel], Type[BaseModel]]] = {
    # Group 1: Health, identity, starter reads (7)
    ("GET", "/api/health"): (HealthQuery, HealthResponse),
    ("GET", "/api/me"): (MeQuery, MeResponse),
    ("GET", "/api/starter-postings"): (PaginationQuery, StarterPostingListResponse),
    ("GET", "/api/shelf-life/{product}"): (ShelfLifeLookupPath, ShelfLifeLookupResponse),
    ("GET", "/api/tracts/{geo_id}"): (TractLookupPath, TractLookupResponse),
    ("GET", "/api/recipients"): (RecipientListQuery, RecipientListResponse),
    ("GET", "/api/recipients/{recipient_id}"): (RecipientDetailPath, RecipientDetailResponse),
    # Group 2: Postings, tickets, matching, plans (14)
    ("POST", "/api/postings"): (CreatePostingRequest, PostingResponse),
    ("GET", "/api/postings"): (PaginationQuery, PostingListResponse),
    ("GET", "/api/postings/{posting_id}"): (PostingPath, PostingResponse),
    ("POST", "/api/tickets"): (CreateTicketRequest, TicketResponse),
    ("GET", "/api/tickets"): (PaginationQuery, TicketListResponse),
    ("GET", "/api/tickets/{ticket_id}"): (TicketPath, TicketResponse),
    ("POST", "/api/tickets/{ticket_id}/match"): (RunTicketMatchRequest, PlanResponse),
    ("GET", "/api/tickets/{ticket_id}/parameters"): (TicketPath, TicketParametersResponse),
    ("POST", "/api/tickets/{ticket_id}/parameters"): (
        UpdateTicketParametersRequest,
        TicketParametersResponse,
    ),
    ("POST", "/api/tickets/{ticket_id}/cancel"): (CancelTicketRequest, TicketResponse),
    ("GET", "/api/tickets/{ticket_id}/plans"): (TicketPath, PlanListResponse),
    ("GET", "/api/plans/{plan_id}"): (PlanPath, PlanResponse),
    ("POST", "/api/plans/{plan_id}/approve"): (ApprovePlanRequest, PlanApprovalResponse),
    ("POST", "/api/plans/{plan_id}/reject"): (RejectPlanRequest, PlanResponse),
    # Group 3: Holds, allocations, completion (8)
    ("GET", "/api/tickets/{ticket_id}/holds"): (TicketPath, HoldListResponse),
    ("GET", "/api/holds/{hold_id}"): (HoldPath, HoldResponse),
    ("POST", "/api/holds/{hold_id}/confirm"): (ConfirmHoldRequest, HoldResponse),
    ("POST", "/api/holds/{hold_id}/release"): (ReleaseHoldRequest, HoldResponse),
    ("POST", "/api/tickets/{ticket_id}/decline"): (DeclineAllocationRequest, PlanResponse),
    ("POST", "/api/allocations/{allocation_id}/complete"): (
        CompleteAllocationRequest,
        AllocationResponse,
    ),
    ("POST", "/api/allocations/{allocation_id}/no-show"): (
        NoShowAllocationRequest,
        AllocationResponse,
    ),
    ("GET", "/api/allocations"): (PaginationQuery, AllocationListResponse),
    # Group 4: Recipients, onboarding, profile updates (3)
    ("POST", "/api/recipients/search"): (
        RecipientSemanticSearchRequest,
        RecipientSemanticSearchResponse,
    ),
    ("POST", "/api/recipients"): (OnboardRecipientRequest, OnboardRecipientResponse),
    ("PATCH", "/api/recipients/{recipient_id}"): (
        PatchRecipientRequest,
        RecipientDetailResponse,
    ),
    # Group 5: Tasks, actions, Guide chat (7)
    ("POST", "/api/tasks"): (CreateTaskRequest, TaskResponse),
    ("GET", "/api/tasks"): (PaginationQuery, TaskListResponse),
    ("GET", "/api/tasks/{task_id}"): (TaskPath, TaskResponse),
    ("PATCH", "/api/tasks/{task_id}"): (PatchTaskRequest, TaskResponse),
    ("POST", "/api/actions/approve"): (ApproveActionRequest, ActionApprovalResponse),
    ("POST", "/api/assistant/chat"): (AssistantChatRequest, AssistantChatResponse),
    ("GET", "/api/conversations/{session_id}"): (ConversationPath, ConversationResponse),
    # Group 6: Impact, equity, deserts, safety, last-mile (9)
    ("GET", "/api/tickets/{ticket_id}/impact"): (TicketPath, TicketImpactResponse),
    ("GET", "/api/impact/dashboard"): (PaginationQuery, ImpactDashboardResponse),
    ("POST", "/api/equity/audit"): (RunEquityAuditRequest, EquityAuditResponse),
    ("GET", "/api/equity/{ticket_id}"): (TicketPath, EquityAuditResponse),
    ("GET", "/api/deserts"): (PaginationQuery, DesertListResponse),
    ("GET", "/api/deserts/{tract_geo_id}"): (DesertPath, DesertCellResponse),
    ("POST", "/api/recall/check"): (RecallCheckRequest, RecallCheckResponse),
    ("GET", "/api/tickets/{ticket_id}/recall"): (TicketPath, RecallCheckListResponse),
    ("GET", "/api/tickets/{ticket_id}/last-mile"): (TicketPath, LastMileResponse),
    # Group 7: Maps (bonus), audit, telemetry (4)
    ("POST", "/api/maps/geocode"): (GeocodeRequest, GeocodeResponse),
    ("POST", "/api/maps/route"): (RouteRequest, RouteResponse),
    ("GET", "/api/audit/export"): (AuditExportQuery, AuditExportResponse),
    ("GET", "/api/telemetry"): (TelemetryQuery, TelemetryResponse),
}

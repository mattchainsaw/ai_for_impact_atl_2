"""FastAPI entrypoint for RescueGuard backend.

Implements Phase 0 and Phase 2 endpoints:
- GET /api/health
- POST /api/recipients/search
- GET /api/recipients
- GET /api/recipients/{recipient_id}
- POST /api/recall/check
- GET /api/tickets/{ticket_id}/recall
- GET /api/shelf-life/{product}
- GET /api/tracts/{geo_id}
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union
import uuid
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from google.cloud import bigquery

from backend.app.config import get_settings
from schemas.api import (
    HealthResponse,
    RecipientSemanticSearchRequest,
    RecipientSemanticSearchResponse,
    RecipientListResponse,
    RecipientDetailResponse,
    RecipientRecord,
    RecallCheckRequest,
    RecallCheckResponse,
    RecallCheckListResponse,
    ShelfLifeLookupResponse,
    ShelfLifeItem,
    TractLookupResponse,
    CreatePostingRequest,
    PostingResponse,
    PostingListResponse,
    CreateTicketRequest,
    TicketResponse,
    TicketListResponse,
    DonorTicketResponse,
    RecipientTicketResponse,
    RunTicketMatchRequest,
    PlanResponse,
    PlanListResponse,
    DonorPlanResponse,
    RecipientPlanResponse,
    MatchBriefResponse,
    TicketParametersResponse,
    UpdateTicketParametersRequest,
    MeResponse,
    CancelTicketRequest,
    ApprovePlanRequest,
    PlanApprovalResponse,
    RejectPlanRequest,
    HoldResponse,
    HoldListResponse,
    ConfirmHoldRequest,
    ReleaseHoldRequest,
    DeclineAllocationRequest,
    CompleteAllocationRequest,
    NoShowAllocationRequest,
    AllocationResponse,
    AllocationListResponse,
    CreateTaskRequest,
    TaskResponse,
    TaskListResponse,
    PatchTaskRequest,
    ApproveActionRequest,
    ActionApprovalResponse,
    AssistantChatRequest,
    AssistantChatResponse,
    ConversationResponse,
)
from schemas.common import NoViableMatchFallback
from schemas.enums import (
    ColdStorageType,
    Role,
    TractStatus,
    TriStateStatus,
    VerificationStatus,
)
from backend.services.matcher import match_recipients
from backend.services.recall import check_recall, list_ticket_recall_checks
from backend.services.shelf_life import lookup_foodkeeper
from backend.services.tickets import (
    create_ticket,
    execute_ticket_match,
    get_ticket_parameters,
    get_ticket_service,
    list_tickets_service,
    update_ticket_parameters,
    NoViableMatchException,
)
from backend.services.auth import (
    get_current_role,
    get_current_tenant,
    get_current_org_id,
    check_tenant_access,
    check_donor_access,
    check_recipient_access,
    filter_ticket_for_role,
    filter_plan_for_role,
)
from backend.services.holds import (
    get_holds_for_ticket,
    get_hold,
    confirm_hold,
    release_hold,
)
from backend.services.allocations import (
    get_allocation,
    complete_allocation,
    no_show_allocation,
    list_allocations as list_allocations_service,
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
)
from backend.db.firestore import (
    get_match_brief,
    get_match_brief_for_ticket,
    get_plan,
    get_posting,
    get_ticket,
    list_holds,
    list_plans,
    list_postings,
    save_posting,
)

app = FastAPI(
    title="RescueGuard Backend API",
    description=(
        "Resilient Food Equity & Surplus Broker (Atlanta) — "
        "FastAPI Supervisor with Vertex AI ADK Guide Agent."
    ),
    version="0.2.0",
)


_bq_client: Optional[bigquery.Client] = None


def get_bq_client() -> bigquery.Client:
    """Return singleton BigQuery client."""
    global _bq_client
    if _bq_client is None:
        settings = get_settings()
        _bq_client = bigquery.Client(project=settings.google_cloud_project)
    return _bq_client


def _to_tristate(val: Any) -> TriStateStatus:
    if val is True or val == "YES":
        return TriStateStatus.YES
    elif val is False or val == "NO":
        return TriStateStatus.NO
    return TriStateStatus.UNRECORDED


def _row_to_recipient_record(r: Any) -> RecipientRecord:
    cold_str = (r.cold_storage or "none").lower()
    try:
        cold_enum = ColdStorageType(cold_str)
    except ValueError:
        cold_enum = ColdStorageType.NONE

    v_status = (r.verification_status or "VERIFIED").upper()
    try:
        verif_enum = VerificationStatus(v_status)
    except ValueError:
        verif_enum = VerificationStatus.VERIFIED

    dietary = list(r.dietary_flags) if getattr(r, "dietary_flags", None) else ["UNRECORDED"]

    return RecipientRecord(
        recipient_id=int(r.recipient_id),
        ein=getattr(r, "ein", None),
        name=str(r.name),
        street=str(getattr(r, "street", "") or "N/A"),
        city=str(getattr(r, "city", "") or "Atlanta"),
        state=str(getattr(r, "state", "") or "GA"),
        zip_code=str(getattr(r, "zip_code", "") or "30303"),
        cold_storage=cold_enum,
        frozen_storage=_to_tristate(getattr(r, "frozen_storage", None)),
        loading_dock=_to_tristate(getattr(r, "loading_dock", None)),
        refrigerated_transport=_to_tristate(getattr(r, "refrigerated_transport", None)),
        max_pallets=float(getattr(r, "max_pallets", 0) or 0),
        pickup_window_hours=float(getattr(r, "pickup_window_hours", 4) or 4),
        weekly_households=int(getattr(r, "weekly_households", 0) or 0),
        populations_served=getattr(r, "populations_served", None),
        dietary_flags=dietary,
        service_days=str(getattr(r, "service_days", "") or "Monday, Wednesday, Friday"),
        profile_text=str(getattr(r, "profile_text", "") or ""),
        profile_source=str(getattr(r, "profile_source", "generated") or "generated"),
        latitude=float(getattr(r, "latitude", 0.0) or 0.0),
        longitude=float(getattr(r, "longitude", 0.0) or 0.0),
        verification_status=verif_enum,
    )


# ============================================================================
# Phase 0 Endpoints
# ============================================================================


@app.get("/api/health", response_model=HealthResponse)
def get_health() -> HealthResponse:
    """Return runtime health status and non-secret active configuration."""
    settings = get_settings()
    return HealthResponse(
        status="ok",
        project=settings.google_cloud_project,
        dataset=settings.bq_dataset_starter,
        model_id=settings.model_id,
    )


# ============================================================================
# Phase 2 Endpoints
# ============================================================================


@app.post("/api/recipients/search", response_model=RecipientSemanticSearchResponse)
def search_recipients_endpoint(
    req: RecipientSemanticSearchRequest,
) -> RecipientSemanticSearchResponse:
    """Execute VECTOR_SEARCH over recipient_embeddings and return evaluated candidates."""
    client = get_bq_client()
    candidates, job_id = match_recipients(
        client=client,
        ticket_id=f"search-{req.request_id}",
        query_text=req.query_text,
        top_k=req.top_k,
        tenant_id=req.tenant_id,
    )
    return RecipientSemanticSearchResponse(
        request_id=req.request_id,
        tenant_id=req.tenant_id,
        query_text=req.query_text,
        candidates=candidates,
        bq_job_id=job_id,
    )


@app.get("/api/recipients", response_model=RecipientListResponse)
def list_recipients_endpoint(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    cold_storage: Optional[ColdStorageType] = None,
    verified_only: bool = Query(default=True),
) -> RecipientListResponse:
    """List recipients from v_all_recipients with pagination and filtering."""
    client = get_bq_client()
    settings = get_settings()
    proj = settings.google_cloud_project

    where_clauses = []
    if cold_storage:
        where_clauses.append(f"cold_storage = '{cold_storage.value}'")
    if verified_only:
        where_clauses.append("verification_status IN ('VERIFIED', 'DEMO_SIMULATED')")

    where_str = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

    count_sql = f"SELECT count(*) as total FROM `{proj}.rescueguard_app.v_all_recipients` {where_str}"
    count_res = list(client.query(count_sql).result())[0]
    total_count = int(count_res.total)

    sql = f"""
    SELECT *
    FROM `{proj}.rescueguard_app.v_all_recipients`
    {where_str}
    ORDER BY recipient_id ASC
    LIMIT {limit} OFFSET {offset}
    """
    rows = list(client.query(sql).result())
    records = [_row_to_recipient_record(r) for r in rows]

    return RecipientListResponse(
        recipients=records,
        total_count=total_count,
    )


@app.get("/api/recipients/{recipient_id}", response_model=RecipientDetailResponse)
def get_recipient_endpoint(recipient_id: int) -> RecipientDetailResponse:
    """Get single recipient details and joined demographic tract info."""
    client = get_bq_client()
    settings = get_settings()
    proj = settings.google_cloud_project

    sql = f"""
    SELECT 
      r.*,
      t.tract_geo_id,
      t.tract_status
    FROM `{proj}.rescueguard_app.v_all_recipients` r
    LEFT JOIN `{proj}.rescueguard_app.v_recipient_tract` t
      ON r.recipient_id = t.recipient_id
    WHERE r.recipient_id = {recipient_id}
    """
    rows = list(client.query(sql).result())
    if not rows:
        raise HTTPException(status_code=404, detail=f"Recipient {recipient_id} not found")

    row = rows[0]
    rec_record = _row_to_recipient_record(row)
    t_status = TractStatus.FOUND if row.tract_status == "FOUND" else TractStatus.UNKNOWN

    return RecipientDetailResponse(
        recipient=rec_record,
        tract_geo_id=row.tract_geo_id,
        tract_status=t_status,
    )


@app.post("/api/recall/check", response_model=RecallCheckResponse)
def check_recall_endpoint(req: RecallCheckRequest) -> RecallCheckResponse:
    """Execute openFDA Food Enforcement recall check before matching."""
    res = check_recall(ticket_id=req.ticket_id, product_text=req.product_text)
    return res


@app.get("/api/tickets/{ticket_id}/recall", response_model=RecallCheckListResponse)
def get_ticket_recalls_endpoint(ticket_id: str) -> RecallCheckListResponse:
    """Retrieve all recall checks performed for a specific ticket."""
    checks = list_ticket_recall_checks(ticket_id)
    return RecallCheckListResponse(ticket_id=ticket_id, checks=checks)


@app.get("/api/shelf-life/{product}", response_model=ShelfLifeLookupResponse)
def lookup_shelf_life_endpoint(product: str) -> ShelfLifeLookupResponse:
    """Look up product shelf life from USDA FoodKeeper dataset."""
    client = get_bq_client()
    result = lookup_foodkeeper(client=client, product_query=product)
    
    items: List[ShelfLifeItem] = []
    if result:
        items.append(
            ShelfLifeItem(
                product_id=int(result.product_id),
                product_name=result.product_name,
                product_subtitle=result.product_subtitle,
                category=result.category,
                refrigerated_hours=result.refrigerated_hours,
                pantry_hours=result.pantry_hours,
            )
        )

    return ShelfLifeLookupResponse(
        query_product=product,
        matches=items,
    )


@app.get("/api/tracts/{geo_id}", response_model=TractLookupResponse)
def get_tract_endpoint(geo_id: str) -> TractLookupResponse:
    """Look up census tract demographics by 11-char FIPS geo_id."""
    if len(geo_id) != 11:
        raise HTTPException(status_code=422, detail="geo_id must be an 11-character FIPS string")

    client = get_bq_client()
    settings = get_settings()
    proj = settings.google_cloud_project

    sql = f"""
    SELECT geo_id, tract_lat, tract_lon, total_pop, median_income, poverty_rate, no_vehicle_rate, assistance_rate
    FROM `{proj}.a4i_food.tract_demographics`
    WHERE geo_id = '{geo_id}'
    """
    rows = list(client.query(sql).result())
    if not rows:
        raise HTTPException(status_code=404, detail=f"Census tract {geo_id} not found")

    r = rows[0]
    return TractLookupResponse(
        geo_id=str(r.geo_id),
        tract_lat=float(r.tract_lat),
        tract_lon=float(r.tract_lon),
        total_pop=int(r.total_pop),
        median_income=float(r.median_income) if r.median_income is not None else None,
        poverty_rate=float(r.poverty_rate),
        no_vehicle_rate=float(r.no_vehicle_rate),
        assistance_rate=float(r.assistance_rate),
    )


# ============================================================================
# Phase 3 Exception Handlers & Endpoints
# ============================================================================


@app.exception_handler(NoViableMatchException)
async def no_viable_match_exception_handler(request: Request, exc: NoViableMatchException) -> JSONResponse:
    """Format structured HTTP 422 NoViableMatchFallback response."""
    return JSONResponse(
        status_code=422,
        content=exc.fallback.model_dump(mode="json"),
    )


@app.post("/api/postings", response_model=PostingResponse)
def create_posting_endpoint(req: CreatePostingRequest) -> PostingResponse:
    """Create a live donor posting with address validation (Review Fix M5)."""
    posting_id = f"post-{uuid.uuid4().hex[:8]}"
    posting = PostingResponse(
        request_id=req.request_id,
        tenant_id=req.tenant_id,
        posting_id=posting_id,
        donor_id=req.donor_id,
        donor_org_name=req.donor_org_name,
        pickup_address=req.pickup_address,
        address_type=req.address_type,
        coordinator_asserted_org_dock=req.coordinator_asserted_org_dock,
        asserted_by_role=req.asserted_by_role,
        asserted_at=req.asserted_at,
        pickup_zip=req.pickup_zip,
        pickup_lat=req.pickup_lat,
        pickup_lon=req.pickup_lon,
        product_text=req.product_text,
        track=req.track,
        quantity=req.quantity,
        quantity_unit=req.quantity_unit,
        pallets_equivalent=req.pallets_equivalent or 1.0,
        split_allowed=req.split_allowed,
        delivery_available=req.delivery_available,
        dietary_flags=req.dietary_flags,
        temperature_requirement=req.temperature_requirement,
        donor_deadline=req.donor_deadline,
        status="OPEN",
        created_at=datetime.now(timezone.utc),
    )
    save_posting(posting.model_dump())
    return posting


@app.get("/api/postings/{posting_id}", response_model=PostingResponse)
def get_posting_endpoint(
    posting_id: str,
    role: Role = Depends(get_current_role),
    org_id: Optional[str] = Depends(get_current_org_id),
    tenant_id: str = Depends(get_current_tenant),
) -> PostingResponse:
    """Get single live donor posting by ID."""
    doc = get_posting(posting_id)
    if not doc:
        raise HTTPException(status_code=404, detail=f"Posting {posting_id} not found")
    check_tenant_access(doc.get("tenant_id"), tenant_id)
    check_donor_access(doc.get("donor_id", ""), role, org_id)
    return PostingResponse(**doc)


@app.get("/api/postings", response_model=PostingListResponse)
def list_postings_endpoint() -> PostingListResponse:
    """List all live donor postings."""
    docs = list_postings()
    return PostingListResponse(
        postings=[PostingResponse(**d) for d in docs],
        total_count=len(docs),
    )


@app.post("/api/tickets", response_model=TicketResponse)
def create_ticket_endpoint(req: CreateTicketRequest) -> TicketResponse:
    """Create a ticket from starter posting or live donor posting."""
    return create_ticket(
        posting_id=req.posting_id,
        posting_source=req.posting_source,
        tenant_id=req.tenant_id,
    )


@app.get("/api/tickets", response_model=TicketListResponse)
def list_tickets_endpoint() -> TicketListResponse:
    """List all tickets."""
    tickets = list_tickets_service()
    return TicketListResponse(
        tickets=tickets,
        total_count=len(tickets),
    )


@app.get(
    "/api/tickets/{ticket_id}",
    response_model=Union[DonorTicketResponse, RecipientTicketResponse, TicketResponse],
)
def get_ticket_endpoint(
    ticket_id: str,
    role: Role = Depends(get_current_role),
    org_id: Optional[str] = Depends(get_current_org_id),
    tenant_id: str = Depends(get_current_tenant),
) -> Any:
    """Get single ticket by ID, filtered according to persona role contract."""
    ticket_doc = get_ticket(ticket_id)
    if not ticket_doc:
        raise HTTPException(status_code=404, detail=f"Ticket {ticket_id} not found")
    check_tenant_access(ticket_doc.get("tenant_id"), tenant_id)

    posting_doc = get_posting(ticket_doc.get("posting_id", "")) if ticket_doc.get("posting_id") else None
    plan_doc = get_plan(ticket_doc.get("current_plan_id", "")) if ticket_doc.get("current_plan_id") else None
    brief_doc = get_match_brief_for_ticket(ticket_id)
    holds_docs = list_holds(ticket_id=ticket_id)

    filtered = filter_ticket_for_role(
        ticket=ticket_doc,
        role=role,
        org_id=org_id,
        posting=posting_doc,
        plan=plan_doc,
        brief=brief_doc,
        holds=holds_docs,
    )
    return filtered


@app.post("/api/tickets/{ticket_id}/match", response_model=PlanResponse)
def match_ticket_endpoint(ticket_id: str, req: Optional[RunTicketMatchRequest] = None) -> PlanResponse:
    """Run Recall Guard, Matcher, Planner, Checker, and Fixer loop for a ticket."""
    force_replan = req.force_replan if req else False
    return execute_ticket_match(ticket_id=ticket_id, force_replan=force_replan)


@app.get("/api/tickets/{ticket_id}/plans", response_model=PlanListResponse)
def list_ticket_plans_endpoint(ticket_id: str) -> PlanListResponse:
    """List all append-only plan versions for a ticket, ordered by version."""
    plans = list_plans(ticket_id)
    return PlanListResponse(
        ticket_id=ticket_id,
        plans=[PlanResponse(**p) for p in plans],
    )


@app.get(
    "/api/plans/{plan_id}",
    response_model=Union[DonorPlanResponse, RecipientPlanResponse, PlanResponse],
)
def get_plan_endpoint(
    plan_id: str,
    role: Role = Depends(get_current_role),
    org_id: Optional[str] = Depends(get_current_org_id),
    tenant_id: str = Depends(get_current_tenant),
) -> Any:
    """Get single plan version by ID, filtered according to persona role contract."""
    plan_doc = get_plan(plan_id)
    if not plan_doc:
        raise HTTPException(status_code=404, detail=f"Plan {plan_id} not found")
    check_tenant_access(plan_doc.get("tenant_id"), tenant_id)

    ticket_doc = get_ticket(plan_doc.get("ticket_id", "")) if plan_doc.get("ticket_id") else None
    posting_doc = get_posting(ticket_doc.get("posting_id", "")) if ticket_doc and ticket_doc.get("posting_id") else None
    brief_doc = get_match_brief(plan_id) or (get_match_brief_for_ticket(plan_doc.get("ticket_id", "")) if plan_doc.get("ticket_id") else None)
    holds_docs = list_holds(ticket_id=plan_doc.get("ticket_id", "")) if plan_doc.get("ticket_id") else []

    filtered = filter_plan_for_role(
        plan=plan_doc,
        role=role,
        org_id=org_id,
        ticket=ticket_doc,
        posting=posting_doc,
        brief=brief_doc,
        holds=holds_docs,
    )
    return filtered


@app.get("/api/tickets/{ticket_id}/parameters", response_model=TicketParametersResponse)
def get_ticket_parameters_endpoint(ticket_id: str) -> TicketParametersResponse:
    """Get ticket-scoped matching parameters."""
    params = get_ticket_parameters(ticket_id)
    return TicketParametersResponse(
        ticket_id=ticket_id,
        parameters=params,
    )


@app.post("/api/tickets/{ticket_id}/parameters", response_model=TicketParametersResponse)
def update_ticket_parameters_endpoint(
    ticket_id: str,
    req: UpdateTicketParametersRequest,
) -> TicketParametersResponse:
    """Update ticket-scoped matching parameters."""
    params = update_ticket_parameters(ticket_id, req.parameters)
    return TicketParametersResponse(
        ticket_id=ticket_id,
        parameters=params,
    )


# ============================================================================
# Phase 4 Endpoints: Supervisor, Identity, Holds, Tasks, Guide Chat
# ============================================================================


@app.get("/api/me", response_model=MeResponse)
def get_me_endpoint(
    role: Role = Depends(get_current_role),
    tenant_id: str = Depends(get_current_tenant),
    org_id: Optional[str] = Depends(get_current_org_id),
) -> MeResponse:
    """Return persona and tenant derived from request headers."""
    eff_org_id = org_id or ("atlanta-coordinator-desk" if role == Role.COORDINATOR else f"{role.value.lower()}-org")
    return MeResponse(
        role=role,
        org_id=eff_org_id,
        tenant_id=tenant_id,
    )


@app.post("/api/tickets/{ticket_id}/cancel", response_model=TicketResponse)
def cancel_ticket_endpoint(
    ticket_id: str,
    req: Optional[CancelTicketRequest] = None,
    role: Role = Depends(get_current_role),
    org_id: Optional[str] = Depends(get_current_org_id),
    tenant_id: str = Depends(get_current_tenant),
) -> TicketResponse:
    """Cancel ticket, internally release all active holds, and notify recipients."""
    reason = req.reason if req else "Cancelled by user"
    cancelled = cancel_ticket(ticket_id, reason=reason, role=role, current_org_id=org_id)
    check_tenant_access(cancelled.get("tenant_id"), tenant_id)
    return TicketResponse(**cancelled)


@app.post("/api/plans/{plan_id}/approve", response_model=PlanApprovalResponse)
def approve_plan_endpoint(
    plan_id: str,
    req: Optional[ApprovePlanRequest] = None,
    role: Role = Depends(get_current_role),
    tenant_id: str = Depends(get_current_tenant),
) -> PlanApprovalResponse:
    """Approve a plan version, starting 10-minute holds for all allocations."""
    approver_role = req.approver_role if (req and req.approver_role) else role
    notes = req.notes if req else None
    request_id = req.request_id if (req and req.request_id and req.request_id != "req-default") else None
    result = approve_plan(
        plan_id=plan_id,
        approver_role=approver_role,
        notes=notes,
        request_id=request_id,
    )
    return PlanApprovalResponse(**result)


@app.post("/api/plans/{plan_id}/reject", response_model=PlanResponse)
def reject_plan_endpoint(
    plan_id: str,
    req: RejectPlanRequest,
    role: Role = Depends(get_current_role),
) -> PlanResponse:
    """Coordinator rejects a plan version, recording reason and triggering re-plan."""
    new_plan = reject_plan(plan_id=plan_id, reason=req.reason)
    return PlanResponse(**new_plan)


@app.get("/api/tickets/{ticket_id}/holds", response_model=HoldListResponse)
def list_ticket_holds_endpoint(
    ticket_id: str,
    role: Role = Depends(get_current_role),
    org_id: Optional[str] = Depends(get_current_org_id),
    tenant_id: str = Depends(get_current_tenant),
) -> HoldListResponse:
    """List holds for a ticket, evaluating 10-minute expiry."""
    ticket = get_ticket_service(ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail=f"Ticket {ticket_id} not found")
    check_tenant_access(ticket.tenant_id, tenant_id)
    holds = get_holds_for_ticket(ticket_id)
    if role == Role.RECIPIENT and org_id:
        holds = [h for h in holds if str(h.get("recipient_id")) == str(org_id)]
    return HoldListResponse(
        ticket_id=ticket_id,
        holds=[HoldResponse(**h) for h in holds],
    )


@app.get("/api/holds/{hold_id}", response_model=HoldResponse)
def get_hold_endpoint(
    hold_id: str,
    role: Role = Depends(get_current_role),
    org_id: Optional[str] = Depends(get_current_org_id),
    tenant_id: str = Depends(get_current_tenant),
) -> HoldResponse:
    """Get single hold record by ID."""
    hold = get_hold(hold_id)
    check_tenant_access(hold.get("tenant_id"), tenant_id)
    check_recipient_access(hold.get("recipient_id"), role, org_id)
    return HoldResponse(**hold)


@app.post("/api/holds/{hold_id}/confirm", response_model=HoldResponse)
def confirm_hold_endpoint(
    hold_id: str,
    req: ConfirmHoldRequest,
    role: Role = Depends(get_current_role),
    org_id: Optional[str] = Depends(get_current_org_id),
    tenant_id: str = Depends(get_current_tenant),
) -> HoldResponse:
    """Recipient accepts/confirms an active hold."""
    check_recipient_access(req.recipient_id, role, org_id)
    hold = confirm_hold(hold_id=hold_id, recipient_id=req.recipient_id)
    check_tenant_access(hold.get("tenant_id"), tenant_id)
    return HoldResponse(**hold)


@app.post("/api/holds/{hold_id}/release", response_model=HoldResponse)
def release_hold_endpoint(
    hold_id: str,
    req: ReleaseHoldRequest,
) -> HoldResponse:
    """Release an active hold, freeing capacity."""
    hold = release_hold(hold_id=hold_id, reason=req.reason)
    return HoldResponse(**hold)


@app.post("/api/tickets/{ticket_id}/decline", response_model=PlanResponse)
def decline_allocation_endpoint(
    ticket_id: str,
    req: DeclineAllocationRequest,
    role: Role = Depends(get_current_role),
    org_id: Optional[str] = Depends(get_current_org_id),
) -> PlanResponse:
    """Process per-allocation decline, promote next viable pantry, and generate new plan version."""
    check_recipient_access(req.recipient_id, role, org_id)
    new_plan = decline_allocation_and_replan(
        ticket_id=ticket_id,
        recipient_id=req.recipient_id,
        allocation_id=req.allocation_id,
        reason=req.reason,
        request_id=req.request_id,
    )
    return PlanResponse(**new_plan)


@app.post("/api/allocations/{allocation_id}/complete", response_model=AllocationResponse)
def complete_allocation_endpoint(
    allocation_id: str,
    req: Optional[CompleteAllocationRequest] = None,
) -> AllocationResponse:
    """Mark allocation completed when pickup finishes."""
    notes = req.notes if req else None
    alloc = complete_allocation(allocation_id=allocation_id, notes=notes)
    return AllocationResponse(**alloc)


@app.post("/api/allocations/{allocation_id}/no-show", response_model=AllocationResponse)
def no_show_allocation_endpoint(
    allocation_id: str,
    req: NoShowAllocationRequest,
) -> AllocationResponse:
    """Record recipient no-show in fairness ledger."""
    alloc = no_show_allocation(allocation_id=allocation_id, reason=req.reason)
    return AllocationResponse(**alloc)


@app.get("/api/allocations", response_model=AllocationListResponse)
def list_allocations_endpoint(
    ticket_id: Optional[str] = Query(None),
    role: Role = Depends(get_current_role),
    org_id: Optional[str] = Depends(get_current_org_id),
    tenant_id: str = Depends(get_current_tenant),
) -> AllocationListResponse:
    """List allocations filtered by tenant and persona."""
    allocs = list_allocations_service(ticket_id=ticket_id)
    filtered = []
    for a in allocs:
        if a.get("tenant_id") and a.get("tenant_id") != tenant_id:
            continue
        if role == Role.RECIPIENT and org_id and str(a.get("recipient_id")) != str(org_id):
            continue
        filtered.append(AllocationResponse(**a))
    return AllocationListResponse(
        allocations=filtered,
        total_count=len(filtered),
    )


@app.post("/api/tasks", response_model=TaskResponse)
def create_task_endpoint(
    req: CreateTaskRequest,
    tenant_id: str = Depends(get_current_tenant),
) -> TaskResponse:
    """Create a coordinator or system gap task."""
    task = create_task(
        ticket_id=req.ticket_id,
        task_type=req.task_type,
        owner_role=req.owner_role,
        description=req.description,
        plan_id=req.plan_id,
        tenant_id=req.tenant_id or tenant_id,
    )
    return TaskResponse(**task)


@app.get("/api/tasks", response_model=TaskListResponse)
def list_tasks_endpoint(
    ticket_id: Optional[str] = Query(None),
    owner_role: Optional[str] = Query(None),
    tenant_id: str = Depends(get_current_tenant),
) -> TaskListResponse:
    """List tasks filtered by ticket, owner_role, and tenant."""
    tasks = list_tasks(ticket_id=ticket_id, owner_role=owner_role)
    filtered = [TaskResponse(**t) for t in tasks if t.get("tenant_id", tenant_id) == tenant_id]
    return TaskListResponse(tasks=filtered, total_count=len(filtered))


@app.get("/api/tasks/{task_id}", response_model=TaskResponse)
def get_task_endpoint(
    task_id: str,
    tenant_id: str = Depends(get_current_tenant),
) -> TaskResponse:
    """Get single task by ID."""
    task = get_task(task_id)
    check_tenant_access(task.get("tenant_id"), tenant_id)
    return TaskResponse(**task)


@app.patch("/api/tasks/{task_id}", response_model=TaskResponse)
def patch_task_endpoint(
    task_id: str,
    req: PatchTaskRequest,
) -> TaskResponse:
    """Update task status, delegating to approval service if APPROVED."""
    req_id = req.request_id if (req.request_id and req.request_id != "req-default") else None
    task = patch_task(
        task_id=task_id,
        status=req.status,
        approver_role=req.approver_role,
        request_id=req_id,
    )
    return TaskResponse(**task)


@app.post("/api/actions/approve", response_model=ActionApprovalResponse)
def approve_action_endpoint(
    req: ApproveActionRequest,
) -> ActionApprovalResponse:
    """Canonical entry point for approving actions proposed by Guide chat or desk."""
    req_id = req.request_id if (req.request_id and req.request_id != "req-default") else None
    res = approve_action(
        action=req.action,
        approver_role=req.approver_role,
        request_id=req_id,
    )
    return ActionApprovalResponse(**res)


@app.post("/api/assistant/chat", response_model=AssistantChatResponse)
def assistant_chat_endpoint(
    req: AssistantChatRequest,
) -> AssistantChatResponse:
    """Interact with Guide agent (Vertex AI ADK)."""
    hold_val = req.hold_status.value if req.hold_status and hasattr(req.hold_status, "value") else (str(req.hold_status) if req.hold_status else None)
    res = handle_assistant_chat(
        session_id=req.session_id,
        message=req.message,
        role=req.role,
        ticket_id=req.ticket_id,
        posting_id=req.posting_id,
        plan_version=req.plan_version,
        step=req.step,
        hold_status=hold_val,
    )
    return AssistantChatResponse(**res)


@app.get("/api/conversations/{session_id}", response_model=ConversationResponse)
def get_conversation_endpoint(session_id: str) -> ConversationResponse:
    """Retrieve full conversation history for session."""
    conv = get_conversation_history(session_id)
    return ConversationResponse(**conv)



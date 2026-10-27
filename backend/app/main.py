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
from typing import Any, Dict, List, Optional
import uuid
from fastapi import FastAPI, HTTPException, Query, Request
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
    RunTicketMatchRequest,
    PlanResponse,
    PlanListResponse,
    TicketParametersResponse,
    UpdateTicketParametersRequest,
)
from schemas.common import NoViableMatchFallback
from schemas.enums import (
    ColdStorageType,
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
from backend.db.firestore import (
    get_plan,
    get_posting,
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
def get_posting_endpoint(posting_id: str) -> PostingResponse:
    """Get single live donor posting by ID."""
    doc = get_posting(posting_id)
    if not doc:
        raise HTTPException(status_code=404, detail=f"Posting {posting_id} not found")
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


@app.get("/api/tickets/{ticket_id}", response_model=TicketResponse)
def get_ticket_endpoint(ticket_id: str) -> TicketResponse:
    """Get single ticket by ID."""
    t = get_ticket_service(ticket_id)
    if not t:
        raise HTTPException(status_code=404, detail=f"Ticket {ticket_id} not found")
    return t


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


@app.get("/api/plans/{plan_id}", response_model=PlanResponse)
def get_plan_endpoint(plan_id: str) -> PlanResponse:
    """Get single plan version by ID."""
    plan = get_plan(plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail=f"Plan {plan_id} not found")
    return PlanResponse(**plan)


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


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

from typing import Any, Dict, List, Optional
from fastapi import FastAPI, HTTPException, Query
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
)
from schemas.enums import (
    ColdStorageType,
    TractStatus,
    TriStateStatus,
    VerificationStatus,
)
from backend.services.matcher import match_recipients
from backend.services.recall import check_recall, list_ticket_recall_checks
from backend.services.shelf_life import lookup_foodkeeper

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

"""Phase 0 contract, hard-gate, pickup-address validation, health, and MCP test suite."""

from datetime import datetime, timezone
from pathlib import Path
from fastapi.testclient import TestClient
import pytest
from pydantic import ValidationError

from backend.app.config import (
    CHECKER_MAX_ATTEMPTS,
    CRATES_PER_PALLET,
    HOLD_MINUTES,
    OPENFDA_MAX_CALLS_PER_RUN,
    get_settings,
)
from backend.app.main import app
from backend.tools.mcp_bigquery import (
    execute_readonly_mcp_sql,
    list_mcp_tools,
    validate_readonly_sql,
)
from schemas.api import (
    ALL_29_CONTRACT_STORES,
    BQ_HISTORY_SINKS,
    CreatePostingRequest,
    ENDPOINT_CONTRACT_REGISTRY,
    FIRESTORE_PEOPLE_SAFETY_AUDIT_COLLECTIONS,
    FIRESTORE_TICKET_COLLECTIONS,
    HealthResponse,
    STARTER_BQ_TABLES,
    TEAM_BQ_TABLES_AND_VIEWS,
)
from schemas.common import (
    ActionCard,
    ResolvedClockContract,
    compute_clock_margin_hours,
    compute_impact_score,
    convert_to_pallets,
    validate_donor_pickup_address,
)
from schemas.enums import (
    ActionTargetType,
    AddressType,
    AllocationStatus,
    CandidateStatus,
    ColdStorageType,
    DistanceSource,
    EquityVerdict,
    ExecutionSource,
    HoldStatus,
    NotificationEvent,
    OverrideStatus,
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

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_all_29_contract_stores_registered() -> None:
    """Verify all 29 locked stores/collections/views from Part 2 are present and registered."""
    assert len(ALL_29_CONTRACT_STORES) == 29
    assert len(STARTER_BQ_TABLES) == 4
    assert len(TEAM_BQ_TABLES_AND_VIEWS) == 6
    assert len(FIRESTORE_TICKET_COLLECTIONS) == 9
    assert len(FIRESTORE_PEOPLE_SAFETY_AUDIT_COLLECTIONS) == 7
    assert len(BQ_HISTORY_SINKS) == 3

    contracts_md = (REPO_ROOT / "CONTRACTS.md").read_text(encoding="utf-8")
    context_md = (REPO_ROOT / "CONTEXT.md").read_text(encoding="utf-8")

    for store in ALL_29_CONTRACT_STORES:
        assert store.split(".")[-1] in contracts_md, f"Store {store} missing in CONTRACTS.md"
        assert store.split(".")[-1] in context_md, f"Store {store} missing in CONTEXT.md"


def test_all_52_endpoint_contracts_registered_and_valid() -> None:
    """Verify all 52 frozen endpoints from Part 2 are registered with valid request/response models."""
    assert len(ENDPOINT_CONTRACT_REGISTRY) == 52

    contracts_md = (REPO_ROOT / "CONTRACTS.md").read_text(encoding="utf-8")
    context_md = (REPO_ROOT / "CONTEXT.md").read_text(encoding="utf-8")

    for (method, path), (req_cls, resp_cls) in ENDPOINT_CONTRACT_REGISTRY.items():
        assert path.startswith("/api/"), f"Endpoint must start with /api/: {path}"
        assert req_cls is not None
        assert resp_cls is not None
        assert path in contracts_md, f"Endpoint path {path} missing in CONTRACTS.md"
        assert (
            f"`{method}` | `{path}`" in contracts_md
            or f"{method}  {path}" in contracts_md
            or f"{method} {path}" in contracts_md
        ), f"Endpoint {method} {path} missing in CONTRACTS.md"
        assert path in context_md, f"Endpoint {path} missing in CONTEXT.md"


def test_hard_gate_1_units_conversion() -> None:
    """Verify Hard Gate 1: CRATES_PER_PALLET = 20 and unit conversion calculations."""
    assert CRATES_PER_PALLET == 20
    assert convert_to_pallets(20.0, QuantityUnit.CRATES) == 1.0
    assert convert_to_pallets(10.0, QuantityUnit.CRATES) == 0.5
    assert convert_to_pallets(5.0, QuantityUnit.CRATES) == 0.25
    assert convert_to_pallets(2.5, QuantityUnit.PALLETS) == 2.5

    with pytest.raises(ValueError):
        convert_to_pallets(-1.0, QuantityUnit.CRATES)

    with pytest.raises(ValueError):
        convert_to_pallets(0.0, QuantityUnit.PALLETS)


def test_hard_gate_2_resolved_clock_and_starter_field_facts() -> None:
    """Verify Hard Gate 2: Resolved clock model, margin formula, and starter field facts."""
    now = datetime.now(timezone.utc)
    clock = ResolvedClockContract(
        resolved_deadline=now,
        resolved_shelf_life_hours=6.0,
        shelf_life_source=ShelfLifeSource.FOODKEEPER,
        resolved_at=now,
    )
    assert clock.shelf_life_source == ShelfLifeSource.FOODKEEPER
    assert clock.resolved_shelf_life_hours == 6.0

    # Margin formula: resolved_hours_left - pickup_window_hours - travel_buffer_hours
    margin = compute_clock_margin_hours(
        resolved_hours_left=6.0,
        pickup_window_hours=2.0,
        travel_buffer_hours=0.5,
    )
    assert margin == 3.5

    # ShelfLifeSource values
    assert ShelfLifeSource.FOODKEEPER.value == "FOODKEEPER"
    assert ShelfLifeSource.DONOR_FALLBACK.value == "DONOR_FALLBACK"
    assert ShelfLifeSource.NOT_APPLICABLE.value == "NOT_APPLICABLE"

    # Verified distinct cold_storage values in Atlanta starter data
    assert ColdStorageType.DOMESTIC.value == "domestic"
    assert ColdStorageType.WALK_IN.value == "walk-in"
    assert ColdStorageType.MEDICAL.value == "medical"
    assert ColdStorageType.COMMERCIAL.value == "commercial"
    assert ColdStorageType.NONE.value == "none"
    assert ColdStorageType.VEHICLE.value == "vehicle"


def test_review_fix_m5_donor_pickup_address_validation() -> None:
    """Verify Review Fix M5: ORG_DOCK + coordinator assertion accepted; residential pattern rejected."""
    # (1) Valid posting: ORG_DOCK with coordinator assertion and commercial address
    valid_posting = CreatePostingRequest(
        donor_id="org-midtown-market",
        donor_org_name="Midtown Fresh Market",
        pickup_address="650 Ponce de Leon Ave NE Dock B, Atlanta, GA 30308",
        address_type=AddressType.ORG_DOCK,
        coordinator_asserted_org_dock=True,
        asserted_by_role=Role.COORDINATOR,
        pickup_zip="30308",
        product_text="10 crates fresh spinach",
        quantity=10.0,
        quantity_unit=QuantityUnit.CRATES,
        donor_deadline=datetime.now(timezone.utc),
    )
    assert valid_posting.address_type == AddressType.ORG_DOCK
    assert valid_posting.pallets_equivalent == 0.5

    # (2) Reject obviously residential free-text address
    with pytest.raises(ValueError, match="Rejected residential free-text pattern"):
        CreatePostingRequest(
            donor_id="donor-home",
            donor_org_name="Jane Doe",
            pickup_address="123 Peachtree St Apt 4B, pick up at my house front porch, Atlanta, GA",
            address_type=AddressType.ORG_DOCK,
            coordinator_asserted_org_dock=True,
            asserted_by_role=Role.COORDINATOR,
            pickup_zip="30308",
            product_text="Leftover party trays",
            quantity=2.0,
            quantity_unit=QuantityUnit.CRATES,
            donor_deadline=datetime.now(timezone.utc),
        )

    # (3) Reject non-ORG_DOCK address_type
    with pytest.raises(ValueError, match="Invalid address_type"):
        validate_donor_pickup_address(
            donor_org_name="Midtown Market",
            pickup_address="650 Ponce de Leon Ave NE Dock B, Atlanta, GA 30308",
            address_type=AddressType.RESIDENTIAL,
            coordinator_asserted_org_dock=True,
            asserted_by_role=Role.COORDINATOR,
        )

    # (4) Reject missing coordinator assertion
    with pytest.raises(ValueError, match="requires coordinator assertion of ORG_DOCK"):
        validate_donor_pickup_address(
            donor_org_name="Midtown Market",
            pickup_address="650 Ponce de Leon Ave NE Dock B, Atlanta, GA 30308",
            address_type=AddressType.ORG_DOCK,
            coordinator_asserted_org_dock=False,
            asserted_by_role=Role.DONOR,
        )


def test_review_fix_m1_execution_source_and_impact_score_fixture() -> None:
    """Verify Review Fix M1 enum and locked Impact Score formula fixture check."""
    assert ExecutionSource.CODE_EXECUTION.value == "CODE_EXECUTION"
    assert ExecutionSource.PYTHON_FALLBACK.value == "PYTHON_FALLBACK"

    # Part 2 line 765 hand-checked fixture: Need 88, Rescue 100, Equity 82, Reliability 85 -> 88.9 -> 89
    total = compute_impact_score(need=88.0, rescue=100.0, equity=82.0, reliability=85.0)
    assert total == 89, f"Expected locked fixture total 89, got {total}"


def test_action_card_schema() -> None:
    """Verify ActionCard schema for canonical POST /api/actions/approve."""
    card = ActionCard(
        action_id="act-plan-001",
        target_type=ActionTargetType.PLAN,
        target_id="plan-v1",
        target_endpoint="/api/plans/plan-v1/approve",
        description="Approve equity-optimal plan version 1",
    )
    dumped = card.model_dump()
    assert dumped["target_type"] == "plan"
    assert dumped["target_endpoint"] == "/api/plans/plan-v1/approve"


def test_phase_0_okf_files_and_no_frontend_folder() -> None:
    """Verify CONTEXT.md (<300 lines), CONTRACTS.md, frontend-contracts/README.md, and all 12 skills."""
    context_path = REPO_ROOT / "CONTEXT.md"
    contracts_path = REPO_ROOT / "CONTRACTS.md"
    fe_readme_path = REPO_ROOT / "frontend-contracts" / "README.md"

    assert context_path.exists()
    assert contracts_path.exists()
    assert fe_readme_path.exists()
    assert not (REPO_ROOT / "frontend").exists(), "No frontend/ folder allowed in Phases 0-9"

    context_lines = context_path.read_text(encoding="utf-8").splitlines()
    assert len(context_lines) < 300, f"CONTEXT.md must be <300 lines, got {len(context_lines)}"

    expected_skills = [
        "matcher",
        "constraint",
        "planner",
        "checker",
        "supervisor",
        "guide",
        "data",
        "onboarding",
        "maps",
        "impact-fairness",
        "recall",
        "last-mile",
    ]
    for skill_name in expected_skills:
        skill_file = REPO_ROOT / ".agent" / "skills" / skill_name / "SKILL.md"
        assert skill_file.exists(), f"Missing skill stub: {skill_file}"


def test_settings_and_health_endpoint() -> None:
    """Verify runtime settings and GET /api/health response."""
    settings = get_settings()
    assert settings.google_cloud_project and settings.google_cloud_project != "your-gcp-project-id"
    assert settings.bq_dataset_starter == "a4i_food"
    assert settings.bq_dataset_app == "rescueguard_app"
    assert settings.checker_max_attempts == 3
    assert settings.hold_minutes == 10
    assert settings.crates_per_pallet == 20
    assert settings.firestore_location == "nam5"

    client = TestClient(app)
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    validated = HealthResponse.model_validate(body)
    assert validated.status == "ok"
    assert validated.project == settings.google_cloud_project
    assert validated.dataset == "a4i_food"
    assert validated.model_id == "gemini-2.5-flash"


def test_managed_bigquery_mcp_called_and_readonly_guard() -> None:
    """Verify Review Fix C1: read-only SQL guard + live call to https://bigquery.googleapis.com/mcp."""
    with pytest.raises(ValueError, match="MCP_READONLY_VIOLATION"):
        validate_readonly_sql("DROP TABLE a4i_food.recipients")

    with pytest.raises(ValueError, match="MCP_READONLY_VIOLATION"):
        validate_readonly_sql("INSERT INTO a4i_food.recipients VALUES (999)")

    tools = list_mcp_tools()
    tool_names = {t.get("name") for t in tools}
    assert "execute_sql" in tool_names

    sql = (
        "SELECT COUNT(*) AS recipient_count, "
        "COUNTIF(profile_source = 'planted') AS planted_count "
        "FROM `a4i_food.recipients`"
    )
    mcp_res = execute_readonly_mcp_sql(sql)
    assert mcp_res["mcp_endpoint"] == "https://bigquery.googleapis.com/mcp"
    assert mcp_res["job_complete"] is True
    assert mcp_res["job_id"], "Expected non-empty BigQuery MCP queryId/job_id"
    assert len(mcp_res["rows"]) == 1
    assert mcp_res["rows"][0]["recipient_count"] == "127"
    assert mcp_res["rows"][0]["planted_count"] == "9"

"""Phase 3 Test Suite — Planner, Splitter, Checker, Fixer, Code Execution, and Plan Versions.

Per Part 2 lines 1410-1423:
1. Spinach fixture: a v1 that wastes part of the load is rejected with reason;
   v2 split places the full load and passes.
2. Farm fixture: 12-pallet-type load splits across pantries with no overload
   (using verified Atlanta capacities/units).
3. Loop fixture: fixer fails 3 times -> escalates, plan stays DRAFT, no infinite loop.
4. No-viable fixture: match returns 422 fallback (NoViableMatchFallback), not a plan.
5. Ticket creation from starter posting and live donor posting work and do not collide on IDs.
6. Code Execution explicit integration point (Review Fix M1): split/margin maths
   execute via Gemini Code Execution (or labeled fallback); code and output stored on the plan.
7. API endpoints integration: full REST flow for postings, tickets, match, plans, and parameters.
"""

from datetime import datetime, timezone, timedelta
import uuid
import pytest
from fastapi.testclient import TestClient
from google.cloud import bigquery

from backend.app.config import get_settings
from backend.app.main import app
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
    execute_ticket_match,
    NoViableMatchException,
)
from backend.db.firestore import (
    get_plan,
    list_plans,
    save_posting,
)
from schemas.api import (
    CreatePostingRequest,
    CreateTicketRequest,
    RunTicketMatchRequest,
    TicketParameters,
    UpdateTicketParametersRequest,
)
from schemas.enums import (
    AddressType,
    ExecutionSource,
    PlanStatus,
    PostingSource,
    QuantityUnit,
    Role,
    TicketStep,
)


@pytest.fixture(scope="module")
def bq_client():
    settings = get_settings()
    return bigquery.Client(project=settings.google_cloud_project)


@pytest.fixture(scope="module")
def api_client():
    return TestClient(app)


# ============================================================================
# Test 1: Spinach Fixture (Waste rejected in v1; split v2 passes)
# ============================================================================


def test_spinach_fixture_waste_rejected_and_v2_split_passes():
    """Test 1: Spinach fixture — v1 with waste rejected; v2 split places full load and passes."""
    ticket_id = f"test-spinach-{uuid.uuid4().hex[:8]}"

    # Posting data: 10 crates of spinach (0.5 pallets), refrigerated
    posting_data = {
        "product_text": "10 crates of spinach, harvested yesterday, needs cold storage",
        "quantity": 10.0,
        "quantity_unit": QuantityUnit.CRATES,
        "pallets_equivalent": 0.5,
        "temperature_requirement": "refrigerated",
        "split_allowed": True,
        "resolved_shelf_life_hours": 24.0,
    }

    # Two viable pantries with cold storage, capacity 8 crates (0.4 pallets) each
    viable_candidates = [
        {
            "recipient_id": 101,
            "name": "Atlanta Community Food Bank - South Hub",
            "max_pallets": 0.4,  # max 8 crates
            "pickup_window_hours": 2.0,
            "travel_buffer_hours": 0.5,
            "tract_geo_id": "13121000100",
            "need_score": 65.0,
            "distance_km": 3.2,
            "cold_storage": "yes",
            "frozen_storage": False,
        },
        {
            "recipient_id": 102,
            "name": "West End Neighborhood Pantry",
            "max_pallets": 0.4,  # max 8 crates
            "pickup_window_hours": 2.0,
            "travel_buffer_hours": 0.5,
            "tract_geo_id": "13121000200",
            "need_score": 58.0,
            "distance_km": 4.5,
            "cold_storage": "yes",
            "frozen_storage": False,
        },
    ]
    cand_lookup = {c["recipient_id"]: c for c in viable_candidates}

    # Generate v1 with intentional waste (only allocates 40% / 4 crates, wasting 6 crates)
    plan_v1 = create_initial_plan(
        ticket_id=ticket_id,
        posting_data=posting_data,
        viable_candidates=viable_candidates,
        plan_version=1,
        force_waste=True,
    )

    assert plan_v1.plan_version == 1
    assert plan_v1.plan_id == f"plan-{ticket_id}-v1"
    assert len(plan_v1.allocations) == 1
    assert plan_v1.allocations[0].quantity == 4.0  # 4 crates allocated

    # Run Independent Checker on v1
    is_passed_v1, reasons_v1, _ = check_plan(
        plan=plan_v1,
        posting_data=posting_data,
        candidate_lookup=cand_lookup,
    )

    # v1 MUST be rejected due to unallocated waste
    assert not is_passed_v1
    assert plan_v1.status == PlanStatus.CHECKER_REJECTED
    assert len(reasons_v1) >= 1
    assert any("wasted" in r or "unallocated" in r for r in reasons_v1)
    assert any("6.0 CRATES wasted" in r for r in reasons_v1)

    # Fixer rewrites the flagged waste: allocates full load across both viable pantries
    plan_v2, is_escalated = fix_plan(
        plan=plan_v1,
        checker_reasons=reasons_v1,
        posting_data=posting_data,
        viable_candidates=viable_candidates,
        candidate_lookup=cand_lookup,
    )

    assert not is_escalated
    assert plan_v2.plan_version == 2
    assert plan_v2.plan_id == f"plan-{ticket_id}-v2"
    assert plan_v2.fixer_attempt_count == 1
    assert plan_v2.last_plan_hash == plan_v1.plan_hash
    assert plan_v2.last_checker_reason is not None
    assert len(plan_v2.fixer_changes) >= 1

    # In v2, the full load (10 crates) is allocated
    total_alloc_v2 = sum(a.quantity for a in plan_v2.allocations)
    assert total_alloc_v2 == 10.0
    assert len(plan_v2.allocations) == 2  # split across both pantries (e.g. 8 + 2 crates)

    # Run Independent Checker on v2
    is_passed_v2, reasons_v2, _ = check_plan(
        plan=plan_v2,
        posting_data=posting_data,
        candidate_lookup=cand_lookup,
    )

    # v2 MUST pass with zero checker rejection reasons
    assert is_passed_v2
    assert plan_v2.status == PlanStatus.DRAFT
    assert reasons_v2 == []

    # Verify append-only history in Firestore: both v1 and v2 exist in order
    plans = list_plans(ticket_id)
    assert len(plans) >= 2
    assert plans[0]["plan_version"] == 1
    assert plans[1]["plan_version"] == 2
    assert plans[0]["status"] == PlanStatus.CHECKER_REJECTED.value
    assert plans[1]["status"] == PlanStatus.DRAFT.value


# ============================================================================
# Test 2: Farm Fixture (12-pallet load splits with no overload)
# ============================================================================


def test_farm_fixture_large_load_splits_without_overload():
    """Test 2: Farm fixture — 12-pallet load splits across pantries with no overload."""
    ticket_id = f"test-farm-{uuid.uuid4().hex[:8]}"

    posting_data = {
        "product_text": "5 tons of potatoes still in the field, we can load pallets",
        "quantity": 12.0,
        "quantity_unit": QuantityUnit.PALLETS,
        "pallets_equivalent": 12.0,
        "temperature_requirement": "ambient",
        "split_allowed": True,
        "resolved_shelf_life_hours": 72.0,
    }

    # Verified Atlanta pantries with varying capacities (no single pantry can take 12 pallets)
    viable_candidates = [
        {
            "recipient_id": 201,
            "name": "Midtown Atlanta Food Center",
            "max_pallets": 5.0,
            "pickup_window_hours": 3.0,
            "travel_buffer_hours": 0.5,
            "tract_geo_id": "13121001000",
            "need_score": 72.0,
            "distance_km": 5.1,
            "cold_storage": "none",
            "frozen_storage": False,
        },
        {
            "recipient_id": 202,
            "name": "East Lake Community Pantry",
            "max_pallets": 4.0,
            "pickup_window_hours": 3.0,
            "travel_buffer_hours": 0.5,
            "tract_geo_id": "13121001200",
            "need_score": 64.0,
            "distance_km": 7.4,
            "cold_storage": "none",
            "frozen_storage": False,
        },
        {
            "recipient_id": 203,
            "name": "Bankhead Relief Mission",
            "max_pallets": 3.0,
            "pickup_window_hours": 4.0,
            "travel_buffer_hours": 0.5,
            "tract_geo_id": "13121001500",
            "need_score": 80.0,
            "distance_km": 8.9,
            "cold_storage": "none",
            "frozen_storage": False,
        },
    ]
    cand_lookup = {c["recipient_id"]: c for c in viable_candidates}

    plan = create_initial_plan(
        ticket_id=ticket_id,
        posting_data=posting_data,
        viable_candidates=viable_candidates,
        plan_version=1,
    )

    # All 12 pallets must be allocated across the 3 pantries (5 + 4 + 3 = 12)
    total_pallets = sum(a.pallets_equivalent for a in plan.allocations)
    assert total_pallets == 12.0
    assert len(plan.allocations) == 3

    # Verify each pantry is within its individual max capacity
    for alloc in plan.allocations:
        cand = cand_lookup[alloc.recipient_id]
        assert alloc.pallets_equivalent <= cand["max_pallets"]

    # Checker verifies no capacity overload and passes
    is_passed, reasons, _ = check_plan(
        plan=plan,
        posting_data=posting_data,
        candidate_lookup=cand_lookup,
    )
    assert is_passed
    assert plan.status == PlanStatus.DRAFT
    assert reasons == []


# ============================================================================
# Test 3: Loop Fixture (Fixer fails 3 times -> escalates, no infinite loop)
# ============================================================================


def test_loop_fixture_max_attempts_and_guards_escalate():
    """Test 3: Loop fixture — fixer fails 3 times -> escalates, plan stays DRAFT, no loop."""
    ticket_id = f"test-loop-{uuid.uuid4().hex[:8]}"

    posting_data = {
        "product_text": "Test perishables",
        "quantity": 10.0,
        "quantity_unit": QuantityUnit.PALLETS,
        "pallets_equivalent": 10.0,
        "temperature_requirement": "refrigerated",
        "resolved_shelf_life_hours": 24.0,
    }

    plan_v0 = create_initial_plan(
        ticket_id=ticket_id,
        posting_data=posting_data,
        viable_candidates=[],
        plan_version=1,
        force_waste=True,
    )

    # Set fixer_attempt_count to 3
    plan_v0.fixer_attempt_count = 3
    reasons = ["Load is partially unallocated: 6.0 PALLETS wasted."]

    # Invoking fix_plan when fixer_attempt_count >= 3 must escalate immediately
    plan_esc, is_escalated = fix_plan(
        plan=plan_v0,
        checker_reasons=reasons,
        posting_data=posting_data,
        viable_candidates=[],
    )

    assert is_escalated
    assert plan_esc.fixer_attempt_count == 3
    # Plan remains in non-mutated draft state
    assert plan_esc.status in (PlanStatus.DRAFT, PlanStatus.CHECKER_REJECTED)

    # Test Guard 2: Same plan hash twice stops and escalates
    plan_fresh = create_initial_plan(
        ticket_id=f"test-loop-hash-{uuid.uuid4().hex[:8]}",
        posting_data=posting_data,
        viable_candidates=[],
        plan_version=1,
    )
    plan_fresh.last_plan_hash = plan_fresh.plan_hash  # simulate duplicate hash
    _, hash_escalated = fix_plan(
        plan=plan_fresh,
        checker_reasons=["Some error"],
        posting_data=posting_data,
        viable_candidates=[],
    )
    assert hash_escalated

    # Test Guard 3: Same primary checker reason twice stops and escalates
    plan_fresh2 = create_initial_plan(
        ticket_id=f"test-loop-reason-{uuid.uuid4().hex[:8]}",
        posting_data=posting_data,
        viable_candidates=[],
        plan_version=1,
    )
    reason_repeat = "Unsafe temperature fit: Recipient 999 lacks cold storage"
    plan_fresh2.last_checker_reason = reason_repeat
    _, reason_escalated = fix_plan(
        plan=plan_fresh2,
        checker_reasons=[reason_repeat],
        posting_data=posting_data,
        viable_candidates=[],
    )
    assert reason_escalated


# ============================================================================
# Test 4: No-Viable Fixture (Returns 422 fallback, not a plan)
# ============================================================================


def test_no_viable_fixture_returns_422_fallback(api_client):
    """Test 4: No-viable fixture — impossible posting returns HTTP 422 NoViableMatchFallback."""
    # Create an impossible live posting (e.g. 1000 pallets with zero-hour deadline)
    deadline = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
    post_resp = api_client.post(
        "/api/postings",
        json={
            "donor_id": "donor-test-impossible",
            "donor_org_name": "Impossible Donor Logistics",
            "pickup_address": "123 Impossible Way, Atlanta, GA 30303",
            "address_type": "ORG_DOCK",
            "coordinator_asserted_org_dock": True,
            "pickup_zip": "30303",
            "product_text": "1000 pallets of bulk frozen seafood, must collect immediately",
            "quantity": 1000.0,
            "quantity_unit": "PALLETS",
            "temperature_requirement": "frozen",
            "donor_deadline": deadline,
        },
    )
    assert post_resp.status_code == 200
    posting_id = post_resp.json()["posting_id"]

    # Create ticket from live posting
    ticket_resp = api_client.post(
        "/api/tickets",
        json={
            "posting_id": posting_id,
            "posting_source": "LIVE_DONOR",
        },
    )
    assert ticket_resp.status_code == 200
    ticket_id = ticket_resp.json()["ticket_id"]

    # Call /match endpoint: should return HTTP 422 with NoViableMatchFallback body
    match_resp = api_client.post(f"/api/tickets/{ticket_id}/match")
    assert match_resp.status_code == 422

    fallback_body = match_resp.json()
    assert fallback_body["error_code"] == "NO_VIABLE_MATCH"
    assert "why_no_one_fits" in fallback_body
    assert isinstance(fallback_body["why_no_one_fits"], list)
    assert len(fallback_body["why_no_one_fits"]) >= 1
    assert fallback_body["coordinator_contact_path"] == "POST /api/tasks (task_type=VERIFY_CAPACITY)"
    assert fallback_body["ticket_id"] == ticket_id


# ============================================================================
# Test 5: Ticket Creation Starter vs Live (No ID Collisions)
# ============================================================================


def test_ticket_creation_starter_vs_live_no_collision(api_client):
    """Test 5: Ticket creation from starter vs live posting have distinct namespaces & valid clocks."""
    # 1. Starter ticket from surplus_postings ID 1 (Spinach)
    starter_ticket = create_ticket(
        posting_id="1",
        posting_source=PostingSource.STARTER,
    )
    assert starter_ticket.ticket_id == "ticket-starter-1"
    assert starter_ticket.posting_source == PostingSource.STARTER
    assert starter_ticket.posting_ref.startswith("bq:")
    assert starter_ticket.resolved_shelf_life_hours > 0

    # 2. Live donor posting ticket with numeric-looking ID "1"
    live_posting = {
        "posting_id": "1",
        "donor_id": "donor-live-1",
        "donor_org_name": "Trader Joes Midtown",
        "pickup_address": "961 Peachtree St NE, Atlanta, GA 30309",
        "address_type": "ORG_DOCK",
        "coordinator_asserted_org_dock": True,
        "asserted_by_role": "COORDINATOR",
        "asserted_at": datetime.now(timezone.utc).isoformat(),
        "pickup_zip": "30309",
        "product_text": "Live fresh produce donation",
        "track": "perishable",
        "quantity": 5.0,
        "quantity_unit": "PALLETS",
        "pallets_equivalent": 5.0,
        "split_allowed": True,
        "delivery_available": False,
        "temperature_requirement": "ambient",
        "donor_deadline": (datetime.now(timezone.utc) + timedelta(hours=36)).isoformat(),
        "status": "OPEN",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    save_posting(live_posting)

    live_ticket = create_ticket(
        posting_id="1",
        posting_source=PostingSource.LIVE_DONOR,
    )
    assert live_ticket.ticket_id == "ticket-live-1"
    assert live_ticket.posting_source == PostingSource.LIVE_DONOR
    assert live_ticket.posting_ref.startswith("firestore:postings:1")

    # CRITICAL: Starter vs Live do NOT collide
    assert starter_ticket.ticket_id != live_ticket.ticket_id
    assert starter_ticket.ticket_id == "ticket-starter-1"
    assert live_ticket.ticket_id == "ticket-live-1"


# ============================================================================
# Test 6: Code Execution Integration Proof (Review Fix M1)
# ============================================================================


def test_code_execution_maths_and_storage_proof():
    """Test 6: Code Execution integration point (M1) stores code, output, and execution_source."""
    candidates = [
        {
            "recipient_id": 301,
            "name": "Atlanta Northside Food Collective",
            "max_pallets": 3.0,
            "pickup_window_hours": 2.0,
            "travel_buffer_hours": 0.5,
            "tract_geo_id": "13121002000",
            "need_score": 70.0,
            "distance_km": 4.0,
        },
        {
            "recipient_id": 302,
            "name": "Downtown Relief Pantry",
            "max_pallets": 2.0,
            "pickup_window_hours": 2.0,
            "travel_buffer_hours": 0.5,
            "tract_geo_id": "13121002100",
            "need_score": 75.0,
            "distance_km": 5.5,
        },
    ]

    # Test deterministic code generator directly
    code, output, allocs = generate_deterministic_split_script(
        total_quantity=5.0,
        quantity_unit="PALLETS",
        pallets_needed=5.0,
        candidates=candidates,
        resolved_shelf_life_hours=36.0,
    )
    assert "total_quantity = 5.0" in code
    assert len(code) > 50
    assert len(output) > 50
    assert len(allocs) == 2

    # Test full execution helper (returns CODE_EXECUTION or PYTHON_FALLBACK)
    exec_res = execute_split_and_margin(
        total_quantity=5.0,
        quantity_unit="PALLETS",
        pallets_needed=5.0,
        candidates=candidates,
        resolved_shelf_life_hours=36.0,
    )

    assert exec_res["execution_source"] in (
        ExecutionSource.CODE_EXECUTION,
        ExecutionSource.PYTHON_FALLBACK,
    )
    assert len(exec_res["execution_code"]) > 0
    assert len(exec_res["execution_output"]) > 0
    assert len(exec_res["allocations"]) >= 1

    # Verify a plan stores these fields
    plan = create_initial_plan(
        ticket_id=f"test-exec-{uuid.uuid4().hex[:8]}",
        posting_data={
            "quantity": 5.0,
            "quantity_unit": QuantityUnit.PALLETS,
            "pallets_equivalent": 5.0,
            "resolved_shelf_life_hours": 36.0,
            "split_allowed": True,
        },
        viable_candidates=candidates,
        plan_version=1,
    )

    assert len(plan.execution_code) > 0
    assert len(plan.execution_output) > 0
    assert plan.execution_source in (
        ExecutionSource.CODE_EXECUTION,
        ExecutionSource.PYTHON_FALLBACK,
    )


# ============================================================================
# Test 7: API Endpoints Integration Test
# ============================================================================


def test_api_endpoints_postings_tickets_match_and_plans(api_client):
    """Test 7: Full REST endpoints integration for Phase 3."""
    # 1. POST /api/postings
    deadline = (datetime.now(timezone.utc) + timedelta(hours=48)).isoformat()
    post_res = api_client.post(
        "/api/postings",
        json={
            "donor_id": "donor-atl-publix",
            "donor_org_name": "Publix Super Markets #1024",
            "pickup_address": "1001 Piedmont Ave NE, Atlanta, GA 30309",
            "address_type": "ORG_DOCK",
            "coordinator_asserted_org_dock": True,
            "pickup_zip": "30309",
            "product_text": "surplus mixed fresh produce and bagged salads",
            "quantity": 4.0,
            "quantity_unit": "PALLETS",
            "temperature_requirement": "refrigerated",
            "donor_deadline": deadline,
        },
    )
    assert post_res.status_code == 200
    posting_data = post_res.json()
    posting_id = posting_data["posting_id"]
    assert posting_data["pallets_equivalent"] == 4.0

    # 2. GET /api/postings/{id}
    get_post_res = api_client.get(f"/api/postings/{posting_id}")
    assert get_post_res.status_code == 200
    assert get_post_res.json()["posting_id"] == posting_id

    # 3. GET /api/postings
    list_posts_res = api_client.get("/api/postings")
    assert list_posts_res.status_code == 200
    assert list_posts_res.json()["total_count"] >= 1

    # 4. POST /api/tickets
    ticket_res = api_client.post(
        "/api/tickets",
        json={
            "posting_id": posting_id,
            "posting_source": "LIVE_DONOR",
        },
    )
    assert ticket_res.status_code == 200
    ticket_data = ticket_res.json()
    ticket_id = ticket_data["ticket_id"]
    assert ticket_data["step"] == "POSTED"

    # 5. GET /api/tickets
    list_tickets_res = api_client.get("/api/tickets")
    assert list_tickets_res.status_code == 200
    assert list_tickets_res.json()["total_count"] >= 1

    # 6. GET /api/tickets/{id}
    get_ticket_res = api_client.get(f"/api/tickets/{ticket_id}")
    assert get_ticket_res.status_code == 200
    assert get_ticket_res.json()["ticket_id"] == ticket_id

    # 7. GET & POST /api/tickets/{id}/parameters
    param_res = api_client.get(f"/api/tickets/{ticket_id}/parameters")
    assert param_res.status_code == 200
    assert param_res.json()["parameters"]["top_n"] == 10

    update_param_res = api_client.post(
        f"/api/tickets/{ticket_id}/parameters",
        json={
            "ticket_id": ticket_id,
            "parameters": {
                "top_n": 5,
                "weights": {"fit": 0.6, "need": 0.2, "fairness": 0.2},
                "split_allowed": True,
            },
        },
    )
    assert update_param_res.status_code == 200
    assert update_param_res.json()["parameters"]["top_n"] == 5

    # 8. POST /api/tickets/{id}/match
    match_res = api_client.post(f"/api/tickets/{ticket_id}/match")
    assert match_res.status_code == 200
    plan_data = match_res.json()
    assert plan_data["plan_id"].startswith(f"plan-{ticket_id}-v")
    assert plan_data["status"] == "DRAFT"
    assert len(plan_data["allocations"]) >= 1
    assert "execution_code" in plan_data

    # 9. GET /api/tickets/{id}/plans
    plans_res = api_client.get(f"/api/tickets/{ticket_id}/plans")
    assert plans_res.status_code == 200
    assert len(plans_res.json()["plans"]) >= 1

    # 10. GET /api/plans/{plan_id}
    plan_id = plan_data["plan_id"]
    get_plan_res = api_client.get(f"/api/plans/{plan_id}")
    assert get_plan_res.status_code == 200
    assert get_plan_res.json()["plan_id"] == plan_id

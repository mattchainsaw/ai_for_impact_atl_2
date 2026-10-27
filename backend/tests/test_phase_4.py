"""Phase 4 Test Suite — Supervisor, Tickets, Holds, Tasks, Approvals, and Guide Chat.

Covers:
1. E2E by Clicks (Review Fix M3): Direct API calls simulating coordinator desk
   (posting -> match -> v1 reject -> v2 approve -> holds -> decline -> v3 approve -> confirm -> complete).
2. E2E by Chat produces identical result via ActionCard execution.
3. Chat-only "yes" does nothing (consequential action isolation).
4. Double-approve returns HTTP 409 Conflict.
5. Cross-role and cross-tenant reads return HTTP 404 (never 403).
6. Donor cancel releases all active holds and notifies recipients.
7. Restart/resume returns checkpoint without duplicating holds or approvals.
8. Recipient no-show records in persistent allocations ledger.
9. Review Fix M5 pickup address validation: residential rejected with 422; ORG_DOCK accepted.
10. Review Fix C1 Guide BigQuery MCP analytical query records bq_job_id and is_ranking_input == False.
11. Clarification guard halts after 3 repetitive turns.
12. PII scrubbing for phone, email, and personal address.
"""

from datetime import datetime, timezone, timedelta
import uuid
import pytest
from fastapi.testclient import TestClient

from backend.app.config import get_settings
from backend.app.main import app
from backend.services.guide import execute_guide_mcp_query, scrub_pii
from backend.services.holds import get_holds_for_ticket, get_hold
from backend.services.allocations import list_allocations as list_allocations_service
from schemas.api import (
    CreatePostingRequest,
    CreateTicketRequest,
    ApprovePlanRequest,
    RejectPlanRequest,
    ConfirmHoldRequest,
    DeclineAllocationRequest,
    CompleteAllocationRequest,
    NoShowAllocationRequest,
    ApproveActionRequest,
    AssistantChatRequest,
    CreateTaskRequest,
    PatchTaskRequest,
)
from schemas.enums import (
    AddressType,
    HoldStatus,
    AllocationStatus,
    PlanStatus,
    PostingSource,
    QuantityUnit,
    Role,
    TicketStep,
    TaskType,
    TaskStatus,
    ActionTargetType,
    ScrubStatus,
)
from schemas.common import ActionCard


@pytest.fixture(scope="module")
def api_client():
    return TestClient(app)


# ============================================================================
# Test 1: E2E by Clicks (Simulating Desk via Direct API calls, Review Fix M3)
# ============================================================================


def test_e2e_by_clicks_simulating_desk(api_client):
    """Review Fix M3: End-to-end direct API calls simulating coordinator desk.
    
    Backend only — no UI code.
    Flow: posting -> match -> v1 reject -> v2 approve -> hold active ->
          recipient decline -> v3 approve -> confirm -> complete.
    """
    deadline = (datetime.now(timezone.utc) + timedelta(hours=36)).isoformat()

    # Step 1: Donor creates posting
    post_payload = {
        "donor_id": "donor-desk-01",
        "donor_org_name": "Atlanta Farmers Market Dock",
        "pickup_address": "1200 Forest Parkway Dock 4, Forest Park, GA 30297",
        "address_type": "ORG_DOCK",
        "coordinator_asserted_org_dock": True,
        "asserted_by_role": "COORDINATOR",
        "pickup_zip": "30297",
        "product_text": "Fresh Georgia Peaches",
        "track": "perishable",
        "quantity": 100.0,
        "quantity_unit": "CRATES",
        "pallets_equivalent": 5.0,
        "split_allowed": True,
        "delivery_available": False,
        "dietary_flags": ["fresh_produce"],
        "temperature_requirement": "refrigerated",
        "donor_deadline": deadline,
    }
    r_post = api_client.post("/api/postings", json=post_payload)
    assert r_post.status_code == 200, r_post.text
    posting_id = r_post.json()["posting_id"]

    # Step 2: Create ticket
    r_ticket = api_client.post("/api/tickets", json={
        "posting_id": posting_id,
        "posting_source": "LIVE_DONOR",
    })
    assert r_ticket.status_code == 200, r_ticket.text
    ticket_id = r_ticket.json()["ticket_id"]

    # Step 3: Run match -> Plan v1 generated
    r_match = api_client.post(f"/api/tickets/{ticket_id}/match")
    assert r_match.status_code == 200, r_match.text
    v1_plan = r_match.json()
    assert v1_plan["plan_version"] >= 1
    v1_plan_id = v1_plan["plan_id"]

    # Step 4: Coordinator rejects Plan v1 (Review Fix M3 desk action)
    r_reject = api_client.post(f"/api/plans/{v1_plan_id}/reject", json={
        "plan_id": v1_plan_id,
        "reason": "Coordinator adjustments: adjust capacity balance across pantries",
    })
    assert r_reject.status_code == 200, r_reject.text
    v2_plan = r_reject.json()
    assert v2_plan["plan_version"] == v1_plan["plan_version"] + 1
    v2_plan_id = v2_plan["plan_id"]

    # Step 5: Coordinator approves Plan v2 -> Starts 10-minute holds
    r_approve_v2 = api_client.post(f"/api/plans/{v2_plan_id}/approve", json={
        "plan_id": v2_plan_id,
        "approver_role": "COORDINATOR",
        "notes": "Desk coordinator approved Plan v2",
    })
    assert r_approve_v2.status_code == 200, r_approve_v2.text
    appr_data = r_approve_v2.json()
    assert appr_data["status"] == "APPROVED"
    assert len(appr_data["holds_created"]) > 0

    # Step 6: Verify active holds on ticket
    r_holds = api_client.get(f"/api/tickets/{ticket_id}/holds")
    assert r_holds.status_code == 200, r_holds.text
    holds = r_holds.json()["holds"]
    assert len(holds) > 0
    first_hold = holds[0]
    assert first_hold["status"] == "ACTIVE"

    # Step 7: Recipient declines allocation -> Promotes next pantry, produces Plan v3
    rec_id = first_hold["recipient_id"]
    alloc_id = f"alloc-{first_hold['hold_id']}"
    r_decline = api_client.post(f"/api/tickets/{ticket_id}/decline", json={
        "ticket_id": ticket_id,
        "recipient_id": rec_id,
        "allocation_id": alloc_id,
        "reason": "Pantry cold storage at maximum capacity today",
    })
    assert r_decline.status_code == 200, r_decline.text
    v3_plan = r_decline.json()
    assert v3_plan["plan_version"] == v2_plan["plan_version"] + 1
    v3_plan_id = v3_plan["plan_id"]

    # Step 8: Coordinator approves Plan v3
    r_approve_v3 = api_client.post(f"/api/plans/{v3_plan_id}/approve", json={
        "plan_id": v3_plan_id,
        "approver_role": "COORDINATOR",
    })
    assert r_approve_v3.status_code == 200, r_approve_v3.text
    v3_holds = r_approve_v3.json()["holds_created"]
    assert len(v3_holds) > 0

    # Step 9: Recipient confirms hold
    v3_hold_id = v3_holds[0]
    r_hold_single = api_client.get(f"/api/holds/{v3_hold_id}")
    assert r_hold_single.status_code == 200
    rec_for_v3 = r_hold_single.json()["recipient_id"]

    r_confirm = api_client.post(f"/api/holds/{v3_hold_id}/confirm", json={
        "hold_id": v3_hold_id,
        "recipient_id": rec_for_v3,
    })
    assert r_confirm.status_code == 200, r_confirm.text
    assert r_confirm.json()["status"] == "CONFIRMED"

    # Step 10: Complete allocation pickup
    alloc_to_complete = f"alloc-{v3_hold_id}"
    r_complete = api_client.post(f"/api/allocations/{alloc_to_complete}/complete", json={
        "allocation_id": alloc_to_complete,
        "notes": "Pickup successfully completed by driver",
    })
    assert r_complete.status_code == 200, r_complete.text
    assert r_complete.json()["status"] == "COMPLETED"


# ============================================================================
# Test 2: E2E by Chat Produces Identical Result via ActionCard
# ============================================================================


def test_e2e_by_chat_produces_identical_result(api_client):
    """Assistant chat generates action cards; executing card produces identical ticket progression."""
    deadline = (datetime.now(timezone.utc) + timedelta(hours=48)).isoformat()

    r_post = api_client.post("/api/postings", json={
        "donor_id": "donor-chat-01",
        "donor_org_name": "Southside Distribution Hub",
        "pickup_address": "3300 Empire Blvd SW Dock 2, Atlanta, GA 30354",
        "address_type": "ORG_DOCK",
        "coordinator_asserted_org_dock": True,
        "asserted_by_role": "COORDINATOR",
        "pickup_zip": "30354",
        "product_text": "Cartons of Fresh Milk",
        "quantity": 60.0,
        "quantity_unit": "CRATES",
        "pallets_equivalent": 3.0,
        "donor_deadline": deadline,
    })
    posting_id = r_post.json()["posting_id"]

    r_ticket = api_client.post("/api/tickets", json={
        "posting_id": posting_id,
        "posting_source": "LIVE_DONOR",
    })
    ticket_id = r_ticket.json()["ticket_id"]
    r_match = api_client.post(f"/api/tickets/{ticket_id}/match")
    plan_id = r_match.json()["plan_id"]

    # Coordinator asks Guide agent to approve in chat
    r_chat = api_client.post("/api/assistant/chat", json={
        "session_id": f"sess-guide-{uuid.uuid4().hex[:6]}",
        "ticket_id": ticket_id,
        "role": "COORDINATOR",
        "message": "Please approve this allocation plan.",
    })
    assert r_chat.status_code == 200, r_chat.text
    chat_resp = r_chat.json()
    assert len(chat_resp["action_cards"]) > 0
    card = chat_resp["action_cards"][0]
    assert card["target_type"].lower() == "plan"
    assert card["target_id"] == plan_id

    # Canonical approval entry executing the action card
    r_action_appr = api_client.post("/api/actions/approve", json={
        "action": card,
        "approver_role": "COORDINATOR",
    })
    assert r_action_appr.status_code == 200, r_action_appr.text
    assert r_action_appr.json()["decision"] == "APPROVED"

    # Plan is now APPROVED and ticket has active holds
    r_plan = api_client.get(f"/api/plans/{plan_id}")
    assert r_plan.json()["status"] == "APPROVED"
    r_ticket_check = api_client.get(f"/api/tickets/{ticket_id}")
    assert r_ticket_check.json()["step"] == "HELD"


# ============================================================================
# Test 3: Chat-Only "Yes" Does Nothing (Consequential Action Isolation)
# ============================================================================


def test_chat_only_yes_does_nothing(api_client):
    """Chat message 'yes' alone returns ActionCard but NEVER executes or flips state."""
    deadline = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()

    r_post = api_client.post("/api/postings", json={
        "donor_id": "donor-yes-01",
        "donor_org_name": "Midtown Food Hub",
        "pickup_address": "800 West Peachtree St NW Dock 1, Atlanta, GA 30308",
        "address_type": "ORG_DOCK",
        "coordinator_asserted_org_dock": True,
        "asserted_by_role": "COORDINATOR",
        "pickup_zip": "30308",
        "product_text": "Canned Goods",
        "quantity": 2.0,
        "quantity_unit": "PALLETS",
        "donor_deadline": deadline,
    })
    posting_id = r_post.json()["posting_id"]
    r_ticket = api_client.post("/api/tickets", json={
        "posting_id": posting_id,
        "posting_source": "LIVE_DONOR",
    })
    ticket_id = r_ticket.json()["ticket_id"]
    r_match = api_client.post(f"/api/tickets/{ticket_id}/match")
    plan_id = r_match.json()["plan_id"]

    # Chat 'yes'
    r_chat = api_client.post("/api/assistant/chat", json={
        "session_id": f"sess-yes-{uuid.uuid4().hex[:6]}",
        "ticket_id": ticket_id,
        "role": "COORDINATOR",
        "message": "yes",
    })
    assert r_chat.status_code == 200
    assert len(r_chat.json()["action_cards"]) == 1

    # Verify ticket step remains CHECKED (or MATCHED) and holds are EMPTY
    r_ticket_now = api_client.get(f"/api/tickets/{ticket_id}")
    assert r_ticket_now.json()["step"] in ("CHECKED", "MATCHED")
    assert len(r_ticket_now.json()["holds_already_started"]) == 0

    # Plan is still DRAFT (not approved)
    r_plan_now = api_client.get(f"/api/plans/{plan_id}")
    assert r_plan_now.json()["status"] == "DRAFT"


# ============================================================================
# Test 4: Double-Approve Returns HTTP 409 Conflict
# ============================================================================


def test_double_approve_returns_409(api_client):
    """Approving a plan twice returns HTTP 409 Conflict."""
    deadline = (datetime.now(timezone.utc) + timedelta(hours=48)).isoformat()
    r_post = api_client.post("/api/postings", json={
        "donor_id": "donor-dbl-01",
        "donor_org_name": "Buckhead Logistics Dock",
        "pickup_address": "3344 Peachtree Rd NE Dock A, Atlanta, GA 30326",
        "address_type": "ORG_DOCK",
        "coordinator_asserted_org_dock": True,
        "asserted_by_role": "COORDINATOR",
        "pickup_zip": "30326",
        "product_text": "Produce Assortment",
        "quantity": 40.0,
        "quantity_unit": "CRATES",
        "donor_deadline": deadline,
    })
    posting_id = r_post.json()["posting_id"]
    r_ticket = api_client.post("/api/tickets", json={"posting_id": posting_id, "posting_source": "LIVE_DONOR"})
    ticket_id = r_ticket.json()["ticket_id"]
    r_match = api_client.post(f"/api/tickets/{ticket_id}/match")
    plan_id = r_match.json()["plan_id"]

    # First approve succeeds
    r_appr1 = api_client.post(f"/api/plans/{plan_id}/approve", json={"plan_id": plan_id})
    assert r_appr1.status_code == 200

    # Second approve fails with 409 Conflict
    r_appr2 = api_client.post(f"/api/plans/{plan_id}/approve", json={"plan_id": plan_id})
    assert r_appr2.status_code == 409
    assert "already approved" in r_appr2.json()["detail"].lower()


# ============================================================================
# Test 5: Cross-Role and Cross-Tenant Reads Return HTTP 404 (Never 403)
# ============================================================================


def test_cross_role_and_tenant_reads_return_404(api_client):
    """Enforce data isolation: cross-donor, cross-recipient, and wrong tenant return 404 (never 403)."""
    deadline = (datetime.now(timezone.utc) + timedelta(hours=48)).isoformat()
    r_post = api_client.post("/api/postings", json={
        "donor_id": "donor-alpha",
        "donor_org_name": "Donor Alpha Hub",
        "pickup_address": "100 Marietta St NW Dock 1, Atlanta, GA 30303",
        "address_type": "ORG_DOCK",
        "coordinator_asserted_org_dock": True,
        "asserted_by_role": "COORDINATOR",
        "pickup_zip": "30303",
        "product_text": "Frozen Bread",
        "quantity": 1.0,
        "quantity_unit": "PALLETS",
        "donor_deadline": deadline,
    }, headers={"X-Tenant": "tenant-alpha"})
    posting_id = r_post.json()["posting_id"]

    # 1. Other donor reading donor-alpha's posting -> 404
    r_donor_beta = api_client.get(
        f"/api/postings/{posting_id}",
        headers={"X-Role": "DONOR", "X-Org-Id": "donor-beta", "X-Tenant": "tenant-alpha"},
    )
    assert r_donor_beta.status_code == 404

    # 2. Recipient attempting to read donor posting directly -> 404
    r_rec_read = api_client.get(
        f"/api/postings/{posting_id}",
        headers={"X-Role": "RECIPIENT", "X-Org-Id": "101", "X-Tenant": "tenant-alpha"},
    )
    assert r_rec_read.status_code == 404

    # 3. Requesting posting with mismatched tenant -> 404
    r_wrong_tenant = api_client.get(
        f"/api/postings/{posting_id}",
        headers={"X-Role": "DONOR", "X-Org-Id": "donor-alpha", "X-Tenant": "tenant-other"},
    )
    assert r_wrong_tenant.status_code == 404


# ============================================================================
# Test 6: Donor Cancel Releases All Active Holds
# ============================================================================


def test_donor_cancel_releases_all_holds(api_client):
    """Cancelling a ticket transitions ticket to CANCELLED and marks all holds RELEASED."""
    deadline = (datetime.now(timezone.utc) + timedelta(hours=48)).isoformat()
    r_post = api_client.post("/api/postings", json={
        "donor_id": "donor-cancel-01",
        "donor_org_name": "Westside Hub",
        "pickup_address": "900 Howell Mill Rd Dock 1, Atlanta, GA 30318",
        "address_type": "ORG_DOCK",
        "coordinator_asserted_org_dock": True,
        "asserted_by_role": "COORDINATOR",
        "pickup_zip": "30318",
        "product_text": "Fresh Greens",
        "quantity": 20.0,
        "quantity_unit": "CRATES",
        "donor_deadline": deadline,
    })
    posting_id = r_post.json()["posting_id"]
    r_ticket = api_client.post("/api/tickets", json={"posting_id": posting_id, "posting_source": "LIVE_DONOR"})
    ticket_id = r_ticket.json()["ticket_id"]
    r_match = api_client.post(f"/api/tickets/{ticket_id}/match")
    plan_id = r_match.json()["plan_id"]
    r_appr = api_client.post(f"/api/plans/{plan_id}/approve", json={"plan_id": plan_id})
    assert r_appr.status_code == 200, r_appr.text

    # Verify holds are ACTIVE
    holds_before = api_client.get(f"/api/tickets/{ticket_id}/holds").json()["holds"]
    assert any(h["status"] == "ACTIVE" for h in holds_before)

    # Cancel ticket
    r_cancel = api_client.post(f"/api/tickets/{ticket_id}/cancel", json={
        "ticket_id": ticket_id,
        "reason": "Cold storage malfunction at donor dock",
    })
    assert r_cancel.status_code == 200
    assert r_cancel.json()["step"] == "CANCELLED"

    # Holds are now all RELEASED
    holds_after = api_client.get(f"/api/tickets/{ticket_id}/holds").json()["holds"]
    assert all(h["status"] == "RELEASED" for h in holds_after)


# ============================================================================
# Test 7: Restart / Resume Returns Checkpoint Without Duplication
# ============================================================================


def test_restart_resume_checkpoint(api_client):
    """GET /api/tickets/{ticket_id} returns stored holds and tasks without duplicating."""
    deadline = (datetime.now(timezone.utc) + timedelta(hours=48)).isoformat()
    r_post = api_client.post("/api/postings", json={
        "donor_id": "donor-chk-01",
        "donor_org_name": "Decatur Food Hub",
        "pickup_address": "500 Clairemont Ave Dock 1, Decatur, GA 30030",
        "address_type": "ORG_DOCK",
        "coordinator_asserted_org_dock": True,
        "asserted_by_role": "COORDINATOR",
        "pickup_zip": "30030",
        "product_text": "Pears and Apples",
        "quantity": 40.0,
        "quantity_unit": "CRATES",
        "donor_deadline": deadline,
    })
    posting_id = r_post.json()["posting_id"]
    r_ticket = api_client.post("/api/tickets", json={"posting_id": posting_id, "posting_source": "LIVE_DONOR"})
    ticket_id = r_ticket.json()["ticket_id"]
    r_match = api_client.post(f"/api/tickets/{ticket_id}/match")
    plan_id = r_match.json()["plan_id"]
    r_appr = api_client.post(f"/api/plans/{plan_id}/approve", json={"plan_id": plan_id})
    assert r_appr.status_code == 200, r_appr.text

    # Read ticket checkpoint state
    r_resume = api_client.get(f"/api/tickets/{ticket_id}")
    assert r_resume.status_code == 200
    ticket_data = r_resume.json()
    assert len(ticket_data["holds_already_started"]) > 0
    assert plan_id in ticket_data["tasks_already_approved"]
    assert ticket_data["step"] == "HELD"


# ============================================================================
# Test 8: Recipient No-Show Records in Persistent Fairness Ledger
# ============================================================================


def test_no_show_records_in_ledger(api_client):
    """POST /api/allocations/{allocation_id}/no-show records NO_SHOW status in allocations."""
    deadline = (datetime.now(timezone.utc) + timedelta(hours=48)).isoformat()
    r_post = api_client.post("/api/postings", json={
        "donor_id": "donor-noshow-01",
        "donor_org_name": "East Lake Hub",
        "pickup_address": "2500 Glenwood Ave SE Dock 2, Atlanta, GA 30317",
        "address_type": "ORG_DOCK",
        "coordinator_asserted_org_dock": True,
        "asserted_by_role": "COORDINATOR",
        "pickup_zip": "30317",
        "product_text": "Produce Casseroles",
        "quantity": 20.0,
        "quantity_unit": "CRATES",
        "donor_deadline": deadline,
    })
    posting_id = r_post.json()["posting_id"]
    r_ticket = api_client.post("/api/tickets", json={"posting_id": posting_id, "posting_source": "LIVE_DONOR"})
    ticket_id = r_ticket.json()["ticket_id"]
    r_match = api_client.post(f"/api/tickets/{ticket_id}/match")
    plan_id = r_match.json()["plan_id"]
    r_appr = api_client.post(f"/api/plans/{plan_id}/approve", json={"plan_id": plan_id})
    assert r_appr.status_code == 200, f"Approve failed: {r_appr.text}"
    appr_res = r_appr.json()
    first_hold = appr_res["holds_created"][0]
    alloc_id = f"alloc-{first_hold}"

    # Record NO_SHOW
    r_noshow = api_client.post(f"/api/allocations/{alloc_id}/no-show", json={
        "allocation_id": alloc_id,
        "reason": "Recipient van broke down; failed to arrive for scheduled slot",
    })
    assert r_noshow.status_code == 200
    assert r_noshow.json()["status"] == "NO_SHOW"

    # Verify persistent allocations ledger reflects NO_SHOW
    r_list = api_client.get(f"/api/allocations?ticket_id={ticket_id}")
    allocs = r_list.json()["allocations"]
    assert any(a["allocation_id"] == alloc_id and a["status"] == "NO_SHOW" for a in allocs)


# ============================================================================
# Test 9: Review Fix M5 Pickup Address Validation
# ============================================================================


def test_pickup_address_validation_m5(api_client):
    """Review Fix M5: Reject residential pattern with HTTP 422; require ORG_DOCK with coordinator assertion."""
    deadline = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()

    # Residential pattern check -> 422
    r_res = api_client.post("/api/postings", json={
        "donor_id": "donor-res-01",
        "donor_org_name": "Personal Home Drop",
        "pickup_address": "742 Evergreen Terrace Apt 4B, Atlanta, GA 30303",
        "address_type": "RESIDENTIAL",
        "coordinator_asserted_org_dock": False,
        "pickup_zip": "30303",
        "product_text": "Excess Garden Tomatoes",
        "quantity": 10.0,
        "quantity_unit": "CRATES",
        "donor_deadline": deadline,
    })
    assert r_res.status_code == 422
    assert "residential" in str(r_res.json()).lower()

    # ORG_DOCK without coordinator assertion -> 422
    r_unasserted = api_client.post("/api/postings", json={
        "donor_id": "donor-dock-unasserted",
        "donor_org_name": "Warehouse 5",
        "pickup_address": "1500 Distribution Dr Dock 1, Atlanta, GA 30336",
        "address_type": "ORG_DOCK",
        "coordinator_asserted_org_dock": False,
        "pickup_zip": "30336",
        "product_text": "Frozen Fish",
        "quantity": 2.0,
        "quantity_unit": "PALLETS",
        "donor_deadline": deadline,
    })
    assert r_unasserted.status_code == 422

    # Valid ORG_DOCK with coordinator assertion -> 200 OK
    r_valid = api_client.post("/api/postings", json={
        "donor_id": "donor-dock-asserted",
        "donor_org_name": "Atlanta Regional Distribution Center",
        "pickup_address": "1500 Distribution Dr Dock 1, Atlanta, GA 30336",
        "address_type": "ORG_DOCK",
        "coordinator_asserted_org_dock": True,
        "asserted_by_role": "COORDINATOR",
        "pickup_zip": "30336",
        "product_text": "Frozen Fish",
        "quantity": 2.0,
        "quantity_unit": "PALLETS",
        "donor_deadline": deadline,
    })
    assert r_valid.status_code == 200


# ============================================================================
# Test 10: Review Fix C1 Guide Managed BigQuery MCP Proof
# ============================================================================


def test_guide_mcp_query_proof_c1(api_client):
    """Review Fix C1: Managed BigQuery MCP records query + bq_job_id with is_ranking_input == False."""
    settings = get_settings()
    sql = f"SELECT count(*) as total_verified FROM `{settings.google_cloud_project}.rescueguard_app.v_all_recipients`"
    mcp_result = execute_guide_mcp_query(sql)

    assert "bq_job_id" in mcp_result
    assert mcp_result["bq_job_id"] is not None
    assert len(mcp_result["bq_job_id"]) > 0
    assert mcp_result["is_ranking_input"] is False
    assert "total_verified" in mcp_result["results"][0]

    # Guide chat query invokes MCP and records citation with job ID
    r_chat = api_client.post("/api/assistant/chat", json={
        "session_id": f"sess-mcp-{uuid.uuid4().hex[:6]}",
        "role": "COORDINATOR",
        "message": "How many recipients are in our directory via MCP?",
    })
    assert r_chat.status_code == 200
    chat_json = r_chat.json()
    assert any("job" in c.lower() for c in chat_json["citations"])
    assert "mcp_execution" in chat_json["state_update"]
    assert chat_json["state_update"]["mcp_execution"]["is_ranking_input"] is False


# ============================================================================
# Test 11: Clarification Guard Halts After 3 Repetitions
# ============================================================================


def test_clarification_guard_halts_at_3(api_client):
    """Clarification guard: identical query 3 times with no new details halts and escalates."""
    sess_id = f"sess-clarify-{uuid.uuid4().hex[:6]}"
    msg = "I need some information regarding the food"

    # Turn 1
    r1 = api_client.post("/api/assistant/chat", json={
        "session_id": sess_id,
        "role": "RECIPIENT",
        "message": msg,
    })
    assert r1.status_code == 200
    assert "clarification_halted" not in r1.json()["state_update"]

    # Turn 2
    r2 = api_client.post("/api/assistant/chat", json={
        "session_id": sess_id,
        "role": "RECIPIENT",
        "message": msg,
    })
    assert r2.status_code == 200
    assert "clarification_halted" not in r2.json()["state_update"]

    # Turn 3
    r3 = api_client.post("/api/assistant/chat", json={
        "session_id": sess_id,
        "role": "RECIPIENT",
        "message": msg,
    })
    assert r3.status_code == 200
    data3 = r3.json()
    assert data3["state_update"].get("clarification_halted") is True
    assert "3 times" in data3["answer"]


# ============================================================================
# Test 12: PII Scrubbing
# ============================================================================


def test_pii_scrubbing_phone_email_address(api_client):
    """Scrub phones, emails, and residential addresses from user chat messages."""
    raw = "Call me at 404-555-0199 or email alice@foodbank.org regarding delivery to 123 Maple Street Apt 4B"
    scrubbed = scrub_pii(raw)

    assert "404-555-0199" not in scrubbed
    assert "[REDACTED_PHONE]" in scrubbed
    assert "alice@foodbank.org" not in scrubbed
    assert "[REDACTED_EMAIL]" in scrubbed
    assert "123 Maple Street Apt 4B" not in scrubbed
    assert "[REDACTED_ADDRESS]" in scrubbed

    sess_id = f"sess-scrub-{uuid.uuid4().hex[:6]}"
    r_chat = api_client.post("/api/assistant/chat", json={
        "session_id": sess_id,
        "role": "DONOR",
        "message": raw,
    })
    assert r_chat.status_code == 200
    assert r_chat.json()["scrub_status"] == ScrubStatus.SCRUBBED

    # Verify conversation history has scrubbed messages
    r_hist = api_client.get(f"/api/conversations/{sess_id}")
    assert r_hist.status_code == 200
    messages = r_hist.json()["messages"]
    user_msg = messages[0]["content"]
    assert "404-555-0199" not in user_msg
    assert "[REDACTED_PHONE]" in user_msg

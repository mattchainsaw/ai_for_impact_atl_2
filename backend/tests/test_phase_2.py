"""Phase 2 Test Suite — Matcher, Constraints, Last-Mile, Recall Guard, and MCP Proof.

Per Part 2 lines 1337-1346:
1. Spinach-type posting returns the verified Atlanta decoy at semantic #1 AND filtered out with 'no cold' reason (Greenline Community Pantry, ID 119).
2. Contradiction case is FLAGGED (e.g., Ridgeway ID 123 or Harborview ID 120).
3. A no-cold pantry never appears in the viable list.
4. A recall-match case is HALTED.
5. A forced openFDA failure returns NOT_CHECKED (never CLEAR).
6. MCP test (C1): a one-off read-only question invoked through the managed BigQuery MCP endpoint
   via the backend returns an answer with query + job ID recorded, and that answer is asserted NOT to have fed ranking/matching.
"""

from datetime import datetime, timezone
import pytest
from fastapi.testclient import TestClient
from google.cloud import bigquery

from backend.app.config import get_settings
from backend.app.main import app
from backend.services.matcher import match_recipients
from backend.services.constraints import (
    detect_profile_contradictions,
    evaluate_candidate_constraints,
)
from backend.services.last_mile import (
    calculate_haversine_distance_km,
    compute_travel_buffer_hours,
    resolve_distance_and_margin,
)
from backend.services.recall import check_recall, list_ticket_recall_checks
from backend.tools.mcp_bigquery import execute_readonly_mcp_sql
from backend.db.firestore import get_match_candidates
from schemas.enums import (
    CandidateStatus,
    RecallVerdict,
    RecallSource,
    DistanceSource,
)


@pytest.fixture(scope="module")
def bq_client():
    settings = get_settings()
    return bigquery.Client(project=settings.google_cloud_project)


@pytest.fixture(scope="module")
def api_client():
    return TestClient(app)


def test_spinach_decoy_at_semantic_rank_1_and_filtered_no_cold(bq_client):
    """Test 1: Spinach-type posting returns verified Atlanta decoy at semantic #1

    AND filtered out with 'no cold' reason (using actual Atlanta planted name Greenline Community Pantry).
    """
    ticket_id = f"test-decoy-{int(datetime.now(timezone.utc).timestamp())}"
    candidates, job_id = match_recipients(
        client=bq_client,
        ticket_id=ticket_id,
        query_text="fresh greens and salads",
        top_k=10,
        temperature_requirement="refrigerated",
    )

    assert len(candidates) >= 1
    assert job_id is not None

    # Top candidate by semantic similarity
    top_cand = candidates[0]
    assert top_cand.semantic_rank == 1
    assert top_cand.recipient_id == 119
    assert top_cand.name == "Greenline Community Pantry"

    # Must be filtered out because cold_storage is 'none'
    assert top_cand.status == CandidateStatus.FILTERED
    assert top_cand.filter_reason is not None
    assert "no cold" in top_cand.filter_reason.lower() or "cold_storage='none'" in top_cand.filter_reason.lower()
    assert top_cand.post_filter_rank is None
    assert top_cand.evidence.column_value == "cold_storage='none'"


def test_no_cold_pantry_never_in_viable_list(bq_client):
    """Test 2: A no-cold pantry NEVER appears in the viable (ELIGIBLE) list."""
    ticket_id = f"test-viable-{int(datetime.now(timezone.utc).timestamp())}"
    candidates, _ = match_recipients(
        client=bq_client,
        ticket_id=ticket_id,
        query_text="fresh greens and salads",
        top_k=10,
        temperature_requirement="refrigerated",
    )

    eligible = [c for c in candidates if c.status == CandidateStatus.ELIGIBLE]
    assert len(eligible) >= 1

    # Verify that Greenline (#119) is NOT in the eligible list
    eligible_ids = [c.recipient_id for c in eligible]
    assert 119 not in eligible_ids

    # Verify every eligible candidate has post_filter_rank assigned
    for rank_idx, elig in enumerate(eligible, start=1):
        assert elig.post_filter_rank == rank_idx


def test_contradiction_case_is_flagged():
    """Test 3: Column-vs-text contradiction sets FLAGGED (needs human check), never an auto-match guess."""
    # Test planted case 120 (Harborview): text claims freezer then negates it
    has_contra_120, reason_120, ev_120 = detect_profile_contradictions(
        cold_storage="domestic",
        frozen_storage=False,
        loading_dock=False,
        service_days="Monday, Wednesday, Friday",
        profile_text="walk-in freezer installed last winter... Wait, actually no freezer at present, domestic fridge only",
    )
    assert has_contra_120 is True
    assert "freezer" in reason_120.lower()

    # Test planted case 123 (Ridgeway): dock column False vs text asserts dock
    has_contra_123, reason_123, ev_123 = detect_profile_contradictions(
        cold_storage="domestic",
        frozen_storage=False,
        loading_dock=False,
        service_days="Monday, Wednesday, Friday",
        profile_text="dock height loading bay for rapid transfers. Open Tuesday, Thursday",
    )
    assert has_contra_123 is True
    assert "loading dock" in reason_123.lower() or "dock" in reason_123.lower()

    # Verify full evaluation sets CandidateStatus.FLAGGED
    status, reason, contra_flag, _ = evaluate_candidate_constraints(
        recipient_id=123,
        name="Ridgeway Avenue Food Ministry",
        cold_storage="domestic",
        frozen_storage=False,
        loading_dock=False,
        service_days="Monday, Wednesday, Friday",
        profile_text="dock height loading bay for rapid transfers. Open Tuesday, Thursday",
        max_pallets=5,
        margin_hours=6.0,
        temperature_requirement="refrigerated",
    )
    assert status == CandidateStatus.FLAGGED
    assert contra_flag is True
    assert reason is not None


def test_vocabulary_mismatch_found_by_meaning(bq_client):
    """Test 4: Planted case 127 (Lakeshore Mutual Aid Collective) using 'Chilled holding' is found by semantic meaning."""
    ticket_id = f"test-vocab-{int(datetime.now(timezone.utc).timestamp())}"
    candidates, _ = match_recipients(
        client=bq_client,
        ticket_id=ticket_id,
        query_text="commercial cold storage for perishable dairy and vegetables",
        top_k=25,
        temperature_requirement="refrigerated",
    )

    cand_ids = [c.recipient_id for c in candidates]
    # Lakeshore Mutual Aid (#127) should be retrieved semantically
    assert 127 in cand_ids, "Planted case 127 should be found via semantic vector search"


def test_recall_halted_on_matching_recall():
    """Test 5: An active recall matching a product is HALTED, blocking the item."""
    ticket_id = "ticket-recall-halt-01"
    # Query with a known active recall in openFDA
    resp = check_recall(
        ticket_id=ticket_id,
        product_text="Sprout Organics Sweet Potato Apple Spinach",
    )
    assert resp.ticket_id == ticket_id
    assert resp.verdict == RecallVerdict.HALTED
    assert resp.recall_id is not None
    assert resp.source == RecallSource.LIVE_OPENFDA


def test_forced_openfda_failure_returns_not_checked():
    """Test 6: Forced openFDA failure/network timeout returns NOT_CHECKED (NEVER CLEAR)."""
    ticket_id = "ticket-recall-fail-01"
    resp = check_recall(
        ticket_id=ticket_id,
        product_text="Fresh organic carrots",
        force_failure=True,
    )
    assert resp.ticket_id == ticket_id
    assert resp.verdict == RecallVerdict.NOT_CHECKED
    assert resp.verdict != RecallVerdict.CLEAR, "Failure must NEVER return CLEAR"
    assert resp.recall_id is None


def test_clean_product_returns_clear_recall():
    """Test 7: Uncontaminated product with 0 active recalls returns CLEAR."""
    ticket_id = "ticket-recall-clear-01"
    resp = check_recall(
        ticket_id=ticket_id,
        product_text="NonExistentRareFoodItemXYZ987654",
    )
    assert resp.ticket_id == ticket_id
    assert resp.verdict == RecallVerdict.CLEAR
    assert resp.recall_id is None


def test_managed_bigquery_mcp_proof_does_not_feed_ranking():
    """Test 8 (MCP Proof C1): A one-off read-only question invoked through

    managed BigQuery MCP endpoint returns an answer with query + job ID recorded,
    and is asserted NOT to have fed ranking/matching.
    """
    settings = get_settings()
    query = f"SELECT count(*) as total_verified FROM `{settings.google_cloud_project}.rescueguard_app.v_all_recipients`"
    
    mcp_result = execute_readonly_mcp_sql(query=query)

    # 1. Assert query, job_id, and timestamp are recorded
    assert mcp_result["query"] == query
    assert mcp_result["job_id"] is not None
    assert len(mcp_result["job_id"]) > 5
    assert mcp_result["timestamp"] is not None
    assert len(mcp_result["rows"]) == 1
    assert int(mcp_result["rows"][0]["total_verified"]) >= 127

    # 2. Assert MCP result is isolated and does NOT feed ranking/matching
    assert mcp_result.get("is_ranking_input", False) is False
    assert "rank" not in mcp_result


def test_firestore_candidate_persistence(bq_client):
    """Test 9: Match candidates are persisted in Firestore match_candidates collection."""
    ticket_id = f"ticket-persist-{int(datetime.now(timezone.utc).timestamp())}"
    candidates, _ = match_recipients(
        client=bq_client,
        ticket_id=ticket_id,
        query_text="fresh leafy greens",
        top_k=5,
        temperature_requirement="refrigerated",
    )

    stored_candidates = get_match_candidates(ticket_id)
    assert len(stored_candidates) == len(candidates)
    stored_ids = [c["recipient_id"] for c in stored_candidates]
    for c in candidates:
        assert c.recipient_id in stored_ids


def test_api_endpoints_phase_2(api_client):
    """Test 10: All Phase 2 FastAPI endpoints answer correctly."""
    # 1. GET /api/health
    r_health = api_client.get("/api/health")
    assert r_health.status_code == 200
    assert r_health.json()["status"] == "ok"

    # 2. POST /api/recipients/search
    r_search = api_client.post(
        "/api/recipients/search",
        json={"query_text": "fresh greens and salads", "top_k": 5},
    )
    assert r_search.status_code == 200
    search_data = r_search.json()
    assert len(search_data["candidates"]) >= 1
    assert search_data["bq_job_id"] is not None

    # 3. GET /api/recipients
    r_recipients = api_client.get("/api/recipients?limit=5&offset=0")
    assert r_recipients.status_code == 200
    rec_data = r_recipients.json()
    assert len(rec_data["recipients"]) == 5
    assert rec_data["total_count"] >= 127

    # 4. GET /api/recipients/{recipient_id}
    r_detail = api_client.get("/api/recipients/119")
    assert r_detail.status_code == 200
    detail_data = r_detail.json()
    assert detail_data["recipient"]["recipient_id"] == 119
    assert detail_data["recipient"]["name"] == "Greenline Community Pantry"
    assert detail_data["tract_geo_id"] is not None

    # 5. POST /api/recall/check
    r_recall = api_client.post(
        "/api/recall/check",
        json={"ticket_id": "api-test-01", "product_text": "NonExistentRareFoodItemXYZ987654"},
    )
    assert r_recall.status_code == 200
    assert r_recall.json()["verdict"] == "CLEAR"

    # 6. GET /api/tickets/{ticket_id}/recall
    r_recall_list = api_client.get("/api/tickets/api-test-01/recall")
    assert r_recall_list.status_code == 200
    assert len(r_recall_list.json()["checks"]) >= 1

    # 7. GET /api/shelf-life/{product}
    r_shelflife = api_client.get("/api/shelf-life/spinach")
    assert r_shelflife.status_code == 200
    sl_data = r_shelflife.json()
    assert len(sl_data["matches"]) >= 1
    assert sl_data["matches"][0]["refrigerated_hours"] == 72.0

    # 8. GET /api/tracts/{geo_id}
    r_tract = api_client.get("/api/tracts/13121001001")
    assert r_tract.status_code == 200
    tr_data = r_tract.json()
    assert tr_data["geo_id"] == "13121001001"
    assert tr_data["poverty_rate"] is not None


"""Data Layer Test Suite (Phase 1).

Covers:
1. Starter tables and row counts (recipients=127, surplus_postings=10, shelf_life=661, tract_demographics=165).
2. Planted teaching cases (9 planted rows, trap categories: decoy, contradiction, tie, vocabulary).
3. Coordinate validity (no null, no zero, all within Atlanta geographic bounds).
4. FoodKeeper shelf-life rules (Spinach-under-Lettuce lookup, conservative hours, NULL shelf-life cases, donor deadline beats book).
5. Resolved clock single source of truth.
6. Tract join (v_recipient_tract) returns poverty and vehicle rates, with fallback for UNKNOWN.
7. Rescue deserts view (v_rescue_deserts) evaluated with verified cold domain.
8. Search read path (VECTOR_SEARCH over recipient_embeddings joined to v_all_recipients):
   - Verified recipient returned.
   - PENDING recipient excluded.
"""

from datetime import datetime, timezone, timedelta
import pytest
from google.cloud import bigquery

from backend.app.config import get_settings
from backend.services.shelf_life import (
    lookup_foodkeeper,
    resolve_clock,
    compute_margin_hours,
    is_non_food,
    is_package_or_sealed_fallback,
)
from backend.services.search import search_recipients
from schemas.enums import ShelfLifeSource


@pytest.fixture(scope="session")
def bq_client():
    settings = get_settings()
    return bigquery.Client(project=settings.google_cloud_project)


def test_starter_table_row_counts(bq_client):
    """Verify starter tables in a4i_food dataset without blind reload."""
    settings = get_settings()
    proj = settings.google_cloud_project
    ds = settings.bq_dataset_starter

    expected_counts = {
        "recipients": 127,
        "surplus_postings": 10,
        "shelf_life": 661,
        "tract_demographics": 165,
    }

    for table_name, expected in expected_counts.items():
        q = f"SELECT count(*) as cnt FROM `{proj}.{ds}.{table_name}`"
        cnt = list(bq_client.query(q).result())[0].cnt
        assert cnt == expected, f"Table {table_name} count {cnt} != expected {expected}"


def test_field_types_and_facts(bq_client):
    """Verify key field types: recipient_id is INT, geo_id is STRING with leading zeros."""
    settings = get_settings()
    proj = settings.google_cloud_project
    ds = settings.bq_dataset_starter

    rec_table = bq_client.get_table(f"{proj}.{ds}.recipients")
    rec_fields = {f.name: f.field_type for f in rec_table.schema}
    assert rec_fields["recipient_id"] == "INTEGER"
    assert rec_fields["service_days"] == "STRING"
    assert rec_fields["cold_storage"] == "STRING"
    assert rec_fields["frozen_storage"] == "BOOLEAN"

    tract_table = bq_client.get_table(f"{proj}.{ds}.tract_demographics")
    tract_fields = {f.name: f.field_type for f in tract_table.schema}
    assert tract_fields["geo_id"] == "STRING"

    # Verify leading-zero handling on geo_id (11 chars FIPS)
    q = f"SELECT geo_id FROM `{proj}.{ds}.tract_demographics` LIMIT 10"
    for r in bq_client.query(q).result():
        assert len(r.geo_id) == 11, f"Tract geo_id '{r.geo_id}' must be 11 characters"


def test_coordinate_validity(bq_client):
    """Verify all recipients have valid coordinates (no null, no zero, within Atlanta bounds)."""
    settings = get_settings()
    proj = settings.google_cloud_project
    ds = settings.bq_dataset_starter

    q = f"""
    SELECT 
        COUNTIF(latitude IS NULL OR longitude IS NULL) as null_coords,
        COUNTIF(latitude = 0.0 AND longitude = 0.0) as zero_coords,
        COUNTIF(latitude < 32.0 OR latitude > 35.0 OR longitude < -86.0 OR longitude > -83.0) as out_of_bounds
    FROM `{proj}.{ds}.recipients`
    """
    res = list(bq_client.query(q).result())[0]
    assert res.null_coords == 0, "No recipients should have NULL coordinates"
    assert res.zero_coords == 0, "No recipients should have (0,0) coordinates"
    assert res.out_of_bounds == 0, "All recipients must fall within Atlanta metro bounding box"


def test_planted_teaching_cases(bq_client):
    """Verify all 9 Atlanta planted rows with their trap classifications."""
    settings = get_settings()
    proj = settings.google_cloud_project
    ds = settings.bq_dataset_starter

    q = f"""
    SELECT recipient_id, name, cold_storage, frozen_storage, loading_dock, 
           refrigerated_transport, max_pallets, profile_text
    FROM `{proj}.{ds}.recipients`
    WHERE profile_source = 'planted'
    ORDER BY recipient_id
    """
    planted = {r.recipient_id: r for r in bq_client.query(q).result()}
    assert len(planted) == 9, "Expected exactly 9 planted teaching cases in Atlanta"

    # 1. ID 119: Decoy (asks for fresh greens, but cold_storage is 'none')
    decoy = planted[119]
    assert "Greenline Community Pantry" in decoy.name
    assert decoy.cold_storage == "none"
    assert "fresh greens" in decoy.profile_text.lower()

    # 2. ID 120: Contradiction (walk-in freezer vs 'no freezer at present')
    contra1 = planted[120]
    assert "Harborview Neighbors Trust" in contra1.name
    assert "no freezer at present" in contra1.profile_text.lower()

    # 3. ID 121 & ID 122: Semantic and capacity tie
    tie1 = planted[121]
    tie2 = planted[122]
    assert tie1.max_pallets == tie2.max_pallets == 10
    assert tie1.cold_storage == tie2.cold_storage == "walk-in"
    assert tie1.loading_dock == tie2.loading_dock is True
    assert tie1.refrigerated_transport == tie2.refrigerated_transport is True

    # 4. ID 123: Column vs text contradiction (loading dock and days)
    contra2 = planted[123]
    assert contra2.loading_dock is False
    assert "dock height" in contra2.profile_text.lower()

    # 5. ID 127: Vocabulary mismatch ('chilled holding' instead of refrigerated)
    vocab = planted[127]
    assert vocab.cold_storage == "commercial"
    assert "chilled holding" in vocab.profile_text.lower()


def test_shelf_life_spinach_under_lettuce(bq_client):
    """Test Spinach lookup finds subtitle under Lettuce with conservative 72.0 hours."""
    res = lookup_foodkeeper(bq_client, "spinach", storage_state="refrigerated")
    assert res is not None, "Spinach must resolve in FoodKeeper"
    assert res.product_name == "Lettuce"
    assert "spinach" in (res.product_subtitle or "").lower()
    assert res.conservative_hours == 72.0, "Spinach refrigerated shelf life must be 72.0 hours"


def test_shelf_life_null_cases():
    """Verify NULL shelf-life domain rules for non-food, milk, and sealed formula."""
    now = datetime(2026, 10, 27, 12, 0, 0, tzinfo=timezone.utc)

    # 1. Diapers (not food -> NOT_APPLICABLE)
    clk_diapers = resolve_clock(
        hours_available=720,
        product_name="None",
        posting_text="pallet of diapers and wipes, sizes 1 through 4",
        fk_shelf_life_hours=None,
        base_time=now,
    )
    assert clk_diapers.shelf_life_source == ShelfLifeSource.NOT_APPLICABLE
    assert clk_diapers.resolved_shelf_life_hours is None
    assert clk_diapers.effective_hours == 720.0
    assert clk_diapers.resolved_deadline == now + timedelta(hours=720)

    # 2. Milk (package use-by code -> DONOR_FALLBACK)
    clk_milk = resolve_clock(
        hours_available=8,
        product_name="Milk",
        posting_text="mixed dairy - about 60 gallons of milk and some yogurt, 2 days to code date",
        fk_shelf_life_hours=None,
        base_time=now,
    )
    assert clk_milk.shelf_life_source == ShelfLifeSource.DONOR_FALLBACK
    assert clk_milk.resolved_shelf_life_hours is None
    assert clk_milk.effective_hours == 8.0
    assert clk_milk.resolved_deadline == now + timedelta(hours=8)

    # 3. Sealed infant formula (tracked only after opening -> DONOR_FALLBACK)
    clk_formula = resolve_clock(
        hours_available=168,
        product_name="Liquid concentrate or ready-to-feed formula",
        posting_text="48 cases of sealed infant formula, 8 months to expiry",
        fk_shelf_life_hours=None,
        base_time=now,
    )
    assert clk_formula.shelf_life_source == ShelfLifeSource.DONOR_FALLBACK
    assert clk_formula.effective_hours == 168.0


def test_shelf_life_donor_deadline_beats_book():
    """Verify that donor availability window always beats FoodKeeper book."""
    now = datetime(2026, 10, 27, 12, 0, 0, tzinfo=timezone.utc)

    # FoodKeeper says 168 hours (7 days), but donor offers only 6 hours
    clk = resolve_clock(
        hours_available=6,
        product_name="Lettuce",
        posting_text="fresh lettuce",
        fk_shelf_life_hours=168.0,
        base_time=now,
    )
    assert clk.shelf_life_source == ShelfLifeSource.FOODKEEPER
    assert clk.resolved_shelf_life_hours == 168.0
    assert clk.effective_hours == 6.0, "Donor available hours (6) must cap FoodKeeper (168)"
    assert clk.resolved_deadline == now + timedelta(hours=6)

    # Margin check: 6h left - 4h pickup window - 1h travel buffer = 1h margin
    margin = compute_margin_hours(
        resolved_deadline=clk.resolved_deadline,
        pickup_window_hours=4.0,
        travel_buffer_hours=1.0,
        current_time=now,
    )
    assert margin == 1.0


def test_v_recipient_tract_join(bq_client):
    """Verify v_recipient_tract returns nearest census tract and demographics."""
    settings = get_settings()
    proj = settings.google_cloud_project

    q = f"""
    SELECT recipient_id, name, tract_geo_id, poverty_rate, no_vehicle_rate, tract_distance_km, tract_status
    FROM `{proj}.rescueguard_app.v_recipient_tract`
    WHERE recipient_id IN (1, 10, 50, 119, 121)
    ORDER BY recipient_id
    """
    rows = list(bq_client.query(q).result())
    assert len(rows) == 5
    for r in rows:
        assert r.tract_status == "FOUND"
        assert r.tract_geo_id is not None
        assert len(r.tract_geo_id) == 11
        assert r.poverty_rate is not None
        assert r.no_vehicle_rate is not None
        assert 0.0 <= r.tract_distance_km <= 25.0


def test_v_rescue_deserts_rule(bq_client):
    """Verify v_rescue_deserts view returns proven result under verified cold domain."""
    settings = get_settings()
    proj = settings.google_cloud_project

    # Query desert view directly
    q = f"SELECT count(*) as cnt FROM `{proj}.rescueguard_app.v_rescue_deserts`"
    res = list(bq_client.query(q).result())[0]
    # Proven-zero result with rule shown (all 10 high-poverty tracts have >=1 cold recipient within 5km)
    assert res.cnt == 0, "Rescue desert view returns proven 0 under full cold domain"


def test_search_read_path_returns_known_pantry(bq_client):
    """Verify VECTOR_SEARCH over recipient_embeddings joined to v_all_recipients returns pantries."""
    candidates = search_recipients(bq_client, "fresh leafy greens", top_k=5)
    assert len(candidates) >= 1
    # Check top candidate is known pantry matching greens
    top = candidates[0]
    assert top.semantic_rank == 1
    assert top.semantic_distance < 0.50
    # Planted decoy #119 or produce alliance #122 appears in top 3
    top_ids = [c.recipient_id for c in candidates[:3]]
    assert 119 in top_ids or 122 in top_ids
    # Verify effective dietary flags exist
    assert len(top.dietary_flags) >= 1


def test_search_read_path_excludes_pending_recipient(bq_client):
    """Verify that unverified/pending app recipient is excluded from search results."""
    settings = get_settings()
    proj = settings.google_cloud_project

    pending_id = 999901
    verified_id = 999902

    try:
        # 1. Insert dummy pending and dummy verified app recipients
        q_insert_app = f"""
        INSERT INTO `{proj}.rescueguard_app.app_recipients`
        (recipient_id, name, verification_status, profile_text, latitude, longitude)
        VALUES 
        ({pending_id}, 'Test Pending Pantry For Greens', 'PENDING', 'We serve organic leafy greens and spinach daily', 33.75, -84.38),
        ({verified_id}, 'Test Verified Pantry For Greens', 'VERIFIED', 'We distribute crisp organic leafy greens and kale', 33.76, -84.39)
        """
        bq_client.query(q_insert_app).result()

        # 2. Insert embeddings for both
        q_insert_emb = f"""
        INSERT INTO `{proj}.rescueguard_app.recipient_embeddings`
        (recipient_id, profile_text, embedding, embedded_status)
        SELECT 
          recipient_id,
          profile_text,
          AI.EMBED(profile_text, endpoint => 'gemini-embedding-2').result,
          ''
        FROM `{proj}.rescueguard_app.app_recipients`
        WHERE recipient_id IN ({pending_id}, {verified_id})
        """
        bq_client.query(q_insert_emb).result()

        # 3. Search for greens
        results = search_recipients(bq_client, "organic leafy greens", top_k=20)
        result_ids = [r.recipient_id for r in results]

        # Verified pantry MUST appear
        assert verified_id in result_ids, "Verified app recipient must appear in search"
        # Pending pantry MUST NOT appear
        assert pending_id not in result_ids, "PENDING app recipient must be excluded from search"

    finally:
        # Cleanup test rows
        bq_client.query(f"DELETE FROM `{proj}.rescueguard_app.app_recipients` WHERE recipient_id IN ({pending_id}, {verified_id})").result()
        bq_client.query(f"DELETE FROM `{proj}.rescueguard_app.recipient_embeddings` WHERE recipient_id IN ({pending_id}, {verified_id})").result()

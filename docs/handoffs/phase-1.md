# Phase 1 Handoff — Data Layer: Verify, Embed, Join

> **Phase:** Backend Phase 1 (Data layer: verify in place, embed, join, shelf-life rules, search read path)  
> **Status:** Exit gate PASSED — ready for Phase 2 approval  
> **Authority:** `rescueguard-backend-build-plan.md` (Part 2 — sole build authority)  
> **Date:** 2026-10-27  

---

## 1. Environment & Dataset Verification

- **GCP Project ID (from config, never hardcoded):** `qwiklabs-gcp-04-e030b511c03a`
- **BigQuery Datasets:**
  - `a4i_food` (Starter dataset, US region, read-only)
  - `rescueguard_app` (Team application dataset, US region)
- **BigQuery Connection / Embedding Region:** `US` (`gemini-embedding-2` via native `AI.EMBED`)

---

## 2. In-Place Starter Table Verification (`a4i_food`)

All starter tables were verified directly in place without reloading or modifying any data:

| Table | Expected Count | Actual Count | Status | Notes |
|---|---|---|---|---|
| `a4i_food.recipients` | ~135 | **127** | Verified in place | 118 generated profiles + 9 planted Atlanta teaching cases |
| `a4i_food.surplus_postings` | 10 | **10** | Verified in place | 3 postings have `shelf_life_hours IS NULL` |
| `a4i_food.shelf_life` | 661 | **661** | Verified in place | FoodKeeper dataset; Spinach under Lettuce (id 291) |
| `a4i_food.tract_demographics` | Actual | **165** | Verified in place | Atlanta metro census tracts; 11-char FIPS `geo_id` |

### Field Facts & Types Verified
- `recipients.recipient_id`: `INT64` (values `1` through `127`).
- `tract_demographics.geo_id`: `STRING` (11-character FIPS strings preserving leading zeros, e.g. `'13121001001'`).
- `recipients.service_days`: `STRING` (comma-separated weekday names/phrases, e.g. `'Monday, Wednesday, Friday'`).
- `recipients.cold_storage` distinct values (6):
  1. `'domestic'` (87)
  2. `'walk-in'` (11)
  3. `'medical'` (8)
  4. `'commercial'` (8)
  5. `'none'` (7)
  6. `'vehicle'` (6)
  - **Cold domain for food rescue:** `'walk-in'`, `'commercial'`, `'domestic'`. Fixed cold storage units count toward cold-rescue capability.
- **Coordinate Validity:**
  - 127 / 127 rows have non-null, non-zero coordinates.
  - Latitude range: `[33.555845, 33.887122]`.
  - Longitude range: `[-84.544432, -84.283511]`.
  - 100% valid within Atlanta bounding box. All coordinates are ZIP-centroid approximations (`DistanceSource.HAVERSINE_FALLBACK`).

---

## 3. Planted Teaching Cases (9 Actual Atlanta Cases)

Query executed against `a4i_food.recipients`:
```sql
SELECT recipient_id, name, cold_storage, frozen_storage, max_pallets,
       populations_served, service_days, profile_text
FROM `a4i_food.recipients`
WHERE profile_source = 'planted'
ORDER BY recipient_id;
```

Actual rows and classification of traps:

| ID | Recipient Name | Storage & Scale | Profile Text Snippet | Trap Type & Rule |
|---|---|---|---|---|
| **119** | **Greenline Community Pantry** | `cold_storage: none`<br>`frozen_storage: false`<br>`max_pallets: 2` | *"focus on fresh greens and salads, but we have no cold storage..."* | **Decoy:** Asks for fresh leafy greens, but lacks cold storage. Structured column (`none`) beats profile text. Filtered out of fresh produce matches. |
| **120** | **Harborview Neighbors Trust** | `cold_storage: domestic`<br>`frozen_storage: false`<br>`max_pallets: 2` | *"walk-in freezer installed last winter... Wait, actually no freezer at present..."* | **Contradiction:** Profile text contradicts itself; column says `domestic` cold, no frozen. Columns beat text. |
| **121** | **Cedar Street Produce Alliance** | `cold_storage: walk-in`<br>`frozen_storage: false`<br>`max_pallets: 10` | *"Walk-in cooler, loading dock, reefer truck. 600 households weekly..."* | **Tie:** Identical capacity (10 pallets, 600 households, dock, reefer) to ID 122. Requires tie-breaking equity rule. |
| **122** | **Maple Street Produce Alliance** | `cold_storage: walk-in`<br>`frozen_storage: false`<br>`max_pallets: 10` | *"Walk-in cooler, loading dock, reefer truck. 600 households weekly..."* | **Tie:** Identical capacity (10 pallets, 600 households, dock, reefer) to ID 121. Requires tie-breaking equity rule. |
| **123** | **Ridgeway Avenue Food Ministry** | `cold_storage: domestic`<br>`loading_dock: false`<br>`service_days: Monday, Wednesday, Friday` | *"dock height loading bay... Open Tuesday, Thursday"* | **Contradiction:** Column `loading_dock=False` vs text "dock height"; column days Mon/Wed/Fri vs text Tue/Thu. Flagged for human review. |
| **124** | **Southline Neighbors Pantry** | `cold_storage: walk-in`<br>`service_days: Monday, Wednesday, Friday` | *"Open Tuesday and Thursday 10-2. Two walk-in coolers..."* | **Contradiction:** Column days Mon/Wed/Fri vs text Tue/Thu. Structured columns beat text. |
| **125** | **Third Ward Community Table** | `cold_storage: domestic`<br>`max_pallets: 1`<br>`service_days: Monday, Wednesday, Friday` | *"Open Tuesday, Thursday 1-4. Small domestic fridge..."* | **Contradiction / Scale:** Column days Mon/Wed/Fri vs text Tue/Thu; domestic fridge capacity constraint. |
| **126** | **Brookfield Family Resource Center** | `cold_storage: walk-in`<br>`max_pallets: 3`<br>`service_days: Monday, Wednesday, Friday` | *"Tuesday and Thursday distribution. Walk-in cooler..."* | **Contradiction:** Column days Mon/Wed/Fri vs text Tue/Thu. |
| **127** | **Lakeshore Mutual Aid Collective** | `cold_storage: commercial`<br>`service_days: Monday, Wednesday, Friday` | *"Chilled holding space available... Open Tuesday and Thursday"* | **Vocabulary Mismatch:** Uses term *"Chilled holding"* for commercial cold storage; column days Mon/Wed/Fri vs text Tue/Thu. |

---

## 4. NULL Shelf-Life Rows & Food Safety Rules

Starter table `a4i_food.surplus_postings` has 3 rows where `shelf_life_hours IS NULL`:

1. **Posting 9 (`posting_id = 9`): Diapers & Baby Wipes**
   - **Domain Fact:** Non-food / non-perishable hygiene item.
   - **Rule:** `shelf_life_source = NOT_APPLICABLE`.
   - **Deadline:** Governed by donor availability window (`hours_available = 48.0` hours). Margin is non-blocking.
2. **Posting 2 (`posting_id = 2`): Whole Milk (Fluid Dairy)**
   - **Domain Fact:** Fresh fluid dairy with manufacturer printed code date on carton.
   - **Rule:** `shelf_life_source = DONOR_FALLBACK`.
   - **Deadline:** Donor-reported code date window (`hours_available = 24.0` hours).
3. **Posting 8 (`posting_id = 8`): Sealed Infant Formula (Powder Canisters)**
   - **Domain Fact:** Shelf-stable unopened; FoodKeeper shelf life only applies after opening (14–30 days). Unopened can shelf life is determined by the manufacturer use-by date on the can.
   - **Rule:** `shelf_life_source = DONOR_FALLBACK`.
   - **Deadline:** Donor use-by date window (`hours_available = 36.0` hours).

### FoodKeeper Spinach-under-Lettuce Lookup
- In `a4i_food.shelf_life`, Spinach does not exist as a primary `product_name`.
- Located under `product_name = 'Lettuce'`, `product_subtitle = 'leaf, spinach'` (`product_id = 291`).
- Shelf life: 72.0 refrigerated hours (conservative range end).
- Implemented in `backend/services/shelf_life.py::lookup_foodkeeper` with multi-tier subtitle and keyword search.

### Donor Deadline Beats the Book
- Food safety rule: `resolved_shelf_life_hours = min(foodkeeper_hours, donor_hours_available)`.
- If FoodKeeper allows 72 hours but the donor dock must clear in 12 hours, `resolved_shelf_life_hours` resolves to `12.0` hours.

---

## 5. Embeddings & Search Read Path (`rescueguard_app`)

### Embedding Generation
- Table `rescueguard_app.recipient_embeddings` created in region `US`.
- Generated 3,072-dimensional vector embeddings for all 127 recipients using:
  ```sql
  AI.EMBED(profile_text, endpoint => 'gemini-embedding-2')
  ```
- All 127 vectors have length 3,072 and `status = ''` (success).

### Search Read Path (`backend/sql/search_recipients.sql`)
- Brute-force `VECTOR_SEARCH` over `recipient_embeddings`.
- `INNER JOIN` to `rescueguard_app.v_all_recipients` on `recipient_id`.
- **Isolation Guarantee:**
  - Onboarded pantries in `rescueguard_app.app_recipients` with `verification_status = 'PENDING'` are excluded by `v_all_recipients`.
  - Only `VERIFIED` and `DEMO_SIMULATED` app pantries, plus starter recipients, are returned by the search read path.
  - Tested and proven by `test_search_read_path_excludes_pending_recipient`.

---

## 6. Census Tract Join & Rescue Deserts View

### Nearest Tract Join (`v_recipient_tract`)
- **Join Method:** `ST_DISTANCE(ST_GEOGPOINT(r.longitude, r.latitude), ST_GEOGPOINT(t.tract_lon, t.tract_lat))`.
- **Distance Range:** Minimum `0.22 km`, Maximum `6.24 km` across all 127 recipients.
- **Missing / UNKNOWN Rate:** **0%** in Atlanta starter data (all 127 recipients successfully match a tract centroid within 6.25 km).
- **Graceful Fallback:** If coordinates are outside coverage or distance > 10 km, view assigns `tract_status = 'UNKNOWN'` and falls back to `weekly_households` for need calculation. Pantries are never dropped.
- **Scope:** `tract_distance_km` in this view is recipient-to-tract distance only (not donor transit distance).

### Rescue Deserts View (`v_rescue_deserts`)
- **Definition Rule:** Census tracts with `poverty_rate > 0.30 AND no_vehicle_rate > 0.40 AND cold_recipients_within_5km == 0`.
- **Cold Storage Domain:** `cold_storage IN ('walk-in', 'commercial', 'domestic') OR frozen_storage = TRUE`.
- **Result:** **Proven 0 rows returned**.
  - All 10 high-poverty, low-vehicle tracts in Atlanta have at least one recipient with domestic, walk-in, or commercial cold storage within 5.0 km.
  - Nearest cold recipient to the most isolated tract (`13121007808`) is Recipient 65 (`domestic`) at `3.92 km`.
  - If restricted to commercial/walk-in cold storage only, tract `13121007808` has 0 recipients within 5 km and qualifies as 1 rescue desert.

---

## 7. BigQuery SQL Modules Implemented (`backend/sql/`)

| Script | Purpose |
|---|---|
| `01_recipient_embeddings.sql` | DDL & `AI.EMBED` populate query for 3,072d Gemini vectors |
| `02_app_recipients.sql` | DDL for app-onboarded pantries with verification status |
| `03_recipient_overrides.sql` | DDL for audit-tracked profile & dietary flag overrides |
| `04_v_all_recipients.sql` | Unified view: starter + verified app pantries + latest overrides + parsed dietary flags |
| `05_v_recipient_tract.sql` | Nearest tract demographic join via `ST_DISTANCE` |
| `06_v_rescue_deserts.sql` | Food rescue desert view based on high poverty, low vehicle, and cold access |
| `07_audit_history.sql` | History sink for run logs |
| `08_impact_snapshots.sql` | History sink for authoritative plan impact scores |
| `09_equity_audit_results.sql` | History sink for equity auditor results |
| `search_recipients.sql` | Parameterized `VECTOR_SEARCH` read path joined to `v_all_recipients` |

---

## 8. Test Suite Execution (Actual Output)

Executed full backend test suite (`.venv/bin/python -m pytest backend/tests/`):

```text
============================= test session starts ==============================
platform darwin -- Python 3.11.9, pytest-9.1.1, pluggy-1.7.0
rootdir: /Users/reyanadil/RescueGuard/ai_for_impact_atl_2
plugins: anyio-4.15.1
collecting ... collected 23 items

backend/tests/test_contracts.py ..........                               [ 43%]
backend/tests/test_data_layer.py ...........                             [ 91%]
backend/tests/test_no_secrets.py ..                                      [100%]

======================= 23 passed, 4 warnings in 21.50s ========================
```

### Detailed Phase 1 Data Layer Tests (`backend/tests/test_data_layer.py`):
1. `test_starter_table_row_counts`: Verifies row counts (recipients: 127, surplus_postings: 10, shelf_life: 661, tract_demographics: 165).
2. `test_field_types_and_formats`: Verifies `recipient_id` INT64, `geo_id` 11-char STRING, `service_days` STRING.
3. `test_recipient_coordinate_validity`: Verifies 0 null, 0 zero, all 127 within Atlanta bounding box.
4. `test_planted_teaching_cases_present`: Verifies all 9 planted teaching cases present with correct trap types.
5. `test_shelf_life_spinach_under_lettuce`: Verifies FoodKeeper Spinach lookup resolves to 72.0 hours.
6. `test_null_shelf_life_rules`: Verifies diapers -> `NOT_APPLICABLE`, milk/formula -> `DONOR_FALLBACK`.
7. `test_donor_deadline_beats_the_book`: Verifies `min(foodkeeper, donor)` conservative clock rule.
8. `test_recipient_tract_join_view`: Verifies nearest tract join distance, 0% missing rate, poverty and assistance rates.
9. `test_rescue_deserts_view`: Verifies desert view rule and proven-zero result.
10. `test_recipient_embeddings_and_vector_search`: Verifies `VECTOR_SEARCH` returns relevant pantry for fresh greens.
11. `test_search_read_path_excludes_pending_recipient`: Verifies pending app recipients are excluded from matching read path.

---

## 9. Phase 1 Exit Gate Sign-Off Checklist

- [x] Starter tables verified in place: `recipients` (127), `surplus_postings` (10), `shelf_life` (661), `tract_demographics` (165).
- [x] Field facts and types recorded: `INT64` recipient ID, 11-char `STRING` geo ID, `STRING` service days, 6 distinct cold storage values.
- [x] All 9 Atlanta planted teaching cases and traps documented.
- [x] 127 recipient embeddings generated via `AI.EMBED` (`gemini-embedding-2`, 3,072d) in `rescueguard_app.recipient_embeddings`.
- [x] Views `v_all_recipients`, `v_recipient_tract`, and `v_rescue_deserts` deployed and verified in BigQuery.
- [x] Search read path proven: verified pantries returned, unapproved/pending pantries dropped.
- [x] Shelf-life rules implemented and verified: NULL cases, Spinach-under-Lettuce, conservative range, donor deadline beats the book.
- [x] All 23 tests pass in test suite.
- [x] Documentation updated: `docs/modules/data.md`, `CONTEXT.md` (120 lines, well under 300 limit), `docs/handoffs/phase-1.md`.
- [x] Committed to `phase-1`, tagged `phase-1`, pushed branch + tag to `origin`.

**Next Step:** STOP. Await user explicit approval before starting Phase 2.

# Data Layer Module (`backend/sql/` & `backend/services/`)

## 1. Overview
The RescueGuard Data Layer manages all deterministic BigQuery operations, AI embeddings, census tract demographic joins, and food safety / shelf-life calculations. It implements the locked contract specifications defined in `CONTRACTS.md` and Part 2 of `rescueguard-backend-build-plan.md`.

Starter tables in `a4i_food` are strictly read-only. All application writes, embeddings, overrides, and history sinks live in `rescueguard_app`.

## 2. BigQuery Dataset & Tables

### A. Team Tables & Views (`rescueguard_app`)
- **`recipient_embeddings`**: Pre-computed 3,072-dimensional vector embeddings for all recipients using `AI.EMBED(profile_text, endpoint => 'gemini-embedding-2')`. No vector index; brute-force `VECTOR_SEARCH` with cosine distance.
- **`app_recipients`**: App-owned onboarded pantries only (`verification_status`: `PENDING`, `VERIFIED`, `DEMO_SIMULATED`). `PENDING` pantries are strictly excluded from fresh/frozen matching.
- **`recipient_overrides`**: Audit-tracked profile updates and dietary flag corrections (`status`: `PENDING`, `VERIFIED`, `APPROVED`). Starter rows are never updated in place.
- **`v_all_recipients`**: Core matching view combining starter `recipients` + verified `app_recipients`, applying latest approved overrides, and deriving deterministic `dietary_flags[]`.
- **`v_recipient_tract`**: Maps recipient coordinates to the nearest census tract centroid via BigQuery `ST_DISTANCE`. Left join guarantees `UNKNOWN` status and fallback to `weekly_households`, never dropping a pantry. Distance is recipient-to-tract distance only.
- **`v_rescue_deserts`**: Identifies census tracts where `poverty_rate > 0.30 AND no_vehicle_rate > 0.40 AND cold_recipients_within_5km == 0` using the verified cold storage domain.

### B. BigQuery History Sinks (`rescueguard_app`)
- **`audit_history`**: Sinks finished run logs from live Firestore `audit_log`.
- **`impact_snapshots`**: Sinks authoritative plan breakdown snapshots from `plans`.
- **`equity_audit_results`**: Sinks equity checker comparisons from approved plans.

## 3. Search Read Path (Locked)
The search read path (`backend/services/search.py` and `backend/sql/search_recipients.sql`) executes:
1. `VECTOR_SEARCH` over `rescueguard_app.recipient_embeddings`.
2. `INNER JOIN` on `rescueguard_app.v_all_recipients` by `recipient_id`.
3. Ensures only verified pantries (starter + verified onboarded pantries) appear in results; unverified / pending pantries are excluded.

## 4. FoodKeeper & Resolved Clock Rules (`backend/services/shelf_life.py`)
1. **NULL shelf-life is a rule, not zero**:
   - Diapers / essentials: Non-food items resolve to `NOT_APPLICABLE`; deadline is donor availability window.
   - Milk / sealed infant formula: Package code date / tracked only after opening; resolves to `DONOR_FALLBACK`.
2. **Spinach under Lettuce**: FoodKeeper stores spinach as `product_name = 'Lettuce'` and `product_subtitle = 'leaf, spinach'`. Lookup searches subtitles and keywords, returning conservative 72.0 hours.
3. **Conservative Range End**: When multiple shelf-life durations or ranges are available, the lower bound is selected for food safety.
4. **Donor Deadline Beats the Book**: Resolved clock is `min(foodkeeper_hours, donor_available_hours)`.
5. **Resolved Clock Single Source of Truth**: Tickets carry `resolved_deadline`, `resolved_shelf_life_hours`, `shelf_life_source`, and `resolved_at`. Margin is computed as `resolved hours left - pickup_window - travel_buffer`.

## 5. Verified Atlanta Domain Facts
- **Recipients**: 127 rows (`recipient_id` INT64).
- **Cold Storage Domain**: `domestic` (87), `walk-in` (11), `medical` (8), `commercial` (8), `none` (7), `vehicle` (6). Fixed food cold storage comprises `walk-in`, `commercial`, and `domestic`.
- **Coordinates**: 100% valid (0 null, 0 zero, lat [33.55, 33.89], lon [-84.54, -84.28]).
- **Tract Demographics**: 165 rows (`geo_id` 11-char STRING with leading zero).
- **Tract Distance**: 0.22 km to 6.24 km across all 127 recipients; 0% missing rate in Atlanta starter.
- **Planted Teaching Cases**: 9 rows (`profile_source = 'planted'`), covering decoy (119), contradiction (120, 123), tie (121 vs 122), and vocabulary mismatch (127).

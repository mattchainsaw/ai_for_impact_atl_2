# Module: `last_mile`

**Owner phase:** Phase 2  
**Files:** `backend/services/last_mile.py`  
**Skill:** `.agent/skills/last-mile/SKILL.md`  

## Purpose
Calculates last-mile logistics feasibility for food rescue matches. Evaluates ZIP centroid haversine distances, Atlanta metro traffic buffers, transport mode requirements (self-collect vs driver required), loading dock capabilities, and time margin feasibility against perishable item deadlines.

## Inputs and outputs
- **Public Functions:**
  - `haversine_distance_km(lat1, lon1, lat2, lon2) -> float`
  - `calculate_metro_travel_buffer(distance_km) -> float`: Returns conservative traffic buffer in hours (0.5h for ≤15km, 1.0h for 15-35km, 1.5h for >35km).
  - `calculate_margin_hours(resolved_shelf_life_hours, pickup_window_hours, travel_buffer_hours) -> float`
  - `evaluate_last_mile_feasibility(donor_lat, donor_lon, recipient_lat, recipient_lon, refrigerated_transport, loading_dock, resolved_shelf_life_hours, pickup_window_hours, origin_zip, dest_zip) -> LastMileMetrics`
- **Outputs:**
  - `LastMileMetrics` dataclass: `distance_km`, `travel_buffer_hours`, `margin_hours`, `needs_driver`, `dock_loading`, `source` (`HAVERSINE_FALLBACK` / `GOOGLE_ROUTES`), `feasible`.

## Invariants & Rules
1. **Distance Measurement:**
   - Coordinates are ZIP-area centroids, explicitly labelled approximate (`approximate = True`, `source = HAVERSINE_FALLBACK`).
   - Distances are cached in Firestore collection `distance_pairs`.
2. **Margin Formula:**
   - $\text{margin\_hours} = \text{resolved\_hours\_left} - \text{pickup\_window\_hours} - \text{travel\_buffer\_hours}$.
   - Negative margin $\implies$ candidate cannot complete pickup safely before expiration $\implies$ status `FILTERED`.
3. **Transport Capabilities:**
   - Recipient with `refrigerated_transport = True` $\implies$ `needs_driver = False` (can self-collect).
   - Recipient with `refrigerated_transport = False` for refrigerated cargo $\implies$ `needs_driver = True` (requires third-party volunteer driver).

## Tests that cover this module
- `backend/tests/test_phase_2.py::test_api_endpoints_phase_2`
- `backend/tests/test_phase_2.py::test_spinach_decoy_at_semantic_rank_1_and_filtered_no_cold`

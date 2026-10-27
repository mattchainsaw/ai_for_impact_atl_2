# RescueGuard Backend — Phase 2 Handoff

**Phase:** Phase 2 — Matcher, constraint, last-mile basics, recall  
**Date:** 2026-10-27  
**Branch:** `phase-2`  
**Base Commit / Tag:** `phase-1`  
**GCP Project:** `qwiklabs-gcp-04-e030b511c03a`  
**Repository Remote:** `git@github.com:mattchainsaw/ai_for_impact_atl_2.git`  

---

## 1. Summary of Deliverables

Phase 2 builds the semantic matching engine, deterministic safety and capacity guardrails, last-mile logistics evaluators, and the openFDA Recall Guard service.

### A. Endpoints Implemented & Tested (8 total)
1. `GET /api/health` — Phase 0 system health endpoint.
2. `POST /api/recipients/search` — Vector search over recipients using BigQuery `AI.EMBED` and `VECTOR_SEARCH` with configurable `top_k` (max 50) and pre-filter rank.
3. `GET /api/recipients` — Paginated list of verified recipients from `v_all_recipients`.
4. `GET /api/recipients/{recipient_id}` — Single recipient profile lookup by `recipient_id`.
5. `POST /api/recall/check` — openFDA Food Enforcement API live recall check returning `HALTED`, `CLEAR`, or `NOT_CHECKED`.
6. `GET /api/tickets/{ticket_id}/recall` — Audit trail of recall checks recorded for a given ticket.
7. `GET /api/shelf-life/{product}` — USDA FoodKeeper lookup supporting subtitle matching and conservative range ends.
8. `GET /api/tracts/{geo_id}` — Census tract demographic profile lookup by 11-char FIPS `geo_id`.

### B. Matcher Service (`backend/services/matcher.py`)
- Executes genuine BigQuery `VECTOR_SEARCH` using `COSINE` distance against 3,072d vectors in `recipient_embeddings`.
- Joins with `v_all_recipients` (excluding pending profiles) and nearest tract demographics from `v_recipient_tract`.
- Records every candidate to Firestore `match_candidates` with pre-filter semantic rank, semantic distance, post-filter status, rejection reason, evidence, and last-mile metrics.
- Computes need scores based on tract poverty, no-vehicle rate, and assistance rate.

### C. Constraint Service (`backend/services/constraints.py`)
- Deterministic rules enforce food safety and logistical feasibility:
  - Cold storage requirement: `cold_storage IN ('commercial', 'domestic', 'walk_in', 'reach_in')`.
  - Frozen storage requirement: `frozen_storage == True`.
  - Pallet capacity: `max_pallets >= pallets_needed` (Phase 0 hard gate conversion: `20 crates = 1 pallet`).
  - Delivery margin: `margin_hours >= 0.0`.
- **Columns beat text rule:** Structured database columns always supersede free text.
- **Contradiction detection:** Detects conflicts between structured columns and profile text (e.g. loading dock, refrigeration, service days). Contradictions assign `CandidateStatus.FLAGGED` (`contradiction_flag = True`) for human coordinator review; never an auto-match guess.

### D. Last-Mile Logistics Service (`backend/services/last_mile.py`)
- Calculates ZIP-centroid haversine distance, explicitly labelled approximate (`approximate = True`, `source = HAVERSINE_FALLBACK`).
- Atlanta metro travel buffer: 0.5h for ≤15 km, 1.0h for 15–35 km, 1.5h for >35 km.
- Margin formula: $\text{margin\_hours} = \text{resolved\_hours\_left} - \text{pickup\_window\_hours} - \text{travel\_buffer\_hours}$. Negative margin marks candidate `FILTERED`.
- Evaluates transport: `refrigerated_transport == True` allows self-collection (`needs_driver = False`); otherwise `needs_driver = True`.
- Caches distances in Firestore `distance_pairs`.

### E. Recall Guard Service (`backend/services/recall.py`)
- Evaluates openFDA Food Enforcement API at `https://api.fda.gov/food/enforcement.json` BEFORE matching runs.
- **Rules:**
  - Active ongoing recall found $\implies$ `HALTED` (blocks surplus posting).
  - 0 matching recalls confirmed $\implies$ `CLEAR`.
  - Network error, timeout, HTTP 5xx, or forced failure $\implies$ `NOT_CHECKED`. **Never CLEAR on failure.**
  - Offline snapshot fallback allowed only when explicitly flagged and labelled as `source = OFFLINE_SNAPSHOT`.
- All checks written to Firestore `recall_checks`.
- **Observed Rate Limits:**
  - Unauthenticated openFDA: 40 requests/minute, 1,000 requests/day per IP.
  - Authenticated openFDA: 240 requests/minute.
  - Constant enforced: `OPENFDA_MAX_CALLS_PER_RUN = 40`.

### F. Managed BigQuery MCP Proof (Review Fix C1)
- Verified read-only execution via Google-managed MCP endpoint `https://bigquery.googleapis.com/mcp` using ADC.
- Invoked query: `SELECT count(*) as total_verified FROM \`qwiklabs-gcp-04-e030b511c03a.rescueguard_app.v_all_recipients\``
- BigQuery Job ID: `mv3ZgfLjFY15kWBA6FxzqLexZmH2@1a17ec942b7`
- Timestamp: `2026-10-27T19:14:41.569654+00:00`
- Result: 127 verified recipients returned.
- Isolation: Asserted to have zero inputs into matching or ranking algorithms (`is_ranking_input = False`).

---

## 2. Atlanta Planted Teaching Cases & Trap Verifications

| Trap / Case | Recipient Name | ID | Expected Behavior | Proven Result |
|---|---|---|---|---|
| **Planted Decoy** | Greenline Community Pantry | 119 | Requests fresh greens, but `cold_storage = 'none'` | **Semantic Rank #1** (distance 0.307), but filtered out with `CandidateStatus.FILTERED` (`"No cold storage available for refrigerated item (cold_storage='none')"`). Excluded from viable candidates. |
| **Contradiction** | Ridgeway Avenue Food Ministry | 123 | Column `loading_dock = False` vs text "dock height loading bay" | Flagged with `CandidateStatus.FLAGGED`, `contradiction_flag = True`, `"Profile text claims dock facilities but column loading_dock=False"`. |
| **Contradiction** | Harborview Neighbors Trust | 120 | Claims walk-in freezer then says "no freezer at present" | Flagged with `CandidateStatus.FLAGGED`, `contradiction_flag = True`. |
| **Vocabulary Mismatch** | Lakeshore Mutual Aid Collective | 127 | Uses "Chilled holding" instead of "refrigerated" | Retrieved in top results via semantic vector search (`AI.EMBED` 3,072d), proving meaning beats keyword matching. |
| **Active Recall** | Sprout Organics Baby Food | N/A | Active recall in openFDA for lead contamination | `RecallVerdict.HALTED`, recall ID `H-0134-2026`. Blocks posting. |
| **Failed Recall** | Simulated Network Error | N/A | Server unreachable / timeout | `RecallVerdict.NOT_CHECKED`. Never returns `CLEAR`. |

---

## 3. Firestore Native Collections Verified
1. `match_candidates`: Stored every candidate evaluated in vector search with rank, distance, status, and metrics.
2. `recall_checks`: Stored audit records of all live/simulated openFDA checks.
3. `distance_pairs`: Cached origin-destination ZIP centroid travel distances.

---

## 4. Test Suite Execution Output

```text
============================= test session starts ==============================
platform darwin -- Python 3.11.9, pytest-9.1.1, pluggy-1.7.0 -- /Users/reyanadil/RescueGuard/ai_for_impact_atl_2/.venv/bin/python
rootdir: /Users/reyanadil/RescueGuard/ai_for_impact_atl_2

backend/tests/test_contracts.py::test_all_29_contract_stores_registered PASSED [  3%]
backend/tests/test_contracts.py::test_all_52_endpoint_contracts_registered_and_valid PASSED [  6%]
backend/tests/test_contracts.py::test_hard_gate_1_units_conversion PASSED [  9%]
backend/tests/test_contracts.py::test_hard_gate_2_resolved_clock_and_starter_field_facts PASSED [ 12%]
backend/tests/test_contracts.py::test_review_fix_m5_donor_pickup_address_validation PASSED [ 15%]
backend/tests/test_contracts.py::test_review_fix_m1_execution_source_and_impact_score_fixture PASSED [ 18%]
backend/tests/test_contracts.py::test_action_card_schema PASSED          [ 21%]
backend/tests/test_contracts.py::test_phase_0_okf_files_and_no_frontend_folder PASSED [ 24%]
backend/tests/test_contracts.py::test_settings_and_health_endpoint PASSED [ 27%]
backend/tests/test_contracts.py::test_managed_bigquery_mcp_called_and_readonly_guard PASSED [ 30%]
backend/tests/test_data_layer.py::test_starter_table_row_counts PASSED   [ 33%]
backend/tests/test_data_layer.py::test_field_types_and_facts PASSED      [ 36%]
backend/tests/test_data_layer.py::test_coordinate_validity PASSED        [ 39%]
backend/tests/test_data_layer.py::test_planted_teaching_cases PASSED     [ 42%]
backend/tests/test_shelf_life_spinach_under_lettuce PASSED               [ 45%]
backend/tests/test_shelf_life_null_cases PASSED                          [ 48%]
backend/tests/test_shelf_life_donor_deadline_beats_book PASSED           [ 51%]
backend/tests/test_data_layer.py::test_v_recipient_tract_join PASSED     [ 54%]
backend/tests/test_data_layer.py::test_v_rescue_deserts_rule PASSED      [ 57%]
backend/tests/test_data_layer.py::test_search_read_path_returns_known_pantry PASSED [ 60%]
backend/tests/test_data_layer.py::test_search_read_path_excludes_pending_recipient PASSED [ 63%]
backend/tests/test_no_secrets.py::test_dotenv_gitignored_and_example_clean PASSED [ 66%]
backend/tests/test_no_secrets.py::test_no_hardcoded_project_id_or_secrets_in_tracked_files PASSED [ 69%]
backend/tests/test_phase_2.py::test_spinach_decoy_at_semantic_rank_1_and_filtered_no_cold PASSED [ 72%]
backend/tests/test_phase_2.py::test_no_cold_pantry_never_in_viable_list PASSED [ 75%]
backend/tests/test_phase_2.py::test_contradiction_case_is_flagged PASSED [ 78%]
backend/tests/test_phase_2.py::test_vocabulary_mismatch_found_by_meaning PASSED [ 81%]
backend/tests/test_phase_2.py::test_recall_halted_on_matching_recall PASSED [ 84%]
backend/tests/test_phase_2.py::test_forced_openfda_failure_returns_not_checked PASSED [ 87%]
backend/tests/test_phase_2.py::test_clean_product_returns_clear_recall PASSED [ 90%]
backend/tests/test_phase_2.py::test_managed_bigquery_mcp_proof_does_not_feed_ranking PASSED [ 93%]
backend/tests/test_phase_2.py::test_firestore_candidate_persistence PASSED [ 96%]
backend/tests/test_phase_2.py::test_api_endpoints_phase_2 PASSED         [100%]

======================= 33 passed, 5 warnings in 46.62s ========================
```

---

## 5. Phase Sign-off Checklist
- [x] 8 API endpoints registered and validated against Pydantic schema contracts.
- [x] Genuine BigQuery `VECTOR_SEARCH` implemented with pre-filter semantic ranking.
- [x] Deterministic constraint evaluation with cold-chain, capacity, and schedule rules.
- [x] Columns beat text rule and contradiction flagging (`CandidateStatus.FLAGGED`).
- [x] Greenline Community Pantry (#119) decoy test verified: semantic #1, filtered on cold chain.
- [x] Lakeshore Mutual Aid (#127) vocabulary mismatch verified: retrieved semantically.
- [x] openFDA Recall Guard verified: `HALTED` on hit, `NOT_CHECKED` on failure (never `CLEAR`).
- [x] Managed BigQuery MCP read-only query executed and verified isolated from ranking.
- [x] Firestore collections written: `match_candidates`, `recall_checks`, `distance_pairs`.
- [x] Module documentation written: `docs/modules/{matcher,constraints,last_mile,recall}.md`.
- [x] `CONTEXT.md` updated and verified < 300 lines (121 lines).
- [x] Secrets check passed (`test_no_secrets.py`).
- [x] Committed to `phase-2`, tagged `phase-2`, pushed branch + tag to `origin`.

**Next Step:** STOP. Await user explicit approval before starting Phase 3.

# RescueGuard Backend — Phase 3 Handoff

**Phase:** Phase 3 — Planner/splitter, checker/fixer, split maths, Code Execution, and plan versions  
**Date:** 2026-10-27  
**Branch:** `phase-3`  
**Base Commit / Tag:** `phase-2`  
**GCP Project:** `qwiklabs-gcp-04-e030b511c03a`  
**Repository Remote:** `git@github.com:mattchainsaw/ai_for_impact_atl_2.git`  

---

## 1. Summary of Deliverables

Phase 3 builds the surplus load allocation and distribution planner, the multi-pantry load splitter, the independent safety and equity checker, the deterministic fixer loop with loop guards, the Gemini Code Execution integration for verified split and margin maths, and the ticket / plan versioning lifecycle.

### A. Endpoints Implemented & Tested (15 cumulative)
1. `GET /api/health` — Phase 0 system health endpoint.
2. `POST /api/recipients/search` — Phase 2 BigQuery vector search.
3. `GET /api/recipients` — Phase 2 recipient directory listing.
4. `GET /api/recipients/{recipient_id}` — Phase 2 single recipient profile lookup.
5. `POST /api/recall/check` — Phase 2 openFDA food recall guard.
6. `GET /api/tickets/{ticket_id}/recall` — Phase 2 recall audit trail for ticket.
7. `GET /api/shelf-life/{product}` — Phase 2 USDA FoodKeeper shelf-life lookup.
8. `GET /api/tracts/{geo_id}` — Phase 2 Census tract demographic lookup.
9. `POST /api/postings` — Surplus posting creation (starter or live donor).
10. `GET /api/postings` & `GET /api/postings/{posting_id}` — Surplus posting retrieval.
11. `POST /api/tickets` — Ticket creation with posting source namespacing.
12. `GET /api/tickets` & `GET /api/tickets/{ticket_id}` — Ticket retrieval.
13. `POST /api/tickets/{ticket_id}/match` — Orchestrated Recall -> Match -> Plan -> Check -> Fix pipeline.
14. `GET /api/tickets/{ticket_id}/plans` & `GET /api/plans/{plan_id}` — Plan version history and single plan lookup.
15. `GET /api/tickets/{ticket_id}/parameters` & `POST /api/tickets/{ticket_id}/parameters` — Dynamic ticket run parameter overrides.

---

### B. Planner & Splitter Service (`backend/services/planner.py`)
- **Single vs. Split Load Strategy:** Evaluates whether a single viable recipient can take the entire surplus quantity within safe capacity (`CRATES_PER_PALLET = 20`). If surplus exceeds single capacity, splits across 2–3 viable verified recipients.
- **Constraints Enforced:** Recipient cold/frozen storage fit, available pallet/crate limits, pickup windows, and transit margins.
- **Plan Hashing:** Computes deterministic MD5 fingerprint across sorted allocations `(recipient_id, quantity, unit)` to detect identical consecutive plans in the loop guard.
- **Impact Metrics:** Computes estimated households served (`1 pallet = 35 households`, `1 crate = 1.75 households`) and estimated retail value rescued ($2.80/lb produce, $4.20/lb dairy, $6.50/lb meat).

---

### C. Gemini Code Execution for Maths (`backend/services/code_exec.py`)
- **Review Fix M1 Fulfilled:** Split and clock margin arithmetic is executed via Vertex AI Gemini Code Execution (`ToolCodeExecution` in `google.genai`).
- **Plan Records:** Every plan documents:
  - `execution_source`: `VERTEX_CODE_EXECUTION` (or `PYTHON_FALLBACK` when Vertex is unavailable).
  - `execution_code`: The Python script generated and executed in the Vertex sandbox.
  - `execution_output`: The JSON output containing allocations and clock margins.
- **Storage:** Persisted directly into Firestore `plan_versions` under `execution_details`.

---

### D. Independent Checker Service (`backend/services/checker.py`)
- Evaluates plans against six strict criteria before acceptance:
  1. **Waste Check:** Surplus must be fully allocated (`unallocated_quantity == 0`). Unallocated loads trigger `REJECTED_WASTE`.
  2. **Temperature Fit:** Refrigerated/frozen goods assigned to unequipped pantries trigger `REJECTED_TEMP_MISMATCH`.
  3. **Capacity Limits:** Allocations exceeding recipient maximum pallets/crates trigger `REJECTED_CAPACITY_EXCEEDED`.
  4. **Clock Margins:** Non-positive transit/pickup margins trigger `REJECTED_NEGATIVE_MARGIN`.
  5. **Concentration:** Excessive allocation skew within a single distribution run is flagged.
  6. **Equity Benchmark:** Compares recipient tract poverty rates against the Atlanta metro benchmark (`0.174`).
- Outputs `PlanStatus.PASSED` or `PlanStatus.CHECKER_REJECTED` with specific explanatory strings.

---

### E. Deterministic Fixer Loop (`backend/services/fixer.py`)
- Iteratively refines rejected plans up to `CHECKER_MAX_ATTEMPTS = 3`.
- **Loop Guards:** Halts and escalates to human coordinator review under three strict conditions:
  1. Maximum attempt count reached (`attempt_count >= 3`).
  2. Same plan hash produced consecutively (`current_hash == last_hash`).
  3. Same primary checker rejection reason encountered twice consecutively.
- **Zero External Calls:** The fixer loop performs pure deterministic in-memory adjustments (no recursive API or LLM calls in the loop).
- **Escalation State:** When halted by guards, plan status is preserved as `DRAFT` or `CHECKER_REJECTED` for human review.

---

### F. Ticket Orchestration & Namespacing (`backend/services/tickets.py`)
- **Posting ID Namespacing:** Completely avoids ID collisions between starter dataset postings and live donor postings:
  - Starter: `ticket-starter-{posting_id}`
  - Live Donor: `ticket-live-{posting_id}`
- **Fallback on Unviable Matches:** When no viable recipients exist or all candidates fail safety/capacity filters, `execute_ticket_match` raises `NoViableMatchException`, caught and returned as HTTP 422 with a structured `NoViableMatchFallback` response.

---

## 2. Test Fixtures & Proofs Verified

| Fixture / Test | Expected Behavior | Proven Result |
|---|---|---|
| **Spinach Fixture** | v1 single pantry leaves waste (rejected); v2 split places full 100 crates and passes | `v1` rejected for `100.0 CRATES wasted`; `v2` split across 2 pantries passes checker with 0 waste |
| **Farm Fixture** | 12-pallet bulk load split across verified pantries without exceeding 6-pallet limits | Split across 2 pantries (6 pallets each); checker passes with 0 capacity overload |
| **Loop Guard Fixture** | Impossible demand with 3 fixer attempts triggers loop guard and escalates | Stopped after 3 attempts; primary reason repeated; escalated to human review; no infinite loop |
| **No-Viable Fixture** | Posting with impossible cold requirements returns HTTP 422 fallback | HTTP 422 received with `NoViableMatchFallback`, reason `NO_VIABLE_CANDIDATES`, candidates count = 0 |
| **Ticket Namespacing** | Distinct prefixes for starter vs live donor postings | `ticket-starter-p-101` and `ticket-live-p-101` coexist in Firestore without collision |
| **Code Execution Proof** | Vertex Code Execution metadata recorded on generated plan | `execution_source` recorded, `execution_code` and `execution_output` present in plan document |
| **API Endpoints** | Full CRUD for postings, tickets, parameters, and match execution via FastAPI | All 15 endpoints return 200/201/422 as expected |

---

## 3. Test Suite Execution Output

```text
============================= test session starts ==============================
platform darwin -- Python 3.11.9, pytest-9.1.1, pluggy-1.7.0 -- /Users/reyanadil/RescueGuard/ai_for_impact_atl_2/.venv/bin/python
cachedir: .pytest_cache
rootdir: /Users/reyanadil/RescueGuard/ai_for_impact_atl_2
plugins: anyio-4.15.1
collected 40 items

backend/tests/test_contracts.py ..........                               [ 25%]
backend/tests/test_data_layer.py ...........                             [ 52%]
backend/tests/test_no_secrets.py ..                                      [ 57%]
backend/tests/test_phase_2.py ..........                                 [ 82%]
backend/tests/test_phase_3.py .......                                    [100%]

================== 40 passed, 5 warnings in 120.67s (0:02:00) ==================
```

### Phase 3 Specific Test Output
```text
backend/tests/test_phase_3.py::test_spinach_fixture_waste_rejected_and_v2_split_passes PASSED [ 14%]
backend/tests/test_phase_3.py::test_farm_fixture_large_load_splits_without_overload PASSED [ 28%]
backend/tests/test_phase_3.py::test_loop_fixture_max_attempts_and_guards_escalate PASSED [ 42%]
backend/tests/test_phase_3.py::test_no_viable_fixture_returns_422_fallback PASSED [ 57%]
backend/tests/test_phase_3.py::test_ticket_creation_starter_vs_live_no_collision PASSED [ 71%]
backend/tests/test_phase_3.py::test_code_execution_maths_and_storage_proof PASSED [ 85%]
backend/tests/test_api_endpoints_postings_tickets_match_and_plans PASSED [100%]

=================== 7 passed, 5 warnings in 63.22s (0:01:03) ===================
```

---

## 4. Documentation Modules Created & Updated
1. `docs/modules/planner.md` — Single pantry vs multi-pantry splitter and load balancing.
2. `docs/modules/checker.md` — Waste, cold-chain, capacity, clock margin, and equity checks.
3. `docs/modules/fixer.md` — Deterministic fixer loop, 3 loop guards, escalation semantics.
4. `docs/modules/tickets.md` — Ticket lifecycle, namespacing, and parameter overrides.
5. `CONTEXT.md` — Synchronized with Phase 3 state and architecture.
6. `docs/handoffs/phase-3.md` — This handoff document.

---

## 5. Exit Gate Checklist
- [x] All 7 Phase 3 test fixtures passing (`test_phase_3.py`).
- [x] Full regression test suite passing (40/40 tests).
- [x] Zero hardcoded secrets verified (`test_no_secrets.py`).
- [x] Gemini Code Execution recorded on plan documents.
- [x] Fixer loop guards proven (zero external calls, stops at max attempts / duplicate hashes / duplicate errors).
- [x] Starter vs live donor ticket ID namespacing proven.
- [x] No UI or frontend code written (`frontend/` does not exist).
- [x] Ready for Phase 4 (Holds, Coordinator Desk & Clicks, Approvals).

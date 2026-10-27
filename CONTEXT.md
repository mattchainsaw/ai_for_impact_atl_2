# CONTEXT — RescueGuard backend

## Purpose (3 lines max)
RescueGuard is a backend-only, multi-agent food-rescue broker for Atlanta that matches perishable surplus postings to community recipients using BigQuery `VECTOR_SEARCH`, deterministic safety/capacity constraints, Gemini Code Execution split/margin maths, independent Checker/Fixer verification, and transactional Firestore holds.
FastAPI owns all orchestration, state transitions, and deterministic specialists; Vertex AI via ADK (`google-adk`) is used solely for the conversational Guide agent (`POST /api/assistant/chat`).
No frontend UI, video, or deck code exists in this build (`frontend-contracts/` holds contract notes only).

## Architecture (supervisor + specialists, text diagram)
```text
Frontend contracts (later, outside this plan) --HTTP/JSON only--> Backend (Cloud Run, stateless, FastAPI)
  Supervisor — routes, owns ticket + plan versions, veto/escalate,
               approval gate, holds, tenant/role filtering (demo, recorded)
  Specialists — Matcher | Constraint+Last-Mile | Recall Guard |
                Planner/Splitter | Checker/Auditor | Fixer |
                Impact & Fairness | Guide (ADK, chat only) |
                Onboarding (bonus)
  Data — BigQuery starter (read-only) + app history/views |
         Firestore (live ticket state)
  External — Vertex/ADK models, openFDA, Maps (bonus, fallback)
```
- **Architectural lock:** FastAPI owns everything. ADK is used only for Guide chat (`POST /api/assistant/chat`). ADK v2 graph is a documented subgraph fallback only and is not the primary supervisor.

## APIs (name + signature only, full detail in CONTRACTS.md)
- **Health, identity, starter reads (7):** `GET /api/health`, `GET /api/me`, `GET /api/starter-postings`, `GET /api/shelf-life/{product}`, `GET /api/tracts/{geo_id}`, `GET /api/recipients`, `GET /api/recipients/{recipient_id}`
- **Postings, tickets, matching, plans (14):** `POST /api/postings`, `GET /api/postings`, `GET /api/postings/{posting_id}`, `POST /api/tickets`, `GET /api/tickets`, `GET /api/tickets/{ticket_id}`, `POST /api/tickets/{ticket_id}/match`, `GET /api/tickets/{ticket_id}/parameters`, `POST /api/tickets/{ticket_id}/parameters`, `POST /api/tickets/{ticket_id}/cancel`, `GET /api/tickets/{ticket_id}/plans`, `GET /api/plans/{plan_id}`, `POST /api/plans/{plan_id}/approve`, `POST /api/plans/{plan_id}/reject`
- **Holds, allocations, completion (8):** `GET /api/tickets/{ticket_id}/holds`, `GET /api/holds/{hold_id}`, `POST /api/holds/{hold_id}/confirm`, `POST /api/holds/{hold_id}/release`, `POST /api/tickets/{ticket_id}/decline`, `POST /api/allocations/{allocation_id}/complete`, `POST /api/allocations/{allocation_id}/no-show`, `GET /api/allocations`
- **Recipients, onboarding, profile updates (3):** `POST /api/recipients/search`, `POST /api/recipients`, `PATCH /api/recipients/{recipient_id}`
- **Tasks, actions, Guide chat (7):** `POST /api/tasks`, `GET /api/tasks`, `GET /api/tasks/{task_id}`, `PATCH /api/tasks/{task_id}`, `POST /api/actions/approve`, `POST /api/assistant/chat`, `GET /api/conversations/{session_id}`
- **Impact, equity, deserts, safety, last-mile (9):** `GET /api/tickets/{ticket_id}/impact`, `GET /api/impact/dashboard`, `POST /api/equity/audit`, `GET /api/equity/{ticket_id}`, `GET /api/deserts`, `GET /api/deserts/{tract_geo_id}`, `POST /api/recall/check`, `GET /api/tickets/{ticket_id}/recall`, `GET /api/tickets/{ticket_id}/last-mile`
- **Maps (bonus), audit, telemetry (4):** `POST /api/maps/geocode`, `POST /api/maps/route`, `GET /api/audit/export`, `GET /api/telemetry`

## Tables (name + key columns only — 29 total)
- **A. Starter BigQuery `a4i_food` (4, read-only):**
  1. `recipients` (127 rows, `recipient_id INT64, name, zip_code, cold_storage, frozen_storage, loading_dock, refrigerated_transport, max_pallets, pickup_window_hours, weekly_households, populations_served, service_days, profile_text, profile_source, latitude, longitude`)
  2. `surplus_postings` (10 rows, `posting_id, track, posting_text, foodkeeper_product, storage_state, hours_available, shelf_life_hours, hours_remaining`)
  3. `shelf_life` (661 rows, `product_id, product_name, product_subtitle, keywords, category, refrigerated_hours, pantry_hours`)
  4. `tract_demographics` (165 rows, `geo_id STRING 11-char, tract_lat, tract_lon, total_pop, median_income, poverty_rate, no_vehicle_rate, assistance_rate`)
- **B. Team BigQuery `rescueguard_app` (6):**
  5. `recipient_embeddings` (127 rows, `recipient_id INT64, profile_text, embedding ARRAY<FLOAT64> 3072d via AI.EMBED, embedded_status`)
  6. `app_recipients` (`recipient_id INT64, name, cold_storage, max_pallets, verification_status PENDING|VERIFIED|DEMO_SIMULATED, created_at`)
  7. `recipient_overrides` (`override_id, recipient_id, changed_fields, parsed_dietary_flags, status PENDING|VERIFIED|APPROVED, effective_date, approver_role`)
  8. `v_all_recipients` (127 rows, starter + verified app recipients with latest approved overrides & parsed `dietary_flags[]`)
  9. `v_recipient_tract` (127 rows, nearest tract via `ST_DISTANCE`, recipient-to-tract distance 0.22–6.24 km, fallback `weekly_households`, status `FOUND|UNKNOWN`)
  10. `v_rescue_deserts` (0 rows under full cold domain; tracts with poverty > 0.30 & no_vehicle > 0.40 & cold_recipients_within_5km == 0)
- **C. Firestore Live — tickets/plans/holds (9):**
  11. `postings` (`posting_id, donor_org_name, pickup_address, address_type=ORG_DOCK, coordinator_asserted_org_dock, quantity, quantity_unit, pallets_equivalent, donor_deadline, tenant_id`)
  12. `tickets` (`ticket_id, posting_id, posting_source, current_plan_id, resolved_deadline, resolved_shelf_life_hours, shelf_life_source, status, tenant_id`)
  13. `plans` (`plan_id, ticket_id, plan_version, status, allocations[], execution_source, plan_hash, fixer_attempt_count, tenant_id`)
  14. `match_candidates` (`ticket_id, run_id, recipient_id, semantic_rank, semantic_distance, status, filter_reason, evidence, need_score`)
  15. `match_briefs` (`ticket_id, plan_id, plan_version, brief_text, guardrail_callout, next_two_options[]`)
  16. `holds` (`hold_id, ticket_id, plan_id, recipient_id, quantity, quantity_unit, status, expires_at, request_id, tenant_id`)
  17. `allocations` (`allocation_id, hold_id, recipient_id, ticket_id, plan_id, quantity, status, tract_geo_id, need_score_at_allocation, tenant_id`)
  18. `tasks` (`task_id, ticket_id, plan_id, task_type, owner_role, status, tenant_id`)
  19. `approvals` (`approval_id, target_type, target_id, action_id, decision, approver_role, plan_version, request_id, tenant_id`)
- **D. Firestore Live — people/safety/audit (7):**
  20. `conversations` (`session_id, ticket_id, role, messages[], action_cards[], scrub_status, tenant_id`)
  21. `recall_checks` (`check_id, ticket_id, product_text, verdict, recall_id, checked_at, source, tenant_id`)
  22. `notifications` (`notification_id, recipient_role, recipient_org_id, ticket_id, event, read_status, tenant_id`)
  23. `audit_log` (`audit_id, ticket_id, plan_version, event_type, actor_role, action, timestamp, request_id, tenant_id`)
  24. `telemetry_events` (`event_id, request_id, tool_or_endpoint, latency_ms, status, created_at, tenant_id`)
  25. `distance_pairs` (`pair_key, distance_km, drive_time_minutes, source, cached_at, expires_at, tenant_id`)
  26. `users_roles` (`user_id, role, org_id, tenant_id`)
- **E. BigQuery History `rescueguard_app` Sinks (3):**
  27. `audit_history` (`audit_id, ticket_id, plan_version, event_type, actor_role, timestamp, request_id, tenant_id`)
  28. `impact_snapshots` (`snapshot_id, ticket_id, plan_id, total_impact_score, need_score, food_rescued_score, equity_score, reliability_score`)
  29. `equity_audit_results` (`audit_id, ticket_id, plan_id, verdict, reasons, audited_at, tenant_id`)

## Enums (YES/NO/UNRECORDED, plan/hold/allocation statuses, verdicts)
- **Capability/Fact Tri-State:** `YES`, `NO`, `UNRECORDED`
- **TicketStep:** `POSTED`, `MATCHED`, `CHECKED`, `APPROVED`, `HELD`, `CONFIRMED`, `COMPLETED`, `DECLINED`, `RE_PLANNED`, `CANCELLED`, `EXPIRED`, `FDA_HALTED`, `SPLIT_REQUIRED`
- **TicketStatus:** `ACTIVE`, `RESUMABLE`, `INTERRUPTED`, `COMPLETED`, `CANCELLED`, `FDA_HALTED`
- **PlanStatus:** `DRAFT`, `CHECKER_REJECTED`, `APPROVED`, `SUPERSEDED`
- **CandidateStatus:** `ELIGIBLE`, `FILTERED`, `FLAGGED`, `TIED`
- **HoldStatus:** `ACTIVE`, `CONFIRMED`, `EXPIRED`, `RELEASED`
- **AllocationStatus:** `CONFIRMED`, `DECLINED`, `NO_SHOW`, `EXPIRED`, `COMPLETED`
- **Verdicts:** Recall = `CLEAR | HALTED | NOT_CHECKED`; Equity = `PASS | WARN`; ShelfLifeSource = `FOODKEEPER | DONOR_FALLBACK | NOT_APPLICABLE`; ExecutionSource = `CODE_EXECUTION | PYTHON_FALLBACK`; DistanceSource = `GOOGLE_ROUTES | HAVERSINE_FALLBACK`; TractStatus = `FOUND | UNKNOWN`

## Non-negotiable rules (the 10 rules in this file)
1. **Honest unknowns:** Unrecorded is not no, not-checked is not clear, blank shelf-life is never a silent zero (`YES / NO / UNRECORDED`; failed recall = `NOT_CHECKED`).
2. **Columns beat text:** When structured columns and profile text disagree, the column wins for filtering and the row is flagged `Needs human check`.
3. **Meaning is not capacity:** Vector search finds semantic candidates only; deterministic hard constraints decide viability.
4. **Deterministic maths + Code Execution (M1):** Split and margin maths for a plan MUST run through Gemini Code Execution (`execution_source = CODE_EXECUTION`), with plain deterministic Python as a labelled fallback only (`execution_source = PYTHON_FALLBACK`).
5. **Human-in-the-loop is a gate, not a label:** No plan approved, no hold started, nothing dispatched without an idempotent human approval record (`request_id`).
6. **Every plan change is a new version:** Append-only plans (`v1`, `v2`, `v3`); never overwrite an approved or rejected plan.
7. **Loop guards:** Checker/fixer capped at `CHECKER_MAX_ATTEMPTS = 3`, duplicate `plan_hash` and repeated `last_checker_reason` stop the loop, zero external calls inside the loop.
8. **Need is area-level, never a moral score:** Tract `poverty_rate`, `no_vehicle_rate`, `assistance_rate` only; never race or `reported_income`. Fit first, need second, fairness third.
9. **Guardrail transparency:** Every Match Brief includes the “Safety & Capacity Guardrails: Why Top Semantic Matches Were Filtered” callout from stored `match_candidates`.
10. **Honest labels:** Households reached are estimated (never summed as unique people); ZIP-centroid distances are approximate; donor deadline always beats FoodKeeper.

## Traps (planted, NULL shelf-life, Spinach-under-Lettuce, ZIP centroid, tract join)
1. **9 Planted teaching cases (`profile_source = 'planted'`):**
   - ID 119: Greenline Community Pantry (Decoy: asks for fresh greens, but `cold_storage = 'none'`).
   - ID 120: Harborview Neighbors Trust (Contradiction: profile text claims walk-in freezer then says 'no freezer at present').
   - ID 121 & ID 122: Cedar Street vs Maple Street Produce Alliances (Tie: identical 10 pallets, 600 households, dock, reefer truck).
   - ID 123: Ridgeway Avenue Food Ministry (Contradiction: column dock=False vs text dock height, service days Mon/Wed/Fri vs text Tue/Thu).
   - ID 124: Southline Neighbors Pantry (Column Mon/Wed/Fri vs text Tue/Thu; 2 walk-in coolers).
   - ID 125: Third Ward Community Table (Column Mon/Wed/Fri vs text Tue/Thu; small domestic fridge, 1 pallet).
   - ID 126: Brookfield Family Resource Center (Column Mon/Wed/Fri vs text Tue/Thu; walk-in, 3 pallets).
   - ID 127: Lakeshore Mutual Aid Collective (Vocabulary mismatch: 'Chilled holding' for commercial cold).
2. **NULL shelf-life (`shelf_life_hours IS NULL`):**
   - Posting 9: Diapers / wipes -> `NOT_APPLICABLE` (non-food).
   - Posting 2: Milk (use-by code date) -> `DONOR_FALLBACK`.
   - Posting 8: Sealed infant formula (tracked only after opening) -> `DONOR_FALLBACK`.
   - All fall back to donor `hours_available`, never `0`.
3. **“Spinach” under “Lettuce”:** In `a4i_food.shelf_life`, Spinach is located under `product_name = 'Lettuce'` and `product_subtitle = 'leaf, spinach'` (product_id = 291, 72.0 refrigerated hours). Conservative range end enforced.
4. **ZIP centroids:** Recipient `latitude`/`longitude` are ZIP centroids (0 invalid, 0 out-of-bounds in Atlanta starter). Distance is labelled `HAVERSINE_FALLBACK`.
5. **Tract join & types:** `recipient_id` is `INT64`; `tract_demographics.geo_id` is 11-char `STRING` (with leading zeros, e.g. `'13121001001'`); `service_days` is comma-separated `STRING`. Left-join nearest tract via `ST_DISTANCE` (all 127 recipients between 0.22 km and 6.24 km from nearest tract centroid; 0% missing rate in starter; fallback to `weekly_households`, status `FOUND | UNKNOWN`).

## Decisions log (date — decision — why, newest last, keep last 30)
- `2026-10-27` — **C1 Managed BigQuery MCP Locked:** Use built-in Google-managed BigQuery MCP (`https://bigquery.googleapis.com/mcp`) via backend for guarded read-only one-off questions (`execute_sql_readonly`), recording SQL + `job_id`. No MCP Toolbox container.
- `2026-10-27` — **C2 Part 1 Redaction Locked:** Redacted literal project ID in `rescueguard-build-plan-setup-information.md` to `<event-project-from-config>` / `$GOOGLE_CLOUD_PROJECT` before push.
- `2026-10-27` — **C3 Canonical Working Copy Locked:** Antigravity session clone `/Users/reyanadil/RescueGuard/ai_for_impact_atl_2` is canonical; pushes go to `origin` (`mattchainsaw/ai_for_impact_atl_2`).
- `2026-10-27` — **M1–M5 Review Fixes Locked:** Code Execution primary (`CODE_EXECUTION`) with `PYTHON_FALLBACK`; canonical local/deploy commands; "by clicks" = direct HTTP API calls; frontend diagram relabelled; `ORG_DOCK` + coordinator assertion + residential regex validation on live postings.
- `2026-10-27` — **Hard Gate 1 (Units) & Hard Gate 2 (Resolved Clock) Locked:** `CRATES_PER_PALLET = 20` in `backend/app/config.py`; single resolved clock (`resolved_deadline`, `resolved_shelf_life_hours`, `shelf_life_source`, `resolved_at`) and margin formula locked in `CONTRACTS.md` (contracts frozen v1, 29/52).
- `2026-10-27` — **Phase 1 Data Layer Built & Proven:** `rescueguard_app` created in US region; 127 recipient embeddings generated via `AI.EMBED` gemini-embedding-2 (3,072d); `v_all_recipients`, `v_recipient_tract`, and `v_rescue_deserts` deployed; search read path proven (`VECTOR_SEARCH` returns verified recipients and drops pending ones); 9 Atlanta planted teaching cases and traps documented. 23/23 tests pass.
- `2026-10-27` — **Phase 2 Matcher, Constraints, Last-Mile & Recall Guard Built & Proven:** Real `VECTOR_SEARCH` matching with pre-filter semantic ranking and post-filter viability ranking; Greenline #119 decoy proves semantic #1 is safely filtered on cold chain; Ridgeway #123 proves column-beats-text sets `FLAGGED`; Lakeshore #127 proves vocabulary mismatch handled; openFDA rate limit recorded (40 req/min unauthenticated, `OPENFDA_MAX_CALLS_PER_RUN = 40`), `HALTED` on match, `NOT_CHECKED` on error (never CLEAR); managed BigQuery MCP (C1) executed read-only and verified isolated from ranking; Firestore Native persistence verified across `match_candidates`, `recall_checks`, and `distance_pairs`. 33/33 tests pass.

## Current phase / Last test result / Next phase
- **Current phase:** Phase 2 — Matcher, constraint, last-mile basics, recall (COMPLETE — awaiting user approval for Phase 3)
- **Last test result:** `pytest backend/tests/` — ALL 33 PASSED (10 contract tests, 11 data layer tests, 2 no-secrets tests, 10 phase 2 matcher/constraint/recall tests).
- **Next phase:** Phase 3 — Planner, checker/fixer, split maths, Code Execution, holds (do NOT start until user approves).

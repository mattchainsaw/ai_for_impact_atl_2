# CONTRACTS.md — RescueGuard Frozen Backend Contracts (v1, 29 Tables / 52 Endpoints)

> **Contract Authority:** `rescueguard-backend-build-plan.md` (Part 2 — sole build authority).
> Any change to a public endpoint, table/collection schema, enum, or hard gate requires updating `CONTRACTS.md` first with an explicit contract-change note, then `schemas/`, then code and tests.

---

## 1. Phase 0 Review Fixes & Architectural Locks

1. **Managed MCP Implementation (Review Fix C1 — Locked):**
   - **Chosen implementation:** Google's **built-in managed BigQuery MCP server** (`https://bigquery.googleapis.com/mcp`), invoked through the backend (`backend/tools/mcp_bigquery.py`) for guarded, read-only, one-off data questions (`execute_sql_readonly` only).
   - **Explicitly excluded:** We do **not** run a self-hosted MCP Toolbox container.
   - **Proof requirement:** Every MCP invocation returns and logs `{sql_query, job_id, project_id, mcp_endpoint, executed_at_utc, rows}` proving execution against BigQuery with a non-empty `job_id`. Free-form MCP SQL never feeds ranking, matching, or impact calculations.
2. **Part 1 Redaction & Push Decision (Review Fix C2 — Locked):**
   - `rescueguard-build-plan-setup-information.md` (Part 1) has its literal project ID redacted to `<event-project-from-config>` / `$GOOGLE_CLOUD_PROJECT` before being committed and pushed. No file in `backend/`, `schemas/`, config files, or `.env.example` may contain the literal GCP project ID.
3. **Canonical Working Copy (Review Fix C3 — Locked):**
   - The Antigravity session clone at `/Users/reyanadil/RescueGuard/ai_for_impact_atl_2` (remote `origin` = `https://github.com/mattchainsaw/ai_for_impact_atl_2.git`) is the canonical working copy for Phase 0 and subsequent Antigravity build sessions; Reyan's separate manual inspection clone is for inspection/review unless explicitly pushed from.
4. **Code Execution vs. Deterministic Python (Review Fix M1 — Locked):**
   - Split and clock-margin maths for a plan **MUST** run through the **Gemini Code Execution** tool (`execution_source = "CODE_EXECUTION"`), storing `{code, output, execution_source}` on the plan.
   - Deterministic in-process Python is permitted **only as an explicitly labelled fallback** (`execution_source = "PYTHON_FALLBACK"`) if Gemini Code Execution is unavailable or times out in the lab environment.
5. **Canonical Local Run & Deploy Commands (Review Fix M2 — Locked):**
   - **Local run:**
     ```bash
     pip install -r requirements.txt
     uvicorn backend.app.main:app --host 0.0.0.0 --port 8080
     # Health check:
     curl -s localhost:8080/api/health
     ```
   - **Deploy template:**
     ```bash
     gcloud run deploy rescueguard-backend \
       --source . \
       --project "$GOOGLE_CLOUD_PROJECT" \
       --region "$CLOUD_RUN_REGION" \
       --allow-unauthenticated
     ```
6. **"By Clicks" Definition (Review Fix M3 — Locked):**
   - In Phase 4 and all backend tests, "by clicks" means direct HTTP API requests simulating coordinator/donor/recipient desk actions (`POST /api/actions/approve`, `POST /api/plans/{plan_id}/approve`, `POST /api/holds/{hold_id}/confirm`, etc.) producing the exact same Firestore ticket/plan/hold state as the Guide chat proposal path — **zero frontend UI code**.
7. **Architecture Diagram Frontend Label (Review Fix M4 — Locked):**
   - Architecture diagrams label the client boundary strictly as: `Frontend contracts (later, outside this plan) --HTTP/JSON only--> Backend (Cloud Run, stateless, FastAPI)`.
8. **Donor Pickup-Address Validation Rule (Review Fix M5 — Locked):**
   - Live donor postings (`POST /api/postings`) are rejected with HTTP `422` unless **all three** conditions hold:
     - **(a)** `address_type == "ORG_DOCK"`
     - **(b)** Coordinator assertion is present (`coordinator_asserted_org_dock == True`, non-empty `asserted_by_role == "COORDINATOR"`, and `asserted_at` timestamp recorded)
     - **(c)** Format check passes: non-empty `donor_org_name` and `pickup_address` does not match residential free-text patterns (`\b(home|house|apt|apartment|residence|residential|condo|unit\s*#?\d+|private\s+residence|my\s+place)\b`, case-insensitive).
9. **Model Choice & Firestore Location (Phase 0 Lock):**
   - Single `MODEL_ID` (`gemini-2.5-flash` from config) serves Guide chat (via Vertex AI ADK), matcher explanations, and Gemini Code Execution. No second unrecorded model variable may be introduced.
   - Firestore database `(default)` is verified as `FIRESTORE_NATIVE` in location `nam5` (multi-region US).

---

## 2. Hard Gates (Phase 0 Mandatory Locks)

### Hard Gate 1 — Units Conversion Rule (`CRATES_PER_PALLET`)
- **Rule Locked:** Standard crate-to-pallet conversion is **20 crates = 1 pallet** (`CRATES_PER_PALLET = 20`).
- **Decider:** RescueGuard Backend Architecture Team (Phase 0 contract freeze).
- **Config Location:** `backend/app/config.py` (`Settings.crates_per_pallet = 20`, module constant `CRATES_PER_PALLET = 20`, overridable via `CRATES_PER_PALLET` env var).
- **Conversion Formula:**
  - When `quantity_unit == "PALLETS"`, `pallets_equivalent = float(quantity)`.
  - When `quantity_unit == "CRATES"`, `pallets_equivalent = round(float(quantity) / CRATES_PER_PALLET, 4)`.
  - Holds, allocations, and plans store both `quantity + quantity_unit` and `pallets_equivalent` used for checking against `max_pallets`.

### Hard Gate 2 — Resolved Clock Rule & Starter Field Facts
- **Resolved Clock Fields on Every Ticket (`tickets`):**
  - `resolved_deadline` (`datetime` UTC): Single authoritative expiration timestamp for the ticket.
  - `resolved_shelf_life_hours` (`float`): Effective hours remaining from `resolved_at` until `resolved_deadline`.
  - `shelf_life_source` (`ShelfLifeSource` enum):
    - `FOODKEEPER`: `min(hours_available, foodkeeper_refrigerated_or_pantry_hours)` governed by FoodKeeper biological shelf life (conservative end of range; `"Spinach"` matched via subtitle under `"Lettuce"`).
    - `DONOR_FALLBACK`: FoodKeeper `shelf_life_hours` is `NULL` on a food item with package-date guidance (e.g., milk use-by date, sealed infant formula) OR `hours_available <= shelf_life_hours`; falls back to donor `hours_available` / `donor_deadline`. Never treat `NULL` as `0`.
    - `NOT_APPLICABLE`: Non-perishable / non-food item (e.g., diapers where `foodkeeper_product` is `NULL` or non-food); governed strictly by donor availability window (`hours_available`).
  - `resolved_at` (`datetime` UTC): Timestamp when the clock was resolved.
- **Safety Margin Formula (Single Source of Truth):**
  $$\text{margin\_hours} = \text{resolved\_hours\_left} - \text{pickup\_window\_hours} - \text{travel\_buffer\_hours}$$
  - A candidate allocation is clock-safe if and only if $\text{margin\_hours} \ge 0$ and $\text{pickup\_eta} \le \text{resolved\_deadline}$.
- **Verified Starter Field Facts (`a4i_food` in US):**
  - `recipients.recipient_id`: `INTEGER` (`INT64`, values `1`..`127` in starter; app-onboarded recipients use `INT64 >= 10001`).
  - `tract_demographics.geo_id`: `STRING` (11-character FIPS string preserving leading zeros, e.g., `"13121001001"`).
  - `recipients.service_days`: `STRING` (comma-separated day names/phrases such as `"Monday, Wednesday, Friday"`, `"Tuesday, Thursday"`, `"Weekdays"`, `"Daily"`).
  - `recipients.cold_storage` distinct values (6): `'domestic'` (87), `'walk-in'` (11), `'medical'` (8), `'commercial'` (8), `'none'` (7), `'vehicle'` (6).

---

## 3. Tables & Collections Contract — 29 Total, Locked

### A. Starter BigQuery `a4i_food` — Read-Only (4)

| # | Table | Key Columns & Contract Notes |
|---|---|---|
| 1 | `a4i_food.recipients` | `recipient_id (INT64), ein, name, street, city, state, zip_code, cold_storage, frozen_storage, loading_dock, refrigerated_transport, max_pallets, pickup_window_hours, weekly_households, reported_income (never used for ranking), populations_served, service_days, profile_text, profile_source, latitude, longitude` |
| 2 | `a4i_food.surplus_postings` | `posting_id, track, posting_text, foodkeeper_product, storage_state, hours_available, shelf_life_hours (nullable), hours_remaining`. No donor name/address. |
| 3 | `a4i_food.shelf_life` | `product_id, product_name, product_subtitle, keywords, category, refrigerated_hours, refrigerated_note, pantry_hours, pantry_note` |
| 4 | `a4i_food.tract_demographics` | `geo_id (STRING), tract_lat, tract_lon, total_pop, median_income, poverty_rate, no_vehicle_rate, assistance_rate`. No race columns. |

### B. Team BigQuery `rescueguard_app` Tables & Views (6)

| # | Table / View | Purpose & Contract Rules |
|---|---|---|
| 5 | `rescueguard_app.recipient_embeddings` | `recipient_id (INT64), profile_text, embedding (ARRAY<FLOAT64>, 3072d via AI.EMBED gemini-embedding-2), embedded_status`. Brute-force `VECTOR_SEARCH`, joined to `v_all_recipients`. |
| 6 | `rescueguard_app.app_recipients` | App-owned onboarded pantries only. Never insert into starter `recipients`. `verification_status: PENDING \| VERIFIED \| DEMO_SIMULATED`; `PENDING` is ineligible for fresh/frozen. |
| 7 | `rescueguard_app.recipient_overrides` | App-owned profile changes: `override_id, recipient_id, changed_fields, parsed_dietary_flags, status (PENDING \| VERIFIED \| APPROVED), effective_date, approver_role`. |
| 8 | `rescueguard_app.v_all_recipients` | View combining starter `recipients` + verified `app_recipients` with `APPROVED` `recipient_overrides` applied and parsed `dietary_flags[]`. All matching reads through this view. |
| 9 | `rescueguard_app.v_recipient_tract` | View mapping recipient → nearest census tract (`tract_geo_id, poverty_rate, no_vehicle_rate, assistance_rate, median_income, tract_distance_km, tract_status FOUND \| UNKNOWN`). `tract_distance_km` is recipient-to-tract only, never donor-to-recipient. |
| 10 | `rescueguard_app.v_rescue_deserts` | View identifying tracts where `poverty_rate > 0.30 AND no_vehicle_rate > 0.40` and verified cold-capable recipients within 5 km = `0`. |

### C. Firestore Live — Tickets, Plans, Holds (9 Collections)

| # | Collection | Key Fields & Contract Rules |
|---|---|---|
| 11 | `postings` | Live donor offers: `posting_id, donor_id, donor_org_name, pickup_address, address_type (must be ORG_DOCK), coordinator_asserted_org_dock, asserted_by_role, asserted_at, pickup_zip, pickup_lat, pickup_lon, product_text, track, quantity, quantity_unit, pallets_equivalent, split_allowed, delivery_available, dietary_flags[], temperature_requirement, donor_deadline, status, created_at, expires_at, tenant_id` |
| 12 | `tickets` | `ticket_id, posting_id, posting_source (STARTER \| LIVE_DONOR), posting_ref, metro, step, current_plan_id, plan_version_current, parameters {top_n, weights, split_allowed}, resolved_deadline, resolved_shelf_life_hours, shelf_life_source, resolved_at, holds_already_started[], tasks_already_approved[], step_started_at, status (ACTIVE \| RESUMABLE \| INTERRUPTED \| COMPLETED \| CANCELLED \| FDA_HALTED), tenant_id` |
| 13 | `plans` | Append-only per version: `plan_id, ticket_id, plan_version, status (DRAFT \| CHECKER_REJECTED \| APPROVED \| SUPERSEDED), allocations[], checker_reasons[], fixer_changes[], fixer_attempt_count, last_plan_hash, last_checker_reason, plan_hash, execution_source (CODE_EXECUTION \| PYTHON_FALLBACK), execution_code, execution_output, impact_breakdown, equity_checker_result, parameters_snapshot, tract_snapshot, created_at, approved_by_role, approved_at, tenant_id` |
| 14 | `match_candidates` | Per candidate per match run: `ticket_id, run_id, recipient_id, name, semantic_rank, semantic_distance, post_filter_rank, status (ELIGIBLE \| FILTERED \| FLAGGED \| TIED), filter_reason, contradiction_flag, evidence {column_value, profile_text_excerpt}, tie_break_values, donor_to_recipient_distance_km, distance_source, need_score, tenant_id`. Authoritative for Match Brief. |
| 15 | `match_briefs` | Per plan version: `ticket_id, plan_id, plan_version, brief_text, outreach_message_draft, guardrail_callout, next_two_options[], maps_attribution_text, disclaimer_text, created_at, tenant_id` |
| 16 | `holds` | Internal lock created by supervisor on approve: `hold_id, ticket_id, plan_id, recipient_id, quantity, quantity_unit, pallets_equivalent, status (ACTIVE \| CONFIRMED \| EXPIRED \| RELEASED), started_at, expires_at, confirmed_at, request_id, tenant_id` |
| 17 | `allocations` | Confirmed assignment + fairness-ledger record derived from holds: `allocation_id, hold_id, recipient_id, ticket_id, plan_id, quantity, quantity_unit, pallets_equivalent, status (CONFIRMED \| DECLINED \| NO_SHOW \| EXPIRED \| COMPLETED), allocated_at, confirmed_at, completed_at, tract_geo_id, need_score_at_allocation, tenant_id` |
| 18 | `tasks` | `task_id, ticket_id, plan_id, task_type (APPROVE_PLAN \| CONFIRM_PICKUP \| UPDATE_PROFILE \| CHECK_CONTRADICTION \| VERIFY_CAPACITY \| SETUP_PICKUP), owner_role, status (OPEN \| APPROVED \| DECLINED \| ASSIGNED), created_at, tenant_id` |
| 19 | `approvals` | Separate idempotent collection: `approval_id, target_type (task \| plan \| hold \| onboarding), target_id, action_id, decision, approver_role, approved_at, plan_version, request_id, tenant_id`. Keyed by `(request_id, target_id)`. |

### D. Firestore Live — People, Safety, Audit (7 Collections)

| # | Collection | Key Fields & Contract Rules |
|---|---|---|
| 20 | `conversations` | `session_id, ticket_id, role, messages[], context {ticket_id, plan_version, step, hold_status}, tool_calls[], action_cards[], approvals[], model_version, prompt_version, scrub_status (SCRUBBED \| REJECTED_ON_MATCH), tenant_id` |
| 21 | `recall_checks` | `check_id, ticket_id, product_text, fda_query, verdict (CLEAR \| HALTED \| NOT_CHECKED), recall_id, checked_at, source (LIVE_OPENFDA \| OFFLINE_SNAPSHOT), tenant_id` |
| 22 | `notifications` | `notification_id, recipient_role, recipient_org_id, ticket_id, event (OFFER_MADE \| DECLINE \| REPLAN \| CANCEL \| HOLD_EXPIRED \| CONFIRMED \| COMPLETED), message, created_at, read_status, tenant_id` |
| 23 | `audit_log` | Live append-only: `audit_id, ticket_id, plan_version, event_type, actor_role, action, timestamp, request_id, tenant_id` |
| 24 | `telemetry_events` | Aggregate-only sink: `event_id, request_id, tool_or_endpoint, latency_ms, status, created_at, tenant_id`. Never stores bodies, addresses, names, or transcripts. |
| 25 | `distance_pairs` | Pair-keyed Firestore cache: `pair_key (hash of donor pickup + recipient ref), distance_km, drive_time_minutes, source (GOOGLE_ROUTES \| HAVERSINE_FALLBACK), cached_at, expires_at (max 30 days), tenant_id` |
| 26 | `users_roles` | `user_id, role (COORDINATOR \| DONOR \| RECIPIENT), org_id, tenant_id`. Demo-only role mapping. |

### E. BigQuery History Sinks in `rescueguard_app` (3)

| # | Table | Contract Rules |
|---|---|---|
| 27 | `rescueguard_app.audit_history` | Post-run sink of Firestore `audit_log`. Live = Firestore; finished run history = BigQuery. |
| 28 | `rescueguard_app.impact_snapshots` | One row per approved plan sunk from `plans.impact_breakdown`. Live source is the plan document. |
| 29 | `rescueguard_app.equity_audit_results` | One row per equity audit sunk from `plans.equity_checker_result`. Live Checker never reads this table. |

**Total Contract Stores: 4 + 6 + 9 + 7 + 3 = 29.**

---

## 4. API Endpoints Contract — 52 Total, Locked

Every endpoint accepts `X-Role`, `X-Tenant`, and `X-Request-Id` headers, echoes `request_id` and header-derived `tenant_id`, and is backed by explicit Pydantic models in `schemas/api.py`.

### Group 1: Health, Identity, Starter Reads (7)

| # | Method | Path | Request Model | Response Model |
|---|---|---|---|---|
| 1 | `GET` | `/api/health` | `HealthQuery` (headers/none) | `HealthResponse` |
| 2 | `GET` | `/api/me` | `MeQuery` (headers) | `MeResponse` |
| 3 | `GET` | `/api/starter-postings` | `PaginationQuery` | `StarterPostingListResponse` |
| 4 | `GET` | `/api/shelf-life/{product}` | `ShelfLifeLookupPath` | `ShelfLifeLookupResponse` |
| 5 | `GET` | `/api/tracts/{geo_id}` | `TractLookupPath` | `TractLookupResponse` |
| 6 | `GET` | `/api/recipients` | `RecipientListQuery` | `RecipientListResponse` |
| 7 | `GET` | `/api/recipients/{recipient_id}` | `RecipientDetailPath` | `RecipientDetailResponse` |

### Group 2: Postings, Tickets, Matching, Plans (14)

| # | Method | Path | Request Model | Response Model |
|---|---|---|---|---|
| 8 | `POST` | `/api/postings` | `CreatePostingRequest` | `PostingResponse` |
| 9 | `GET` | `/api/postings` | `PaginationQuery` | `PostingListResponse` |
| 10 | `GET` | `/api/postings/{posting_id}` | `PostingPath` | `PostingResponse` |
| 11 | `POST` | `/api/tickets` | `CreateTicketRequest` | `TicketResponse` |
| 12 | `GET` | `/api/tickets` | `PaginationQuery` | `TicketListResponse` |
| 13 | `GET` | `/api/tickets/{ticket_id}` | `TicketPath` | `TicketResponse` |
| 14 | `POST` | `/api/tickets/{ticket_id}/match` | `RunTicketMatchRequest` | `PlanResponse` |
| 15 | `GET` | `/api/tickets/{ticket_id}/parameters` | `TicketPath` | `TicketParametersResponse` |
| 16 | `POST` | `/api/tickets/{ticket_id}/parameters` | `UpdateTicketParametersRequest` | `TicketParametersResponse` |
| 17 | `POST` | `/api/tickets/{ticket_id}/cancel` | `CancelTicketRequest` | `TicketResponse` |
| 18 | `GET` | `/api/tickets/{ticket_id}/plans` | `TicketPath` | `PlanListResponse` |
| 19 | `GET` | `/api/plans/{plan_id}` | `PlanPath` | `PlanResponse` |
| 20 | `POST` | `/api/plans/{plan_id}/approve` | `ApprovePlanRequest` | `PlanApprovalResponse` |
| 21 | `POST` | `/api/plans/{plan_id}/reject` | `RejectPlanRequest` | `PlanResponse` |

### Group 3: Holds, Allocations, Completion (8)

| # | Method | Path | Request Model | Response Model |
|---|---|---|---|---|
| 22 | `GET` | `/api/tickets/{ticket_id}/holds` | `TicketPath` | `HoldListResponse` |
| 23 | `GET` | `/api/holds/{hold_id}` | `HoldPath` | `HoldResponse` |
| 24 | `POST` | `/api/holds/{hold_id}/confirm` | `ConfirmHoldRequest` | `HoldResponse` |
| 25 | `POST` | `/api/holds/{hold_id}/release` | `ReleaseHoldRequest` | `HoldResponse` |
| 26 | `POST` | `/api/tickets/{ticket_id}/decline` | `DeclineAllocationRequest` | `PlanResponse` |
| 27 | `POST` | `/api/allocations/{allocation_id}/complete` | `CompleteAllocationRequest` | `AllocationResponse` |
| 28 | `POST` | `/api/allocations/{allocation_id}/no-show` | `NoShowAllocationRequest` | `AllocationResponse` |
| 29 | `GET` | `/api/allocations` | `PaginationQuery` | `AllocationListResponse` |

### Group 4: Recipients, Onboarding, Profile Updates (3)

| # | Method | Path | Request Model | Response Model |
|---|---|---|---|---|
| 30 | `POST` | `/api/recipients/search` | `RecipientSemanticSearchRequest` | `RecipientSemanticSearchResponse` |
| 31 | `POST` | `/api/recipients` | `OnboardRecipientRequest` | `OnboardRecipientResponse` |
| 32 | `PATCH` | `/api/recipients/{recipient_id}` | `PatchRecipientRequest` | `RecipientDetailResponse` |

### Group 5: Tasks, Actions, Guide Chat (7)

| # | Method | Path | Request Model | Response Model |
|---|---|---|---|---|
| 33 | `POST` | `/api/tasks` | `CreateTaskRequest` | `TaskResponse` |
| 34 | `GET` | `/api/tasks` | `PaginationQuery` | `TaskListResponse` |
| 35 | `GET` | `/api/tasks/{task_id}` | `TaskPath` | `TaskResponse` |
| 36 | `PATCH` | `/api/tasks/{task_id}` | `PatchTaskRequest` | `TaskResponse` |
| 37 | `POST` | `/api/actions/approve` | `ApproveActionRequest` | `ActionApprovalResponse` |
| 38 | `POST` | `/api/assistant/chat` | `AssistantChatRequest` | `AssistantChatResponse` |
| 39 | `GET` | `/api/conversations/{session_id}` | `ConversationPath` | `ConversationResponse` |

### Group 6: Impact, Equity, Deserts, Safety, Last-Mile (9)

| # | Method | Path | Request Model | Response Model |
|---|---|---|---|---|
| 40 | `GET` | `/api/tickets/{ticket_id}/impact` | `TicketPath` | `TicketImpactResponse` |
| 41 | `GET` | `/api/impact/dashboard` | `PaginationQuery` | `ImpactDashboardResponse` |
| 42 | `POST` | `/api/equity/audit` | `RunEquityAuditRequest` | `EquityAuditResponse` |
| 43 | `GET` | `/api/equity/{ticket_id}` | `TicketPath` | `EquityAuditResponse` |
| 44 | `GET` | `/api/deserts` | `PaginationQuery` | `DesertListResponse` |
| 45 | `GET` | `/api/deserts/{tract_geo_id}` | `DesertPath` | `DesertCellResponse` |
| 46 | `POST` | `/api/recall/check` | `RecallCheckRequest` | `RecallCheckResponse` |
| 47 | `GET` | `/api/tickets/{ticket_id}/recall` | `TicketPath` | `RecallCheckListResponse` |
| 48 | `GET` | `/api/tickets/{ticket_id}/last-mile` | `TicketPath` | `LastMileResponse` |

### Group 7: Maps (Bonus), Audit, Telemetry (4)

| # | Method | Path | Request Model | Response Model |
|---|---|---|---|---|
| 49 | `POST` | `/api/maps/geocode` | `GeocodeRequest` | `GeocodeResponse` |
| 50 | `POST` | `/api/maps/route` | `RouteRequest` | `RouteResponse` |
| 51 | `GET` | `/api/audit/export` | `AuditExportQuery` | `AuditExportResponse` |
| 52 | `GET` | `/api/telemetry` | `TelemetryQuery` | `TelemetryResponse` |

**Total Contract Endpoints: 7 + 14 + 8 + 3 + 7 + 9 + 4 = 52.**

---

## 5. Enums & HTTP Error Codes Contract

### Locked Enums (`schemas/enums.py`)
- **`TriStateStatus`**: `YES`, `NO`, `UNRECORDED`
- **`Role`**: `COORDINATOR`, `DONOR`, `RECIPIENT`
- **`AddressType`**: `ORG_DOCK`, `RESIDENTIAL`, `UNKNOWN`
- **`QuantityUnit`**: `PALLETS`, `CRATES`
- **`PostingSource`**: `STARTER`, `LIVE_DONOR`
- **`ShelfLifeSource`**: `FOODKEEPER`, `DONOR_FALLBACK`, `NOT_APPLICABLE`
- **`TicketStep`**: `POSTED`, `MATCHED`, `CHECKED`, `APPROVED`, `HELD`, `CONFIRMED`, `COMPLETED`, `DECLINED`, `RE_PLANNED`, `CANCELLED`, `EXPIRED`, `FDA_HALTED`, `SPLIT_REQUIRED`
- **`TicketStatus`**: `ACTIVE`, `RESUMABLE`, `INTERRUPTED`, `COMPLETED`, `CANCELLED`, `FDA_HALTED`
- **`PlanStatus`**: `DRAFT`, `CHECKER_REJECTED`, `APPROVED`, `SUPERSEDED`
- **`CandidateStatus`**: `ELIGIBLE`, `FILTERED`, `FLAGGED`, `TIED`
- **`HoldStatus`**: `ACTIVE`, `CONFIRMED`, `EXPIRED`, `RELEASED`
- **`AllocationStatus`**: `CONFIRMED`, `DECLINED`, `NO_SHOW`, `EXPIRED`, `COMPLETED`
- **`TaskType`**: `APPROVE_PLAN`, `CONFIRM_PICKUP`, `UPDATE_PROFILE`, `CHECK_CONTRADICTION`, `VERIFY_CAPACITY`, `SETUP_PICKUP`
- **`TaskStatus`**: `OPEN`, `APPROVED`, `DECLINED`, `ASSIGNED`
- **`ActionTargetType`**: `task`, `plan`, `hold`, `onboarding`
- **`VerificationStatus`**: `PENDING`, `VERIFIED`, `DEMO_SIMULATED`
- **`OverrideStatus`**: `PENDING`, `VERIFIED`, `APPROVED`
- **`RecallVerdict`**: `CLEAR`, `HALTED`, `NOT_CHECKED`
- **`EquityVerdict`**: `PASS`, `WARN`
- **`ExecutionSource`**: `CODE_EXECUTION`, `PYTHON_FALLBACK`
- **`DistanceSource`**: `GOOGLE_ROUTES`, `HAVERSINE_FALLBACK`
- **`TractStatus`**: `FOUND`, `UNKNOWN`
- **`ScrubStatus`**: `SCRUBBED`, `REJECTED_ON_MATCH`
- **`NotificationEvent`**: `OFFER_MADE`, `DECLINE`, `REPLAN`, `CANCEL`, `HOLD_EXPIRED`, `CONFIRMED`, `COMPLETED`

### Locked HTTP Status Codes
- `200 OK` / `201 Created`: Valid request with `request_id` echoed.
- `404 Not Found`: Missing resource **or** cross-role / cross-tenant read (`404, not 403`).
- `409 Conflict`: Duplicate approval or state transition (`request_id + action_id` already decided, or hold already `CONFIRMED`/`EXPIRED`).
- `422 Unprocessable Entity`: Pickup-address validation failure (`ORG_DOCK` / coordinator assertion / residential text pattern), plan not in checker-passed state on approve, or no viable match (returns structured fallback body).

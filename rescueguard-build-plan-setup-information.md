# RescueGuard Build Plan – Part 1: Setup Information

> **Status: DRAFT FOR REVIEW.** This file has the tables and endpoints review fixes applied. It does not lock the contracts until the user accepts it. If anything here conflicts with a starter README in the hackathon repo, stop and report the conflict instead of guessing.

> **Backend first.** This build is backend only until the backend phases are tagged. The frontend exists in this file only as API contracts the backend must satisfy. Do not build UI code from this file.

## The two documents from last time

Last night, for SurgeGuard, we created two documents. RescueGuard uses the same pair:

1. **Part 1 – Setup Information (this file).** What to build, what environment to build it in, what data already exists, the tables and endpoints contracts, the rules that must never be broken, and what "ready to start" means. It does not contain the phase tasks.

2. **Part 2 – Backend Build Plan (separate file, next).** The phase-by-phase build plan that turns this setup into ordered work for Antigravity: one phase per fresh session, with tests, an exit gate, a commit, and a tag per phase.

When the user says "start Phase N", use the setup in this file as already-decided context. Do not re-decide the architecture, data rules, or scope below.

## How to use this file

- Read this whole file before writing any code.
- Before coding, complete the setup checklist at the end and report each item as verified, missing, or blocked — with the actual output (project ID from config, dataset, row counts), not just "done".
- Never hardcode a GCP project ID, an API key, a token, or a password into code or commits. All such values come from environment variables or Google Cloud Application Default Credentials (ADC). The project ID recorded in this file is a build record, not a code value.
- Do not invent table names, endpoint names, or field names mid-build. If a contract below is missing something a phase needs, stop, note it as a contract change, and get it reviewed before building on it.

## What RescueGuard is

ATL RescueGuard is a self-correcting food dispatcher for the Agents for Impact Hackathon — Atlanta, Tuesday Oct 27, 2026, Coca‑Cola Roxy. It owns a dispatch ticket from posting to hold, checks its own work, splits loads that do not fit, and re-plans when someone says no.

It is a **ticket system, not a search box**. It is not a ranked list of pantries, and it is not a chatbot that just reads data back. The agent does work — matching, constraint checking, planning, checking its own plan, drafting the brief — and a human approves consequential actions before they execute.

### Challenge and track

- **Challenge 2 — Resilient Food Equity & Surplus Broker.**
- **Primary track: Track 1 — Retail & grocer rescue.** Small, perishable, clock-ticking offers. Name this track early in the deck; judges score against the track chosen.
- **Supporting modes on the same system:** Track 2 — Farm surplus (large loads split across pantries) and Track 3 — Critical essentials (formula, diapers). These are not three separate products. The starter allows combining tracks.

Judging, from the starter READMEs: Impact & insight 30, Technical execution 30, Rigor & judgment 25, Craft & communication 15, Bonus for range +10 on top of 100 (max 110).

### Three personas, one ticket

- **Coordinator / dispatcher — the main user, internal staff.** Runs the desk, sees all postings, matches, checker reasons, impact and fairness, and approves plans. Approving a plan starts a hold; it does not send trucks, emails, or dispatches.
- **Donor — supplies the food.** Posts an offer with pickup address and deadline, and tracks only its own offers.
- **Recipient pantry — receives the food.** Sees only offers made to it, confirms or declines in one tap, and can propose updates to its own storage and capacity.

People who need food do not log in and are never users of this system. They benefit indirectly, through their local pantry. The system never collects their names, addresses, or health details, and there is no end-beneficiary table.

### The core flow

Posting → Match → Check (reject and fix if needed) → Human approve → 10-minute hold → Recipient confirm or decline → Pickup complete, or re-plan to a new plan version. Every step is recorded on the same ticket, and chat and screens read from that same ticket state.

## Non-negotiable rules

These rules override any shortcut, model suggestion, or starter code pattern.

1. **Honest unknowns.** Unrecorded is not no, not-checked is not clear, and a blank shelf-life value is never a silent zero. Capability, storage, and recall statuses use YES / NO / UNRECORDED, and a failed recall check is NOT_CHECKED, never CLEAR.
2. **Columns beat text.** When a recipient's structured columns and its profile text disagree, the column wins for filtering and the row is flagged for a human check. Never guess which sentence in a contradictory profile is true.
3. **Meaning is not capacity.** Vector search finds candidates only. Hard constraints — cold and frozen storage, capacity, pickup window, service day, dietary and cultural hard constraints — decide who is viable, deterministically.
4. **Deterministic maths.** Margins, splits, need scores, tie-breaks, and impact scores are calculated in code, with the calculation stored. The model explains; it does not invent numbers.
5. **Human-in-the-loop is a gate, not a label.** No plan is approved, no hold starts, and nothing is dispatched without a human approval record. No auto-approve, and no approval on silence. A chat "yes" is a proposal only, until the approval call succeeds.
6. **Every plan change is a new version.** Never overwrite a plan. Keep v1, the checker rejection and its reasons, the fixer change, and v2 and later, for audit and replay.
7. **Loop guards.** The checker/fixer loop runs at most 3 attempts, detects the same plan hash and the same rejection reason, makes no external calls inside the loop, and escalates to a human instead of looping again.
8. **Need is area-level, never a moral score.** Need comes from tract poverty, no-vehicle, and assistance rates. Fit comes first, need second, fairness over time third. Race is never used — the tract table has no race columns. Reported recipient income is not a ranking input.
9. **Guardrail transparency.** Every Match Brief includes a "Safety & Capacity Guardrails: Why Top Semantic Matches Were Filtered" callout, generated from stored candidate data: semantic rank before filtering, rank after, drop reason, contradiction flag, and tie-break numbers.
10. **Numbers and distances are labelled honestly.** Households reached are estimated, never summed across overlapping groups as unique people. Distances from ZIP centroids are ZIP-area approximate, never exact door-to-door road time.

## GCP setup — do this first

### Project

- **Event GCP project ID: `<event-project-from-config>` (`$GOOGLE_CLOUD_PROJECT`)** — recorded in `docs/handoffs/` as a build record for today's event project. Code must read the project from `GOOGLE_CLOUD_PROJECT` / `gcloud config` at runtime and must work in a different project by changing environment variables only. Never hardcode this ID in code, schemas, or examples.
- The developer is Reyan Adil. Team members work in the same shared event project; there is not one project per teammate.
- Billing and API enablement must be verified in this project, not assumed from any earlier project.

### Authenticate and verify

```bash
gcloud --version
gcloud config set project "$GOOGLE_CLOUD_PROJECT"
gcloud config get-value project        # must print the event project ID above
gcloud auth application-default login  # ADC — how local code calls BigQuery / Vertex
gcloud services list --enabled --project "$GOOGLE_CLOUD_PROJECT"
```

Backend code authenticates with ADC or the Cloud Run service account. Never put a service-account JSON key in the repo, in `.env`, or in chat.

### APIs to verify

Verify each of these is enabled in the event project before coding, and record the actual enabled list in the Phase 0 handoff. Do not assume an API is available because console search did or did not find it; check by service name.

- Vertex AI API (`aiplatform.googleapis.com`) — the agent calls models through Vertex AI / ADK, not a standalone Gemini API key.
- BigQuery (`bigquery.googleapis.com`), including the managed BigQuery MCP endpoint `https://bigquery.googleapis.com/mcp` for guarded, read-only, one-off data questions only.
- Firestore (`firestore.googleapis.com`), Cloud Run (`run.googleapis.com`).
- Maps Geocoding and Routes — bonus phase only. Check whether they are enabled; if they are not, the build falls back to ZIP-area distance and says so. A Maps failure never blocks a match.

### Environment variables

Create a `.env` file locally (never committed) and an equivalent configuration on Cloud Run. A committed `.env.example` lists names with placeholder values only.

| Variable | Meaning |
|---|---|
| `GOOGLE_CLOUD_PROJECT` | Target GCP project ID, read at runtime |
| `GOOGLE_CLOUD_LOCATION` | Vertex / Cloud Run region; BigQuery starter dataset location is US |
| `GOOGLE_GENAI_USE_VERTEXAI` | Route ADK model calls through Vertex AI: `TRUE` |
| `BQ_DATASET_STARTER` | Starter dataset: `a4i_food` |
| `BQ_DATASET_APP` | App history dataset: `rescueguard_app` |
| `MODEL_ID` | Model ID; record the exact version in every run |
| `CHECKER_MAX_ATTEMPTS` | Checker / fixer loop cap: `3` |
| `HOLD_MINUTES` | Hold length: `10` |

An empty `.env` file (0 bytes) breaks agent loading silently. Always check the file has real content, and never print secrets from it into logs, chat, or commits.

## GitHub repo and periodic pushes

- **Repo to clone: https://github.com/mattchainsaw/ai_for_impact_atl_2**
- Clone it once, work inside that clone, and treat it as the shared team repo. Do not fork a Toronto team's repo as the base, and do not build in a separate private copy that the team cannot see.

```bash
git clone https://github.com/mattchainsaw/ai_for_impact_atl_2
cd ai_for_impact_atl_2
git status   # must be clean before the first change
```

### Push cadence — periodic, not at the end

- Work in short-lived branches per lane or per phase, and merge to the main branch only when a lane has something other lanes need.
- **After each phase passes its exit gate: commit, tag `phase-<n>`, and push both the branch/commits and the tag to origin.** A phase that exists only on one laptop is not done.
- Also push at any natural stopping point during a long phase (a passing test run, a finished contract file), so work is never more than one working session away from the remote.
- Commit messages name the phase and the contract area touched, for example `phase-2: matcher constraint filter + match_candidates`.
- Never force-push shared branches. Never commit `.env`, credentials, service-account keys, or personal contact data. Run a secret grep before every push.
- The Phase 0 handoff records: clone path, current branch, last pushed commit, and last tag. Later handoffs update the last pushed commit and tag each time.

## Architecture — supervisor, specialists, and shared state

RescueGuard is a separate backend and frontend. The frontend never calls BigQuery, Maps, or Vertex directly. The backend owns the supervisor, all specialists, all data access, and the human-approval gate.

```text
Frontend (coordinator desk + donor view + recipient view + floating Guide)
        |  HTTP / JSON only, via the API contracts below
Backend (Cloud Run, stateless — FastAPI owns everything)
        |
   Supervisor — owns ticket, plan versions, routing, veto, escalation, holds
        |
   Specialists: Matcher · Constraint + Last-Mile · Recall Guard ·
                Planner / Splitter · Checker / Auditor · Fixer ·
                Impact & Fairness · Guide (ADK, chat only) · Onboarding (bonus)
        |
   BigQuery (starter, read-only + app history) · Firestore (live ticket state)
   openFDA (recall) · Maps Geocoding / Routes (bonus, with fallback)
```

- **FastAPI owns everything.** The supervisor is a plain FastAPI orchestrator. Specialists are Python tools behind it. ADK is used only for the Guide chat agent, which calls the supervisor API and never calls specialists directly.
- **One state, no second truth.** Supervisor state for a ticket lives in Firestore and is the single source of truth for screens and chat. There is never a chat plan and a separate screen plan.
- **Persona filtering is enforced in the backend**, on every query, by tenant (metro + organisation) and role. Cross-role and cross-tenant reads return 404, not 403, so existence is not leaked. Demo role/tenant headers are recorded, demo-only, and not authenticated — never claim spoof-resistant enforcement in the deck.

## BigQuery starter data — already ported, verify in place

The user has **already ported the original starter tables into BigQuery** in the event project. Do not reload them blindly. Phase 0 verifies what is there — dataset, tables, row counts, field types — and reports any mismatch before any app table is created.

- **Starter dataset:** `a4i_food`, location US.
- **Starter tables are read-only.** Never `UPDATE` or `DELETE` an existing starter row. Onboarding and profile changes never write into these tables — they write to the app-owned stores in the tables contract below, and a combined view presents starter and app recipients together.

| Table | Expected content | Verify in Phase 0 |
|---|---|---|
| `recipients` | Real IRS identities, generated operations; about 135 Atlanta rows including 9 planted | Row count; `recipient_id` type; `service_days` format; distinct `cold_storage` values; planted rows by `profile_source = 'planted'` |
| `surplus_postings` | 10 synthetic postings across Retail / Farm / Essentials | Row count; which rows have NULL `shelf_life_hours` |
| `shelf_life` | 661 USDA FoodKeeper rows | Row count; confirm there is no product named exactly "Spinach" |
| `tract_demographics` | ACS tract data: poverty, no-vehicle, assistance, income; no race columns | Row count; `geo_id` type and leading-zero handling |

### Traps in the starter data — handle all of them

1. **Planted teaching cases.** Rows with `profile_source = 'planted'` are invented, adversarial cases: a near-miss decoy that ranks first on meaning but has no cold storage, a self-contradictory profile, genuine operational ties, and vocabulary-mismatch rows a keyword search would miss. Query the actual Atlanta planted rows in Phase 0 and record their real names and values. Do not put planted names from another city into the Atlanta deck or demo until that query confirms them, and label planted cases as starter teaching cases, not real pantries' actual fridge status.
2. **NULL shelf life is a rule, not a zero.** Diapers are not food, milk defers to its package use-by date, and sealed formula is tracked only after opening. In those cases the resolved clock falls back to the donor window, and the source of the resolved value is recorded.
3. **"Spinach" is a subtitle, not a product name.** It sits under "Lettuce" in FoodKeeper. Use the conservative end of a range, and remember the donor deadline always beats the book.
4. **Coordinates are ZIP centroids.** Recipient latitude/longitude is the centre of a ZIP area, not a building pin. Distances from it are approximate by construction.
5. **Addresses are organisation addresses only.** Recipient street/city/state/ZIP is a public IRS organisation address. The starter deliberately dropped personal contact columns; never reintroduce personal names, phones, or emails.
6. **Tract join is not given.** Recipients carry no tract ID. The join is nearest tract by distance to the ZIP centroid, with a left join so a missing tract becomes UNKNOWN and falls back to weekly households — never a silent zero, and never a dropped pantry.

## Tables contract — review fixes applied

This is the corrected list. The earlier draft counts were wrong and several core features had no stored home; the fixes below are part of the contract, not optional notes. Count rule: tasks and approvals are two collections; the optional Maps cache is not counted.

### A. Starter tables in BigQuery, dataset `a4i_food` — read-only (4)

| Table | Key fields and notes |
|---|---|
| `recipients` | `recipient_id`, `ein`, `name`, street/city/state/`zip_code`, `cold_storage`, `frozen_storage`, `loading_dock`, `refrigerated_transport`, `max_pallets`, `pickup_window_hours`, `weekly_households`, `populations_served`, `service_days`, `profile_text`, `profile_source`, `latitude`, `longitude` |
| `surplus_postings` | `posting_id`, `track`, `posting_text`, `foodkeeper_product`, `storage_state`, `hours_available`, nullable `shelf_life_hours`, `hours_remaining`. No donor name or address exists here |
| `shelf_life` | `product_id`, `product_name`, `product_subtitle`, `keywords`, `category`, `refrigerated_hours`, `refrigerated_note`, `pantry_hours`, `pantry_note` |
| `tract_demographics` | `geo_id`, `tract_lat`, `tract_lon`, `total_pop`, `median_income`, `poverty_rate`, `no_vehicle_rate`, `assistance_rate` |

### B. Team-created tables and views in BigQuery (3 tables, 3 views)

| Table / view | Purpose and key rules |
|---|---|
| `recipient_embeddings` | `recipient_id`, source profile text, `embedding` (gemini-embedding-2, 3,072 dimensions), `embedded_status`. No vector index; brute-force vector search. Connection region must match dataset region US |
| `app_recipients` | App-owned onboarded pantries only. Starter `recipients` is never inserted into. Carries `verification_status` (PENDING / VERIFIED / DEMO_SIMULATED); a PENDING pantry is not eligible for fresh or frozen matches |
| `recipient_overrides` | App-owned profile changes: recipient reference, changed fields, status (PENDING / VERIFIED / APPROVED), effective date, approver role. Starter rows are never updated in place, and history is kept |
| `v_all_recipients` | View presenting starter recipients plus verified app recipients together, with effective cold/capacity values after approved overrides. All matching reads through this view |
| `v_recipient_tract` and `v_rescue_deserts` | Recipient-to-nearest-tract view (with `tract_status` FOUND / UNKNOWN) and desert view (poverty > 0.30, no-vehicle > 0.40, zero cold recipients within 5 km, using the verified `cold_storage` value domain). Views are live; approved plans snapshot the tract values they used, so a plan can be replayed after onboarding changes the view |

### C. Live state in Firestore — tickets, plans, holds (9 collections)

Firestore (Native mode) is the live store. BigQuery is never used as a lock or live state store.

| Collection | Key fields and notes |
|---|---|
| `postings` | Live donor offers only, distinct from starter postings: donor org, pickup address (organisation/dock address, never a home address), pickup ZIP, quantity with explicit unit, `split_allowed`, delivery/transport flags, dietary flags, donor deadline, status |
| `tickets` | One per dispatch job: `posting_source` (STARTER / LIVE_DONOR) plus posting reference, step, `current_plan_id`, parameters (top_n, weights, split allowed), checkpoint fields (current step, holds already started, tasks already approved, status ACTIVE / RESUMABLE / INTERRUPTED), resolved clock (below) |
| `plans` | Append-only, one per version: status (DRAFT / CHECKER_REJECTED / APPROVED / SUPERSEDED), allocations, checker reasons, fixer changes, `fixer_attempt_count`, `last_plan_hash`, `last_checker_reason`, plan hash, impact breakdown, snapshotted tract values at approval |
| `match_candidates` | One row per candidate per match run: recipient, semantic rank and distance before filtering, status (ELIGIBLE / FILTERED / FLAGGED / TIED), filter reason, evidence (column value vs profile text), tie-break values, donor-to-recipient distance and its source. This is the stored source of the Guardrails callout |
| `match_briefs` | One per approved plan version: brief text, outreach message draft, guardrails callout, next two options, Maps attribution text where a Maps link is shown. The Brief is a stored artifact, not a re-rendering guess |
| `holds` | Internal only — created by the supervisor inside approve, never by a public client call: recipient, quantity held, status (ACTIVE / CONFIRMED / EXPIRED / RELEASED), start and expiry, idempotency `request_id`. A hold is the lock |
| `allocations` | The confirmed assignment record, derived from holds: recipient, ticket, plan, quantity, status (CONFIRMED / DECLINED / NO_SHOW / EXPIRED), dates, tract and need score at allocation. This is the fairness ledger source |
| `tasks` and `approvals` | Two collections. Tasks: type (APPROVE_PLAN / CONFIRM_PICKUP / UPDATE_PROFILE / CHECK_CONTRADICTION, plus coordinator-created gap tasks), owner role, status. Approvals: decision, approver role, date, plan version, and idempotency `request_id` on every record — a repeated approval with the same request ID must not double-assign |

### D. Live state in Firestore — people, safety, audit (6 collections, plus `users_roles` below)

| Collection | Key fields and notes |
|---|---|
| `conversations` | Per session: role, messages in order, ticket context at each message, tool calls, action cards, approvals with role, model and prompt versions, and a scrub status field so scrubbed records are distinguishable in audit. Personal phone/email in chat is redacted; recipient conversations are anonymised after confirmation |
| `recall_checks` | Product text, FDA query, verdict (CLEAR / HALTED / NOT_CHECKED), recall ID if any, date, source (live openFDA or labelled offline snapshot). Recall matching is by product text, not a structured product ID; respect the API call limit recorded in the handoff |
| `notifications` | Persona inbox and status log: recipient of the notification, role, ticket, event (offer made, decline, re-plan, cancel, hold expiry), date, read status. Donor and recipient views read from here, not by re-deriving state from tickets |
| `audit_log` | Live, append-only event log in Firestore: ticket, plan version, event, actor role, action, timestamp, request ID. This is the live source the audit export reads |
| `telemetry_events` | Aggregate-only metrics: request ID, tool/endpoint, latency, status. Never bodies, addresses, names, or transcripts |
| `distance_pairs` | Pair-keyed distance cache (donor pickup to recipient), in Firestore, not BigQuery: pair key, distance, drive time if any, source (GOOGLE_ROUTES / HAVERSINE_FALLBACK), cached at, run-scoped expiry (max 30 days). Never store Maps phone, text, or photos |

Plus `users_roles`: user, role (coordinator / donor / recipient), organisation, tenant. Demo-only role mapping with a retention/deletion rule for the Google account identifier; org name and address live on postings and recipients, not duplicated here.

### E. History in BigQuery, dataset `rescueguard_app` — sinks, not live sources (3)

| Table | Notes |
|---|---|
| `audit_history` | Post-run sink of the Firestore `audit_log`. Live audit is Firestore; this table is history only |
| `impact_snapshots` | One row per approved plan, sunk from `plans`. The plan's stored impact breakdown is authoritative live; this table must not drift from it |
| `equity_audit_results` | One row per equity audit, sunk from the Checker result stored on the plan. The live Checker check happens before approval and never reads this table |

### F. Resolved clock and units — two contract rules

- **Resolved clock.** Tickets carry one resolved clock, not three competing ones: `resolved_deadline`, `resolved_shelf_life_hours`, and `shelf_life_source` (FOODKEEPER / DONOR_FALLBACK / NOT_APPLICABLE). Margin is always hours left on the resolved clock, minus pickup window, minus travel buffer.
- **Units.** Starter capacity is in pallets (`max_pallets`); donor quantities may be stated in crates. Phase 0 must define and record the crates-per-pallet conversion used for capacity checks, or require donor quantities in pallets. No planner code is written until this rule is recorded — a builder must not invent a conversion.

### G. Tables we do not create

No AlloyDB, Spanner, or Cloud SQL. No live driver-fleet table in core (last-mile is self-collect vs needs-driver, from starter fields). No end-beneficiary table, and no personal contacts table.

## API endpoints contract — review fixes applied

### Contract rules for every endpoint

- Every request carries a `request_id`; every response echoes it. Every consequential POST body includes `request_id`, and approvals are idempotent by that ID.
- Every fact carries a source label. Statuses use YES / NO / UNRECORDED.
- Already-decided or already-approved returns 409. A plan that is not in a checker-passed state returns 422 on approve — approve itself creates the approval record, so no prior approval record is ever required.
- No viable match returns 422 with a structured fallback body (why no one fits, nearest option and why not, coordinator contact path). Never return an empty plan or a guessed pantry. The match endpoint restates this rule explicitly.
- Cross-role and cross-tenant reads return 404, not 403.
- **Canonical approval path:** `POST /api/actions/approve` is the single entry for chat-initiated approvals. The plan-approve and task endpoints delegate to the same idempotent approval service, keyed by `request_id` and action ID. One approval flips exactly one target.
- **Holds are internal.** There is no public endpoint to create or expire a hold. Holds are created by the supervisor inside approve, and expiry is a system transition. Public hold transitions are confirm and release only, with role and ownership checks.
- Maps endpoints are top-matches only, fall back to straight-line ZIP distance labelled as estimated, and never claim exact door-to-door time from ZIP centroids.

### Health, identity, and starter reads

```text
GET  /api/health
GET  /api/me                          -> { role, org_id, tenant_id }  # demo-only; switching role re-filters all later reads in the backend
GET  /api/starter-postings            # the 10 starter offers, read-only
GET  /api/shelf-life/{product}        # FoodKeeper lookup, for UI and Guide
GET  /api/tracts/{geo_id}             # tract need values, for UI and Guide
GET  /api/recipients                  # role-filtered, through v_all_recipients
GET  /api/recipients/{recipient_id}
```

### Postings, tickets, matching, and plans

```text
POST /api/postings                    # donor / coordinator creates a live posting
GET  /api/postings                    # role-filtered, sorted by expiry
GET  /api/postings/{posting_id}
POST /api/tickets                     # body: { posting_id, posting_source: "STARTER" | "LIVE_DONOR" }
GET  /api/tickets                     # role-filtered, sorted by expiry
GET  /api/tickets/{ticket_id}         # canonical ticket state AND the resume endpoint: returns checkpoint status and resumes without re-running Maps or re-approving tasks
POST /api/tickets/{ticket_id}/match   # Matcher -> Constraint -> Planner -> Checker -> Fixer (max 3); 422 fallback if no viable recipient
GET  /api/tickets/{ticket_id}/parameters
POST /api/tickets/{ticket_id}/parameters
POST /api/tickets/{ticket_id}/cancel  # donor (own posting) or coordinator: releases all holds internally, notifies recipients, ticket becomes CANCELLED
GET  /api/tickets/{ticket_id}/plans
GET  /api/plans/{plan_id}
POST /api/plans/{plan_id}/approve     # delegates to canonical approval service; on success the supervisor creates holds internally
POST /api/plans/{plan_id}/reject
```

### Holds, allocations, and completion — two separate transitions

Offer-confirm and pickup-complete are different events. Confirming means the pantry accepts the offer; completing means the pickup actually happened.

```text
GET  /api/tickets/{ticket_id}/holds
GET  /api/holds/{hold_id}
POST /api/holds/{hold_id}/confirm            # recipient accepts the offer: hold -> CONFIRMED
POST /api/holds/{hold_id}/release            # role + ownership checked: hold -> RELEASED, capacity freed
POST /api/tickets/{ticket_id}/decline        # body: { recipient_id, allocation_id, reason? }; per-allocation, promotes next pantry, new plan version; 409 if that hold is already CONFIRMED / EXPIRED, 422 if no active hold for that recipient
POST /api/allocations/{allocation_id}/complete  # pickup happened: ticket -> COMPLETED
POST /api/allocations/{allocation_id}/no-show   # records NO_SHOW in the fairness ledger
GET  /api/allocations                        # fairness ledger, role-filtered
```

### Recipients, onboarding, and profile updates

```text
POST /api/recipients/search           # genuine vector search; returns semantic candidates BEFORE constraint filtering, so the Brief can show rank before vs after
POST /api/recipients                  # onboard: writes app_recipients + recipient_embeddings, verification_status PENDING / DEMO_SIMULATED; not eligible for fresh/frozen until VERIFIED. Onboarding alone never auto-approves or auto-holds — after it succeeds, the coordinator (or a Guide action card) calls match again, which creates a new plan version
PATCH /api/recipients/{recipient_id}  # own org only; writes recipient_overrides, never the starter row; re-embeds if profile text changed
```

### Tasks, actions, and Guide chat

```text
POST /api/tasks                       # coordinator-created gap tasks (verify capacity, check contradiction) as well as system-created tasks
GET  /api/tasks
GET  /api/tasks/{task_id}
PATCH /api/tasks/{task_id}            # delegates to canonical approval service
POST /api/actions/approve             # canonical approval entry (see contract rules)
POST /api/assistant/chat              # proposes action cards; never executes; returns answer + state_update
GET  /api/conversations/{session_id}
```

Anonymising or deleting a recipient conversation on request is out of scope for the event API and is handled as an operator data action, recorded in the audit log. It is not silently omitted: the deck and repo must state this limit.

### Impact, equity, deserts, safety, and last-mile

```text
GET  /api/tickets/{ticket_id}/impact  # total + Need / Rescue / Equity / Reliability, v1 vs v2 vs do-nothing, labelled estimated
GET  /api/impact/dashboard
POST /api/equity/audit                # Checker-owned equity check for a plan; result stored on the plan, sunk to BigQuery later
GET  /api/equity/{ticket_id}
GET  /api/deserts
GET  /api/deserts/{tract_geo_id}
POST /api/recall/check                # verdict CLEAR / HALTED / NOT_CHECKED; HALTED blocks that item from matching
GET  /api/tickets/{ticket_id}/recall  # all recall checks for the ticket
GET  /api/tickets/{ticket_id}/last-mile
```

### Maps (bonus), audit, and telemetry

```text
POST /api/maps/geocode                # bonus; fallback to ZIP centroid, labelled fallback
POST /api/maps/route                  # bonus; top matches only; source GOOGLE_ROUTES / HAVERSINE_FALLBACK
GET  /api/audit/export                # live runs read Firestore audit_log; finished runs read BigQuery audit_history
GET  /api/telemetry                   # aggregates computed from telemetry_events and run records, tenant-filtered; never bodies or addresses
```

## Phase order — summary only

The full phase tasks, tests, and exit gates live in Part 2 (Backend Build Plan). The order is fixed; core is Phases 0–6 plus 9–10, and bonus is Phases 7–8 in that order — onboarding before Maps, because onboarding does not depend on Maps API availability.

| Phase | Scope |
|---|---|
| 0 | Setup and contracts: project, repo clone, this file accepted, health endpoint, contract tests |
| 1 | Data: verify starter tables in place, embeddings, tract join, desert view, planted list, unit and clock rules recorded |
| 2 | Matcher, constraint and last-mile basics, recall guard, candidate/guardrail data stored |
| 3 | Planner/splitter, checker/fixer with loop guards, plan versions |
| 4 | Supervisor, ticket, holds, tasks, approvals, Guide chat, persona filtering, resume |
| 5 | Role views contract and the Match Brief, including the Guardrails callout |
| 6 | Impact score, fairness ledger, equity audit, deserts, last-mile panel data |
| 7 | Bonus 1: onboarding and desert flip, with verification gate |
| 8 | Bonus 2: Maps geocoding and routes, with fallback |
| 9 | Observability, audit, deploy, eval suite built from verified Atlanta cases |
| 10 | Deck, video, freeze on the last tagged phase |

If time runs out, demo from the last tagged phase and list unfinished phases as future work. Never cut a feature silently.

## Setup checklist — complete before Phase 1

Report each item as verified, missing, or blocked, with the actual output.

- [ ] Event project set and confirmed: `gcloud config get-value project` prints `<event-project-from-config>`, read from config, not hardcoded in code.
- [ ] ADC works locally; billing confirmed enabled in the event project.
- [ ] Enabled APIs listed from `gcloud services list --enabled` and recorded in the Phase 0 handoff, including whether Maps Geocoding/Routes are enabled.
- [ ] Repo cloned from https://github.com/mattchainsaw/ai_for_impact_atl_2 , working tree clean, push access confirmed with one test push.
- [ ] BigQuery starter dataset `a4i_food` present (already ported by the user): row counts recorded for `recipients`, `surplus_postings`, `shelf_life`, and `tract_demographics`.
- [ ] Field facts recorded, not assumed: `recipient_id` type, `geo_id` type and leading-zero handling, `service_days` format, distinct `cold_storage` values (the desert rule depends on this domain).
- [ ] Planted rows listed from the actual Atlanta table (`profile_source = 'planted'`), with names and values recorded.
- [ ] Crates-to-pallets rule recorded (conversion, or pallets-only donor quantities), and the resolved-clock rule recorded.
- [ ] Firestore database exists in Native mode; no app collections are created before this file is accepted.
- [ ] `.env` exists locally with real content, is not committed, and `.env.example` lists names with placeholders only. Secret grep passes.
- [ ] ADK and Python versions recorded; FastAPI scaffold answers `GET /api/health`.

## Review gate

This file is the first markdown setup file for RescueGuard and is **put on review** as written. The tables and endpoints contracts above already carry the two independent reviews' fixes. What review still has to confirm before Part 2 locks Phase 0:

- The onboarding resolution (app-owned `app_recipients` plus `recipient_overrides`, starter tables untouched) is accepted.
- The count and naming in the tables contract are accepted as corrected, replacing the earlier draft counts.
- The internal-only holds rule and the canonical approval path are accepted.
- Any item in the setup checklist that Phase 0 cannot verify is reported as blocked, not worked around.

# RescueGuard — Backend Build Plan (Part 2)

> **For Antigravity:** This is Part 2 of two. It is **backend only**.
> Build the backend in phases, in order, one phase per fresh session.
> Do not build frontend UI, video, or deck code in Phases 0–9.
> The frontend exists here only as API contracts the backend must satisfy.
> Phase 10 is submission work outside the backend, not backend code.
>
> **Precedence — read first.** This file is the **sole build authority**
> for RescueGuard. Part 1, *RescueGuard Build Plan – Setup Information*,
> is **reference only**. Read Part 1 for context in Phase 0 and Phase 1.
> **If Part 1 and this file conflict, this file wins.** Do not silently
> resolve a conflict: stop, report the conflict in the phase handoff,
> and build to this file. If a starter README in the repo conflicts
> with this file, stop and report that conflict instead of guessing.
>
> After each phase: run its tests, update `CONTEXT.md` and
> `CONTRACTS.md` (see the OKF system), commit, tag `phase-<n>`,
> and push — see the git workflow. Then stop. The user will start a
> new session for the next phase.
>
> **One file, many sessions, not one mega-session.** Do not try to do
> Phases 0–10 in a single session.

## Locked decisions — do not re-decide these

- **Challenge 2, Track 1 primary.** Resilient Food Equity & Surplus
  Broker. Primary track: Track 1 — Retail & grocer rescue. Track 2
  (Farm surplus) and Track 3 (Critical essentials) are supporting
  modes on the same system, not separate products.
- **Backend first, FastAPI owns everything.** The supervisor is a
  plain Python FastAPI orchestrator. Specialists are Python tools
  behind it. ADK is used **only** for the Guide chat agent, which
  calls the supervisor API and never calls specialists directly.
- **ADK v2 graph fallback, only if needed:** if a later phase
  genuinely needs graph orchestration for a subgraph only (for
  example the checker/fixer loop), it may use ADK v2 graph behind
  FastAPI, with state still in Firestore/BigQuery and FastAPI
  ownership unchanged. If a graph is not needed, do not add it.
- **No cuts without user approval.** No feature in this file is
  pre-authorised for cutting. An emergency cut requires the user's
  approval at that moment, is reported in the handoff, and is never
  silent. If time runs out, demo from the last tagged phase and
  list unfinished phases as future work.

- **GCP project is known and recorded in Part 1.** Code must read
  the project from `GOOGLE_CLOUD_PROJECT` / `gcloud config` at
  runtime and must work in a different project by changing env
  only. Never hardcode a project ID in code, schemas, or examples.
  Commands in this file use `$GOOGLE_CLOUD_PROJECT`. Phase handoffs
  under `docs/handoffs/` are build records and **may** record the
  project ID from config, because they are records, not code.
- **Repo is the teammate's repo — clone it and use it.**
  `https://github.com/mattchainsaw/ai_for_impact_atl_2` is the
  team's shared repo for this event (`mattchainsaw` is a teammate).
  Clone that repo, work inside that clone, and push to its `origin`.
  Do **not** apply generic template/fork advice to this build:
  do not create a separate team repo, do not re-point `origin`
  away from that repo, and do not treat it as an organiser repo
  the team cannot push to. First push is a test push on a
  non-`main` test branch on that repo (see Phase 0).
- **Starter data is already ported.** The user already ported the
  original starter tables to BigQuery in the event project.
  Phase 0 checks existence only; Phase 1 verifies counts, types,
  planted rows, and the tract join in place. Do not reload or
  overwrite starter tables blindly.
- **Starter tables are read-only.** Never `UPDATE`/`DELETE` an
  existing starter row. Onboarding writes to app-owned
  `app_recipients`; profile changes write to `recipient_overrides`;
  matching reads through `v_all_recipients`. See Tables.
- **Demo auth, downgraded honestly:** `X-Role` + `X-Tenant` headers
  are recorded, demo-only, **not authenticated**. The server filters
  by the header it was given and tests assert that filtering. This
  does **not** protect against spoofing. Production would need
  server-issued tokens. Never claim spoof-resistant enforcement.
- **Locked totals:** **29** tables/views/collections and **52**
  endpoints, as listed in this file. A builder must not silently
  add a 30th table or a 53rd endpoint. A needed addition is a
  contract change: update `CONTRACTS.md`, note it in the handoff,
  and get it reviewed before building on it.
- **Part 1 must not be pushed as-is (Review fix C2).** Part 1
  still contains a literal project ID in its header, a
  `gcloud config set project` example, and a checklist line.
  **Decision recorded here, overriding Part 1 on this point:**
  do NOT push Part 1 to the teammate repo in its current form.
  If the team wants Part 1 in the repo at all, first redact
  every literal project ID in it to `$GOOGLE_CLOUD_PROJECT` /
  `<event-project-from-config>`, then push the redacted copy.
  The actual ID lives only in local `gcloud config` and in
  uncommitted / handoff build records — never in a pushed file.
  Phase 0 Task 1 must record which choice was made: “Part 1
  not pushed” or “Part 1 redacted, then pushed”.
- **Canonical working copy (Review fix C3).** The canonical
  working copy for Antigravity sessions is a fresh clone of
  the teammate repo **inside the Antigravity / Cloud Shell
  session workspace**, pushed after every phase. Reyan's Mac
  clone is for inspection, local verification, and review
  unless Reyan explicitly says he is pushing from it in that
  session. There is one canonical clone per Antigravity
  session; do not work in two clones in parallel without
  pushing and recording the last pushed commit first. Phase 0
  Task 1 must record: canonical clone path, branch, remote
  URL, and last pushed commit / tag.

## Keep it manageable — enough to win, not a production system

The hard parts are data traps, human-approval enforcement,
versioned plans, and stored guardrail evidence — not complex
algorithms. Most code is: pre-written SQL, deterministic constraint
and split maths, FastAPI endpoints, Firestore writes, one recall
check, and one chat agent. No model training, no fleet system.

**Winning slice — build this well:**
Posting → meaning match → hard-constraint filter with reasons →
deterministic split → checker rejects v1 → fixer v2 → human approve
→ 10-minute hold → recipient confirm/decline → re-plan → Match Brief
with the Guardrails callout, Impact Score, and fairness ledger.

**Thin, demonstrable versions — not full systems:**
Equity audit with real numbers, desert view, onboarding re-match,
Maps geocode/routes with fallback, telemetry and audit export.
Each must be demoable, not polished as a standalone product.

Do not expand scope to meet a test. If a test would require a full
production system, implement the minimal testable version that
satisfies the test and note it as demo-thin in the handoff.

## What RescueGuard is, in one paragraph

ATL RescueGuard is a self-correcting food dispatcher. It owns a
dispatch ticket from posting to hold, checks its own work, splits
loads that do not fit, and re-plans when someone says no. It is a
**ticket system, not a search box**: not a ranked list of pantries,
and not a chatbot that reads data back. The agent does work —
matching, constraint checking, planning, checking its own plan,
drafting the brief — and a human approves consequential actions
before they execute. Approving a plan starts a hold; it does not
send trucks, emails, or dispatches.

Judging, from the starter READMEs: Impact & insight 30, Technical
execution 30, Rigor & judgment 25, Craft & communication 15,
Bonus for range +10 on top of 100 (max 110).

**Three personas, one ticket:**

- **Coordinator/dispatcher — main user, internal staff.** Sees all
  postings, matches, checker reasons, impact and fairness; approves.
- **Donor — supplies food.** Posts an offer with pickup address and
  deadline; tracks only its own offers.
- **Recipient pantry — receives food.** Sees only offers made to
  it; confirms/declines in one tap; proposes updates to its own
  storage/capacity via overrides.

People who need food do not log in, are never users, and are never
collected as data. There is no end-beneficiary table.

---

## How to use this file — read this before any code

1. Work **one phase only** per session. The prompt names the phase,
   for example “start Phase 3”.
2. At session start, read only: this file's section for that phase,
   `CONTEXT.md`, `CONTRACTS.md`, and the previous phase handoff.
   Do not read the whole codebase to “get up to speed”.
   **Exceptions:** Phase 0 and Phase 1 may also read Part 1 and the
   starter schema, because `CONTEXT.md` does not yet contain them.
   After Phase 1, those exceptions close.
3. Do not refactor a previous phase unless its test fails in this
   phase. If a previous phase's public interface must change,
   change `CONTRACTS.md` and the module README first, then code,
   then re-run that phase's tests.
4. At phase end, complete that phase's OKF update before stopping.
   A phase without its OKF update is not done.
5. Never hardcode a GCP project ID, API key, token, or password.
   Read the project from `GOOGLE_CLOUD_PROJECT`. Docs/handoffs may
   record the project ID from config as a build record (see Locked
   decisions); code, schemas, and examples may not contain it.
6. If a starter README, Part 1, or a tool output conflicts with
   this file, stop and report the conflict. Do not guess.

## The OKF system — how the agent does not forget

### Files to create in Phase 0

| File | Purpose | Limit |
|---|---|---|
| `CONTEXT.md` | Living summary: purpose, architecture, decisions, traps, current/next phase | 300 lines max, prune every phase |
| `CONTRACTS.md` | Frozen API list, table list, enums, error codes | No chatty prose |
| `schemas/` | Pydantic models for every API request/response | One model per contract |
| `docs/modules/<name>.md` | Per-module interface: public functions, parameters, returns, side effects, invariants | 1 page per module |
| `.agent/skills/<name>/SKILL.md` | One skill per subsystem: matcher, constraint, planner, checker, supervisor, guide, data, onboarding, maps, impact-fairness, recall, last-mile | Load only the current phase's skill |

### `CONTEXT.md` template — fill it exactly in this shape

```markdown
# CONTEXT — RescueGuard backend
## Purpose (3 lines max)
## Architecture (supervisor + specialists, text diagram)
## APIs (name + signature only, full detail in CONTRACTS.md)
## Tables (name + key columns only — 29 total)
## Enums (YES/NO/UNRECORDED, plan/hold/allocation statuses, verdicts)
## Non-negotiable rules (the 10 rules in this file)
## Traps (planted, NULL shelf-life, Spinach-under-Lettuce, ZIP centroid, tract join)
## Decisions log (date — decision — why, newest last, keep last 30)
## Current phase / Last test result / Next phase
```

### Rules that apply in every phase

- Start: read `CONTEXT.md`, `CONTRACTS.md`, this phase's skill,
  and the last handoff only (plus the Phase 0/1 exceptions).
- End: update `CONTEXT.md` (prune under 300 lines), update the
  module README for any module touched, update `CONTRACTS.md`
  **only if** a contract changed (with a contract-change note),
  and write `docs/handoffs/phase-<n>.md` with: what was built,
  test command and result, files changed, open risks, last pushed
  commit and tag, exact next step.
- **Prune rules:** never prune the 10 non-negotiable rules, the
  traps, the enums, or contract signatures. Prune only chatty logs
  and superseded decisions, archiving them to `docs/handoffs/`.
- Commit and tag only after the exit gate passes: `git tag
  phase-<n>`, then push the tag (command in Git workflow below).
- If a test fails, fix that phase. Do not proceed on a failing gate.

---

# Setup information — everything needed before Phase 1

## Non-negotiable rules (10)

1. **Honest unknowns.** Unrecorded is not no, not-checked is not
   clear, blank shelf-life is never a silent zero. Capability,
   storage and recall use `YES / NO / UNRECORDED`; a failed recall
   check is `NOT_CHECKED`, never `CLEAR`.
2. **Columns beat text.** When structured columns and profile text
   disagree, the column wins for filtering and the row is flagged
   `Needs human check`. Never guess which sentence is true.
3. **Meaning is not capacity.** Vector search finds candidates
   only. Hard constraints decide viability, deterministically:
   cold/frozen, capacity, pickup window, service day, dietary and
   cultural hard constraints, dock/transport.
4. **Deterministic maths.** Margins, splits, need scores,
   tie-breaks and impact scores are calculated in code, with
   the calculation stored. The model explains; it does not
   invent numbers. **Code Execution — locked (Review fix
   M1).** Split and margin maths for a plan MUST be executed
   through the **Gemini Code Execution** tool called by the
   Planner/Splitter (see Phase 3 Task 2): the planner sends
   the candidate allocations, quantities in the Phase 0 unit
   rule, pickup windows, and travel buffers as inputs, the
   sandbox returns the split quantities and margins, and
   the plan stores `{code, output, execution_source:
   CODE_EXECUTION}`. Plain in-process Python is a **fallback
   only** if Code Execution is unavailable in the lab —
   in that case the plan stores `execution_source:
   PYTHON_FALLBACK`, the reason, and the same code + output,
   and the Phase 3 handoff records the fallback. Do not
   present plain Python alone as Code Execution, and do
   not leave “code / Code Execution” as an either/or in
   code, tests, or the deck.
5. **Human-in-the-loop is a gate, not a label.** No plan approved,
   no hold started, nothing dispatched without a human approval
   record. No auto-approve, no approval on silence. A chat “yes”
   is a proposal only, until the approval call succeeds.
6. **Every plan change is a new version.** Never overwrite a plan.
   Keep v1, checker rejection and reasons, fixer change, v2+.
7. **Loop guards.** Checker/fixer: max 3 attempts, same-plan hash
   and same-reason detection, no external calls in the loop,
   escalate to a human instead of looping again. See Loop guards.
8. **Need is area-level, never a moral score.** Need is tract
   poverty + no-vehicle + assistance. Fit first, need second,
   fairness over time third. Race is never used — the tract table
   has no race columns. Recipient `reported_income` is **not** a
   ranking input.
9. **Guardrail transparency.** Every Match Brief includes the
   “Safety & Capacity Guardrails: Why Top Semantic Matches Were
   Filtered” callout, generated from stored `match_candidates`:
   semantic rank before filter, rank after, drop reason,
   contradiction flag, tie-break numbers.
10. **Honest labels.** Households reached are estimated, never
    summed across overlapping groups as unique people. ZIP-centroid
    distances are ZIP-area approximate, never exact door-to-door
    road time. Donor deadline always beats the FoodKeeper book.

## GCP — verify, do not assume

```bash
gcloud --version
gcloud config set project "$GOOGLE_CLOUD_PROJECT"
gcloud config get-value project   # must print the event project recorded in Part 1 / Phase 0 handoff
gcloud auth application-default login
gcloud services list --enabled --project "$GOOGLE_CLOUD_PROJECT"
```

- The event project ID is recorded in Part 1 as a build record and
  must be confirmed from config in the Phase 0 handoff. It must
  not appear in backend code, schemas, config files, or examples.
- One shared event project for the team; no project per teammate.
- Billing: verify/report billing status in Phase 0. If billing
  cannot be confirmed in the organiser/Qwiklabs project (for
  example for lack of permission), report it as **blocked** in the
  handoff. Do not work around it by creating a personal project.
- Verify by service name, not console search. Record the actual
  enabled list in the Phase 0 handoff:
  - Vertex AI API (`aiplatform.googleapis.com`) — models are
    called through Vertex AI / ADK, not a standalone Gemini key.
  - BigQuery (`bigquery.googleapis.com`), including the managed
    BigQuery MCP endpoint `https://bigquery.googleapis.com/mcp`
    for guarded, read-only, one-off questions only.
    **MCP implementation — locked (Review fix C1).** The MCP
    path for this build is the **built-in managed BigQuery MCP
    server** at that endpoint, used only through the backend
    for one-off, read-only questions (Guide / coordinator
    one-off path). It is NOT MCP Toolbox, and no Toolbox
    container is to be deployed unless the user approves a
    contract change first. Ranking, matching, and impact must
    never go through MCP — they use pre-written SQL /
    `VECTOR_SEARCH` directly. A mention in a README does not
    satisfy the starter requirement: Phases 2, 4, and 9 below
    each carry a passing test / eval case that the MCP
    endpoint was actually invoked through the backend, with
    the query, BigQuery job ID, and timestamp recorded in the
    phase handoff / stored run record.
  - Firestore (`firestore.googleapis.com`), Cloud Run
    (`run.googleapis.com`).
  - Maps Geocoding / Routes — bonus only (Phase 8). If not
    enabled, fall back to ZIP-area distance and say so; a Maps
    failure never blocks a match.
- Firestore existence check (Phase 0, testable — run one and record
  the output in the handoff):

```bash
gcloud firestore databases describe --project "$GOOGLE_CLOUD_PROJECT"
# expect: a (default) database, type FIRESTORE_NATIVE
```

If no Native-mode database exists, report blocked; do not switch
to Datastore mode mid-build.

### Environment variables

`.env` locally (never committed) and equivalent config on Cloud
Run. `.env.example` lists names with placeholders only. An empty
0-byte `.env` breaks agent loading silently — check `wc -c`.

| Variable | Meaning |
|---|---|
| `GOOGLE_CLOUD_PROJECT` | GCP project, read at runtime |
| `GOOGLE_CLOUD_LOCATION` | Vertex location; keep distinct from Cloud Run region |
| `CLOUD_RUN_REGION` | Cloud Run region, from env |
| `GOOGLE_GENAI_USE_VERTEXAI` | Route ADK via Vertex: `TRUE` |
| `BQ_DATASET_STARTER` | `a4i_food` (location US) |
| `BQ_DATASET_APP` | `rescueguard_app` |
| `MODEL_ID` | Model ID; record exact version in every run |
| `CHECKER_MAX_ATTEMPTS` | `3` |
| `HOLD_MINUTES` | `10` |
| `OPENFDA_MAX_CALLS_PER_RUN` | Set from the limit observed/recorded in Phase 2, not copied from another event |

Backend code authenticates with ADC or the Cloud Run service
account. Never put a service-account JSON key in the repo, `.env`
examples, chat, or commits.

## Local toolchain — pin or freeze in Phase 0

Recording a version after teammates have drifted is not pinning.
Phase 0 must **either** pin the versions below **or** record the
exact versions present in the event lab in the Phase 0 handoff and
freeze them for all later phases. State which was done.

- Python: pin the event-lab Python in `requirements.txt` /
  runtime config in Phase 0; do not let Cloud Shell and Mac
  versions drift silently. If the lab version differs from any
  version named in Part 1, the lab version recorded in the
  Phase 0 handoff is the frozen version.
- `google-adk`: pin the exact version present/verified in the
  event lab in Phase 0 `requirements.txt` (for example as
  `google-adk==<lab-version>`), and record it in every run.
  Do not upgrade/downgrade mid-build without a contract note.
- Also pin/range in Phase 0: `fastapi`, `google-cloud-bigquery`,
  `google-cloud-firestore`, `pydantic`. Record all in the handoff.
- Repo layout (create missing folders in Phase 0, inside the
  cloned teammate repo):

```text
ai_for_impact_atl_2/
  backend/app/  backend/agents/  backend/tools/  backend/sql/
  backend/tests/  schemas/  docs/handoffs/  docs/modules/
  frontend-contracts/   # contracts only — README: “no UI code in this build”
  CONTEXT.md  CONTRACTS.md  requirements.txt  .env.example
  # do NOT create a frontend/ folder in Phases 0–9
```

## Canonical local run and deploy commands (Review fix M2)

Do not invent a different port, service name, or start command
in a later session. If these commands do not work in the lab,
stop, record the actual working command in the Phase 0
handoff, and use that recorded command for all later phases.

**Local run (canonical):**

```bash
pip install -r requirements.txt
uvicorn backend.app.main:app --host 0.0.0.0 --port 8080
# health check, in a second terminal:
curl -s localhost:8080/api/health
```

Service name (locked for the demo): `rescueguard-backend`.
Region and project are never literals in commands in pushed
files — they come from env / config:

**Deploy template (canonical, Phase 9 uses this shape):**

```bash
gcloud run deploy rescueguard-backend \
  --source . \
  --project "$GOOGLE_CLOUD_PROJECT" \
  --region "$CLOUD_RUN_REGION" \
  --allow-unauthenticated
```

Phase 9 must record in its handoff: actual service name,
actual region value used, deployed URL, and revision. Those
are deploy records, not code values.

**Model choice (record in Phase 0).** Phase 0 must record
whether one `MODEL_ID` serves Guide chat, matcher
explanations, and Code Execution, or whether Guide has its
own model variable. Do not let Phase 4 invent a second model
variable silently — a second variable is a contract note in
`CONTRACTS.md` + the Phase 0 / Phase 4 handoff.
**Firestore location (record in Phase 0).** Phase 0 must
record the Firestore database location / region returned by
the describe command, alongside mode. Do not assume it
matches the BigQuery location (US) or the Cloud Run region.

## Git workflow — teammate repo, periodic pushes

**Origin is the teammate repo above.** The user has already
cloned it on Mac (`git version 2.38.1`, clone succeeded, working
tree listed `agent data notebooks notes scripts` etc.).
**Canonical copy is the Antigravity session clone (see Locked
decisions, Review fix C3)** — the Mac clone is inspection /
review unless Reyan explicitly pushes from it. Every phase
handoff records which clone was canonical for that phase.

```bash
git clone https://github.com/mattchainsaw/ai_for_impact_atl_2.git
cd ai_for_impact_atl_2
git remote -v   # origin must be the mattchainsaw repo above
git status      # must be clean before the first change
```

- **`.gitignore` check before first push:** verify the starter
  `.gitignore` covers `.env`. If it does not, add `.env` to
  `.gitignore` in Phase 0 **before** any test push. Run a secret
  grep before every push (grep scope in Phase 0).
- **Test push:** on a non-`main` test branch on that repo only,
  for example `git checkout -b test-push`, then
  `git push -u origin test-push`. Passing this confirms push
  access. Do not test-push to `main`.
- **Branches:** short-lived branch per lane or per phase
  (`data`, `agent`, `story`, `phase-<n>`). After Phase 0, no
  direct pushes to `main`: merge to `main` via a reviewed pull
  request, or a coordinator merge recorded in the handoff, only
  when another lane needs that work. Never force-push.
- **Periodic pushes:** after each phase exit gate, commit, tag,
  and push. Also push at natural stopping points in a long phase.

```bash
git add .
git commit -m "phase-<n>: <contract area touched>"
git push origin <your-branch>
git tag phase-<n>
git push origin phase-<n>        # tag push — required, not optional
# if pushing all tags: git push origin --tags
```

- Commit messages name phase + contract area, for example
  `phase-2: matcher constraint filter + match_candidates`.
- Phase handoffs record: clone path, branch, last pushed commit,
  last tag. A phase that exists only on one laptop is not done.

## Architecture — supervisor, specialists, shared state

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

- **FastAPI owns everything.** Supervisor is a plain FastAPI
  orchestrator, not an ADK agent. Specialists are Python tools.
  ADK only for Guide. Guide calls the supervisor API, never
  specialists directly. No specialist calls the supervisor, the
  supervisor never calls itself, chat never calls itself.
- **One state, no second truth.** Ticket state in Firestore is
  the single source of truth for screens and chat. There is never
  a chat plan and a separate screen plan.
- **Persona filtering is backend-enforced** on every query, by
  tenant (metro + organisation) and role. See Persona handoff.
- **State split (locked):** BigQuery = starter (read-only) +
  derived views + analytics/audit history. Firestore = live
  state: postings, tickets, plans, candidates, briefs, holds,
  allocations, tasks, approvals, conversations, recall checks,
  notifications, audit log, telemetry, distance pairs, roles.
  BigQuery is never a lock/live store; Firestore is never the
  long-term analytics sink alone.

### Specialists — what each one does, and does not do

| Agent/tool | Does | Does not do |
|---|---|---|
| Supervisor | Own ticket, versions, routing order, veto/escalate, hold creation inside approve, loop guards | Rank, check fridges, or do split maths itself |
| Matcher | Embed posting text, genuine `VECTOR_SEARCH` over embeddings, return semantic candidates + distance, pre-filter | Decide who gets food; apply hard constraints |
| Constraint + Last-Mile | Deterministic hard filters + margin + self-collect/needs-driver, dock, window, service day, dietary flags | Guess a missing column from bio text |
| Recall Guard | openFDA check before matching; `HALTED` blocks item, failure = `NOT_CHECKED` | Treat a failed check as `CLEAR` |
| Planner/Splitter | Deterministic whole-or-split plan; split/margin maths executed via Gemini Code Execution (Python fallback only, labelled — see Rule 4 / Phase 3), code + output stored on the plan | Let a model invent capacities or split numbers |
| Checker/Auditor | Independently try to reject: waste, unsafe fit, low-need skew, concentration, donor deadline ignored; incl. equity audit | Help make the plan it is checking |
| Fixer | Rewrite only flagged parts, max 3, hash/reason guards | Loop forever, make external calls in the loop |
| Impact & Fairness | Impact Score before approval; fairness ledger + rotation boost; unknown history = neutral | Sum overlapping households as unique people |
| Guide (ADK) | Answer/guide from checked ticket state, propose action cards, return `state_update` | Execute, approve, dispatch, or call specialists |
| Onboarding (bonus) | Write app recipient + embedding, verification gate, then coordinator-triggered re-match | Auto-approve, auto-hold, or make a PENDING pantry eligible for fresh/frozen |

### Crash / connection-loss resume (required)

Each ticket step writes a Firestore checkpoint **before** the next
step: `ticket_id, current_step, plan_version/current_plan_id,
holds_already_started, tasks_already_approved, step_started_at`.
Ticket run status includes `RESUMABLE` / `INTERRUPTED` in addition
to normal statuses.

- **Designated resume endpoint (locked): `GET
  /api/tickets/{ticket_id}`.** On the next GET after a restart, the
  supervisor reloads the last checkpoint, returns checkpoint status
  and resumed state, and does **not** re-run Maps, re-create holds,
  or re-approve tasks. Client polling on that GET is how a
  disconnected client discovers resumed state; there is no
  separate resume endpoint.
- Approvals/holds are idempotent by `request_id`, so a retry never
  double-assigns or double-holds.
- An expired hold or expired Maps/distance cache on resume is
  re-checked and recorded as a new check, never silently reused.
- **Demo fallback:** a fresh restart of a ticket is an acceptable
  demo fallback if resume fails. Persistence itself is **not**
  optional, because audit, versions, and holds require it. Do not
  present fresh restart as the normal path.

### Infinite-loop guards — all required

1. Hard cap 3 fixer attempts: v1 → v2 → v3. Still rejected →
   escalate to human with checker reasons + fixer attempts. Plan
   stays `DRAFT`.
2. Same-plan detection: hash every plan version (canonical JSON of
   allocations + parameters). A hash already seen stops the loop.
   Fields: `last_plan_hash` on plan/ticket (see Tables).
3. Same-reason detection: same checker reason twice after a fix
   stops the loop. Field: `last_checker_reason`, counter:
   `fixer_attempt_count`.
4. Deterministic planner in the loop: retries operate on maths
   outputs, not model randomness.
5. No external calls in the loop: no Maps, openFDA, or MCP calls
   inside checker/fixer. Those run once, before the loop.
6. Whole-ticket time/token/cost budget set by supervisor. On
   breach, stop and escalate; never retry in the background.
7. No tool-graph cycles; chat never auto-reruns match. Chat
   proposes an action card; only a human approval triggers a run.
   Guide clarification asked 3 times with no new information →
   stop, fall back to form / coordinator.

### Persona handoff contract (core, Phase 4/5)

Ticket states move: `POSTED → MATCHED → CHECKED → APPROVED →
HELD → CONFIRMED → COMPLETED`, with `DECLINED → RE-PLANNED`,
`CANCELLED`, `EXPIRED`, `FDA_HALTED`, `SPLIT_REQUIRED` also in the
ticket step/status enums where the idea names them. Every
transition records who, in which role, when, plan version, and
what changed, in `audit_log` + a `notifications` entry.

| Handoff | Sender → Receiver | Transfers | Does not transfer |
|---|---|---|---|
| Posting | Donor → Coordinator | Posting, pickup address (org/dock), deadline, quantity/unit | Other donors' offers |
| Approval | Coordinator → Recipient | Only that recipient's allocation, margin, pickup/delivery org addresses, hold timer | Other allocations, full ranking, checker/fairness internals |
| Confirm/Decline | Recipient → Coordinator | Decision + optional reason, per allocation | — (donor gets a status notification only, not re-plan internals) |
| Re-plan/Cancel | Coordinator → Donor + Recipients | Updated final pickup plan / “offer withdrawn”, holds released on cancel | Internal checker notes unless coordinator shares them |

- Backend filtering, not UI hiding: coordinator = all for tenant;
  donor = own postings only; recipient = own offers only.
  Cross-role/cross-tenant reads return **404, not 403**.
- Role switch: `GET /api/me` returns the current role/org/tenant;
  switching role re-filters **all** later backend reads, and Guide
  must acknowledge the switch in its context. Guide never reveals
  another persona's private view in chat.
- Inbox derivation is **not** ad hoc: donor/recipient inbox and
  status views read from `notifications` (Phase 4) plus their own
  holds/allocations. Do not re-derive donor notifications from
  tickets alone.

## BigQuery starter data — traps, all must be handled

Starter dataset `a4i_food`, location US, read-only.

1. **Planted teaching cases (9 expected, verify, do not assume).**
   `profile_source='planted'`: near-miss decoy (semantic #1, no
   cold), contradiction (columns vs text), genuine ties (identical
   operations, different words), vocabulary-mismatch rows (keyword
   search would miss, meaning search finds). Query actual Atlanta
   rows in Phase 1 and record real names/values. Do not put another
   city's planted names in code, tests, deck, or demo. Label
   planted cases as starter teaching cases, not real fridge status.
2. **NULL shelf-life is a rule, not zero.** Diapers (not food),
   milk (package use-by sentence), sealed formula (tracked only
   after opening) → resolved clock falls back to donor window,
   source recorded as `DONOR_FALLBACK` / `NOT_APPLICABLE`.
3. **“Spinach” is a subtitle under “Lettuce”** in FoodKeeper, not a
   product name. Use the conservative end of a range. Donor
   deadline beats the book.
4. **ZIP centroids.** Recipient lat/lon is a ZIP centre, not a
   building pin. Distances from it are approximate by construction.
5. **Org addresses only.** Recipient street/city/state/ZIP is a
   public IRS org address. The starter dropped personal contacts;
   never reintroduce personal names/phones/emails.
6. **Tract join is not given.** Recipients have no tract ID. Join =
   nearest tract by distance to ZIP centroid, **left join**, so a
   missing tract = `UNKNOWN`, fallback to weekly households, never
   zero and never a dropped pantry. Record method, cutoff, and
   missing rate in Phase 1. `geo_id` type and leading-zero handling
   (`LPAD` where needed) must be verified in Phase 0/1 — state
   whether `geo_id` is STRING or INT in the handoff.
7. **Cold domain must be verified.** The desert rule and filters
   depend on the full distinct `cold_storage` values in Atlanta.
   Query them in Phase 0/1; do not assume only `none`/walk-in.
   State in Phase 1 which values count as “cold” for deserts.
8. **Types must be verified, not assumed:** `recipient_id` type,
   `service_days` format (array/string/weekdays — constraint code
   cannot be built until this is known), `populations_served`
   format (free text — see parsed dietary flags in Tables).
9. **Coordinates:** test null, (0,0), and out-of-range lat/lon;
   flag/drop bad rows explicitly, never feed them silently into
   distance maths.

BigQuery rules: core numbers use pre-written, parameterised SQL
in `backend/sql/`, never string-concatenated user input. Free-form
model SQL is allowed only for one-off read-only questions via the
managed BigQuery MCP (`execute_sql_readonly` only), must show
query + job ID, and must never feed ranking, matching, or impact.

## Tables contract — 29 total, locked

Count rule: `tasks` and `approvals` are two collections; views
count as tables/views; the Firestore distance cache counts (it
replaced the earlier BigQuery maps cache — do not recreate that).

### A. Starter, BigQuery `a4i_food` — read-only (4)

| Table | Key fields / notes |
|---|---|
| `recipients` | `recipient_id, ein, name, street, city, state, zip_code, cold_storage, frozen_storage, loading_dock, refrigerated_transport, max_pallets, pickup_window_hours, weekly_households, reported_income (not a ranking input), populations_served, service_days, profile_text, profile_source, latitude, longitude` |
| `surplus_postings` | `posting_id, track, posting_text, foodkeeper_product, storage_state, hours_available, shelf_life_hours (nullable), hours_remaining`. No donor name/address |
| `shelf_life` | `product_id, product_name, product_subtitle, keywords, category, refrigerated_hours, refrigerated_note, pantry_hours, pantry_note` |
| `tract_demographics` | `geo_id, tract_lat, tract_lon, total_pop, median_income, poverty_rate, no_vehicle_rate, assistance_rate`. No race columns |

### B. Team BigQuery tables/views (6)

| Table/view | Purpose / rules |
|---|---|
| `recipient_embeddings` | `recipient_id, profile_text, embedding` (gemini-embedding-2, 3,072d via `AI.EMBED`), `embedded_status`. No vector index; brute-force `VECTOR_SEARCH`. Connection region = dataset region US. Filter `embedded_status=''` for search where the starter pattern applies — verify in Phase 1 |
| `app_recipients` | App-owned onboarded pantries only. Never insert into starter `recipients`. `verification_status: PENDING/VERIFIED/DEMO_SIMULATED`; PENDING is not eligible for fresh/frozen |
| `recipient_overrides` | App-owned profile changes: recipient ref, changed fields, parsed dietary/population flags if changed, status `PENDING/VERIFIED/APPROVED`, effective date, approver role. History kept; starter never updated in place |
| `v_all_recipients` | Starter + verified app recipients, with effective cold/capacity after approved overrides. All matching reads through this view (search path in Phase 1) |
| `v_recipient_tract` | Recipient → nearest tract: `tract_geo_id, poverty, no_vehicle, assistance, median_income, tract_distance_km (recipient-to-tract distance only), tract_status FOUND/UNKNOWN`. This distance is **not** donor-to-recipient distance — do not reuse the field for that |
| `v_rescue_deserts` | Tract where poverty >0.30 AND no-vehicle >0.40 AND cold recipients within 5 km = 0, using the verified cold domain |

### Search read path through `v_all_recipients` (locked, Phase 1)

Vector search must not bypass the view, and the view must not hide
a verified onboarded pantry from search. Phase 1 must implement
and test this exact path, and record it in the handoff:

1. `VECTOR_SEARCH` runs over `recipient_embeddings` joined by
   `recipient_id` to `v_all_recipients`.
2. Only rows present in `v_all_recipients` (starter + **verified**
   app recipients, with approved overrides applied) are returned.
   `PENDING` app recipients and unapproved overrides are excluded.
3. A pantry is searchable only if it is in **both** the view and
   `recipient_embeddings`. Onboarding (Phase 7) is incomplete if
   either write fails, and must report incomplete, not searchable.
4. Test in Phase 1/7: a verified app recipient appears in search
   after onboarding and does not appear before it.

### C. Firestore live — tickets/plans/holds (9 collections)

| Collection | Key fields / rules |
|---|---|
| `postings` | Live donor offers only: `posting_id, donor_id (org), donor_org_name, pickup_address, address_type (required, must be ORG_DOCK — see pickup-address validation below), pickup_zip, pickup_lat/lon (geocode or ZIP fallback, labelled), product_text, track, quantity + quantity_unit, split_allowed, delivery_available/donor_transport, dietary_flags, temperature_requirement, donor_deadline, status, created_at, expires_at, tenant_id` |
| `tickets` | `ticket_id, posting_id, posting_source (STARTER/LIVE_DONOR), posting_ref, metro, step, current_plan_id (not just a version number), plan_version_current (display only, derived from current_plan_id), parameters {top_n, weights, split_allowed}, resolved clock (below), checkpoint fields, status ACTIVE/RESUMABLE/INTERRUPTED, tenant_id` |
| `plans` | Append-only per version: `plan_id, ticket_id, plan_version, status DRAFT/CHECKER_REJECTED/APPROVED/SUPERSEDED, allocations[], checker_reasons, fixer_changes, fixer_attempt_count, last_plan_hash, last_checker_reason, plan_hash, impact breakdown, equity checker result, parameters snapshot, tract values snapshotted at approval, created_at, approved_by_role, approved_at, tenant_id` |
| `match_candidates` | Per candidate per match run: `ticket_id, run_id, recipient_id, semantic_rank, semantic_distance, status ELIGIBLE/FILTERED/FLAGGED/TIED, filter_reason, evidence {column_value, profile_text_excerpt}, tie_break_values, donor_to_recipient_distance_km, distance_source, need_score`. **This row, at match time, is authoritative for the Brief.** |
| `match_briefs` | Per approved plan version: `ticket_id, plan_id, plan_version, brief_text, outreach_message_draft, guardrail_callout, next_two_options, maps_attribution_text, created_at` |
| `holds` | **Internal only** — supervisor-created inside approve: `hold_id, ticket_id, plan_id, recipient_id, quantity + unit, status ACTIVE/CONFIRMED/EXPIRED/RELEASED, started_at, expires_at, confirmed_at, request_id, tenant_id`. A hold is the **lock** |
| `allocations` | Confirmed assignment, derived from holds: `allocation_id, recipient_id, ticket_id, plan_id, quantity + unit, status CONFIRMED/DECLINED/NO_SHOW/EXPIRED, allocated_at, confirmed_at, tract_geo_id, need_score_at_allocation, tenant_id`. Allocation is the **assignment + fairness-ledger record**; hold drives the recipient inbox lock state, allocation drives donor status + fairness. State this mapping in code/README, do not merge the two |
| `tasks` | `task_id, ticket_id, plan_id, task_type (APPROVE_PLAN/CONFIRM_PICKUP/UPDATE_PROFILE/CHECK_CONTRADICTION + coordinator gap types), owner_role, status OPEN/APPROVED/DECLINED/ASSIGNED, tenant_id` |
| `approvals` | Separate collection: `approval_id, task_id/plan_id/action_id, decision, approver_role, approved_at, plan_version, request_id`. Every consequential approval carries `request_id`; a repeat with the same `request_id` must not double-assign |

### D. Firestore live — people/safety/audit (7 collections)

| Collection | Key fields / rules |
|---|---|
| `conversations` | `session_id, ticket_id, role, messages[], context per message {ticket_id, plan_version, step, hold_status}, tool_calls, action_cards, approvals with role, model_version, prompt_version, scrub_status (SCRUBBED/REJECTED_ON_MATCH), tenant_id` |
| `recall_checks` | `check_id, ticket_id, product_text, fda_query, verdict CLEAR/HALTED/NOT_CHECKED, recall_id, checked_at, source (live openFDA / labelled offline snapshot), tenant_id`. Matching is by product text, not a structured product ID |
| `notifications` | `notification_id, recipient_role, recipient_org_id, ticket_id, event (OFFER_MADE/DECLINE/REPLAN/CANCEL/HOLD_EXPIRED/CONFIRMED/COMPLETED), created_at, read_status, tenant_id` |
| `audit_log` | Live append-only: `audit_id, ticket_id, plan_version, event_type, actor_role, action, timestamp, request_id, tenant_id`. Live audit export reads this |
| `telemetry_events` | Aggregate-only sink: `request_id, tool/endpoint, latency_ms, status, created_at, tenant_id`. Never bodies, addresses, names, transcripts |
| `distance_pairs` | Pair-keyed cache in **Firestore, not BigQuery**: `pair_key (hash of donor pickup + recipient ref — not a single-address key), distance_km, drive_time_minutes, source GOOGLE_ROUTES/HAVERSINE_FALLBACK, cached_at, expires_at (run-scoped, max 30 days), tenant_id`. Cache is a lookup only; the candidate row snapshot in `match_candidates` is authoritative for a Brief. Never store Maps phone/text/photos |
| `users_roles` | `user_id (Google account), role, org_id, tenant_id`. Demo-only role mapping. Org name/address live only on postings/recipients, not duplicated here |

### E. BigQuery history, `rescueguard_app` — sinks, not live sources (3)

| Table | Rules |
|---|---|
| `audit_history` | Post-run sink of Firestore `audit_log`. Live = Firestore; history = this table |
| `impact_snapshots` | One row per approved plan, sunk from `plans`. Plan's stored breakdown is authoritative live; this must not drift from it |
| `equity_audit_results` | One row per equity audit, sunk from the Checker result stored on the plan. Live Checker never reads this table |

**Total: 4 + 6 + 9 + 7 + 3 = 29.**

### Resolved clock, units, parsed flags — contract rules

- **Resolved clock (single source of truth).** Tickets carry:
  `resolved_deadline, resolved_shelf_life_hours,
  shelf_life_source (FOODKEEPER/DONOR_FALLBACK/NOT_APPLICABLE),
  resolved_at`. Margin is always: hours left on the resolved
  clock − pickup window − travel buffer. Do not compute margin
  separately from `hours_available`, `hours_remaining`, and
  `donor_deadline` in different modules.
- **Units — hard Phase 0 gate (see Phase 0).** Starter capacity
  is pallets (`max_pallets`); donor quantities may be crates.
  Phase 0 must record **either** a crates-per-pallet conversion
  (value + who decided it + where it is configured) **or** a
  pallets-only donor-quantity rule. Holds/allocations/plans store
  `quantity + quantity_unit` and, where conversion applies, the
  converted pallet value used for the capacity check. No planner
  code (Phase 2/3) may be written on an assumed conversion.
- **Parsed dietary/population flags.** `populations_served` in
  the starter is free text. Phase 1 must derive a parsed field
  (for example on the view/candidate: `dietary_flags[]` with
  values such as halal, pork-free, infant, medically restricted,
  plus `UNRECORDED` when the text does not support a flag) and
  record the parsing rule. Hard dietary constraints in Phase 2
  read the parsed flags + the live posting's `dietary_flags`,
  never raw free text at match time.
- **Impact Score formula (hand-checked, locked).** Components
  are scores 0–100. Points: Need 30, Food Rescued 25, Equity 25,
  Reliability 20. Total =
  `0.30×Need + 0.25×Rescue + 0.25×Equity + 0.20×Reliability`.
  Test fixture: Need 88, Rescue 100, Equity 82, Reliability 85 →
  `26.4 + 25 + 20.5 + 17 = 88.9`, reported as **89**, not 84.
  Any UI/deck figure must use the backend's stored total, and
  Phase 6 must hand-check this fixture in its tests.

- **Pickup-address validation — testable rule (Review fix
  M5).** A live posting is rejected (422) unless ALL of:
  (a) `address_type` is present and equals `ORG_DOCK`;
  (b) a coordinator has asserted `address_type` for that
  posting (assertion recorded: approver role + timestamp
  on the posting / approval record — a donor self-typing
  an address alone is not an assertion); and (c) the
  address text passes a format check that rejects an
  obviously residential posting: missing org/dock name,
  or free text matching the residential-pattern list in
  code/config (for example “home”, “house”, “apartment” /
  “apt”, “residence” with no org name). This is a format +
  coordinator-assertion rule, NOT a geocoding-based
  residential detector — do not invent one. Phase 4 must
  include a test: a home-address posting (no `ORG_DOCK`
  assertion, residential pattern) is rejected and never
  stored; an org/dock posting with coordinator assertion
  is accepted.

### What we store, update, and never store

- Store: tickets, plan versions (append-only), candidates with
  evidence, briefs, holds, allocations, tasks/approvals with
  `request_id`, recall verdict + ID + date only, notifications,
  audit log, telemetry aggregates, distance pairs (coordinates/
  drive time/place_id only, no Maps content), conversations with
  scrub status, run snapshot for replay (derived-table/view
  version, tract-join version, weights, thresholds, model +
  prompt versions, tenant).
- Update: only via new versions/overrides/app tables. Never
  mutate an approved plan, a starter row, or audit history.
  A correction is a new entry/version.
- Never store: end-beneficiary names/addresses/health details;
  personal donor/pantry phones/emails; Maps phone/text/photos;
  service-account keys/secrets/codes; a donor home address
  (pickup address must be validated as org/dock address);
  full openFDA response text as “proof” (verdict + ID + date only).

### Retention — one line per store (event-demo policy)

Write this policy to a policy file in Phase 9 and enforce what
the event API can enforce; state any operator-only part plainly.

| Store | Retention |
|---|---|
| Starter BigQuery tables | Organiser data; do not delete |
| Team views/tables + history sinks | Keep for judging/audit; delete on organiser request |
| `postings, tickets, plans, match_candidates, match_briefs` | Keep for audit through judging, then operator deletion on request |
| `holds, allocations` | Same as tickets; expired/released holds kept as history, not deleted mid-run |
| `tasks, approvals` | Keep with plan audit trail |
| `conversations` | Coordinator: 90 days. Recipient: anonymised after confirmation, within 24h, keeping only `task_id, plan_version, decision, approver_role, date`. Deletion on request must be possible (operator action, see API note) |
| `recall_checks, notifications` | Keep with ticket audit trail; notifications marked read, not deleted mid-run |
| `audit_log / telemetry_events` | Audit: keep through judging. Telemetry: aggregates only, keep 30 days in demo |
| `distance_pairs` | Run-scoped, expires max 30 days; expired entries re-checked, never silently reused |
| `users_roles` | Delete the Google-account mapping on request and at event end; do not keep it as a user registry |

## Scalability, observability, traceability, audit, telemetry, governance, feedback, tenancy

- **Scalability:** stateless Cloud Run (scale to zero), one metro
  per ticket run, deterministic code for ranking/splitting so cost
  scales with data not model calls per crate, Maps/Routes only for
  top matches, checker caps above, embeddings brute-force at this
  scale (no vector index).
- **Observability (is it healthy?):** request ID on every call,
  propagated to logs/Firestore/BigQuery records; structured logs
  (method, route, status, duration, request_id — no bodies);
  latency per step, Maps success rate, checker loop count, hold
  expiry rate, escalation rate, tokens/cost per run. Source:
  `telemetry_events`.
- **Traceability (why this decision?):** for every number — SQL
  file/fingerprint (SHA-256 of normalised SQL + parameters),
  parameters, BigQuery job ID, timestamp; for every match —
  candidate row + evidence; for every plan — version, rule,
  snapshot; for every action — approval record. Replay from the
  stored snapshot must reproduce the plan, not re-read live views.
- **Audit:** Firestore `audit_log` live, BigQuery `audit_history`
  post-run sink. Export reads Firestore for live runs, BigQuery
  for finished runs. A superseded plan stays readable.
- **Telemetry:** aggregate only — never bodies, addresses, names,
  transcripts, health details. `GET /api/telemetry` computes
  aggregates from `telemetry_events` + run records, tenant-filtered
  when a filter is supplied. There is no separate telemetry table
  beyond `telemetry_events`.
- **Governance:** source + licence per dataset recorded (IRS
  public, FoodKeeper CC0, ACS public, openFDA CC0 — publisher wins
  over catalogue); generated/modelled/planted data labelled;
  model + prompt version per run; a prompt change must re-run the
  Atlanta trap/eval suite before shipping; disclaimer in Brief/
  Guide output: “This is a matching aid, not a food-safety
  guarantee — follow official food-safety guidance, coordinator
  approves.”
- **Feedback:** Short loop — recipient/coordinator answer →
  draft recheck/new plan version only, human approval still
  required; pantry report → coordinator queue, unverified;
  coordinator edit → override + new version; checker reasons
  inform the fixer in that run only. Long loop — human-reviewed
  patterns → eval/trap suite → tested, approved changes only.
  Never train on pantry conversations/addresses/donor details;
  never let a report auto-change the official recipient list.
- **Multi-tenancy (demo, recorded not authenticated):** tenant =
  metro + organisation. Every row/plan/session/task/audit entry
  carries `tenant_id`; every backend query filters by the
  header-derived tenant + role. Header spoofing is not stopped by
  demo auth — state that limitation in every handoff/demo, never
  hide it. Conversation PII scrubbing: redact personal phone/
  email/address by regex in donor/recipient chat, reject-on-match
  for free-text address/phone in recipient intake, **before**
  storage, and record `scrub_status`.

## API contracts — 52 endpoints, locked

Define every request/response as a Pydantic model in `schemas/`
in Phase 0. A new field goes into the schema + `CONTRACTS.md`
first, or the contract test fails.

### Contract rules for every endpoint

- Every request carries `request_id`; every response echoes it.
  Every consequential POST body includes `request_id`; approvals
  are idempotent by `request_id` + action ID.
- Every fact carries a source label. Statuses `YES/NO/UNRECORDED`.
- Already-decided/approved → **409**. Approve on a plan not in a
  checker-passed state → **422**. Approve itself creates the
  approval record — never require a prior approval record.
- No viable match → **422** with a structured fallback body (why
  no one fits, nearest option and why not, coordinator contact
  path). Never an empty plan or a guessed pantry. The match
  endpoint restates this rule in its own spec.
- Cross-role/cross-tenant reads → **404, not 403**.
- **Canonical approval:** `POST /api/actions/approve` is the single
  entry for chat-initiated approvals. Plan-approve and task
  endpoints delegate to the same idempotent approval service,
  keyed by `request_id` + action ID. One approval flips exactly
  one target; a second identical approval → 409.
- **Holds are internal.** No public create/expire hold endpoint.
  Holds are created by the supervisor inside approve; expiry is a
  system transition. Public hold transitions: confirm + release,
  with role + ownership checks.
- **Demo auth:** `X-Role` + `X-Tenant` headers on every call,
  recorded/demo-only/not authenticated (see Locked decisions).
  `tenant_id` is header-derived on every endpoint; no endpoint
  requires `tenant_id` in the body. Telemetry/audit are aggregate-
  only unless a tenant filter is supplied, then they filter.
- **Pagination/caps:** list endpoints `limit` (default 50, max
  200) + `offset`; search `top_k`/`top_n` max 50; Routes calls
  top matches only. Every Pydantic model includes `tenant_id`
  (header-derived) where the resource is tenant-scoped.
- Maps failure → `UNVERIFIED`/estimated fallback, never exact.
  Anonymising/deleting a recipient conversation on request is
  **out of scope for the event API**: it is an operator data
  action recorded in `audit_log`, and the repo/deck must state
  this limit — do not silently omit it.

### Health, identity, starter reads (7)

```text
GET  /api/health
GET  /api/me
GET  /api/starter-postings
GET  /api/shelf-life/{product}
GET  /api/tracts/{geo_id}
GET  /api/recipients
GET  /api/recipients/{recipient_id}
```

Notes: `/api/health` returns `{status, project (from config),
dataset, model_id}` — no secrets. `/api/me` returns `{role,
org_id, tenant_id}` (demo-only); a role switch re-filters all
later backend reads. Starter/shelf-life/tract reads are the API
path for UI/Guide FoodKeeper and tract questions; a separate
guarded MCP query is for one-off questions only and never feeds
ranking.

### Postings, tickets, matching, plans (14)

```text
POST /api/postings
GET  /api/postings
GET  /api/postings/{posting_id}
POST /api/tickets
GET  /api/tickets
GET  /api/tickets/{ticket_id}
POST /api/tickets/{ticket_id}/match
GET  /api/tickets/{ticket_id}/parameters
POST /api/tickets/{ticket_id}/parameters
POST /api/tickets/{ticket_id}/cancel
GET  /api/tickets/{ticket_id}/plans
GET  /api/plans/{plan_id}
POST /api/plans/{plan_id}/approve
POST /api/plans/{plan_id}/reject
```

Notes: `POST /api/tickets` body is `{posting_id, posting_source:
"STARTER"|"LIVE_DONOR", request_id}` — the discriminator is
required; a bare `posting_id` is a contract error. Lists are
role-filtered and sorted by expiry, not posting order.
`GET /api/tickets/{ticket_id}` is canonical ticket state **and**
the resume endpoint. `POST …/match` runs Matcher → Constraint →
Planner → Checker → Fixer (max 3) and returns a plan version; it
does not approve or hold; on no viable recipient it returns the
422 fallback above. `…/parameters` GET returns the parameters
stored on the ticket; POST sets them for that ticket only and
creates a new plan version on re-match, never a global default.
`…/cancel` is donor (own posting only) or coordinator: it
releases all holds internally, notifies recipients, and creates a
`CANCELLED` ticket/plan state. `…/approve` delegates to the
canonical approval service; on success the supervisor creates
holds internally. `…/reject` records a reason and triggers a
fixer/re-plan as a new version.

### Holds, allocations, completion (8)

```text
GET  /api/tickets/{ticket_id}/holds
GET  /api/holds/{hold_id}
POST /api/holds/{hold_id}/confirm
POST /api/holds/{hold_id}/release
POST /api/tickets/{ticket_id}/decline
POST /api/allocations/{allocation_id}/complete
POST /api/allocations/{allocation_id}/no-show
GET  /api/allocations
```

Notes: Offer-confirm and pickup-complete are **separate**
transitions. `confirm` = recipient accepts (`ACTIVE → CONFIRMED`).
`complete` = pickup actually happened (ticket → `COMPLETED`).
`no-show` records `NO_SHOW` in the fairness ledger. Without
`complete`/`no-show`, `COMPLETED`/`NO_SHOW` are unreachable — do
not merge them into `confirm`. `decline` is per-allocation, body
`{recipient_id, allocation_id, reason?, request_id}`, returns a
new plan version with the next pantry promoted and other holds
kept; 409 if that hold is already `CONFIRMED`/`EXPIRED`, 422 if
no active hold exists for that recipient. `release` is role +
ownership checked and frees capacity.

### Recipients, onboarding, profile updates (3)

```text
POST /api/recipients/search
POST /api/recipients
PATCH /api/recipients/{recipient_id}
```

Notes: `search` genuinely calls `VECTOR_SEARCH` through the
locked search read path and returns semantic candidates **before**
constraint filtering, with rank + distance, so the Brief can show
rank before vs after. Never substitute keyword/`LIKE`.
`POST /api/recipients` (onboarding) writes `app_recipients` +
`recipient_embeddings`, sets `verification_status`
(`PENDING/VERIFIED/DEMO_SIMULATED`), writes an audit entry, and
is **incomplete/not searchable** if either write fails. A
`PENDING` pantry is not eligible for fresh/frozen. Onboarding
alone never auto-approves or auto-holds: after it succeeds, the
coordinator (or a Guide action card) calls `POST
/api/tickets/{ticket_id}/match` again, which creates a new plan
version. `PATCH` is own-org only, writes `recipient_overrides`
(never the starter row), and re-embeds if profile text changed.

### Tasks, actions, Guide chat (7)

```text
POST /api/tasks
GET  /api/tasks
GET  /api/tasks/{task_id}
PATCH /api/tasks/{task_id}
POST /api/actions/approve
POST /api/assistant/chat
GET  /api/conversations/{session_id}
```

Notes: `POST /api/tasks` creates coordinator gap tasks (verify
capacity, check contradiction, set up pickup) as well as system
tasks. `PATCH /api/tasks/{task_id}` delegates to the canonical
approval service. Action schema (locked, in `schemas/`):
`action = {action_id, target_type: "task"|"plan"|"hold"|
"onboarding", target_id, target_endpoint}`. Approving an action
calls exactly that endpoint with the approver role; a second
identical approval → 409. `POST /api/assistant/chat` input carries
`{session_id, ticket_id, posting_id, plan_version, step, role,
hold_status, message}`; output is `{answer, citations[],
action_cards[], state_update}`. Guide never executes a
consequential action itself.

### Impact, equity, deserts, safety, last-mile (9)

```text
GET  /api/tickets/{ticket_id}/impact
GET  /api/impact/dashboard
POST /api/equity/audit
GET  /api/equity/{ticket_id}
GET  /api/deserts
GET  /api/deserts/{tract_geo_id}
POST /api/recall/check
GET  /api/tickets/{ticket_id}/recall
GET  /api/tickets/{ticket_id}/last-mile
```

Notes: `impact` is the score for a plan (total + breakdown +
v1 vs v2 vs do-nothing, labelled estimated). `equity/audit` is
the detailed Checker-owned tract comparison for a plan (chosen
averages vs metro averages, `PASS/WARN` with numbers); its result
is stored on the plan and later sunk to BigQuery — do not build
duplicate equity logic in the impact service. `last-mile` is a
filtered view of the current plan's allocations + candidates, not
a separate store. `recall/check` returns `CLEAR/HALTED/
NOT_CHECKED`; `HALTED` blocks that item. The recall list endpoint
returns all checks for a ticket.

### Maps (bonus), audit, telemetry (4)

```text
POST /api/maps/geocode
POST /api/maps/route
GET  /api/audit/export
GET  /api/telemetry
```

Notes: Geocode/route are Phase 8, top matches only, source
`GOOGLE_ROUTES/HAVERSINE_FALLBACK`, cache key is the pair hash in
`distance_pairs`, TTL run-scoped max 30 days, attribution text is
stored on the Brief where a Maps link is shown. Audit export:
live = Firestore `audit_log`, finished = BigQuery
`audit_history`. Telemetry: aggregates from `telemetry_events`.

**Total: 7 + 14 + 8 + 3 + 7 + 9 + 4 = 52 endpoints.**

## How RescueGuard differs — backend facts to preserve

- Most brokers collapse meaning, fit, and audit into one score.
  RescueGuard separates them: meaning finds, deterministic maths
  decides fit, an independent checker tries to reject the plan.
  A builder must not re-collapse them into a single ranking call.
- Most matchers are stateless. RescueGuard is stateful: versions,
  transactional Firestore holds, declines and allocations are
  remembered, and the fairness ledger changes later matches.
- Guardrail Transparency is stored evidence (`match_candidates`),
  not a UI annotation invented at render time.
- Do **not** copy: another city's planted names or trap values,
  Toronto/SurgeGuard numbers, prompts, gates, or eval results as
  Atlanta facts; a keyword/`LIKE` search presented as vector
  search; an in-memory ledger as live state (it loses the plan on
  restart); or BigQuery as a hold/lock store.

---

# Phases — backend only, each independently testable

Each phase lists goal, owns/does not touch, tasks, test, exit
gate, eval subset, and OKF update. Run the eval subset at the end
of the phase, not only at the end of the build. Phase numbering
is unambiguous:

- **Phase 0** = project, repo, health, contracts, starter
  **existence** check, and the hard unit/clock gates.
- **Phase 1** = starter **counts/types/planted/tract/embeddings**
  verification and derived views.
Do not let both phases claim the same gate.

## Phase 0 — Setup and contract freeze (no product logic)

**Goal:** repo, environment, frozen contracts, OKF files, working
health endpoint, and the two hard decision gates recorded.

**Owns:** repo layout, `.env.example`, `CONTEXT.md`,
`CONTRACTS.md`, `schemas/`, skill stubs, config, `/api/health`.
**Does not touch:** matcher, planner, checker, chat logic.

**Tasks:**

1. Clone/verify the teammate repo (Git workflow above).
   **First task in Phase 0 — close C1–C3 before any product
   code:** (C3) Name the canonical working copy for this
   session (Antigravity session clone — see Locked
   decisions) and record in the handoff: canonical clone
   path, branch, remote URL, and last pushed commit / tag;
   state that Reyan's Mac clone is inspection/review unless
   he explicitly pushes from it. (C2) Record the Part 1
   decision: “Part 1 not pushed” or “Part 1 redacted, then
   pushed” — do not push Part 1 with a literal project ID.
   (C1) Record the locked MCP path: built-in managed
   BigQuery MCP (`https://bigquery.googleapis.com/mcp`),
   backend-invoked, read-only, one-off only — not MCP
   Toolbox. Verify `.gitignore` covers `.env` **before**
   any push; add it if not. Do the test push on a
   non-`main` test branch on that repo.
2. Create the repo layout, `frontend-contracts/README.md`
   (“no UI code in this build”), `CONTEXT.md` from the template,
   `CONTRACTS.md` from the API/Tables sections (29 / 52), and a
   Pydantic model for every endpoint. Create one skill stub per
   subsystem — matcher, constraint, planner, checker,
   supervisor, guide, data, onboarding, maps, **impact-fairness,
   recall, last-mile** — each with: trigger, interface, traps,
   test name. No subsystem in the Architecture table may be
   left without a skill stub.
3. Config module reads all env vars in one place, with
   `CHECKER_MAX_ATTEMPTS=3` and `HOLD_MINUTES=10` as named
   constants. Pin or freeze Python + ADK + library versions (see
   Toolchain) in `requirements.txt` and record them in the
   handoff, stating pin-vs-freeze. FastAPI app with
   `GET /api/health` only. Record the canonical local run
   command (see Canonical commands) and verify it starts
   the server on port 8080; record the model choice (one
   `MODEL_ID` for all, or Guide's own variable as a
   contract note) and the Firestore location from the
   describe output. Set `$GOOGLE_CLOUD_PROJECT` from the
   lab environment / Part 1 record in this session — a
   fresh session must not guess its value; the Phase 0
   handoff records that it was set from config in the lab.
4. Secret grep test: grep **only** `backend/`, `schemas/`, config
   files, and `.env*` for a project-ID pattern and secret-like
   strings. Explicitly exclude `*.md` docs/handoffs, which may
   record the project ID as a build record.
5. Record actual outputs in `docs/handoffs/phase-0.md`: project
   from config, frozen versions, enabled API list (incl. whether
   Maps Geocoding/Routes are enabled), billing status (or
   **blocked**, with no personal-project workaround), Firestore
   database describe output, starter dataset/tables **existence**
   (counts are Phase 1).
6. **HARD GATE — units:** record either the crates-per-pallet
   conversion (value, decider, config location) **or** the
   pallets-only donor rule, in `CONTRACTS.md` + handoff.
7. **HARD GATE — resolved clock:** record the resolved-clock rule
   (fields + margin formula in Tables) in `CONTRACTS.md` +
   handoff, including `NOT_APPLICABLE`/`DONOR_FALLBACK` handling.
   Also record, as far as Phase 0 queries allow: `recipient_id`
   type, `geo_id` type, `service_days` format, distinct
   `cold_storage` values — or list them as Phase 1 blockers.
   **If either hard gate cannot be recorded, Phase 0 fails.
   Stop. Do not proceed to Phase 1, and Phase 2/3 must not start
   on an assumed conversion or clock.**

**Test (independent):**

```bash
gcloud config get-value project
gcloud firestore databases describe --project "$GOOGLE_CLOUD_PROJECT"
python -c "import sys; print(sys.version)"
pip show google-adk | grep Version
curl -s localhost:8080/api/health
pytest backend/tests/test_contracts.py backend/tests/test_no_secrets.py
bq ls a4i_food   # existence only in Phase 0
```

**Exit gate:** project is the event project (from config, not
hardcoded), `/api/health` answers, contract + secret tests pass,
OKF files exist, Firestore Native confirmed, `.gitignore` + test
push confirmed, versions pinned/frozen and recorded, **both hard
gates (units + resolved clock) recorded**, and the architecture
decision is recorded in `CONTEXT.md` (FastAPI owns everything;
ADK only for Guide; ADK v2 graph fallback only, subgraph only).
Tag `phase-0`, push branch + tag, stop.

**Eval subset:** contract tests only — no product eval yet.
**OKF update:** fill `CONTEXT.md` architecture + decisions
(“contracts frozen v1, 29/52”), write handoff, prune.

## Phase 1 — Data layer: verify, embed, join

**Goal:** Atlanta data the matcher can actually use, with traps
known and the search read path proven.

**Owns:** `backend/sql/`, embeddings builder, views
(`v_all_recipients`, `v_recipient_tract`, `v_rescue_deserts`),
parsed dietary flags, data tests.
**Does not touch:** planner, holds, Guide, Maps routes.

**Tasks:**

1. Verify in place (do not reload): row counts for `recipients`
   (~135 expected), `surplus_postings` (10), `shelf_life` (661),
   `tract_demographics` (record actual). Record any mismatch.
2. Record field facts: `recipient_id` type, `geo_id` type +
   leading-zero handling, `service_days` format, distinct
   `cold_storage` values + which values count as cold for the
   desert rule, coordinate-validity results, NULL shelf-life rows.
3. Planted query: list actual Atlanta rows where
   `profile_source='planted'` with name, cold/frozen, capacity,
   and trap type (decoy/contradiction/tie/vocabulary). Record
   them in the handoff. These, and only these, may be used as
   Atlanta planted cases in later tests/deck.
4. Embeddings: `AI.EMBED` profile text with gemini-embedding-2
   (3,072d) into `recipient_embeddings`; no vector index;
   brute-force `VECTOR_SEARCH`; connection region = US.
   Implement the locked search read path (embeddings joined by
   `recipient_id` to `v_all_recipients`, verified-only) and test
   that a verified recipient is returned and a pending/unapproved
   one is not.
5. Tract join: nearest tract to ZIP centroid, left join, with
   method, cutoff, distance, and missing/UNKNOWN rate recorded.
   Build `v_recipient_tract` (tract distance field is recipient-
   to-tract only) and `v_rescue_deserts` using the verified cold
   domain. Build the parsed dietary/population flags + rule.
6. Shelf-life rules as code + tests: NULL cases, Spinach-under-
   Lettuce lookup, conservative range end, donor deadline wins,
   resolved-clock fields populated from these rules.

**Test:** embedding search returns a known pantry for “fresh
leafy greens”; tract join returns poverty/no-vehicle for 5 sample
recipients (or `UNKNOWN` with fallback, explicitly); desert view
returns rows or a proven-zero result with the rule shown; planted
list is non-empty or reported as a blocker with the query shown.

**Exit gate:** counts/types/planted/join/embeddings all recorded
in `docs/handoffs/phase-1.md`; search read path proven. If the
planted query or tract join cannot be verified, stop and report
— do not proceed on Chicago/Toronto assumptions. Tag `phase-1`,
push, stop.
**Eval subset:** data-trap cases: NULL shelf-life, Spinach
lookup, coordinate validity, planted decoy present in data.
**OKF update:** `CONTEXT.md` tables/traps with verified Atlanta
values, module README for data, handoff, prune.

## Phase 2 — Matcher, constraint, last-mile basics, recall

**Goal:** meaning search that does not trust its own #1, with
stored guardrail evidence for every candidate.

**Owns:** Matcher, Constraint + Last-Mile, Recall Guard,
`match_candidates` writes, recall endpoints.
**Does not touch:** planner splits, checker/fixer, holds, approve.

**Tasks:**

1. Endpoints: `POST /api/recipients/search`, `GET
   /api/recipients`, `GET /api/recipients/{recipient_id}`,
   `POST /api/recall/check`, `GET /api/tickets/{ticket_id}/recall`.
   **Recall read clarification:** there is no single-check
   endpoint in the 52 — do not add a 53rd endpoint. The
   ticket recall list IS the list path, and individual check
   details (verdict, recall_id, checked_at, source) are
   returned inside that list. Also `GET
   /api/shelf-life/{product}` and `GET /api/tracts/{geo_id}`
   if not already stubbed in Phase 0.
   **MCP proof (C1):** in this phase, invoke the managed
   BigQuery MCP endpoint once through the backend for a
   one-off read-only question (for example a pantry-count
   question that does NOT feed ranking), and record query +
   BigQuery job ID + timestamp in the Phase 2 handoff.
2. Matcher: genuine `VECTOR_SEARCH` via the Phase 1 read path,
   `top_k` configurable (max 50), semantic rank + distance
   returned pre-filter. No keyword/`LIKE` substitute.
3. Constraint filter, deterministic, with a reason per candidate:
   cold/frozen for this item, capacity in the Phase 0 unit rule,
   max pallets, pickup window vs resolved-clock hours left,
   service day (using the verified `service_days` format), parsed
   dietary/cultural hard constraints, dock/transport. Columns
   beat text: a column-vs-text contradiction sets `FLAGGED`
   (needs human check), never an auto-match guess.
4. Last-mile basics: self-collect vs needs-driver from
   `refrigerated_transport`, loading dock vs hand-unload only,
   ZIP-area distance (haversine from ZIP centroids, labelled
   approximate) + travel buffer, margin = resolved hours left −
   pickup window − buffer. Negative margin = out, with reason.
   Write distance + source onto the candidate row; also write the
   pair cache in `distance_pairs` as a lookup only.
5. Recall Guard: openFDA check **before** matching. Record the
   actual API limit observed in the event project in the handoff
   and set `OPENFDA_MAX_CALLS_PER_RUN` from it — do not copy a
   limit from another event as a fact. `HALTED` blocks the item;
   any failure/timeout = `NOT_CHECKED`, never `CLEAR`. Offline
   snapshot fallback is allowed only if labelled as snapshot.
6. Store every candidate in `match_candidates`: semantic rank/
   distance before filter, status, filter reason, evidence
   (column value vs profile excerpt), tie-break values, distance
   + source. This store is the Brief's guardrail source in
   Phase 5 — build the data now, not the Brief yet.

**Test:** spinach-type posting returns the verified Atlanta decoy
at semantic #1 **and** filtered out with “no cold” reason (use the
actual Phase 1 planted name in the test, not a name from another
city); contradiction case is `FLAGGED`; a no-cold pantry never
appears in the viable list; a recall-match case is `HALTED`; a
forced openFDA failure returns `NOT_CHECKED`; **MCP test
(C1): a one-off read-only question invoked through the
managed BigQuery MCP endpoint via the backend returns an
answer with query + job ID recorded, and that answer is
asserted NOT to have fed ranking/matching.**

**Exit gate:** all five tests pass with stored candidate rows
that reproduce rank-before vs rank-after. Tag `phase-2`, push, stop.
**Eval subset:** decoy, contradiction, vocabulary-mismatch
(found by meaning), recall halt, recall failure state.
**OKF update:** matcher/constraint module READMEs, `CONTEXT.md`
traps with Atlanta names, handoff (incl. openFDA limit), prune.

## Phase 3 — Planner/splitter, checker/fixer

**Goal:** a plan that can be rejected and fixed, not just a list.

**Owns:** Planner/Splitter, Checker/Auditor (incl. equity check
logic), Fixer, plan versions, match endpoint.
**Does not touch:** holds, approve execution, Guide, onboarding.

**Tasks:**

1. Endpoints: `POST /api/tickets` (with `posting_source`),
   `POST /api/tickets/{ticket_id}/match`, `GET
   /api/tickets/{ticket_id}/plans`, `GET /api/plans/{plan_id}`,
   `GET + POST /api/tickets/{ticket_id}/parameters`.
   Ticket creation from a starter posting and from a live posting
   must both work and must not collide on IDs.
2. Planner, deterministic: whole load fits → whole; does not fit
   → split across 2–3 verified pantries, each within capacity
   (Phase 0 unit rule), cold, window, and margin.
   **Code Execution — explicit integration point (M1):**
   the Planner/Splitter tool calls the **Gemini Code
   Execution** tool for split/margin maths. Inputs: candidate
   allocations, quantity + unit (Phase 0 rule), capacities,
   pickup windows, travel buffers, resolved hours left.
   Outputs stored on the plan: split quantities, margins,
   plus `{code, output, execution_source}`. Fallback only:
   if Code Execution is unavailable in the lab, run the
   identical deterministic Python calculation, store
   `execution_source: PYTHON_FALLBACK` + reason + code +
   output, and record the fallback in the handoff. A plan
   with neither code nor output stored fails this task.
3. Need + tie-break: among viable candidates, need score =
   `0.6×poverty + 0.4×no_vehicle` for the pantry's tract
   (`UNKNOWN` tract → fallback to weekly households, flagged).
   Genuine ties break in order: distance, then tract need, then
   recent donation history (Phase 6 ledger; in Phase 3, history
   is neutral/empty and must be recorded as such, not invented).
4. Checker, independent of planner: waste? unsafe fit? low-need
   skew (chosen tract averages vs metro averages, with numbers)?
   concentration (same pantries, others zero — full fairness
   ledger arrives in Phase 6; in Phase 3 check within-run
   concentration only and record that limit)? donor deadline /
   resolved clock ignored? If any bad answer: `CHECKER_REJECTED`
   with reasons stored on the plan.
5. Fixer: rewrites only flagged parts, max 3, with
   `fixer_attempt_count`, `last_plan_hash`, `last_checker_reason`
   maintained on ticket/plan. Same hash or same reason twice →
   stop and escalate. No external calls in the loop.
6. Essentials mode: no cold-chain rule, but safety, size, and
   donor-window fallback apply; recall still applies. Farm mode:
   large-load split as in Task 2, no single pantry overloaded.
   Plan versions are append-only; never mutate an approved plan
   (no approved plans exist until Phase 4 — enforce the invariant
   in code/tests anyway).

**Test:** spinach fixture — a v1 that wastes part of the load is
rejected with reason, v2 split places the full load and passes;
farm fixture — 12-pallet-type load splits across pantries with no
overload (use verified Atlanta capacities/units); loop fixture —
fixer fails 3 times → escalates, plan stays `DRAFT`, no infinite
loop; no-viable fixture — match returns 422 fallback, not a plan.

**Exit gate:** all four tests pass with plan versions + checker
reasons stored and replayable from the stored snapshot. Tag
`phase-3`, push, stop.
**Eval subset:** split, waste-reject, loop-escalate, 422 fallback,
essentials donor-window fallback.
**OKF update:** planner/checker READMEs, plan enums in
`CONTRACTS.md` if changed (with note), handoff, prune.

## Phase 4 — Supervisor, ticket, holds, tasks, Guide chat

**Goal:** one ticket, one state, human approval, lock — the heart
of the product. This is the largest phase; if it must split, split
as 4a (supervisor/holds/tasks) and 4b (Guide/persona/resume) in
two sessions, with a handoff between them, and tag only when both
pass. Do not tag a half-phase as `phase-4`.

**Owns:** Supervisor orchestration, live postings, holds,
tasks/approvals, notifications, Guide chat, persona filtering,
resume/checkpoint.
**Does not touch:** Brief rendering (Phase 5), impact dashboard
(Phase 6), onboarding (Phase 7), Maps routes (Phase 8).

**Tasks:**

1. Endpoints (postings/tickets/holds/allocations/tasks/actions/
   chat/conversations/me — all 52-list entries for these groups):
   `POST/GET /api/postings`, `GET /api/postings/{id}`,
   `GET /api/tickets`, `GET /api/tickets/{ticket_id}`,
   `POST …/cancel`, `POST /api/plans/{plan_id}/approve`,
   `POST /api/plans/{plan_id}/reject`, `GET
   /api/tickets/{ticket_id}/holds`, `GET /api/holds/{hold_id}`,
   `POST /api/holds/{hold_id}/confirm`,
   `POST /api/holds/{hold_id}/release`,
   `POST /api/tickets/{ticket_id}/decline`,
   `POST /api/allocations/{allocation_id}/complete`,
   `POST /api/allocations/{allocation_id}/no-show`,
   `GET /api/allocations`, `POST/GET /api/tasks`,
   `GET /api/tasks/{task_id}`, `PATCH /api/tasks/{task_id}`,
   `POST /api/actions/approve`, `POST /api/assistant/chat`,
   `GET /api/conversations/{session_id}`, `GET /api/me`.
   There is **no** public hold-create or hold-expire endpoint.
2. Supervisor: owns ticket versions, routing order, veto/
   escalation, loop guards, approval enforcement, Firestore
   state. Live postings are separate from starter postings, with
   expiry and the full status machine (incl. `FDA_HALTED`,
   `SPLIT_REQUIRED`, `EXPIRED`, `CANCELLED`).
   **Pickup-address validation (M5):** enforce the
   testable rule in Tables — `address_type: ORG_DOCK`
   required, coordinator assertion recorded, residential-
   pattern format check rejects an obviously residential
   posting with 422 and never stores it. **Guide MCP
   proof (C1):** a Guide one-off question that uses the
   managed BigQuery MCP path must go through the backend,
   show query + job ID, and never feed ranking — test it
   in this phase alongside the chat tests below.
3. Holds: Firestore transactional, 10 minutes (`HOLD_MINUTES`),
   created **only** inside approve, 409 on double-hold/double-
   approve, idempotent by `request_id`, expiry is a system
   transition that releases capacity, writes a notification, and
   returns the ticket to the coordinator.
4. Approval service (canonical): one service behind
   `POST /api/actions/approve`, plan-approve, and task PATCH.
   Approve = record decision + approver role + plan version, flip
   the **one** target, start holds if a plan. Approve does not
   send, dispatch, or book. Chat “yes” alone does nothing.
5. Decline/complete/no-show: decline is per-allocation (see API
   notes), promotes the next pantry, keeps other holds, creates a
   new plan version, and notifies the donor of the updated plan
   only. Complete and no-show are separate endpoints (see API).
   Cancel releases all holds, notifies recipients (“offer
   withdrawn”), and cancels the ticket.
6. Tasks: system-created + coordinator-created gap tasks
   (`POST /api/tasks`). “Approve – assign to [owner role]” →
   “Assigned to [owner] – actioned”, with the approval record in
   `approvals`, idempotent by `request_id`.
7. Guide chat (ADK only): every message carries session/ticket/
   posting/plan_version/step/role/hold_status; response is answer
   + citations + action cards + `state_update`. Guide calls the
   supervisor API only. Clarification guard: same question 3
   times, no new info → stop, fall back to form/coordinator.
   Conversations are PII-scrubbed before storage, with
   `scrub_status` recorded.
8. Persona filtering + notifications: backend filtering per the
   Persona handoff contract; every handoff transition writes a
   `notifications` entry and an `audit_log` entry. `GET /api/me`
   + role switch re-filter all later reads in the backend.
9. Crash/resume: checkpoint before each step; `GET
   /api/tickets/{ticket_id}` is the resume endpoint (see
   Architecture). Test restart without re-running Maps/recall,
   without duplicate holds, and without re-approving tasks; an
   expired hold on resume is re-checked, not silently reused.

**Test:** end-to-end by clicks **and** by chat, same result:
posting → match → v1 reject → v2 approve → hold countdown →
recipient decline → v3 approve → confirm → complete.
**“By clicks” — backend-only reading (Review fix M3):**
in this backend-only build, “by clicks” means **by direct
API calls simulating the coordinator desk actions** — the
same HTTP calls a frontend would make (create posting,
match, approve, confirm, complete). It does NOT mean
building or using a UI. Do not create frontend code to
satisfy this test, and do not stall waiting for a frontend.
The chat path and the direct-API path must produce the
same ticket result. Plus:
chat-only “yes” without the action call does nothing; double-
approve → 409; cross-role read → 404; donor cancel releases all
holds; restart-resume returns the same ticket with no duplicate
hold/approval; no-show records in the ledger; **a
home-address posting is rejected (422, never stored) and
an org/dock posting with coordinator assertion is
accepted (M5); a Guide MCP one-off call records query +
job ID and does not feed ranking (C1).**

**Exit gate:** all tests pass. Tag `phase-4`, push, stop.
**Eval subset:** hold conflict, decline re-plan, cancel release,
resume, persona-filter (404), approval idempotency.
**OKF update:** supervisor/guide READMEs, status enums frozen,
handoff (note 4a/4b split if used), prune.

## Phase 5 — Role contracts + Match Brief (BACKEND ONLY)

**Goal:** three role views as **backend contracts and tests**, and
the stored Match Brief a coordinator can actually send.

> **Backend-only clarification (locked).** Phase 5 builds **only**
> backend contracts, role-filtered read behaviour, Brief
> generation, and their tests. It builds **no** frontend, UI,
> video, or deck code, even though the phase name mentions role
> views. A “role view” in this phase means: the filtered API
> response for that role, proven by tests. Frontend work, if any,
> happens outside this backend plan, after the backend is tagged.

**Owns:** role-filtered reads (already enforced in Phase 4 — now
contract-tested per role), `match_briefs` generation, Brief data
in plan/ticket responses.
**Does not touch:** new matching logic, onboarding, Maps routes.
**No new endpoints:** the Brief is a stored rendering of a plan,
served via `GET /api/plans/{plan_id}` + `GET
/api/tickets/{ticket_id}`. Do not add a 53rd Brief endpoint.

**Tasks:**

1. Role contract tests: same ticket as coordinator, donor, and
   recipient — each response contains only that role's data
   (fields asserted, not just status codes), cross-role → 404.
   Donor response: own postings, matched pantries with org
   addresses + allocations, hold status, final pickup plan.
   Recipient response: own offers only, donor pickup org address
   + own delivery org address, confirm/decline state.
2. Match Brief generation, stored in `match_briefs` per approved
   plan version, with required sections: which org (name + org
   address, ZIP-area label); why them (human sentence + profile
   evidence); what they can actually take vs quantity/unit;
   clock + margin on the resolved clock; who it helps (tract
   poverty/no-vehicle, labelled area-level); drafted outreach
   message (coordinator sends it; the system does not send it);
   next two options; Maps link + attribution text where shown,
   distance labelled ZIP-area approximate.
3. **Guardrails callout (required, from stored data):**
   “Safety & Capacity Guardrails: Why Top Semantic Matches Were
   Filtered” — built only from `match_candidates` for that run:
   semantic rank before vs after, drop reason, contradiction flag,
   tie-break numbers. If candidate data is missing, the Brief
   must say so — never invent a guardrail example at render time.
4. Address rules in Brief data: recipient org address from the
   view; donor pickup org address from the live posting (or, for
   a starter-posting demo, explicitly labelled as having no donor
   address in starter data). Never a personal address. The
   donor address shown must be the validated posting address
   (`address_type: ORG_DOCK`, coordinator-asserted — see
   Tables / Phase 4, Review fix M5); an unvalidated address
   must never appear in a Brief.

**Test:** same-ticket three-role contract test passes; Brief for
an approved split plan contains every required section; its
guardrail callout matches the stored candidate rows for that run
(names/reasons compared programmatically, not eyeballed).

**Exit gate:** role tests + Brief tests pass, brief is stored and
reproducible for a judged plan after the run. Tag `phase-5`, push, stop.
**Eval subset:** guardrail callout fidelity, role leakage (none),
Brief completeness.
**OKF update:** Brief/role module README, handoff, prune.

## Phase 6 — Impact, fairness, equity, deserts, last-mile data

**Goal:** prove impact with stored numbers, before approval.

**Owns:** Impact & Fairness service, equity audit endpoint,
desert reads, last-mile view, history sinks for impact/equity.
**Does not touch:** onboarding, Maps routes, new matching rules
beyond the fairness boost specified here.

**Tasks:**

1. Endpoints: `GET /api/tickets/{ticket_id}/impact`, `GET
   /api/impact/dashboard`, `POST /api/equity/audit`, `GET
   /api/equity/{ticket_id}`, `GET /api/deserts`, `GET
   /api/deserts/{tract_geo_id}`, `GET
   /api/tickets/{ticket_id}/last-mile`. (`GET /api/allocations`
   was built in Phase 4; Phase 6 proves its fairness use.)
2. Impact Score **before** approval, using the locked formula
   (see Tables): total + Need/Rescue/Equity/Reliability
   breakdown, v1 vs v2 vs do-nothing, labelled estimated, stored
   on the plan. Sink approved plans to `impact_snapshots`
   without drift from the plan's stored breakdown.
3. Fairness ledger in full: rotation boost from `allocations`
   (served 0 times this week beats served 5 times on a tie/close
   call, per the recorded boost rule in code/config), tie-break
   recent-history now reads real ledger data (replacing Phase 3's
   neutral history — record this change in `CONTRACTS.md`/
   handoff), unknown history = neutral. Checker concentration
   check now uses the full ledger, not only within-run data.
4. Equity audit: `POST /api/equity/audit` runs the Checker-owned
   comparison for a plan, stores the result on the plan, returns
   chosen vs metro averages with `PASS/WARN` + numbers. Sink to
   `equity_audit_results`. Race is never an input.
5. Deserts + last-mile data: desert reads serve `v_rescue_deserts`
   with nearby recipients + whether a new pantry would clear the
   tract. Last-mile view serves, per allocated pantry: self-
   collect vs needs-driver, dock, window, ZIP distance + source,
   buffer, margin — from candidate/plan data, not recomputed
   with new external calls.

**Test:** hand-check the locked Impact fixture (Need 88, Rescue
100, Equity 82, Reliability 85 → total 89) against the endpoint;
fairness fixture — a pantry served 5 times is deprioritised vs an
unserved pantry on a tie; equity audit returns metro comparison
with numbers (badge alone fails); dashboard totals match the
sum of approved-plan snapshots without double-counting people.

**Exit gate:** all tests pass, including the hand-checked total.
Tag `phase-6`, push, stop. **Core ends here** (with Phases 9–10
still required for deploy/submission).
**Eval subset:** impact maths (hand-checked), fairness rotation,
equity numbers, desert rule.
**OKF update:** impact/fairness READMEs, boost rule recorded,
handoff, prune.

## Phase 7 — BONUS 1: Onboarding + desert flip

**Goal:** close the loop live: a new pantry becomes searchable
and a desert posting re-matches to it. Bonus, after core.

**Owns:** onboarding + profile-update endpoints in full,
verification gate, re-match link.
**Does not touch:** Maps routes (Phase 8).

**Tasks:**

1. Endpoints in full: `POST /api/recipients`, `PATCH
   /api/recipients/{recipient_id}` (stubbed/guarded in earlier
   phases if present — in this phase they must meet the full
   contract below). Do not add endpoints beyond the 52.
2. Onboarding input: org name, ZIP, cold/frozen/dock/transport/
   max pallets/service days, profile text. One intake path in
   the demo: form first; voice only if time remains, as the same
   backend contract, not a second path.
3. Writes: `app_recipients` + `recipient_embeddings`, atomically
   in demo logic — if the embeddings write fails, onboarding is
   incomplete and must report incomplete/not searchable. Set
   `verification_status`; a coordinator verification step (task +
   approval) moves `PENDING → VERIFIED/DEMO_SIMULATED`. Until
   verified, the pantry is **not** eligible for fresh/frozen.
   Log every change in `audit_log`/`audit_history`.
4. Re-match link (locked): onboarding alone does not auto-match,
   auto-approve, or auto-hold. After verification succeeds, the
   coordinator (or a Guide action card, approved by a human)
   calls `POST /api/tickets/{ticket_id}/match`, creating a new
   plan version in which the new pantry may appear.
5. Profile update: own-org only, writes `recipient_overrides`,
   re-embeds if profile text changed, verified/approved per the
   override status flow. Setting cold to `none` (as verified)
   pauses fresh matches for that pantry.
6. Desert flip demo path: a desert posting that previously
   matched far away re-matches to the newly verified local
   pantry; the desert view for that tract updates because
   coverage changed (tract data itself is never edited). Label
   the demo onboarding as simulated, ZIP-area location only.
   Prepare a screenshot/recorded fallback for the demo in case
   live embedding is slow on stage (fallback is a demo asset,
   not backend code).

**Test:** new pantry does not appear in search before onboarding,
appears **only after** both writes + verification, and does not
appear as fresh/frozen-eligible while `PENDING`; a desert posting
re-matches to it as a new plan version; a failed embeddings write
reports incomplete.

**Exit gate:** tests pass. Tag `phase-7`, push, stop. If time is
out before this phase, demo from `phase-6` and list onboarding as
future work in Phase 10 — no silent cut, report it.
**Eval subset:** onboarding searchable, verification gate, desert flip.
**OKF update:** onboarding README, handoff, prune.

## Phase 8 — BONUS 2: Maps geocode + routes

**Goal:** real donor addresses → drive times for top matches,
with fallback, never blocking core. Bonus, after onboarding.

**Owns:** Maps endpoints, `distance_pairs` cache in full, map
display contract (Leaflet/OpenStreetMap is a frontend contract
only — no frontend code in this phase).
**Does not touch:** matching rules, holds, onboarding logic.

**Tasks:**

1. Endpoints: `POST /api/maps/geocode`, `POST /api/maps/route`.
   First, re-check the Phase 0 API record: if Geocoding/Routes
   are not enabled in the event project, skip the live calls,
   keep the ZIP-distance fallback, record that in the handoff,
   and tag the phase as fallback-only. Do not let a Maps failure
   kill a match, and do not create a personal project/API key.
2. Geocode: donor pickup org address → lat/lon, once at posting
   time. On failure, fall back to the pickup ZIP centroid and
   label the result as fallback on the posting/candidate.
3. Routes: top matches only (the plan's allocated + next-option
   pantries, max the recorded top-matches cap in config — never
   all recipients), returning drive time + distance with source
   `GOOGLE_ROUTES`. On any failure, fall back to haversine ZIP
   distance with source `HAVERSINE_FALLBACK` and label it
   “estimated, not road time” in the response/Brief data.
4. Cache in `distance_pairs` (Firestore): pair hash key, lat/lon
   result, drive time, distance, source, expiry (run-scoped, max
   30 days). Never store Maps phone/text/photos. Attribution text
   for any Maps link shown is passed to the Brief store (Phase 5
   field) — update the Brief for an affected approved plan only
   as a new Brief record/version note, never by mutating history
   silently; record what was done in the handoff.

**Test:** a donor org address geocodes to a point or a labelled
ZIP fallback; top matches get a Routes time or a labelled
fallback; non-top matches still work on ZIP distance; a forced
Maps failure does not fail the match endpoint.

**Exit gate:** tests pass (or fallback-only is recorded with the
disabled-API evidence). Tag `phase-8`, push, stop. If Maps is
not enabled, demo from `phase-7`/`phase-6` and say so in Phase 10.
**Eval subset:** geocode fallback, routes fallback labelling.
**OKF update:** maps README, cache/authoritative-source note
(candidate row is authoritative for the Brief), handoff, prune.

## Phase 9 — Observability, audit, deploy, evals

**Goal:** deployable, auditable, testable. Judges score the repo,
deck, and video after the event with no Q&A, so evidence must be
in the repo.

**Owns:** audit export, telemetry endpoint, Cloud Run deploy,
replay snapshot, eval suite, retention policy file.
**Does not touch:** new product features. A feature found missing
here is a contract change, not a Phase 9 addition.

**Tasks:**

1. Endpoints in full: `GET /api/audit/export`, `GET
   /api/telemetry` (aggregates per the API notes; no new store
   beyond `telemetry_events`).
2. Audit sink: on run completion, sink Firestore `audit_log` →
   BigQuery `audit_history`; likewise confirm impact/equity
   sinks from Phase 6. Export reads Firestore for live runs and
   BigQuery for finished runs — test both paths.
3. Replay: every finished ticket can be replayed from its stored
   snapshot (view/derived version, tract-join version, weights,
   thresholds, model/prompt versions, tenant) and must reproduce
   the approved plan. Test replay on one split plan and one
   declined/re-planned plan.
4. Deploy: Cloud Run, stateless backend, state only in
   BigQuery/Firestore, config from env, one metro per run in the
   demo, model/Maps caps enforced. Use the canonical deploy
   template in the Canonical commands section (service
   `rescueguard-backend`, project/region from env — no
   literals). Record the deployed service URL + revision +
   actual region used in the handoff (URL is a deploy
   record, not a code value).
5. Retention/governance: write the retention policy file from the
   Tables retention table; record dataset source/licence list,
   model/prompt versions, and the food-safety disclaimer text
   served by Brief/Guide.
6. Eval suite — Atlanta only, deterministic checks only, no LLM
   judge in the suite: decoy, contradiction, tie, vocabulary
   mismatch, NULL shelf-life, Spinach-under-Lettuce, split,
   waste-reject, recall halt, recall `NOT_CHECKED`, hold
   conflict, decline re-plan, cancel release, onboarding
   searchable + verification gate, desert flip, impact maths
   (hand-checked fixture), fairness rotation, role leakage,
   **managed-MCP-call case (C1: a backend-invoked managed
   BigQuery MCP read-only call with query + job ID recorded,
   asserted not to feed ranking), Code Execution case
   (M1: a plan whose split/margin code + output are stored
   with `execution_source` recorded), pickup-address case
   (M5: home-address posting rejected, org/dock accepted).**
   Build cases only from Phase 1 verified Atlanta data. Do not
   copy another event's eval numbers or cases as Atlanta facts.
   Run the full suite here; earlier phases ran subsets only.

**Test:**

```bash
curl -s <deployed-url>/api/health
pytest backend/tests/ -k "contract or audit or telemetry or replay"
# full Atlanta eval suite — command recorded in the handoff
```

**Exit gate:** deployed `/api/health` answers, audit export
returns a full trail for a finished ticket from BigQuery and for
a live ticket from Firestore, replay reproduces both test plans,
full eval suite passes (or failures are listed as blockers with
no silent pass). Tag `phase-9`, push, stop.
**Eval subset:** the full suite (above).
**OKF update:** deploy/eval READMEs, `CONTEXT.md` current phase =
submission-ready, handoff with deployed URL/revision, prune.

## Phase 10 — Deck, video, freeze (submission, not backend code)

**Goal:** judges understand the build without the team in the
room. **This phase builds no backend code.** Bug fixes found
during rehearsal go through the owning phase's tests, are
committed with that phase named, and are re-tagged — do not add
features in Phase 10.

**Tasks (team, outside Antigravity backend sessions):**

1. Deck, short and front-loaded: problem; scenario (Atlanta,
   grocer, perishable offer, hours left); Track 1 named early;
   what the agent does; what was found (guardrails from stored
   candidates, Impact v1 vs v2, fairness, deserts); honest
   limitations (ZIP-area distances, generated operations data,
   planted cases labelled as teaching cases, Maps fallback if
   used, demo auth is not production auth, estimated households
   are not unique people, conversation deletion is an operator
   action not an API); what is next.
2. Demo script, rehearsed, two postings max: (a) perishable
   checker-reject → split → approve → hold → decline → re-plan;
   plus **one** bonus only if time is tight (onboarding desert
   flip **or** farm split, not both rushed).
3. Pitch video: screen-share, one narrator, running the actual
   deployed demo from the last tagged phase, with screenshots/
   recorded fallback ready if the live version misbehaves.
4. Freeze: the last tagged phase is the demo version. List any
   unfinished phases (for example Phase 7/8 if not tagged) as
   future work in the deck. Never silently trim a feature; any
   cut needs the user's approval at that moment and must be
   reported here.
5. Submit: upload deck + video to the submission portal with the
   repo link (the teammate repo above) + Skills project link,
   before the facilitator deadline. Record the submission
   confirmation in `docs/handoffs/phase-10.md`.

**Exit gate:** deck + video submitted, freeze tag matches the
demoed version, handoff records the submission. Tag `final`
on the frozen commit and push branch + tag. **Post-freeze
fixes:** if a bug fix is approved after `final` is tagged,
do NOT silently move `final` and do NOT force-push a tag.
Tag the fixed commit as `final-<n>` (for example `final-2`),
record the approval + new tag in the handoff, and demo
from the newest `final-<n>`.
**OKF update:** final handoff only; do not rewrite `CONTEXT.md`
history to make unfinished work look finished.

---

## Order summary — for the team wall

```text
0 Setup/Contracts (+ hard unit/clock gates)
→ 1 Data (verify/embed/join/desert)
→ 2 Matcher/Constraint/Recall (+ candidate evidence)
→ 3 Planner/Checker/Fixer
→ 4 Supervisor/Ticket/Hold/Tasks/Guide/Persona/Resume
→ 5 Role contracts + Match Brief (backend only)
→ 6 Impact/Fairness/Equity/Deserts
→ 7 BONUS Onboarding + Desert Flip
→ 8 BONUS Maps Geocode/Routes
→ 9 Deploy/Evals/Audit/Replay
→ 10 Deck/Video/Freeze (no backend code)
```

Core = Phases 0–6 + 9–10. Bonus = 7–8, in that order —
onboarding first, Maps second, because onboarding does not
depend on Maps API availability.

## What to do next — for Reyan and the team

1. **Reyan (already done):** Mac clone of the teammate repo
   succeeded. Next on that Mac, in that clone: check
   `git remote -v` (origin = the mattchainsaw repo), check
   `cat .gitignore` for `.env`, set the event project with
   `gcloud config set project <event-project>` using the
   actual project ID recorded in Part 1 (type the actual
   ID on your Mac — do not paste the variable name before
   the variable is set), export it as
   `GOOGLE_CLOUD_PROJECT` for the session, and confirm with
   `gcloud config get-value project`. A fresh Antigravity
   session reads the value from the lab config / Part 1
   record — it must not guess it. Do not run a starter
   reload — data is already ported. Do not push Part 1
   from that Mac in its current form (see C2 above).
2. **Team:** read this file + Part 1 (reference), then start
   **Phase 0 only** in a fresh Antigravity session with the
   prompt “start Phase 0”. Do not start Phase 1 until Phase 0's
   exit gate passes, including both hard gates.
3. **After each phase:** check the handoff, the tag, and the
   push before starting the next phase in a fresh session.

---

## Appendix — Exact Phase 0 prompt for Antigravity (copy-paste)

Copy everything inside the block below, paste it as the
first message in a **fresh** Antigravity session, in the
canonical session clone of the teammate repo. Do not add
Phase 1 work to that session.

```text
You are building RescueGuard, Challenge 2 (Food Equity),
Track 1 primary. Backend only.

FIRST, read these files in this order, and nothing else yet:
1. rescueguard-backend-build-plan.md — Part 2, the Backend
   Build Plan. This file is the SOLE build authority.
2. Part 1, RescueGuard Build Plan – Setup Information —
   REFERENCE ONLY. If Part 1 conflicts with Part 2, Part 2
   wins. Stop and report the conflict; do not silently
   resolve it. Do NOT push Part 1 to this repo in its
   current form — it contains a literal project ID. Record
   in your Phase 0 handoff: “Part 1 not pushed” or
   “Part 1 redacted, then pushed”.
3. The starter README.md in this repo. If it conflicts
   with Part 2, stop and report it.

REPO AND PROJECT — do not re-decide these:
- Repo: https://github.com/mattchainsaw/ai_for_impact_atl_2
  It is our teammate's shared team repo. Clone it, work
  in it, push to its origin. Do NOT fork it, do NOT use
  “Use this template”, do NOT create a separate team
  repo, do NOT re-point origin.
- Canonical working copy: THIS session's clone is the
  canonical copy for this phase. Reyan's Mac clone is
  inspection/review only unless he says otherwise.
  Record in the handoff: canonical clone path, branch,
  remote URL, last pushed commit and tag.
- GCP project: read it from gcloud config / the lab
  environment / the project recorded in Part 1. Set
  GOOGLE_CLOUD_PROJECT from that value in this session;
  do not guess it, and NEVER hardcode a project ID in
  code, schemas, config, examples, or any pushed file.
  Commands use $GOOGLE_CLOUD_PROJECT.
- Starter BigQuery tables are ALREADY ported by the user
  to dataset a4i_food in the event project. Do NOT
  reload, recreate, or overwrite them. Phase 0 checks
  EXISTENCE only. Counts/types/planted/tract verification
  is Phase 1, not this session.

YOUR TASK: Start Phase 0 ONLY, exactly as written in
Part 2, Phase 0. Do not start Phase 1. Do not build
matcher, planner, checker, holds, chat, or any product
logic. Do not build any frontend/UI/video/deck code.

Phase 0 must deliver, in order:
1. Clone/verify + C1–C3 closure recorded in the handoff:
   - C3 canonical clone path/branch/remote/last push.
   - C2 Part 1 push decision (above).
   - C1 MCP path locked: built-in managed BigQuery MCP
     at https://bigquery.googleapis.com/mcp, backend-
     invoked, read-only, one-off only. NOT MCP Toolbox.
     No Toolbox container.
   - Verify .gitignore covers .env BEFORE any push;
     add .env to .gitignore first if it does not.
   - Test push ONLY on a non-main test branch.
2. Repo layout from Part 2, frontend-contracts/README.md
   (“no UI code in this build”), CONTEXT.md from the
   Part 2 template, CONTRACTS.md frozen at 29 tables /
   52 endpoints, Pydantic schemas for every endpoint,
   and one skill stub per subsystem — matcher, constraint,
   planner, checker, supervisor, guide, data, onboarding,
   maps, impact-fairness, recall, last-mile.
3. Config from env in one place, CHECKER_MAX_ATTEMPTS=3,
   HOLD_MINUTES=10, pinned-or-frozen Python + google-adk
   + fastapi + google-cloud-bigquery +
   google-cloud-firestore + pydantic versions recorded
   (state pin-vs-freeze), model choice recorded (one
   MODEL_ID or Guide's own — as a contract note), and
   FastAPI with GET /api/health ONLY. Canonical local
   run command is:
     pip install -r requirements.txt
     uvicorn backend.app.main:app --host 0.0.0.0 --port 8080
   Verify it starts and curl -s localhost:8080/api/health
   answers. If it does not work in the lab, stop and
   record the actual working command in the handoff.
4. Secret grep test scoped ONLY to backend/, schemas/,
   config files and .env* (exclude *.md), plus:
     gcloud config get-value project
     gcloud firestore databases describe --project "$GOOGLE_CLOUD_PROJECT"
   Record: project from config, enabled APIs list,
   billing status (or BLOCKED — never work around it
   with a personal project), Firestore mode AND
   Firestore location, starter dataset/tables existence
   (bq ls a4i_food — existence only).
5. HARD GATE — units: record in CONTRACTS.md + handoff
   EITHER the crates-per-pallet conversion (value, who
   decided it, config location) OR a pallets-only donor
   quantity rule.
6. HARD GATE — resolved clock: record in CONTRACTS.md +
   handoff the resolved-clock rule (resolved_deadline,
   resolved_shelf_life_hours, shelf_life_source =
   FOODKEEPER / DONOR_FALLBACK / NOT_APPLICABLE, margin =
   resolved hours left − pickup window − travel buffer).
   Also record, as far as Phase 0 queries allow:
   recipient_id type, geo_id type, service_days format,
   distinct cold_storage values — or list each as a
   Phase 1 blocker.

STOP CONDITIONS — stop and report, do not proceed:
- Either hard gate (units or resolved clock) cannot be
  recorded. Phase 0 FAILS. Do not proceed to Phase 1,
  and do not let Phase 2/3 start on an assumption.
- Push access to the teammate repo fails on the test
  branch, Firestore is not Native mode, billing check
  is blocked, or Part 1 / starter README conflicts with
  Part 2. Report the exact output; do not work around
  it by forking, creating a personal project, or
  switching Firestore mode.

EXIT GATE — only when ALL of these pass, tag and stop:
project from config (not hardcoded), /api/health
answers via the canonical run command, contract +
secret tests pass, OKF files exist, Firestore Native +
location recorded, .gitignore + test push confirmed,
versions pinned/frozen, BOTH hard gates recorded,
architecture recorded in CONTEXT.md (FastAPI owns
everything; ADK only for Guide; ADK v2 graph fallback
only, subgraph only).
Then: write docs/handoffs/phase-0.md (what was built,
test commands + results, files changed, open risks,
canonical clone path/branch/remote, last pushed commit,
exact next step), commit on your phase branch, push the
branch, then:
  git tag phase-0
  git push origin phase-0
After Phase 0, no direct pushes to main — merge via a
reviewed PR or a coordinator merge recorded in the
handoff. Never force-push. Then STOP. Do not start
Phase 1 in this session. I will start Phase 1 in a new
session after reviewing your Phase 0 handoff.
```

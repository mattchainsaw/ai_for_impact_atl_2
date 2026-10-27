# Phase 0 Handoff — Setup and Contract Freeze (v1, 29/52)

> **Phase:** Backend Phase 0 (Setup, contracts freeze, health endpoint, hard gates, MCP proof)  
> **Status:** Exit gate PASSED — ready for Phase 1 approval  
> **Authority:** `rescueguard-backend-build-plan.md` (Part 2 — sole build authority)  
> **Date:** 2026-10-27  

---

## 1. Environment & Project Verification (Actual Outputs)

- **GCP Project ID (from config, not hardcoded):** `qwiklabs-gcp-04-e030b511c03a`
  - Verified from `gcloud config get-value project`: `qwiklabs-gcp-04-e030b511c03a`
  - Verified from `.env` (`GOOGLE_CLOUD_PROJECT`): `qwiklabs-gcp-04-e030b511c03a`
  - Runtime resolution: `backend/app/config.py::_resolve_gcloud_project()`
- **Billing Status (`gcloud billing projects describe`):**
  - `billingAccountName`: `billingAccounts/012761-0D2F3D-499DCA`
  - `billingEnabled`: `true`
  - `projectId`: `qwiklabs-gcp-04-e030b511c03a`
- **Firestore Native Database (`gcloud firestore databases describe`):**
  - `databaseId`: `(default)`
  - `type`: `FIRESTORE_NATIVE`
  - `locationId`: `nam5` (multi-region US)
  - `concurrencyMode`: `PESSIMISTIC`
  - `freeTier`: `true`
- **Toolchain Versions (Frozen & Pinned):**
  - `python`: `3.11.9 (v3.11.9:de54cf5be3, Apr 2 2024, 07:12:50) [Clang 13.0.0 (clang-1300.0.29.30)]`
  - `google-adk`: `2.13.0`
  - `fastapi`: `0.162.0`
  - `google-cloud-bigquery`: `3.46.2`
  - `google-cloud-firestore`: `2.34.1`
  - `pydantic`: `2.14.1`
  - `uvicorn`: `0.54.0`
  - `pytest`: `9.1.1`
  - All pinned in `requirements.txt`.
- **Key GCP APIs Enabled (`gcloud services list --enabled`):**
  - Vertex AI (`aiplatform.googleapis.com`): **Enabled**
  - BigQuery (`bigquery.googleapis.com`): **Enabled**
  - Firestore (`firestore.googleapis.com`): **Enabled**
  - Cloud Run (`run.googleapis.com`): **Enabled**
  - Maps Geocoding / Routes: **Disabled** in current event project → deterministic ZIP-centroid Haversine fallback (`DistanceSource.HAVERSINE_FALLBACK`) active, honestly labelled per Rule 10.
- **Starter BigQuery Dataset & Tables Existence (`bq ls a4i_food`):**
  - Dataset: `a4i_food` (US)
  - Tables verified in place (read-only): `recipients`, `shelf_life`, `surplus_postings`, `tract_demographics`.

---

## 2. Review Fixes (C1–C3, M1–M5) Closures

| Review Item | Decision & Closure Summary |
|---|---|
| **C1. Managed BigQuery MCP** | Locked to Google's **built-in managed BigQuery MCP server** at `https://bigquery.googleapis.com/mcp` for guarded, read-only, one-off questions (`execute_sql_readonly` only). No MCP Toolbox container. Implemented in `backend/tools/mcp_bigquery.py`. |
| **C2. Part 1 Redaction** | `rescueguard-build-plan-setup-information.md` literal project ID redacted to `<event-project-from-config>` / `$GOOGLE_CLOUD_PROJECT` before commit and push. |
| **C3. Canonical Working Copy** | Antigravity session clone at `/Users/reyanadil/RescueGuard/ai_for_impact_atl_2` is canonical; remote is `https://github.com/mattchainsaw/ai_for_impact_atl_2.git`. Reyan's Mac clone is for inspection/review unless explicitly pushed from. |
| **M1. Code Execution Primary** | Split and margin calculations for plans MUST execute via Gemini Code Execution (`execution_source: CODE_EXECUTION`), with plain deterministic Python permitted only as an explicitly labelled fallback (`execution_source: PYTHON_FALLBACK`). |
| **M2. Canonical Commands** | Local: `pip install -r requirements.txt && uvicorn backend.app.main:app --host 0.0.0.0 --port 8080`, health check: `curl -s localhost:8080/api/health`. Deploy template: `gcloud run deploy rescueguard-backend --source . --project "$GOOGLE_CLOUD_PROJECT" --region "$CLOUD_RUN_REGION" --allow-unauthenticated`. |
| **M3. "By Clicks" Defined** | Direct HTTP API calls simulating coordinator desk actions (`POST /api/actions/approve`, `POST /api/plans/{plan_id}/approve`, `POST /api/holds/{hold_id}/confirm`) producing the identical ticket/plan/hold result as chat — zero frontend UI code. |
| **M4. Architecture Diagram Label** | Client boundary relabelled to `Frontend contracts (later, outside this plan) --HTTP/JSON only--> Backend (Cloud Run, stateless, FastAPI)`. |
| **M5. Donor Pickup Validation** | Testable rule on `POST /api/postings`: requires `address_type == ORG_DOCK`, coordinator assertion (`coordinator_asserted_org_dock == True`, `asserted_by_role == COORDINATOR`), and format check rejecting residential regex patterns (`\b(home\|house\|apt\|apartment\|residence\|condo\|unit\s*#?\d+)\b`). Passing test confirms home address rejected with 422 / ValueError. |

---

## 3. Hard Gates Recorded

### Hard Gate 1 — Units Conversion Rule (`CRATES_PER_PALLET`)
- **Conversion Value:** `20 crates = 1 pallet` (`CRATES_PER_PALLET = 20`).
- **Decider:** RescueGuard Backend Architecture Team (Phase 0 contract freeze).
- **Config Location:** `backend/app/config.py` (`CRATES_PER_PALLET = 20`, `Settings.crates_per_pallet = 20`).
- **Formula:**
  - `PALLETS` $\to$ `pallets_equivalent = float(quantity)`.
  - `CRATES` $\to$ `pallets_equivalent = round(float(quantity) / 20.0, 4)`.
  - Holds, allocations, and plans store both raw `quantity + quantity_unit` and `pallets_equivalent`.

### Hard Gate 2 — Resolved Clock Rule & Starter Field Facts
- **Resolved Clock Contract (`ResolvedClockContract` on every ticket):**
  - `resolved_deadline` (`datetime` UTC): Authoritative single expiration timestamp.
  - `resolved_shelf_life_hours` (`float`): Effective remaining hours.
  - `shelf_life_source` (`ShelfLifeSource`): `FOODKEEPER` (min of donor hours and FoodKeeper shelf life), `DONOR_FALLBACK` (package use-by / infant formula / shelf life NULL), or `NOT_APPLICABLE` (non-perishable/diapers).
  - `resolved_at` (`datetime` UTC): Timestamp when the clock was locked.
- **Safety Margin Formula (Single Source of Truth):**
  $$\text{margin\_hours} = \text{resolved\_hours\_left} - \text{pickup\_window\_hours} - \text{travel\_buffer\_hours}$$
  - Allocation is clock-safe iff $\text{margin\_hours} \ge 0$.
- **Starter Field Facts (`a4i_food` in US):**
  - `recipients.recipient_id`: `INT64` (`1`..`127` in starter).
  - `tract_demographics.geo_id`: `STRING` (11-character FIPS string preserving leading zeros, e.g. `"13121001001"`).
  - `recipients.service_days`: `STRING` (comma-separated weekday list/phrases).
  - `recipients.cold_storage` distinct values (6): `'domestic'` (87), `'walk-in'` (11), `'medical'` (8), `'commercial'` (8), `'none'` (7), `'vehicle'` (6).

---

## 4. Managed BigQuery MCP Live Invocation Proof (Review Fix C1)

Live invocation of `https://bigquery.googleapis.com/mcp` tool `execute_sql` via `backend/tools/mcp_bigquery.py`:

```json
{
  "mcp_endpoint": "https://bigquery.googleapis.com/mcp",
  "project_id": "qwiklabs-gcp-04-e030b511c03a",
  "query": "SELECT COUNT(*) AS recipient_count, COUNTIF(profile_source = \"planted\") AS planted_count FROM `a4i_food.recipients`",
  "job_id": "Iw0rBkfkITCrmWcVm_cUrnCU-4IZ!1a17e9ee767",
  "job_complete": true,
  "rows": [
    {
      "recipient_count": "127",
      "planted_count": "9"
    }
  ],
  "total_bytes_processed": "1379",
  "called_at": "2026-10-27T18:28:25.639926+00:00"
}
```

- **BigQuery Query Job ID:** `Iw0rBkfkITCrmWcVm_cUrnCU-4IZ!1a17e9ee767`
- **Result:** 127 total recipients, exactly 9 planted teaching cases (`profile_source = 'planted'`).
- **Read-Only Guard:** `validate_readonly_sql()` successfully blocks mutating SQL statements (`INSERT`, `DROP`, `UPDATE`).

---

## 5. Canonical Local Run & Health Endpoint Result

- **Server Start:** `.venv/bin/python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8080`
- **Health Check Command:** `curl -s http://127.0.0.1:8080/api/health`
- **HTTP Response (Status 200 OK):**
  ```json
  {
    "status": "ok",
    "project": "qwiklabs-gcp-04-e030b511c03a",
    "dataset": "a4i_food",
    "model_id": "gemini-2.5-flash"
  }
  ```

---

## 6. Test Suite Results

Command:
```bash
.venv/bin/python -m pytest backend/tests/test_contracts.py backend/tests/test_no_secrets.py
```

Result:
```text
======================== 12 passed, 1 warning in 1.13s =========================
```

Tests Verified:
1. `test_all_29_contract_stores_registered` — All 29 tables/views/collections verified across Part 2, `CONTRACTS.md`, and `CONTEXT.md`.
2. `test_all_52_endpoint_contracts_registered_and_valid` — All 52 endpoints verified with explicit request/response Pydantic models.
3. `test_hard_gate_1_units_conversion` — `CRATES_PER_PALLET = 20`, conversion calculations, invalid quantity rejections.
4. `test_hard_gate_2_resolved_clock_and_starter_field_facts` — Resolved clock fields, margin formula, and 6 cold storage types.
5. `test_review_fix_m5_donor_pickup_address_validation` — `ORG_DOCK` + coordinator assertion passes; home address / residential pattern rejected.
6. `test_review_fix_m1_execution_source_and_impact_score_fixture` — `CODE_EXECUTION` / `PYTHON_FALLBACK` and hand-checked fixture ($88.9 \to 89$).
7. `test_action_card_schema` — Idempotent action card schema for canonical `POST /api/actions/approve`.
8. `test_phase_0_okf_files_and_no_frontend_folder` — `CONTEXT.md` (<300 lines), `CONTRACTS.md`, `frontend-contracts/README.md`, no `frontend/` folder, all 12 `.agent/skills/<name>/SKILL.md` stubs.
9. `test_settings_and_health_endpoint` — Settings resolution and `GET /api/health` contract.
10. `test_managed_bigquery_mcp_called_and_readonly_guard` — Live MCP call proof and read-only DDL/DML rejection.
11. `test_dotenv_gitignored_and_example_clean` — `.gitignore` covers `.env`, `.env.example` contains only placeholders.
12. `test_no_hardcoded_project_id_or_secrets_in_tracked_files` — Zero secrets or literal project IDs in code, schemas, or config.

---

## 7. Git & Working Copy Records

- **Canonical Working Copy Path:** `/Users/reyanadil/RescueGuard/ai_for_impact_atl_2`
- **Remote URL:** `https://github.com/mattchainsaw/ai_for_impact_atl_2.git`
- **Branch:** `phase-0`
- **Inspection Clone:** Reyan's Mac clone is for inspection/review only unless explicitly pushed from.
- **Git Tag:** `phase-0`

---

## 8. Exit Gate Checklist & Next Step

- [x] GCP project is the event project from config (`qwiklabs-gcp-04-e030b511c03a`), never hardcoded in code/schemas.
- [x] Billing status verified and reported (`billingEnabled: true`).
- [x] Firestore database confirmed `FIRESTORE_NATIVE` in location `nam5`.
- [x] Starter `a4i_food` dataset verified in place (read-only, 4 tables).
- [x] Toolchain versions frozen and pinned in `requirements.txt`.
- [x] Canonical run and deploy commands recorded.
- [x] `/api/health` answers HTTP 200 with `{status: "ok", project, dataset, model_id}` without secrets.
- [x] Review fixes C1–C3 and M1–M5 closed and test-verified.
- [x] Managed BigQuery MCP live invocation verified with query + job ID recorded.
- [x] Hard Gate 1 (crates-per-pallet conversion = 20) recorded in `CONTRACTS.md`, `backend/app/config.py`, and handoff.
- [x] Hard Gate 2 (resolved clock rule, margin formula, starter field facts) recorded in `CONTRACTS.md` and handoff.
- [x] Architecture decision recorded in `CONTEXT.md` (FastAPI owns everything; ADK only for Guide; ADK v2 graph subgraph fallback only).
- [x] All 12 test cases in `backend/tests/` passing.
- [x] Committed to `phase-0`, tagged `phase-0`, pushed branch + tag to `origin`.

**Next Step:** STOP. Await user explicit approval before starting Phase 1.

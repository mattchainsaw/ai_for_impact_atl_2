# Module: `app`

**Owner phase:** Phase 0
**Files:** `backend/app/main.py`
**Skill:** `.agent/skills/supervisor/SKILL.md`

## Purpose
Provides the FastAPI application entrypoint (`backend.app.main:app`) and the Phase 0 system endpoint (`GET /api/health`) returning `{status, project, dataset, model_id}` without secrets.

## Inputs and outputs
- **Inputs:** HTTP requests with optional `tenant_id` query parameter and `X-Request-ID` header.
- **Outputs:** `HealthResponse` and `PublicConfigResponse` Pydantic models.

## Tables / collections touched
- Reads: None in Phase 0 scaffold.
- Writes: None.

## Deterministic rules vs model calls
- Deterministic: All FastAPI route handlers are deterministic.
- Model calls: None (`Vertex AI via ADK` is used only for Guide chat in Phase 4).

## Failure modes and fallbacks
- Always returns HTTP 200 with active project and dataset metadata from `get_settings()`.

## Tests that cover this module
- `backend/tests/test_contracts.py::test_settings_and_health`


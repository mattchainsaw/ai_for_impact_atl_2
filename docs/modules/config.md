# Module: `config`

**Owner phase:** Phase 0
**Files:** `backend/app/config.py`, `.env.example`
**Skill:** `.agent/skills/data/SKILL.md`

## Purpose
Loads runtime environment configuration from `.env`, OS environment variables, or `gcloud config get-value project` without ever hardcoding a GCP project ID, region, or secret.

## Inputs and outputs
- **Inputs:** Environment variables (`GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION`, `CLOUD_RUN_REGION`, `GOOGLE_GENAI_USE_VERTEXAI`, `BQ_DATASET_STARTER`, `BQ_DATASET_APP`, `MODEL_ID`, `CHECKER_MAX_ATTEMPTS`, `HOLD_MINUTES`, `OPENFDA_MAX_CALLS_PER_RUN`, `CRATES_PER_PALLET`, `FIRESTORE_LOCATION`, `MCP_BIGQUERY_ENDPOINT`, `DEFAULT_TENANT_ID`, `SERVICE_NAME`) and `gcloud config` fallback.
- **Outputs:** Frozen `Settings` dataclass returned by `get_settings()`.

## Tables / collections touched
- Reads: None
- Writes: None

## Deterministic rules vs model calls
- Deterministic: 100% deterministic resolution of environment variables and `gcloud config`.
- Model calls: None.

## Failure modes and fallbacks
- If `GOOGLE_CLOUD_PROJECT` is unset or set to the placeholder `your-gcp-project-id`, falls back to `gcloud config get-value project`.

## Tests that cover this module
- `backend/tests/test_contracts.py::test_settings_and_health`
- `backend/tests/test_no_secrets.py`


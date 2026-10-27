# Module: `mcp_bigquery`

**Owner phase:** Phase 0
**Files:** `backend/tools/mcp_bigquery.py`
**Skill:** `.agent/skills/data/SKILL.md`

## Purpose
Implements the Review Fix C1 integration with the built-in Google-managed BigQuery MCP server (`https://bigquery.googleapis.com/mcp`) for guarded, read-only, one-off data questions via the backend. No MCP Toolbox container is used.

## Inputs and outputs
- **Inputs:** Read-only SQL query (`SELECT` / `WITH` only) and optional `project_id`.
- **Outputs:** Dictionary with `mcp_endpoint`, `project_id`, `query`, `job_id` (BigQuery `queryId`), `job_complete`, `rows`, `total_bytes_processed`, and `called_at`.

## Tables / collections touched
- Reads: `a4i_food.*` and `rescueguard_app.*` (read-only via `https://bigquery.googleapis.com/mcp` `execute_sql`).
- Writes: None (DDL/DML strictly blocked by `validate_readonly_sql`).

## Deterministic rules vs model calls
- Deterministic: Pre-call SQL read-only guard (`validate_readonly_sql`) rejects any non-`SELECT`/`WITH` query or forbidden DDL/DML keyword (`INSERT`, `UPDATE`, `DELETE`, `DROP`, `CREATE`, `ALTER`, `MERGE`, `TRUNCATE`).
- Model calls: None.

## Failure modes and fallbacks
- Raises `ValueError("MCP_READONLY_VIOLATION: ...")` before making any network call if a mutating SQL statement is supplied.

## Tests that cover this module
- `backend/tests/test_contracts.py::test_managed_bigquery_mcp_called_and_readonly_guard`


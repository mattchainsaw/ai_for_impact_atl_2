---
name: data
description: BigQuery starter verification, rescueguard_app derived tables/views, AI.EMBED, Firestore Native collections, and managed BigQuery MCP (Phases 0, 1).
---

# Skill: `data`

## When to read this
Read before editing any file in `backend/db/`, `backend/tools/mcp_bigquery.py`, or `backend/app/config.py`.

## Rules this skill enforces
- Rule 1: `a4i_food` starter tables (`recipients`, `surplus_postings`, `shelf_life`, `tract_demographics`) are strictly read-only. Never modify or reload them blindly.
- Review Fix C1: Use the built-in Google-managed BigQuery MCP (`https://bigquery.googleapis.com/mcp`) for guarded, read-only, one-off data questions via `backend/tools/mcp_bigquery.py`.

## Files in scope
- `backend/app/config.py`
- `backend/tools/mcp_bigquery.py`
- `backend/db/`
- `docs/modules/config.md`
- `docs/modules/mcp_bigquery.md`

## Files out of scope
- Do not edit `CONTRACTS.md` without an explicit contract-change note in the handoff.
- Do not touch `a4i_food.*`.

## Verification command
```bash
pytest -q backend/tests/test_contracts.py
```


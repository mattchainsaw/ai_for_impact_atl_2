---
name: recall
description: OpenFDA food enforcement recall checks, BigQuery openfda_cache, budget guard (OPENFDA_MAX_CALLS_PER_RUN=240), and recall holds (Phase 2, 5).
---

# Skill: `recall`

## When to read this
Read before editing any file in `backend/tools/openfda.py` or `backend/app/routers/recalls.py`.

## Rules this skill enforces
- Enforce `OPENFDA_MAX_CALLS_PER_RUN = 240` and cache responses in `rescueguard_app.openfda_cache`.
- Rule 6: Clearing an active recall hold (`POST /api/recalls/holds/{recall_hold_id}/clear`) requires coordinator role and audit logging in `rescueguard_app.recall_hold_log`.

## Files in scope
- `backend/tools/openfda.py`
- `backend/app/routers/recalls.py`
- `docs/modules/recall.md`

## Files out of scope
- Do not edit `CONTRACTS.md` without an explicit contract-change note in the handoff.
- Do not touch `a4i_food.*`.

## Verification command
```bash
pytest -q backend/tests/test_contracts.py
```


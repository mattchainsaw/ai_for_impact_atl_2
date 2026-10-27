---
name: onboarding
description: Conversational recipient onboarding, verification gate, promotion to app_recipients, live AI.EMBED, and cold-chain desert flip (Phase 7 / Bonus 1).
---

# Skill: `onboarding`

## When to read this
Read before editing any file in `backend/services/onboarding.py` or `backend/app/routers/onboarding.py`.

## Rules this skill enforces
- Rule 1: Never insert into `a4i_food.recipients`. New recipients are written to `rescueguard_app.app_recipients` and surfaced via `rescueguard_app.v_Recipients_Effective`.
- Rule 6: Promotion to active matching (`POST /api/onboarding/{onboarding_id}/promote`) requires verification plus human approval (`APPROVE_ONBOARDING_PROMOTION`).

## Files in scope
- `backend/services/onboarding.py`
- `backend/app/routers/onboarding.py`
- `docs/modules/onboarding.md`

## Files out of scope
- Do not edit `CONTRACTS.md` without an explicit contract-change note in the handoff.
- Do not touch `a4i_food.*`.

## Verification command
```bash
pytest -q backend/tests/test_contracts.py
```


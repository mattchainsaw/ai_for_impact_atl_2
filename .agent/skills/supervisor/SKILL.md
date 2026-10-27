---
name: supervisor
description: End-to-end match run orchestration, 10-minute internal holds, human approval gate, and decline re-routing (Phase 3).
---

# Skill: `supervisor`

## When to read this
Read before editing any file in `backend/agents/supervisor.py`, `backend/services/approvals.py`, or `backend/services/holds.py`.

## Rules this skill enforces
- Rule 5: Holds (`HOLD_MINUTES = 10`) are internal capacity reservations in Firestore `holds`; never send external notifications when a hold is created.
- Rule 6: Human approval (`POST /api/approvals/{action_id}/approve`) gates every external commitment, split plan, decline re-route, recall clearance, or onboarding promotion.
- Review Fix M3: Direct API calls ("by clicks") and Guide chat actions produce the exact same `pending_approvals` ticket and audit trail.

## Files in scope
- `backend/agents/supervisor.py`
- `backend/services/approvals.py`
- `backend/services/holds.py`
- `docs/modules/supervisor.md`

## Files out of scope
- Do not edit `CONTRACTS.md` without an explicit contract-change note in the handoff.
- Do not touch `a4i_food.*`.

## Verification command
```bash
pytest -q backend/tests/test_contracts.py
```


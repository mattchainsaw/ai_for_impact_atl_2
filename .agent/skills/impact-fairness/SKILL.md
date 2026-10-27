---
name: impact-fairness
description: Area-level equity audit, fairness ledger saturation tracking, and cold-chain desert cell computation (Phase 6).
---

# Skill: `impact-fairness`

## When to read this
Read before editing any file in `backend/services/equity.py`, `backend/services/fairness.py`, or `backend/services/deserts.py`.

## Rules this skill enforces
- Rule 8: Need comes from census tract `poverty_rate`, `no_vehicle_rate`, and `assistance_rate`. Fit comes first, area need second, fairness over time (`fairness_ledger`) third. Never use race or `reported_income`.
- Rule 10: Label household impact numbers as `ESTIMATED_CAPACITY` and never sum across overlapping deliveries as unique individuals.

## Files in scope
- `backend/services/equity.py`
- `backend/services/fairness.py`
- `backend/services/deserts.py`
- `docs/modules/impact_fairness.md`

## Files out of scope
- Do not edit `CONTRACTS.md` without an explicit contract-change note in the handoff.
- Do not touch `a4i_food.*`.

## Verification command
```bash
pytest -q backend/tests/test_contracts.py
```


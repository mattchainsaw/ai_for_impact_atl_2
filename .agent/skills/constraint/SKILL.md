---
name: constraint
description: Deterministic hard-constraint filtering for cold/frozen storage, clock margin, capacity, service days, dietary rules, and contradiction traps (Phase 2).
---

# Skill: `constraint`

## When to read this
Read before editing any file in `backend/agents/constraint.py`, `backend/services/clock.py`, or `backend/services/flags.py`.

## Rules this skill enforces
- Rule 3: Structured fields win on safety; text wins on restrictions. Flag contradictions (`Harborview Neighbors Trust`, `recipient_id = 120`) with `contradiction_flag = true` and use the safer interpretation.
- Rule 4: Resolve the clock once (`resolved_deadline`, `resolved_shelf_life_hours`, `shelf_life_source`, `resolved_at`) and enforce `margin = resolved_hours_left - pickup_window_hours - travel_buffer_hours >= 0`.
- Rule 9: Record exact `drop_reason` (`NO_COLD_STORAGE`, `CONTRADICTION_UNSAFE`, `CLOCK_MARGIN_NEGATIVE`, etc.) for every eliminated candidate.

## Files in scope
- `backend/agents/constraint.py`
- `backend/services/clock.py`
- `docs/modules/constraint.md`

## Files out of scope
- Do not edit `CONTRACTS.md` without an explicit contract-change note in the handoff.
- Do not touch `a4i_food.*`.

## Verification command
```bash
pytest -q backend/tests/test_contracts.py
```


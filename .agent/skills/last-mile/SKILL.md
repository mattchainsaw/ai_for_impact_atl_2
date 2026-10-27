---
name: last-mile
description: Last-mile pickup and transport mode selection (recipient reefer van, donor drop, hub-and-spoke mobile pantry, volunteer courier) (Phase 6).
---

# Skill: `last-mile`

## When to read this
Read before editing any file in `backend/services/last_mile.py` or `backend/app/routers/last_mile.py`.

## Rules this skill enforces
- Rule 4: Every last-mile option must preserve a non-negative clock safety margin (`resolved_hours_left - pickup_window_hours - travel_buffer_hours >= 0`).
- Prioritize recipients with `refrigerated_transport = True` (`RECIPIENT_REEFER_VAN`) or pair a regional hub (`loading_dock = True`) with a mobile pantry (`cold_storage = 'vehicle'`, `HUB_AND_SPOKE_MOBILE`).

## Files in scope
- `backend/services/last_mile.py`
- `backend/app/routers/last_mile.py`
- `docs/modules/last_mile.md`

## Files out of scope
- Do not edit `CONTRACTS.md` without an explicit contract-change note in the handoff.
- Do not touch `a4i_food.*`.

## Verification command
```bash
pytest -q backend/tests/test_contracts.py
```


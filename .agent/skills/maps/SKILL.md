---
name: maps
description: Geocoding, route distance/duration matrix, BigQuery routes_cache, and deterministic ZIP-centroid Haversine fallback (Phase 8 / Bonus 2).
---

# Skill: `maps`

## When to read this
Read before editing any file in `backend/tools/maps.py` or `backend/app/routers/maps.py`.

## Rules this skill enforces
- Rule 10: Every distance and travel time must be honestly labelled with `distance_source` (`GOOGLE_ROUTES` when Google Routes API is enabled and used, or `ZIP_CENTROID_HAVERSINE` when falling back to ZIP-centroid Haversine calculation).
- Cache route lookups in `rescueguard_app.routes_cache`.

## Files in scope
- `backend/tools/maps.py`
- `backend/app/routers/maps.py`
- `docs/modules/maps.md`

## Files out of scope
- Do not edit `CONTRACTS.md` without an explicit contract-change note in the handoff.
- Do not touch `a4i_food.*`.

## Verification command
```bash
pytest -q backend/tests/test_contracts.py
```


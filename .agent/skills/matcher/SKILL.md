---
name: matcher
description: Semantic candidate generation via BigQuery AI.EMBED (gemini-embedding-2) and brute-force VECTOR_SEARCH over recipient_embeddings (Phase 2).
---

# Skill: `matcher`

## When to read this
Read before editing any file in `backend/agents/matcher.py`, `backend/services/matching.py`, or `schemas/api.py` (candidate models).

## Rules this skill enforces
- Rule 1: Never modify `a4i_food` starter tables; query `rescueguard_app.recipient_embeddings` and `rescueguard_app.v_Recipients_Effective`.
- Rule 2: Retrieval is not decision — `VECTOR_SEARCH` generates top-25 semantic candidates using `options => '{"use_brute_force":true}'` on the 127-row corpus; never let vector similarity bypass hard constraints.
- Rule 9: Persist `semantic_rank` and `semantic_distance` in `rescueguard_app.match_candidates` so Guardrail Transparency can explain filtered near-misses (`Greenline Community Pantry`).

## Files in scope
- `backend/agents/matcher.py`
- `docs/modules/matcher.md`
- `backend/tests/test_matcher.py`

## Files out of scope
- Do not edit `CONTRACTS.md` without an explicit contract-change note in the handoff.
- Do not touch `a4i_food.*`.

## Verification command
```bash
pytest -q backend/tests/test_contracts.py
```


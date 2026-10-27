---
name: checker
description: Deterministic plan verification, fixer loop, and loop-guard enforcement (max 3 attempts, duplicate hash & reason detection) (Phase 3).
---

# Skill: `checker`

## When to read this
Read before editing any file in `backend/agents/checker.py` or `backend/tests/test_checker.py`.

## Rules this skill enforces
- Rule 7: Run at most `CHECKER_MAX_ATTEMPTS = 3` attempts; detect duplicate `plan_hash` and repeated `violation_codes`; make zero external network/API calls inside the checker/fixer loop; escalate to `HUMAN_ESCALATION` if exhausted.
- Persist every attempt in `rescueguard_app.checker_attempts`.

## Files in scope
- `backend/agents/checker.py`
- `docs/modules/checker.md`
- `backend/tests/test_checker.py`

## Files out of scope
- Do not edit `CONTRACTS.md` without an explicit contract-change note in the handoff.
- Do not touch `a4i_food.*`.

## Verification command
```bash
pytest -q backend/tests/test_contracts.py
```


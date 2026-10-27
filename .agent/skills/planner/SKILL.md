---
name: planner
description: Multi-lens tradeoff planning (SPEED_OPTIMAL, EQUITY_OPTIMAL, LOAD_SPLIT, RESILIENCE_FALLBACK) and Gemini Code Execution split/margin math (Phase 2).
---

# Skill: `planner`

## When to read this
Read before editing any file in `backend/agents/planner.py` or `backend/tools/code_exec.py`.

## Rules this skill enforces
- Review Fix M1: Split and clock-margin maths for a plan MUST go through Gemini Code Execution (`execution_source = "CODE_EXECUTION"`), with deterministic Python as a labelled fallback only (`execution_source = "PYTHON_FALLBACK"`).
- Hard Gate 1: Convert crates to pallets using `CRATES_PER_PALLET = 20` from `backend/app/config.py`.
- Rule 8: Need comes from census tract `poverty_rate`, `no_vehicle_rate`, and `assistance_rate`, plus `fairness_ledger` saturation; never use race or `reported_income`.

## Files in scope
- `backend/agents/planner.py`
- `backend/tools/code_exec.py`
- `docs/modules/planner.md`

## Files out of scope
- Do not edit `CONTRACTS.md` without an explicit contract-change note in the handoff.
- Do not touch `a4i_food.*`.

## Verification command
```bash
pytest -q backend/tests/test_contracts.py
```


---
name: guide
description: Vertex AI ADK conversational Guide agent for Donor, Recipient, and Coordinator personas (Phase 4).
---

# Skill: `guide`

## When to read this
Read before editing any file in `backend/agents/guide.py` or `backend/app/routers/chat.py`.

## Rules this skill enforces
- Use Vertex AI via ADK (`google-adk`) for the Guide chat interface only; FastAPI owns all deterministic matching, planning, checking, and approval persistence.
- Guide chat never bypasses the human approval gate (`pending_approvals`); proposing an action via chat creates the same `ActionProposal` ticket as direct API calls.

## Files in scope
- `backend/agents/guide.py`
- `backend/app/routers/chat.py`
- `docs/modules/guide.md`

## Files out of scope
- Do not edit `CONTRACTS.md` without an explicit contract-change note in the handoff.
- Do not touch `a4i_food.*`.

## Verification command
```bash
pytest -q backend/tests/test_contracts.py
```


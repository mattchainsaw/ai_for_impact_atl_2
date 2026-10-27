# Phase 5 Handoff: Role Contracts & Match Brief

- **Branch**: `phase-5`
- **Tag**: `phase-5`
- **Scope**: Backend contracts and stored Match Briefs only. No frontend or UI code created.

## Implemented Deliverables
1. **Match Brief Generation & Persistence**:
   - Implemented in `backend/services/briefs.py`.
   - Persisted to Firestore collection `match_briefs`.
   - Generated on plan approval via `backend/services/approvals.py`.
2. **Three Role Contracts & Strict 404 Isolation**:
   - `filter_ticket_for_role` and `filter_plan_for_role` in `backend/services/auth.py`.
   - Served directly via `GET /api/tickets/{ticket_id}` and `GET /api/plans/{plan_id}`.
   - Cross-role, cross-donor, and cross-recipient reads return HTTP 404.
3. **Guardrails Callout**:
   - Grounded strictly in stored `match_candidates` for that ticket run.
4. **Address Security**:
   - Suppresses unvalidated/residential addresses. Only exposes validated `ORG_DOCK`.

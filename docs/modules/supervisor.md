# Supervisor Module Architecture

## Overview
The RescueGuard Supervisor orchestrates the entire ticket lifecycle across postings, semantic matching, checker verification, plan approval, hold management, task execution, and pickup completion.

## State Machine & Ticket Steps
A ticket transitions through strictly defined `TicketStep` states:
1. `CREATED`: Live donor posting or starter posting created.
2. `MATCHED`: Candidate pantry retrieval from BigQuery complete.
3. `CHECKED`: Safety, capacity, schedule, and equity checks verified by Checker.
4. `PROPOSED`: Plan v1 presented to coordinator desk or Guide chat.
5. `HELD`: Plan approved by coordinator, creating transactional 10-minute holds.
6. `CONFIRMED`: All recipient holds confirmed.
7. `RE_PLANNED`: Triggered on coordinator plan rejection or recipient decline; increments `plan_version` and promotes next candidate.
8. `CANCELLED`: Donor cancellation; immediately releases active holds and notifies recipients.

## Consequential Action Isolation & ActionCards
In compliance with strict safety guardrails:
- Natural language chat messages (e.g. "yes", "approve") in Guide Chat **never** trigger consequential state mutations directly.
- The assistant emits structured `ActionCard` objects (type `PLAN`, action `APPROVE`).
- Consequential mutations occur solely through authenticated `POST /api/actions/approve` or direct API calls (`/api/plans/{id}/approve`).
- Double-approval is blocked with HTTP 409 Conflict.

## Checkpoint & Crash Resilience
- All ticket state, approved tasks (`tasks_already_approved`), active holds (`holds_already_started`), and current plan versions are persisted in Firestore.
- Calling `GET /api/tickets/{ticket_id}` returns the complete resumed checkpoint state without duplicating holds or re-running expensive external queries.

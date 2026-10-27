# Tickets & Matching Orchestrator (`backend/services/tickets.py`)

## 1. Overview
The Tickets service manages the ticket lifecycle from posting creation, through semantic recipient matching, recall guards, and iterative plan generation.

## 2. Key Capabilities
- **Posting Source Support:**
  - `STARTER`: Reads from BigQuery `a4i_food.surplus_postings`. Ticket ID: `ticket-starter-{posting_id}`.
  - `LIVE_DONOR`: Reads from Firestore `postings`. Ticket ID: `ticket-live-{posting_id}`.
  - Prevents ID collisions across sources.
- **Clock Resolution:** Resolves shelf-life hours deterministically via Hard Gate 2 (`resolve_clock`):
  - Non-food: `NOT_APPLICABLE`.
  - Packaged / dairy / formula: `DONOR_FALLBACK`.
  - FoodKeeper book match: `min(fk_shelf_life, hours_available)`.
- **End-to-End Matching Pipeline (`POST /api/tickets/{ticket_id}/match`):**
  1. Recall Guard: Evaluates item text; halts with `FDA_HALTED` if Class I/II recall is active.
  2. Candidate Matcher: Vector search over embeddings with deterministic constraints.
  3. No-Viable Match Guard: If 0 pantries are eligible, returns HTTP 422 with structured `NoViableMatchFallback` response.
  4. Plan Generation & Checker/Fixer Loop: Runs initial plan creation, executes independent checker, and invokes fixer loop (up to 3 attempts) until passed or escalated.
- **REST Endpoints:**
  - `POST /api/postings`, `GET /api/postings/{id}`, `GET /api/postings`
  - `POST /api/tickets`, `GET /api/tickets/{id}`, `GET /api/tickets`
  - `POST /api/tickets/{id}/match`
  - `GET /api/tickets/{id}/plans`, `GET /api/plans/{plan_id}`
  - `GET /api/tickets/{id}/parameters`, `POST /api/tickets/{id}/parameters`


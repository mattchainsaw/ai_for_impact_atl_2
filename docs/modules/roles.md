# Role Contracts & Access Isolation

## Persona Views (Backend Contracts)
Enforced across `GET /api/tickets/{ticket_id}` and `GET /api/plans/{plan_id}`:

### 1. Coordinator View
- Full access to all internal ticket checkpoints, tasks, parameters, candidates, and full Match Brief.

### 2. Donor View
- Access restricted to own postings, matched pantries with org addresses, allocated quantities, hold statuses, and final pickup schedule.
- Internal coordinator parameters and cross-donor records return `404 Not Found` (never 403).

### 3. Recipient View
- Access restricted to own offer, allocated quantity/unit, hold confirmation state, own delivery address, and donor pickup org dock address.
- Competing recipients and cross-recipient reads return `404 Not Found` (never 403).

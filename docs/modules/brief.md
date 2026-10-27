# Match Brief Module

## Overview
The Match Brief is a stored rendering of an approved allocation plan, persisted to Firestore collection `match_briefs`.
Served via:
- `GET /api/plans/{plan_id}`
- `GET /api/tickets/{ticket_id}`

No 53rd endpoint was added.

## Structure & Sections
1. **Which Org**: Recipient name, org delivery address, and `ZIP-area approximate` badge.
2. **Why Them**: Verified capacity and profile evidence text excerpt.
3. **What They Can Take**: Capacity statement against allocated quantities and units.
4. **Resolved Clock & Margin**: FoodKeeper shelf-life, pickup window, travel buffer, and safety margin hours.
5. **Who It Helps**: Census tract area-level aggregate poverty and no-vehicle household rates.
6. **Next Two Options**: Runner-up eligible matches for rapid re-dispatch if declined.
7. **Attribution**: `Google Routes API (ZIP-area approximate)`.
8. **Drafted Coordinator Outreach**: Ready-to-send draft message (sent manually by coordinator; never sent automatically by system).
9. **Safety & Capacity Guardrails Callout**: Built strictly from `match_candidates` for that ticket run; displays semantic rank before/after, filter reason, contradiction flags, and tie-break stats. Missing data is noted explicitly; examples are never synthesized.

## Address Protection Rules
- Recipient address originates from validated recipient profile dock.
- Donor pickup address is displayed strictly when asserted by coordinator as `address_type: ORG_DOCK`.
- Starter postings are explicitly labelled as having no donor address.
- Unvalidated or residential addresses are strictly suppressed to eliminate PII leakage.


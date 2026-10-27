# Holds and Allocations Module Architecture

## Dual Store Separation (Part 2, line 710)
RescueGuard enforces strict separation between transactional holds and enduring allocations:
- **Holds (`holds` collection):** Internal transactional locks created *only* inside plan approval. Holds feature a 10-minute timeout window (`HOLD_MINUTES = 10`), driving recipient inbox locks and preventing over-commitment.
- **Allocations (`allocations` collection):** Enduring assignment and fairness ledger records derived from approved holds. Allocations persist long-term outcomes (`CONFIRMED`, `DECLINED`, `NO_SHOW`, `COMPLETED`), tracking historical service counts for equity and rotation algorithms.

## Lifecycle & Transitions
1. **Plan Approval:** Creates 10-minute `ACTIVE` holds for each recipient allocated in the plan. Allocations are initialized.
2. **Hold Expiry:** If a hold is not confirmed within 10 minutes, background evaluation marks it `EXPIRED`, releasing capacity back to the pool.
3. **Recipient Decline:** Allows a recipient to decline an allocation before confirmation. The decline marks the hold `RELEASED`, the allocation `DECLINED`, promotes the next eligible pantry from candidate store, creates a new plan version ($v_{current} + 1$), and keeps non-declined holds active.
4. **Donor Cancellation:** Cancelling a ticket immediately transitions all active holds to `RELEASED` and dispatches recipient notifications.
5. **No-Show:** If a recipient fails to collect scheduled food, the coordinator records `NO_SHOW` in the allocations collection, preventing unearned fairness credit.

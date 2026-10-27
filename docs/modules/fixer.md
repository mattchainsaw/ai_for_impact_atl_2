# Fixer Module (`backend/services/fixer.py`)

## 1. Overview
The Fixer service takes plans rejected by the Checker, analyzes the specific rejection reasons, and deterministically rewrites only the flagged parts.

## 2. Core Operational Rules
- **Zero External Calls:** To ensure rapid, deterministic loop convergence, all fixer calculations run in-process using deterministic Python (no external API or network calls inside the fixer loop).
- **Loop Guards:**
  1. `fixer_attempt_count >= 3`: Immediately halts and escalates for human coordinator review.
  2. `current_plan_hash == last_plan_hash`: If no progress was made between iterations, immediately halts and escalates.
  3. `primary_checker_reason == last_checker_reason`: If the exact same reason is flagged twice consecutively, immediately halts and escalates.
  4. Escalation preserves the plan in Firestore, marks escalation notes, and terminates without infinite looping.
- **Append-Only Generation:** Produces `v(N+1)` as a distinct new document in Firestore with `fixer_changes` and incremented `fixer_attempt_count`.
- **Targeted Corrections:**
  - Waste: Expands split allocations across 2nd and 3rd viable pantries so 100% of the load is placed.
  - Incompatible Storage: Excludes flagged pantries from viable candidate pool and re-splits across compliant pantries.
  - Capacity Overloads: Enforces pantry caps and redistributes excess pallets to adjacent candidates.


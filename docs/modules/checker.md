# Checker / Auditor Module (`backend/services/checker.py`)

## 1. Overview
The Checker / Auditor service provides independent, rule-based verification of proposed distribution plans, completely decoupled from the Planner and Fixer.

## 2. Verification Rules
1. **Waste Check:** Flags any unallocated surplus (`allocated_quantity < total_quantity - 0.01`).
2. **Unsafe Fit (Temperature):** Flags allocations of refrigerated/frozen goods to pantries lacking cold storage (`cold_storage == 'none'`) or frozen storage.
3. **Capacity Overload:** Flags allocations where `pallets_equivalent > max_pallets`.
4. **Resolved Clock Margins:** Flags negative delivery clock margins (`clock_margin_hours < 0.0`), asserting that donor deadlines and pickup windows are respected.
5. **Within-Run Concentration:** Flags duplicate allocations to the same pantry within a single distribution run.
6. **Equity & Demographic Skew:** Evaluates chosen candidate tract demographic averages against Atlanta metro benchmarks (`metro_poverty = 0.174`, `metro_no_vehicle = 0.118`). Produces a structured `EquityCheckerResult` with actual numbers.

## 3. Decision Outcomes
- **Pass:** Sets `PlanStatus.DRAFT` (or ready for Phase 4 supervisor approval), with empty `checker_reasons`.
- **Fail:** Sets `PlanStatus.CHECKER_REJECTED` with specific, descriptive `checker_reasons` stored directly on the plan document in Firestore.


# Planner / Splitter Module (`backend/services/planner.py`, `backend/services/code_exec.py`)

## 1. Overview
The Planner / Splitter service converts verified viable recipient candidates and posting quantities into actionable distribution plans with append-only versions (`v1`, `v2`, `v3`).

## 2. Core Responsibilities
- **Capacity & Unit Conversions:** Evaluates surplus loads using the Phase 0 crates-per-pallet rule (`crates_per_pallet = 20`).
- **Single vs. Split Allocation:**
  - If a single pantry can hold the full load and splitting is disabled/unnecessary, allocates the whole load.
  - If load exceeds capacity, splits across 2–3 verified pantries within capacities, pickup windows, and temperature constraints.
- **Code Execution Integration (Review Fix M1):**
  - Split and clock margin maths are executed through Vertex AI Gemini Code Execution (`ToolCodeExecution` with `gemini-2.5-flash`).
  - Inputs: candidate allocations, quantities, unit, capacities, pickup windows, travel buffers, resolved hours left.
  - Plan output fields: stores `{execution_code, execution_output, execution_source}` on each plan.
  - Deterministic Python calculation is an explicit labeled fallback (`ExecutionSource.PYTHON_FALLBACK`) with fallback reason recorded.
- **Append-Only Immutability:** Each modification or fix produces a new plan version in Firestore `plans` (`plan-{ticket_id}-v{version}`); existing plans are never mutated in place.
- **Deterministic Hashing:** Calculates `plan_hash` (SHA-256 over recipient allocations and quantities) to identify cycles and enable fixer loop guards.


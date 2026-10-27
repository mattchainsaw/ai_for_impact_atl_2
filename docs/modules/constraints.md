# Module: `constraints`

**Owner phase:** Phase 2  
**Files:** `backend/services/constraints.py`  
**Skill:** `.agent/skills/constraint/SKILL.md`  

## Purpose
Enforces deterministic safety, capacity, schedule, and profile consistency rules on recipient candidates. Decides whether each candidate is `ELIGIBLE`, `FILTERED`, or `FLAGGED` (Needs human check). Structured database columns always supersede unstructured profile text; any detected contradiction between columns and free-text profile automatically flags the candidate without guessing.

## Inputs and outputs
- **Public Functions:**
  - `detect_profile_contradictions(...) -> Tuple[bool, List[str]]`: Analyzes dock, refrigeration, and service day claims across structured vs profile text.
  - `evaluate_candidate_constraints(...) -> Tuple[CandidateStatus, Optional[str], bool, List[str]]`: Evaluates cold storage, frozen storage, pallet capacity, margin hours, schedule, and contradictions.
- **Outputs:**
  - `status: CandidateStatus` (`ELIGIBLE`, `FILTERED`, `FLAGGED`)
  - `reason: Optional[str]` (Detailed human-readable explanation of rejection or flag)
  - `contradiction_flag: bool` (True if columns and text contradict)
  - `evidence: List[str]` (Specific evidentiary statements supporting the verdict)

## Invariants & Rules
1. **Cold Chain Compliance:**
   - Perishable/refrigerated items require `cold_storage IN ('commercial', 'domestic', 'walk_in', 'reach_in')`. If `cold_storage == 'none'`, status is `FILTERED`.
   - Frozen items require `frozen_storage == True`.
2. **Pallet Capacity:**
   - Requires `max_pallets >= pallets_needed`.
3. **Margin Hours:**
   - Requires `margin_hours >= 0.0`. If travel buffer + pickup window exceeds resolved shelf-life hours, status is `FILTERED`.
4. **Columns Beat Text & Contradiction Flagging:**
   - Ridgeway Avenue Food Ministry (ID 123) / Harborview (ID 120): If structured column states `loading_dock = False` but profile text claims "dock height loading bay", the column wins and `CandidateStatus.FLAGGED` is set (`contradiction_flag = True`). Never an auto-match guess.

## Tests that cover this module
- `backend/tests/test_phase_2.py::test_contradiction_case_is_flagged`
- `backend/tests/test_phase_2.py::test_no_cold_pantry_never_in_viable_list`

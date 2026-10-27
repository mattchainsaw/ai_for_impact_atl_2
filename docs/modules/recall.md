# Module: `recall`

**Owner phase:** Phase 2  
**Files:** `backend/services/recall.py`  
**Skill:** `.agent/skills/recall/SKILL.md`  

## Purpose
Integrates openFDA Food Enforcement API to guard food safety before surplus postings are matched. Checks live FDA recalls for active ongoing enforcement actions against donor product items. HALTED stops the item immediately. Any network or service failure returns NOT_CHECKED and NEVER silent CLEAR.

## Inputs and outputs
- **Public Functions:**
  - `check_recall(ticket_id: str, product_text: str, force_failure: bool = False, use_snapshot: bool = False, snapshot_data: Optional[Dict] = None) -> RecallCheckResponse`
- **Outputs:**
  - `RecallCheckResponse`: `check_id`, `ticket_id`, `product_text`, `fda_query`, `verdict` (`HALTED` | `CLEAR` | `NOT_CHECKED`), `recall_id`, `checked_at`, `source` (`LIVE_OPENFDA` | `OFFLINE_SNAPSHOT`).

## Invariants & Rules
1. **Timing:**
   - openFDA check runs BEFORE matching.
2. **Safety Verdicts:**
   - Active ongoing recall found $\implies$ `HALTED` (blocks item / posting).
   - Zero matching recalls confirmed $\implies$ `CLEAR`.
   - Network error, timeout, HTTP 5xx, or forced failure $\implies$ `NOT_CHECKED`. **Never CLEAR on failure.**
3. **Auditability & Persistence:**
   - Every recall check is recorded in Firestore collection `recall_checks` with full query and timestamp.
4. **Rate Limits & Offline Snapshot:**
   - Observed unauthenticated openFDA rate limit is 40 requests/minute (1,000 requests/day per IP); authenticated is 240 requests/minute.
   - Offline snapshot fallback is allowed only when explicitly requested and labelled as `source = OFFLINE_SNAPSHOT`.

## Tests that cover this module
- `backend/tests/test_phase_2.py::test_recall_halted_on_matching_recall`
- `backend/tests/test_phase_2.py::test_forced_openfda_failure_returns_not_checked`
- `backend/tests/test_phase_2.py::test_clean_product_returns_clear_recall`

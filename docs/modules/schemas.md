# Module: `schemas`

**Owner phase:** Phase 0
**Files:** `schemas/enums.py`, `schemas/common.py`, `schemas/api.py`, `schemas/__init__.py`
**Skill:** `.agent/skills/supervisor/SKILL.md`

## Purpose
Defines the frozen Pydantic v2 request/response contracts for all 52 endpoints (`ENDPOINT_CONTRACT_REGISTRY`), shared enums, multi-tenant envelopes (`BaseEnvelope`, `ErrorResponse`, `ActionProposal`), and the Donor Pickup-Address Validation rule (`validate_donor_pickup_address`).

## Inputs and outputs
- **Inputs:** Raw JSON payloads across all 52 API endpoints.
- **Outputs:** Validated Pydantic models with `request_id`, `tenant_id`, and `timestamp`.

## Tables / collections touched
- Reads: None
- Writes: None

## Deterministic rules vs model calls
- Deterministic: Enforces `address_type == "ORG_DOCK"`, `coordinator_asserted_org_dock == True`, `asserted_by_role == "COORDINATOR"`, and regex rejection of residential free-text (`validate_donor_pickup_address`).
- Model calls: None.

## Failure modes and fallbacks
- Rejects residential or unasserted donor pickup postings with `RESIDENTIAL_PICKUP_REJECTED`.

## Tests that cover this module
- `backend/tests/test_contracts.py::test_all_52_endpoint_schemas_registered_and_valid`
- `backend/tests/test_contracts.py::test_donor_pickup_address_validation_rule`


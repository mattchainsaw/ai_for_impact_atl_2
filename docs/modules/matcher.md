# Module: `matcher`

**Owner phase:** Phase 2  
**Files:** `backend/services/matcher.py`, `backend/services/search.py`, `backend/sql/search_recipients.sql`  
**Skill:** `.agent/skills/matcher/SKILL.md`  

## Purpose
Executes semantic matching of food rescue surplus postings against the recipient directory. Uses genuine BigQuery `VECTOR_SEARCH` (`COSINE` distance) against 3,072-dimensional embeddings generated with `gemini-embedding-2` (`text-embedding-005` fallback) joined with `v_all_recipients` and `v_recipient_tract`. Evaluates deterministic safety/capacity constraints and last-mile travel feasibility, ranks viable candidates, and records all candidates to Firestore `match_candidates`.

## Inputs and outputs
- **Inputs:**
  - `client: bigquery.Client`
  - `ticket_id: str`
  - `query_text: str` (surplus posting description or requirements)
  - `temperature_requirement: str = "ambient"` ("refrigerated" | "frozen" | "ambient")
  - `pallets_needed: float = 1.0`
  - `donor_zip: str = "30303"`
  - `resolved_shelf_life_hours: float = 48.0`
  - `top_k: int = 10` (max 50)
  - `origin_lat: Optional[float]`, `origin_lon: Optional[float]`
- **Outputs:**
  - `Tuple[List[MatchCandidate], str]`: List of evaluated candidate models and BigQuery execution `job_id`.

## Tables / collections touched
- **BigQuery Reads:**
  - `{project}.rescueguard_app.recipient_embeddings` (vector index)
  - `{project}.rescueguard_app.v_all_recipients` (profile details, verification status, overrides)
  - `{project}.rescueguard_app.v_recipient_tract` (nearest tract poverty, vehicle access, assistance rates)
- **Firestore Writes:**
  - `match_candidates` collection: Every candidate scored by vector search is stored with `semantic_rank`, `semantic_distance`, `status` (`ELIGIBLE` | `FILTERED` | `FLAGGED` | `TIED`), `filter_reason`, `evidence`, and last-mile logistics metrics.

## Deterministic rules vs model calls
- **Model calls:** BigQuery `AI.EMBED` (or Vertex AI text-embedding-005) converts `query_text` into a 3,072d FLOAT64 embedding vector in SQL.
- **Deterministic rules:** All post-retrieval filtering (cold/frozen compatibility, capacity in pallets, travel margin, service days, contradiction checks) and tie-breaking (need score, vehicle access, distance) are deterministic Python logic.

## Invariants & Traps Handled
- Decoy case (Greenline Community Pantry, ID 119): High semantic match for leafy greens, but deterministic filter flags `cold_storage = 'none'` and excludes it from viable candidates.
- Meaning is not capacity: High semantic similarity never bypasses cold chain or capacity limits.
- Vocabulary mismatch (Lakeshore Mutual Aid Collective, ID 127): Matched semantically on "Chilled holding" even without exact keyword matches.

## Tests that cover this module
- `backend/tests/test_phase_2.py::test_spinach_decoy_at_semantic_rank_1_and_filtered_no_cold`
- `backend/tests/test_phase_2.py::test_no_cold_pantry_never_in_viable_list`
- `backend/tests/test_phase_2.py::test_vocabulary_mismatch_found_by_meaning`
- `backend/tests/test_phase_2.py::test_firestore_candidate_persistence`

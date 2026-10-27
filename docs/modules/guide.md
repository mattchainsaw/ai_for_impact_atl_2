# Guide Module Architecture

## Overview
RescueGuard Guide provides an intelligent conversational assistant interface powered by Vertex AI via Agent Development Kit (ADK) / Gemini.

## Managed BigQuery MCP Proof (Review Fix C1)
- Guide analytical queries run through a dedicated BigQuery managed execution path (`execute_guide_mcp_query`).
- Query execution records both the BigQuery SQL query text and the `bq_job_id`.
- The execution guarantees `is_ranking_input == False`, ensuring one-off analytical inquiries never leak into or pollute the operational semantic matching ranking pipeline.

## Clarification Guard
- To prevent infinite loops or assistant stalls when inputs are ambiguous, the clarification guard tracks conversational turns.
- If repetitive questions reach turn 3 without resolution, the assistant halts further open-ended queries and surfaces a concrete coordinator ActionCard or direct fallback option.

## Privacy & PII Scrubbing
- User chat messages and postings pass through automatic PII scrubbers (`scrub_pii`).
- Regex patterns detect and redact US phone numbers, personal emails, and free-text residential street addresses (`[REDACTED_PHONE]`, `[REDACTED_EMAIL]`, `[REDACTED_ADDRESS]`).
- Coordinator dock pickup addresses are verified via `ORG_DOCK` assertions and kept strictly distinguished from residential PII.

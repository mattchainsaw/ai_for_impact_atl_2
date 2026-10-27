"""Built-in Google-managed BigQuery MCP client (Review Fix C1).

Connects to https://bigquery.googleapis.com/mcp using Application Default
Credentials (ADC) for guarded, read-only, one-off data questions via the
backend. Does NOT use an MCP Toolbox container. Every execute_sql invocation
validates that the query is read-only and returns the exact query and BigQuery
queryId/job_id for auditability.
"""

from datetime import datetime, timezone
import re
from typing import Any, Dict, List, Optional
import google.auth
import google.auth.transport.requests
import httpx

from backend.app.config import get_settings


_FORBIDDEN_SQL_PATTERN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|MERGE|DROP|ALTER|TRUNCATE|CREATE|GRANT|REVOKE|CALL|EXECUTE)\b",
    re.IGNORECASE,
)


def validate_readonly_sql(query: str) -> None:
    """Ensure SQL query is strictly read-only (SELECT / WITH only)."""
    stripped = query.strip()
    if not stripped:
        raise ValueError("MCP_READONLY_VIOLATION: Empty SQL query.")
    upper = stripped.upper()
    if not (upper.startswith("SELECT") or upper.startswith("WITH")):
        raise ValueError("MCP_READONLY_VIOLATION: Only SELECT/WITH read-only queries are allowed.")
    if _FORBIDDEN_SQL_PATTERN.search(stripped):
        raise ValueError("MCP_READONLY_VIOLATION: Mutating or DDL keywords are forbidden.")


def _get_adc_headers(project_id: str) -> Dict[str, str]:
    creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    auth_req = google.auth.transport.requests.Request()
    creds.refresh(auth_req)
    return {
        "Authorization": f"Bearer {creds.token}",
        "x-goog-user-project": project_id,
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }


def list_mcp_tools(project_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Call tools/list on the managed BigQuery MCP endpoint."""
    settings = get_settings()
    proj = project_id or settings.google_cloud_project
    headers = _get_adc_headers(proj)
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/list",
        "params": {},
    }
    with httpx.Client(timeout=30.0) as client:
        resp = client.post(settings.mcp_bigquery_endpoint, headers=headers, json=payload)
        resp.raise_for_status()
        body = resp.json()
    return body.get("result", {}).get("tools", [])


def execute_readonly_mcp_sql(
    query: str,
    project_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Execute a read-only SQL query via the managed BigQuery MCP server (`execute_sql`)
    and return the query, BigQuery job_id (`queryId`), parsed rows, and metadata."""
    validate_readonly_sql(query)
    settings = get_settings()
    proj = project_id or settings.google_cloud_project
    headers = _get_adc_headers(proj)
    payload = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/call",
        "params": {
            "name": "execute_sql",
            "arguments": {
                "projectId": proj,
                "query": query,
            },
        },
    }
    with httpx.Client(timeout=30.0) as client:
        resp = client.post(settings.mcp_bigquery_endpoint, headers=headers, json=payload)
        resp.raise_for_status()
        body = resp.json()

    result = body.get("result", {})
    structured = result.get("structuredContent", {})
    job_id = structured.get("queryId") or structured.get("jobId")
    fields = [f.get("name") for f in structured.get("schema", {}).get("fields", [])]
    parsed_rows: List[Dict[str, Any]] = []
    for raw_row in structured.get("rows", []):
        cells = raw_row.get("f", [])
        row_dict = {
            fields[i]: cells[i].get("v") if i < len(cells) else None
            for i in range(len(fields))
        }
        parsed_rows.append(row_dict)

    return {
        "mcp_endpoint": settings.mcp_bigquery_endpoint,
        "project_id": proj,
        "query": query,
        "job_id": job_id,
        "job_complete": structured.get("jobComplete", False),
        "rows": parsed_rows,
        "total_bytes_processed": structured.get("totalBytesProcessed", "0"),
        "called_at": datetime.now(timezone.utc).isoformat(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


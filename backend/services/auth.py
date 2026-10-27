"""Persona and Multi-Tenant filtering service (Phase 4).

Extracts and validates demo identity headers (X-Role, X-Tenant, X-Org-Id).
Enforces cross-role and cross-tenant access control returning HTTP 404 (never 403)
per the RescueGuard build plan and Persona handoff contract.
"""

from typing import Optional
from fastapi import Header, HTTPException

from schemas.enums import Role


def get_current_role(x_role: Optional[str] = Header(default="COORDINATOR")) -> Role:
    """Extract and validate persona role from X-Role header."""
    role_str = (x_role or "COORDINATOR").strip().upper()
    try:
        return Role(role_str)
    except ValueError:
        return Role.COORDINATOR


def get_current_tenant(x_tenant: Optional[str] = Header(default="atlanta-default")) -> str:
    """Extract tenant from X-Tenant header."""
    return (x_tenant or "atlanta-default").strip()


def get_current_org_id(x_org_id: Optional[str] = Header(default=None)) -> Optional[str]:
    """Extract org ID from X-Org-Id header."""
    if not x_org_id:
        return None
    return x_org_id.strip()


def check_tenant_access(resource_tenant: Optional[str], current_tenant: str) -> None:
    """Enforce tenant isolation. Mismatches return 404 Not Found (never 403)."""
    if resource_tenant and resource_tenant != current_tenant:
        raise HTTPException(
            status_code=404,
            detail="Resource not found in tenant.",
        )


def check_donor_access(posting_donor_id: str, role: Role, current_org_id: Optional[str]) -> None:
    """Enforce donor data isolation. Cross-donor reads return 404 (never 403)."""
    if role == Role.COORDINATOR:
        return
    if role == Role.DONOR:
        if current_org_id and posting_donor_id != current_org_id:
            raise HTTPException(
                status_code=404,
                detail="Posting not found.",
            )
        return
    # Recipient attempting to read donor posting directly
    raise HTTPException(
        status_code=404,
        detail="Resource not found.",
    )


def check_recipient_access(allocation_recipient_id: int, role: Role, current_org_id: Optional[str]) -> None:
    """Enforce recipient data isolation. Cross-recipient reads return 404 (never 403)."""
    if role == Role.COORDINATOR:
        return
    if role == Role.RECIPIENT:
        if current_org_id and int(allocation_recipient_id) != int(current_org_id):
            raise HTTPException(
                status_code=404,
                detail="Allocation not found for recipient.",
            )
        return
    # Donor attempting to read recipient allocation directly
    raise HTTPException(
        status_code=404,
        detail="Resource not found.",
    )

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


# ============================================================================
# Phase 5: Role-Filtered Ticket and Plan Read Views
# ============================================================================


def filter_ticket_for_role(
    ticket: dict,
    role: Role,
    org_id: Optional[str],
    posting: Optional[dict] = None,
    plan: Optional[dict] = None,
    brief: Optional[dict] = None,
    holds: Optional[list] = None,
) -> dict:
    """Transform ticket response according to the requesting persona's contract.
    
    Coordinator: full view with internal tasks, parameters, checkpoints, and brief.
    Donor: own postings, matched pantries with org addresses + allocations, hold status, final pickup plan.
    Recipient: own offers only, donor pickup org address + own delivery org address, confirm/decline state.
    Cross-role or unauthorized org -> 404 Not Found (never 403).
    """
    if role == Role.COORDINATOR:
        res = dict(ticket)
        if brief:
            res["match_brief"] = brief
        return res

    if role == Role.DONOR:
        posting_donor = (posting.get("donor_id") if posting else "") or ticket.get("donor_id") or ""
        if not org_id or str(posting_donor) != str(org_id):
            raise HTTPException(status_code=404, detail="Ticket not found for donor.")

        # Build matched pantries from plan allocations
        matched_pantries = []
        allocations = (plan.get("allocations") if plan else []) or []
        holds_list = holds or []
        for a in allocations:
            r_id = int(a.get("recipient_id", 0))
            h_stat = "ACTIVE"
            for h in holds_list:
                if int(h.get("recipient_id", -1)) == r_id:
                    h_stat = str(h.get("status", "ACTIVE"))
                    break
            matched_pantries.append({
                "recipient_id": r_id,
                "name": str(a.get("recipient_name", f"Pantry {r_id}")),
                "org_address": str(a.get("org_address") or "100 Community Way, Atlanta, GA 30303"),
                "allocated_quantity": float(a.get("quantity", 0.0)),
                "allocated_unit": str(a.get("quantity_unit", "PALLETS")),
                "hold_status": h_stat,
                "allocation_status": "PENDING_CONFIRMATION",
                "request_id": ticket.get("request_id", "req-default"),
                "tenant_id": ticket.get("tenant_id", "atlanta-default"),
            })

        final_pickup_plan = None
        if plan:
            final_pickup_plan = {
                "plan_id": plan.get("plan_id"),
                "plan_version": plan.get("plan_version", 1),
                "status": plan.get("status"),
                "resolved_deadline": ticket.get("resolved_deadline"),
                "allocations": allocations,
            }

        hold_status_summary = "ACTIVE" if matched_pantries else "NONE"
        return {
            "role": Role.DONOR,
            "ticket_id": ticket.get("ticket_id"),
            "posting_id": ticket.get("posting_id"),
            "status": ticket.get("status"),
            "posting": posting or {},
            "matched_pantries": matched_pantries,
            "hold_status": hold_status_summary,
            "final_pickup_plan": final_pickup_plan,
            "match_brief": brief,
            "request_id": ticket.get("request_id", "req-default"),
            "tenant_id": ticket.get("tenant_id", "atlanta-default"),
        }

    if role == Role.RECIPIENT:
        if not org_id:
            raise HTTPException(status_code=404, detail="Recipient org ID required.")

        try:
            target_r_id = int(org_id)
        except ValueError:
            raise HTTPException(status_code=404, detail="Invalid recipient org ID.")

        allocations = (plan.get("allocations") if plan else []) or []
        target_alloc = None
        for a in allocations:
            if int(a.get("recipient_id", -1)) == target_r_id:
                target_alloc = a
                break

        holds_list = holds or []
        target_hold = None
        for h in holds_list:
            if int(h.get("recipient_id", -1)) == target_r_id:
                target_hold = h
                break

        if not target_alloc and not target_hold:
            raise HTTPException(
                status_code=404,
                detail=f"Ticket not found for recipient {target_r_id}.",
            )

        # Donor pickup address logic
        donor_pickup_addr = "Starter posting data: no donor pickup address recorded"
        if posting:
            addr_type = str(posting.get("address_type", "")).upper()
            asserted = bool(
                posting.get("coordinator_asserted_org_dock")
                or posting.get("asserted_by_role") == "COORDINATOR"
            )
            if addr_type == "ORG_DOCK" and asserted:
                donor_pickup_addr = posting.get("pickup_address", "").strip()
            else:
                donor_pickup_addr = "SUPPRESSED: Address not asserted as ORG_DOCK by coordinator"

        r_name = ""
        r_qty = 0.0
        r_unit = "PALLETS"
        if target_alloc:
            r_name = str(target_alloc.get("recipient_name", f"Pantry {target_r_id}"))
            r_qty = float(target_alloc.get("quantity", 0.0))
            r_unit = str(target_alloc.get("quantity_unit", "PALLETS"))
        elif target_hold:
            r_name = f"Pantry {target_r_id}"
            r_qty = float(target_hold.get("quantity", 0.0))
            r_unit = str(target_hold.get("quantity_unit", "PALLETS"))

        hold_id = target_hold.get("hold_id") if target_hold else None
        h_status = target_hold.get("status") if target_hold else "ACTIVE"
        confirm_state = str(h_status)

        offer = {
            "recipient_id": target_r_id,
            "name": r_name,
            "allocated_quantity": r_qty,
            "allocated_unit": r_unit,
            "hold_id": hold_id,
            "hold_status": h_status,
            "confirm_decline_state": confirm_state,
            "donor_pickup_org_address": donor_pickup_addr,
            "own_delivery_org_address": str(
                (target_alloc.get("org_address") if target_alloc else None)
                or "100 Community Way, Atlanta, GA 30303"
            ),
            "donor_deadline": ticket.get("resolved_deadline"),
            "request_id": ticket.get("request_id", "req-default"),
            "tenant_id": ticket.get("tenant_id", "atlanta-default"),
        }

        return {
            "role": Role.RECIPIENT,
            "ticket_id": ticket.get("ticket_id"),
            "current_plan_id": ticket.get("current_plan_id"),
            "offer": offer,
            "request_id": ticket.get("request_id", "req-default"),
            "tenant_id": ticket.get("tenant_id", "atlanta-default"),
        }

    raise HTTPException(status_code=404, detail="Resource not found.")


def filter_plan_for_role(
    plan: dict,
    role: Role,
    org_id: Optional[str],
    ticket: Optional[dict] = None,
    posting: Optional[dict] = None,
    brief: Optional[dict] = None,
    holds: Optional[list] = None,
) -> dict:
    """Transform plan response according to the requesting persona's contract."""
    if role == Role.COORDINATOR:
        res = dict(plan)
        if brief:
            res["match_brief"] = brief
        return res

    if role == Role.DONOR:
        posting_donor = (posting.get("donor_id") if posting else "") or (ticket.get("donor_id") if ticket else "") or ""
        if not org_id or str(posting_donor) != str(org_id):
            raise HTTPException(status_code=404, detail="Plan not found for donor.")

        matched_pantries = []
        allocations = plan.get("allocations", []) or []
        holds_list = holds or []
        for a in allocations:
            r_id = int(a.get("recipient_id", 0))
            h_stat = "ACTIVE"
            for h in holds_list:
                if int(h.get("recipient_id", -1)) == r_id:
                    h_stat = str(h.get("status", "ACTIVE"))
                    break
            matched_pantries.append({
                "recipient_id": r_id,
                "name": str(a.get("recipient_name", f"Pantry {r_id}")),
                "org_address": str(a.get("org_address") or "100 Community Way, Atlanta, GA 30303"),
                "allocated_quantity": float(a.get("quantity", 0.0)),
                "allocated_unit": str(a.get("quantity_unit", "PALLETS")),
                "hold_status": h_stat,
                "allocation_status": "PENDING_CONFIRMATION",
                "request_id": plan.get("request_id", "req-default"),
                "tenant_id": plan.get("tenant_id", "atlanta-default"),
            })

        final_pickup_plan = {
            "plan_id": plan.get("plan_id"),
            "plan_version": plan.get("plan_version", 1),
            "status": plan.get("status"),
            "resolved_deadline": ticket.get("resolved_deadline") if ticket else None,
            "allocations": allocations,
        }

        return {
            "role": Role.DONOR,
            "plan_id": plan.get("plan_id"),
            "ticket_id": plan.get("ticket_id"),
            "plan_version": plan.get("plan_version", 1),
            "status": plan.get("status"),
            "matched_pantries": matched_pantries,
            "final_pickup_plan": final_pickup_plan,
            "match_brief": brief,
            "request_id": plan.get("request_id", "req-default"),
            "tenant_id": plan.get("tenant_id", "atlanta-default"),
        }

    if role == Role.RECIPIENT:
        if not org_id:
            raise HTTPException(status_code=404, detail="Recipient org ID required.")

        try:
            target_r_id = int(org_id)
        except ValueError:
            raise HTTPException(status_code=404, detail="Invalid recipient org ID.")

        allocations = plan.get("allocations", []) or []
        target_alloc = None
        for a in allocations:
            if int(a.get("recipient_id", -1)) == target_r_id:
                target_alloc = a
                break

        if not target_alloc:
            raise HTTPException(
                status_code=404,
                detail=f"Plan not found for recipient {target_r_id}.",
            )

        donor_pickup_addr = "Starter posting data: no donor pickup address recorded"
        if posting:
            addr_type = str(posting.get("address_type", "")).upper()
            asserted = bool(
                posting.get("coordinator_asserted_org_dock")
                or posting.get("asserted_by_role") == "COORDINATOR"
            )
            if addr_type == "ORG_DOCK" and asserted:
                donor_pickup_addr = posting.get("pickup_address", "").strip()
            else:
                donor_pickup_addr = "SUPPRESSED: Address not asserted as ORG_DOCK by coordinator"

        holds_list = holds or []
        target_hold = None
        for h in holds_list:
            if int(h.get("recipient_id", -1)) == target_r_id:
                target_hold = h
                break

        offer = {
            "recipient_id": target_r_id,
            "name": str(target_alloc.get("recipient_name", f"Pantry {target_r_id}")),
            "allocated_quantity": float(target_alloc.get("quantity", 0.0)),
            "allocated_unit": str(target_alloc.get("quantity_unit", "PALLETS")),
            "hold_id": target_hold.get("hold_id") if target_hold else None,
            "hold_status": target_hold.get("status") if target_hold else "ACTIVE",
            "confirm_decline_state": target_hold.get("status") if target_hold else "ACTIVE",
            "donor_pickup_org_address": donor_pickup_addr,
            "own_delivery_org_address": str(
                target_alloc.get("org_address") or "100 Community Way, Atlanta, GA 30303"
            ),
            "donor_deadline": ticket.get("resolved_deadline") if ticket else None,
            "request_id": plan.get("request_id", "req-default"),
            "tenant_id": plan.get("tenant_id", "atlanta-default"),
        }

        return {
            "role": Role.RECIPIENT,
            "plan_id": plan.get("plan_id"),
            "ticket_id": plan.get("ticket_id"),
            "plan_version": plan.get("plan_version", 1),
            "status": plan.get("status"),
            "offer": offer,
            "request_id": plan.get("request_id", "req-default"),
            "tenant_id": plan.get("tenant_id", "atlanta-default"),
        }

    raise HTTPException(status_code=404, detail="Resource not found.")


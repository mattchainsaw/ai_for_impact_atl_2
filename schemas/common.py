"""Shared Pydantic domain models and hard-gate validators for RescueGuard Backend (Phase 0)."""

import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from backend.app.config import CRATES_PER_PALLET
from schemas.enums import (
    ActionTargetType,
    AddressType,
    CandidateStatus,
    DistanceSource,
    EquityVerdict,
    ExecutionSource,
    QuantityUnit,
    Role,
    ShelfLifeSource,
)

# Review Fix M5: Residential free-text patterns that must be rejected on live donor postings.
RESIDENTIAL_ADDRESS_REGEX = re.compile(
    r"\b("
    r"home|house|apt|apartment|residence|residential|condo|townhouse|duplex|"
    r"unit\s*#?\d+|private\s+residence|my\s+place|bedroom|living\s+room|front\s+porch"
    r")\b",
    re.IGNORECASE,
)


def convert_to_pallets(
    quantity: float,
    quantity_unit: QuantityUnit,
    crates_per_pallet: int = CRATES_PER_PALLET,
) -> float:
    """Hard Gate 1: Convert quantity to pallets using frozen CRATES_PER_PALLET = 20."""
    if quantity <= 0:
        raise ValueError("quantity must be strictly positive")
    if quantity_unit == QuantityUnit.PALLETS:
        return round(float(quantity), 4)
    if quantity_unit == QuantityUnit.CRATES:
        return round(float(quantity) / float(crates_per_pallet), 4)
    raise ValueError(f"Unsupported quantity_unit: {quantity_unit}")


def compute_clock_margin_hours(
    resolved_hours_left: float,
    pickup_window_hours: float,
    travel_buffer_hours: float,
) -> float:
    """Hard Gate 2: Single source of truth for resolved clock safety margin."""
    return round(
        float(resolved_hours_left) - float(pickup_window_hours) - float(travel_buffer_hours),
        4,
    )


def compute_impact_score(
    need: float,
    rescue: float,
    equity: float,
    reliability: float,
) -> int:
    """Locked Impact Score formula: round(0.30*Need + 0.25*Rescue + 0.25*Equity + 0.20*Reliability).

    Fixture check: Need=88, Rescue=100, Equity=82, Reliability=85 -> 88.9 -> 89.
    """
    raw = 0.30 * float(need) + 0.25 * float(rescue) + 0.25 * float(equity) + 0.20 * float(reliability)
    return int(round(raw))


def validate_donor_pickup_address(
    donor_org_name: str,
    pickup_address: str,
    address_type: AddressType,
    coordinator_asserted_org_dock: bool,
    asserted_by_role: Optional[Role] = None,
) -> None:
    """Review Fix M5: Testable donor pickup-address validation rule.

    Raises ValueError if any of the 3 conditions fail:
    (a) address_type == AddressType.ORG_DOCK
    (b) coordinator has asserted ORG_DOCK (coordinator_asserted_org_dock=True and role=COORDINATOR)
    (c) non-empty donor_org_name and pickup_address does not match residential free-text regex.
    """
    if address_type != AddressType.ORG_DOCK:
        raise ValueError(
            f"Invalid address_type '{address_type}'. Donor pickup must be AddressType.ORG_DOCK."
        )
    if not coordinator_asserted_org_dock or (
        asserted_by_role is not None and asserted_by_role != Role.COORDINATOR
    ):
        raise ValueError(
            "Donor pickup address requires coordinator assertion of ORG_DOCK "
            "(coordinator_asserted_org_dock=True, asserted_by_role=COORDINATOR)."
        )
    if not donor_org_name or not donor_org_name.strip():
        raise ValueError("donor_org_name is required for an organizational dock pickup.")
    if not pickup_address or len(pickup_address.strip()) < 5:
        raise ValueError("pickup_address must be a valid commercial/organizational dock address.")
    match = RESIDENTIAL_ADDRESS_REGEX.search(pickup_address)
    if match:
        raise ValueError(
            f"Rejected residential free-text pattern '{match.group(0)}' in pickup_address. "
            "Home/residential pickup addresses are prohibited."
        )


class ResolvedClockContract(BaseModel):
    """Hard Gate 2: Single resolved clock carried on every ticket."""

    resolved_deadline: datetime
    resolved_shelf_life_hours: float
    shelf_life_source: ShelfLifeSource
    resolved_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CandidateEvidence(BaseModel):
    """Structured column vs profile text evidence stored on `match_candidates`."""

    column_value: str
    profile_text_excerpt: str


class MatchCandidateRecord(BaseModel):
    """Authoritative candidate row stored in `match_candidates`."""

    ticket_id: str
    run_id: str
    recipient_id: int = Field(..., description="INT64 recipient_id")
    name: str
    semantic_rank: int
    semantic_distance: float
    post_filter_rank: Optional[int] = None
    status: CandidateStatus
    filter_reason: Optional[str] = None
    contradiction_flag: bool = False
    evidence: CandidateEvidence
    tie_break_values: Dict[str, Any] = Field(default_factory=dict)
    donor_to_recipient_distance_km: float
    distance_source: DistanceSource = DistanceSource.HAVERSINE_FALLBACK
    need_score: float
    tenant_id: str = "atlanta-default"


class PlanAllocationItem(BaseModel):
    """Individual recipient allocation inside a plan version (`plans.allocations[]`)."""

    recipient_id: int
    recipient_name: str
    quantity: float
    quantity_unit: QuantityUnit
    pallets_equivalent: float
    clock_margin_hours: float
    donor_to_recipient_distance_km: float
    distance_source: DistanceSource = DistanceSource.HAVERSINE_FALLBACK
    tract_geo_id: str
    need_score: float


class ImpactBreakdown(BaseModel):
    """Stored Impact Score breakdown on a plan (`0.30*Need + 0.25*Rescue + 0.25*Equity + 0.20*Reliability`)."""

    need_score: float
    rescue_score: float
    equity_score: float
    reliability_score: float
    raw_total: float
    reported_total: int
    estimated_households_label: str = "ESTIMATED_CAPACITY"


class EquityCheckerResult(BaseModel):
    """Checker-owned tract comparison stored on a plan and sunk to `equity_audit_results`."""

    verdict: EquityVerdict
    chosen_poverty_rate_avg: float
    metro_poverty_rate_avg: float
    chosen_no_vehicle_rate_avg: float
    metro_no_vehicle_rate_avg: float
    chosen_assistance_rate_avg: float
    metro_assistance_rate_avg: float
    notes: str = ""


class ActionCard(BaseModel):
    """Locked Action schema for Guide chat proposals and `POST /api/actions/approve`."""

    action_id: str
    target_type: ActionTargetType
    target_id: str
    target_endpoint: str
    description: Optional[str] = None


class NoViableMatchFallback(BaseModel):
    """Structured 422 fallback body when no recipient passes hard constraints."""

    request_id: str
    ticket_id: str
    error_code: str = "NO_VIABLE_MATCH"
    why_no_one_fits: List[str]
    nearest_option_recipient_id: Optional[int] = None
    nearest_option_why_not: Optional[str] = None
    coordinator_contact_path: str = "POST /api/tasks (task_type=VERIFY_CAPACITY)"
    tenant_id: str = "atlanta-default"

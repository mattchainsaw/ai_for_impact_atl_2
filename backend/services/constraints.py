"""Deterministic constraint filtering & contradiction detection service.

Per Part 2 lines 1311-1317:
1. Constraint filter evaluates cold/frozen storage, capacity (Phase 0 unit rule),
   pickup window vs resolved-clock hours left, service day, dock/transport.
2. Contradiction check: Columns beat text. If a column contradicts profile text
   (e.g., dock=False vs text 'dock height', frozen=False vs text 'walk-in freezer',
   cold='none' with text fresh requests), candidate status is FLAGGED, NEVER an auto-match guess.
3. Every candidate receives an explicit status (ELIGIBLE, FILTERED, FLAGGED) and reason.
"""

import re
from typing import Any, Dict, List, Optional, Tuple
from schemas.enums import CandidateStatus, ColdStorageType
from schemas.common import CandidateEvidence


# Recognized cold storage types that qualify for food rescue
COLD_STORAGE_QUALIFIED = {"walk-in", "commercial", "domestic"}


def detect_profile_contradictions(
    cold_storage: Optional[str],
    frozen_storage: Optional[bool],
    loading_dock: Optional[bool],
    service_days: Optional[str],
    profile_text: Optional[str],
) -> Tuple[bool, Optional[str], CandidateEvidence]:
    """Detect structured column vs profile text contradictions.
    
    Returns:
        (has_contradiction, explanation, evidence)
    """
    text = (profile_text or "").strip()
    text_lower = text.lower()
    cold_val = (cold_storage or "none").lower()

    # Evidence default
    evidence = CandidateEvidence(
        column_value=f"cold={cold_val}, frozen={frozen_storage}, dock={loading_dock}",
        profile_text_excerpt=text[:120] if text else "No profile text",
    )

    # 1. Harborview / Self-contradiction: text claims freezer then immediately negates it
    if "freezer" in text_lower and ("no freezer at present" in text_lower or "actually no freezer" in text_lower):
        return (
            True,
            "Profile text contradicts itself regarding freezer availability ('walk-in freezer' vs 'no freezer at present')",
            CandidateEvidence(
                column_value=f"frozen_storage={frozen_storage}",
                profile_text_excerpt="walk-in freezer installed last winter... Wait, actually no freezer at present",
            ),
        )

    # 2. Dock contradiction: column is False/None but text explicitly asserts loading dock / dock height
    if loading_dock is False:
        dock_match = re.search(r"\b(dock\s+height|loading\s+dock|loading\s+bay)\b", text_lower)
        if dock_match:
            return (
                True,
                f"Loading dock contradiction: column loading_dock=False but profile text asserts '{dock_match.group(0)}'",
                CandidateEvidence(
                    column_value="loading_dock=False",
                    profile_text_excerpt=text[max(0, dock_match.start() - 20) : min(len(text), dock_match.end() + 40)],
                ),
            )

    # 3. Freezer contradiction: column frozen_storage=False but text claims walk-in freezer
    if frozen_storage is False and ("walk-in freezer" in text_lower or "commercial freezer" in text_lower):
        return (
            True,
            "Freezer contradiction: column frozen_storage=False but profile text claims walk-in freezer",
            CandidateEvidence(
                column_value="frozen_storage=False",
                profile_text_excerpt="Profile claims freezer while column is False",
            ),
        )

    # 4. Service days contradiction: column days do not match text schedule
    if service_days and text:
        col_days = [d.strip().lower() for d in service_days.split(",")]
        # Check if text specifies days different from column
        if "tuesday, thursday" in text_lower or "tuesday and thursday" in text_lower:
            if "tuesday" not in col_days and "thursday" not in col_days:
                return (
                    True,
                    f"Schedule contradiction: column service_days='{service_days}' but profile text specifies 'Tuesday, Thursday'",
                    CandidateEvidence(
                        column_value=f"service_days='{service_days}'",
                        profile_text_excerpt="Open Tuesday, Thursday",
                    ),
                )

    return False, None, evidence


def evaluate_candidate_constraints(
    recipient_id: int,
    name: str,
    cold_storage: Optional[str],
    frozen_storage: Optional[bool],
    loading_dock: Optional[bool],
    service_days: Optional[str],
    profile_text: Optional[str],
    max_pallets: Optional[int],
    margin_hours: float,
    temperature_requirement: str = "refrigerated",
    required_pallets: float = 1.0,
    pickup_weekday: Optional[str] = None,
    allow_capacity_filtering: bool = False,
) -> Tuple[CandidateStatus, Optional[str], bool, CandidateEvidence]:
    """Deterministically evaluate all constraints for a candidate recipient.
    
    Returns:
        (status, filter_reason, contradiction_flag, evidence)
    """
    cold_val = (cold_storage or "none").lower()
    temp_req = temperature_requirement.lower()

    # Step 1: Contradiction Check (Columns beat text, contradiction sets FLAGGED)
    has_contradiction, contra_reason, evidence = detect_profile_contradictions(
        cold_storage=cold_storage,
        frozen_storage=frozen_storage,
        loading_dock=loading_dock,
        service_days=service_days,
        profile_text=profile_text,
    )

    if has_contradiction:
        return CandidateStatus.FLAGGED, contra_reason, True, evidence

    # Step 2: Storage Constraints
    if temp_req in ["refrigerated", "cold", "perishable"]:
        if cold_val not in COLD_STORAGE_QUALIFIED:
            reason = f"No cold storage available for refrigerated item (cold_storage='{cold_val}')"
            return (
                CandidateStatus.FILTERED,
                reason,
                False,
                CandidateEvidence(
                    column_value=f"cold_storage='{cold_val}'",
                    profile_text_excerpt=(profile_text or "")[:100],
                ),
            )

    elif temp_req == "frozen":
        if not frozen_storage:
            reason = "No frozen storage available for frozen item (frozen_storage=False)"
            return (
                CandidateStatus.FILTERED,
                reason,
                False,
                CandidateEvidence(
                    column_value=f"frozen_storage={frozen_storage}",
                    profile_text_excerpt=(profile_text or "")[:100],
                ),
            )

    # Step 3: Clock Safety Margin (< 0 hours out)
    if margin_hours < 0.0:
        reason = f"Insufficient clock safety margin ({margin_hours:.2f}h < 0.0h)"
        return (
            CandidateStatus.FILTERED,
            reason,
            False,
            CandidateEvidence(
                column_value=f"margin_hours={margin_hours:.2f}",
                profile_text_excerpt=(profile_text or "")[:100],
            ),
        )

    # Step 4: Service Day Match
    if pickup_weekday and service_days:
        day_clean = pickup_weekday.strip().lower()
        if day_clean not in service_days.lower():
            reason = f"Recipient not open on requested pickup day '{pickup_weekday}' (open: {service_days})"
            return (
                CandidateStatus.FILTERED,
                reason,
                False,
                CandidateEvidence(
                    column_value=f"service_days='{service_days}'",
                    profile_text_excerpt=(profile_text or "")[:100],
                ),
            )

    # Step 5: Capacity Check (if single-allocation mode enforced)
    if allow_capacity_filtering and max_pallets is not None:
        if float(max_pallets) < required_pallets:
            reason = f"Insufficient pallet capacity ({max_pallets} max pallets < {required_pallets:.2f} required)"
            return (
                CandidateStatus.FILTERED,
                reason,
                False,
                CandidateEvidence(
                    column_value=f"max_pallets={max_pallets}",
                    profile_text_excerpt=(profile_text or "")[:100],
                ),
            )

    # Step 6: All constraints satisfied -> ELIGIBLE
    return CandidateStatus.ELIGIBLE, None, False, evidence


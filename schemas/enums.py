"""Frozen enumeration contracts for RescueGuard Backend (Phase 0 — 29 tables / 52 endpoints)."""

from enum import Enum


class TriStateStatus(str, Enum):
    """Rule 1: Honest unknowns for capability, storage, and facts."""

    YES = "YES"
    NO = "NO"
    UNRECORDED = "UNRECORDED"


class Role(str, Enum):
    """Persona roles enforced by backend header/query filtering."""

    COORDINATOR = "COORDINATOR"
    DONOR = "DONOR"
    RECIPIENT = "RECIPIENT"


class AddressType(str, Enum):
    """Pickup address classification (Review Fix M5)."""

    ORG_DOCK = "ORG_DOCK"
    RESIDENTIAL = "RESIDENTIAL"
    UNKNOWN = "UNKNOWN"


class QuantityUnit(str, Enum):
    """Supported physical load units (Hard Gate 1)."""

    PALLETS = "PALLETS"
    CRATES = "CRATES"


class PostingSource(str, Enum):
    """Discriminator required when creating a ticket (`POST /api/tickets`)."""

    STARTER = "STARTER"
    LIVE_DONOR = "LIVE_DONOR"


class ShelfLifeSource(str, Enum):
    """Authoritative source of resolved clock deadline (Hard Gate 2)."""

    FOODKEEPER = "FOODKEEPER"
    DONOR_FALLBACK = "DONOR_FALLBACK"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class ColdStorageType(str, Enum):
    """Distinct cold_storage values verified in Atlanta starter data (Hard Gate 2)."""

    DOMESTIC = "domestic"
    WALK_IN = "walk-in"
    MEDICAL = "medical"
    COMMERCIAL = "commercial"
    NONE = "none"
    VEHICLE = "vehicle"


class TicketStep(str, Enum):
    """Lifecycle steps of a rescue ticket across personas."""

    POSTED = "POSTED"
    MATCHED = "MATCHED"
    CHECKED = "CHECKED"
    APPROVED = "APPROVED"
    HELD = "HELD"
    CONFIRMED = "CONFIRMED"
    COMPLETED = "COMPLETED"
    DECLINED = "DECLINED"
    RE_PLANNED = "RE-PLANNED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"
    FDA_HALTED = "FDA_HALTED"
    SPLIT_REQUIRED = "SPLIT_REQUIRED"


class TicketStatus(str, Enum):
    """Top-level ticket execution / crash-resume status."""

    ACTIVE = "ACTIVE"
    RESUMABLE = "RESUMABLE"
    INTERRUPTED = "INTERRUPTED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    FDA_HALTED = "FDA_HALTED"


class PlanStatus(str, Enum):
    """Append-only plan version statuses."""

    DRAFT = "DRAFT"
    CHECKER_REJECTED = "CHECKER_REJECTED"
    APPROVED = "APPROVED"
    SUPERSEDED = "SUPERSEDED"


class CandidateStatus(str, Enum):
    """Status of each candidate evaluated in a match run (`match_candidates`)."""

    ELIGIBLE = "ELIGIBLE"
    FILTERED = "FILTERED"
    FLAGGED = "FLAGGED"
    TIED = "TIED"


class HoldStatus(str, Enum):
    """Transactional Firestore hold states (`holds`)."""

    ACTIVE = "ACTIVE"
    CONFIRMED = "CONFIRMED"
    EXPIRED = "EXPIRED"
    RELEASED = "RELEASED"


class AllocationStatus(str, Enum):
    """Confirmed assignment + fairness-ledger states (`allocations`)."""

    CONFIRMED = "CONFIRMED"
    DECLINED = "DECLINED"
    NO_SHOW = "NO_SHOW"
    EXPIRED = "EXPIRED"
    COMPLETED = "COMPLETED"


class TaskType(str, Enum):
    """Coordinator and recipient task types (`tasks`)."""

    APPROVE_PLAN = "APPROVE_PLAN"
    CONFIRM_PICKUP = "CONFIRM_PICKUP"
    UPDATE_PROFILE = "UPDATE_PROFILE"
    CHECK_CONTRADICTION = "CHECK_CONTRADICTION"
    VERIFY_CAPACITY = "VERIFY_CAPACITY"
    SETUP_PICKUP = "SETUP_PICKUP"


class TaskStatus(str, Enum):
    """Task lifecycle statuses (`tasks`)."""

    OPEN = "OPEN"
    APPROVED = "APPROVED"
    DECLINED = "DECLINED"
    ASSIGNED = "ASSIGNED"


class ActionTargetType(str, Enum):
    """Locked target types for canonical `POST /api/actions/approve`."""

    TASK = "task"
    PLAN = "plan"
    HOLD = "hold"
    ONBOARDING = "onboarding"


class VerificationStatus(str, Enum):
    """Onboarding verification states (`app_recipients`)."""

    PENDING = "PENDING"
    VERIFIED = "VERIFIED"
    DEMO_SIMULATED = "DEMO_SIMULATED"


class OverrideStatus(str, Enum):
    """Profile override approval states (`recipient_overrides`)."""

    PENDING = "PENDING"
    VERIFIED = "VERIFIED"
    APPROVED = "APPROVED"


class RecallVerdict(str, Enum):
    """OpenFDA food enforcement recall verdicts (`recall_checks`)."""

    CLEAR = "CLEAR"
    HALTED = "HALTED"
    NOT_CHECKED = "NOT_CHECKED"


class RecallSource(str, Enum):
    """Source of recall check result."""

    LIVE_OPENFDA = "LIVE_OPENFDA"
    OFFLINE_SNAPSHOT = "OFFLINE_SNAPSHOT"


class EquityVerdict(str, Enum):
    """Checker-owned tract equity comparison verdict."""

    PASS = "PASS"
    WARN = "WARN"


class ExecutionSource(str, Enum):
    """Source of split and margin calculations (Review Fix M1)."""

    CODE_EXECUTION = "CODE_EXECUTION"
    PYTHON_FALLBACK = "PYTHON_FALLBACK"


class DistanceSource(str, Enum):
    """Source of travel distance and duration (`distance_pairs` & `match_candidates`)."""

    GOOGLE_ROUTES = "GOOGLE_ROUTES"
    HAVERSINE_FALLBACK = "HAVERSINE_FALLBACK"


class TractStatus(str, Enum):
    """Status of left-joined census tract on `v_recipient_tract`."""

    FOUND = "FOUND"
    UNKNOWN = "UNKNOWN"


class ScrubStatus(str, Enum):
    """PII scrubbing status on `conversations`."""

    SCRUBBED = "SCRUBBED"
    REJECTED_ON_MATCH = "REJECTED_ON_MATCH"


class NotificationEvent(str, Enum):
    """Events recorded in `notifications` for persona inbox views."""

    OFFER_MADE = "OFFER_MADE"
    DECLINE = "DECLINE"
    REPLAN = "REPLAN"
    CANCEL = "CANCEL"
    HOLD_EXPIRED = "HOLD_EXPIRED"
    CONFIRMED = "CONFIRMED"
    COMPLETED = "COMPLETED"

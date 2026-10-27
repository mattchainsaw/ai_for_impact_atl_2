"""FoodKeeper and Resolved Clock rules module for RescueGuard.

Implements core domain rules from Part 2:
1. NULL shelf-life is a rule, not zero (diapers -> NOT_APPLICABLE, milk / sealed formula -> DONOR_FALLBACK).
2. 'Spinach' is a subtitle under 'Lettuce' in FoodKeeper; search covers product_name and product_subtitle.
3. Conservative range end: use lower shelf-life hours for safety.
4. Donor deadline always beats the FoodKeeper book: min(foodkeeper_hours, donor_hours).
5. Single source of truth: resolved_deadline, resolved_shelf_life_hours, shelf_life_source, resolved_at.
"""

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any
from google.cloud import bigquery

from schemas.enums import ShelfLifeSource
from backend.app.config import get_settings


@dataclass(frozen=True)
class FoodKeeperResult:
    """Result of FoodKeeper BigQuery lookup."""
    product_id: str
    product_name: str
    product_subtitle: Optional[str]
    category: str
    refrigerated_hours: Optional[float]
    pantry_hours: Optional[float]
    conservative_hours: float


@dataclass(frozen=True)
class ResolvedClock:
    """Resolved clock fields guaranteed as single source of truth."""
    resolved_deadline: datetime
    resolved_shelf_life_hours: Optional[float]
    shelf_life_source: ShelfLifeSource
    resolved_at: datetime
    effective_hours: float


NON_FOOD_KEYWORDS = ["diaper", "diapers", "wipe", "wipes", "essential", "hygiene", "formula, sealed"]
DONOR_FALLBACK_KEYWORDS = ["milk", "dairy", "yogurt", "infant formula", "formula"]


def is_non_food(product_or_text: str) -> bool:
    """Check if item is non-food where FoodKeeper shelf-life is NOT_APPLICABLE."""
    low = (product_or_text or "").lower()
    return any(kw in low for kw in ["diaper", "wipe", "hygiene", "soap", "sanitizer"])


def is_package_or_sealed_fallback(product_or_text: str) -> bool:
    """Check if item is package use-by / sealed formula tracked only after opening."""
    low = (product_or_text or "").lower()
    if is_non_food(low):
        return False
    return any(kw in low for kw in ["milk", "dairy", "yogurt", "infant formula", "sealed formula"])


def lookup_foodkeeper(
    client: bigquery.Client,
    product_query: str,
    storage_state: str = "refrigerated",
) -> Optional[FoodKeeperResult]:
    """Look up FoodKeeper shelf-life in a4i_food.shelf_life.
    
    Handles Spinach-under-Lettuce subtitle match and returns conservative shelf life hours.
    """
    settings = get_settings()
    project = settings.google_cloud_project
    dataset = settings.bq_dataset_starter
    query_clean = (product_query or "").strip().lower()

    if not query_clean or query_clean in ("none", "null"):
        return None

    # Query BigQuery shelf_life table
    sql = f"""
    SELECT 
        product_id,
        product_name,
        product_subtitle,
        category,
        refrigerated_hours,
        pantry_hours
    FROM `{project}.{dataset}.shelf_life`
    WHERE LOWER(product_name) = @clean_query
       OR LOWER(product_name) LIKE @like_query
       OR (product_subtitle IS NOT NULL AND LOWER(product_subtitle) LIKE @like_query)
       OR (keywords IS NOT NULL AND LOWER(keywords) LIKE @like_query)
    ORDER BY 
        -- Exact match priority
        CASE WHEN LOWER(product_name) = @clean_query THEN 1
             WHEN product_subtitle IS NOT NULL AND LOWER(product_subtitle) LIKE @like_query THEN 2
             ELSE 3
        END,
        -- Conservative end of range (minimum shelf life hours)
        COALESCE(refrigerated_hours, pantry_hours, 999999.0) ASC
    LIMIT 5
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("clean_query", "STRING", query_clean),
            bigquery.ScalarQueryParameter("like_query", "STRING", f"%{query_clean}%"),
        ]
    )
    results = list(client.query(sql, job_config=job_config).result())
    if not results:
        return None

    best = results[0]
    is_pantry = storage_state.lower() in ("pantry", "ambient", "dry")
    if is_pantry:
        conservative = best.pantry_hours if best.pantry_hours is not None else best.refrigerated_hours
    else:
        conservative = best.refrigerated_hours if best.refrigerated_hours is not None else best.pantry_hours

    if conservative is None:
        conservative = 72.0

    return FoodKeeperResult(
        product_id=str(best.product_id),
        product_name=best.product_name,
        product_subtitle=best.product_subtitle,
        category=best.category,
        refrigerated_hours=best.refrigerated_hours,
        pantry_hours=best.pantry_hours,
        conservative_hours=float(conservative),
    )


def resolve_clock(
    hours_available: float,
    product_name: Optional[str] = None,
    posting_text: Optional[str] = None,
    fk_shelf_life_hours: Optional[float] = None,
    base_time: Optional[datetime] = None,
) -> ResolvedClock:
    """Resolve clock deadline and source deterministically.
    
    Rules:
    - Diapers / non-food -> NOT_APPLICABLE, hours = hours_available.
    - Milk / sealed formula / NULL shelf-life -> DONOR_FALLBACK, hours = hours_available.
    - FoodKeeper product -> min(fk_shelf_life_hours, hours_available) (donor deadline beats book!).
    """
    resolved_at = base_time or datetime.now(timezone.utc)
    combined_text = f"{product_name or ''} {posting_text or ''}".strip().lower()

    # Rule 1: Non-food items (diapers, wipes)
    if is_non_food(combined_text):
        effective_hrs = float(hours_available)
        return ResolvedClock(
            resolved_deadline=resolved_at + timedelta(hours=effective_hrs),
            resolved_shelf_life_hours=None,
            shelf_life_source=ShelfLifeSource.NOT_APPLICABLE,
            resolved_at=resolved_at,
            effective_hours=effective_hrs,
        )

    # Rule 2: Milk / sealed infant formula / missing FoodKeeper data
    if fk_shelf_life_hours is None or is_package_or_sealed_fallback(combined_text):
        effective_hrs = float(hours_available)
        return ResolvedClock(
            resolved_deadline=resolved_at + timedelta(hours=effective_hrs),
            resolved_shelf_life_hours=None,
            shelf_life_source=ShelfLifeSource.DONOR_FALLBACK,
            resolved_at=resolved_at,
            effective_hours=effective_hrs,
        )

    # Rule 3 & 4: FoodKeeper shelf life present; donor deadline beats the book!
    effective_hrs = min(float(fk_shelf_life_hours), float(hours_available))
    return ResolvedClock(
        resolved_deadline=resolved_at + timedelta(hours=effective_hrs),
        resolved_shelf_life_hours=float(fk_shelf_life_hours),
        shelf_life_source=ShelfLifeSource.FOODKEEPER,
        resolved_at=resolved_at,
        effective_hours=effective_hrs,
    )


def compute_margin_hours(
    resolved_deadline: datetime,
    pickup_window_hours: float,
    travel_buffer_hours: float = 1.0,
    current_time: Optional[datetime] = None,
) -> float:
    """Compute margin: hours left on resolved clock - pickup window - travel buffer."""
    now = current_time or datetime.now(timezone.utc)
    if resolved_deadline.tzinfo is None:
        resolved_deadline = resolved_deadline.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    hours_left = (resolved_deadline - now).total_seconds() / 3600.0
    return hours_left - float(pickup_window_hours) - float(travel_buffer_hours)

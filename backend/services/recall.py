"""Recall Guard service with openFDA Food Enforcement API integration.

Per Part 2 lines 1325-1330:
1. openFDA check runs BEFORE matching.
2. HALTED blocks the item / posting.
3. Any failure or timeout returns NOT_CHECKED, NEVER CLEAR.
4. Offline snapshot fallback is allowed only if explicitly labelled as OFFLINE_SNAPSHOT.
5. All checks are recorded to Firestore `recall_checks`.
"""

from datetime import datetime, timezone
import logging
import re
from typing import Any, Dict, List, Optional
import uuid
import httpx

from schemas.api import RecallCheckResponse
from schemas.enums import RecallSource, RecallVerdict
from backend.app.config import get_settings
from backend.db.firestore import save_recall_check, get_recall_checks


logger = logging.getLogger(__name__)

OPENFDA_FOOD_ENFORCEMENT_URL = "https://api.fda.gov/food/enforcement.json"


def _clean_query_term(term: str) -> str:
    """Sanitize free-text product terms for openFDA query string."""
    cleaned = re.sub(r'[^a-zA-Z0-9\s]', ' ', term)
    tokens = [t.strip() for t in cleaned.split() if len(t.strip()) >= 3]
    return " ".join(tokens[:2]) if tokens else "food"


def check_recall(
    ticket_id: str,
    product_text: str,
    force_failure: bool = False,
    use_snapshot: bool = False,
    snapshot_data: Optional[Dict[str, Any]] = None,
) -> RecallCheckResponse:
    """Execute Recall Guard check via openFDA Food Enforcement API.
    
    Rules:
    - HALTED if active recall matches the product/brand in distribution area.
    - CLEAR if openFDA confirms 0 active recalls for query.
    - NOT_CHECKED if network error, timeout, HTTP 5xx, or forced failure occurs. Never CLEAR on failure!
    """
    settings = get_settings()
    check_id = f"chk-{uuid.uuid4().hex[:10]}"
    checked_at = datetime.now(timezone.utc)
    search_term = _clean_query_term(product_text)
    fda_query = f'status:"Ongoing" AND product_description:"{search_term}"'

    # 1. Forced failure / simulation test path
    if force_failure:
        record = RecallCheckResponse(
            check_id=check_id,
            ticket_id=ticket_id,
            product_text=product_text,
            fda_query=fda_query,
            verdict=RecallVerdict.NOT_CHECKED,
            recall_id=None,
            checked_at=checked_at,
            source=RecallSource.LIVE_OPENFDA,
        )
        save_recall_check(record.model_dump())
        return record

    # 2. Offline snapshot fallback
    if use_snapshot:
        verdict = RecallVerdict.CLEAR
        recall_id = None
        if snapshot_data and snapshot_data.get("matches"):
            verdict = RecallVerdict.HALTED
            recall_id = snapshot_data["matches"][0].get("recall_number", "SNAPSHOT-RECALL-001")
        record = RecallCheckResponse(
            check_id=check_id,
            ticket_id=ticket_id,
            product_text=product_text,
            fda_query=fda_query,
            verdict=verdict,
            recall_id=recall_id,
            checked_at=checked_at,
            source=RecallSource.OFFLINE_SNAPSHOT,
        )
        save_recall_check(record.model_dump())
        return record

    # 3. Live openFDA API call
    params = {
        "search": f'status:"Ongoing" AND product_description:"{search_term}"',
        "limit": 5,
    }

    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(OPENFDA_FOOD_ENFORCEMENT_URL, params=params)

        if resp.status_code == 200:
            data = resp.json()
            results = data.get("results", [])
            if results:
                # Active ongoing recall found
                matched_recall = results[0]
                rec_id = matched_recall.get("recall_number") or matched_recall.get("event_id") or "FDA-RECALL"
                record = RecallCheckResponse(
                    check_id=check_id,
                    ticket_id=ticket_id,
                    product_text=product_text,
                    fda_query=params["search"],
                    verdict=RecallVerdict.HALTED,
                    recall_id=rec_id,
                    checked_at=checked_at,
                    source=RecallSource.LIVE_OPENFDA,
                )
            else:
                record = RecallCheckResponse(
                    check_id=check_id,
                    ticket_id=ticket_id,
                    product_text=product_text,
                    fda_query=params["search"],
                    verdict=RecallVerdict.CLEAR,
                    recall_id=None,
                    checked_at=checked_at,
                    source=RecallSource.LIVE_OPENFDA,
                )
        elif resp.status_code == 404:
            # openFDA returns 404 with {"error": {"code": "NOT_FOUND"}} when 0 records match
            record = RecallCheckResponse(
                check_id=check_id,
                ticket_id=ticket_id,
                product_text=product_text,
                fda_query=params["search"],
                verdict=RecallVerdict.CLEAR,
                recall_id=None,
                checked_at=checked_at,
                source=RecallSource.LIVE_OPENFDA,
            )
        else:
            # Any HTTP error (429, 500, 503) -> NOT_CHECKED (never CLEAR)
            logger.warning(f"openFDA returned non-200/404 code: {resp.status_code}")
            record = RecallCheckResponse(
                check_id=check_id,
                ticket_id=ticket_id,
                product_text=product_text,
                fda_query=params["search"],
                verdict=RecallVerdict.NOT_CHECKED,
                recall_id=None,
                checked_at=checked_at,
                source=RecallSource.LIVE_OPENFDA,
            )

    except Exception as exc:
        # Any exception/timeout -> NOT_CHECKED (never CLEAR)
        logger.error(f"openFDA connection error: {exc}")
        record = RecallCheckResponse(
            check_id=check_id,
            ticket_id=ticket_id,
            product_text=product_text,
            fda_query=params["search"],
            verdict=RecallVerdict.NOT_CHECKED,
            recall_id=None,
            checked_at=checked_at,
            source=RecallSource.LIVE_OPENFDA,
        )

    # Persist check record in Firestore
    save_recall_check(record.model_dump())
    return record


def list_ticket_recall_checks(ticket_id: str) -> List[RecallCheckResponse]:
    """Retrieve all recall checks performed for a given ticket."""
    raw_checks = get_recall_checks(ticket_id)
    return [RecallCheckResponse(**chk) for chk in raw_checks]

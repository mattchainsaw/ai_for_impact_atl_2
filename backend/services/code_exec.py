"""Gemini Code Execution integration for Planner / Splitter maths (Review Fix M1).

Part 2 locked rule:
Split and margin maths for a plan MUST be executed through the Gemini Code Execution
tool called by the Planner/Splitter.
Inputs: candidate allocations, quantities, unit, capacities, pickup windows, travel buffers, resolved hours left.
Outputs stored on the plan: split quantities, margins, plus {execution_code, execution_output, execution_source}.
Fallback only: if Code Execution is unavailable in the lab, run the identical deterministic Python calculation,
store execution_source: PYTHON_FALLBACK + reason + code + output.
"""

from datetime import datetime, timezone
import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from google import genai
from google.genai import types

from schemas.enums import ExecutionSource
from backend.app.config import get_settings

logger = logging.getLogger(__name__)


def generate_deterministic_split_script(
    total_quantity: float,
    quantity_unit: str,
    pallets_needed: float,
    candidates: List[Dict[str, Any]],
    resolved_shelf_life_hours: float,
    split_allowed: bool = True,
    crates_per_pallet: int = 20,
) -> Tuple[str, str, List[Dict[str, Any]]]:
    """Pure deterministic Python calculation of splits and margins, returning (code, output, allocations)."""
    code = f"""# Deterministic Split & Margin Calculation
import json

total_quantity = {total_quantity}
quantity_unit = "{quantity_unit}"
pallets_needed = {pallets_needed}
crates_per_pallet = {crates_per_pallet}
resolved_shelf_life_hours = {resolved_shelf_life_hours}
split_allowed = {split_allowed}
candidates = {json.dumps(candidates, indent=2)}

allocations = []
remaining_pallets = float(pallets_needed)

for cand in candidates:
    if remaining_pallets <= 0.0:
        break
    cap = float(cand.get("max_pallets", 1.0))
    take_pallets = min(cap, remaining_pallets) if split_allowed else (pallets_needed if cap >= pallets_needed else 0.0)
    if take_pallets <= 0.0:
        continue
    
    if quantity_unit.upper() == "CRATES":
        take_qty = round(take_pallets * crates_per_pallet, 1)
    else:
        take_qty = round(take_pallets, 2)
        
    window = float(cand.get("pickup_window_hours", 2.0))
    buffer = float(cand.get("travel_buffer_hours", 0.5))
    margin = round(resolved_shelf_life_hours - window - buffer, 2)
    
    allocations.append({{
        "recipient_id": int(cand["recipient_id"]),
        "recipient_name": str(cand.get("name", "")),
        "quantity": take_qty,
        "quantity_unit": quantity_unit,
        "pallets_equivalent": round(take_pallets, 2),
        "clock_margin_hours": margin,
        "tract_geo_id": str(cand.get("tract_geo_id", "13121000000")),
        "need_score": float(cand.get("need_score", 50.0)),
        "donor_to_recipient_distance_km": float(cand.get("distance_km", 0.0)),
    }})
    remaining_pallets = round(remaining_pallets - take_pallets, 4)
    if not split_allowed:
        break

output = {{
    "allocations": allocations,
    "remaining_unallocated_pallets": remaining_pallets,
}}
print(json.dumps(output, indent=2))
"""
    # Execute deterministic logic in Python
    allocations: List[Dict[str, Any]] = []
    rem_pallets = float(pallets_needed)
    
    for cand in candidates:
        if rem_pallets <= 0.0:
            break
        cap = float(cand.get("max_pallets", 1.0))
        take_pallets = min(cap, rem_pallets) if split_allowed else (pallets_needed if cap >= pallets_needed else 0.0)
        if take_pallets <= 0.0:
            continue
            
        if quantity_unit.upper() == "CRATES":
            take_qty = round(take_pallets * crates_per_pallet, 1)
        else:
            take_qty = round(take_pallets, 2)
            
        window = float(cand.get("pickup_window_hours", 2.0))
        buf = float(cand.get("travel_buffer_hours", 0.5))
        margin = round(resolved_shelf_life_hours - window - buf, 2)
        
        allocations.append({
            "recipient_id": int(cand["recipient_id"]),
            "recipient_name": str(cand.get("name", "")),
            "quantity": take_qty,
            "quantity_unit": quantity_unit,
            "pallets_equivalent": round(take_pallets, 2),
            "clock_margin_hours": margin,
            "tract_geo_id": str(cand.get("tract_geo_id", "13121000000")),
            "need_score": float(cand.get("need_score", 50.0)),
            "donor_to_recipient_distance_km": float(cand.get("distance_km", 0.0)),
        })
        rem_pallets = round(rem_pallets - take_pallets, 4)
        if not split_allowed:
            break

    output_dict = {
        "allocations": allocations,
        "remaining_unallocated_pallets": rem_pallets,
    }
    output_str = json.dumps(output_dict, indent=2)
    return code, output_str, allocations


def execute_split_and_margin(
    total_quantity: float,
    quantity_unit: str,
    pallets_needed: float,
    candidates: List[Dict[str, Any]],
    resolved_shelf_life_hours: float,
    split_allowed: bool = True,
    crates_per_pallet: int = 20,
    force_fallback: bool = False,
) -> Dict[str, Any]:
    """Execute split & margin maths using Gemini Code Execution tool (with labeled fallback)."""
    settings = get_settings()

    # If force_fallback is explicitly requested (e.g. for offline testing)
    if force_fallback:
        code, out, allocs = generate_deterministic_split_script(
            total_quantity=total_quantity,
            quantity_unit=quantity_unit,
            pallets_needed=pallets_needed,
            candidates=candidates,
            resolved_shelf_life_hours=resolved_shelf_life_hours,
            split_allowed=split_allowed,
            crates_per_pallet=crates_per_pallet,
        )
        return {
            "allocations": allocs,
            "execution_source": ExecutionSource.PYTHON_FALLBACK,
            "execution_code": code,
            "execution_output": out,
            "fallback_reason": "Forced fallback requested",
        }

    # Attempt primary execution via Gemini Code Execution tool
    try:
        client = genai.Client(
            vertexai=True,
            project=settings.google_cloud_project,
            location=settings.google_cloud_location,
        )

        candidates_payload = [
            {
                "recipient_id": int(c["recipient_id"]),
                "name": str(c.get("name", "")),
                "max_pallets": float(c.get("max_pallets", 1.0)),
                "pickup_window_hours": float(c.get("pickup_window_hours", 2.0)),
                "travel_buffer_hours": float(c.get("travel_buffer_hours", 0.5)),
                "tract_geo_id": str(c.get("tract_geo_id", "13121000000")),
                "need_score": float(c.get("need_score", 50.0)),
                "distance_km": float(c.get("distance_km", 0.0)),
            }
            for c in candidates
        ]

        prompt = f"""You MUST use the code execution tool to write and execute Python code to calculate the split of surplus and clock margins across recipient pantries.
Surplus: total_quantity={total_quantity} {quantity_unit} ({pallets_needed} pallets equivalent).
Crates per pallet: {crates_per_pallet}.
Split allowed: {split_allowed}.
Resolved shelf-life hours: {resolved_shelf_life_hours}.
Candidates: {json.dumps(candidates_payload)}

Rules:
1. For each allocated pantry, allocated pallets cannot exceed max_pallets.
2. If single pantry can take whole load and split_allowed is False (or first pantry capacity >= pallets_needed), allocate whole load to candidate 1.
3. Otherwise, if split is needed and allowed, distribute across pantries in order up to 3 pantries without exceeding their capacities until all pallets are allocated.
4. For each allocated pantry, clock_margin_hours = resolved_shelf_life_hours - pickup_window_hours - travel_buffer_hours.
5. Print valid JSON with format:
{{
  "allocations": [
    {{
      "recipient_id": int,
      "recipient_name": str,
      "quantity": float,
      "quantity_unit": str,
      "pallets_equivalent": float,
      "clock_margin_hours": float,
      "tract_geo_id": str,
      "need_score": float,
      "donor_to_recipient_distance_km": float
    }}
  ],
  "remaining_unallocated_pallets": float
}}
"""
        response = client.models.generate_content(
            model=settings.model_id,
            contents=prompt,
            config=types.GenerateContentConfig(
                tools=[types.Tool(code_execution=types.ToolCodeExecution())],
                temperature=0.0,
            ),
        )

        code_str: Optional[str] = None
        output_str: Optional[str] = None

        for part in response.candidates[0].content.parts:
            if part.executable_code:
                code_str = part.executable_code.code
            if part.code_execution_result:
                output_str = part.code_execution_result.output

        if code_str and output_str:
            # Parse allocations from the code output
            # Strip markdown code blocks if wrapped
            clean_out = output_str.strip()
            if clean_out.startswith("```json"):
                clean_out = clean_out[7:]
            if clean_out.startswith("```"):
                clean_out = clean_out[3:]
            if clean_out.endswith("```"):
                clean_out = clean_out[:-3]
            clean_out = clean_out.strip()

            parsed = json.loads(clean_out)
            allocs = parsed.get("allocations", [])
            return {
                "allocations": allocs,
                "execution_source": ExecutionSource.CODE_EXECUTION,
                "execution_code": code_str,
                "execution_output": output_str,
                "fallback_reason": None,
            }
        else:
            logger.warning("Gemini did not return executable_code / code_execution_result; falling back")
            fallback_reason = "Model generated response without invoking code execution"

    except Exception as exc:
        logger.warning("Gemini Code Execution failed: %s; using deterministic fallback", exc)
        fallback_reason = str(exc)

    # Fallback path: deterministic in-process calculation
    code, out, allocs = generate_deterministic_split_script(
        total_quantity=total_quantity,
        quantity_unit=quantity_unit,
        pallets_needed=pallets_needed,
        candidates=candidates,
        resolved_shelf_life_hours=resolved_shelf_life_hours,
        split_allowed=split_allowed,
        crates_per_pallet=crates_per_pallet,
    )
    return {
        "allocations": allocs,
        "execution_source": ExecutionSource.PYTHON_FALLBACK,
        "execution_code": code,
        "execution_output": out,
        "fallback_reason": fallback_reason,
    }


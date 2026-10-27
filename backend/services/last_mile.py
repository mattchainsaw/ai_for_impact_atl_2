"""Last-Mile logistics, distance calculations, and travel buffer service.

Per Part 2 lines 1318-1324:
1. Distance is computed via Haversine between ZIP centroids (labelled DistanceSource.HAVERSINE_FALLBACK, approximate=True).
2. Pair cache is maintained in Firestore `distance_pairs` as a lookup.
3. Travel buffer is added to pickup window when computing clock safety margin:
   margin = resolved_hours_left - pickup_window_hours - travel_buffer_hours.
4. Negative margin filters candidate out with an explicit reason.
5. Logistics capabilities: self-collect vs needs-driver from refrigerated_transport;
   loading dock vs hand-unload only.
"""

import math
from typing import Optional, Tuple
from schemas.enums import DistanceSource
from schemas.common import compute_clock_margin_hours
from backend.db.firestore import get_cached_distance, cache_distance_pair


# Earth radius in kilometers
EARTH_RADIUS_KM = 6371.0


def calculate_haversine_distance_km(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> float:
    """Calculate Great Circle distance between two points in kilometers."""
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * (math.sin(delta_lambda / 2.0) ** 2)
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return round(EARTH_RADIUS_KM * c, 2)


def compute_travel_buffer_hours(distance_km: float) -> float:
    """Compute travel buffer hours based on metro travel distance.
    
    Local metro buffer:
    - <= 15 km: 0.5 hours (30 min)
    - 15 km - 35 km: 1.0 hours (60 min)
    - > 35 km: 1.5 hours (90 min)
    """
    if distance_km <= 15.0:
        return 0.5
    elif distance_km <= 35.0:
        return 1.0
    else:
        return 1.5


def resolve_distance_and_margin(
    donor_lat: Optional[float],
    donor_lon: Optional[float],
    donor_zip: str,
    recipient_lat: Optional[float],
    recipient_lon: Optional[float],
    recipient_zip: str,
    pickup_window_hours: float,
    resolved_hours_left: float,
) -> Tuple[float, DistanceSource, float, float]:
    """Resolve distance (with pair caching), travel buffer, and safety margin.
    
    Returns:
        (distance_km, distance_source, travel_buffer_hours, margin_hours)
    """
    # 1. Check pair cache if ZIPs available
    cached_dist = None
    if donor_zip and recipient_zip:
        cached_dist = get_cached_distance(donor_zip, recipient_zip)

    if cached_dist is not None:
        distance_km = cached_dist
    else:
        # 2. Compute Haversine distance
        if (
            donor_lat is not None
            and donor_lon is not None
            and recipient_lat is not None
            and recipient_lon is not None
        ):
            distance_km = calculate_haversine_distance_km(
                donor_lat, donor_lon, recipient_lat, recipient_lon
            )
        else:
            # Fallback distance if coordinates missing
            distance_km = 12.0

        # Cache in Firestore distance_pairs
        if donor_zip and recipient_zip:
            cache_distance_pair(donor_zip, recipient_zip, distance_km)

    # 3. Travel buffer and safety margin
    travel_buffer = compute_travel_buffer_hours(distance_km)
    margin = compute_clock_margin_hours(
        resolved_hours_left=resolved_hours_left,
        pickup_window_hours=pickup_window_hours,
        travel_buffer_hours=travel_buffer,
    )

    return distance_km, DistanceSource.HAVERSINE_FALLBACK, travel_buffer, margin


def evaluate_logistics_capabilities(
    refrigerated_transport: Optional[bool],
    loading_dock: Optional[bool],
    temperature_requirement: str = "refrigerated",
) -> Tuple[str, str]:
    """Evaluate transport requirement and loading capability.
    
    Returns:
        (transport_mode, loading_mode)
        transport_mode: 'self_collect' or 'needs_driver'
        loading_mode: 'dock_loading' or 'hand_unload'
    """
    needs_cold = temperature_requirement.lower() in ["refrigerated", "cold", "frozen"]
    
    if needs_cold:
        if refrigerated_transport is True:
            transport_mode = "self_collect"
        else:
            transport_mode = "needs_driver"
    else:
        transport_mode = "self_collect"

    if loading_dock is True:
        loading_mode = "dock_loading"
    else:
        loading_mode = "hand_unload"

    return transport_mode, loading_mode


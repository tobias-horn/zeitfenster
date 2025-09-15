import time
from typing import List, Optional, Dict, Any

try:
    # mvg is provided via https://pypi.org/project/mvg/
    from mvg import MvgApi, TransportType
except Exception:  # pragma: no cover - allow running without dependency locally
    MvgApi = None  # type: ignore
    TransportType = None  # type: ignore


TRANSPORT_TYPE_MAP = {
    'UBAHN': 'U-Bahn',
    'SBAHN': 'S-Bahn',
    'BUS': 'Bus',
    'TRAM': 'Tram',
}


def _resolve_transport_labels(type_names: Optional[List[str]]):
    """Map config type names (e.g., 'UBAHN') to MVG 'type' labels (e.g., 'U-Bahn')."""
    if not type_names:
        return None
    labels = []
    for name in type_names:
        key = (name or '').upper()
        if key in TRANSPORT_TYPE_MAP:
            labels.append(TRANSPORT_TYPE_MAP[key])
    return labels or None


def get_departures_for_station(
    station_query: str,
    *,
    limit: int = 4,
    offset: int = 0,
    transport_types: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """Get simplified departures for a station and enforce total count across selected types.

    - If transport_types is provided (e.g., ['UBAHN', 'BUS']), return the next
      departures across those types with a TOTAL count of `limit`.
    - If a single type is provided, return `limit` departures of that type.
    - If no types are provided, return `limit` departures across all types.

    Returns a list of dicts with: line, destination, minutes, cancelled, type.
    """
    if MvgApi is None:
        # Dependency not available. Caller can decide to fallback to embed.
        return []

    station = MvgApi.station(station_query)
    if not station:
        return []

    api = MvgApi(station['id'])
    labels = _resolve_transport_labels(transport_types)
    try:
        # Request more than needed to be able to filter locally and still keep TOTAL=limit
        internal_limit = max(limit * 5, 20)
        dep_list = api.departures(limit=internal_limit, offset=offset)
    except Exception:
        return []

    now_s = int(time.time())
    simplified: List[Dict[str, Any]] = []
    for dep in dep_list:
        dep_type = dep.get('type', '')
        if labels and dep_type not in labels:
            continue
        when = int(dep.get('time') or dep.get('planned') or now_s)
        minutes = max(0, round((when - now_s) / 60))
        simplified.append({
            'line': dep.get('line', ''),
            'destination': dep.get('destination', ''),
            'minutes': minutes,
            'cancelled': bool(dep.get('cancelled', False)),
            'type': dep_type,
        })
        if len(simplified) >= limit:
            break

    return simplified

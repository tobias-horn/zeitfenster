# weather.py

import requests
from datetime import datetime
import time
from typing import Any, Dict, Optional, Tuple

from transport import get_station_coordinates

try:
    # Python 3.9+
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover
    ZoneInfo = None  # type: ignore


def _to_local(dt_str: str, tzname: str = "Europe/Berlin") -> datetime:
    try:
        # Open-Meteo returns local time already when timezone parameter is set.
        # Still, parse to datetime for comparisons.
        dt = datetime.fromisoformat(dt_str)
        if dt.tzinfo is None and ZoneInfo is not None:
            dt = dt.replace(tzinfo=ZoneInfo(tzname))
        return dt
    except Exception:
        return datetime.utcnow()


def _round_temperature(value):
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return value


DEFAULT_COORDINATES: Tuple[float, float] = (48.183171, 11.611294)
_WEATHER_CACHE: Dict[str, Dict[str, Any]] = {}
_WEATHER_TTL_SECONDS = 600  # 10 minutes


def _resolve_coordinates(station_query: Optional[str]) -> Tuple[float, float]:
    coords = get_station_coordinates(station_query or '')
    if coords and all(component is not None for component in coords):
        return coords
    return DEFAULT_COORDINATES


def get_weather_data(station_query: Optional[str] = None):
    lat, lon = _resolve_coordinates(station_query)
    cache_key = f"{lat:.4f},{lon:.4f}"
    cached_entry = _WEATHER_CACHE.get(cache_key)
    cache_ts = cached_entry['ts'] if cached_entry else 0.0
    now_ts = time.time()
    if cached_entry and (now_ts - cache_ts) < _WEATHER_TTL_SECONDS:
        return cached_entry['data']

    meteo_url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat:.6f}&longitude={lon:.6f}"
        "&current=temperature_2m"
        "&hourly=uv_index"
        "&daily=temperature_2m_max,temperature_2m_min,uv_index_max,sunrise,sunset"
        "&timezone=Europe%2FBerlin&forecast_days=2"
    )

    try:
        response = requests.get(meteo_url)
        response.raise_for_status()
        data = response.json()

        # Extract current temperature
        current_temperature = _round_temperature(data['current']['temperature_2m'])

        daily = data['daily']

        # Determine whether to show today's or tomorrow's UV index based on sunset
        tzname = "Europe/Berlin"
        now_local = (datetime.now(ZoneInfo(tzname)) if ZoneInfo else datetime.now())

        today_sunset = _to_local(daily['sunset'][0], tzname)
        use_idx = 1 if now_local > today_sunset else 0

        max_temp = _round_temperature(daily['temperature_2m_max'][0])
        min_temp = _round_temperature(daily['temperature_2m_min'][0])

        uv_day_label = 'Morgen' if use_idx == 1 else 'Heute'

        hourly = data.get('hourly', {})
        hourly_times = hourly.get('time') or []
        hourly_uv = hourly.get('uv_index') or []
        remaining_uv = None

        if use_idx == 0 and hourly_times and hourly_uv:
            # Find the maximum forecast UV value still ahead of us today.
            today = now_local.date()
            for ts, uv_val in zip(hourly_times, hourly_uv):
                try:
                    uv_float = float(uv_val)
                except (TypeError, ValueError):
                    continue
                dt_local = _to_local(ts, tzname)
                if dt_local.date() != today:
                    continue
                if dt_local < now_local:
                    continue
                remaining_uv = uv_float if remaining_uv is None else max(remaining_uv, uv_float)

        if use_idx == 0:
            uv_index = remaining_uv if remaining_uv is not None else daily['uv_index_max'][0]
        else:
            uv_index = daily['uv_index_max'][use_idx]

        sunrise = daily['sunrise'][use_idx]
        sunset = daily['sunset'][use_idx]

        # Prepare the weather data dictionary
        weather_data = {
            'current_temperature': current_temperature,
            'max_temperature': max_temp,
            'min_temperature': min_temp,
            'uv_index_max': uv_index,
            'uv_day_label': uv_day_label,
            'sunrise': sunrise,
            'sunset': sunset,
            'latitude': lat,
            'longitude': lon,
        }

        _WEATHER_CACHE[cache_key] = {'data': weather_data, 'ts': time.time()}
        return weather_data

    except requests.RequestException as e:
        print(f"Error fetching weather data: {e}")
        if cached_entry is not None:
            return cached_entry['data']
        return None
    except KeyError as e:
        print(f"Key error: {e}")
        if cached_entry is not None:
            return cached_entry['data']
        return None

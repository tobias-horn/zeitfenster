# weather.py

import requests
from datetime import datetime
import time

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


_WEATHER_CACHE = {'data': None, 'ts': 0.0}
_WEATHER_TTL_SECONDS = 600  # 10 minutes


def get_weather_data():
    meteo_url = (
        "https://api.open-meteo.com/v1/forecast"
        "?latitude=48.183171&longitude=11.611294"
        "&current=temperature_2m"
        "&daily=temperature_2m_max,temperature_2m_min,uv_index_max,sunrise,sunset"
        "&timezone=Europe%2FBerlin&forecast_days=2"
    )

    cached_data = _WEATHER_CACHE.get('data')
    cache_ts = _WEATHER_CACHE.get('ts', 0.0)
    now_ts = time.time()
    if cached_data is not None and (now_ts - cache_ts) < _WEATHER_TTL_SECONDS:
        return cached_data

    try:
        response = requests.get(meteo_url, timeout=5)
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

        uv_index = daily['uv_index_max'][use_idx]
        uv_day_label = 'Morgen' if use_idx == 1 else 'Heute'

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
        }

        _WEATHER_CACHE.update({'data': weather_data, 'ts': time.time()})
        return weather_data

    except requests.RequestException as e:
        print(f"Error fetching weather data: {e}")
        if cached_data is not None:
            return cached_data
        return None
    except KeyError as e:
        print(f"Key error: {e}")
        if cached_data is not None:
            return cached_data
        return None

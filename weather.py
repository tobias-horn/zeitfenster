# weather.py

import requests
from datetime import datetime

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


def get_weather_data():
    meteo_url = (
        "https://api.open-meteo.com/v1/forecast"
        "?latitude=48.183171&longitude=11.611294"
        "&current=temperature_2m"
        "&daily=temperature_2m_max,temperature_2m_min,uv_index_max,sunrise,sunset"
        "&timezone=Europe%2FBerlin&forecast_days=2"
    )

    try:
        response = requests.get(meteo_url)
        response.raise_for_status()
        data = response.json()

        # Extract current temperature
        current_temperature = data['current']['temperature_2m']

        daily = data['daily']

        # Determine whether to show today's or tomorrow's UV index based on sunset
        tzname = "Europe/Berlin"
        now_local = (datetime.now(ZoneInfo(tzname)) if ZoneInfo else datetime.now())

        today_sunset = _to_local(daily['sunset'][0], tzname)
        use_idx = 1 if now_local > today_sunset else 0

        max_temp = daily['temperature_2m_max'][0]
        min_temp = daily['temperature_2m_min'][0]

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

        return weather_data

    except requests.RequestException as e:
        print(f"Error fetching weather data: {e}")
        return None
    except KeyError as e:
        print(f"Key error: {e}")
        return None

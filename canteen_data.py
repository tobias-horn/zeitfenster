# canteen_data.py

import requests
from datetime import datetime, timedelta
import time
import config

_MENU_CACHE = {}
_MENU_CACHE_TTL_SECONDS = 3600  # 1 hour

def get_current_date_info():
    today = datetime.now()
    date_str = today.strftime('%Y-%m-%d')
    return date_str, today

def fetch_menu_for_key(canteen_key, year, week_num):
    url = f"https://tum-dev.github.io/eat-api/{canteen_key}/{year}/{week_num:02d}.json"
    try:
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        menu_data = response.json()
        return menu_data
    except requests.RequestException as e:
        print(f"Error fetching menu data: {e}")
        return None

def get_todays_menu(canteen_key: str | None = None):
    """Return the menu for today, except after 14:00 switch to the next day.

    Falls back to the next available day (max 7 days ahead) if no dishes
    are available for the chosen date (e.g., weekends or holidays).
    """
    now = datetime.now()
    # After 14:00, show menu for the next day
    date_obj = now + timedelta(days=1) if now.hour >= 14 else now
    attempts = 0
    max_attempts = 7  # Limit to 7 days ahead
    menu_data_cache = {}
    if not canteen_key:
        canteen_key = getattr(config, 'CANTEEN_KEY', 'mensa-garching')

    target_date_str = date_obj.strftime('%Y-%m-%d')
    cache_key = (canteen_key, target_date_str)
    cache_entry = _MENU_CACHE.get(cache_key)
    stale_data = cache_entry.get('data') if cache_entry else None
    now_ts = time.time()
    if cache_entry and (now_ts - cache_entry.get('ts', 0.0)) < _MENU_CACHE_TTL_SECONDS:
        return cache_entry.get('data')

    while attempts < max_attempts:
        date_str = date_obj.strftime('%Y-%m-%d')
        year = date_obj.year
        week_num = date_obj.isocalendar()[1]

        if (year, week_num) not in menu_data_cache:
            menu_data = fetch_menu_for_key(canteen_key, year, week_num)
            if not menu_data:
                # Cannot fetch menu data for this week
                menu_data_cache[(year, week_num)] = None
            else:
                menu_data_cache[(year, week_num)] = menu_data
        else:
            menu_data = menu_data_cache[(year, week_num)]

        if menu_data:
            days = menu_data.get('days', [])
            # Find the day matching the target_date
            todays_entry = next((day for day in days if day.get('date') == date_str), None)
            if todays_entry:
                dishes = todays_entry.get('dishes', [])
                if dishes:
                    # Prepare data for the template
                    canteen_data = {
                        'date': date_str,
                        'dishes': dishes
                    }
                    _MENU_CACHE[cache_key] = {'ts': time.time(), 'data': canteen_data}
                    return canteen_data
        # If not found, increment date_obj by one day
        date_obj += timedelta(days=1)
        attempts += 1

    # After max_attempts days, if no menu found
    print("No available menu found in the next 7 days.")
    if stale_data is not None:
        return stale_data
    return None

def get_canteen_name(canteen_key):
    url = "https://tum-dev.github.io/eat-api/enums/canteens.json"
    try:
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        canteens = response.json()
        
        # Find the canteen with the matching canteen_id
        for canteen in canteens:
            if canteen["canteen_id"] == canteen_key:
                return canteen["name"]
        
        return "Canteen not found"
    except requests.RequestException as e:
        print(f"Error fetching canteen data: {e}")
        return None

def list_canteens():
    """Return list of canteens as [{'id': key, 'name': name}, ...]."""
    url = "https://tum-dev.github.io/eat-api/enums/canteens.json"
    try:
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        canteens = response.json()
        out = []
        for c in canteens:
            out.append({'id': c.get('canteen_id'), 'name': c.get('name')})
        return out
    except requests.RequestException as e:
        print(f"Error fetching canteen list: {e}")
        return []

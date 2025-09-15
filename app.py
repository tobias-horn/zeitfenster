# app.py

from flask import Flask, render_template, jsonify, request
from canteen_data import get_todays_menu, get_canteen_name, list_canteens  # Import helpers
from weather import get_weather_data
from transport import get_departures_for_station
import datetime
import config

app = Flask(__name__)

@app.route('/')
def index():
    # Show setup wizard if required params are missing
    if not request.args.get('station') or not request.args.get('canteen'):
        return render_template('setup.html', hide_chrome=True)

    canteen_key = request.args.get('canteen')
    canteen_name = get_canteen_name(canteen_key) if canteen_key else None
    canteen_data = get_todays_menu(canteen_key) if canteen_key else None
    show_prices_param = (request.args.get('show_prices') or '1').lower()
    show_prices = show_prices_param not in ('0', 'false', 'no')

    # Get the current time and date in the desired formats
    current_time = datetime.datetime.now().strftime("%H:%M")
    current_date = datetime.datetime.now().strftime("%d.%m.%Y")

    context = dict(
        canteen_data=canteen_data,
        canteen_name=canteen_name,
        time=current_time,
        date=current_date,
        show_prices=show_prices,
        first_monitor_label=config.FIRST_MONITOR_LABEL,
        second_monitor_label=config.SECOND_MONITOR_LABEL,
        first_monitor_code=config.FIRST_MONITOR_CODE,
        second_monitor_code=config.SECOND_MONITOR_CODE,
    )

    if canteen_data:
        return render_template('index.html', **context)
    else:
        error_message = "Could not retrieve today's menu."
        return render_template('index.html', error=error_message, **context)

# New route to serve weather data as JSON
@app.route('/weather_data')
def weather_data():
    weather_data = get_weather_data()
    if weather_data:
        return jsonify(weather_data)
    else:
        return jsonify({'error': 'Could not retrieve weather data'}), 500

# New route to serve MVG transport data as JSON
@app.route('/transport_data')
def transport_data():
    # Parse from URL params
    station = request.args.get('station')
    limit = int(request.args.get('limit', '4'))
    offset = int(request.args.get('offset', '0'))
    types_param = request.args.get('types', '')
    transport_types = [t.strip() for t in types_param.split(',') if t.strip()] or None

    first = get_departures_for_station(
        station or '',
        limit=limit,
        offset=offset,
        transport_types=transport_types,
    )
    return jsonify({'first': first})

# Setup helpers
@app.route('/stations')
def stations():
    try:
        from mvg import MvgApi
    except Exception:
        return jsonify([])
    q = (request.args.get('q') or '').strip().lower()
    try:
        stations = MvgApi.stations()
    except Exception:
        return jsonify([])
    out = []
    for s in stations:
        name = s.get('name', '')
        place = s.get('place', '')
        label = f"{name}, {place}" if place else name
        if not q or q in label.lower():
            out.append({
                'id': s.get('id'),
                'name': name,
                'place': place,
                'label': label,
            })
            if len(out) >= 50:
                break
    return jsonify(out)

@app.route('/canteens')
def canteens():
    return jsonify(list_canteens())

if __name__ == '__main__':
    app.run(debug=True)

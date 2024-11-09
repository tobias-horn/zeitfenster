# app.py

from flask import Flask, render_template, jsonify
from canteen_data import get_todays_menu, get_canteen_name  # Import get_canteen_name
from weather import get_weather_data
import datetime
import config

app = Flask(__name__)

@app.route('/')
def index():
    canteen_data = get_todays_menu()
    canteen_name = get_canteen_name(config.CANTEEN_KEY)  # Get the full canteen name
    
    # Get the current time and date in the desired formats
    current_time = datetime.datetime.now().strftime("%H:%M")
    current_date = datetime.datetime.now().strftime("%d.%m.%Y")
    
    if canteen_data:
        return render_template('index.html', canteen_data=canteen_data, canteen_name=canteen_name, time=current_time, date=current_date, first_monitor_label =config.FIRST_MONITOR_LABEL, second_monitor_label = config.SECOND_MONITOR_LABEL, first_monitor_code = config.FIRST_MONITOR_CODE, second_monitor_code = config.SECOND_MONITOR_CODE)
    else:
        error_message = "Could not retrieve today's menu."
        return render_template('index.html', error=error_message, canteen_name=canteen_name, time=current_time, date=current_date)

# New route to serve weather data as JSON
@app.route('/weather_data')
def weather_data():
    weather_data = get_weather_data()
    if weather_data:
        return jsonify(weather_data)
    else:
        return jsonify({'error': 'Could not retrieve weather data'}), 500

if __name__ == '__main__':
    app.run(debug=True)
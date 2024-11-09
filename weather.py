# weather.py

import requests

def get_weather_data():
    meteo_url = "https://api.open-meteo.com/v1/forecast?latitude=48.183171&longitude=11.611294&current=temperature_2m&daily=temperature_2m_max,temperature_2m_min&timezone=Europe%2FBerlin&forecast_days=1"

    try:
        response = requests.get(meteo_url)
        response.raise_for_status()
        data = response.json()

        # Extract current temperature
        current_temperature = data['current']['temperature_2m']

        # Extract max and min daily temperature
        daily_temperatures = data['daily']
        max_temp = daily_temperatures['temperature_2m_max'][0]
        min_temp = daily_temperatures['temperature_2m_min'][0]

        # Prepare the weather data dictionary
        weather_data = {
            'current_temperature': current_temperature,
            'max_temperature': max_temp,
            'min_temperature': min_temp
        }

        return weather_data

    except requests.RequestException as e:
        print(f"Error fetching weather data: {e}")
        return None
    except KeyError as e:
        print(f"Key error: {e}")
        return None
    
print(requests.get("https://api.open-meteo.com/v1/forecast?latitude=48.183171&longitude=11.611294&current=temperature_2m&daily=temperature_2m_max,temperature_2m_min&timezone=Europe%2FBerlin&forecast_days=1").text)
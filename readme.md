# CampusConnect

![CampusConnect Logo](https://github.com/tobias-horn/campusConnect/blob/main/static/assets/logo.png)

**CampusConnect** is an information display system designed for students, providing real-time updates on weather, canteen menus, and public transportation schedules. Hosted on a Raspberry Pi, CampusConnect serves as a centralized info screen to keep students informed and organized throughout their campus life.

## Table of Contents

- [Features](#features)
- [Demo](#demo)
- [Technologies Used](#technologies-used)
- [Getting Started](#getting-started)
  - [Prerequisites](#prerequisites)
  - [Installation](#installation)
  - [Configuration](#configuration)
- [Usage](#usage)
- [API Integrations](#api-integrations)
  - [TUM-EAT API](#tum-eat-api)
  - [Open-Meteo API](#open-meteo-api)
  - [MVG Public Transport Widget](#mvg-public-transport-widget)
- [Project Structure](#project-structure)

## Features

- **Real-Time Weather Updates**: Displays current temperature, maximum and minimum temperatures using the Open-Meteo API.
- **Canteen Menu**: Shows the daily menu of a selected canteen using the TUM-EAT API.
- **Public Transport Schedule**: Embeds live public transportation schedules from MVG (Münchner Verkehrsgesellschaft) for selected routes.
- **Customizable Interface**: Easily configure which canteen and transportation routes to display.
- **Raspberry Pi Compatible**: Optimized to run smoothly on Raspberry Pi devices.

## Demo

![CampusConnect Screenshot](https://github.com/tobias-horn/campusConnect/blob/main/assets/screenshot.png)

## Technologies Used

- **Python Flask**: Backend framework for handling routes and data processing.
- **HTML/CSS/JavaScript**: Frontend technologies for building the user interface.
- **Open-Meteo API**: Fetches weather data.
- **TUM-EAT API**: Retrieves canteen menu information.
- **MVG Public Transport Widget**: Embeds live public transport schedules.
- **Raspberry Pi**: Hardware platform for hosting CampusConnect.

## Getting Started

Follow these instructions to set up CampusConnect on your Raspberry Pi.

### Prerequisites

- **Raspberry Pi** (any model compatible with Raspberry Pi OS)
- **Python 3.7+**
- **Git**
- **pip** (Python package installer)

### Installation

1. **Clone the Repository**

   ```bash
   git clone https://github.com/yourusername/CampusConnect.git
   cd CampusConnect
   ```

2. **Create a Virtual Environment**

   It's recommended to use a virtual environment to manage dependencies.

   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

3. **Install Dependencies**

   ```bash
   pip install -r requirements.txt
   ```

4. **Set Up Configuration**

   Update `config.py` with your preferred settings.

   **Configuration Parameters:**

   - `CANTEEN_KEY`: Select your preferred canteen key from [TUM-EAT API Canteens](https://github.com/TUM-Dev/eat-api).
   - `FIRST_MONITOR_LABEL` & `SECOND_MONITOR_LABEL`: Labels for your public transport monitors.
   - `FIRST_MONITOR_CODE` & `SECOND_MONITOR_CODE`: Embed codes for MVV departure monitors. Obtain these by configuring your preferred monitors at [MVV Developer Page](https://www.mvv-muenchen.de/fahrplanauskunft/fuer-entwickler/homepage-services/index.html).

5. **Run the Application**

   ```bash
   python app.py
   ```

   The application will start in development mode. For production, consider using a production-ready server like Gunicorn.

6. **Access CampusConnect**

   Open a web browser and navigate to `http://<your-raspberry-pi-ip>:5000/` to view the CampusConnect dashboard.

### Configuration

Ensure that you have properly configured the `config.py` file with the correct canteen key and MVV monitor codes. The canteen key determines which canteen's menu will be displayed, and the MVV monitor codes customize the public transport schedules shown on the screen.

## Usage

Once the application is running, CampusConnect will display:

- **Current Time and Date**: Updates every minute with a blinking colon separator.
- **Weather Information**: Current temperature, maximum, and minimum temperatures in Munich.
- **Canteen Menu**: Daily menu of the selected canteen with dish details and prices.
- **Public Transport Schedule**: Live departure times for the configured routes.

## API Integrations

### TUM-EAT API

CampusConnect integrates with the [TUM-EAT API](https://github.com/TUM-Dev/eat-api) to fetch the daily canteen menu.

- **Endpoint**: `https://tum-dev.github.io/eat-api/`
- **Configuration**: Set the `CANTEEN_KEY` in `config.py` to your preferred canteen.

### Open-Meteo API

Weather data is fetched using the [Open-Meteo API](https://open-meteo.com/).

- **Endpoint**: `https://api.open-meteo.com/v1/forecast`
- **Parameters**:
  - `latitude`: 48.183171
  - `longitude`: 11.611294
  - `current_weather`: temperature at 2 meters
  - `daily`: maximum and minimum temperatures
  - `timezone`: Europe/Berlin
  - `forecast_days`: 1

### MVG Public Transport Widget

Public transportation schedules are embedded using a custom MVV (Münchner Verkehrsgesellschaft) widget.

- **Configuration**:
  1. Visit the [MVV Developer Page](https://www.mvv-muenchen.de/fahrplanauskunft/fuer-entwickler/homepage-services/index.html).
  2. Configure your preferred monitor settings.
  3. Copy the generated `<div></div>` element and paste it into the `FIRST_MONITOR_CODE` and `SECOND_MONITOR_CODE` fields in `config.py`.

## Project Structure

```
CampusConnect/
├── app.py
├── canteen_data.py
├── config.py
├── requirements.txt
├── weather.py
├── templates/
│   ├── base.html
│   ├── index.html
│   ├── canteen.html
│   └── transport.html
└── static/
    ├── styles.css
    ├── script.js
    └── assets/
        ├── logo.png
        └── screenshot.png

```

- **app.py**: Main Flask application file handling routes and rendering templates.
- **canteen_data.py**: Handles fetching and processing canteen menu data from the TUM-EAT API.
- **weather.py**: Fetches and processes weather data from the Open-Meteo API.
- **config.py**: Configuration file containing canteen keys and MVV monitor codes.
- **templates/**: Contains HTML templates for the frontend.
- **static/**: Contains static files like CSS and JavaScript.
- **assets/**: Stores images and other media assets.

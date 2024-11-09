// static/script.js

// Function to update the current time with a blinking colon
function updateTime() {
    const timeElement = document.getElementById('current-time');
    if (timeElement) {
        const now = new Date();
        const [hours, minutes] = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false }).split(':');
        const dateString = now.toLocaleDateString('de-DE');
        timeElement.innerHTML = `${hours}<span class="blinking-colon">:</span>${minutes} | ${dateString}`;
    }
}

// Initial call to align the time with the next full minute
function startTimerOnTheDot() {
    updateTime(); // Initial update
    const now = new Date();
    const msUntilNextMinute = (60 - now.getSeconds()) * 1000;

    // Delay the start of the interval to the next full minute
    setTimeout(() => {
        updateTime(); // Update at the next full minute
        setInterval(updateTime, 60000); // Repeat every 60 seconds
    }, msUntilNextMinute);
}

// Start the timer on the next full minute
startTimerOnTheDot();

// Function to fetch and update weather data
function updateWeather() {
    fetch('/weather_data')
        .then(response => response.json())
        .then(data => {
            if (!data.error) {
                document.getElementById('current-temperature').textContent = `${data.current_temperature}°C`;
                document.getElementById('max-temperature').textContent = `H: ${data.max_temperature} °C`;
                document.getElementById('min-temperature').textContent = `L: ${data.min_temperature} °C`;
            } else {
                console.error('Error fetching weather data:', data.error);
                // Optionally, display an error message on the page
            }
        })
        .catch(error => console.error('Error:', error));
}

// Update weather immediately and then every 15 minutes
updateWeather();
setInterval(updateWeather, 900000); // 900000 milliseconds = 15 minutes

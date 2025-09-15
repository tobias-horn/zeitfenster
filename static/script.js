// static/script.js

// Function to update the current time (no animation for e-ink)
function updateTime() {
    const timeElement = document.getElementById('current-time');
    if (timeElement) {
        const now = new Date();
        const [hours, minutes] = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false }).split(':');
        const dateString = now.toLocaleDateString('de-DE');
        timeElement.textContent = `${hours}:${minutes} | ${dateString}`;
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
                const curEl = document.getElementById('current-temperature');
                if (curEl) curEl.textContent = `${data.current_temperature}°C`;
                const maxEl = document.getElementById('max-temperature');
                if (maxEl) maxEl.textContent = `H: ${data.max_temperature} °C`;
                const minEl = document.getElementById('min-temperature');
                if (minEl) minEl.textContent = `L: ${data.min_temperature} °C`;

                // UV index and sunrise/sunset
                const uvEl = document.getElementById('uv-index');
                if (uvEl && data.uv_index_max !== undefined) {
                    uvEl.textContent = `UV ${data.uv_day_label}: ${data.uv_index_max}`;
                }
                const sunriseEl = document.getElementById('sunrise');
                const sunsetEl = document.getElementById('sunset');
                if (sunriseEl && data.sunrise) {
                    const t = new Date(data.sunrise);
                    sunriseEl.textContent = `${t.toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'})}`;
                }
                if (sunsetEl && data.sunset) {
                    const t = new Date(data.sunset);
                    sunsetEl.textContent = `${t.toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'})}`;
                }
            } else {
                console.error('Error fetching weather data:', data.error);
            }
        })
        .catch(error => console.error('Error:', error));
}

// Update weather immediately and then every 15 minutes
updateWeather();
setInterval(updateWeather, 900000); // 900000 milliseconds = 15 minutes

// Function to fetch and update MVG transport data
function updateTransport() {
    const qs = window.location.search || '';
    fetch('/transport_data' + qs)
        .then(response => response.json())
        .then(data => {
            const firstBody = document.getElementById('first-monitor-body');
            let hasData = false;

            function renderRows(list, tbody) {
                if (!tbody) return false;
                tbody.innerHTML = '';
                if (list && list.length) {
                    hasData = true;
                    for (const dep of list) {
                        const tr = document.createElement('tr');
                        tr.innerHTML = `<td>${dep.line}</td><td>${dep.destination}</td><td>${dep.minutes} min</td>`;
                        tbody.appendChild(tr);
                    }
                } else {
                    const tr = document.createElement('tr');
                    tr.innerHTML = '<td colspan="3"><em>Keine Daten</em></td>';
                    tbody.appendChild(tr);
                }
            }

            renderRows(data.first, firstBody);

            // No legacy embed fallback
        })
        .catch(err => {
            console.error('Transport fetch failed', err);
        });
}

// Initial fetch and periodic refresh (e-ink friendly: every 60s)
updateTransport();
setInterval(updateTransport, 60000);

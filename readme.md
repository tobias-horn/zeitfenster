# ZEITFENSTER v2

A compact Flask dashboard (time, weather, canteen, transport) with a Kindle‑friendly PNG snapshot endpoint. This README summarizes all current behavior and lessons learned (Playwright on Heroku, scaling, rotation, setup flow, etc.).

## Quick Start

- Python 3.10+
- No Node required

Local

```bash
git clone <repo>
cd <repo>
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium
python app.py  # http://127.0.0.1:5000
```

Heroku

- Stack: heroku-24
- Buildpacks (order):
  1. heroku-community/apt
  2. heroku/python
- `Procfile` (already in repo):

```
web: sh -c "python -m playwright install chromium && gunicorn app:app"
```

The `Aptfile` contains the Chromium system libraries needed by Playwright.

## What You Get

- Setup wizard (signup) to pick station, types, limit, offset, and canteen.
- Dashboard tiles:
  - Header: “ZEITFENSTER” + “Version: v2” and current time/date (Europe/Berlin)
  - Weather (Munich, Open‑Meteo): current, H/L, UV, sunrise/sunset
  - Transport (MVG): live departures with filtering
  - Canteen (TUM‑Dev Eat API): daily menu; shows next day after 14:00 if needed
- PNG snapshot endpoint for Kindles and e‑ink displays.

## Key Files

```
app.py                # Flask routes + /image-push.png
canteen_data.py       # TUM‑Dev Eat API helpers
weather.py            # Open‑Meteo integration
transport.py          # MVG departures (mvg package)
templates/            # base.html, index.html, tiles, setup.html
static/styles.css     # Styles (Inter font)
static/script.js      # Client updates for weather/transport
Procfile              # Heroku boot
Aptfile               # Chromium libs for Playwright
```

## Endpoints

- `/` — dashboard
  - Query params: `station`, `types` (`UBAHN,SBAHN,BUS,TRAM`), `limit` (int), `offset` (int minutes), `canteen`, `show_prices` (`1|0`)
  - If `station` or `canteen` missing, shows the setup wizard

- `/image-push.png` — Kindle snapshot
  - Forwards the dashboard params above
  - Additional:
    - `orientation`: `portrait` (600×800) or `landscape` — for landscape, content is rotated 90° so the delivered PNG is still portrait 600×800
    - `scale` (alias `zoom`): 0.5–1.5 — renders at a scaled viewport and resamples to exact size
    - `cache`: `0` to bypass the 30s in‑memory cache
    - `token`: required if `IMAGE_PUSH_TOKEN` env var is set
  - Response headers: `X-Viewport`, `X-Scale`, `X-Render-Viewport`, `X-URL`

- `/weather_data` — JSON for the weather tile
- `/transport_data` — JSON for departures (accepts `station,types,limit,offset`)
- `/stations` — station search results (typed)
- `/canteens` — canteen list

## Snapshot Behavior (Kindle)

- Exact size: delivered PNG is always portrait 600×800
- For `orientation=landscape`: the content is rotated to fit portrait output
- Grayscale: 8‑bit (no alpha, non‑interlaced PNG)
- Emoji: stripped from text nodes during capture
- Data readiness before capture:
  - DOM and grid present; web fonts ready (Inter)
  - Weather shows a numeric value
  - One successful `/transport_data` response
  - The “Wird geladen …” placeholder in the table is gone (even if 0 departures)
- Scaling: `scale` changes the render viewport; downsampled to exact output

Tip: For very small scale values the render viewport becomes large; the implementation clamps to 0.5–1.5 for safety on Heroku. Use `&cache=0` when iterating.

## Setup Wizard (Signup)

- Step 1 — Welcome
- Step 2 — Transportation
  - Full‑width station search
  - Help text: “Please select your closest public transportation station.”
  - Departure limit help: “Number of public transport options to be displayed.”
  - Offset minutes help: “Shifts departures by your walking time to the station.”
- Step 3 — Canteen
  - Help text: “Please select your preferred canteen.”

## Data Sources

- Weather: Open‑Meteo (Munich, Europe/Berlin)
- Canteen: TUM‑Dev Eat API (falls forward up to 7 days; after 14:00 shows next day)
- Transport: MVG via `mvg` Python package
  - Types filter: `UBAHN, SBAHN, BUS, TRAM`

## Deployment Notes & Troubleshooting

- Local: always run `python -m playwright install chromium` after `pip install -r requirements.txt`
- Heroku: ensure stack heroku‑24 and buildpacks `heroku-community/apt` then `heroku/python`
- H12 timeouts: the snapshot route uses bounded waits; keep `limit` reasonable and avoid extremely small scales
- Missing emojis: emojis are intentionally stripped in snapshots for e‑ink clarity

## Optional E‑Ink Tuning

For even cleaner e‑ink output you can quantize to ~16 gray levels with dithering (not enabled by default). You can add this in the Pillow post‑process or pre‑process with ImageMagick:

```
convert input.png -resize 600x800\! -colorspace Gray -dither FloydSteinberg -colors 16 -depth 8 PNG8:output.png
```

## Security

- Set `IMAGE_PUSH_TOKEN` to require `?token=...` on `/image-push.png`.

## License

No license is declared in this repository.

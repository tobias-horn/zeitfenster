# app.py

from flask import Flask, render_template, jsonify, request, make_response, abort, url_for
from canteen_data import get_todays_menu, get_canteen_name, list_canteens  # Import helpers
from weather import get_weather_data
from transport import get_departures_for_station
import datetime
import os
from urllib.parse import urlencode

# Optional: Pillow for fallback PNG generation if Playwright fails
try:
    from PIL import Image, ImageDraw, ImageFont
except Exception:
    Image = None
    ImageDraw = None
    ImageFont = None

# Optional: Playwright for server-side PNG snapshots
try:
    from playwright.sync_api import sync_playwright
except Exception:  # Defer import errors until the snapshot route is used
    sync_playwright = None

# Timezone support (kept available if needed later)
try:
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover
    ZoneInfo = None  # type: ignore

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


# -------- Kindle image-push endpoint --------

# Simple in-memory cache to avoid relaunching Chromium too often
_IMG_CACHE = {
    'key': None,
    'ts': 0,
    'img': None,
}

KINDLE_LANDSCAPE = (800, 600)
KINDLE_PORTRAIT = (600, 800)


def _render_dashboard_png(url: str, width: int, height: int) -> bytes:
    if sync_playwright is None:
        raise RuntimeError('Playwright is not installed. Add "playwright" to requirements and install browsers.')
    with sync_playwright() as p:
        # Launch Chromium; rely on Playwright-managed browser
        browser = p.chromium.launch(args=["--no-sandbox", "--disable-setuid-sandbox"], headless=True)
        context = browser.new_context(
            viewport={"width": width, "height": height},
            device_scale_factor=2,
            timezone_id="Europe/Berlin",
            locale="de-DE",
        )
        page = context.new_page()
        page.goto(url, wait_until="networkidle", timeout=30000)
        # Force zero margins and exact canvas sizing in the capture context to avoid empty borders
        page.add_style_tag(content=f"""
            html, body {{
                margin: 0 !important;
                padding: 0 !important;
                width: {width}px !important;
                height: {height}px !important;
                overflow: hidden !important;
                background: #fff !important;
                color: #000 !important;
            }}
            main {{ width: 100% !important; height: 100% !important; }}
        """)
        # Wait for fonts and async layout to settle
        try:
            page.evaluate("return (document.fonts ? document.fonts.ready : Promise.resolve())")
        except Exception:
            pass
        page.wait_for_timeout(300)
        # Ensure white background for any transparent areas
        page.evaluate("document.documentElement.style.background='white'; document.body.style.background='white';")
        png_bytes = page.screenshot(type="png", full_page=False)
        # Downscale to exact canvas size if DPR > 1 to keep output at {width}x{height}
        if Image is not None:
            try:
                from io import BytesIO
                im = Image.open(BytesIO(png_bytes))
                if im.size != (width, height):
                    im = im.resize((width, height), Image.LANCZOS)
                    out = BytesIO()
                    im.save(out, format='PNG')
                    png_bytes = out.getvalue()
            except Exception:
                pass
        context.close()
        browser.close()
        return png_bytes


def _render_error_png(width: int, height: int, message: str) -> bytes:
    if Image is None or ImageDraw is None:
        # As last resort, return plain bytes to avoid 500 HTML for Kindle
        return b""
    img = Image.new('RGB', (width, height), color='white')
    draw = ImageDraw.Draw(img)
    # Basic text layout
    title = "Service Unavailable"
    body = (message or "Rendering failed").strip()
    try:
        font_title = ImageFont.load_default()
        font_body = ImageFont.load_default()
    except Exception:
        font_title = font_body = None
    # Center text roughly
    y = 40
    draw.text((20, y), title, fill='black', font=font_title)
    y += 30
    # Wrap body text
    max_width = width - 40
    words = body.split()
    line = ""
    for w in words:
        test = (line + " " + w).strip()
        # crude wrap heuristic
        if len(test) > 48:
            draw.text((20, y), line, fill='black', font=font_body)
            y += 18
            line = w
        else:
            line = test
    if line:
        draw.text((20, y), line, fill='black', font=font_body)
    from io import BytesIO
    buf = BytesIO()
    img.save(buf, format='PNG')
    return buf.getvalue()


@app.get('/image-push.png')
def image_push():
    # Optional token protection
    token_required = os.getenv('IMAGE_PUSH_TOKEN')
    if token_required:
        if request.args.get('token') != token_required:
            abort(403)

    # Orientation and Kindle size
    orientation = (request.args.get('orientation') or 'landscape').strip().lower()
    if orientation == 'potrait':
        orientation = 'portrait'
    if orientation not in ('landscape', 'portrait'):
        orientation = 'landscape'
    width, height = KINDLE_LANDSCAPE if orientation == 'landscape' else KINDLE_PORTRAIT

    # Forward key params for dashboard rendering
    forward_params = {
        'station': request.args.get('station', ''),
        'canteen': request.args.get('canteen', ''),
        'show_prices': request.args.get('show_prices', '1'),
        'types': request.args.get('types', ''),
        'limit': request.args.get('limit', '4'),
        'offset': request.args.get('offset', '0'),
    }
    # Build absolute dashboard URL (screenshot the main page)
    dash_url = url_for('index', _external=True) + '?' + urlencode(forward_params)

    # Cache key per URL and viewport
    cache_key = f"{dash_url}|{width}x{height}"
    now_ts = int(datetime.datetime.now().timestamp())
    if _IMG_CACHE['key'] == cache_key and _IMG_CACHE['img'] is not None and (now_ts - _IMG_CACHE['ts']) < 30:
        img = _IMG_CACHE['img']
    else:
        try:
            img = _render_dashboard_png(dash_url, width, height)
        except Exception as e:
            # Return a PNG with the error text so Kindle shows something
            img = _render_error_png(width, height, str(e))
        _IMG_CACHE.update({'key': cache_key, 'ts': now_ts, 'img': img})

    resp = make_response(img)
    resp.headers['Content-Type'] = 'image/png'
    resp.headers['Cache-Control'] = 'no-store, max-age=0'
    resp.headers['X-Rendered-At'] = str(now_ts)
    return resp

if __name__ == '__main__':
    app.run(debug=True)

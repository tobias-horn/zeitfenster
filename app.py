# app.py

from flask import Flask, render_template, jsonify, request, make_response, abort, url_for
from canteen_data import get_todays_menu, get_canteen_name, list_canteens  # Import helpers
from weather import get_weather_data
from transport import get_departures_for_station
import datetime
import os
from urllib.parse import urlencode
import math

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


def _render_dashboard_png(url: str, width: int, height: int, *, zoom: float | None = None) -> bytes:
    if sync_playwright is None:
        raise RuntimeError('Playwright is not installed. Add "playwright" to requirements and install browsers.')
    # Compute render viewport from desired scale (zoom). We render larger for zoom<1
    # and smaller for zoom>1, then resize back to the exact target size.
    eff_scale = 1.0
    try:
        if zoom is not None:
            eff_scale = float(zoom)
    except Exception:
        eff_scale = 1.0
    # Clamp to avoid massive viewports that can crash in headless environments
    if eff_scale < 0.5:
        eff_scale = 0.5
    if eff_scale > 1.5:
        eff_scale = 1.5
    render_w = max(1, int(round(width / eff_scale)))
    render_h = max(1, int(round(height / eff_scale)))
    # Keep memory bounded by reducing DPR for very large render viewports
    dsf = 2
    if render_w * render_h > 1600 * 1200:
        dsf = 1

    with sync_playwright() as p:
        # Launch Chromium; rely on Playwright-managed browser
        browser = p.chromium.launch(args=["--no-sandbox", "--disable-setuid-sandbox"], headless=True)
        context = browser.new_context(
            viewport={"width": render_w, "height": render_h},
            device_scale_factor=dsf,
            timezone_id="Europe/Berlin",
            locale="de-DE",
        )
        page = context.new_page()
        try:
            # Use a conservative wait to avoid H12 timeouts; the page loads its own data via JS
            page.goto(url, wait_until="domcontentloaded", timeout=10000)
            # Wait for the dashboard shell to be present (but don't block for long)
            try:
                page.wait_for_selector('.dashboard-grid', timeout=3000)
            except Exception:
                pass
            # Ensure web fonts are loaded for consistent typography
            try:
                page.evaluate("return (document.fonts ? document.fonts.ready : Promise.resolve())")
            except Exception:
                pass
            # Wait for weather + transport data to populate (bounded)
            try:
                page.wait_for_function(
                    """
                    () => {
                      const w = document.getElementById('current-temperature');
                      const weatherOK = !!(w && /\d/.test((w.textContent||'').trim()));
                      const b = document.getElementById('first-monitor-body');
                      const transportOK = !!(b && b.querySelectorAll('tr').length && !b.textContent.includes('Wird geladen'));
                      return weatherOK && transportOK;
                    }
                    """,
                    timeout=7000,
                )
            except Exception:
                pass
            # Apply scale so the content visibly shrinks/expands, while keeping borders about the same.
            if zoom is not None:
                try:
                    z = float(zoom)
                    if 0.1 <= z <= 2.0 and abs(z - 1.0) > 1e-6:
                        page.evaluate(
                            """
                            (function(z){
                              var grid = document.querySelector('.dashboard-grid');
                              var root = grid || document.body;
                              // Set CSS var for border compensation
                              document.documentElement.style.setProperty('--ccScale', String(z));
                              // Inject overrides for border widths so they stay visually consistent
                              if (!document.getElementById('cc-scale-style')) {
                                var s = document.createElement('style');
                                s.id = 'cc-scale-style';
                                s.textContent = `
                                  .tile { border-width: calc(2px / var(--ccScale, 1)); }
                                  .dish-box { border-width: calc(1px / var(--ccScale, 1)); }
                                  .departures thead tr { border-bottom-width: calc(2px / var(--ccScale, 1)); }
                                  .departures tbody tr { border-top-width: calc(1px / var(--ccScale, 1)); }
                                `;
                                document.head.appendChild(s);
                              }
                              // Prefer CSS zoom; fallback to transform
                              root.style.transformOrigin = 'top left';
                              root.style.transform = '';
                              root.style.zoom = '';
                              try { root.style.zoom = String(z); } catch(e) {}
                              if (!root.style.zoom) {
                                root.style.transform = 'scale(' + z + ')';
                              }
                            })(arguments[0]);
                            """,
                            z,
                        )
                        # allow a short repaint after scaling
                        page.wait_for_timeout(100)
                except Exception:
                    pass
            # Remove emojis from text nodes for the image route only
            try:
                page.evaluate(
                    """
                    (function(){
                      var emojiRe;
                      try { emojiRe = new RegExp('[\\\p{Extended_Pictographic}\\uFE0F\\u200D]','gu'); }
                      catch(e) { emojiRe = /[\u231A-\u231B\u23E9-\u23EC\u23F0\u23F3\u25FD-\u25FE\u2600-\u27BF\u2934-\u2935\u2B05-\u2B07\u3030\u303D\u3297\u3299\ud83c[\ud000-\udfff]|\ud83d[\ud000-\udfff]|\ud83e[\ud000-\udfff]|\ufe0f|\u200d/g; }
                      var walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
                      var nodes = [];
                      var n;
                      while ((n = walker.nextNode())) { nodes.push(n); }
                      nodes.forEach(function(t){
                        if (emojiRe.test(t.nodeValue)) {
                          t.nodeValue = t.nodeValue.replace(emojiRe, '').replace(/\s{2,}/g,' ').trim();
                        }
                      });
                      // Hide empty spans that only held emojis
                      Array.from(document.querySelectorAll('span')).forEach(function(el){
                        if (!el.textContent || !el.textContent.trim()) { el.style.display = 'none'; }
                      });
                    })();
                    """
                )
            except Exception:
                pass
            # Minimal settle
            page.wait_for_timeout(250)
            # Ensure white background for any transparent areas
            page.evaluate("document.documentElement.style.background='white'; document.body.style.background='white';")
            png_bytes = page.screenshot(type="png", full_page=False)
        finally:
            # Always close to avoid TargetClosedError leaks
            try:
                context.close()
            except Exception:
                pass
            try:
                browser.close()
            except Exception:
                pass

        # Post-process with Pillow: ensure exact size and 8-bit grayscale, non-interlaced
        if Image is not None:
            try:
                from io import BytesIO
                im = Image.open(BytesIO(png_bytes))
                # Resize to exact target size regardless of render viewport
                if im.size != (width, height):
                    im = im.resize((width, height), Image.LANCZOS)
                # Convert to 8-bit grayscale (Kindle-friendly: color type 0, no alpha)
                if im.mode != 'L':
                    im = im.convert('L')
                out = BytesIO()
                # Save non-interlaced PNG by default (no alpha, no exotic chunks)
                im.save(out, format='PNG', optimize=True)
                png_bytes = out.getvalue()
            except Exception:
                # If Pillow fails, fall back to original screenshot
                pass

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
    # Optional scale control: support both ?scale= and ?zoom=
    zoom_param = request.args.get('scale') or request.args.get('zoom')
    zoom = None
    if zoom_param:
        try:
            zoom = float(zoom_param)
        except Exception:
            zoom = None

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

    # Cache key per URL, viewport, and zoom
    cache_key = f"{dash_url}|{width}x{height}|scale={zoom if zoom is not None else 'none'}"
    now_ts = int(datetime.datetime.now().timestamp())
    # Optional cache bypass via ?cache=0
    cache_param = (request.args.get('cache') or '').lower()
    bypass_cache = cache_param in ('0', 'false', 'no')
    if (not bypass_cache) and _IMG_CACHE['key'] == cache_key and _IMG_CACHE['img'] is not None and (now_ts - _IMG_CACHE['ts']) < 30:
        img = _IMG_CACHE['img']
    else:
        try:
            img = _render_dashboard_png(dash_url, width, height, zoom=zoom)
        except Exception as e:
            # Return a PNG with the error text so Kindle shows something
            img = _render_error_png(width, height, str(e))
        _IMG_CACHE.update({'key': cache_key, 'ts': now_ts, 'img': img})

    resp = make_response(img)
    resp.headers['Content-Type'] = 'image/png'
    resp.headers['Cache-Control'] = 'no-store, max-age=0'
    resp.headers['X-Rendered-At'] = str(now_ts)
    resp.headers['X-Viewport'] = f"{width}x{height}"
    resp.headers['X-Scale'] = str(zoom) if zoom is not None else 'none'
    resp.headers['X-URL'] = dash_url
    # Report internal render viewport used for scaling
    try:
        eff_scale = float(zoom) if zoom is not None else 1.0
    except Exception:
        eff_scale = 1.0
    if eff_scale < 0.5:
        eff_scale = 0.5
    if eff_scale > 1.5:
        eff_scale = 1.5
    render_w = max(1, int(round(width / eff_scale)))
    render_h = max(1, int(round(height / eff_scale)))
    resp.headers['X-Render-Viewport'] = f"{render_w}x{render_h}"
    return resp

if __name__ == '__main__':
    app.run(debug=True)

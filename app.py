# app.py

from flask import Flask, render_template, jsonify, request, make_response, abort, url_for
from canteen_data import get_todays_menu, get_canteen_name, list_canteens  # Import helpers
from weather import get_weather_data
from transport import get_departures_for_station
import datetime
import os
from urllib.parse import urlencode
import math
import threading
import time

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

_PLAYWRIGHT_LOCK = threading.Lock()
_PLAYWRIGHT_INSTANCE = None
_BROWSER_INSTANCE = None
_WARM_LOCK = threading.Lock()
_WARM_TRIGGERED = False
_BROWSER_KEEPALIVE_INTERVAL = 240  # seconds
_BROWSER_LAST_PING = 0.0


def _reset_browser():
    global _PLAYWRIGHT_INSTANCE, _BROWSER_INSTANCE, _BROWSER_LAST_PING
    try:
        if _BROWSER_INSTANCE is not None:
            _BROWSER_INSTANCE.close()
    except Exception:
        pass
    _BROWSER_INSTANCE = None
    try:
        if _PLAYWRIGHT_INSTANCE is not None:
            _PLAYWRIGHT_INSTANCE.stop()
    except Exception:
        pass
    _PLAYWRIGHT_INSTANCE = None
    _BROWSER_LAST_PING = 0.0


def _get_browser():
    global _PLAYWRIGHT_INSTANCE, _BROWSER_INSTANCE
    if sync_playwright is None:
        raise RuntimeError('Playwright is not installed. Add "playwright" to requirements and install browsers.')
    if _BROWSER_INSTANCE is not None:
        return _BROWSER_INSTANCE
    with _PLAYWRIGHT_LOCK:
        if _BROWSER_INSTANCE is not None:
            return _BROWSER_INSTANCE
        try:
            _PLAYWRIGHT_INSTANCE = sync_playwright().start()
            _BROWSER_INSTANCE = _PLAYWRIGHT_INSTANCE.chromium.launch(
                args=["--no-sandbox", "--disable-setuid-sandbox"],
                headless=True,
            )
        except Exception:
            _reset_browser()
            raise
    return _BROWSER_INSTANCE


def _ensure_browser_alive(browser):
    global _BROWSER_LAST_PING
    now = time.time()
    if (now - _BROWSER_LAST_PING) < _BROWSER_KEEPALIVE_INTERVAL:
        return
    ctx = None
    try:
        ctx = browser.new_context()
        _BROWSER_LAST_PING = now
    except BaseException as exc:
        _reset_browser()
        print(f"Browser keepalive failed: {exc}")
        raise
    finally:
        if ctx is not None:
            try:
                ctx.close()
            except Exception:
                pass


def _render_dashboard_png(
    url: str,
    width: int,
    height: int,
    *,
    zoom: float | None = None,
    expected_rows: int | None = None,
) -> bytes:
    if sync_playwright is None:
        raise RuntimeError('Playwright is not installed. Add "playwright" to requirements and install browsers.')
    render_start = time.time()

    def _check_budget():
        if (time.time() - render_start) > 25:
            raise TimeoutError("Screenshot render exceeded 25s budget")

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

    browser = _get_browser()
    context = None
    try:
        try:
            _ensure_browser_alive(browser)
        except Exception:
            _reset_browser()
            browser = _get_browser()
            _ensure_browser_alive(browser)
        try:
            global _BROWSER_LAST_PING
            context = browser.new_context(
                viewport={"width": render_w, "height": render_h},
                device_scale_factor=dsf,
                timezone_id="Europe/Berlin",
                locale="de-DE",
            )
            _BROWSER_LAST_PING = time.time()
        except Exception:
            _reset_browser()
            browser = _get_browser()
            _ensure_browser_alive(browser)
            context = browser.new_context(
                viewport={"width": render_w, "height": render_h},
                device_scale_factor=dsf,
                timezone_id="Europe/Berlin",
                locale="de-DE",
            )
            _BROWSER_LAST_PING = time.time()
        _check_budget()
        page = context.new_page()
        try:
            # Use a conservative wait to avoid H12 timeouts; the page loads its own data via JS
            page.goto(url, wait_until="domcontentloaded", timeout=20000)
            _check_budget()
            # Wait for the dashboard shell to be present (but don't block for long)
            try:
                page.wait_for_selector('.dashboard-grid', timeout=3000)
            except Exception:
                pass
            # Screenshot-only CSS tweaks (tighter price spacing/size for canteen items)
            try:
                page.add_style_tag(content='''.price-line{font-size:0.80rem !important;margin-top:1px !important;} .dish-title{margin-top:2px !important;margin-bottom:1px !important;}''')
            except Exception:
                pass
            try:
                page.add_style_tag(content='html{font-size:22px !important;} body{font-size:22px !important;}')
            except Exception:
                pass
            # Auto-fit height: if no explicit scale is provided, binary-search a viewport scale
            # so that the measured content height matches the target height within 1px.
            if zoom is None:
                try:
                    target_h = float(height)

                    def measure():
                        return page.evaluate(
                            "(() => {\n"
                            "  const root = document.querySelector('.dashboard-grid') || document.body;\n"
                            "  const r = root.getBoundingClientRect();\n"
                            "  const docH = Math.max(document.documentElement.scrollHeight||0, document.body.scrollHeight||0);\n"
                            "  const rootH = Math.max(r.height, root.scrollHeight||0);\n"
                            "  return Math.ceil(Math.max(docH, rootH));\n"
                            "})()"
                        )

                    # Binary search scale in [0.5, 1.5]
                    lo, hi = 0.5, 1.5
                    best_s, best_err = 1.0, 10**9
                    for _ in range(8):
                        s = (lo + hi) / 2.0
                        vw = max(1, int(math.ceil(width / s)))
                        vh = max(1, int(math.ceil(height / s)))
                        page.set_viewport_size({"width": vw, "height": vh})
                        page.wait_for_timeout(120)
                        H = measure() or 0
                        err = abs(H - target_h)
                        if err < best_err:
                            best_err, best_s = err, s
                        # Decide which half to keep: if content taller than target, shrink more (decrease s)
                        if H > target_h:
                            hi = s
                        else:
                            lo = s
                        if err <= 1:
                            break
                    # Ensure viewport reflects best found scale
                    final_vw = max(1, int(math.ceil(width / best_s)))
                    final_vh = max(1, int(math.ceil(height / best_s)))
                    page.set_viewport_size({"width": final_vw, "height": final_vh})
                    page.wait_for_timeout(100)
                except Exception:
                    pass
            _check_budget()
            # Ensure web fonts are loaded for consistent typography
            try:
                page.evaluate("return (document.fonts ? document.fonts.ready : Promise.resolve())")
            except Exception:
                pass
            _check_budget()
            # Wait for weather + transport data to populate (bounded)
            try:
                # Weather: wait until current temperature shows a digit
                page.wait_for_function(
                    "() => { const w = document.getElementById('current-temperature'); return !!(w && /\\d/.test((w.textContent||'').trim())); }",
                    timeout=5000,
                )
            except Exception:
                pass
            try:
                # Transport: wait for the fetch to complete at least once
                page.wait_for_response(lambda r: ('/transport_data' in r.url) and r.ok, timeout=6000)
            except Exception:
                pass
            try:
                # Finally: consider transport "loaded" as soon as the loading placeholder disappears,
                # regardless of how many rows the API returned (it may legitimately be zero).
                page.wait_for_function(
                    """
                    () => {
                      const b = document.getElementById('first-monitor-body');
                      if (!b) return false;
                      const txt = (b.textContent || '');
                      return !/Wird geladen/i.test(txt);
                    }
                    """,
                    timeout=3000,
                )
            except Exception:
                pass
            _check_budget()
            # Compute and apply precise visual scale using browser zoom/transform (no app code changes)
            try:
                # Decide desired scale: explicit override or auto-fit to target height
                if zoom is not None:
                    z = float(zoom)
                    z = max(0.4, min(1.6, z))
                else:
                    # Auto: measure current content height and compute exact scale so height == target
                    H0 = page.evaluate("(() => { const el = document.querySelector('.dashboard-grid') || document.body; const r = el.getBoundingClientRect(); const sh = Math.max(el.scrollHeight||0, document.documentElement.scrollHeight||0, document.body.scrollHeight||0); return Math.ceil(Math.max(r.height, sh)); })()") or 0
                    z = 1.0
                    if H0 > 0:
                        z = max(0.4, min(1.6, float(height) / float(H0)))

                # Apply scale with CSS zoom in percent for Chrome; also set transform fallback and size compensation
                for _ in range(2):  # refine once after reflow
                    page.evaluate(
                        """
                        (function(z){
                          var grid = document.querySelector('.dashboard-grid');
                          var root = grid || document.body;
                          // Border compensation remains subtle; avoid heavy overrides
                          // Prefer CSS zoom as a percentage (Chrome). Also set transform as fallback.
                          document.documentElement.style.zoom = (z*100) + '%';
                          document.body.style.zoom = (z*100) + '%';
                          root.style.transformOrigin = 'top left';
                          root.style.transform = 'scale(' + z + ')';
                          // Expand layout area so the scaled content still fills the viewport
                          var W = window.innerWidth, H = window.innerHeight;
                          root.style.width = Math.ceil(W / z) + 'px';
                          root.style.height = Math.ceil(H / z) + 'px';
                        })(arguments[0]);
                        """,
                        z,
                    )
                    page.wait_for_timeout(120)
                    # Refine scale once using the new measured height
                    H1 = page.evaluate("(() => { const el = document.querySelector('.dashboard-grid') || document.body; const r = el.getBoundingClientRect(); const sh = Math.max(el.scrollHeight||0, document.documentElement.scrollHeight||0, document.body.scrollHeight||0); return Math.ceil(Math.max(r.height, sh)); })()") or 0
                    if H1 > 0:
                        z2 = max(0.4, min(1.6, z * (float(height)/float(H1))))
                        if abs(z2 - z) < 0.01:
                            break
                        z = z2
            except Exception:
                pass
            _check_budget()
            # Remove emojis from text nodes for the image route only
            try:
                page.evaluate(
                    """
                    (function(){
                      var emojiRe;
                      try { emojiRe = new RegExp('[\\\\p{Extended_Pictographic}\\uFE0F\\u200D]','gu'); }
                      catch(e) { emojiRe = /[\u231A-\u231B\u23E9-\u23EC\u23F0\u23F3\u25FD-\u25FE\u2600-\u27BF\u2934-\u2935\u2B05-\u2B07\u3030\u303D\u3297\u3299\ud83c[\ud000-\udfff]|\ud83d[\ud000-\udfff]|\ud83e[\ud000-\udfff]|\ufe0f|\u200d/g; }
                      var walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
                      var nodes = [];
                      var n;
                      while ((n = walker.nextNode())) { nodes.push(n); }
                      nodes.forEach(function(t){
                        if (emojiRe.test(t.nodeValue)) {
                          t.nodeValue = t.nodeValue.replace(emojiRe, '').replace(/\\s{2,}/g,' ').trim();
                        }
                      });
                      // Hide spans that became empty AND do not contain any child elements (keep icon-only spans)
                      Array.from(document.querySelectorAll('span')).forEach(function(el){
                        var hasText = !!(el.textContent && el.textContent.trim());
                        var hasChildren = el.children && el.children.length > 0;
                        if (!hasText && !hasChildren) { el.style.display = 'none'; }
                      });
                    })();
                    """
                )
            except Exception:
                pass
            _check_budget()
            # Ensure weather icons (UV/sunrise/sunset) are loaded before capture
            try:
                page.wait_for_function(
                    "(() => { const imgs = Array.from(document.querySelectorAll('.weather-tile img.icon')); if (!imgs.length) return true; return imgs.every(img => img.complete && img.naturalWidth > 0); })()",
                    timeout=3000,
                )
            except Exception:
                pass
            _check_budget()
            # Minimal settle
            page.wait_for_timeout(250)
            # Ensure white background for any transparent areas
            page.evaluate("document.documentElement.style.background='white'; document.body.style.background='white';")
            _check_budget()
            png_bytes = page.screenshot(type="png", full_page=False)
        finally:
            if context is not None:
                try:
                    context.close()
                except Exception:
                    pass
    except Exception:
        _reset_browser()
        raise

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
            # Expected transport rows equals requested limit (bounded 1..12)
            try:
                expected_rows = int(request.args.get('limit', '4'))
            except Exception:
                expected_rows = 4
            expected_rows = max(1, min(12, expected_rows))
            img = _render_dashboard_png(dash_url, width, height, zoom=zoom, expected_rows=expected_rows)
        except BaseException as e:
            print(f"image_push render failed: {e}")
            img = _render_error_png(width, height, str(e))
        # Rotate landscape content so delivered image is portrait
        if orientation == 'landscape' and Image is not None and img:
            try:
                from io import BytesIO
                im = Image.open(BytesIO(img))
                im = im.rotate(90, expand=True)
                if im.mode != 'L':
                    im = im.convert('L')
                out = BytesIO()
                im.save(out, format='PNG', optimize=True)
                img = out.getvalue()
            except Exception:
                pass
        _IMG_CACHE.update({'key': cache_key, 'ts': now_ts, 'img': img})

    resp = make_response(img)
    resp.headers['Content-Type'] = 'image/png'
    resp.headers['Cache-Control'] = 'no-store, max-age=0'
    resp.headers['X-Rendered-At'] = str(now_ts)
    # Report delivered dimensions (after rotation for landscape)
    if orientation == 'landscape':
        delivered_w, delivered_h = height, width
    else:
        delivered_w, delivered_h = width, height
    resp.headers['X-Viewport'] = f"{delivered_w}x{delivered_h}"
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


def _warm_start():
    global _WARM_TRIGGERED
    with _WARM_LOCK:
        if _WARM_TRIGGERED:
            return
        _WARM_TRIGGERED = True
    try:
        _get_browser()
    except Exception as exc:
        print(f"Playwright warm start failed: {exc}")
    try:
        get_weather_data()
    except Exception as exc:
        print(f"Weather warm start failed: {exc}")
    try:
        get_todays_menu()
    except Exception as exc:
        print(f"Canteen warm start failed: {exc}")

def _schedule_warm_start():
    try:
        threading.Thread(target=_warm_start, daemon=True).start()
    except Exception as exc:
        print(f"Warm start scheduling failed: {exc}")

_schedule_warm_start()
if __name__ == '__main__':
    app.run(debug=True)

"""Local Guild Wars 2 inventory viewer. Run with Python 3.10+."""
import json
import os
import logging
import hashlib
from datetime import datetime, timezone
from app_cache import DailyCache
import cleanup
import item_uses
import item_locations
import legendary
import legendary_catalog
import wiki_notes
import wiki_acquisition
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote, urlsplit
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
API = "https://api.guildwars2.com/v2"
ART_PROFESSIONS = {'guardian', 'elementalist', 'engineer', 'mesmer', 'necromancer', 'ranger', 'thief', 'warrior'}
CLIENT_DISCONNECTS = (BrokenPipeError, ConnectionResetError, ConnectionAbortedError)
LOGGER = logging.getLogger(__name__)
GAME_CACHE = DailyCache()


def account_partition(key):
    return hashlib.sha256(key.encode()).hexdigest() if key else 'public'


def refresh_cache(key):
    GAME_CACHE.clear(account_partition(key))
    GAME_CACHE.clear('public')
    wiki_acquisition.DATA_CACHE.clear()
    with wiki_notes._lock:
        wiki_notes._cache.clear()
    with item_uses._recipe_lock:
        item_uses._recipe_ids.clear()
    with cleanup._lock:
        cleanup._catalog = None


def load_key():
    values = {}
    if (ROOT / ".env").exists():
        for line in (ROOT / ".env").read_text(encoding="utf-8-sig").splitlines():
            if line.strip() and not line.lstrip().startswith("#") and "=" in line:
                name, value = line.split("=", 1)
                values[name.strip()] = value.strip().strip("\"'")
    return os.environ.get("GW2_API_KEY", values.get("GW2_API_KEY", "")).strip()


class ApiError(Exception):
    def __init__(self, message, status=502):
        super().__init__(message)
        self.status = status


def gw2(path, key=None):
    if path == '/tokeninfo':
        return fetch_gw2(path, key)  # Connecting always validates the live key.
    return GAME_CACHE.get((account_partition(key), path), lambda: fetch_gw2(path, key))


def fetch_gw2(path, key=None):
    headers = {"Accept": "application/json", "User-Agent": "LocalGW2Inventory/1.0"}
    if key:
        headers["Authorization"] = "Bearer " + key
    try:
        with urlopen(Request(API + path, headers=headers), timeout=20) as response:
            return json.load(response)
    except HTTPError as error:
        messages = {
            401: "Your API key was rejected. Check GW2_API_KEY in .env.",
            403: "Access denied. Check your key has characters and inventories permissions.",
            404: "That character or item could not be found. Refresh and try again.",
            429: "Guild Wars 2 is limiting requests. Wait a moment, then refresh.",
        }
        raise ApiError(messages.get(error.code, "Guild Wars 2 is unavailable. Try again shortly."), error.code if error.code in messages else 502) from None
    except (URLError, TimeoutError, ValueError):
        raise ApiError("Could not reach Guild Wars 2. Check your connection and try again.") from None


def inventory(name, key):
    data = gw2("/characters/" + quote(name, safe="") + "/inventory", key)
    ids = set()
    for bag in data["bags"]:
        if bag:
            ids.add(bag["id"])
            ids.update(item["id"] for item in bag["inventory"] if item)
    ids = sorted(ids)
    chunks = [ids[i:i + 200] for i in range(0, len(ids), 200)]
    items = {}
    warning = None
    try:
        with ThreadPoolExecutor(max_workers=4) as pool:
            for batch in pool.map(lambda chunk: gw2("/items?ids=" + ",".join(map(str, chunk))), chunks):
                items.update({str(item["id"]): item for item in batch})
    except ApiError:
        warning = "Some item details are unavailable. Inventory quantities are still shown; refresh to retry."
    return {"bags": data["bags"], "items": items, "warning": warning}


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        host = self.headers.get('Host', '')
        allowed = {f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'}
        if self.path != '/api/refresh' or host not in allowed or self.headers.get('Origin') not in (None, 'http://' + host) or self.headers.get('Content-Type') != 'application/json':
            self.send(403, b'{"error":"Request not allowed."}', 'application/json')
            return
        try:
            refresh_cache(self.get_key())
            self.send(200, b'{"ok":true}', 'application/json')
        except ApiError as error:
            self.send(error.status, json.dumps({'error': str(error)}).encode(), 'application/json')

    def get_key(self):
        return load_key()

    def handle(self):
        try:
            super().handle()
        except CLIENT_DISCONNECTS:
            self.close_connection = True

    def finish(self):
        try:
            super().finish()
        except CLIENT_DISCONNECTS:
            self.close_connection = True

    def send(self, status, body, content_type):
        # Catch disconnects here, including while sending an error response.
        # The browser may abort a request when changing characters or refreshing.
        try:
            self._send_response(status, body, content_type)
        except CLIENT_DISCONNECTS:
            self.close_connection = True

    def _send_response(self, status, body, content_type):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; img-src 'self' https://render.guildwars2.com; style-src 'self'; script-src 'self'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        url = urlsplit(self.path)
        static = {"/": ("index.html", "text/html"), "/app.js": ("app.js", "text/javascript"), "/style.css": ("style.css", "text/css"),
                  "/quaggan.svg": ("quaggan.svg", "image/svg+xml"), "/favicon.ico": ("favicon.ico", "image/x-icon")}
        try:
            if url.path == '/api/legendaries':
                self.send(200, json.dumps({'items': legendary_catalog.catalogue(gw2)}).encode(), 'application/json')
                return
            if url.path == '/api/project-definition':
                raw_id = parse_qs(url.query).get('id', [''])[0]
                if not raw_id.isascii() or not raw_id.isdigit(): raise ApiError('Choose a valid legendary.', 400)
                raw_route = parse_qs(url.query).get('route', ['0'])[0]
                if not raw_route.isascii() or not raw_route.isdigit() or int(raw_route) >= 32: raise ApiError('Choose a valid recipe route.', 400)
                self.send(200, json.dumps(legendary_catalog.definition(int(raw_id), gw2, int(raw_route))).encode(), 'application/json')
                return
            if url.path == '/bifrost.json':
                self.send(200, json.dumps(legendary.CATALOG).encode(), 'application/json')
                return
            if url.path == '/projects.js':
                self.send(200, (ROOT / 'public/projects.js').read_bytes(), 'text/javascript; charset=utf-8')
                return
            if url.path in {f'/art/{name}.jpg' for name in ART_PROFESSIONS}:
                self.send(200, (ROOT / 'public' / url.path.lstrip('/')).read_bytes(), 'image/jpeg')
                return
            if url.path in static:
                filename, content_type = static[url.path]
                self.send(200, (ROOT / "public" / filename).read_bytes(), content_type + "; charset=utf-8")
                return
            if url.path == '/api/acquisition':
                raw_id = parse_qs(url.query).get('id', [''])[0]
                if not (raw_id.isascii() and raw_id.isdigit() and 0 < int(raw_id) < 2147483648):
                    raise ApiError('Choose a valid item.', 400)
                try:
                    data = wiki_acquisition.lookup(int(raw_id), gw2)
                except Exception:
                    raise ApiError('Acquisition details could not be retrieved or matched to this item. Please retry shortly; the wiki may be unavailable.') from None
                self.send(200, json.dumps(data).encode(), 'application/json')
                return
            if url.path in ('/api/crafting-summary', '/api/wiki-summary'):
                parts = parse_qs(url.query).get('ids', [''])[0].split(',')
                if len(parts) > 20 or not all(p.isascii() and p.isdigit() and 0 < int(p) < 2147483648 for p in parts):
                    raise ApiError('Supply between 1 and 20 valid item IDs.', 400)
                ids = sorted(set(map(int, parts)))
                data = wiki_notes.summary(ids, gw2) if url.path == '/api/wiki-summary' else item_uses.crafting_summary(ids, gw2)
                self.send(200, json.dumps(data).encode(), 'application/json')
                return
            if url.path not in ("/api/characters", "/api/inventory", "/api/cleanup", "/api/item-uses", '/api/character-profile', '/api/item-locations', '/api/projects/bifrost', '/api/legendary-progress'):
                raise ApiError("Not found", 404)
            key = self.get_key()
            if not key or key == "your_api_key_here":
                raise ApiError("Add your API key to GW2_API_KEY in .env, then click Retry. Enable characters and inventories permissions on your key.", 503)
            if url.path == "/api/characters":
                data = gw2("/characters", key)
            elif url.path == '/api/legendary-progress':
                data = legendary_catalog.collection_progress(key, gw2)
            elif url.path == '/api/projects/bifrost':
                raw_id = parse_qs(url.query).get('id', [str(legendary.CATALOG['root'])])[0]
                if not raw_id.isascii() or not raw_id.isdigit(): raise ApiError('Choose a valid legendary.', 400)
                raw_route = parse_qs(url.query).get('route', ['0'])[0]
                if not raw_route.isascii() or not raw_route.isdigit() or int(raw_route) >= 32: raise ApiError('Choose a valid recipe route.', 400)
                data = legendary.progress(key, gw2, legendary_catalog.definition(int(raw_id), gw2, int(raw_route)))
            elif url.path == '/api/item-locations':
                raw_id = parse_qs(url.query).get('id', [''])[0]
                if not (raw_id.isascii() and raw_id.isdigit() and 0 < int(raw_id) < 2147483648):
                    raise ApiError('Choose a valid item.', 400)
                data = item_locations.find(int(raw_id), key, gw2)
            elif url.path == '/api/character-profile':
                name = parse_qs(url.query).get('character', [''])[0].strip()
                if not name or len(name) > 100:
                    raise ApiError('Choose a valid character.', 400)
                core = gw2('/characters/' + quote(name, safe='') + '/core', key)
                data = {k: core.get(k) for k in ('name', 'race', 'profession', 'level')}
                profession = str(core.get('profession', '')).lower()
                data['art'] = f'/art/{profession}.jpg' if profession in ART_PROFESSIONS else None
                try:
                    data['icon'] = gw2('/professions/' + quote(core['profession'], safe='')).get('icon_big')
                except ApiError:
                    data['icon'] = None
            elif url.path == '/api/item-uses':
                params = parse_qs(url.query)
                raw_id = params.get('id', [''])[0]
                raw_page = params.get('page', ['0'])[0]
                character = params.get('character', [''])[0].strip()
                if not (raw_id.isascii() and raw_id.isdigit() and 0 < int(raw_id) < 2147483648 and raw_page.isascii() and raw_page.isdigit() and int(raw_page) < 10000 and 0 < len(character) <= 100):
                    raise ApiError('Choose a valid item, character, and recipe page.', 400)
                data = item_uses.lookup(int(raw_id), int(raw_page), character, key, gw2)
            elif url.path == "/api/cleanup":
                raw = parse_qs(url.query).get('ids', [''])[0]
                parts = raw.split(',')
                if len(parts) > 1000 or not all(p.isascii() and p.isdigit() and 0 < int(p) < 2147483648 for p in parts):
                    raise ApiError('Supply between 1 and 1000 valid item IDs.', 400)
                try:
                    character = parse_qs(url.query).get('character', [''])[0].strip()
                    if len(character) > 100:
                        raise ApiError('Choose a valid character.', 400)
                    if character:
                        data = cleanup.analyze(sorted(set(map(int, parts))), key, gw2, character=character)
                    else:
                        data = cleanup.analyze(sorted(set(map(int, parts))), key, gw2)
                except ApiError as error:
                    if error.status in (401, 403):
                        raise ApiError('Collection checks need a valid API key with progression permission. Update GW2_API_KEY in .env and retry the collection check.', error.status) from None
                    raise
                except ValueError:
                    raise ApiError('Collection definitions are incomplete. No disposal recommendations can be made; retry later.') from None
            else:
                name = parse_qs(url.query).get("character", [""])[0].strip()
                if not name or len(name) > 100:
                    raise ApiError("Choose a valid character.", 400)
                data = inventory(name, key)
            if isinstance(data, dict) and 'checked_at' in data:
                stamp = GAME_CACHE.oldest(account_partition(key))
                if stamp:
                    data['checked_at'] = datetime.fromtimestamp(stamp, timezone.utc).isoformat()
            self.send(200, json.dumps(data).encode(), "application/json")
        except ApiError as error:
            self.send(error.status, json.dumps({"error": str(error)}).encode(), "application/json")
        except CLIENT_DISCONNECTS:
            self.close_connection = True
        except Exception as error:
            # Keep a concise diagnostic without logging keys, URLs, or account data.
            trace = error.__traceback__
            while trace.tb_next:
                trace = trace.tb_next
            LOGGER.error('Request failed: %s at %s:%s', type(error).__name__,
                         Path(trace.tb_frame.f_code.co_filename).name, trace.tb_lineno)
            self.send(500, b'{"error":"An unexpected error occurred. Please retry."}', "application/json")

    def log_message(self, *_):
        pass  # Avoid logging character names or other account data.


if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", 8000), Handler)
    print("Guild Wars 2 inventory: http://127.0.0.1:8000 (Ctrl+C to stop)", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()

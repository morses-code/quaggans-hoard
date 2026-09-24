"""Cross-platform desktop entry point. Browser mode remains available through server.py."""
import ctypes
import json
import os
import secrets
import sys
import threading
import time
import subprocess
from http.cookies import SimpleCookie
from pathlib import Path
from urllib.request import Request, urlopen

import server

SERVICE = 'QuaggansHoard'
RELEASE_API = 'https://api.github.com/repos/morses-code/quaggans-hoard/releases/latest'
RELEASES_URL = 'https://github.com/morses-code/quaggans-hoard/releases/latest'
PREFERENCE_KEYS = {'tyria.defaultCharacter', 'quaggansHoard.protectedItems', 'quaggansHoard.bifrostActive', 'quaggansHoard.selectedLegendary', 'quaggansHoard.trackedLegendary', 'quaggansHoard.trackedRecipe'}


def app_version():
    root = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))
    try:
        value = (root / 'app-version.txt').read_text(encoding='utf-8').strip()
        if value and all(part.isdigit() for part in value.split('.')):
            return value
    except OSError:
        pass
    return '0.0.0'


def version_tuple(value):
    try:
        parts = tuple(int(part) for part in value.removeprefix('v').split('.'))
        return parts + (0,) * (4 - len(parts)) if 3 <= len(parts) <= 4 else ()
    except (AttributeError, ValueError):
        return ()


def latest_release():
    request = Request(RELEASE_API, headers={'Accept': 'application/vnd.github+json',
                                            'User-Agent': 'Quaggans-Hoard-update-check'})
    with urlopen(request, timeout=8) as response:
        data = json.load(response)
    tag = data.get('tag_name', '') if isinstance(data, dict) else ''
    latest = tag.removeprefix('v')
    if not version_tuple(latest):
        raise ValueError('The release service returned an invalid version.')
    current = app_version()
    return {'current_version': current, 'latest_version': latest,
            'update_available': version_tuple(latest) > version_tuple(current),
            'release_url': RELEASES_URL}


def platform_details():
    if sys.platform == 'win32':
        return 'Windows', 'Windows Credential Manager'
    if sys.platform == 'darwin':
        return 'macOS', 'macOS Keychain'
    return 'Linux', 'your desktop keyring'


def data_directory():
    if sys.platform == 'win32':
        return Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData' / 'Local')) / 'QuaggansHoard'
    if sys.platform == 'darwin':
        return Path.home() / 'Library' / 'Application Support' / 'QuaggansHoard'
    return Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local' / 'share')) / 'QuaggansHoard'


class DesktopState:
    def __init__(self, vault, directory):
        self.vault = vault
        self.directory = directory
        self.lock = threading.RLock()
        self.key = vault.get_password(SERVICE, 'GW2_API_KEY') or ''
        self.preferences = {}
        try:
            data = json.loads((directory / 'preferences.json').read_text(encoding='utf-8'))
            if isinstance(data, dict):
                self.preferences = {k: v for k, v in data.items() if k in PREFERENCE_KEYS and isinstance(v, str)}
        except (OSError, ValueError):
            pass

    def connect(self, key):
        if not isinstance(key, str) or not 20 <= len(key.strip()) <= 200 or not key.strip().isascii() or any(c.isspace() for c in key.strip()):
            raise server.ApiError('Enter a valid Guild Wars 2 API key.', 400)
        key = key.strip()
        try:
            permissions = server.gw2('/tokeninfo', key).get('permissions', [])
        except server.ApiError as error:
            if error.status in (401, 403):
                raise server.ApiError('This API key was rejected. Check the key and try again.', 401) from None
            raise
        missing = {'account', 'characters', 'inventories', 'progression'} - set(permissions)
        if missing:
            raise server.ApiError('Enable these API key permissions: ' + ', '.join(sorted(missing)), 400)
        with self.lock:
            self.vault.set_password(SERVICE, 'GW2_API_KEY', key)
            self.key = key

    def disconnect(self):
        with self.lock:
            if self.vault.get_password(SERVICE, 'GW2_API_KEY') is not None:
                self.vault.delete_password(SERVICE, 'GW2_API_KEY')
            server.GAME_CACHE.clear(server.account_partition(self.key))
            self.key = ''

    def save_preferences(self, values):
        if not isinstance(values, dict) or any(k not in PREFERENCE_KEYS or not isinstance(v, str) or len(v) > 20000 for k, v in values.items()):
            raise server.ApiError('Invalid preferences.', 400)
        with self.lock:
            self.directory.mkdir(parents=True, exist_ok=True)
            temporary = self.directory / 'preferences.tmp'
            temporary.write_text(json.dumps(values), encoding='utf-8')
            temporary.replace(self.directory / 'preferences.json')
            self.preferences = values.copy()


def create_server(state):
    token = secrets.token_urlsafe(32)

    class DesktopHandler(server.Handler):
        def get_key(self):
            if not state.key:
                raise server.ApiError('Connect your API key using Account settings.', 401)
            return state.key

        def allowed(self):
            expected = f'127.0.0.1:{self.server.server_port}'
            if self.headers.get('Host') != expected:
                return False
            if self.headers.get('Origin') not in (None, 'http://' + expected):
                return False
            cookie = SimpleCookie()
            try:
                cookie.load(self.headers.get('Cookie', ''))
                return secrets.compare_digest(cookie['qh_session'].value, token)
            except (KeyError, ValueError):
                return False

        def do_GET(self):
            path = server.urlsplit(self.path).path
            if path == '/launch/' + token and self.headers.get('Host') == f'127.0.0.1:{self.server.server_port}':
                self.send_response(302)
                self.send_header('Set-Cookie', f'qh_session={token}; HttpOnly; SameSite=Strict; Path=/')
                self.send_header('Location', '/')
                self.send_header('Cache-Control', 'no-store')
                self.send_header('Content-Length', '0')
                self.end_headers()
                return
            if not self.allowed():
                self.send(403, b'{"error":"Open this page through the desktop app."}', 'application/json')
                return
            if path == '/desktop/state':
                with state.lock:
                    platform_name, credential_store = platform_details()
                    data = {'connected': bool(state.key), 'preferences': state.preferences.copy(),
                            'platform': platform_name, 'credential_store': credential_store,
                            'version': app_version()}
                self.send(200, json.dumps(data).encode(), 'application/json')
            elif path == '/desktop/update':
                try:
                    self.send(200, json.dumps(latest_release()).encode(), 'application/json')
                except Exception:
                    self.send(503, b'{"error":"Could not check for updates. Check your connection and try again."}', 'application/json')
            elif path == '/desktop.js':
                self.send(200, (server.ROOT / 'public/desktop.js').read_bytes(), 'text/javascript; charset=utf-8')
            elif path == '/':
                html = (server.ROOT / 'public/index.html').read_text(encoding='utf-8')
                html = html.replace('src="/app.js"', 'src="/desktop.js"')
                self.send(200, html.encode(), 'text/html; charset=utf-8')
            else:
                super().do_GET()

        def do_POST(self):
            if not self.allowed() or self.headers.get('Content-Type') != 'application/json':
                self.send(403, b'{"error":"Request not allowed."}', 'application/json')
                return
            if self.path == '/api/refresh':
                super().do_POST()
                return
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 50000:
                    raise server.ApiError('Invalid request size.', 400)
                self.connection.settimeout(10)
                data = json.loads(self.rfile.read(length))
                if not isinstance(data, dict):
                    raise server.ApiError('Invalid request.', 400)
                if self.path == '/desktop/connect':
                    state.connect(data.get('key'))
                elif self.path == '/desktop/disconnect':
                    state.disconnect()
                elif self.path == '/desktop/preferences':
                    state.save_preferences(data)
                else:
                    raise server.ApiError('Not found', 404)
                self.send(200, b'{"ok":true}', 'application/json')
            except server.ApiError as error:
                self.send(error.status, json.dumps({'error': str(error)}).encode(), 'application/json')
            except (ValueError, TimeoutError):
                self.send(400, b'{"error":"Invalid or incomplete request."}', 'application/json')
            except Exception:
                self.send(500, b'{"error":"The operating system could not save this change. Please retry."}', 'application/json')

    http = server.ThreadingHTTPServer(('127.0.0.1', 0), DesktopHandler)
    http.daemon_threads = True
    return http, f'http://127.0.0.1:{http.server_port}/launch/{token}'


def main():
    import webview
    import keyring
    directory = data_directory()
    smoke_report = Path(sys.argv[2]) if len(sys.argv) == 3 and sys.argv[1] == '--smoke-test' else None
    package_report = Path(sys.argv[2]) if len(sys.argv) == 3 and sys.argv[1] == '--package-smoke-test' else None
    # Packaging diagnostics never read or write a real user's credential.
    class EmptyVault:
        def get_password(self, *args):
            return None
    state = DesktopState(EmptyVault() if smoke_report or package_report else keyring, directory)
    http, url = create_server(state)
    thread = threading.Thread(target=http.serve_forever, daemon=True)
    thread.start()
    try:
        if package_report:
            from http.cookiejar import CookieJar
            from urllib.request import build_opener, HTTPCookieProcessor
            result = {'passed': False}
            try:
                client = build_opener(HTTPCookieProcessor(CookieJar()))
                html = client.open(url, timeout=10).read()
                state_data = json.load(client.open(f'http://127.0.0.1:{http.server_port}/desktop/state', timeout=10))
                result['passed'] = b'/desktop.js' in html and state_data['platform'] == platform_details()[0]
            except Exception as error:
                result['error'] = type(error).__name__
            package_report.write_text(json.dumps(result), encoding='utf-8')
            return
        webview.settings['ALLOW_FILE_URLS'] = False
        webview.settings['OPEN_EXTERNAL_LINKS_IN_BROWSER'] = True
        window = webview.create_window("Quaggan's Hoard", url, width=1280, height=900, min_size=(720, 600), background_color='#17383d', text_select=True, hidden=bool(smoke_report))
        def smoke_check():
            result = {'passed': False}
            try:
                for _ in range(150):
                    if window.evaluate_js("!!document.getElementById('connect-form') && typeof categoryFor === 'function'"):
                        result['passed'] = bool(window.evaluate_js("!document.getElementById('connect-form').hidden && document.getElementById('desktop-key').type === 'password' && window.desktopConnected === false"))
                        break
                    time.sleep(.1)
            except Exception as error:
                result['error'] = type(error).__name__
            finally:
                smoke_report.write_text(json.dumps(result), encoding='utf-8')
                window.destroy()
        gui = {'win32': 'edgechromium', 'darwin': 'cocoa'}.get(sys.platform, 'qt')
        icon = str(server.ROOT / 'public' / ('favicon.ico' if sys.platform == 'win32' else 'quaggan-512.png'))
        webview.start(smoke_check if smoke_report else None, gui=gui, private_mode=True, debug=False, icon=icon)
    finally:
        http.shutdown()
        http.server_close()


def show_startup_error():
    platform_name, credential_store = platform_details()
    message = f"Quaggan's Hoard could not start. Check that the system web view and {credential_store} are available."
    if sys.platform == 'win32':
        ctypes.windll.user32.MessageBoxW(None, message + ' Install Microsoft Edge WebView2 Runtime if needed.', "Quaggan's Hoard", 0x10)
    elif sys.platform == 'darwin':
        subprocess.run(['osascript', '-e', f'display alert "Quaggan\'s Hoard" message {json.dumps(message)} as critical'], check=False)
    else:
        try:
            subprocess.run(['zenity', '--error', '--title', "Quaggan's Hoard", '--text', message], check=False)
        except OSError:
            print(f'{platform_name}: {message}', file=sys.stderr)


if __name__ == '__main__':
    try:
        main()
    except Exception:
        show_startup_error()
        sys.exit(1)

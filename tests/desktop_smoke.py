"""Exercise the actual WebView2 window, hidden, without real credentials."""
import sys
import tempfile
import threading
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import webview
import desktop
from unittest.mock import patch
from test_desktop import FakeVault

result = []
with tempfile.TemporaryDirectory() as directory:
    state = desktop.DesktopState(FakeVault(), Path(directory))
    http, url = desktop.create_server(state)
    threading.Thread(target=http.serve_forever, daemon=True).start()
    window = webview.create_window('Desktop smoke', url, hidden=True)
    def check():
        try:
            for _ in range(100):
                if window.evaluate_js("!!document.getElementById('connect-form') && typeof categoryFor === 'function'"):
                    break
                time.sleep(.1)
            else:
                raise AssertionError('Desktop bootstrap did not finish')
            assert window.evaluate_js("!document.getElementById('connect-form').hidden")
            assert window.evaluate_js("document.getElementById('desktop-key').type === 'password'")
            assert window.evaluate_js("window.desktopConnected === false")
            with patch.object(desktop.server, 'gw2', side_effect=lambda path, key=None: {'permissions': ['account', 'characters', 'inventories', 'progression']} if path == '/tokeninfo' else []):
                window.evaluate_js("document.getElementById('desktop-key').value = 'native-smoke-fake-api-key'; document.getElementById('connect-form').requestSubmit();")
                for _ in range(100):
                    if window.evaluate_js("window.desktopConnected === true && !!document.getElementById('forget-key')"):
                        break
                    time.sleep(.1)
                else:
                    raise AssertionError('Native key setup did not connect')
                assert state.vault.key == 'native-smoke-fake-api-key'
                window.evaluate_js("document.getElementById('account-settings').click(); document.getElementById('forget-key').click();")
                for _ in range(100):
                    if state.vault.key is None and window.evaluate_js("window.desktopConnected === false && !!document.getElementById('connect-form') && !document.getElementById('connect-form').hidden"):
                        break
                    time.sleep(.1)
                else:
                    raise AssertionError('Forget key did not return to setup')
            result.append('passed')
        except Exception as error:
            result.append(type(error).__name__ + ': ' + str(error))
        finally:
            window.destroy()
    try:
        webview.start(check, gui='edgechromium', private_mode=True)
    finally:
        http.shutdown()
        http.server_close()
if result != ['passed']:
    raise AssertionError(result)
print('Native desktop smoke passed: WebView2, authenticated bootstrap, first-run setup.')

"""Render desktop and mobile screenshots with synthetic inventory data."""
import json
from pathlib import Path
import subprocess
import tempfile
import threading
import time
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server
from browser_smoke import FixtureHandler, ADVICE

ITEMS = server.gw2('/items?ids=19721,46731,19723,19726,19727,19728,19729,19730,19731,19732,19733,19734')
ITEM_MAP = {str(i['id']): i for i in ITEMS}
SLOTS = [{'id': item['id'], 'count': (index + 1) * 7} for index, item in enumerate(ITEMS)]


class Preview(FixtureHandler):
    def do_GET(self):
        path = self.path.split('?')[0]
        if path == '/app.js':
            mobile = b"\nif (location.search.includes('mobile')) { document.documentElement.style.width='390px'; document.body.style.width='390px'; }"
            project = b"\nif (location.search.includes('projects')) { showAppView(true); } if (location.search.includes('acquisition')) { const previewTimer = setInterval(() => { const card = [...document.querySelectorAll('.material-card')].find(node => node.querySelector('strong')?.textContent === 'Mystic Clover'); if (card) { clearInterval(previewTimer); card.open = true; const preview = card.cloneNode(true); document.querySelector('main').hidden = true; document.querySelector('.site-header').hidden = true; preview.style.margin = '18px'; document.body.append(preview); window.scrollTo(0, 0); } }, 100); }"
            self.send(200, (server.ROOT / 'public/app.js').read_bytes() + mobile + project, 'text/javascript; charset=utf-8')
            return
        data = None
        if path == '/api/inventory':
            data = {'bags': [{'id': 0, 'size': 16, 'inventory': SLOTS + [None] * 4}], 'items': {**ITEM_MAP, '0': {'name': 'Reinforced inventory bag'}}}
        elif path == '/api/cleanup':
            data = {'items': {str(i['id']): ADVICE for i in ITEMS}, 'warnings': [], 'checked_at': ADVICE['checked_at']}
        elif path == '/api/wiki-summary':
            data = {'items': {str(i['id']): {'state': 'none', 'notes': [], 'message': 'No disposal guidance.', 'source': 'https://wiki.guildwars2.com'} for i in ITEMS}}
        elif path == '/api/crafting-summary':
            data = {'items': {str(i['id']): {'count': 5} for i in ITEMS}}
        if data is not None:
            self.send(200, json.dumps(data).encode(), 'application/json')
        else:
            super().do_GET()


if __name__ == '__main__':
    http = server.ThreadingHTTPServer(('127.0.0.1', 0), Preview)
    threading.Thread(target=http.serve_forever, daemon=True).start()
    directory = server.ROOT / 'artifacts'
    directory.mkdir(exist_ok=True)
    try:
        for label, size in [('desktop', '1440,1400'), ('mobile', '390,1100')]:
            view = label + ('&projects' if '--projects' in sys.argv or '--acquisition' in sys.argv else '') + ('&acquisition' if '--acquisition' in sys.argv else '')
            target = directory / f'{label}-review-{time.time_ns()}.png'
            with tempfile.TemporaryDirectory(prefix='inventory-visual-', ignore_cleanup_errors=True) as profile:
                subprocess.run([r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe', '--headless', '--disable-gpu', '--no-first-run', '--no-default-browser-check', '--hide-scrollbars', '--user-data-dir=' + profile, '--window-size=' + size, '--screenshot=' + str(target), '--virtual-time-budget=10000', f'http://127.0.0.1:{http.server_port}/?{view}'], capture_output=True, timeout=30)
                for _ in range(100):
                    if target.exists():
                        break
                    time.sleep(.2)
                if not target.exists():
                    raise RuntimeError('Screenshot not produced: ' + label)
                print(target)
    finally:
        http.shutdown()
        http.server_close()

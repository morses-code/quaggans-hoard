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
            project = b"""
const previewWait = condition => new Promise(resolve => { const timer = setInterval(() => { if (condition()) { clearInterval(timer); resolve(); } }, 100); });
(async () => {
  const mode = new URLSearchParams(location.search).get('view') || '';
  if (mode === 'item' || mode === 'item-sources') {
    await previewWait(() => current && !analysisLoading && document.querySelector('button.slot'));
    document.querySelector('button.slot').click();
    await previewWait(() => $('item-uses').textContent.includes('Example crafted output'));
    $('find-item').click();
    await previewWait(() => !$('find-item').disabled);
    $('item-dialog').scrollTop = mode === 'item-sources' ? 650 : 0;
  }
  if (mode === 'projects' || mode === 'requirements' || mode === 'acquisition') {
    showAppView(true);
  }
  if (mode === 'requirements' || mode === 'acquisition') {
    await previewWait(() => legendaryItems.length > 0);
    await selectLegendary(30698);
    await previewWait(() => bifrostProgress && $('project-results').textContent.includes('Still to collect'));
    if (mode === 'requirements') {
      $('legendary-library').hidden = true;
      document.querySelector('.legendary-browser-heading').hidden = true;
      window.scrollTo(0, 0);
    }
  }
  if (mode === 'acquisition') {
    const card = [...document.querySelectorAll('.material-card')].find(node => node.querySelector('strong')?.textContent === 'Mystic Clover');
    card.open = true;
    await previewWait(() => card.querySelector('.wiki-acquisition'));
    const preview = card.cloneNode(true);
    preview.querySelectorAll('details').forEach(node => node.open = true);
    document.querySelector('main').hidden = true;
    document.querySelector('.site-header').hidden = true;
    preview.style.margin = '18px';
    document.body.append(preview);
    window.scrollTo(0, 0);
  }
})();
"""
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
        elif path == '/api/item-uses':
            data = {'storage': {'carried': 7, 'stored': 240, 'capacity': 250, 'eligible': True,
                                'depositable': 7, 'overflow': 0, 'total': 247},
                    'crafting': {'total': 1, 'page': 0, 'has_more': False, 'recipes': [
                        {'id': 3, 'name': 'Example crafted output', 'count': 1,
                         'disciplines': ['Artificer'], 'rating': 400,
                         'ingredients': [{'name': 'Glob of Ectoplasm', 'count': 5, 'selected': True}],
                         'wiki': 'https://wiki.guildwars2.com',
                         'source': 'https://api.guildwars2.com/v2/recipes/3'}]}}
        if data is not None:
            self.send(200, json.dumps(data).encode(), 'application/json')
        else:
            super().do_GET()


if __name__ == '__main__':
    http = server.ThreadingHTTPServer(('127.0.0.1', 0), Preview)
    threading.Thread(target=http.serve_forever, daemon=True).start()
    docs = '--docs' in sys.argv
    directory = server.ROOT / ('docs/images' if docs else 'artifacts')
    directory.mkdir(exist_ok=True)
    try:
        views = ([('inventory-overview', '1440,1400', ''),
                  ('item-details', '1440,1400', 'item'),
                  ('item-sources', '1440,1400', 'item-sources'),
                  ('legendary-projects', '1440,1400', 'projects'),
                  ('legendary-requirements', '1440,1400', 'requirements'),
                  ('legendary-acquisition', '1440,1600', 'acquisition')]
                 if docs else [('desktop', '1440,1400', 'projects' if '--projects' in sys.argv else ''),
                               ('mobile', '390,1100', 'projects' if '--projects' in sys.argv else '')])
        for label, size, view in views:
            target = directory / (f'{label}.png' if docs else f'{label}-review-{time.time_ns()}.png')
            target.unlink(missing_ok=True)
            with tempfile.TemporaryDirectory(prefix='inventory-visual-', ignore_cleanup_errors=True) as profile:
                subprocess.run([r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe', '--headless', '--disable-gpu', '--no-first-run', '--no-default-browser-check', '--hide-scrollbars', '--user-data-dir=' + profile, '--window-size=' + size, '--screenshot=' + str(target), '--virtual-time-budget=15000', f'http://127.0.0.1:{http.server_port}/?view={view}'], capture_output=True, timeout=30)
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

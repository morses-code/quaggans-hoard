"""Manual browser smoke check: python tests/browser_smoke.py (Microsoft Edge required)."""
import json
from pathlib import Path
import subprocess
import tempfile
import threading
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server

ITEM = {'id': 1, 'name': 'Test material', 'type': 'CraftingMaterial', 'description': 'A test item.'}
ADVICE = {'status': 'check', 'reason': 'Not disposal advice', 'collections': [],
          'storage': {'overflow': 10},
          'checked_at': '2026-09-22T12:00:00Z', 'primary_action': 'deposit',
          'actions': [{'kind': 'deposit', 'label': 'Deposit materials', 'reason': 'Room for 10.',
                       'evidence': 'API checked', 'source': 'https://api.guildwars2.com/v2/items/1'}]}
SCRIPT = b"""
async function smoke() {
  function expect(condition, message) { if (!condition) throw new Error(message); }
  for (let i=0; i<100 && !current; i++) await new Promise(r => setTimeout(r, 50));
  expect(current, 'inventory did not load');
  expect($('bags').querySelectorAll('button.slot').length === 1, 'inventory visible while loading');
  expect(!document.getElementById('check-cleanup'), 'manual analysis button removed');
  for (let i=0; i<200 && analysisLoading; i++) await new Promise(r => setTimeout(r, 50));
  expect(craftingResults[1]?.count === 1, 'recipes checked automatically');
  expect($('analysis-panel').dataset.state === 'complete', 'visible completion state');
  expect($('analysis-percent').textContent === '100%', 'progress reaches completion');
  expect($('recipes-progress').value === 1, 'recipe progress reflects results');
  expect(wikiResults[1]?.state === 'notes', 'wiki checked automatically');
  expect(categoryFor(1) === 'crafting', 'crafting category');
  expect($('cleanup-filter').options.length === 7, 'six categories and all');
  for (const type of ['Armor', 'Weapon', 'Trinket', 'Back', 'Gathering', 'Bag', 'Relic', 'Consumable']) {
    current.items[98] = {type};
    expect(categoryFor(98) === (type === 'Consumable' ? 'consumables' : 'equipment'), 'item type category before checks: ' + type);
    craftingResults[98] = {count: 2};
    expect(categoryFor(98) === (type === 'Consumable' ? 'consumables' : 'equipment'), 'type category remains after recipes: ' + type);
    delete craftingResults[98];
  }
  delete current.items[98];
  const gear = {type: 'Weapon', rarity: 'Exotic', level: 80, details: {type: 'Sword'}};
  current.items[97] = gear;
  current.items[96] = {type: 'Consumable', details: {type: 'Food'}};
  refreshDetailFilters();
  $('gear-rarity').value = 'Exotic';
  $('gear-type').value = 'Sword';
  $('gear-binding').value = 'Account';
  $('gear-min').value = '70';
  expect(matchesEquipment(gear, {binding: 'Account'}), 'combined equipment filters');
  expect(!matchesEquipment(gear, {}), 'binding filter uses actual slot binding');
  $('gear-max').value = '79';
  expect(!matchesEquipment(gear, {binding: 'Account'}), 'maximum level filter');
  expect([...$('consumable-type').options].some(option => option.value === 'Food'), 'consumable subtype choices');
  delete current.items[97]; delete current.items[96];
  refreshDetailFilters();
  $('cleanup-filter').value = 'crafting'; render();
  expect($('bags').querySelectorAll('button.slot').length === 1, 'crafting filter');
  $('bags').querySelector('button.slot').click();
  expect($('item-dialog').open, 'item dialog');
  $('find-item').click();
  expect($('item-locations').querySelector('.spinner'), 'account lookup spinner visible');
  expect($('item-locations').getAttribute('aria-busy') === 'true', 'account lookup announces busy');
  for (let i=0; i<100 && $('find-item').disabled; i++) await new Promise(r => setTimeout(r, 50));
  expect($('item-locations').textContent.includes('Other Character'), 'account finder displays character locations');
  expect(!$('item-locations').querySelector('.spinner'), 'completed lookup removes spinner');
  expect($('item-locations').getAttribute('aria-busy') === 'false', 'completed lookup clears busy state');
  expect(!document.getElementById('checklist-only'), 'checklist removed');
  const originalFetch = window.fetch;
  window.fetch = (path, options) => {
    if (path === '/__timeout') return new Promise((resolve, reject) => options.signal.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')), {once: true}));
    if (path.startsWith('/api/item-locations')) return Promise.reject(new TypeError('Test connection failed'));
    return originalFetch(path, options);
  };
  try {
    let timedOut = false;
    try { await api('/__timeout', undefined, 10); } catch (error) { timedOut = error.message.includes('timed out'); }
    expect(timedOut, 'stalled requests become actionable timeout errors');
    $('find-item').click();
    for (let i=0; i<100 && $('find-item').disabled; i++) await new Promise(r => setTimeout(r, 10));
    expect($('item-locations').querySelector('.lookup-error'), 'failed lookup shows error');
    expect(!$('item-locations').querySelector('.spinner'), 'failed lookup removes spinner');
    expect(!$('find-item').disabled, 'failed lookup permits retry');
  } finally { window.fetch = originalFetch; }
  expect($('item-cleanup').textContent.includes('API checked'), 'evidence label');
  expect($('item-cleanup').textContent.includes('Room for 10.'), 'action explanation');
  expect($('item-cleanup').textContent.includes('Example wiki note.'), 'wiki note displayed');
  $('item-cleanup').querySelector('button').click();
  expect(categoryFor(1) === 'keep', 'personal keep overrides crafting');
  expect(JSON.parse(localStorage.getItem(protectedItemsKey)).includes(1), 'keep preference persisted');
  expect(cardReason(current.items[1], {id: 1}) === 'Keep for me', 'personal reason visible');
  $('item-cleanup').querySelector('button').click();
  expect(categoryFor(1) === 'crafting', 'removing keep restores category');
  for (let i=0; i<100 && !$('item-uses').textContent.includes('Test crafted output'); i++) await new Promise(r => setTimeout(r, 50));
  expect($('item-uses').textContent.includes('Test crafted output'), 'recipe output');
  expect($('item-uses').textContent.includes('10 would remain'), 'storage overflow');
  $('item-dialog').close();
  $('cleanup-filter').value = 'sell'; render();
  expect($('bags').querySelectorAll('button.slot').length === 0, 'crafting item excluded from sell');
  cleanupResults[99] = { status: 'safe', actions: [{kind: 'vendor'}] };
  wikiResults[99] = {state: 'none'};
  expect(categoryFor(99) === 'check', 'pending recipes block sell');
  craftingResults[99] = {error: 'Unavailable'};
  expect(categoryFor(99) === 'check', 'failed recipes block sell');
  craftingResults[99] = {count: 0};
  expect(categoryFor(99) === 'sell', 'confirmed non-crafting sale');
  craftingResults[99] = {count: 1};
  expect(categoryFor(99) === 'crafting', 'crafting overrides sale');
  craftingResults[99] = {count: 0};
  wikiResults[99] = {state: 'review'};
  expect(categoryFor(99) === 'check', 'conditional wiki advice blocks automatic sale');
  cleanupResults[99] = {status: 'check', collections_available: true, collections: []};
  wikiResults[99] = {state: 'explicit'};
  expect(categoryFor(99) === 'sell', 'explicit wiki advice supports disposal');
  cleanupResults[99].collections_available = false;
  expect(categoryFor(99) === 'check', 'wiki does not bypass unavailable collection checks');
  current.bags[0].inventory.push({id: 1, count: 5, binding: 'Account'});
  cleanupResults[1].elsewhere = {bank: 20, shared: null};
  render();
  expect(spaceFlags(1).duplicates, 'duplicate copies detected across bag slots');
  expect(!spaceFlags(1).combine, 'duplicates do not imply stackability');
  expect(spaceFlags(1).overflow && spaceFlags(1).elsewhere, 'storage highlights detected');
  $('cleanup-filter').value = 'all';
  for (const filter of ['duplicates', 'overflow', 'elsewhere']) {
    $('space-filter').value = filter; render();
    expect($('bags').querySelectorAll('button.slot').length === 2, 'space filter: ' + filter);
  }
  $('space-filter').value = 'combine'; render();
  expect(!$('bags').querySelector('button.slot'), 'unmergeable duplicates excluded');
  $('space-filter').value = 'duplicates';
  $('cleanup-filter').value = 'equipment'; render();
  expect(!$('bags').querySelector('button.slot'), 'space and category filters intersect');
  $('cleanup-filter').value = 'all'; render();
  $('bags').querySelector('button.slot').click();
  expect($('item-cleanup').textContent.includes('Bag 1, slot 3: 5'), 'duplicate slot locations shown');
  expect($('item-cleanup').textContent.includes('Bank: 20'), 'bank quantity shown');
  expect($('item-cleanup').textContent.includes('Shared inventory: Unavailable'), 'failed source is not zero');
  $('item-dialog').close();
  $('cleanup-filter').value = 'all';
  $('space-filter').value = 'all';
  expect(!document.getElementById('changes-only'), 'change tracking removed');
  await loadInventory();
  expect($('space-filter').value === 'all', 'refresh clears space filter');
  expect(Object.keys(cleanupResults).length === 0, 'refresh must clear advice');
  document.body.dataset.smoke = 'passed';
  await fetch('/__smoke?result=passed');
}
smoke().catch(error => { fetch('/__smoke?result=' + encodeURIComponent(error.message)); });
"""
finished = threading.Event()
outcome = []


class FixtureHandler(server.Handler):
    def do_GET(self):
        path = self.path.split('?')[0]
        if path == '/__smoke':
            outcome.append(server.parse_qs(server.urlsplit(self.path).query).get('result', ['unknown'])[0])
            finished.set()
            self.send(200, b'ok', 'text/plain')
            return
        fixtures = {
            '/api/item-locations': {'total': 5, 'locations': [{'location': 'Other Character', 'slot': 'Bag 1, slot 1', 'count': 5}], 'warnings': []},
            '/api/characters': ['Test Character'],
            '/api/character-profile': {'name': 'Test Character', 'profession': 'Guardian', 'race': 'Human', 'level': 80, 'art': '/art/guardian.jpg', 'icon': None},
            '/api/inventory': {'bags': [{'id': 2, 'size': 2, 'inventory': [{'id': 1, 'count': 10}, None]}], 'items': {'1': ITEM}},
            '/api/cleanup': {'items': {'1': ADVICE}, 'checked_at': ADVICE['checked_at'], 'warnings': []},
            '/api/crafting-summary': {'items': {'1': {'count': 1}}},
            '/api/wiki-summary': {'items': {'1': {'state': 'notes', 'notes': ['Example wiki note.'], 'message': 'No disposal guidance.', 'source': 'https://wiki.guildwars2.com/wiki/Example#Notes'}}},
            '/api/item-uses': {'storage': {'carried': 10, 'stored': 250, 'capacity': 250, 'eligible': True, 'depositable': 0, 'overflow': 10, 'total': 260},
                               'crafting': {'total': 1, 'page': 0, 'has_more': False, 'recipes': [
                                   {'id': 3, 'name': 'Test crafted output', 'count': 1, 'disciplines': ['Artificer'], 'rating': 400,
                                    'ingredients': [{'name': 'Test material', 'count': 5, 'selected': True}],
                                    'wiki': 'https://wiki.guildwars2.com', 'source': 'https://api.guildwars2.com/v2/recipes/3'}]}},
        }
        if path in fixtures:
            self.send(200, json.dumps(fixtures[path]).encode(), 'application/json')
        elif path == '/app.js':
            self.send(200, (server.ROOT / 'public/app.js').read_bytes() + SCRIPT, 'text/javascript; charset=utf-8')
        else:
            super().do_GET()


if __name__ == '__main__':
    http = server.ThreadingHTTPServer(('127.0.0.1', 0), FixtureHandler)
    thread = threading.Thread(target=http.serve_forever, daemon=True)
    thread.start()
    try:
        with tempfile.TemporaryDirectory(prefix='inventory-browser-test-', ignore_cleanup_errors=True) as profile:
            result = subprocess.run([
                r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',
                '--headless', '--disable-gpu', '--no-first-run', '--no-default-browser-check',
                '--disable-background-networking', '--user-data-dir=' + profile,
                '--dump-dom', '--virtual-time-budget=15000', f'http://127.0.0.1:{http.server_port}',
            ], capture_output=True, timeout=45, encoding='utf-8')
            finished.wait(20)
            if outcome != ['passed']:
                raise AssertionError(str(outcome) + result.stdout[-5000:] + result.stderr[-1000:])
            print('Browser smoke passed: load, analysis, filters, item dialog, evidence, refresh invalidation.')
    finally:
        http.shutdown()
        http.server_close()

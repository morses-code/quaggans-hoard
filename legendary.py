"""Source-reviewed Bifrost recipe tree and request-local account allocation."""
import json
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

CATALOG = json.loads((Path(__file__).parent / 'bifrost.json').read_text(encoding='utf-8'))


def allocate(holdings, catalog=CATALOG):
    remaining = defaultdict(int, holdings)
    shopping = {}
    needed = set()

    def visit(item_id, required):
        item = catalog['nodes'][str(item_id)]
        used = min(required, remaining[item_id])
        remaining[item_id] -= used
        missing = required - used
        needed.add(item_id)
        children = [visit(part['id'], part['count'] * missing) for part in item['ingredients']] if missing else []
        if not item['ingredients']:
            row = shopping.setdefault(item_id, {**item, 'required': 0, 'allocated': 0, 'missing': 0})
            row['required'] += required
            row['allocated'] += used
            row['missing'] += missing
        return {**item, 'required': required, 'allocated': used, 'missing': missing,
                'children': children, 'ready': missing == 0 or bool(children) and all(child['ready'] for child in children)}

    tree = visit(catalog['root'], 1)
    return {'tree': tree, 'shopping': sorted(shopping.values(), key=lambda row: row['name']),
            'needed_ids': sorted(needed - {catalog['root']})}


def progress(key, fetch):
    jobs = [('Bank', '/account/bank', 'slots'), ('Shared inventory', '/account/inventory', 'slots'),
            ('Material storage', '/account/materials', 'slots'), ('Legendary Armory', '/account/legendaryarmory', 'slots'),
            ('Wallet', '/account/wallet', 'wallet')]
    warnings = []
    try:
        names = fetch('/characters', key)
        jobs.extend((name, '/characters/' + quote(name, safe='') + '/inventory', 'bags') for name in names)
    except Exception:
        warnings.append('Character inventories could not be listed.')

    def read(job):
        label, path, kind = job
        try:
            data = fetch(path, key)
            if kind == 'wallet':
                return label, data, None
            slots = [slot for bag in data['bags'] if bag for slot in bag['inventory']] if kind == 'bags' else data
            return label, [slot for slot in slots if slot], None
        except Exception:
            return label, [], f'{label} unavailable; its items are not counted.'

    holdings = defaultdict(int)
    locations = defaultdict(list)
    wallet = None
    acquisition_warnings = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        for label, slots, warning in pool.map(read, jobs):
            if label == 'Wallet':
                if warning:
                    acquisition_warnings.append('Wallet unavailable. Enable wallet permission on your API key to compare currency costs.')
                else:
                    wallet = {row['id']: row['value'] for row in slots}
                continue
            if warning:
                warnings.append(warning)
            for slot in slots:
                holdings[slot['id']] += slot['count']
                if slot['count']:
                    locations[slot['id']].append({'location': label, 'count': slot['count']})
    result = allocate(holdings)
    result['wallet'] = wallet
    result['acquisition_warnings'] = acquisition_warnings
    result.update({'holdings': dict(holdings), 'locations': dict(locations), 'warnings': warnings,
                   'complete_scan': not warnings, 'checked_at': datetime.now(timezone.utc).isoformat()})
    return result

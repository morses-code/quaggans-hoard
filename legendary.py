"""Source-reviewed Bifrost recipe tree and request-local account allocation."""
import json
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

CATALOG = json.loads((Path(__file__).parent / 'bifrost.json').read_text(encoding='utf-8'))
ACQUISITION = json.loads((Path(__file__).parent / 'acquisition.json').read_text(encoding='utf-8'))


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
    cost_ids = {r['id'] for r in ACQUISITION['resources'].values() if r['kind'] == 'item'}
    tracked_ids = set(map(int, CATALOG['nodes'])) | cost_ids
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
            return label, [slot for slot in slots if slot and slot['id'] in tracked_ids], None
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
    result['acquisition'] = acquisition_options(result, holdings, wallet, not warnings)
    result['acquisition_warnings'] = acquisition_warnings
    result.update({'holdings': dict(holdings), 'locations': dict(locations), 'warnings': warnings,
                   'complete_scan': not warnings, 'checked_at': datetime.now(timezone.utc).isoformat()})
    return result


def acquisition_options(plan, holdings, wallet, inventory_complete, catalog=ACQUISITION):
    """Compare alternatives independently, after reserving the direct recipe inputs."""
    reserved = defaultdict(int)
    def visit(row):
        reserved[row['id']] += row['allocated']
        for child in row['children']:
            visit(child)
    visit(plan['tree'])
    results = {}
    for row in plan['shopping']:
        item_id, missing = row['id'], row['missing']
        entry = catalog['items'].get(str(item_id), {})
        offers = []
        for offer in entry.get('offers', []):
            trades = (missing + offer['output'] - 1) // offer['output']
            costs = []
            capacity = []
            for cost in offer['costs']:
                resource = catalog['resources'][cost['resource']]
                is_item = resource['kind'] == 'item'
                known = inventory_complete if is_item else wallet is not None
                owned = holdings.get(resource['id'], 0) if is_item else (wallet or {}).get(resource['id'], 0)
                keep = reserved[resource['id']] if is_item else 0
                free = max(0, owned - keep)
                required = trades * cost['count']
                costs.append({**resource, 'per_trade': cost['count'], 'required': required,
                              'owned': owned if known else None, 'known_owned': owned,
                              'reserved': keep, 'available': free if known else None,
                              'shortfall': max(0, required - free) if known else None})
                capacity.append(free // cost['count'] if known else None)
            affordable = min(capacity) if all(n is not None for n in capacity) else None
            supported = min(affordable, trades, offer['limit'] if offer['limit'] is not None else trades) if affordable is not None else None
            offers.append({**offer, 'costs': costs, 'trades_needed': trades,
                           'supported_output': supported * offer['output'] if supported is not None else None})
        results[str(item_id)] = {**entry, 'offers': offers, 'reviewed': catalog['reviewed']}
    return results

"""Request-local account allocation for dynamically imported legendary recipes."""
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from urllib.parse import quote

def allocate(holdings, catalog):
    remaining = defaultdict(int, holdings)
    shopping = {}
    needed = set()

    def reserve(item_id, required):
        item = catalog['nodes'][str(item_id)]
        used = min(required, remaining[item_id])
        remaining[item_id] -= used
        missing = required - used
        needed.add(item_id)
        if not item['ingredients']:
            row = shopping.setdefault(item_id, {**item, 'required': 0, 'allocated': 0, 'missing': 0})
            row['required'] += required
            row['allocated'] += used
            row['missing'] += missing
        return {**item, 'required': required, 'allocated': used, 'missing': missing, 'children': []}

    tree = reserve(catalog['root'], 1)
    pending = deque([tree])
    # Reserve each recipe level before expanding deeper subcomponents. Otherwise
    # a precursor's materials can consume stock needed by the final combination.
    while pending:
        node = pending.popleft()
        if node['missing']:
            node['children'] = [reserve(part['id'], part['count'] * node['missing']) for part in node['ingredients']]
            pending.extend(node['children'])

    def finish(node):
        for child in node['children']:
            finish(child)
        node['ready'] = node['missing'] == 0 or bool(node['children']) and all(child['ready'] for child in node['children'])
    finish(tree)
    return {'tree': tree, 'shopping': sorted(shopping.values(), key=lambda row: row['name']),
            'needed_ids': sorted(needed - {catalog['root']})}


def progress(key, fetch, catalog):
    jobs = [('Bank', '/account/bank', 'bank'), ('Shared inventory', '/account/inventory', 'shared'),
            ('Material storage', '/account/materials', 'materials'), ('Legendary Armory', '/account/legendaryarmory', 'armory'),
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
                return label, kind, data, None
            slots = [slot for bag in data['bags'] if bag for slot in bag['inventory']] if kind == 'bags' else data
            return label, kind, [slot for slot in slots if slot], None
        except Exception:
            return label, kind, [], f'{label} unavailable; its items are not counted.'

    holdings = defaultdict(int)
    locations = defaultdict(list)
    wallet = None
    acquisition_warnings = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        for label, kind, slots, warning in pool.map(read, jobs):
            if kind == 'wallet':
                if warning:
                    acquisition_warnings.append('Wallet unavailable. Enable wallet permission on your API key to compare currency costs.')
                else:
                    wallet = {row['id']: row['value'] for row in slots}
                continue
            if warning:
                warnings.append(warning)
            source_counts = defaultdict(int)
            for slot in slots:
                if kind == 'armory' and slot['id'] != catalog['root']:
                    continue  # Ownership is not a consumable crafting ingredient.
                holdings[slot['id']] += slot['count']
                source_counts[slot['id']] += slot['count']
            for item_id, count in source_counts.items():
                if count:
                    locations[item_id].append({'location': label, 'count': count, 'source': kind})
    result = allocate(holdings, catalog)
    def coverage(node):
        owned = node['allocated'] / node['required'] if node['required'] else 1
        return owned + (1 - owned) * (sum(coverage(child) for child in node['children']) / len(node['children']) if node['children'] else 0)
    result['coverage'] = (100 if result['tree']['ready'] else min(99.9, round(coverage(result['tree']) * 100, 1))) if result['tree']['children'] or result['tree']['allocated'] else None
    result['catalog'] = catalog
    result['wallet'] = wallet
    result['acquisition_warnings'] = acquisition_warnings
    result.update({'holdings': dict(holdings), 'locations': dict(locations), 'warnings': warnings,
                   'complete_scan': not warnings, 'checked_at': datetime.now(timezone.utc).isoformat()})
    return result

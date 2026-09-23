"""Request-local search for copies of an item; no private inventory caching."""
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote


def find(item_id, key, fetch):
    warnings = []
    jobs = [('Bank', '/account/bank', 'slots'),
            ('Shared inventory', '/account/inventory', 'slots'),
            ('Material storage', '/account/materials', 'materials')]
    try:
        names = fetch('/characters', key)
        jobs.extend((name, '/characters/' + quote(name, safe='') + '/inventory', 'bags') for name in names)
    except Exception:
        warnings.append('Character list unavailable; character bags were not searched.')

    def scan(job):
        name, path, kind = job
        try:
            data = fetch(path, key)
            if kind == 'bags':
                slots = [(slot, f'Bag {b + 1}, slot {s + 1}')
                         for b, bag in enumerate(data['bags']) if bag
                         for s, slot in enumerate(bag['inventory'])]
            else:
                slots = [(slot, 'Material storage' if kind == 'materials' else f'Slot {s + 1}')
                         for s, slot in enumerate(data)]
            rows = [{'location': name, 'slot': position, 'count': slot['count'],
                     'binding': slot.get('binding'), 'bound_to': slot.get('bound_to')}
                    for slot, position in slots if slot and slot['id'] == item_id and slot['count'] > 0]
            return rows, None
        except Exception:
            return [], f'{name}: unavailable; not included in the total.'

    locations = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        for rows, warning in pool.map(scan, jobs):
            locations.extend(rows)
            if warning:
                warnings.append(warning)
    return {'locations': locations, 'total': sum(row['count'] for row in locations), 'warnings': warnings}

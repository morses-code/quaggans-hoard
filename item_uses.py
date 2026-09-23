"""Look up actual recipe inputs independently of an item's category."""
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote
import time
from threading import Lock, BoundedSemaphore

PAGE_SIZE = 20
_recipe_ids = {}
_recipe_lock = Lock()
_recipe_slots = BoundedSemaphore(4)


def recipe_ids(item_id, fetch):
    with _recipe_lock:
        cached = _recipe_ids.get(item_id)
        if cached and time.monotonic() - cached[0] < 86400:
            return cached[1]
    with _recipe_slots:
        ids = sorted(set(fetch(f'/recipes/search?input={item_id}')))
    with _recipe_lock:
        _recipe_ids[item_id] = (time.monotonic(), ids)
    return ids


def crafting_summary(ids, fetch):
    def check(item_id):
        try:
            return str(item_id), {'count': len(recipe_ids(item_id, fetch))}
        except Exception:
            return str(item_id), {'error': 'Recipe lookup failed. Refresh to retry.'}
    with ThreadPoolExecutor(max_workers=4) as pool:
        return {'items': dict(pool.map(check, ids))}


def recipes(item_id, page, fetch):
    ids = recipe_ids(item_id, fetch)
    selected = ids[page * PAGE_SIZE:(page + 1) * PAGE_SIZE]
    details = fetch('/recipes?ids=' + ','.join(map(str, selected))) if selected else []
    names_needed = set()
    for recipe in details:
        if recipe.get('output_item_id'):
            names_needed.add(recipe['output_item_id'])
        for ingredient in recipe.get('ingredients', []):
            if ingredient.get('type', 'Item') == 'Item':
                names_needed.add(ingredient.get('item_id', ingredient.get('id')))
    names_needed.discard(None)
    names = {}
    ordered = sorted(names_needed)
    for offset in range(0, len(ordered), 200):
        names.update({i['id']: i['name'] for i in fetch('/items?ids=' + ','.join(map(str, ordered[offset:offset + 200])))})
    rows = []
    for recipe in details:
        ingredients = []
        for ingredient in recipe.get('ingredients', []):
            ingredient_id = ingredient.get('item_id', ingredient.get('id'))
            kind = ingredient.get('type', 'Item')
            ingredients.append({'name': names.get(ingredient_id, f'Item #{ingredient_id}') if kind == 'Item' else f'{kind} #{ingredient_id}',
                                'count': ingredient['count'], 'selected': kind == 'Item' and ingredient_id == item_id})
        output_id = recipe.get('output_item_id')
        rows.append({'id': recipe['id'], 'name': names.get(output_id, f'Output #{output_id}'),
                     'count': recipe.get('output_item_count', 1), 'ingredients': ingredients,
                     'disciplines': recipe.get('disciplines', []), 'rating': recipe.get('min_rating', 0),
                     'source': f'https://api.guildwars2.com/v2/recipes/{recipe["id"]}',
                     'wiki': 'https://wiki.guildwars2.com/wiki/Special:Search?search=' + quote(names.get(output_id, str(output_id)))})
    return {'total': len(ids), 'page': page, 'has_more': (page + 1) * PAGE_SIZE < len(ids), 'recipes': rows}


def storage(item_id, character, key, fetch):
    materials = fetch('/account/materials', key)
    match = next((m for m in materials if m['id'] == item_id), None)
    capacity = None
    try:
        capacity = fetch('/account', key).get('material_storage_slots')
    except Exception:
        pass
    bags = fetch('/characters/' + quote(character, safe='') + '/inventory', key)['bags']
    carried = sum(s['count'] for bag in bags if bag for s in bag['inventory'] if s and s['id'] == item_id)
    return storage_summary(carried, match['count'] if match else None, capacity, match is not None)


def storage_summary(carried, stored, capacity, eligible):
    known_capacity = isinstance(capacity, int) and capacity > 0
    room = max(0, capacity - stored) if eligible and known_capacity else None
    return {'carried': carried, 'stored': stored, 'capacity': capacity if known_capacity else None,
            'eligible': eligible, 'depositable': min(carried, room) if room is not None else None,
            'overflow': max(0, carried - room) if room is not None else None,
            'total': carried + stored if stored is not None else carried}


def lookup(item_id, page, character, key, fetch):
    result = {}
    with ThreadPoolExecutor(max_workers=2) as pool:
        work = {'crafting': pool.submit(recipes, item_id, page, fetch),
                'storage': pool.submit(storage, item_id, character, key, fetch)}
        for name, task in work.items():
            try:
                result[name] = task.result()
            except Exception:
                result[name] = {'error': f'{name.capitalize()} information is unavailable. Retry in a moment.'}
    return result

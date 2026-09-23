"""Live legendary equipment catalogue and conservative, bounded recipe imports."""
import re
import time
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote
import wiki_acquisition as wiki
import legendary


def catalogue(fetch):
    def read():
        armory = fetch('/legendaryarmory?ids=all')
        limits = {row['id']: row['max_count'] for row in armory}
        ids = sorted(limits)
        items = []
        for offset in range(0, len(ids), 200):
            items.extend(fetch('/items?ids=' + ','.join(map(str, ids[offset:offset + 200]))))
        return sorted([{'id': item['id'], 'name': item['name'], 'icon': item.get('icon'),
                        'type': item['type'], 'subtype': item.get('details', {}).get('type', ''),
                        'weight': item.get('details', {}).get('weight_class', ''),
                        'max_count': limits[item['id']]} for item in items], key=lambda item: item['name'])
    return wiki.cached('legendary-catalogue', read)


def achievement_links(fetch):
    def read():
        categories = fetch('/achievements/categories?ids=all')
        ids = sorted({i for c in categories if 'legendary' in c['name'].lower() for i in c['achievements']})
        achievements = []
        for offset in range(0, len(ids), 200):
            achievements.extend(fetch('/achievements?ids=' + ','.join(map(str, ids[offset:offset + 200]))))
        def normalized(name):
            return re.sub(r'[^a-z0-9]+', ' ', name.casefold()).strip().removeprefix('the ')
        links = {}
        for item in catalogue(fetch):
            name = normalized(item['name'])
            matches = []
            direct = []
            dedicated = {i for c in categories if ':' in c['name'] and normalized(c['name'].split(':', 1)[1]) == name for i in c['achievements']}
            for achievement in achievements:
                if 'Repeatable' in achievement.get('flags', []): continue
                title = normalized(achievement['name'])
                reward = any(r.get('type') == 'Item' and r.get('id') == item['id'] for r in achievement.get('rewards', []))
                # Name-bound collection series or an explicit item reward only.
                suffix = title[len(name):].strip() if title.startswith(name + ' ') else None
                series = title == name or suffix is not None and re.match(r'^(?:[ivx]+\b|[0-9]+\b|awakening\b)', suffix)
                primary = ':' in achievement['name'] and achievement['name'].lower().startswith('legendary ') and normalized(achievement['name'].split(':', 1)[1]) == name
                if reward or series or primary or achievement['id'] in dedicated:
                    maximum = max((tier['count'] for tier in achievement.get('tiers', [])), default=0)
                    if maximum > 0:
                        row = {'id': achievement['id'], 'name': achievement['name'], 'max': maximum}
                        matches.append(row)
                        if primary: direct.append(row)
            links[str(item['id'])] = direct or matches
        return links
    return wiki.cached('legendary-achievement-links', read)


def collection_progress(key, fetch):
    links = achievement_links(fetch)
    warnings = []
    account = None
    owned = {}
    try:
        account = {a['id']: a for a in fetch('/account/achievements', key)}
    except Exception:
        warnings.append('Achievement progress is unavailable. Check progression permission and retry.')
    try:
        owned = {item['id']: item['count'] for item in fetch('/account/legendaryarmory', key)}
    except Exception:
        warnings.append('Legendary Armory ownership could not be checked.')
    results = {}
    for item_id, achievements in links.items():
        maximum = sum(a['max'] for a in achievements)
        current = None
        if account is not None and maximum:
            current = sum(a['max'] if account.get(a['id'], {}).get('done') else min(a['max'], max(0, account.get(a['id'], {}).get('current', 0))) for a in achievements)
        results[item_id] = {'owned': owned.get(int(item_id), 0), 'current': current, 'max': maximum,
                            'percent': (100 if current == maximum else min(99, round(current / maximum * 100))) if current is not None else None,
                            'achievements': achievements}
    return {'items': results, 'warnings': warnings, 'checked_at': datetime.now(timezone.utc).isoformat()}


def recipe_options(text):
    """Explicit, deterministic, single-output acquisition recipes."""
    section = re.search(r'^==\s*Acquisition\s*==\s*$(.*?)(?=^==[^=]|\Z)', text, re.M | re.S | re.I)
    if not section:
        return []
    recipes = re.findall(r'\{\{recipe\s*\n(.*?)\}\}', section[1], re.S | re.I)
    options = []
    for recipe in recipes:
        if '{{' in recipe: return []
        fields = dict((k.strip().lower(), v.strip()) for k, v in re.findall(r'^\s*\|\s*([^=\n]+)=(.*)$', recipe, re.M))
        if fields.get('quantity', '1') != '1' or fields.get('source', '').lower() != 'mystic forge': return []
        if any(word in recipe.lower() for word in ('chance', 'random', '%', 'output', 'requires')): return []
        parts = []
        for field, value in fields.items():
            if field.startswith('ingredient'):
                if not re.fullmatch(r'ingredient\d+', field): return []
                match = re.fullmatch(r'([1-9]\d*)\s+([^{}|<>\n]+)', value)
                if not match: return []
                parts.append({'count': int(match[1]), 'name': match[2].strip()})
        if not 1 <= len(parts) <= 4: return []
        if parts not in options: options.append(parts)
    return options


def recipe_parts(text):
    options = recipe_options(text)
    return options[0] if len(options) == 1 else []


def definition(item_id, fetch, route=0):
    if not 0 <= route < 32: raise ValueError('Choose a valid recipe route.')
    if item_id == legendary.CATALOG['root']:
        if route: raise ValueError('Choose a valid recipe route.')
        return legendary.CATALOG
    if item_id not in {row['id'] for row in catalogue(fetch)}:
        raise ValueError('Choose an item from the legendary catalogue.')

    def read():
        nodes = {}
        routes = []
        deadline = time.monotonic() + 35
        def api_item(item_id):
            return wiki.cached(('project-item', item_id), lambda: fetch('/items/' + str(item_id)))

        def add(item_id, depth, path):
            if str(item_id) in nodes: return
            if str(item_id) in legendary.CATALOG['nodes']:
                node = legendary.CATALOG['nodes'][str(item_id)]
                nodes[str(item_id)] = node
                for part in node['ingredients']: add(part['id'], depth, path | {item_id})
                return
            item = api_item(item_id)
            node = {'id': item_id, 'name': item['name'], 'icon': item.get('icon'),
                    'source': wiki.WIKI + '/wiki/' + quote(item['name'].replace(' ', '_'), safe=''),
                    'ingredients': [], 'note': 'Obtain this item directly; its crafting steps are not expanded. Open acquisition details for methods and requirements.'}
            nodes[str(item_id)] = node
            # Tradable materials/precursors are acquisition targets, not assumed crafting routes.
            if depth >= 3 or len(nodes) >= 48 or time.monotonic() >= deadline or (depth and item.get('rarity') != 'Legendary' and not {'AccountBound', 'SoulbindOnAcquire'}.intersection(item.get('flags', []))):
                return
            try:
                page = wiki.page(item['name'])
                if item_id not in wiki.item_ids(page['wikitext']['*']): return
                options = recipe_options(page['wikitext']['*'])
                if depth == 0 and options:
                    routes.extend({'id': i, 'label': ' + '.join(f"{p['count']} {p['name']}" for p in option)} for i, option in enumerate(options))
                    if route >= len(options): raise ValueError('Unknown recipe route')
                    parts = options[route]
                else:
                    if len(options) > 1:
                        node['note'] = 'Multiple crafting recipes are available. Open this legendary separately to choose its recipe, or obtain this component directly.'
                        return
                    parts = options[0] if options else []
                def resolve(part):
                    ids = wiki.item_ids(wiki.page(part['name'])['wikitext']['*'])
                    if len(ids) != 1: raise ValueError('Ambiguous ingredient')
                    resolved = next(iter(ids))
                    if resolved in path or resolved == item_id: raise ValueError('Recipe cycle')
                    return {'id': resolved, 'count': part['count']}
                if parts:
                    with ThreadPoolExecutor(max_workers=4) as pool:
                        ingredients = list(pool.map(resolve, parts))
                else:
                    recipe_ids = wiki.cached(('project-recipes', item_id), lambda: fetch('/recipes/search?output=' + str(item_id)))
                    if not recipe_ids or len(recipe_ids) > 12: return
                    recipes = wiki.cached(('project-recipe-details', item_id), lambda: fetch('/recipes?ids=' + ','.join(map(str, recipe_ids))))
                    api_routes = set()
                    for recipe in recipes:
                        if recipe.get('output_item_id') != item_id or recipe.get('output_item_count') != 1: return
                        if recipe.get('guild_ingredients') or any(p.get('type', 'Item') != 'Item' for p in recipe['ingredients']): return
                        api_routes.add(tuple(sorted((p.get('item_id', p.get('id')), p['count']) for p in recipe['ingredients'])))
                    api_routes = sorted(api_routes)
                    if depth == 0:
                        routes.extend({'id': index, 'label': ' + '.join(f"{count} {api_item(i)['name']}" for i, count in parts)} for index, parts in enumerate(api_routes))
                        if route >= len(api_routes): return
                    elif len(api_routes) != 1:
                        node['note'] = 'Multiple crafting recipes are available; this component remains a direct acquisition target.'
                        return
                    ingredients = [{'id': i, 'count': count} for i, count in api_routes[route if depth == 0 else 0]]
                    if not ingredients or any(not p['id'] or p['id'] in path or p['id'] == item_id or p['count'] <= 0 for p in ingredients): return
                for part in ingredients: add(part['id'], depth + 1, path | {item_id})
                node.update(ingredients=ingredients, note='Recipe imported from public game data. Check unlocks and crafting requirements in game.', revision=page['revid'])
            except Exception:
                return  # Unverified steps remain explicit acquisition targets.
        add(item_id, 0, set())
        if route and (not routes or route >= len(routes)): raise ValueError('Choose a valid recipe route.')
        return {'root': item_id, 'name': nodes[str(item_id)]['name'], 'nodes': nodes,
                'routes': routes, 'selected_route': route,
                'scope': 'Progress applies to the selected recipe. Armory weapons cannot be spent as ingredients. Unexpanded subrecipes remain acquisition targets.'}
    return wiki.cached(('legendary-definition', item_id, route), read)

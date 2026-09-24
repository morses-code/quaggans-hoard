"""Conservative, source-backed collection cleanup guidance."""
import json
import time
from datetime import datetime, timezone
from threading import Lock
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote
from collections import defaultdict
from math import ceil
from item_uses import storage_summary

_catalog = None
_catalog_at = 0
_lock = Lock()
MAX_AGE = 86400
COLLECTION_ONLY = 'This item only has value as part of a collection.'
COMMUNITY_SOURCE = 'https://github.com/zwei2stein/gw2stacks/blob/main/data/model.py'


def catalog(fetch):
    global _catalog, _catalog_at
    with _lock:
        if _catalog is not None and time.monotonic() - _catalog_at < MAX_AGE:
            return _catalog
        ids = fetch('/achievements')
        chunks = [ids[i:i + 200] for i in range(0, len(ids), 200)]
        result = []
        with ThreadPoolExecutor(max_workers=4) as pool:
            for batch in pool.map(lambda chunk: fetch('/achievements?ids=' + ','.join(map(str, chunk))), chunks):
                result.extend(batch)
        # A partial catalog must never support a disposal recommendation.
        if {a['id'] for a in result} != set(ids):
            raise ValueError('Incomplete achievement catalog')
        _catalog, _catalog_at = result, time.monotonic()
        return result


def evaluate(item_ids, achievements, progress, items, checked_at):
    account = {a['id']: a for a in progress}
    matches = {str(i): [] for i in item_ids}
    for achievement in achievements:
        for index, bit in enumerate(achievement.get('bits', [])):
            item_id = str(bit.get('id'))
            if bit.get('type') != 'Item' or item_id not in matches:
                continue
            state = account.get(achievement['id'], {})
            repeatable = bool(set(achievement.get('flags', [])) & {'Repeatable', 'Daily', 'Weekly', 'Monthly'})
            credited = state.get('done') is True or index in state.get('bits', [])
            matches[item_id].append({
                'id': achievement['id'], 'name': achievement['name'], 'bit': index,
                'credited': credited, 'repeatable': repeatable,
                'url': 'https://wiki.guildwars2.com/wiki/Special:Search?search=' + quote(achievement['name']),
            })
    result = {}
    for item_id, collections in matches.items():
        item = items.get(item_id, {})
        status = 'check'
        reason = 'No verified disposal rule for this item. Collection credit alone does not establish that it has no other uses.'
        if not collections:
            reason = 'No direct item-to-collection mapping is available. This does not mean the item is unused or safe to discard.'
        elif any(not c['credited'] for c in collections):
            reason = 'Collection credit is not confirmed for every mapped objective. Keep for now and check in game; API updates can be delayed.'
            status = 'keep'
        elif any(c['repeatable'] for c in collections):
            reason = 'This item is linked to a repeatable or resetting achievement. It needs manual review.'
        elif item.get('type') == 'Trophy' and item.get('description', '').strip() == COLLECTION_ONLY:
            status = 'safe'
            reason = 'The official item description explicitly says it is collection-only, and credit is confirmed for every directly mapped objective. This is not inferred merely from its Trophy type.'
        result[item_id] = {
            'status': status, 'reason': reason, 'collections': collections,
            'checked_at': checked_at,
            'wiki': 'https://wiki.guildwars2.com/wiki/Special:Search?search=' + quote(item.get('chat_link') or item.get('name') or item_id),
        }
    return result


def add_actions(results, items, bags=None, materials=None, storage_limit=None):
    """Suggestions are separate from the stricter disposal verdict."""
    slots = defaultdict(list)
    for bag_index, bag in enumerate(bags or []):
        if bag:
            for slot_index, slot in enumerate(bag['inventory']):
                if slot:
                    slots[str(slot['id'])].append((slot, f'Bag {bag_index + 1}, slot {slot_index + 1}'))
    stored = {str(m['id']): m['count'] for m in materials or []}
    for item_id, result in results.items():
        item = items.get(item_id, {})
        flags = item.get('flags', [])
        actions = result['actions'] = []
        carried = sum(s['count'] for s, _ in slots[item_id])
        result['storage'] = storage_summary(carried, stored.get(item_id), storage_limit, item_id in stored) if materials is not None else None

        def action(kind, label, reason, evidence='Conditional advice', source=None):
            actions.append({'kind': kind, 'label': label, 'reason': reason, 'evidence': evidence,
                            'source': source or f'https://api.guildwars2.com/v2/items/{item_id}'})

        if item_id in stored:
            if isinstance(storage_limit, int) and storage_limit > 0:
                room = max(0, storage_limit - stored[item_id])
                if room:
                    quantity = sum(s['count'] for s, _ in slots[item_id])
                    amount = min(quantity, room) if quantity else room
                    action('deposit', 'Deposit materials', f'Material storage has room for {room}. Deposit up to {amount} from these bags; the materials remain yours.', 'API checked')
                else:
                    result['storage_note'] = 'Material storage is full for this item. Keep it, use it, or review its market value; do not discard just because storage is full.'
            else:
                action('deposit', 'Deposit materials if there is room', 'This item has a material-storage slot. Use Deposit All Materials; remaining capacity could not be verified.')

        groups = defaultdict(list)
        for slot, location in slots[item_id]:
            # Require identical binding, upgrades, stats, and all other slot metadata.
            signature = json.dumps({k: v for k, v in slot.items() if k != 'count'}, sort_keys=True)
            groups[signature].append((slot, location))
        for group in groups.values():
            counts = [slot['count'] for slot, _ in group]
            # A real stack proves this variant stacks; never guess from item type.
            if len(counts) > 1 and any(c > 1 for c in counts) and all(0 < c <= 250 for c in counts):
                freed = len(counts) - ceil(sum(counts) / 250)
                if freed > 0:
                    locations = '; '.join(f'{location} ({slot["count"]})' for slot, location in group)
                    action('combine', 'Combine stacks', f'Merge matching stacks to free {freed} slot(s), assuming the usual 250 stack limit. {locations}.', 'Inventory checked', 'https://wiki.guildwars2.com/wiki/Inventory')

        blocked = result['status'] == 'keep' or any(c['repeatable'] for c in result['collections'])
        if result['status'] == 'safe':
            if item.get('vendor_value', 0) > 0 and 'NoSell' not in flags:
                action('vendor', 'Sell collection item', f'Collection credit confirmed. Vendor value: {item["vendor_value"]} copper each. Sell instead of destroying the value.', 'Collection credit + explicit description')
            else:
                action('discard', 'Discard collection item', 'Collection credit confirmed and the description explicitly identifies this as collection-only.', 'Collection credit + explicit description')
        elif not blocked and item.get('rarity') == 'Junk' and item.get('vendor_value', 0) > 0 and 'NoSell' not in flags:
            action('vendor', 'Sell junk to a vendor', f'The API labels this as Junk with a vendor value of {item["vendor_value"]} copper each. Check the linked wiki if you are saving it for a specific use.', 'Community advice', COMMUNITY_SOURCE)
        if not blocked and result['status'] != 'safe':
            if item.get('description', '').strip() == 'Salvage Item' and item.get('type') in ('Trophy', 'CraftingMaterial') and item_id != '19721' and 'NoSalvage' not in flags and item_id not in stored:
                action('salvage', 'Consider salvaging', 'The API explicitly labels this a salvage item. Use an appropriate kit; review its wiki or sale value first. This is not a recommendation to salvage equipment or ectoplasm.', 'Community advice', COMMUNITY_SOURCE)
            if item.get('type') == 'Consumable' and item.get('details', {}).get('type') == 'Currency':
                action('consume', 'Consume for currency', 'This is a currency consumable. Check its description, any currency cap, and alternative uses before consuming. Save it if you need the physical item for a recipe or exchange.', 'Conditional advice')
        if result['status'] == 'keep':
            action('keep', 'Keep for now', result['reason'], 'Collection check')
        if not actions:
            action('check', 'Needs checking', result['reason'], 'Unresolved')
        result['primary_action'] = actions[0]['kind']
    return results


def analyze(item_ids, key, fetch, character=None):
    # Independent sources degrade independently; unavailable progress is never credit.
    warnings = []
    achievements, progress = [], []
    try:
        progress = fetch('/account/achievements', key)
        achievements = catalog(fetch)
    except Exception:
        warnings.append('Collection checks unavailable. Enable progression permission or retry later; no collection disposal is approved.')
        achievements, progress = [], []
    checked_at = datetime.now(timezone.utc).isoformat()
    bags = None
    if character:
        bags = fetch('/characters/' + quote(character, safe='') + '/inventory', key)['bags']
        item_ids = sorted({slot['id'] for bag in bags if bag for slot in bag['inventory'] if slot})
    items = {}
    for offset in range(0, len(item_ids), 200):
        batch = fetch('/items?ids=' + ','.join(map(str, item_ids[offset:offset + 200])))
        items.update({str(i['id']): i for i in batch})
    materials, storage_limit = None, None
    try:
        materials = fetch('/account/materials', key)
        storage_limit = fetch('/account', key).get('material_storage_slots')
    except Exception:
        warnings.append('Material storage capacity could not be fully checked. Other advice is still available.')
    results = evaluate(item_ids, achievements, progress, items, checked_at)
    for result in results.values():
        result['collections_available'] = bool(achievements)
    add_actions(results, items, bags, materials, storage_limit)
    # Keep account contents request-local. A failed source is unknown, never zero.
    with ThreadPoolExecutor(max_workers=2) as pool:
        sources = {name: pool.submit(fetch, path, key) for name, path in
                   [('bank', '/account/bank'), ('shared', '/account/inventory')]}
        for name, task in sources.items():
            totals = None
            try:
                totals = defaultdict(int)
                for slot in task.result():
                    if slot:
                        totals[str(slot['id'])] += slot['count']
            except Exception:
                totals = None
                warnings.append(f'{name.capitalize()} inventory unavailable. Copies there could not be checked.')
            for item_id, result in results.items():
                result.setdefault('elsewhere', {})[name] = totals[item_id] if totals is not None else None
    return {'items': results, 'checked_at': checked_at, 'warnings': warnings}

"""Public, cached wiki acquisition data. No account credentials reach the wiki."""
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from html.parser import HTMLParser
from threading import BoundedSemaphore, Lock
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

WIKI = 'https://wiki.guildwars2.com'
_cache = {}
_lock = Lock()
_slots = BoundedSemaphore(2)


def cached(key, read):
    with _lock:
        hit = _cache.get(key)
        if hit and hit[0] > time.monotonic():
            return hit[1]
    value = read()  # Failures are retryable; never cache account data.
    with _lock:
        if len(_cache) >= 512:
            _cache.clear()
        _cache[key] = (time.monotonic() + 21600, value)
    return value


def page(title):
    def read():
        url = WIKI + '/api.php?' + urlencode(dict(action='parse', page=title,
              prop='text|wikitext|revid', redirects=1, format='json'))
        with _slots, urlopen(Request(url, headers={'User-Agent': 'QuaggansHoard/1.0'}), timeout=12) as response:
            raw = response.read(4_000_001)
        if len(raw) > 4_000_000:
            raise ValueError('Wiki page is too large to import.')
        result = json.loads(raw)
        if 'parse' not in result:
            raise ValueError('No matching wiki page was found.')
        return result['parse']
    return cached(('page', title), read)


def item_ids(wikitext):
    # Only the item infobox, including balanced nested templates.
    match = re.search(r'\{\{\s*(?:Item|Weapon|Armor|Trinket|Back item|Upgrade component|Gathering tool) infobox\b', wikitext, re.I)
    if not match:
        return set()
    tail = wikitext[match.end():]
    depth, end = 1, len(tail)
    for token in re.finditer(r'\{\{|\}\}', tail):
        depth += 1 if token[0] == '{{' else -1
        if depth == 0:
            end = token.start()
            break
    field = re.search(r'^\s*\|\s*id\s*=\s*([\d,; ]+)\s*$', tail[:end], re.M | re.I)
    return set(map(int, re.findall(r'\d+', field[1]))) if field else set()


class Node:
    def __init__(self, tag='', attrs=()):
        self.tag, self.attrs, self.children = tag, dict(attrs), []

    def find(self, tags):
        for child in self.children:
            if isinstance(child, Node):
                if child.tag in tags:
                    yield child
                yield from child.find(tags)

    def text(self, icons=True):
        classes = self.attrs.get('class', '').split()
        if self.tag in ('script', 'style', 'sup') or any(c in classes for c in ('mw-editsection', 'hide', 'sortkey')) or 'display:none' in self.attrs.get('style', '').replace(' ', ''):
            return ''
        if self.tag == 'img':
            return (' ' + self.attrs.get('alt', '').removesuffix('.png') + ' ') if icons else ''
        if self.tag == 'br':
            return ' / '
        text = ''.join(c.text(icons) if isinstance(c, Node) else c for c in self.children)
        text = re.sub(r'[^\S\n]+', ' ', text)
        return ('\n' + text.strip() + '\n') if self.tag in ('li', 'dt', 'dd') else text


class Document(HTMLParser):
    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.root = Node()
        self.stack = [self.root]
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        node = Node(tag, attrs)
        self.stack[-1].children.append(node)
        if tag not in ('img', 'br', 'hr', 'input', 'link', 'meta', 'wbr', 'source'):
            self.stack.append(node)

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                break

    def handle_data(self, data):
        self.stack[-1].children.append(re.sub(r'\s+', ' ', data))


def cost_parts(cell):
    """Accept only complete sums of positive integer quantities and named icons."""
    resources = []
    def tokens(node):
        if isinstance(node, str):
            return node
        if node.tag == 'a':
            title = node.attrs.get('title', '')
            if not node.attrs.get('href', '').startswith('/wiki/') or not title:
                return '?'
            resources.append(title)
            return f' @{len(resources)-1} '
        if 'price' in node.attrs.get('class', '').split():
            value = node.attrs.get('data-sort-value', '')
            if value.isdigit() and int(value) > 0:
                resources.append('Coin')
                return f'{value} @{len(resources)-1}'
            return '?'
        return ''.join(tokens(c) for c in node.children)
    raw = tokens(cell).strip()
    result = []
    for part in raw.split('+'):
        match = re.fullmatch(r'\s*([\d,]+)\s+@(\d+)\s*', part)
        if not match or not re.fullmatch(r'(?:\d+|\d{1,3}(?:,\d{3})+)', match[1]):
            return []
        count = int(match[1].replace(',', ''))
        if count <= 0:
            return []
        result.append({'name': resources[int(match[2])], 'count': count})
    return result


def extract(html):
    root = Document(html).root
    sections, vendors = [], []
    active, section = False, None
    def walk(node):
        nonlocal active, section
        if node.tag == 'h2':
            active = node.text(False).strip().lower() in ('acquisition', 'notes')
            section = None
        if not active:
            for child in node.children:
                if isinstance(child, Node): walk(child)
            return
        if node.tag in ('h2', 'h3', 'h4'):
            section = {'title': node.text(False).strip(), 'blocks': []}
            sections.append(section)
            return
        if node.tag == 'table':
            rows = []
            spans = []
            header = None
            # Spanned tables remain readable, but never used for cost arithmetic.
            complex_table = any(c.attrs.get('rowspan', '1') != '1' or c.attrs.get('colspan', '1') != '1' for c in node.find(('td', 'th')))
            for tr in node.find(('tr',)):
                cells = [c for c in tr.children if isinstance(c, Node) and c.tag in ('td', 'th')]
                if not cells: continue
                texts = [c.text() for c in cells]
                rows.append(texts)
                def span(cell, name):
                    value = cell.attrs.get(name, '1')
                    return min(1000, max(1, int(value))) if value.isdigit() else 1
                spans.append([{'colspan': span(c, 'colspan'), 'rowspan': span(c, 'rowspan'), 'header': c.tag == 'th'} for c in cells])
                if all(c.tag == 'th' for c in cells):
                    header = [c.text(False).strip().lower() for c in cells]
                elif not complex_table and header and 'vendor' in header and 'cost' in header and set(header) <= {'vendor', 'area', 'zone', 'cost', 'notes'} and len(cells) == len(header):
                    values = dict(zip(header, cells))
                    notes = values.get('notes', Node()).text().strip()
                    limit = re.search(r'\bLimit ([\d,]+) per (day|week|season)\.', notes)
                    vendors.append({'vendor': values['vendor'].text(False).strip(),
                        'area': ' / '.join(values[k].text(False) for k in ('area', 'zone') if k in values),
                        'condition': notes, 'raw_cost': values['cost'].text(),
                        'parts': cost_parts(values['cost']), 'output': 1,
                        'limit': int(limit[1].replace(',', '')) if limit else None,
                        'period': limit[2] if limit else None})
            section['blocks'].append({'kind': 'table', 'rows': rows, 'spans': spans})
            return
        if node.tag in ('p', 'ul', 'ol', 'dl'):
            text = node.text()
            if text: section['blocks'].append({'kind': 'text', 'text': text})
            return
        for child in node.children:
            if isinstance(child, Node): walk(child)
    walk(root)
    return [s for s in sections if s['blocks']], vendors


def lookup(item_id, fetch):
    def read():
        item = fetch('/items/' + str(item_id))
        data = page(item['name'])
        if item_id not in item_ids(data['wikitext']['*']):
            raise ValueError('The wiki page could not be matched to this exact item. No acquisition advice was imported.')
        sections, vendors = extract(data['text']['*'])
        source = WIKI + '/wiki/' + quote(data['title'].replace(' ', '_'), safe='')
        resources = {}
        names = sorted({p['name'] for v in vendors for p in v['parts']})
        currencies = cached('currencies', lambda: fetch('/currencies?ids=all')) if names else []
        def resolve(name):
            try:
                matches = [c for c in currencies if c['name'].casefold().rstrip('s') == name.casefold().rstrip('s')]
                if len(matches) == 1:
                    return name, {**matches[0], 'kind': 'currency'}
                ids = item_ids(page(name)['wikitext']['*'])
                if len(ids) == 1:
                    item = cached(('item', next(iter(ids))), lambda: fetch('/items/' + str(next(iter(ids)))))
                    return name, {**item, 'kind': 'item'}
            except Exception:
                pass  # Preserve raw cost; unknown identities disable arithmetic.
            return name, None
        with ThreadPoolExecutor(max_workers=2) as pool:
            for name, resource in pool.map(resolve, names[:24]):
                if resource: resources[name] = resource
        offers = []
        for vendor in vendors:
            parts = vendor.pop('parts')
            if parts and all(p['name'] in resources for p in parts):
                # Repeated resources would require summing before budgeting; keep textual for now.
                if len({(resources[p['name']]['kind'], resources[p['name']]['id']) for p in parts}) == len(parts):
                    offers.append({**vendor, 'costs': [{**resources[p['name']], 'per_trade': p['count']} for p in parts], 'source': source + '#Acquisition'})
        return {'id': item_id, 'name': item['name'], 'sections': sections, 'offers': offers,
                'source': source, 'revision': data['revid'], 'checked_at': datetime.now(timezone.utc).isoformat(),
                'unparsed_offers': len(vendors) - len(offers)}
    return cached(('acquisition', item_id), read)

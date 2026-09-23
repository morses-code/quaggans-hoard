"""Read item Notes through the GW2 Wiki's rendered-page API."""
import json
import re
import time
from datetime import datetime, timezone
from html.parser import HTMLParser
from concurrent.futures import ThreadPoolExecutor
from threading import Lock, BoundedSemaphore
from urllib.parse import urlencode, quote
from urllib.request import Request, urlopen

_cache = {}
_lock = Lock()
_slots = BoundedSemaphore(2)
SAFE_NOTE = re.compile(r'(?:this item |it )?(?:can|may) be safely (?:destroyed|discarded|deleted|sold(?: to vendors)?)(?: after (?:acquisition|acquiring it))?\.', re.I)
READING_NOTE = re.compile(
    r'(?:other than|apart from) to (?:access|read) (?:the )?collected pages '
    r'before acquiring the completed (?:journal|book), '
    r'(?:this item|it) (?:can|may) be safely (?:destroyed|discarded|deleted)\.', re.I)
READING_CAVEAT = ('Destroying this item removes access to its collected pages until you acquire '
                  'the completed book. Keep it if you want to read those pages now.')


class NotesParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.ids = set()
        self.notes = []
        self.in_notes = False
        self.heading = False
        self.heading_text = []
        self.block = None
        self.parts = []
        self.ignore = 0
        self.infobox = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'div':
            if self.infobox:
                self.infobox += 1
            elif {'infobox', 'item'}.issubset(set(attrs.get('class', '').split())):
                self.infobox = 1
        if self.infobox and attrs.get('data-type') == 'item' and attrs.get('data-id', '').isdigit():
            self.ids.add(int(attrs['data-id']))
        if tag in ('script', 'style', 'table'):
            self.ignore += 1
        if self.ignore:
            return
        if tag == 'h2':
            self.finish_block()
            self.in_notes = False
            self.heading = True
            self.heading_text = []
        if tag == 'hr':
            self.finish_block()
            self.in_notes = False
        if self.in_notes and tag in ('li', 'p') and self.block is None:
            self.block = tag
            self.parts = []
        if tag == 'br' and self.block:
            self.parts.append(' ')

    def handle_endtag(self, tag):
        if tag == 'div' and self.infobox:
            self.infobox -= 1
        if tag in ('script', 'style', 'table') and self.ignore:
            self.ignore -= 1
            return
        if self.ignore:
            return
        if tag == 'h2':
            self.heading = False
            text = ''.join(self.heading_text).strip()
            self.in_notes = re.sub(r'\[edit\]', '', text, flags=re.I).strip().lower() == 'notes'
        if tag == self.block:
            self.finish_block()

    def handle_data(self, data):
        if self.ignore:
            return
        if self.heading:
            self.heading_text.append(data)
        if self.block:
            self.parts.append(data)

    def finish_block(self):
        if self.block:
            text = ' '.join(''.join(self.parts).split())
            if text:
                self.notes.append(text)
        self.block = None
        self.parts = []


def parse_page(item_id, data):
    page = data['parse']
    parser = NotesParser()
    parser.feed(page['text']['*'])
    parser.finish_block()
    url = 'https://wiki.guildwars2.com/wiki/' + quote(page['title'].replace(' ', '_'), safe='') + '#Notes'
    if parser.ids != {item_id}:
        return {'state': 'unverified', 'notes': [], 'source': url,
                'message': 'The wiki page could not be matched uniquely to this item ID. Review it manually.'}
    notes = parser.notes
    # Recognize full statements, including a specific optional reading-access trade-off.
    # This depends on the Notes text, never on an item-specific disposal allowlist.
    # Multiple notes or additional qualifications require manual review of context.
    explicit = len(notes) == 1 and SAFE_NOTE.fullmatch(notes[0]) is not None
    reading_tradeoff = len(notes) == 1 and READING_NOTE.fullmatch(notes[0]) is not None
    explicit = explicit or reading_tradeoff
    relevant = any(re.search(r'\b(destroy|discard|delete|sell|sold|keep|retain)\w*\b', note, re.I) for note in notes)
    return {'state': 'explicit' if explicit else 'review' if relevant else 'notes' if notes else 'none',
            'notes': notes, 'source': url, 'revision': page.get('revid'),
            'revision_source': 'https://wiki.guildwars2.com/index.php?' + urlencode({'oldid': page['revid']}) + '#Notes' if page.get('revid') else url,
            'checked_at': datetime.now(timezone.utc).isoformat(),
            'reviewed_caveat': READING_CAVEAT if reading_tradeoff else None,
            'message': ('The wiki permits disposal with a reading-access trade-off. ' + READING_CAVEAT) if reading_tradeoff else 'The wiki explicitly permits disposal. Recipe and collection checks still apply.' if explicit else 'Review these notes and any conditions before discarding.' if relevant else 'No explicit disposal guidance found in Notes.'}


def lookup(item_id, name):
    with _lock:
        cached = _cache.get(item_id)
        if cached and time.monotonic() < cached[0]:
            return cached[1]
    try:
        url = 'https://wiki.guildwars2.com/api.php?' + urlencode({'action': 'parse', 'page': name, 'prop': 'text|revid', 'format': 'json', 'redirects': 1})
        with _slots:
            request = Request(url, headers={'User-Agent': 'TyriaInventory/1.0 (local read-only item notes viewer)'})
            with urlopen(request, timeout=12) as response:
                data = json.load(response)
        result = parse_page(item_id, data)
        ttl = 21600
    except Exception:
        result = {'state': 'unavailable', 'notes': [], 'message': 'Wiki Notes could not be checked. No disposal approval was inferred.',
                  'source': 'https://wiki.guildwars2.com/wiki/' + quote(name.replace(' ', '_'), safe='') + '#Notes'}
        ttl = 60
    with _lock:
        _cache[item_id] = (time.monotonic() + ttl, result)
    return result


def summary(ids, fetch):
    items = fetch('/items?ids=' + ','.join(map(str, ids)))
    with ThreadPoolExecutor(max_workers=2) as pool:
        pairs = pool.map(lambda item: (str(item['id']), lookup(item['id'], item['name'])), items)
        return {'items': dict(pairs)}

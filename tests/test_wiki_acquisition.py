import unittest
from unittest.mock import patch
import wiki_acquisition as wiki


HTML = '''<h2><span>Acquisition</span><span class="mw-editsection">[edit]</span></h2>
<p>Earn from <b>reward tracks</b>. <script>bad()</script></p>
<h3>Sold by</h3><p>These vendors share their weekly limit.</p>
<table><tr><th>Vendor</th><th>Cost</th><th>Notes</th></tr>
<tr><td><a>Example vendor</a></td><td>2 <a href="/wiki/Input" title="Input"><img alt="Input"></a> + 50 <a href="/wiki/Token" title="Token"><img alt="Token"></a></td><td>Limit 10 per week.</td></tr></table>
<h3>Reward tracks</h3><table><tr><th>Track</th><th>Repeatable</th></tr>
<tr><td>Example track</td><td><span class="hide">1</span><img alt="Yes"></td></tr></table>
<h2>Used in</h2><p>Do not import this.</p><h2>Notes</h2><p>Requires an unlock.</p>'''


class AcquisitionTests(unittest.TestCase):
    def setUp(self):
        wiki._cache.clear()

    def test_acquisition_notes_tables_and_hidden_markup(self):
        sections, offers = wiki.extract(HTML)
        text = str(sections)
        self.assertIn('reward tracks', text)
        self.assertIn('Requires an unlock.', text)
        self.assertNotIn('Do not import', text)
        self.assertNotIn('bad()', text)
        self.assertNotIn('[edit]', text)
        repeatable = sections[2]['blocks'][0]['rows'][1][1].strip()
        self.assertEqual(repeatable, 'Yes')
        self.assertEqual(offers[0]['parts'], [{'name': 'Input', 'count': 2}, {'name': 'Token', 'count': 50}])
        self.assertEqual(offers[0]['limit'], 10)

    def test_unknown_cost_never_partially_budgeted(self):
        for cost in ['2 <a href="/wiki/Input" title="Input">Input</a> + unknown fee',
                     '10 for 2 <a href="/wiki/Input" title="Input">Input</a>',
                     '0 <a href="/wiki/Input" title="Input">Input</a>',
                     '2 <a href="https://example.com/" title="Input">Input</a>']:
            cell = wiki.Document('<td>' + cost + '</td>').root.children[0]
            self.assertEqual(wiki.cost_parts(cell), [])

    def test_coin_uses_copper_value(self):
        cell = wiki.Document('<td><span class="price" data-sort-value="10203">1 gold 2 silver 3 copper</span></td>').root.children[0]
        self.assertEqual(wiki.cost_parts(cell), [{'name': 'Coin', 'count': 10203}])

    def test_infobox_id_scoped_and_multiple_variants(self):
        self.assertEqual(wiki.item_ids('{{Item infobox\n| description = {{Nested}}\n| id = 42, 43\n}}\n| id = 99'), {42, 43})
        self.assertEqual(wiki.item_ids('{{Recipe\n| id = 42\n}}'), set())

    def test_identity_mismatch_is_not_cached(self):
        data = {'wikitext': {'*': '{{Item infobox\n| id = 99\n}}'}, 'text': {'*': HTML}, 'title': 'Example', 'revid': 1}
        with patch.object(wiki, 'page', return_value=data) as read:
            for _ in range(2):
                with self.assertRaises(ValueError): wiki.lookup(42, lambda _: {'name': 'Example'})
            self.assertEqual(read.call_count, 2)

    def test_generic_lookup_resolves_costs_and_caches_only_public_data(self):
        def page(name):
            item_id = 42 if name == 'Example' else 7
            return {'wikitext': {'*': '{{Item infobox\n| id = %s\n}}' % item_id},
                    'text': {'*': HTML}, 'title': name, 'revid': 123}
        def fetch(path):
            if path == '/currencies?ids=all': return [{'id': 9, 'name': 'Token'}]
            return {'id': int(path.split('/')[-1]), 'name': 'Example' if path.endswith('/42') else 'Input'}
        with patch.object(wiki, 'page', side_effect=page):
            result = wiki.lookup(42, fetch)
            self.assertEqual([(c['kind'], c['id'], c['per_trade']) for c in result['offers'][0]['costs']], [('item', 7, 2), ('currency', 9, 50)])
            self.assertEqual(wiki.lookup(42, lambda _: self.fail('Should use cache')), result)
            self.assertNotIn('holdings', result)

    def test_missing_sections_is_explicit_empty_result(self):
        self.assertEqual(wiki.extract('<h2>Description</h2><p>Example</p>'), ([], []))


if __name__ == '__main__':
    unittest.main()

import unittest
from unittest.mock import patch
import legendary
import legendary_catalog as catalog
import wiki_acquisition as wiki


RECIPE = '''{{Weapon infobox
| id = 900001
}}
== Acquisition ==
{{Recipe
| source = Mystic Forge
| quantity = 1
| ingredient1 = 2 Example gift
}}
== Notes ==
Other information.
'''


class CatalogueTests(unittest.TestCase):
    def setUp(self):
        wiki._cache.clear()

    def test_only_unambiguous_single_output_recipes(self):
        self.assertEqual(catalog.recipe_parts(RECIPE), [{'count': 2, 'name': 'Example gift'}])
        self.assertEqual(catalog.recipe_parts(RECIPE.replace('quantity = 1', 'quantity = 10')), [])
        self.assertEqual(catalog.recipe_parts(RECIPE.replace('2 Example gift', '{{unknown}}')), [])
        self.assertEqual(catalog.recipe_parts(RECIPE.replace('== Notes ==', '{{Recipe\n| source = Mystic Forge\n}}\n== Notes ==')), [])
        self.assertEqual(wiki.item_ids(RECIPE), {900001})

    def test_dynamic_catalogue_and_imported_tree(self):
        calls = []
        def fetch(path):
            calls.append(path)
            if path == '/legendaryarmory?ids=all': return [{'id': 900001, 'max_count': 2}]
            if path.startswith('/items?ids='): return [{'id': 900001, 'name': 'Example', 'type': 'Weapon', 'details': {'type': 'Sword'}}]
            return {'id': int(path.split('/')[-1]), 'name': 'Example' if path.endswith('900001') else 'Example gift', 'type': 'Trophy', 'flags': []}
        def page(name):
            return {'wikitext': {'*': RECIPE if name == 'Example' else '{{Item infobox\n| id = 900002\n}}'}, 'revid': 1}
        with patch.object(wiki, 'page', side_effect=page):
            definition = catalog.definition(900001, fetch)
            self.assertEqual(definition['nodes']['900001']['ingredients'], [{'id': 900002, 'count': 2}])
            self.assertTrue(legendary.allocate({900002: 2}, definition)['tree']['ready'])
            self.assertEqual(catalog.catalogue(fetch)[0]['max_count'], 2)
            with self.assertRaises(ValueError): catalog.definition(42, fetch)

    def test_unknown_recipe_has_no_fabricated_percentage(self):
        definition = {'root': 10, 'nodes': {'10': {'id': 10, 'name': 'Example', 'ingredients': []}}}
        def fetch(path, key): return []
        result = legendary.progress('key', fetch, definition)
        self.assertIsNone(result['coverage'])

    def test_coverage_accounts_for_partial_stack_and_completed_gift(self):
        definition = {'root': 10, 'nodes': {
            '10': {'id': 10, 'name': 'Example', 'ingredients': [{'id': 20, 'count': 1}, {'id': 30, 'count': 10}]},
            '20': {'id': 20, 'name': 'Gift', 'ingredients': [{'id': 30, 'count': 20}]},
            '30': {'id': 30, 'name': 'Material', 'ingredients': []}}}
        def fetch(path, key):
            return [{'id': 20, 'count': 1}, {'id': 30, 'count': 5}] if path == '/account/bank' else []
        result = legendary.progress('key', fetch, definition)
        self.assertEqual(result['coverage'], 75)
        self.assertEqual(result['shopping'][0]['missing'], 5)

    def test_direct_collection_precedes_optional_precursor_series(self):
        def fetch(path):
            if path == '/achievements/categories?ids=all': return [{'name': 'Legendary Weapons', 'achievements': [1, 2, 3]}]
            return [{'id': 1, 'name': 'Example I: Precursor', 'tiers': [{'count': 10}]},
                    {'id': 2, 'name': 'Legendary Weapon: Example', 'tiers': [{'count': 4}, {'count': 16}]},
                    {'id': 3, 'name': 'Example Repeated', 'tiers': [{'count': 2}], 'flags': ['Repeatable']}]
        with patch.object(catalog, 'catalogue', return_value=[{'id': 42, 'name': 'Example'}, {'id': 43, 'name': 'Unlinked'}]):
            links = catalog.achievement_links(fetch)
        self.assertEqual(links['42'], [{'id': 2, 'name': 'Legendary Weapon: Example', 'max': 16}])
        self.assertEqual(links['43'], [])

    def test_private_collection_progress_is_uncached_and_unknown_on_failure(self):
        links = {'42': [{'id': 2, 'name': 'Example', 'max': 16}], '43': []}
        def fetch(path, key):
            if key == 'denied': raise RuntimeError('Denied')
            if path == '/account/legendaryarmory': return [{'id': 43, 'count': 1}]
            return [{'id': 2, 'current': 15 if key == 'first' else 4}]
        with patch.object(catalog, 'achievement_links', return_value=links):
            self.assertEqual(catalog.collection_progress('first', fetch)['items']['42']['percent'], 94)
            self.assertEqual(catalog.collection_progress('second', fetch)['items']['42']['percent'], 25)
            failed = catalog.collection_progress('denied', fetch)
            self.assertIsNone(failed['items']['42']['percent'])
            self.assertEqual(len(failed['warnings']), 2)
            self.assertIsNone(catalog.collection_progress('first', fetch)['items']['43']['percent'])

    def test_alternative_recipes_remain_separate(self):
        second = '{{Recipe\n| source = Mystic Forge\n| quantity = 1\n| ingredient1 = 3 Other gift\n}}\n'
        text = RECIPE.replace('== Notes ==', second + '== Notes ==')
        self.assertEqual(len(catalog.recipe_options(text)), 2)
        self.assertEqual(catalog.recipe_parts(text), [])
        def fetch(path):
            item_id = int(path.split('/')[-1])
            return {'id': item_id, 'name': {900001: 'Example', 900002: 'Example gift', 900003: 'Other gift'}[item_id], 'flags': []}
        def page(name):
            return {'wikitext': {'*': text if name == 'Example' else '{{Item infobox\n| id = %s\n}}' % (900002 if name == 'Example gift' else 900003)}, 'revid': 1}
        with patch.object(catalog, 'catalogue', return_value=[{'id': 900001}]), patch.object(wiki, 'page', side_effect=page):
            first = catalog.definition(900001, fetch, 0)
            second = catalog.definition(900001, fetch, 1)
            self.assertEqual(first['nodes']['900001']['ingredients'], [{'id': 900002, 'count': 2}])
            self.assertEqual(second['nodes']['900001']['ingredients'], [{'id': 900003, 'count': 3}])
            self.assertEqual(second['selected_route'], 1)
            with self.assertRaises(ValueError): catalog.definition(900001, fetch, 2)

    def test_armory_items_cannot_fund_legendary_ingredients(self):
        definition = {'root': 10, 'nodes': {
            '10': {'id': 10, 'name': 'Combined legendary', 'ingredients': [{'id': 20, 'count': 1}]},
            '20': {'id': 20, 'name': 'Ingredient legendary', 'ingredients': []}}}
        def fetch(path, key):
            if path == '/account/legendaryarmory': return [{'id': 20, 'count': 1}]
            if path == '/account/bank' and key == 'physical': return [{'id': 20, 'count': 1}]
            return []
        self.assertFalse(legendary.progress('armory-only', fetch, definition)['tree']['ready'])
        self.assertTrue(legendary.progress('physical', fetch, definition)['tree']['ready'])

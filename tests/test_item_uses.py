import unittest
import item_uses


class ItemUseTests(unittest.TestCase):
    def setUp(self):
        item_uses._recipe_ids.clear()

    def test_summary_distinguishes_failure_from_no_recipes_and_caches_success(self):
        calls = []
        def fetch(path):
            calls.append(path)
            if path.endswith('=3'):
                raise RuntimeError('Unavailable')
            return [10, 11] if path.endswith('=1') else []
        data = item_uses.crafting_summary([1, 2, 3], fetch)['items']
        self.assertEqual(data['1']['count'], 2)
        self.assertEqual(data['2']['count'], 0)
        self.assertIn('error', data['3'])
        item_uses.crafting_summary([1, 2, 3], fetch)
        self.assertEqual(len(calls), 4)

    def test_recipe_lookup_ignores_item_category_and_keeps_amounts(self):
        paths = []
        def fetch(path):
            paths.append(path)
            if path == '/recipes/search?input=1':
                return [10]
            if path == '/recipes?ids=10':
                return [{'id': 10, 'output_item_id': 2, 'output_item_count': 3,
                         'disciplines': ['Artificer'], 'min_rating': 400,
                         'ingredients': [{'item_id': 1, 'count': 50}, {'item_id': 3, 'count': 2}]}]
            return [{'id': 1, 'name': 'Trophy ingredient'}, {'id': 2, 'name': 'Useful output'}, {'id': 3, 'name': 'Other ingredient'}]
        data = item_uses.recipes(1, 0, fetch)
        self.assertEqual(data['recipes'][0]['name'], 'Useful output')
        self.assertEqual(data['recipes'][0]['ingredients'][0], {'name': 'Trophy ingredient', 'count': 50, 'selected': True})
        self.assertEqual(data['recipes'][0]['count'], 3)
        self.assertEqual(data['recipes'][0]['rating'], 400)

    def test_recipe_pagination(self):
        paths = []
        def fetch(path):
            paths.append(path)
            if path.startswith('/recipes/search'):
                return list(range(1, 42))
            return []
        data = item_uses.recipes(1, 1, fetch)
        self.assertEqual(data['total'], 41)
        self.assertTrue(data['has_more'])
        self.assertEqual(paths[1], '/recipes?ids=' + ','.join(map(str, range(21, 41))))

    def test_empty_recipes_do_not_query_empty_batches(self):
        paths = []
        def fetch(path):
            paths.append(path)
            return []
        data = item_uses.recipes(1, 0, fetch)
        self.assertEqual(data['recipes'], [])
        self.assertEqual(len(paths), 1)

    def test_storage_overflow_is_after_available_deposit(self):
        data = item_uses.storage_summary(100, 240, 250, True)
        self.assertEqual(data['depositable'], 10)
        self.assertEqual(data['overflow'], 90)
        self.assertEqual(data['total'], 340)
        self.assertEqual(item_uses.storage_summary(100, 250, 250, True)['overflow'], 100)
        self.assertEqual(item_uses.storage_summary(100, 0, 250, True)['overflow'], 0)

    def test_unknown_storage_is_not_zero(self):
        self.assertIsNone(item_uses.storage_summary(100, 20, None, True)['overflow'])
        self.assertIsNone(item_uses.storage_summary(100, None, 250, False)['stored'])

    def test_storage_failure_preserves_recipe_results(self):
        def fetch(path, key=None):
            if path.startswith('/recipes/search'):
                return []
            raise RuntimeError('Network unavailable')
        result = item_uses.lookup(1, 0, 'Example', 'key', fetch)
        self.assertEqual(result['crafting']['total'], 0)
        self.assertIn('error', result['storage'])

    def test_recipe_failure_preserves_storage(self):
        def fetch(path, key=None):
            if path == '/account/materials':
                return [{'id': 1, 'count': 250}]
            if path == '/account':
                return {'material_storage_slots': 250}
            if path.startswith('/characters/'):
                return {'bags': [None, {'inventory': [None, {'id': 1, 'count': 30}]}]}
            raise RuntimeError('Network unavailable')
        result = item_uses.lookup(1, 0, 'Example', 'key', fetch)
        self.assertIn('error', result['crafting'])
        self.assertEqual(result['storage']['overflow'], 30)

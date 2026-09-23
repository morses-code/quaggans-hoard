import unittest
import legendary


class BifrostTests(unittest.TestCase):
    def test_completed_component_in_material_storage_satisfies_requirement(self):
        def fetch(path, key):
            return [{'id': 19674, 'count': 1}, {'id': 24277, 'count': 300}] if path == '/account/materials' else []
        result = legendary.progress('key', fetch)
        mastery = next(row for row in result['tree']['children'] if row['id'] == 19674)
        self.assertEqual((mastery['allocated'], mastery['missing'], mastery['children']), (1, 0, []))
        self.assertEqual(result['holdings'][19674], 1)
        self.assertEqual(result['locations'][19674], [{'location': 'Material storage', 'count': 1}])
        self.assertNotIn(19925, result['needed_ids'])
        dust = next(row for row in result['shopping'] if row['id'] == 24277)
        self.assertEqual(dust['allocated'], 300)

    def test_wallet_failure_does_not_mark_inventory_scan_incomplete(self):
        def fetch(path, key):
            if path == '/account/wallet': raise RuntimeError('Denied')
            return []
        result = legendary.progress('key', fetch)
        self.assertTrue(result['complete_scan'])
        self.assertTrue(result['acquisition_warnings'])
        self.assertIsNone(result['wallet'])

    def test_shared_dust_is_allocated_only_once(self):
        result = legendary.allocate({24277: 300})
        dust = next(row for row in result['shopping'] if row['id'] == 24277)
        self.assertEqual((dust['required'], dust['allocated'], dust['missing']), (750, 300, 450))
        self.assertFalse(result['tree']['ready'])

    def test_completed_gift_removes_its_ingredients(self):
        result = legendary.allocate({19654: 1})
        dust = next(row for row in result['shopping'] if row['id'] == 24277)
        self.assertEqual(dust['required'], 250)
        self.assertNotIn(19676, result['needed_ids'])
        self.assertNotIn(19623, result['needed_ids'])
        self.assertIn(19654, result['needed_ids'])

    def test_owned_legendary_and_ready_final_components(self):
        result = legendary.allocate({30698: 1})
        self.assertEqual(result['shopping'], [])
        self.assertEqual(result['needed_ids'], [])
        self.assertEqual(result['tree']['allocated'], 1)
        result = legendary.allocate({29180: 1, 19654: 1, 19626: 1, 19674: 1})
        self.assertTrue(result['tree']['ready'])
        self.assertEqual(result['tree']['allocated'], 0)

    def test_full_raw_materials_are_ready_but_gifts_are_not_marked_owned(self):
        initial = legendary.allocate({})
        holdings = {row['id']: row['required'] for row in initial['shopping']}
        result = legendary.allocate(holdings)
        self.assertTrue(result['tree']['ready'])
        gift = next(row for row in result['tree']['children'] if row['id'] == 19654)
        self.assertEqual(gift['allocated'], 0)
        self.assertTrue(gift['ready'])

    def test_partial_account_sources_are_explicit_and_not_cached(self):
        def fetch(path, key):
            if path == '/characters': return ['Example']
            if path.startswith('/characters/'):
                return {'bags': [None, {'inventory': [None, {'id': 24277, 'count': 50}]}]}
            if path == '/account/bank': raise RuntimeError('Do not expose private errors')
            if path == '/account/materials': return [{'id': 24277, 'count': 250 if key == 'first' else 10}]
            return []
        first = legendary.progress('first', fetch)
        second = legendary.progress('second', fetch)
        self.assertEqual(first['holdings'][24277], 300)
        self.assertEqual(second['holdings'][24277], 60)
        self.assertFalse(first['complete_scan'])
        self.assertEqual(first['warnings'], ['Bank unavailable; its items are not counted.'])

import unittest
from unittest.mock import patch
import cleanup
import server


class ActionTests(unittest.TestCase):
    def advice(self, item, slots=None, materials=None, limit=None, status='check', collections=None):
        result = {'1': {'status': status, 'reason': 'Unresolved', 'collections': collections or []}}
        bags = [{'inventory': slots or []}]
        return cleanup.add_actions(result, {'1': item}, bags, materials, limit)['1']

    def kinds(self, advice):
        return [a['kind'] for a in advice['actions']]

    def test_deposit_capacity_and_partial_deposit(self):
        result = self.advice({}, [{'id': 1, 'count': 100}], [{'id': 1, 'count': 240}], 250)
        self.assertIn('deposit', self.kinds(result))
        self.assertIn('up to 10', result['actions'][0]['reason'])
        self.assertEqual(result['actions'][0]['evidence'], 'API checked')

    def test_full_storage_does_not_suggest_deposit_or_discard(self):
        result = self.advice({}, materials=[{'id': 1, 'count': 250}], limit=250)
        self.assertEqual(self.kinds(result), ['check'])
        self.assertIn('full', result['storage_note'])

    def test_unknown_capacity_is_conditional(self):
        result = self.advice({}, materials=[{'id': 1, 'count': 250}])
        self.assertEqual(result['actions'][0]['evidence'], 'Conditional advice')

    def test_combine_proves_stackability_and_slot_savings(self):
        result = self.advice({}, [{'id': 1, 'count': 100}, {'id': 1, 'count': 50}])
        self.assertIn('combine', self.kinds(result))
        self.assertIn('free 1 slot', result['actions'][0]['reason'])
        self.assertIn('Bag 1, slot 2', result['actions'][0]['reason'])

    def test_combine_does_not_mix_bindings_or_assume_equipment_stacks(self):
        for slots in [
            [{'id': 1, 'count': 1}, {'id': 1, 'count': 1}],
            [{'id': 1, 'count': 100, 'binding': 'Account'}, {'id': 1, 'count': 50}],
            [{'id': 1, 'count': 200}, {'id': 1, 'count': 200}],
            [{'id': 1, 'count': 300}, {'id': 1, 'count': 100}],
        ]:
            self.assertNotIn('combine', self.kinds(self.advice({}, slots)))

    def test_vendor_junk_respects_no_sell_and_collection_credit(self):
        junk = {'rarity': 'Junk', 'vendor_value': 10}
        self.assertIn('vendor', self.kinds(self.advice(junk)))
        self.assertNotIn('vendor', self.kinds(self.advice({**junk, 'flags': ['NoSell']})))
        self.assertNotIn('vendor', self.kinds(self.advice(junk, status='keep')))

    def test_collection_disposal_prefers_vendor_value(self):
        self.assertEqual(self.kinds(self.advice({'vendor_value': 10}, status='safe')), ['vendor'])
        self.assertEqual(self.kinds(self.advice({'vendor_value': 10, 'flags': ['NoSell']}, status='safe')), ['discard'])

    def test_salvage_excludes_equipment_and_materials(self):
        item = {'type': 'Trophy', 'description': 'Salvage Item'}
        self.assertIn('salvage', self.kinds(self.advice(item)))
        for changed in [{**item, 'type': 'Weapon'}, {**item, 'flags': ['NoSalvage']}]:
            self.assertNotIn('salvage', self.kinds(self.advice(changed)))
        self.assertNotIn('salvage', self.kinds(self.advice(item, materials=[{'id': 1, 'count': 0}])))
        results = {'19721': {'status': 'check', 'reason': '', 'collections': []}}
        cleanup.add_actions(results, {'19721': item})
        self.assertNotIn('salvage', self.kinds(results['19721']))

    def test_currency_is_conditional_not_blanket_consumables(self):
        item = {'type': 'Consumable', 'details': {'type': 'Currency'}}
        result = self.advice(item)
        self.assertIn('consume', self.kinds(result))
        self.assertEqual(result['actions'][0]['evidence'], 'Conditional advice')
        self.assertNotIn('consume', self.kinds(self.advice({'type': 'Consumable', 'details': {'type': 'Food'}})))

    def test_generic_collection_only_requires_credit_and_exact_description(self):
        achievement = {'id': 2, 'name': 'Example', 'bits': [{'type': 'Item', 'id': 123}]}
        item = {'123': {'type': 'Trophy', 'description': cleanup.COLLECTION_ONLY}}
        self.assertEqual(cleanup.evaluate([123], [achievement], [{'id': 2, 'bits': [0]}], item, 'now')['123']['status'], 'safe')
        self.assertEqual(cleanup.evaluate([123], [achievement], [], item, 'now')['123']['status'], 'keep')
        self.assertEqual(cleanup.evaluate([123], [], [], item, 'now')['123']['status'], 'check')
        item['123']['description'] += ' Also used in crafting.'
        self.assertEqual(cleanup.evaluate([123], [achievement], [{'id': 2, 'done': True}], item, 'now')['123']['status'], 'check')

    def test_missing_progression_does_not_block_deposit_and_vendor(self):
        def fetch(path, key=None):
            if path == '/account/achievements':
                raise server.ApiError('Denied', 403)
            if path.startswith('/items'):
                return [{'id': 1, 'rarity': 'Junk', 'vendor_value': 5}]
            if path == '/account/materials':
                return [{'id': 1, 'count': 0}]
            if path == '/account':
                return {'material_storage_slots': 250}
            raise AssertionError(path)
        result = cleanup.analyze([1], 'secret', fetch)
        self.assertIn('deposit', self.kinds(result['items']['1']))
        self.assertIn('vendor', self.kinds(result['items']['1']))
        self.assertEqual(result['items']['1']['status'], 'check')
        self.assertTrue(result['warnings'])

    def test_character_analysis_uses_fresh_inventory_ids(self):
        paths = []
        def fetch(path, key=None):
            paths.append(path)
            if path == '/account/achievements':
                return []
            if path.startswith('/characters/'):
                return {'bags': [None, {'inventory': [{'id': 2, 'count': 5}, {'id': 2, 'count': 10}]}]}
            if path.startswith('/items'):
                return [{'id': 2}]
            if path == '/account/materials':
                return []
            if path == '/account':
                return {}
            raise AssertionError(path)
        with patch.object(cleanup, 'catalog', return_value=[]):
            result = cleanup.analyze([1], 'secret', fetch, character='A Name')
        self.assertIn('/characters/A%20Name/inventory', paths)
        self.assertIn('/items?ids=2', paths)
        self.assertEqual(set(result['items']), {'2'})

    def test_elsewhere_counts_are_fresh_and_failed_sources_are_unknown(self):
        def fetch(path, key=None):
            if path.startswith('/items'):
                return [{'id': 1}, {'id': 2}]
            if path == '/account':
                return {'material_storage_slots': 250}
            if path == '/account/bank':
                return [None, {'id': 1, 'count': 3}, {'id': 1, 'count': 7}]
            if path == '/account/inventory':
                if key == 'second-account':
                    return []
                raise server.ApiError('Unavailable')
            return []
        with patch.object(cleanup, 'catalog', return_value=[]):
            first = cleanup.analyze([1, 2], 'first-account', fetch)
            second = cleanup.analyze([1, 2], 'second-account', fetch)
        self.assertEqual(first['items']['1']['elsewhere'], {'bank': 10, 'shared': None})
        self.assertEqual(first['items']['2']['elsewhere'], {'bank': 0, 'shared': None})
        self.assertEqual(second['items']['1']['elsewhere']['shared'], 0)
        self.assertTrue(any('Shared inventory unavailable' in warning for warning in first['warnings']))

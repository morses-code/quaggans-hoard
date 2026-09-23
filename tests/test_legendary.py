import unittest
import legendary


class BifrostTests(unittest.TestCase):
    def test_vendor_costs_reserve_direct_recipe_inputs(self):
        holdings = {19721: 260, 19976: 20}
        plan = legendary.allocate(holdings)
        result = legendary.acquisition_options(plan, holdings, {23: 100, 7: 1500}, True)
        offer = next(row for row in result['19675']['offers'] if row['vendor'] == 'BUY-4373')
        ecto = next(row for row in offer['costs'] if row['kind'] == 'item' and row['id'] == 19721)
        self.assertEqual((ecto['owned'], ecto['reserved'], ecto['available']), (260, 250, 10))
        self.assertEqual((ecto['per_trade'], ecto['required'], ecto['shortfall']), (2, 154, 144))
        self.assertEqual(offer['supported_output'], 5)

    def test_vendor_limits_and_unknown_balances(self):
        holdings = {19721: 1000, 19976: 1000}
        plan = legendary.allocate(holdings)
        wallet = {23: 1000, 7: 100000}
        offers = legendary.acquisition_options(plan, holdings, wallet, True)['19675']['offers']
        offer = next(row for row in offers if row['vendor'] == 'BUY-4373')
        self.assertEqual(offer['supported_output'], 10)
        unknown = legendary.acquisition_options(plan, holdings, None, True)['19675']['offers'][0]
        self.assertIsNone(unknown['supported_output'])
        self.assertTrue(any(row['owned'] is None for row in unknown['costs'] if row['kind'] == 'currency'))
        partial = legendary.acquisition_options(plan, holdings, wallet, False)['19675']['offers'][0]
        self.assertIsNone(partial['supported_output'])
        self.assertEqual(partial['costs'][0]['known_owned'], 1000)

    def test_completed_gift_releases_reserved_trade_materials(self):
        holdings = {19674: 1, 19925: 30, 19721: 300, 19976: 30}
        plan = legendary.allocate(holdings)
        offer = next(row for row in legendary.acquisition_options(plan, holdings, {23: 30}, True)['19675']['offers'] if row['vendor'] == 'Lyhr')
        shard = next(cost for cost in offer['costs'] if cost['id'] == 19925)
        self.assertEqual(shard['reserved'], 0)
        self.assertEqual(offer['supported_output'], 10)

    def test_wallet_failure_does_not_mark_inventory_scan_incomplete(self):
        def fetch(path, key):
            if path == '/account/wallet': raise RuntimeError('Denied')
            return []
        result = legendary.progress('key', fetch)
        self.assertTrue(result['complete_scan'])
        self.assertTrue(result['acquisition_warnings'])
        self.assertIsNone(result['acquisition']['19675']['offers'][0]['supported_output'])

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

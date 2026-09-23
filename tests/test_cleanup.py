import unittest
from unittest.mock import patch
import cleanup
import server
import test_server
from urllib.error import HTTPError
from urllib.request import urlopen
import json


class EvaluationTests(unittest.TestCase):
    def setUp(self):
        self.achievement = {'id': 1754, 'name': 'Koutalophile', 'bits': [{'type': 'Text'}, {'type': 'Item', 'id': 67193}]}
        self.items = {'67193': {'type': 'Trophy', 'description': cleanup.RULES['67193']['expected_description']}}

    def evaluate(self, progress, achievements=None, items=None):
        return cleanup.evaluate([67193], achievements if achievements is not None else [self.achievement], progress, self.items if items is None else items, 'now')['67193']

    def test_exact_zero_based_bit_confirms_credit(self):
        self.assertEqual(self.evaluate([{'id': 1754, 'bits': [1]}])['status'], 'safe')
        self.assertEqual(self.evaluate([{'id': 1754, 'bits': [0]}])['status'], 'keep')

    def test_done_without_bits_confirms_credit(self):
        self.assertEqual(self.evaluate([{'id': 1754, 'done': True}])['status'], 'safe')

    def test_no_progress_does_not_authorize_disposal(self):
        self.assertEqual(self.evaluate([])['status'], 'keep')

    def test_missing_mapping_or_changed_description_is_unknown(self):
        self.assertEqual(self.evaluate([], achievements=[])['status'], 'check')
        self.assertEqual(self.evaluate([{'id': 1754, 'done': True}], items={})['status'], 'check')

    def test_skin_ids_are_not_item_ids(self):
        self.achievement['bits'][1]['type'] = 'Skin'
        self.assertEqual(self.evaluate([{'id': 1754, 'done': True}])['status'], 'check')

    def test_other_collection_blocks_disposal(self):
        other = {'id': 2, 'name': 'Another use', 'bits': [{'type': 'Item', 'id': 67193}]}
        result = self.evaluate([{'id': 1754, 'done': True}], [self.achievement, other])
        self.assertEqual(result['status'], 'keep')

    def test_repeatable_never_safe(self):
        self.achievement['flags'] = ['Repeatable']
        self.assertEqual(self.evaluate([{'id': 1754, 'done': True}])['status'], 'check')

    def test_completed_unknown_item_is_not_safe(self):
        self.achievement['bits'][1]['id'] = 999
        result = cleanup.evaluate([999], [self.achievement], [{'id': 1754, 'done': True}], {}, 'now')
        self.assertEqual(result['999']['status'], 'check')

    def test_catalog_does_not_publish_partial_results(self):
        with patch.object(cleanup, '_catalog', None), patch.object(cleanup, '_catalog_at', 0):
            with self.assertRaises(ValueError):
                cleanup.catalog(lambda path: [1, 2] if path == '/achievements' else [{'id': 1}])
            self.assertIsNone(cleanup._catalog)

    def test_account_progress_is_not_cached(self):
        calls = []
        def fetch(path, key=None):
            calls.append((path, key))
            return []
        with patch.object(cleanup, 'catalog', return_value=[]):
            cleanup.analyze([67193], 'first-key', fetch)
            cleanup.analyze([67193], 'second-key', fetch)
        self.assertIn(('/account/achievements', 'first-key'), calls)
        self.assertIn(('/account/achievements', 'second-key'), calls)
        self.assertTrue(all(key is None for path, key in calls if path.startswith('/items')))


class CleanupHttpTests(unittest.TestCase):
    setUpClass = classmethod(test_server.HttpTests.setUpClass.__func__)
    tearDownClass = classmethod(test_server.HttpTests.tearDownClass.__func__)

    def test_permission_error_is_actionable(self):
        with patch.object(server, 'load_key', return_value='secret'), patch.object(cleanup, 'analyze', side_effect=server.ApiError('Denied', 403)):
            with self.assertRaises(HTTPError) as error:
                urlopen(self.base + '/api/cleanup?ids=67193')
            self.assertIn('progression', json.load(error.exception)['error'])

    def test_invalid_ids_are_rejected(self):
        with patch.object(server, 'load_key', return_value='secret'):
            for ids in ['', '-1', 'abc', '0', '1,', ','.join(['1'] * 1001)]:
                with self.assertRaises(HTTPError) as error:
                    urlopen(self.base + '/api/cleanup?ids=' + ids)
                self.assertEqual(error.exception.code, 400)

    def test_cleanup_route(self):
        with patch.object(server, 'load_key', return_value='secret'), patch.object(cleanup, 'analyze', return_value={'items': {}}) as analyze:
            with urlopen(self.base + '/api/cleanup?ids=67193,67193') as response:
                self.assertEqual(json.load(response), {'items': {}})
            analyze.assert_called_once_with([67193], 'secret', server.gw2)

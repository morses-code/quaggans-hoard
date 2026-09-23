import unittest
import item_locations


class LocationTests(unittest.TestCase):
    def test_partial_sources_preserve_totals_and_encode_character(self):
        paths = []
        def fetch(path, key):
            self.assertEqual(key, 'test-key')
            paths.append(path)
            if path == '/characters':
                return ['A Name/One']
            if path.startswith('/characters/'):
                return {'bags': [None, {'inventory': [None, {'id': 1, 'count': 2}]}]}
            if path == '/account/bank':
                raise RuntimeError('private details')
            if path == '/account/inventory':
                return [None, {'id': 1, 'count': 3}, {'id': 2, 'count': 100}]
            return [{'id': 1, 'count': 20}]
        result = item_locations.find(1, 'test-key', fetch)
        self.assertEqual(result['total'], 25)
        self.assertEqual(len(result['locations']), 3)
        self.assertIn('/characters/A%20Name%2FOne/inventory', paths)
        self.assertEqual(result['locations'][-1]['slot'], 'Bag 2, slot 2')
        self.assertEqual(result['warnings'], ['Bank: unavailable; not included in the total.'])

    def test_failed_character_list_still_searches_storage_without_cache(self):
        def fetch(path, key):
            if path == '/characters':
                raise RuntimeError()
            return [{'id': 1, 'count': 1}] if key == 'first' else []
        self.assertEqual(item_locations.find(1, 'first', fetch)['total'], 3)
        result = item_locations.find(1, 'second', fetch)
        self.assertEqual(result['total'], 0)
        self.assertTrue(result['warnings'])

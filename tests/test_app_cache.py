import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock, patch
from app_cache import DailyCache, DAY
import server
from urllib.request import Request, urlopen
from urllib.error import HTTPError


class CacheTests(unittest.TestCase):
    def test_daily_expiry_and_defensive_copy(self):
        cache = DailyCache()
        read = Mock(return_value={'count': 30})
        with patch('app_cache.time.time', return_value=100):
            cache.get(('account', '/bank'), read)['count'] = 0
        with patch('app_cache.time.time', return_value=100 + DAY - 1):
            self.assertEqual(cache.get(('account', '/bank'), read)['count'], 30)
            self.assertEqual(read.call_count, 1)
        with patch('app_cache.time.time', return_value=100 + DAY):
            cache.get(('account', '/bank'), read)
            self.assertEqual(read.call_count, 2)

    def test_failures_are_retryable(self):
        cache = DailyCache()
        read = Mock(side_effect=[RuntimeError('Offline'), 42])
        with self.assertRaises(RuntimeError): cache.get('item', read)
        self.assertEqual(cache.get('item', read), 42)
        self.assertEqual(read.call_count, 2)

    def test_overlapping_requests_share_work(self):
        cache = DailyCache()
        started, release = threading.Event(), threading.Event()
        def read():
            started.set()
            self.assertTrue(release.wait(2))
            return 42
        read = Mock(side_effect=read)
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(cache.get, 'same', read)
            self.assertTrue(started.wait(2))
            second = pool.submit(cache.get, 'same', read)
            release.set()
            self.assertEqual((first.result(), second.result()), (42, 42))
        self.assertEqual(read.call_count, 1)

    def test_refresh_during_request_prevents_stale_repopulation(self):
        cache = DailyCache()
        def read():
            cache.clear()
            return 'old'
        cache.get('item', read)
        self.assertEqual(cache.get('item', lambda: 'new'), 'new')

    def test_api_keys_are_isolated_and_refresh_preserves_other_accounts(self):
        cache = DailyCache()
        with patch.object(server, 'GAME_CACHE', cache), patch.object(server, 'fetch_gw2', side_effect=lambda path, key: [key]) as read:
            self.assertEqual(server.gw2('/account/bank', 'first'), ['first'])
            self.assertEqual(server.gw2('/account/bank', 'second'), ['second'])
            server.gw2('/account/bank', 'first')
            self.assertEqual(read.call_count, 2)
            server.refresh_cache('first')
            server.gw2('/account/bank', 'first')
            server.gw2('/account/bank', 'second')
            self.assertEqual(read.call_count, 3)
            self.assertNotIn('first', [key[0] for key in cache.entries])

    def test_key_validation_is_always_live(self):
        with patch.object(server, 'fetch_gw2', return_value={}) as read:
            server.gw2('/tokeninfo', 'key')
            server.gw2('/tokeninfo', 'key')
            self.assertEqual(read.call_count, 2)

    def test_cache_is_bounded(self):
        cache = DailyCache(2)
        for i in range(3): cache.get(i, lambda: i)
        self.assertEqual(len(cache.entries), 2)
        self.assertNotIn(0, cache.entries)

    def test_manual_refresh_endpoint_rejects_other_origins(self):
        class Handler(server.Handler):
            def get_key(self): return 'test-key'
        http = server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=http.serve_forever, daemon=True)
        thread.start()
        url = f'http://127.0.0.1:{http.server_port}/api/refresh'
        try:
            with patch.object(server, 'refresh_cache') as refresh:
                request = Request(url, method='POST', headers={'Content-Type': 'application/json'})
                with urlopen(request, timeout=2) as response: self.assertEqual(response.status, 200)
                refresh.assert_called_once_with('test-key')
                request.add_header('Origin', 'https://untrusted.example')
                with self.assertRaises(HTTPError) as error: urlopen(request, timeout=2)
                self.assertEqual(error.exception.code, 403)
                refresh.assert_called_once()
        finally:
            http.shutdown()
            http.server_close()

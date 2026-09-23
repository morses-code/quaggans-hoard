import json
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import urlopen
from unittest.mock import patch, Mock

import server


class DisconnectTests(unittest.TestCase):
    def handler(self):
        handler = object.__new__(server.Handler)
        handler.path = '/api/characters'
        handler.close_connection = False
        handler.send_response = Mock()
        handler.send_header = Mock()
        handler.end_headers = Mock()
        handler.wfile = Mock()
        return handler

    def test_disconnect_during_headers_or_body_does_not_send_second_response(self):
        for error in server.CLIENT_DISCONNECTS:
            for phase in ['headers', 'body']:
                with self.subTest(error=error, phase=phase):
                    handler = self.handler()
                    target = handler.end_headers if phase == 'headers' else handler.wfile.write
                    target.side_effect = error('Browser disconnected')
                    with patch.object(server, 'load_key', return_value='secret'), patch.object(server, 'gw2', return_value=[]), patch.object(server.LOGGER, 'error') as log:
                        handler.do_GET()
                    self.assertTrue(handler.close_connection)
                    handler.send_response.assert_called_once_with(200)
                    log.assert_not_called()

    def test_disconnect_while_sending_api_error_is_quiet(self):
        handler = self.handler()
        handler.end_headers.side_effect = ConnectionAbortedError(10053, 'Aborted')
        with patch.object(server, 'load_key', return_value='secret'), patch.object(server, 'gw2', side_effect=server.ApiError('Unavailable', 502)):
            handler.do_GET()
        handler.send_response.assert_called_once_with(502)
        self.assertTrue(handler.close_connection)

    def test_real_error_is_logged_once_even_if_client_is_gone(self):
        handler = self.handler()
        handler.wfile.write.side_effect = ConnectionResetError('Disconnected')
        with patch.object(server, 'load_key', side_effect=RuntimeError('sensitive text')), self.assertLogs(server.LOGGER, level='ERROR') as logs:
            handler.do_GET()
        handler.send_response.assert_called_once_with(500)
        self.assertEqual(len(logs.output), 1)
        self.assertIn('RuntimeError', logs.output[0])
        self.assertNotIn('sensitive text', logs.output[0])

    def test_read_and_finish_disconnects_are_quiet(self):
        for method in ['handle', 'finish']:
            handler = self.handler()
            with patch.object(server.BaseHTTPRequestHandler, method, side_effect=ConnectionAbortedError('Aborted')):
                getattr(handler, method)()
            self.assertTrue(handler.close_connection)

    def test_unrelated_io_errors_are_not_swallowed(self):
        handler = self.handler()
        handler.wfile.write.side_effect = OSError('Unrelated failure')
        with self.assertRaises(OSError):
            handler.send(200, b'ok', 'text/plain')


class InventoryTests(unittest.TestCase):
    def test_inventory_encodes_name_deduplicates_and_chunks_ids(self):
        slots = [{"id": i, "count": 1} for i in range(1, 203)]
        calls = []

        def fake_api(path, key=None):
            calls.append((path, key))
            if path.startswith('/characters/'):
                return {"bags": [None, {"id": 1, "size": 204, "inventory": slots + [None, slots[0]]}]}
            return [{"id": int(i), "name": "Example"} for i in path.split('=')[1].split(',')]

        with patch.object(server, 'gw2', side_effect=fake_api):
            result = server.inventory('A Name/É', 'secret')
        self.assertEqual(calls[0], ('/characters/A%20Name%2F%C3%89/inventory', 'secret'))
        self.assertEqual(len(result['items']), 202)
        self.assertEqual(len(calls), 3)
        self.assertTrue(all(key is None for _, key in calls[1:]))

    def test_item_failure_preserves_inventory(self):
        bags = [{"id": 1, "size": 1, "inventory": [{"id": 2, "count": 7}]}]
        with patch.object(server, 'gw2', side_effect=[{"bags": bags}, server.ApiError('Unavailable')]):
            result = server.inventory('Example', 'secret')
        self.assertEqual(result['bags'], bags)
        self.assertTrue(result['warning'])


class HttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.http = server.ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
        cls.thread = threading.Thread(target=cls.http.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f'http://127.0.0.1:{cls.http.server_port}'

    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown()
        cls.http.server_close()
        cls.thread.join()

    def test_static_and_secret_file_protection(self):
        for path in ['/', '/app.js', '/style.css', '/quaggan.svg', '/favicon.ico']:
            with urlopen(self.base + path) as response:
                self.assertEqual(response.status, 200)
                self.assertTrue(response.read())
        for path in ['/.env', '/server.py', '/../.env']:
            with self.assertRaises(HTTPError) as error:
                urlopen(self.base + path)
            self.assertEqual(error.exception.code, 404)

    def test_missing_key_is_actionable(self):
        with patch.object(server, 'load_key', return_value=''):
            with self.assertRaises(HTTPError) as error:
                urlopen(self.base + '/api/characters')
            self.assertEqual(error.exception.code, 503)
            self.assertIn('GW2_API_KEY', json.load(error.exception)['error'])

    def test_characters_and_inventory_routes(self):
        with patch.object(server, 'load_key', return_value='secret'), patch.object(server, 'gw2', return_value=['Example']):
            with urlopen(self.base + '/api/characters') as response:
                self.assertEqual(json.load(response), ['Example'])
        with patch.object(server, 'load_key', return_value='secret'), patch.object(server, 'inventory', return_value={"bags": [], "items": {}}) as inventory:
            with urlopen(self.base + '/api/inventory?character=A%20Name') as response:
                self.assertEqual(json.load(response)['bags'], [])
            inventory.assert_called_once_with('A Name', 'secret')

    def test_character_profile_contains_display_data_and_profession_art(self):
        core = {'name': 'Example', 'race': 'Human', 'level': 80, 'profession': 'Guardian', 'created': 'private'}
        with patch.object(server, 'load_key', return_value='secret'), patch.object(server, 'gw2', side_effect=[core, {'icon_big': 'https://render.guildwars2.com/icon.png'}]):
            with urlopen(self.base + '/api/character-profile?character=Example') as response:
                data = json.load(response)
        self.assertEqual(data['art'], '/art/guardian.jpg')
        self.assertEqual(data['profession'], 'Guardian')
        self.assertNotIn('created', data)

    def test_character_profile_survives_unavailable_icon(self):
        with patch.object(server, 'load_key', return_value='secret'), patch.object(server, 'gw2', side_effect=[{'name': 'Example', 'profession': 'Revenant'}, server.ApiError('Unavailable')]):
            with urlopen(self.base + '/api/character-profile?character=Example') as response:
                data = json.load(response)
        self.assertIsNone(data['art'])
        self.assertIsNone(data['icon'])


if __name__ == '__main__':
    unittest.main()

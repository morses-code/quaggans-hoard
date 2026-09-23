import json
from pathlib import Path
import tempfile
import threading
import unittest
from http.cookiejar import CookieJar
from urllib.error import HTTPError
from urllib.request import build_opener, HTTPCookieProcessor, Request, urlopen
from unittest.mock import patch

import desktop
import server


class FakeVault:
    def __init__(self):
        self.key = None
    def get_password(self, *args):
        return self.key
    def set_password(self, service, user, value):
        self.key = value
    def delete_password(self, *args):
        self.key = None


class DesktopTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.vault = FakeVault()
        self.state = desktop.DesktopState(self.vault, Path(self.directory.name))
        self.http, self.launch = desktop.create_server(self.state)
        self.base = f'http://127.0.0.1:{self.http.server_port}'
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.thread.start()
        self.client = build_opener(HTTPCookieProcessor(CookieJar()))
        self.client.open(self.launch).close()

    def tearDown(self):
        self.http.shutdown()
        self.http.server_close()
        self.thread.join()
        self.directory.cleanup()

    def post(self, path, data, **headers):
        return self.client.open(Request(self.base + path, json.dumps(data).encode(),
                                       {'Content-Type': 'application/json', **headers}))

    def test_local_api_requires_session_and_rejects_foreign_origins(self):
        with self.assertRaises(HTTPError) as error:
            urlopen(self.base + '/desktop/state')
        self.assertEqual(error.exception.code, 403)
        with self.assertRaises(HTTPError) as error:
            self.post('/desktop/preferences', {}, Origin='https://example.com')
        self.assertEqual(error.exception.code, 403)

    def test_setup_stores_only_in_vault_and_disconnect_removes_it(self):
        key = 'test-secret-key-for-desktop-only'
        with patch.object(server, 'gw2', return_value={'permissions': ['account', 'characters', 'inventories', 'progression']}):
            self.post('/desktop/connect', {'key': key}).close()
        self.assertEqual(self.vault.key, key)
        with self.client.open(self.base + '/desktop/state') as response:
            body = response.read().decode()
        self.assertNotIn(key, body)
        self.assertTrue(json.loads(body)['connected'])
        self.assertEqual(list(Path(self.directory.name).iterdir()), [])
        self.post('/desktop/disconnect', {}).close()
        self.assertIsNone(self.vault.key)
        self.assertEqual(self.state.key, '')

    def test_invalid_permissions_leave_existing_key_untouched(self):
        self.state.key = self.vault.key = 'existing'
        with patch.object(server, 'gw2', return_value={'permissions': ['account']}):
            with self.assertRaises(HTTPError) as error:
                self.post('/desktop/connect', {'key': 'test-secret-key-for-desktop-only'})
        self.assertEqual(error.exception.code, 400)
        self.assertEqual(self.vault.key, 'existing')

    def test_preferences_survive_restart_and_cannot_contain_keys(self):
        values = {'tyria.defaultCharacter': 'Example', 'quaggansHoard.protectedItems': '[1,2]'}
        self.post('/desktop/preferences', values).close()
        restarted = desktop.DesktopState(self.vault, Path(self.directory.name))
        self.assertEqual(restarted.preferences, values)
        with self.assertRaises(HTTPError):
            self.post('/desktop/preferences', {'GW2_API_KEY': 'never-store-this'})
        self.assertEqual(restarted.preferences, values)

    def test_desktop_does_not_fall_back_to_env_key(self):
        with patch.object(server, 'load_key', return_value='private-development-key') as load:
            with self.assertRaises(HTTPError) as error:
                self.client.open(self.base + '/api/characters')
        self.assertEqual(error.exception.code, 401)
        load.assert_not_called()

    def test_desktop_assets_and_secret_file_protection(self):
        with self.client.open(self.base) as response:
            self.assertIn(b'/desktop.js', response.read())
        with self.assertRaises(HTTPError):
            self.client.open(self.base + '/.env')

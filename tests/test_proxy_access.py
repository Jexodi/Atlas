import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from atlas.ai.access import create_client, PROXY_URL


class AccessTests(unittest.IsolatedAsyncioTestCase):
    async def test_no_key_and_no_setup_access_fails_closed(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, 'Accès SIDERON absent'):
                create_client()

    async def test_setup_access_preferred_over_owner_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'access.bin'
            path.touch()
            with patch('atlas.ai.access.access_path', return_value=path), \
                 patch('atlas.ai.access.decrypt_access', return_value='sideron_test_fixture'), \
                 patch.dict(os.environ, {'OPENAI_API_KEY': 'owner-test-key'}):
                client = create_client()
                self.assertEqual(client.api_key, 'sideron_test_fixture')
                self.assertEqual(str(client.base_url), PROXY_URL)
                self.assertTrue(str(client.websocket_base_url).startswith('wss://atlasbot.freeboxos.fr/'))
                await client.close()

    async def test_developer_direct_mode(self):
        with patch('atlas.ai.access.access_path', return_value=None), \
             patch.dict(os.environ, {'OPENAI_API_KEY': 'owner-test-key', 'OPENAI_BASE_URL': 'https://evil.invalid'}):
            client = create_client()
            self.assertEqual(str(client.base_url), 'https://api.openai.com/v1/')
            await client.close()


if __name__ == '__main__':
    unittest.main()

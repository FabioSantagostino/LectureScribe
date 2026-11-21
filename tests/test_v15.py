import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lecturescribe_webex import add_to_ytdlp_cookiejar, _allowed_domain, inspect_webex, WebexBrowserError
from lecturescribe_openvino import model_directory, MODEL_MAP, device_list


class WebexCookieTests(unittest.TestCase):
    def test_domain_allow_list(self):
        self.assertTrue(_allowed_domain('.politecnicomilano.webex.com'))
        self.assertTrue(_allowed_domain('.webex.com'))
        self.assertFalse(_allowed_domain('webex.com.example.net'))
        self.assertFalse(_allowed_domain('example.com'))

    def test_rejects_lookalike_hostname_before_launch(self):
        with self.assertRaises(WebexBrowserError):
            inspect_webex(Path('unused'), 'https://webex.com.evil.example/recording')

    def test_no_unrelated_cookies(self):
        jar = MagicMock()
        data = [{'name': 'test', 'value': 'secret', 'domain': '.webex.com', 'path': '/', 'expires': -1},
                {'name': 'other', 'value': 'secret', 'domain': '.example.com', 'path': '/'}]
        count = add_to_ytdlp_cookiejar(jar, data)
        self.assertEqual(count, 1)
        self.assertEqual(jar.cookiejar.set_cookie.call_count, 1)


class OpenVINOTests(unittest.TestCase):
    def test_matching_model_paths(self):
        root = Path('models')
        self.assertEqual(model_directory(root, 'turbo'), root / 'whisper-large-v3-turbo')
        self.assertEqual(model_directory(root, 'large-v3'), root / 'whisper-large-v3')

    def test_device_discovery_no_crash(self):
        self.assertIsInstance(device_list(), list)


if __name__ == '__main__':
    unittest.main()

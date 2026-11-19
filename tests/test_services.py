import hashlib
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch, Mock

from lecturescribe_updates import version_tuple, stage_update, VERSION


class TestUpdates(unittest.TestCase):
    def test_versions(self):
        self.assertTrue(version_tuple('v1.2.0') > version_tuple('v1.1.2'))
        self.assertEqual(version_tuple('v1.2.0'), (1, 2, 0))

    def test_missing_digest_fails_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(RuntimeError, 'SHA-256'):
                stage_update({'browser_download_url':'https://github.com/a/b'}, folder)

    def test_reject_non_github_url(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(RuntimeError, 'Untrusted'):
                stage_update({'digest':'sha256:'+'a'*64, 'browser_download_url':'https://example.com/file.zip'}, folder)

if __name__ == '__main__': unittest.main()

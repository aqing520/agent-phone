"""Phone-only DeepSeek archive tests, isolated from user sessions."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from phone_archive import PhoneArchive
import server

class ArchiveTests(unittest.TestCase):
    def test_archive_restore_idempotent_and_persistent(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / 'archive.sqlite'
            store = PhoneArchive(path)
            self.assertEqual(store.ids(), [])
            self.assertEqual(store.set('main', True), ['main'])
            self.assertEqual(store.set('main', True), ['main'])
            self.assertEqual(PhoneArchive(path).ids(), ['main'])
            self.assertEqual(store.set('main', False), [])
            self.assertEqual(store.set('main', False), [])
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_annotation_does_not_change_cached_sessions_or_other_sources(self):
        raw = [{'id':'main', 'source':'dsh'}, {'id':'other', 'source':'codex'}]
        with patch.object(server, '_cache2', {'data':raw, 'at':server.time.time()}), \
             patch.object(server, 'desktop_call', return_value={'ready':False}), \
             patch.object(server, 'PhoneArchive') as archive:
            archive.return_value.ids.return_value = ['main', 'other']
            result = server.get_sessions()
            self.assertTrue(result[0]['archived'])
            self.assertFalse(result[1]['archived'])
            self.assertNotIn('archived', raw[0])
            archive.return_value.ids.assert_called_once()

if __name__ == '__main__': unittest.main()

"""DeepSeek-only discovery regressions; never launches an agent or reads user stores."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import server


class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.events = {}
        self.home = patch.object(server, 'DSH', str(self.root))
        self.home.start()
        self.addCleanup(self.home.stop)
        self.reader = patch.object(server, '_dsh_events', side_effect=lambda sid: self.events.get(sid, []))
        self.reader.start()
        self.addCleanup(self.reader.stop)

    def session(self, sid, **meta):
        path = self.root / 'sessions' / 'project' / sid / 'session.v4.jsonl.zstd'
        path.parent.mkdir(parents=True)
        path.touch()
        self.events[sid] = [dict(type='session', id=sid, cwd=str(self.root), createdAt=1000, **meta),
                            {'type': 'user/message', 'data': {'source': {'kind': 'user'},
                             'content': [{'type': 'text', 'text': 'hello'}]}}]

    def test_persisted_session_without_projection_is_visible_and_resumable(self):
        self.session('main')
        sessions = server.parse_dsh_sessions()
        self.assertEqual([s['id'] for s in sessions], ['main'])
        self.assertEqual(sessions[0]['title'], 'hello')
        self.assertEqual(server.find_control_session('main', 'dsh'), str(self.root))

    def test_delegated_children_excluded_and_not_resumable(self):
        self.session('main')
        self.session('child', delegationDepth=1)
        self.session('child-parent', parentSession='main')
        self.session('child-origin', origin='subagent')
        self.assertEqual([s['id'] for s in server.parse_dsh_sessions()], ['main'])
        self.assertIsNone(server.find_control_session('child', 'dsh'))
        self.assertEqual(server.parse_dsh_messages('child'), [])

    def test_runtime_only_sessions_and_stale_cache_not_listed(self):
        self.session('empty')
        self.events['empty'] = self.events['empty'][:1]
        cache = self.root / 'storages/session_projcache/sessions/stale.json'
        cache.parent.mkdir(parents=True)
        cache.write_text(json.dumps({'record': {'identity': {'cwd': str(self.root)}, 'rows': {}}}))
        self.assertEqual(server.parse_dsh_sessions(), [])

    def test_prompt_quotes_are_not_used_to_classify_subagents(self):
        self.session('main')
        self.events['main'][1]['data']['content'][0]['text'] = 'Your final answer is delivered automatically'
        self.assertEqual(len(server.parse_dsh_sessions()), 1)

    def test_corrupt_projection_does_not_hide_valid_session(self):
        self.session('main')
        cache = self.root / 'storages/session_projcache/sessions/main.json'
        cache.parent.mkdir(parents=True)
        cache.write_text('{broken')
        self.assertEqual(len(server.parse_dsh_sessions()), 1)

    def test_session_lookup_requires_a_literal_directory_name(self):
        self.session('main')
        main = self.root / 'sessions' / 'project' / 'main'
        self.assertEqual(server.dsh_session_dir('main'), str(main))
        self.assertIsNone(server.dsh_session_dir(str(main)))
        self.assertIsNone(server.dsh_session_dir('mai?'))


if __name__ == '__main__':
    unittest.main()

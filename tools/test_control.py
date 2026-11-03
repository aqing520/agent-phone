"""Exercise durable submissions, writer conflicts and worker results without model calls."""
import concurrent.futures
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
import uuid
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from control import ControlService, ControlError, session_context


class ControlTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.sid = str(uuid.uuid4())
        self.rollout = self.root / 'rollout.jsonl'
        self.write_rollout()
        self.fake = self.root / 'codex'
        self.fake.write_text('''#!/usr/bin/env python3
import sys,json,time
text=sys.stdin.read()
if text.strip() == 'LOCK':
 print('thread-store conflict: already has an active writer',file=sys.stderr);sys.exit(1)
if text.strip() == 'EMPTY':sys.exit(0)
if text.strip() == 'FAIL':
 print(json.dumps({'type':'turn.failed'}));sys.exit(1)
print(json.dumps({'type':'thread.started','thread_id':sys.argv[-2]}),flush=True)
print(json.dumps({'type':'turn.started'}),flush=True)
time.sleep(.15)
print(json.dumps({'type':'item.completed','item':{'type':'agent_message','text':'fixture reply'}}),flush=True)
print(json.dumps({'type':'turn.completed'}),flush=True)
''')
        self.fake.chmod(0o700)
        self.service = ControlService(self.root / 'private' / 'jobs.sqlite', str(self.fake))

    def tearDown(self):
        self.tmp.cleanup()

    def write_rollout(self, busy=False):
        events = [
            {'type':'session_meta','payload':{'id':self.sid,'cwd':str(self.root)}},
            {'type':'turn_context','payload':{'sandbox_policy':{'type':'read-only'}}},
            {'type':'event_msg','payload':{'type':'task_started'}},
        ]
        if not busy:
            events.append({'type':'event_msg','payload':{'type':'task_complete'}})
        self.rollout.write_text('\n'.join(json.dumps(e) for e in events) + '\n')

    def payload(self, text='hello'):
        return {'requestId':str(uuid.uuid4()),'source':'codex','session':self.sid,'text':text}

    def submit(self, payload):
        return self.service.submit(payload, lambda sid, src: str(self.rollout))

    def finish(self, job):
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            current = self.service.get(job['id'])
            if current['status'] not in ('queued','starting','running'):
                # Worker is a standalone process; let its SQLite context close.
                time.sleep(.05)
                return current
            time.sleep(.05)
        self.fail('worker did not finish')

    def test_worker_and_gateway_restart_do_not_resend(self):
        payload = self.payload('quote " ; $(touch should-not-exist)')
        job = self.submit(payload)
        fresh = ControlService(self.service.db_path, str(self.fake))
        self.assertEqual(fresh.submit(payload, lambda *a: str(self.rollout))['id'], job['id'])
        self.assertEqual(self.finish(job)['status'], 'completed')
        self.assertFalse((self.root / 'should-not-exist').exists())
        with fresh.db() as conn:
            self.assertEqual(conn.execute('select count(*) from jobs').fetchone()[0], 1)

    def test_concurrent_identical_posts_launch_only_one_worker(self):
        payload = self.payload()
        with patch('control.subprocess.Popen') as spawn:
            spawn.return_value.pid = os.getpid()
            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
                jobs = list(pool.map(lambda _:self.submit(payload), range(5)))
            self.assertEqual(spawn.call_count, 1)
            self.assertEqual({j['id'] for j in jobs}, {payload['requestId']})

    def test_request_id_cannot_be_reused_for_different_text(self):
        payload = self.payload()
        job = self.submit(payload)
        payload['text'] = 'different'
        with self.assertRaises(ControlError) as error:
            self.submit(payload)
        self.assertEqual(error.exception.code, 'request_conflict')
        self.finish(job)

    def test_same_session_cannot_have_two_jobs(self):
        with patch('control.subprocess.Popen') as spawn:
            spawn.return_value.pid = os.getpid()
            self.submit(self.payload())
            with self.assertRaises(ControlError) as error:
                self.submit(self.payload())
            self.assertEqual(error.exception.code, 'session_busy')

    def test_known_busy_turn_is_not_started(self):
        self.write_rollout(busy=True)
        with self.assertRaises(ControlError) as error:
            self.submit(self.payload())
        self.assertEqual(error.exception.code, 'session_busy')

    def test_desktop_writer_lock_is_reported(self):
        job = self.finish(self.submit(self.payload('LOCK')))
        self.assertEqual(job['status'], 'failed')
        self.assertIn('桌面仍持有', job['message'])

    def test_zero_exit_without_turn_completed_is_not_success(self):
        self.assertEqual(self.finish(self.submit(self.payload('EMPTY')))['status'], 'failed')

    def test_model_failure_is_not_success(self):
        self.assertEqual(self.finish(self.submit(self.payload('FAIL')))['status'], 'failed')

    def test_unsupported_sources_and_invalid_input(self):
        payload = self.payload(); payload['source'] = 'workbuddy'
        with self.assertRaises(ControlError) as error:
            self.submit(payload)
        self.assertEqual(error.exception.code, 'unsupported_source')
        for value in ('', 'x' * 12001, 123):
            payload = self.payload(value)
            with self.assertRaises(ControlError):self.submit(payload)

    def test_original_readonly_policy_is_preserved(self):
        self.assertEqual(session_context(self.rollout, with_policy=True)[1], 'read-only')

    def test_full_access_is_capped_at_workspace_write(self):
        with self.rollout.open('a') as stream:
            stream.write(json.dumps({'type':'turn_context','payload':{'sandbox_policy':{'type':'danger-full-access'}}})+'\n')
        self.assertEqual(session_context(self.rollout, with_policy=True)[1], 'workspace-write')

    def test_unknown_job_requires_explicit_acknowledgement(self):
        with patch('control.subprocess.Popen') as spawn:
            spawn.return_value.pid = os.getpid()
            job = self.submit(self.payload())
        self.service.update(job['id'], 'unknown', 'result unknown')
        with self.assertRaises(ControlError):self.submit(self.payload())
        with self.assertRaises(ControlError):self.service.acknowledge(job['id'])
        with self.service.db() as conn:
            conn.execute('update jobs set pid=NULL where id=?',(job['id'],))
        self.assertEqual(self.service.acknowledge(job['id'])['status'], 'interrupted')

    def test_private_storage_permissions(self):
        self.assertEqual(self.service.db_path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.service.db_path.parent.stat().st_mode & 0o777, 0o700)

    def test_readonly_gateway_cannot_start_commands(self):
        service = ControlService(self.service.db_path, str(self.fake), enabled=False)
        self.assertFalse(service.capabilities()['codex']['available'])
        with patch('control.subprocess.Popen') as spawn:
            with self.assertRaises(ControlError):
                service.submit(self.payload(), lambda *a:str(self.rollout))
            spawn.assert_not_called()


if __name__ == '__main__':
    unittest.main()

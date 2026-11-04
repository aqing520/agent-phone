"""Exercise durable submissions, writer conflicts and worker results without model calls."""
import concurrent.futures
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import threading
import unittest
import uuid
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from control import ControlService, ControlError, session_context
from codex_runtime import RuntimeDaemon


class ControlTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="ap-runtime-", dir="/tmp")
        self.root = Path(self.tmp.name)
        self.sid = str(uuid.uuid4())
        self.rollout = self.root / 'rollout.jsonl'
        self.write_rollout()
        self.fake = self.root / 'codex'
        self.calls = self.root / 'calls.jsonl'
        self.fake.write_text('''#!/usr/bin/env python3
import sys,json,time,threading,os,uuid
lock=threading.Lock()
log=__CALLS__
def record(obj):
 with open(log,'a') as f:f.write(json.dumps(obj)+'\\n')
def send(obj):
 with lock:print(json.dumps(obj),flush=True)
record({'method':'process','pid':os.getpid()})
def finish(sid,tid,fail):
 send({'method':'turn/completed','params':{'threadId':sid,'turn':{'id':tid,'status':'failed' if fail else 'completed'}}})
for line in sys.stdin:
 r=json.loads(line);m=r.get('method');p=r.get('params',{});i=r.get('id')
 record({'method':m,'params':p,'result':r.get('result')})
 if i=='permissions-check' and m is None:
  send({'method':'turn/completed','params':{'threadId':permission_sid,'turn':{'id':permission_tid,'status':'completed'}}});continue
 if m=='initialize':send({'id':i,'result':{}})
 elif m=='thread/start':send({'id':i,'result':{'thread':{'id':str(uuid.uuid4())}}})
 elif m=='thread/resume':send({'id':i,'result':{'thread':{'id':p['threadId']}}})
 elif m=='thread/unsubscribe':
  send({'id':i,'result':{'status':'unsubscribed'}})
  send({'method':'thread/closed','params':{'threadId':p['threadId']}})
 elif m=='turn/start':
  text=p['input'][0]['text'];sid=p['threadId'];tid=str(uuid.uuid4())
  if text=='LOCK':send({'id':i,'error':{'message':'thread-store conflict: already has an active writer'}});continue
  if text=='EMPTY':sys.exit(0)
  send({'id':i,'result':{'turn':{'id':tid,'status':'inProgress'}}})
  send({'method':'turn/started','params':{'threadId':sid,'turn':{'id':tid}}})
  if text=='CLOSE':send({'method':'thread/closed','params':{'threadId':sid}});continue
  if text=='PERMISSIONS':
   permission_sid,permission_tid=sid,tid
   send({'id':'permissions-check','method':'item/permissions/requestApproval','params':{'threadId':sid,'turnId':tid,'permissions':{'network':{'enabled':True}}}});continue
  timer=threading.Timer(.8 if text=='SLOW' else .1,finish,args=(sid,tid,text=='FAIL'))
  timer.daemon=True;timer.start()
'''.replace('__CALLS__',repr(str(self.calls))))
        self.fake.chmod(0o700)
        self.service = ControlService(self.root / 'private' / 'jobs.sqlite', str(self.fake))
        self.runtime = RuntimeDaemon(self.service)
        self.runtime_thread = threading.Thread(target=self.runtime.run, daemon=True)
        self.runtime_thread.start()
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if self.service.runtime_call().get('ready'):break
            time.sleep(.05)
        else:self.fail('runtime did not initialize')

    def tearDown(self):
        self.runtime.stop()
        self.runtime_thread.join(timeout=10)
        self.assertFalse(self.runtime_thread.is_alive())
        self.tmp.cleanup()

    def methods(self, name):
        return [r for r in map(json.loads,self.calls.read_text().splitlines()) if r['method']==name]

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

    def test_create_chat_reuses_request_and_returns_new_session(self):
        payload = self.payload()
        del payload['session']
        payload['project'] = ''
        def resolve_workspace(project):
            self.assertEqual(project, '')
            return str(self.root)

        job = self.finish(self.service.submit(payload, None, resolve_workspace))
        self.assertEqual(job['status'], 'completed')
        self.assertNotEqual(job['session'], payload['requestId'])
        self.assertEqual(self.service.submit(payload, None)['session'], job['session'])
        self.assertEqual(len(self.methods('thread/start')), 1)
        self.assertEqual(self.methods('turn/start')[0]['params']['threadId'], job['session'])

    def test_worker_and_gateway_restart_do_not_resend(self):
        payload = self.payload('quote " ; $(touch should-not-exist)')
        job = self.submit(payload)
        fresh = ControlService(self.service.db_path, str(self.fake))
        self.assertEqual(fresh.submit(payload, lambda *a: str(self.rollout))['id'], job['id'])
        self.assertEqual(self.finish(job)['status'], 'completed')
        self.assertFalse((self.root / 'should-not-exist').exists())
        with fresh.db() as conn:
            self.assertEqual(conn.execute('select count(*) from jobs').fetchone()[0], 1)

    def test_concurrent_identical_posts_launch_only_one_turn(self):
        payload = self.payload()
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
            jobs = list(pool.map(lambda _:self.submit(payload), range(5)))
        self.finish(jobs[0])
        self.assertEqual(len(self.methods('turn/start')), 1)
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
        job = self.submit(self.payload('SLOW'))
        with self.assertRaises(ControlError) as error:self.submit(self.payload())
        self.assertEqual(error.exception.code,'session_busy')
        self.finish(job)

    def test_multiple_turns_reuse_process_and_loaded_session(self):
        first=self.finish(self.submit(self.payload('first')))
        pid=self.service.runtime_call()['appServerPid']
        second=self.finish(self.submit(self.payload('second')))
        self.assertEqual((first['status'],second['status']),('completed','completed'))
        self.assertEqual(self.service.runtime_call()['appServerPid'],pid)
        self.assertEqual(len(self.methods('initialize')),1)
        self.assertEqual(len(self.methods('thread/resume')),1)
        self.assertEqual(len(self.methods('turn/start')),2)

    def test_release_rejects_active_turn_and_unloads_idle_session(self):
        job = self.submit(self.payload('SLOW'))
        with self.assertRaises(ControlError):
            self.service.release(self.sid)
        self.finish(job)
        pid = self.service.runtime_call()['appServerPid']
        self.assertTrue(self.service.release(self.sid)['released'])
        self.assertEqual(self.service.runtime_call()['loadedSessions'], 0)
        self.assertEqual(self.service.runtime_call()['appServerPid'], pid)

    def test_distinct_sessions_are_multiplexed_without_mixing_results(self):
        first = self.submit(self.payload('SLOW'))
        second_id = str(uuid.uuid4())
        other_path = self.root / 'other.jsonl'
        other_path.write_text(self.rollout.read_text().replace(self.sid, second_id))
        payload = self.payload('second session'); payload['session'] = second_id
        other = self.service.submit(payload, lambda *a:str(other_path))
        self.assertEqual(self.finish(other)['status'], 'completed')
        self.assertEqual(self.finish(first)['status'], 'completed')
        self.assertEqual(self.service.runtime_call()['loadedSessions'], 2)
        self.assertEqual(len(self.methods('process')), 1)

    def test_unloaded_session_can_be_resumed_in_same_process(self):
        job = self.finish(self.submit(self.payload('CLOSE')))
        self.assertEqual(job['status'], 'unknown')
        self.assertEqual(self.service.runtime_call()['loadedSessions'], 0)
        self.service.acknowledge(job['id'])
        self.assertEqual(self.finish(self.submit(self.payload('again')))['status'], 'completed')
        self.assertEqual(len(self.methods('thread/resume')), 2)
        self.assertEqual(len(self.methods('process')), 1)

    def test_permission_request_is_not_automatically_granted(self):
        self.assertEqual(self.finish(self.submit(self.payload('PERMISSIONS')))['status'], 'completed')
        replies = [r['result'] for r in self.methods(None) if r.get('result') is not None]
        self.assertIn({'permissions':{},'scope':'turn'}, replies)

    def test_known_busy_turn_is_not_started(self):
        self.write_rollout(busy=True)
        with self.assertRaises(ControlError) as error:
            self.submit(self.payload())
        self.assertEqual(error.exception.code, 'session_busy')

    def test_desktop_writer_lock_is_reported(self):
        job = self.finish(self.submit(self.payload('LOCK')))
        self.assertEqual(job['status'], 'failed')
        self.assertIn('其他 Codex', job['message'])

    def test_zero_exit_without_turn_completed_is_not_success(self):
        self.assertEqual(self.finish(self.submit(self.payload('EMPTY')))['status'], 'unknown')

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
        job=self.finish(self.submit(self.payload('EMPTY')))
        self.assertEqual(job['status'],'unknown')
        with self.assertRaises(ControlError):self.submit(self.payload())
        self.assertEqual(self.service.acknowledge(job['id'])['status'],'interrupted')

    def test_acknowledge_cannot_clear_a_live_turn(self):
        job=self.submit(self.payload('SLOW'))
        deadline=time.monotonic()+5
        while time.monotonic()<deadline:
            if self.service.get(job['id'])['status']=='running':break
            time.sleep(.02)
        self.service.update(job['id'],'unknown','test pending result')
        with self.assertRaises(ControlError):self.service.acknowledge(job['id'])
        self.finish(job)

    def test_private_storage_permissions(self):
        self.assertEqual(self.service.db_path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.service.db_path.parent.stat().st_mode & 0o777, 0o700)

    def test_readonly_gateway_cannot_start_commands(self):
        service = ControlService(self.service.db_path, str(self.fake), enabled=False)
        self.assertFalse(service.capabilities()['codex']['available'])
        with self.assertRaises(ControlError):
            service.submit(self.payload(), lambda *a:str(self.rollout))
        self.assertEqual(len(self.methods('turn/start')),0)


if __name__ == '__main__':
    unittest.main()

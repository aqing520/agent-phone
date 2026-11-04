"""Check ACP completion against the committed DeepSeek turn result."""
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from control import ControlService
from dsh_runtime import DeepSeekRuntime


class DeepSeekTests(unittest.TestCase):
    def test_end_turn_requires_a_new_committed_success(self):
        with tempfile.TemporaryDirectory() as root:
            service = ControlService(Path(root) / "jobs.sqlite", dsh="test-dsh")
            runtime = DeepSeekRuntime(service)
            client = Mock()
            client.closed = threading.Event()
            client.request.return_value = {"stopReason": "end_turn"}
            runtime.client = client
            sid = str(uuid.uuid4())
            runtime.loaded.add(sid)
            previous = {"type": "turn/end", "seq": 20, "data": {"turn": 1, "reason": {"kind": "completed"}}}
            for reason, expected in (("error", "failed"), ("completed", "completed"), (None, "unknown")):
                with self.subTest(reason=reason):
                    request_id = str(uuid.uuid4())
                    with patch.object(service, "runtime_call", return_value={"ready": True}):
                        job = service.submit(
                            {"requestId": request_id, "session": sid, "source": "dsh", "text": "test"},
                            lambda sid, source: root,
                        )
                    with service.db() as db:
                        row = db.execute("SELECT * FROM jobs WHERE id=?", (job["id"],)).fetchone()
                    runtime.active[sid] = {"job": job["id"]}
                    events = [previous]
                    if reason:
                        events.append({"type": "turn/end", "seq": 25, "data": {"turn": 2, "reason": {"kind": reason}}})
                    with patch("dsh_runtime._dsh_events", side_effect=([previous], events)), \
                         patch("dsh_runtime.time.monotonic", side_effect=(0, 3)):
                        runtime._start_job(row, client)
                    result = service.get(job["id"])
                    self.assertEqual(result["status"], expected)
                    self.assertEqual(result["turnId"], "2" if reason else None)


if __name__ == "__main__":
    unittest.main()

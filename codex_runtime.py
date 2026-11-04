"""Own one official Codex app-server process and dispatch durable phone turns.

Only wake/status/release are exposed on a user-private Unix socket. HTTP restarts do not
close Codex; a lost Codex connection marks in-flight messages unknown, never queued.
"""
import argparse
import fcntl
import json
import os
from pathlib import Path
from uuid import UUID
import signal
import socketserver
import subprocess
import threading
import time

from control import ControlService, ControlError, session_context


class RpcError(Exception):
    def __init__(self, message, data=None):
        super().__init__(message)
        self.data = data


class AppServerClient:
    arguments = ("app-server", "--stdio", "-c", "thread_unload_delay_secs=0")
    envelope = {}

    def __init__(self, binary, log_path, on_notification):
        self.on_notification = on_notification
        self.pending = {}
        self.lock = threading.RLock()
        self.close_lock = threading.Lock()
        self.next_id = 1
        self.closed = threading.Event()
        fd = os.open(str(log_path), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        self.log = os.fdopen(fd, "w")
        try:
            self.proc = subprocess.Popen(
                [binary, *self.arguments], stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=self.log, text=True,
                encoding="utf-8", errors="replace", bufsize=1,
            )
        except Exception:
            self.log.close()
            raise
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()
        try:
            self.initialize()
        except Exception:
            self.close()
            raise

    def initialize(self):
        self.request("initialize", {"clientInfo": {"name": "agent_phone", "version": "0.2.0"},
                                    "capabilities": {"experimentalApi": True}})
        self.send({"method": "initialized", "params": {}})

    def send(self, message):
        with self.lock:
            if self.closed.is_set():
                raise ConnectionError("Runtime connection closed")
            self.proc.stdin.write(json.dumps({**self.envelope, **message}, ensure_ascii=False) + "\n")
            self.proc.stdin.flush()

    def request(self, method, params, timeout=30):
        done, slot = threading.Event(), {}
        with self.lock:
            request_id = self.next_id
            self.next_id += 1
            self.pending[request_id] = (done, slot)
            try:
                self.send({"id": request_id, "method": method, "params": params})
            except Exception:
                self.pending.pop(request_id, None)
                raise
        if not done.wait(timeout):
            with self.lock:
                self.pending.pop(request_id, None)
            raise TimeoutError("Runtime RPC timed out")
        if "error" in slot:
            raise RpcError(slot["error"].get("message", "Runtime rejected request"), slot["error"].get("data"))
        if "disconnected" in slot:
            raise ConnectionError("Runtime connection closed")
        return slot.get("result", {})

    def _read(self):
        try:
            for line in self.proc.stdout:
                try:
                    message = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(message, dict):
                    continue
                if "method" in message and "id" in message:
                    self._server_request(message)
                elif "id" in message:
                    with self.lock:
                        pending = self.pending.pop(message["id"], None)
                    if pending:
                        pending[1].update(message)
                        pending[0].set()
                else:
                    self.on_notification(self, message)
        except (OSError, ValueError, ConnectionError):
            pass
        finally:
            self.closed.set()
            with self.lock:
                waiting, self.pending = self.pending, {}
            for done, slot in waiting.values():
                slot["disconnected"] = True
                done.set()

    def _server_request(self, message):
        # This release has no approval UI and never grants permissions implicitly.
        method = message["method"]
        if method in ("item/commandExecution/requestApproval", "item/fileChange/requestApproval"):
            result = {"decision": "decline"}
        elif method == "item/permissions/requestApproval":
            result = {"permissions": {}, "scope": "turn"}
        elif method == "mcpServer/elicitation/request":
            result = {"action": "decline", "content": None}
        else:
            self.send({"id": message["id"], "error": {"code": -32601,
                       "message": "Phone client does not support this interactive request"}})
            return
        self.send({"id": message["id"], "result": result})

    def close(self):
        with self.close_lock:
            self.closed.set()
            if self.proc.poll() is None:
                self.proc.terminate()
                try:
                    self.proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.proc.kill()
                    self.proc.wait()
            if self.reader is not threading.current_thread():
                self.reader.join(timeout=2)
            self.proc.stdin.close()
            self.proc.stdout.close()
            self.log.close()


class RuntimeDaemon:
    source = "codex"
    runtime_name = "Codex"
    socket_stem = "runtime"
    client_type = AppServerClient
    stderr_name = "app-server.stderr.log"
    idle_timeout = 300

    def binary(self):
        return self.service.codex

    def __init__(self, service):
        self.service = service
        self.client = None
        self.lock = threading.RLock()
        self.active = {}
        self.loaded = set()
        self.releasing = {}
        self.stop_event = threading.Event()
        self.wake = threading.Event()
        self.server = None

    def status(self):
        with self.lock:
            client = self.client
            return {"ready": True,
                    "appServerPid": client.proc.pid if client and not client.closed.is_set() else None,
                    "loadedSessions": len(self.loaded)}

    def record(self, event, **details):
        path = self.service.db_path.parent / "runtime.log"
        fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(fd, "w") as stream:
            stream.write(json.dumps({"at": int(time.time()*1000), "event": event, **details}, ensure_ascii=False) + "\n")

    def notification(self, client, message):
        method, params = message.get("method"), message.get("params") or {}
        sid, turn = params.get("threadId"), params.get("turn") or {}
        with self.lock:
            if client is not self.client:
                return
            unloaded = method in ("thread/closed", "thread/archived") or (method == "thread/status/changed" and params.get("status", {}).get("type") == "notLoaded")
            if unloaded:
                self.loaded.discard(sid)
                release = self.releasing.get(sid)
                if release:
                    release.set()
            entry = self.active.get(sid)
            if not entry:
                return
            if unloaded:
                self.service.update(entry["job"], "unknown", "会话已关闭，执行结果待确认。请先检查会话历史。")
                with self.service.db() as conn:
                    conn.execute("UPDATE jobs SET pid=NULL WHERE id=?", (entry["job"],))
                self.active.pop(sid, None)
                return
            if entry.get("turn") and turn.get("id") and entry["turn"] != turn["id"]:
                return
            if method == "turn/started":
                entry["turn"] = turn.get("id")
                self.service.update(entry["job"], "running", "Codex 正在执行，回复会显示在会话中。", turn_id=entry["turn"])
            elif method == "turn/completed":
                status = turn.get("status")
                if status == "completed":
                    state, detail = "completed", "执行完成，可以继续发送下一条消息。"
                elif status == "interrupted":
                    state, detail = "interrupted", "本轮执行已中断，请先查看会话结果。"
                else:
                    state, detail = "failed", "Codex 执行失败，请查看会话和 Mac 上的常驻服务日志。"
                self.service.update(entry["job"], state, detail, turn_id=turn.get("id"))
                self.record("turn_finished", job=entry["job"], status=state, turn=turn.get("id"))
                del self.active[sid]
                self.wake.set()

    def _start_job(self, row, client):
        sid, stage = row["session"], "resume"
        try:
            with self.lock:
                loaded = sid in self.loaded
            if not row["rollout"]:
                result = client.request("thread/start", {
                    "cwd": row["cwd"], "approvalPolicy": "never", "sandbox": "workspace-write",
                })
                new_sid = result.get("thread", {}).get("id")
                if not isinstance(new_sid, str) or str(UUID(new_sid)) != new_sid:
                    raise RpcError("Unexpected new thread id")
                with self.lock:
                    if self.client is not client or client.closed.is_set():
                        raise ConnectionError("Runtime changed")
                    with self.service.db() as conn:
                        conn.execute("UPDATE jobs SET session=? WHERE id=?", (new_sid, row["id"]))
                    self.active[new_sid] = self.active.pop(sid)
                    self.loaded.add(new_sid)
                    sid = new_sid
            elif not loaded:
                _, sandbox = session_context(row["rollout"], with_policy=True)
                result = client.request("thread/resume", {
                    "threadId": sid, "cwd": row["cwd"], "approvalPolicy": "never",
                    "sandbox": sandbox, "excludeTurns": True,
                })
                if result.get("thread", {}).get("id") != sid:
                    raise RpcError("Unexpected thread id returned by resume")
                with self.lock:
                    if self.client is not client or client.closed.is_set():
                        raise ConnectionError("Runtime changed")
                    self.loaded.add(sid)
                self.record("thread_resumed", session=sid, pid=client.proc.pid)
            stage = "start"
            result = client.request("turn/start", {
                "threadId": sid, "clientUserMessageId": row["id"],
                "approvalPolicy": "never",
                "input": [{"type": "text", "text": row["text"], "text_elements": []}],
            })
            with self.lock:
                entry = self.active.get(sid)
                if entry and entry["job"] == row["id"] and self.client is client:
                    entry["turn"] = result.get("turn", {}).get("id") or entry.get("turn")
                    self.service.update(row["id"], "running", "Codex 正在执行，回复会显示在会话中。", turn_id=entry["turn"])
        except (RpcError, ControlError) as exc:
            detail = str(exc)
            self.record("request_failed", job=row["id"], stage=stage, error=detail[:2000])
            if "active writer" in detail or "thread-store conflict" in detail:
                state, text = "failed", "其他 Codex 进程仍持有这段会话，请释放后重试；本次未执行。"
            elif stage == "resume":
                state, text = "failed", "无法恢复这段会话，请在 Mac 检查项目目录、会话占用和登录状态。"
            else:
                state, text = "failed", "Codex 未接受本轮请求，请在 Mac 检查登录与会话状态。"
            with self.lock:
                entry = self.active.get(sid)
                if entry and entry["job"] == row["id"]:
                    self.service.update(row["id"], state, text)
                    self.active.pop(sid, None)
        except Exception:
            # An unanswered turn/start might have reached the engine. Close this
            # broken connection and let recovery mark all affected turns unknown.
            client.close()
            self.wake.set()

    def dispatch(self):
        with self.service.db() as conn:
            rows = conn.execute(
                "SELECT * FROM jobs WHERE source=? AND status='queued' ORDER BY created_at LIMIT 8",
                (self.source,),
            ).fetchall()
        for row in rows:
            with self.lock:
                client = self.client
                if not client or client.closed.is_set() or len(self.active) >= 4:
                    return
                if row["session"] in self.active or row["session"] in self.releasing:
                    continue
                with self.service.db() as conn:
                    result = conn.execute("UPDATE jobs SET status='starting',message=?,pid=?,updated_at=? WHERE id=? AND status='queued'",
                                          ("正在接入常驻会话。", client.proc.pid, int(time.time()*1000), row["id"]))
                if not result.rowcount:
                    continue
                self.active[row["session"]] = {"job": row["id"], "turn": None}
                threading.Thread(target=self._start_job, args=(row, client), daemon=True).start()

    def release(self, sid):
        with self.lock:
            client = self.client
            if sid in self.active or sid in self.releasing:
                return {"released": False, "error": "会话正在处理，请稍后再释放。"}
            if self.has_queued_job(sid):
                return {"released": False, "error": "会话还有待执行的消息，请等任务结束。"}
            if not client or client.closed.is_set() or sid not in self.loaded:
                return {"released": True}
            done = threading.Event()
            self.releasing[sid] = done
        try:
            result = client.request("thread/unsubscribe", {"threadId": sid}, timeout=4)
            if result.get("status") == "notLoaded":
                with self.lock:
                    self.loaded.discard(sid)
                return {"released": True}
            if done.wait(8):
                return {"released": True}
        except (RpcError, OSError, TimeoutError):
            pass
        finally:
            with self.lock:
                self.releasing.pop(sid, None)
        return {"released": False, "error": "暂未确认会话已释放，请稍后重试。"}

    def has_queued_job(self, sid):
        with self.service.db() as conn:
            return conn.execute(
                "SELECT 1 FROM jobs WHERE source=? AND session=? AND status='queued'",
                (self.source, sid),
            ).fetchone() is not None

    def _recover(self):
        with self.lock:
            client, self.client = self.client, None
            self.active.clear()
            self.loaded.clear()
        if client:
            client.close()
        with self.service.db() as conn:
            conn.execute("UPDATE jobs SET status='unknown',message=?,updated_at=?,pid=NULL WHERE source=? AND status IN ('starting','running')",
                         (f"{self.runtime_name} 常驻服务连接中断，结果待确认。请先查看会话历史，不要重复提交。",
                          int(time.time()*1000), self.source))

    def run(self):
        root = self.service.db_path.parent
        with (root / (self.socket_stem + ".lock")).open("a") as lease:
            os.chmod(root / (self.socket_stem + ".lock"), 0o600)
            fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
            path = root / (self.socket_stem + ".sock")
            if path.exists():
                path.unlink()
            owner = self

            class Handler(socketserver.StreamRequestHandler):
                def handle(self):
                    self.request.settimeout(3)
                    try:
                        request = json.loads(self.rfile.readline(4096))
                        if not isinstance(request, dict):
                            return
                        if request.get("method") not in ("status", "wake", "release"):
                            return
                        if request["method"] == "wake":
                            owner.wake.set()
                        result = (owner.release(request["session"])
                                  if request["method"] == "release" else owner.status())
                        self.wfile.write((json.dumps(result) + "\n").encode())
                    except (OSError, ValueError):
                        pass

            class Server(socketserver.ThreadingUnixStreamServer):
                daemon_threads = True

            self.server = Server(str(path), Handler)
            os.chmod(path, 0o600)
            socket_thread = threading.Thread(target=self.server.serve_forever, daemon=True)
            socket_thread.start()
            self._recover()
            try:
                self.serve_jobs(root)
            finally:
                self._recover()
                self.server.shutdown()
                self.server.server_close()
                socket_thread.join(timeout=2)
                path.unlink(missing_ok=True)

    def serve_jobs(self, root):
        last_busy = time.monotonic()
        while not self.stop_event.is_set():
            if self.client and self.client.closed.is_set():
                self._recover()
            with self.service.db() as conn:
                queued = conn.execute(
                    "SELECT 1 FROM jobs WHERE source=? AND status='queued' LIMIT 1",
                    (self.source,),
                ).fetchone()
                enabled = self.service.runtime_enabled(conn, self.source)
            with self.lock:
                busy = bool(queued or self.active or self.releasing)
            if busy:
                last_busy = time.monotonic()
            if queued and not self.client:
                try:
                    client = self.client_type(self.binary(), root / self.stderr_name, self.notification)
                    with self.lock:
                        self.client = client
                    self.record("runtime_started", source=self.source, pid=client.proc.pid)
                except Exception as exc:
                    self.record("runtime_start_failed", source=self.source, error=str(exc)[:2000])
                    with self.service.db() as conn:
                        conn.execute(
                            "UPDATE jobs SET status='failed',message=?,updated_at=? WHERE source=? AND status='queued'",
                            (f"{self.runtime_name} 启动失败，请在 Mac 检查客户端。", int(time.time()*1000), self.source),
                        )
            if queued and self.client:
                self.dispatch()
            elif self.client and not busy and (not enabled or time.monotonic() - last_busy >= self.idle_timeout):
                self._recover()
            self.wake.wait(.3 if self.client else 1)
            self.wake.clear()

    def stop(self):
        self.stop_event.set()
        self.wake.set()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--db")
    parser.add_argument("--codex")
    args = parser.parse_args()
    runtime = RuntimeDaemon(ControlService(args.db, args.codex))
    signal.signal(signal.SIGTERM, lambda *_: runtime.stop())
    signal.signal(signal.SIGINT, lambda *_: runtime.stop())
    runtime.run()

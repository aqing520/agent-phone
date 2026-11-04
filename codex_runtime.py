"""Own one official Codex app-server process and dispatch durable phone turns.

Only wake/status are exposed on a user-private Unix socket. HTTP restarts do not
close Codex; a lost Codex connection marks in-flight messages unknown, never queued.
"""
import argparse
import fcntl
import json
import os
from pathlib import Path
import signal
import socketserver
import subprocess
import threading
import time

from control import ControlService, ControlError, session_context


class RpcError(Exception):
    pass


class AppServerClient:
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
                [binary, "app-server", "--stdio"], stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=self.log, text=True,
                encoding="utf-8", errors="replace", bufsize=1,
            )
        except Exception:
            self.log.close()
            raise
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()
        try:
            self.request("initialize", {"clientInfo": {"name": "agent_phone", "version": "0.2.0"},
                                        "capabilities": {"experimentalApi": True}})
            self.send({"method": "initialized", "params": {}})
        except Exception:
            self.close()
            raise

    def send(self, message):
        with self.lock:
            if self.closed.is_set():
                raise ConnectionError("Codex connection closed")
            self.proc.stdin.write(json.dumps(message, ensure_ascii=False) + "\n")
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
            raise TimeoutError("Codex RPC timed out")
        if "error" in slot:
            raise RpcError(slot["error"].get("message", "Codex rejected request"))
        if "disconnected" in slot:
            raise ConnectionError("Codex connection closed")
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
    def __init__(self, service):
        self.service = service
        self.client = None
        self.lock = threading.RLock()
        self.active = {}
        self.loaded = set()
        self.stop_event = threading.Event()
        self.wake = threading.Event()
        self.server = None

    def status(self):
        with self.lock:
            client = self.client
            return {"ready": bool(client and not client.closed.is_set()),
                    "appServerPid": client.proc.pid if client else None,
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
            if not loaded:
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
            rows = conn.execute("SELECT * FROM jobs WHERE source='codex' AND status='queued' ORDER BY created_at LIMIT 8").fetchall()
        for row in rows:
            with self.lock:
                client = self.client
                if not client or client.closed.is_set() or len(self.active) >= 4:
                    return
                if row["session"] in self.active:
                    continue
                with self.service.db() as conn:
                    result = conn.execute("UPDATE jobs SET status='starting',message=?,pid=?,updated_at=? WHERE id=? AND status='queued'",
                                          ("正在接入常驻会话。", client.proc.pid, int(time.time()*1000), row["id"]))
                if not result.rowcount:
                    continue
                self.active[row["session"]] = {"job": row["id"], "turn": None}
                threading.Thread(target=self._start_job, args=(row, client), daemon=True).start()

    def _recover(self):
        with self.lock:
            client, self.client = self.client, None
            if client:
                client.close()
            with self.service.db() as conn:
                conn.execute("UPDATE jobs SET status='unknown',message=?,updated_at=? WHERE source='codex' AND status IN ('starting','running')",
                             ("Codex 常驻服务连接中断，结果待确认。请先查看会话历史，不要重复提交。", int(time.time()*1000)))
            self.active.clear()
            self.loaded.clear()

    def run(self):
        root = self.service.db_path.parent
        with (root / "runtime.lock").open("a") as lease:
            os.chmod(root / "runtime.lock", 0o600)
            fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
            path = root / "runtime.sock"
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
                        if request.get("method") not in ("status", "wake"):
                            return
                        if request["method"] == "wake":
                            owner.wake.set()
                        self.wfile.write((json.dumps(owner.status()) + "\n").encode())
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
                while not self.stop_event.is_set():
                    if not self.client or self.client.closed.is_set():
                        self._recover()
                        try:
                            client = AppServerClient(self.service.codex, root / "app-server.stderr.log", self.notification)
                            with self.lock:
                                self.client = client
                            self.record("app_server_started", pid=client.proc.pid)
                        except Exception:
                            self.stop_event.wait(3)
                            continue
                    self.dispatch()
                    self.wake.wait(.3)
                    self.wake.clear()
            finally:
                self._recover()
                self.server.shutdown()
                self.server.server_close()
                socket_thread.join(timeout=2)
                path.unlink(missing_ok=True)

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

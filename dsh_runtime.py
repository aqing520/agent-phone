"""Manage a local DeepSeek Harness ACP process for durable phone turns."""
import argparse
import signal
import time
from uuid import UUID

from codex_runtime import AppServerClient, RpcError, RuntimeDaemon
from control import ControlService
from server import _dsh_events


class AcpClient(AppServerClient):
    arguments = ("acp",)
    envelope = {"jsonrpc": "2.0"}

    def initialize(self):
        result = self.request("initialize", {"protocolVersion": 1, "clientCapabilities": {}})
        capabilities = result.get("agentCapabilities", {}).get("sessionCapabilities", {})
        if result.get("protocolVersion") != 1 or not {"resume", "close"} <= capabilities.keys():
            raise RpcError("DeepSeek ACP does not support resume and close")

    def _server_request(self, message):
        if message["method"] == "session/request_permission":
            self.send({"id": message["id"], "result": {"outcome": {"outcome": "cancelled"}}})
        else:
            super()._server_request(message)


class DeepSeekRuntime(RuntimeDaemon):
    source = "dsh"
    runtime_name = "DeepSeek Harness"
    socket_stem = "dsh-runtime"
    client_type = AcpClient
    stderr_name = "dsh-acp.stderr.log"

    def binary(self):
        return self.service.dsh

    def notification(self, client, message):
        # The gateway reads committed history from the same session store.
        pass

    @staticmethod
    def committed_turn(sid, after_seq):
        deadline = time.monotonic() + 3
        while True:
            turn = next((event["data"] for event in reversed(_dsh_events(sid))
                         if event.get("type") == "turn/end" and event.get("seq", 0) > after_seq), None)
            if turn or time.monotonic() >= deadline:
                return turn
            time.sleep(.15)

    def _start_job(self, row, client):
        sid = row["session"]
        prompting = False
        turn = None
        try:
            params = {"cwd": row["cwd"], "mcpServers": []}
            with self.lock:
                loaded = sid in self.loaded
            if not row["rollout"]:
                result = client.request("session/new", params)
                new_sid = result["sessionId"]
                if str(UUID(new_sid)) != new_sid:
                    raise ValueError("Unexpected ACP session id")
                with self.lock:
                    if self.client is not client or client.closed.is_set():
                        raise ConnectionError("Runtime changed")
                    with self.service.db() as conn:
                        conn.execute("UPDATE jobs SET session=? WHERE id=?", (new_sid, row["id"]))
                    self.active[new_sid] = self.active.pop(sid)
                    sid = new_sid
            elif not loaded:
                client.request("session/resume", {**params, "sessionId": sid})
            with self.lock:
                if self.client is not client or client.closed.is_set():
                    raise ConnectionError("Runtime changed")
                self.loaded.add(sid)
                self.service.update(row["id"], "running", "DeepSeek 正在执行，回复会显示在会话中。")
            after_seq = max((event.get("seq", 0) for event in _dsh_events(sid)), default=0)
            prompting = True
            result = client.request("session/prompt", {
                "sessionId": sid, "prompt": [{"type": "text", "text": row["text"]}],
            }, timeout=3600)
            reason = result.get("stopReason")
            turn = self.committed_turn(sid, after_seq) if reason == "end_turn" else None
            kind = (turn or {}).get("reason", {}).get("kind")
            if kind == "completed":
                status, message = "completed", "执行完成，可以继续发送下一条消息。"
            elif kind in ("blocked", "error"):
                status, message = "failed", "DeepSeek 执行失败，请查看会话和 Mac 上的常驻服务日志。"
            elif reason == "end_turn" and not turn:
                status, message = "unknown", "未找到本轮结束记录，结果待确认。请先查看会话历史。"
            else:
                status, message = "interrupted", "DeepSeek 提前结束了本轮，请查看会话结果。"
        except RpcError as exc:
            detail = f"{exc} {exc.data}"
            self.record("dsh_request_failed", job=row["id"], error=detail[:2000])
            status = "failed"
            if not prompting and ("active write handle" in detail or "already active" in detail):
                message = "其他 DeepSeek 进程仍持有这段会话，请释放后重试。"
            elif not prompting:
                message = "无法打开 DeepSeek 会话，请检查项目目录和会话状态。"
            else:
                message = "DeepSeek 执行失败，请查看会话和 Mac 上的常驻服务日志。"
        except Exception:
            client.close()
            self.wake.set()
            return
        with self.lock:
            entry = self.active.get(sid)
            if self.client is client and entry and entry["job"] == row["id"]:
                turn_id = str(turn["turn"]) if turn and "turn" in turn else None
                self.service.update(row["id"], status, message, turn_id=turn_id)
                if status == "unknown":
                    with self.service.db() as conn:
                        conn.execute("UPDATE jobs SET pid=NULL WHERE id=?", (row["id"],))
                del self.active[sid]
        self.wake.set()

    def release(self, sid):
        with self.lock:
            client = self.client
            if not client or client.closed.is_set():
                return {"released": False, "error": "DeepSeek 常驻服务暂未就绪。"}
            if sid in self.active or sid in self.releasing or self.has_queued_job(sid):
                return {"released": False, "error": "会话正在处理，请稍后再释放。"}
            if sid not in self.loaded:
                return {"released": True}
            self.releasing[sid] = True
        try:
            client.request("session/close", {"sessionId": sid}, timeout=10)
            with self.lock:
                self.loaded.discard(sid)
            return {"released": True}
        except RpcError:
            return {"released": False, "error": "DeepSeek 未确认释放会话，请稍后重试。"}
        except (OSError, TimeoutError):
            client.close()
            self.wake.set()
            return {"released": False, "error": "连接已中断，请待 DeepSeek 恢复后重试。"}
        finally:
            with self.lock:
                self.releasing.pop(sid, None)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--db")
    parser.add_argument("--dsh")
    args = parser.parse_args()
    service = ControlService(args.db, dsh=args.dsh)
    if not service.dsh:
        parser.exit(1, "DeepSeek Harness CLI was not found\n")
    runtime = DeepSeekRuntime(service)
    signal.signal(signal.SIGTERM, lambda *_: runtime.stop())
    signal.signal(signal.SIGINT, lambda *_: runtime.stop())
    runtime.run()

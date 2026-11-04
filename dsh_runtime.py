"""Manage a local DeepSeek Harness ACP process for durable phone turns."""
import argparse
import json
import signal
import tempfile
import time
from pathlib import Path
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

    def __init__(self, service):
        super().__init__(service)
        self.model_options = {}

    def _recover(self):
        super()._recover()
        self.model_options.clear()

    def open_client(self, on_notification, *, extra_args=()):
        overlay = self.service.db_path.parent / "dsh-provider.patch.yml"
        provider_args = ("--patch", str(overlay)) if overlay.is_file() else ()
        return super().open_client(on_notification, extra_args=(*provider_args, *extra_args))

    def discover_models(self):
        # Use the real profile and credentials while isolating the probe's session.
        with tempfile.TemporaryDirectory(prefix="agent-phone-models-") as root:
            patch = Path(root) / "catalog.json"
            patch.write_text(json.dumps([
                {"id": "session-persistence-jsonl", "config": {"root": root + "/sessions"}},
                {"id": "session-projection-cache", "disabled": True},
            ]))
            client = self.open_client(lambda *_: None, extra_args=("--patch", str(patch)))
            try:
                # Provider catalog plugins hydrate asynchronously after initialization.
                time.sleep(1)
                result = client.request("session/new", {"cwd": root, "mcpServers": []}, timeout=8)
                models = {}
                for config in result.get("configOptions", []):
                    if config.get("category") != "model":
                        continue
                    for group in config.get("options", []):
                        for choice in group.get("options", [group]):
                            label = f"{group['name']} · {choice['name']}" if "group" in group else choice["name"]
                            models[choice["value"]] = label
                client.request("session/close", {"sessionId": result["sessionId"]}, timeout=5)
                return models
            finally:
                client.close()

    def select_model(self, client, sid, model):
        config = self.model_options.get(sid) or {}
        current = config.get("currentValue")
        if model.startswith("["):
            selected = model
        else:
            # Previously queued jobs contain a model name instead of a full route.
            provider = json.loads(current)[0] if current else None
            selected = next(
                (choice["value"] for item in config.get("options", [])
                 for choice in item.get("options", [item])
                 if json.loads(choice["value"])[1] == model
                 and (not provider or json.loads(choice["value"])[0] == provider)),
                None,
            )
        if not selected:
            raise RpcError("requested model unavailable")
        if selected != current:
            params = {"sessionId": sid, "configId": "model", "value": selected}
            try:
                result = client.request("session/set_config_option", params)
            except RpcError:
                # A newly started ACP can receive the selection before providers finish loading.
                time.sleep(1)
                try:
                    result = client.request("session/set_config_option", params)
                except RpcError as exc:
                    raise RpcError("requested model unavailable", exc.data) from exc
            self.remember_options(sid, result)

    def remember_options(self, sid, result):
        self.model_options[sid] = next(
            (config for config in result.get("configOptions", []) if config.get("category") == "model"),
            None,
        )

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
                result = client.request("session/resume", {**params, "sessionId": sid})
            if not loaded:
                self.remember_options(sid, result)
            with self.lock:
                if self.client is not client or client.closed.is_set():
                    raise ConnectionError("Runtime changed")
                self.loaded.add(sid)
                self.service.update(row["id"], "running", "DeepSeek 正在执行，回复会显示在会话中。")
            if row["model"]:
                self.select_model(client, sid, row["model"])
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
            elif "requested model unavailable" in detail:
                message = "所选 DeepSeek 模型路由不可用，请刷新列表或切换模型后重试。"
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
            if sid in self.active or sid in self.releasing or self.has_queued_job(sid):
                return {"released": False, "error": "会话正在处理，请稍后再释放。"}
            if not client or client.closed.is_set() or sid not in self.loaded:
                return {"released": True}
            self.releasing[sid] = True
        try:
            client.request("session/close", {"sessionId": sid}, timeout=10)
            with self.lock:
                self.loaded.discard(sid)
                self.model_options.pop(sid, None)
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

"""Durable message jobs dispatched by local agent runtimes."""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import sqlite3
import time
import uuid


ACTIVE = ("queued", "starting", "running")
MAX_MESSAGE = 12000
DATA_DIR = Path.home() / ".config" / "agent-phone" / "control"
BUNDLED_DSH = Path("/Applications/DeepSeek Harness.app/Contents/Resources/runtime/cli/bin/dsh")
RUNTIME_SOCKETS = {"codex": "runtime.sock", "dsh": "dsh-runtime.sock"}


class ControlError(Exception):
    def __init__(self, code, message, status=400):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


def session_context(path, with_policy=False):
    """Read runtime markers, not file recency, to reject known active turns."""
    cwd, busy, sandbox = None, False, "read-only"
    with open(path, encoding="utf-8", errors="replace") as stream:
        for line in stream:
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if not isinstance(row, dict):
                continue
            payload = row.get("payload") or {}
            if not isinstance(payload, dict):
                continue
            if row.get("type") == "session_meta":
                cwd = payload.get("cwd") or cwd
            if row.get("type") == "turn_context":
                policy = payload.get("sandbox_policy") or {}
                if isinstance(policy, dict) and policy.get("type") in ("read-only", "workspace-write", "danger-full-access"):
                    sandbox = "read-only" if policy.get("type") == "read-only" else "workspace-write"
            if row.get("type") == "event_msg":
                kind = payload.get("type")
                if kind == "task_started":
                    busy = True
                elif kind in ("task_complete", "turn_aborted", "task_aborted"):
                    busy = False
    if not cwd or not os.path.isdir(cwd):
        raise ControlError("workspace_missing", "原会话的项目目录不存在，请先在 Mac 上确认。", 409)
    if busy:
        raise ControlError("session_busy", "这段会话正在执行任务，请等当前任务结束后再发送。", 409)
    result = os.path.realpath(cwd)
    return (result, sandbox) if with_policy else result


class ControlService:
    def __init__(self, db_path=None, codex=None, enabled=True, dsh=None):
        self.db_path = Path(db_path) if db_path else DATA_DIR / "jobs.sqlite"
        self.codex = codex or shutil.which("codex")
        self.dsh = dsh or shutil.which("dsh") or (str(BUNDLED_DSH) if os.access(BUNDLED_DSH, os.X_OK) else None)
        self.enabled = enabled
        self.db_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.db_path.parent.chmod(0o700)
        with self.db() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("""CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY, source TEXT NOT NULL, session TEXT NOT NULL,
                fingerprint TEXT NOT NULL, text TEXT NOT NULL, cwd TEXT NOT NULL,
                rollout TEXT NOT NULL, status TEXT NOT NULL, message TEXT NOT NULL,
                created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL, pid INTEGER, turn_id TEXT
            )""")
            columns = {r[1] for r in conn.execute("PRAGMA table_info(jobs)")}
            if "turn_id" not in columns:
                conn.execute("ALTER TABLE jobs ADD COLUMN turn_id TEXT")
        self.db_path.chmod(0o600)

    @contextmanager
    def db(self):
        conn = sqlite3.connect(str(self.db_path), timeout=15)
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def runtime_call(self, method="status", *, source="codex", **params):
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
                sock.settimeout(14 if method == "release" else 2)
                sock.connect(str(self.db_path.parent / RUNTIME_SOCKETS[source]))
                sock.sendall((json.dumps({"method": method, **params}) + "\n").encode())
                data = b""
                while b"\n" not in data and len(data) < 65536:
                    part = sock.recv(4096)
                    if not part:
                        break
                    data += part
                result = json.loads(data.split(b"\n", 1)[0])
                return result if isinstance(result, dict) else {"ready": False}
        except (OSError, ValueError):
            return {"ready": False}

    def release(self, session, source="codex"):
        if not self.enabled:
            raise ControlError("unsupported_source", "当前网关未启用会话控制。", 403)
        try:
            if not isinstance(session, str) or str(uuid.UUID(session)) != session:
                raise ValueError()
        except ValueError:
            raise ControlError("invalid_id", "会话标识无效。")
        if not isinstance(source, str) or source not in RUNTIME_SOCKETS:
            raise ControlError("unsupported_source", "此客户端尚未接通会话控制。", 501)
        result = self.runtime_call("release", source=source, session=session)
        if not result.get("released"):
            raise ControlError("release_pending", result.get("error", "暂未确认会话已释放，请稍后重试。"), 409)
        return result

    def capabilities(self):
        runtime = self.runtime_call() if self.enabled and self.codex else {"ready": False}
        ready = bool(runtime.get("ready"))
        dsh_ready = self.enabled and bool(self.dsh and self.runtime_call(source="dsh").get("ready"))
        dsh_reason = ("发送仅在私人部署中开启，请将 Mac 网关绑定回环地址。" if not self.enabled else
                      "Mac 未找到 DeepSeek Harness CLI。" if not self.dsh else
                      "DeepSeek Harness 常驻服务尚未就绪。" if not dsh_ready else
                      "DeepSeek Harness 已连接，可连续发送消息。")
        reason = ("发送仅在私人部署中开启，请将 Mac 网关绑定回环地址。" if not self.enabled else
                  "Mac 未找到 Codex CLI。" if not self.codex else
                  "Codex 常驻服务尚未就绪，正在等待连接。" if not ready else
                  "Codex 常驻会话已连接，可连续发送消息。")
        return {
            "codex": {"available": bool(self.codex) and self.enabled and ready,
                      "mode": "app-server", "reason": reason, "release": ready,
                      "note": "同一会话一次执行一条消息；需要额外权限时请回 Mac 处理。",
                      "runtime": {k: runtime.get(k) for k in ("ready", "appServerPid", "loadedSessions")}},
            "workbuddy": {"available": False, "reason": "WorkBuddy 发送入口尚未接通。"},
            "dsh": {"available": dsh_ready, "mode": "acp", "reason": dsh_reason, "release": dsh_ready},
        }

    @staticmethod
    def public(row):
        return {"id": row["id"], "source": row["source"], "session": row["session"],
                "status": row["status"], "message": row["message"],
                "createdAt": row["created_at"], "updatedAt": row["updated_at"], "turnId": row["turn_id"]}

    def get(self, job_id):
        with self.db() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if row is None:
            raise ControlError("job_not_found", "没有找到这条发送记录。", 404)
        # A worker normally survives gateway restarts. Never re-run an ambiguous job.
        if row["status"] in ("starting", "running") and time.time() * 1000 - row["created_at"] > 30000:
            alive = False
            if row["pid"]:
                try:
                    os.kill(row["pid"], 0)
                    alive = True
                except OSError:
                    pass
            if not alive:
                self.update(job_id, "unknown", "执行进程已退出，结果待确认。请先查看会话历史，不要重复提交。")
                return self.get(job_id)
        return self.public(row)

    def update(self, job_id, status, message, pid=None, turn_id=None):
        with self.db() as conn:
            conn.execute("UPDATE jobs SET status=?, message=?, updated_at=?, pid=COALESCE(?,pid), turn_id=COALESCE(?,turn_id) WHERE id=?",
                         (status, message, int(time.time() * 1000), pid, turn_id, job_id))

    def acknowledge(self, job_id):
        job = self.get(job_id)
        if job["status"] != "unknown":
            raise ControlError("invalid_state", "只有结果待确认的记录可以手动结束。", 409)
        with self.db() as conn:
            row = conn.execute("SELECT pid FROM jobs WHERE id=?", (job_id,)).fetchone()
        if row["pid"]:
            try:
                os.kill(row["pid"], 0)
            except OSError:
                pass
            else:
                raise ControlError("worker_alive", "执行进程仍在运行，暂不能解除保护。", 409)
        self.update(job_id, "interrupted", "已确认并结束这条记录。没有自动重新发送。")
        return self.get(job_id)

    def submit(self, payload, find_session, resolve_workspace=None):
        if not isinstance(payload, dict):
            raise ControlError("invalid_request", "请求必须是 JSON 对象。")
        source, sid, text, job_id = (payload.get(k) for k in ("source", "session", "text", "requestId"))
        new_chat = "project" in payload
        if new_chat:
            sid = job_id
        try:
            if not isinstance(job_id, str) or str(uuid.UUID(job_id)) != job_id:
                raise ValueError()
            if not isinstance(sid, str) or str(uuid.UUID(sid)) != sid:
                raise ValueError()
        except (ValueError, AttributeError):
            raise ControlError("invalid_id", "发送请求或会话标识无效。")
        if not isinstance(source, str):
            raise ControlError("unsupported_source", "请选择已接入的客户端。")
        if not isinstance(text, str) or not text.strip() or len(text) > MAX_MESSAGE:
            raise ControlError("invalid_text", f"消息不能为空，且最多 {MAX_MESSAGE} 字。")
        text = text.strip()
        identity = [source, sid, text]
        if new_chat:
            identity.append(payload["project"])
        fingerprint = hashlib.sha256(json.dumps(identity, ensure_ascii=False).encode()).hexdigest()
        with self.db() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            if row:
                if row["fingerprint"] != fingerprint:
                    raise ControlError("request_conflict", "同一请求标识不能用于不同消息。", 409)
                return self.get(job_id)
        capability = self.capabilities().get(source)
        if not capability or not capability["available"]:
            code = "runtime_unavailable" if self.enabled and {"codex": self.codex, "dsh": self.dsh}.get(source) else "unsupported_source"
            raise ControlError(code, (capability or {}).get("reason", "此客户端尚未接通发送。"), 503 if code == "runtime_unavailable" else 501)
        if new_chat:
            if not resolve_workspace:
                raise ControlError("invalid_project", "新建会话需要选择项目。")
            cwd, path = resolve_workspace(payload["project"]), ""
        else:
            path = find_session(sid, source)
            if not path:
                raise ControlError("session_not_found", "没有找到这段本机会话，请刷新会话列表。", 404)
            if source == "dsh":
                cwd = path
                if not os.path.isabs(cwd) or not os.path.isdir(cwd):
                    raise ControlError("workspace_missing", "原会话的项目目录不存在，请先在 Mac 上确认。", 409)
                cwd = os.path.realpath(cwd)
            else:
                cwd = session_context(path)
        now = int(time.time() * 1000)
        with self.db() as conn:
            conn.execute("BEGIN IMMEDIATE")
            # Re-check inside the write transaction for concurrent identical POSTs.
            old = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            if old:
                if old["fingerprint"] != fingerprint:
                    raise ControlError("request_conflict", "同一请求标识不能用于不同消息。", 409)
                return self.public(old)
            active = conn.execute("SELECT id FROM jobs WHERE source=? AND session=? AND status IN ('queued','starting','running','unknown')",
                                  (source, sid)).fetchone()
            if active:
                raise ControlError("session_busy", "这段会话已有发送任务，或上次结果待确认，请先查看发送状态。", 409)
            conn.execute("INSERT INTO jobs (id,source,session,fingerprint,text,cwd,rollout,status,message,created_at,updated_at,pid) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                         (job_id, source, sid, fingerprint, text, cwd, str(path), "queued", "已受理，等待常驻会话处理。", now, now, None))
        # Wake is only a hint. The runtime also polls durable queued jobs, so losing
        # this IPC response never means the user message should be submitted again.
        self.runtime_call("wake", source=source)
        return self.get(job_id)

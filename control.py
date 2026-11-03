"""Durable, single-writer message jobs. Each job runs outside the HTTP process.

The first adapter uses Codex CLI resume. It never steals a desktop writer lock,
changes account settings, or automatically grants tool approvals.
"""
import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
import uuid


ACTIVE = ("queued", "starting", "running")
MAX_MESSAGE = 12000
DATA_DIR = Path.home() / ".config" / "agent-phone" / "control"


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
    def __init__(self, db_path=None, codex=None, enabled=True):
        self.db_path = Path(db_path) if db_path else DATA_DIR / "jobs.sqlite"
        self.codex = codex or shutil.which("codex")
        self.enabled = enabled
        self.db_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.db_path.parent.chmod(0o700)
        with self.db() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("""CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY, source TEXT NOT NULL, session TEXT NOT NULL,
                fingerprint TEXT NOT NULL, text TEXT NOT NULL, cwd TEXT NOT NULL,
                rollout TEXT NOT NULL, status TEXT NOT NULL, message TEXT NOT NULL,
                created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL, pid INTEGER
            )""")
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

    def capabilities(self):
        return {
            "codex": {
                "available": bool(self.codex) and self.enabled, "mode": "cli-resume",
                "reason": ("发送仅在私人部署中开启，请将 Mac 网关绑定回环地址。" if not self.enabled else
                           "CLI 续接原会话；桌面可能需要重新打开会话。" if self.codex else "Mac 未找到 Codex CLI。"),
                "note": "桌面持有会话时会拒绝发送；不要在两端同时操作同一会话。需要额外授权时请回 Mac 处理。",
            },
            "workbuddy": {"available": False, "reason": "WorkBuddy 发送入口尚未接通。"},
            "dsh": {"available": False, "reason": "DeepSeek Harness 发送入口尚未接通。"},
        }

    @staticmethod
    def public(row):
        return {"id": row["id"], "source": row["source"], "session": row["session"],
                "status": row["status"], "message": row["message"],
                "createdAt": row["created_at"], "updatedAt": row["updated_at"]}

    def get(self, job_id):
        with self.db() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if row is None:
            raise ControlError("job_not_found", "没有找到这条发送记录。", 404)
        # A worker normally survives gateway restarts. Never re-run an ambiguous job.
        if row["status"] in ACTIVE and time.time() * 1000 - row["created_at"] > 30000:
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

    def update(self, job_id, status, message, pid=None):
        with self.db() as conn:
            conn.execute("UPDATE jobs SET status=?, message=?, updated_at=?, pid=COALESCE(?,pid) WHERE id=?",
                         (status, message, int(time.time() * 1000), pid, job_id))

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

    def submit(self, payload, find_session):
        if not isinstance(payload, dict):
            raise ControlError("invalid_request", "请求必须是 JSON 对象。")
        source, sid, text, job_id = (payload.get(k) for k in ("source", "session", "text", "requestId"))
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
        fingerprint = hashlib.sha256(json.dumps([source, sid, text], ensure_ascii=False).encode()).hexdigest()
        with self.db() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            if row:
                if row["fingerprint"] != fingerprint:
                    raise ControlError("request_conflict", "同一请求标识不能用于不同消息。", 409)
                return self.get(job_id)
        capability = self.capabilities().get(source)
        if not capability or not capability["available"]:
            raise ControlError("unsupported_source", (capability or {}).get("reason", "此客户端尚未接通发送。"), 501)
        path = find_session(sid, source)
        if not path:
            raise ControlError("session_not_found", "没有找到这段本机会话，请刷新会话列表。", 404)
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
            conn.execute("INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                         (job_id, source, sid, fingerprint, text, cwd, str(path), "queued", "已受理，准备启动 Codex。", now, now, None))
        try:
            log_path = self.db_path.parent / (job_id + ".log")
            fd = os.open(str(log_path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w") as log:
                worker = subprocess.Popen(
                    [sys.executable, str(Path(__file__).resolve()), "--worker", job_id,
                     "--db", str(self.db_path), "--codex", self.codex],
                    stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                    start_new_session=True, close_fds=True,
                )
            with self.db() as conn:
                conn.execute("UPDATE jobs SET pid=? WHERE id=?", (worker.pid, job_id))
            threading.Thread(target=worker.wait, daemon=True).start()
        except OSError:
            self.update(job_id, "failed", "无法启动 Codex 执行进程，消息未送出。")
        return self.get(job_id)


def run_worker(service, job_id):
    with service.db() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    if not row or row["status"] != "queued":
        return
    service.update(job_id, "starting", "正在启动 Codex CLI。", os.getpid())
    error_path = service.db_path.parent / (job_id + ".stderr.log")
    proc = None
    try:
        # A desktop turn may have started since the HTTP request was accepted.
        _, sandbox = session_context(row["rollout"], with_policy=True)
        fd = os.open(str(error_path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as err:
            proc = subprocess.Popen(
                [service.codex, "--ask-for-approval", "never", "exec", "--sandbox", sandbox,
                 "--json", "--skip-git-repo-check", "resume", row["session"], "-"],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=err,
                cwd=row["cwd"], text=True, encoding="utf-8", errors="replace",
            )
            proc.stdin.write(row["text"] + "\n")
            proc.stdin.close()
            completed, failed = False, False
            for line in proc.stdout:
                print(line, end="", flush=True)
                try:
                    event = json.loads(line)
                except ValueError:
                    continue
                kind = event.get("type")
                if kind == "thread.started" and event.get("thread_id") != row["session"]:
                    raise RuntimeError("Codex resumed an unexpected thread")
                if kind == "turn.started":
                    service.update(job_id, "running", "Codex 正在执行，回复会显示在会话中。")
                elif kind == "turn.completed":
                    completed = True
                elif kind in ("turn.failed", "error"):
                    failed = True
            code = proc.wait()
        if code == 0 and completed and not failed:
            service.update(job_id, "completed", "执行完成。桌面若未更新，请重新打开会话。")
        else:
            stderr = error_path.read_text(encoding="utf-8", errors="replace")
            if "active writer" in stderr or "thread-store conflict" in stderr:
                message = "桌面仍持有这段会话，CLI 无法接管。请先在 Mac 释放会话后重试；本次未执行。"
            elif "auth" in stderr.lower() or "not logged in" in stderr.lower():
                message = "Codex 登录或连接失败，请在 Mac 检查 CLI 登录状态和网络。"
            else:
                message = "Codex 执行失败或需要额外权限。请查看会话及 Mac 上的执行日志后再决定是否重试。"
            service.update(job_id, "failed", message)
    except ControlError as exc:
        service.update(job_id, "failed", exc.message)
    except (FileNotFoundError, PermissionError):
        if proc is None:
            service.update(job_id, "failed", "会话文件或 Codex CLI 不可用，本次未开始执行。")
        else:
            service.update(job_id, "unknown", "执行文件访问异常，结果待确认。请先检查会话历史。")
    except Exception:
        if proc and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
        service.update(job_id, "unknown", "执行异常，结果待确认。请先检查会话历史，避免重复执行。")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker", required=True)
    parser.add_argument("--db", required=True)
    parser.add_argument("--codex", required=True)
    args = parser.parse_args()
    run_worker(ControlService(args.db, args.codex), args.worker)

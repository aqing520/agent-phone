#!/usr/bin/env python3
"""
agent-phone 本地网关
- 静态托管前端（本目录）
- GET /api/usage   : 解析 ~/.workbuddy/projects/ 会话 JSONL，返回真实用量
- GET /api/sessions: 返回真实会话列表（标题/项目/时间/token）

解析语义对齐 TokenTracker 的 WorkBuddy reader（MIT）：
- usage 出现在任意带 providerData.rawUsage / providerData.usage 的记录上
  （function_call 和 assistant message 都有），按 providerData.messageId 去重
- prompt_tokens 含缓存（读+写），需拆分：
    cacheRead   = max(cached_tokens, prompt_cache_hit_tokens, cache_read_input_tokens)
    cacheCreate = max(cache_creation_input_tokens, prompt_cache_write_tokens)
    input       = prompt_tokens - cacheRead - cacheCreate
    reasoning   = min(completion_tokens, completion_tokens_details.reasoning_tokens)
    output      = completion_tokens - reasoning
- 模型名日志里是占位（auto），trace 汇总才有真实模型名
默认供局域网使用；私人中转部署通过环境变量绑定回环地址。
无应用层鉴权，请勿直接暴露到公网。
"""
import json
import glob
import os
import re
import threading
import time
import ipaddress
import secrets
from urllib.parse import urlsplit
from datetime import datetime
from collections import defaultdict
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from control import ControlService, ControlError

ROOT = os.path.dirname(os.path.abspath(__file__))
WORKBUDDY = os.path.expanduser("~/.workbuddy")
CODEX = os.path.expanduser("~/.codex")
DSH = os.path.expanduser(os.environ.get("DSH_HOME") or "~/.dsh")
HOST = os.environ.get("AGENT_PHONE_HOST", "0.0.0.0")
PORT = int(os.environ.get("AGENT_PHONE_PORT", "5173"))
STATIC_FILES = {
    "/", "/index.html", "/app.js", "/styles.css",
    "/manifest.webmanifest", "/icon-192.png", "/icon-512.png",
}

_lock = threading.Lock()
_cache = {"at": 0.0, "data": None}
_cache2 = {"at": 0.0, "data": None}
CACHE_TTL = 5.0
CSRF_TOKEN = secrets.token_urlsafe(32)
_control_service = None
_control_lock = threading.Lock()


def get_control_service():
    global _control_service
    with _control_lock:
        if _control_service is None:
            _control_service = ControlService(enabled=HOST in ("127.0.0.1", "::1", "localhost"))
        return _control_service


def nn(v):
    try:
        n = int(v)
        return n if n > 0 else 0
    except (TypeError, ValueError):
        return 0


def normalize_usage(u):
    """把 OpenAI / Anthropic / camelCase 三种形态归一化"""
    if not isinstance(u, dict):
        return None

    # camelCase（providerData.usage / message.usage）
    if "inputTokens" in u or "input_tokens" in u:
        prompt = nn(u.get("inputTokens", u.get("input_tokens")))
        completion = nn(u.get("outputTokens", u.get("output_tokens")))
        cached = 0
        det = u.get("inputTokensDetails")
        if isinstance(det, list) and det:
            cached = nn(det[0].get("cached_tokens"))
        elif isinstance(det, dict):
            cached = nn(det.get("cached_tokens"))
        cache_read = max(cached, nn(u.get("cache_read_input_tokens")))
        cache_create = nn(u.get("cache_creation_input_tokens"))
        reasoning = 0
        odet = u.get("outputTokensDetails")
        if isinstance(odet, list) and odet:
            reasoning = min(completion, nn(odet[0].get("reasoning_tokens")))
        elif isinstance(odet, dict):
            reasoning = min(completion, nn(odet.get("reasoning_tokens")))
    else:
        # rawUsage（snake_case，OpenAI/DeepSeek 形态）
        prompt = nn(u.get("prompt_tokens"))
        completion = nn(u.get("completion_tokens"))
        pdet = u.get("prompt_tokens_details") or {}
        cdet = u.get("completion_tokens_details") or {}
        cache_read = max(
            nn(pdet.get("cached_tokens")),
            nn(u.get("prompt_cache_hit_tokens")),
            nn(u.get("cache_read_input_tokens")),
        )
        cache_create = max(
            nn(u.get("cache_creation_input_tokens")),
            nn(u.get("prompt_cache_write_tokens")),
        )
        reasoning = min(completion, nn(cdet.get("reasoning_tokens")))

    output = max(0, completion - reasoning)
    inp = max(0, prompt - cache_read - cache_create)
    if inp == 0 and output == 0 and cache_read == 0 and cache_create == 0 and reasoning == 0:
        return None
    return {
        "input": inp,
        "cache_read": cache_read,
        "cache_create": cache_create,
        "output": output,
        "reasoning": reasoning,
        "total": inp + output + reasoning + cache_read + cache_create,
    }


def iter_session_files():
    """递归收集 ~/.workbuddy/projects 下所有 *.jsonl（含 subagents）"""
    projects = os.path.join(WORKBUDDY, "projects")
    for pattern in (projects + "/**/*.jsonl",):
        for f in glob.glob(pattern, recursive=True):
            yield f


def parse_session_file(path):
    """解析单个会话文件，返回 (sessions_dict, rounds_list)"""
    session = {
        "id": os.path.basename(path)[:-6],
        "file": path,
        "title": None,
        "project": os.path.basename(os.path.dirname(path)),
        "cwd": None,
        "startedAt": None,
        "endedAt": None,
        "messages": 0,
        "input": 0, "cache_read": 0, "cache_create": 0,
        "output": 0, "reasoning": 0, "total": 0,
        "rounds": 0,
        "models": {},
    }
    seen = set()
    try:
        mtime = os.path.getmtime(path)
        session["mtime"] = mtime
    except OSError:
        session["mtime"] = 0

    try:
        fh = open(path, encoding="utf-8", errors="replace")
    except OSError:
        return session, []

    rounds = []
    with fh:
        for line in fh:
            if len(line) < 3:
                continue
            try:
                d = json.loads(line)
            except Exception:
                continue
            if not isinstance(d, dict):
                continue

            t = d.get("type")
            if t == "ai-title":
                title = d.get("aiTitle") or d.get("title")
                if isinstance(title, str) and title.strip():
                    session["title"] = title.strip()

            ts = d.get("timestamp")
            ts_ms = nn(ts) or _iso_ms(ts)
            if ts_ms:
                if session["startedAt"] is None or ts_ms < session["startedAt"]:
                    session["startedAt"] = ts_ms
                if session["endedAt"] is None or ts_ms > session["endedAt"]:
                    session["endedAt"] = ts_ms

            if t == "message":
                session["messages"] += 1
            if session["cwd"] is None and isinstance(d.get("cwd"), str):
                session["cwd"] = d["cwd"]
                session["project"] = project_label(d["cwd"], session["project"])

            # ---- usage 提取（任意记录类型） ----
            provider = d.get("providerData")
            if not isinstance(provider, dict):
                provider = {}
            raw = provider.get("rawUsage") or provider.get("usage")
            if not isinstance(raw, dict):
                msg = d.get("message")
                raw = msg.get("usage") if isinstance(msg, dict) else None
            if not isinstance(raw, dict):
                continue

            # 去重：providerData.messageId 是同一轮往返的稳定 key
            mid = provider.get("messageId") or d.get("uuid") or d.get("id")
            if not mid and ts_ms:
                mid = f"{session['id']}:{ts_ms}"
            if not mid or mid in seen:
                continue
            norm = normalize_usage(raw)
            seen.add(mid)
            if norm is None:
                continue

            session["rounds"] += 1
            for k in ("input", "cache_read", "cache_create", "output", "reasoning", "total"):
                session[k] += norm[k]
            # 记下每次调用用的模型，用来把用量归到具体智能体
            model = provider.get("model") or "auto"
            mb = session["models"].setdefault(model, {"tokens": 0, "rounds": 0})
            mb["tokens"] += norm["total"]
            mb["rounds"] += 1
            rounds.append({
                "ts": ts_ms or session.get("endedAt") or 0,
                **norm,
            })
    return session, rounds


# ============================================================
# Codex（~/.codex）
# 会话是 rollout-*.jsonl，每行 {type, payload}
#   session_meta          -> session_id / cwd
#   turn_context          -> model
#   token_usage_record    -> payload.usage（response_id 唯一，天然可去重）
#   response_item/message -> 正文（role=user 时看 content_item_kinds 里有 user.text）
# 用量语义：input_tokens 含 cached，total_tokens = input + output
# ============================================================


def _iso_ms(v):
    if not isinstance(v, str):
        return 0
    try:
        from datetime import timezone
        s = v.replace("Z", "+00:00")
        return int(datetime.fromisoformat(s).astimezone(timezone.utc).timestamp() * 1000)
    except Exception:
        return 0


def _blank_session(sid, source, path):
    return {
        "id": sid,
        "source": source,
        "file": path,
        "title": None,
        "project": None,
        "cwd": None,
        "startedAt": None,
        "endedAt": None,
        "messages": 0,
        "input": 0, "cache_read": 0, "cache_create": 0,
        "output": 0, "reasoning": 0, "total": 0,
        "rounds": 0,
        "models": {},
    }


def _norm_codex_usage(u):
    """Codex 的 usage -> 统一结构"""
    if not isinstance(u, dict):
        return None
    prompt = nn(u.get("input_tokens"))
    cached = nn(u.get("cached_input_tokens"))
    cache_write = nn(u.get("cache_write_input_tokens"))
    completion = nn(u.get("output_tokens"))
    reasoning = min(completion, nn(u.get("reasoning_output_tokens")))
    if not (prompt or completion or cached or cache_write):
        return None
    output = max(0, completion - reasoning)
    uncached = max(0, prompt - cached)
    total = max(nn(u.get("total_tokens")),
                uncached + cached + cache_write + output + reasoning)
    return {
        "input": uncached,
        "cache_read": cached,
        "cache_create": cache_write,
        "output": output,
        "reasoning": reasoning,
        "total": total,
    }


def codex_titles():
    """session_index.jsonl: {"id":..., "thread_name":...}"""
    out = {}
    try:
        with open(os.path.join(CODEX, "session_index.jsonl"),
                  encoding="utf-8", errors="replace") as fh:
            for line in fh:
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                if d.get("id") and d.get("thread_name"):
                    out[d["id"]] = d["thread_name"]
    except OSError:
        pass
    return out


def iter_codex_files():
    for f in glob.glob(os.path.join(CODEX, "sessions", "**", "rollout-*.jsonl"),
                       recursive=True):
        yield f


def parse_codex_file(path, titles=None):
    titles = titles or {}
    sid = None
    base = os.path.basename(path)
    m = re.search(r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})", base)
    if m:
        sid = m.group(1)
    s = _blank_session(sid or base, "codex", path)
    try:
        s["mtime"] = os.path.getmtime(path)
    except OSError:
        s["mtime"] = 0

    seen = set()
    s["daily_usage"] = []
    model = None
    try:
        fh = open(path, encoding="utf-8", errors="replace")
    except OSError:
        return s

    with fh:
        for line in fh:
            if len(line) < 3:
                continue
            try:
                d = json.loads(line)
            except Exception:
                continue
            if not isinstance(d, dict):
                continue
            t = d.get("type")
            p = d.get("payload") if isinstance(d.get("payload"), dict) else {}
            ts = _iso_ms(d.get("timestamp"))
            if ts:
                if s["startedAt"] is None or ts < s["startedAt"]:
                    s["startedAt"] = ts
                if s["endedAt"] is None or ts > s["endedAt"]:
                    s["endedAt"] = ts

            if t == "session_meta":
                s["id"] = p.get("id") or p.get("session_id") or s["id"]
                if isinstance(p.get("cwd"), str):
                    s["cwd"] = p["cwd"]
            elif t == "turn_context":
                if p.get("model"):
                    model = p["model"]
            elif t == "response_item" and p.get("type") == "message":
                if p.get("role") in ("user", "assistant"):
                    s["messages"] += 1
            elif t == "token_usage_record":
                rid = p.get("response_id") or f"{p.get('turn_id')}:{ts}"
                if rid in seen:
                    continue
                seen.add(rid)
                norm = _norm_codex_usage(p.get("usage"))
                if not norm:
                    continue
                s["rounds"] += 1
                s["daily_usage"].append((ts, norm["total"]))
                for k in ("input", "cache_read", "cache_create", "output", "reasoning", "total"):
                    s[k] += norm[k]
                mb = s["models"].setdefault(model or "codex", {"tokens": 0, "rounds": 0})
                mb["tokens"] += norm["total"]
                mb["rounds"] += 1

    s["title"] = titles.get(s["id"]) or _codex_first_user_text(path)
    s["project"] = project_label(s["cwd"], "codex")
    if not s["endedAt"] and s.get("mtime"):
        s["endedAt"] = int(s["mtime"] * 1000)
    return s


def _codex_first_user_text(path):
    """没有 thread_name 时，拿第一条真实用户消息当标题"""
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if '"user.text"' not in line:
                    continue
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                p = d.get("payload") or {}
                if p.get("type") != "message" or p.get("role") != "user":
                    continue
                md = p.get("internal_chat_message_metadata_passthrough") or {}
                if "user.text" not in (md.get("content_item_kinds") or []):
                    continue
                txt = block_text(p.get("content")).strip()
                if txt:
                    return txt.splitlines()[0][:60]
    except OSError:
        pass
    return None


# ============================================================
# DeepSeek Harness（~/.dsh）
# 统计口径在 session_projcache/sessions/<id>.json 里（权威）：
#   rows.tokenUsage.val.totals = {uncachedInputTokens, outputTokens, cacheReadTokens, cacheWriteTokens}
#   rows.title.val / rows.sessionStats.val.turns / identity.cwd createdAt
# 正文在 sessions/<proj>/<session>/session.v4.jsonl.zstd（zstd 压缩的事件流）
# ============================================================


def iter_dsh_cache():
    return glob.glob(os.path.join(DSH, "storages", "session_projcache", "sessions", "*.json"))


def _dsh_meta(cache_file):
    with open(cache_file, encoding="utf-8", errors="replace") as fh:
        d = json.load(fh)
    rec = d.get("record") or {}
    rows = rec.get("rows") or {}
    ident = rec.get("identity") or {}
    tu = ((rows.get("tokenUsage") or {}).get("val") or {})
    tot = tu.get("totals") or {}
    return {
        "cwd": ident.get("cwd"),
        "createdAt": nn(ident.get("createdAt")),
        "title": ((rows.get("title") or {}).get("val")),
        "turns": nn(((rows.get("sessionStats") or {}).get("val") or {}).get("turns")),
        "uncached": nn(tot.get("uncachedInputTokens")),
        "output": nn(tot.get("outputTokens")),
        "cache_read": nn(tot.get("cacheReadTokens")),
        "cache_write": nn(tot.get("cacheWriteTokens")),
    }


def dsh_session_dir(sid):
    hits = glob.glob(os.path.join(DSH, "sessions", "**", sid), recursive=True)
    for h in hits:
        if os.path.isdir(h):
            return h
    return None


def _dsh_events(sid):
    """解压并解析事件流，带 mtime 缓存"""
    d = dsh_session_dir(sid)
    if not d:
        return []
    path = None
    for name in ("session.v4.jsonl.zstd", "session.jsonl.zstd"):
        cand = os.path.join(d, name)
        if os.path.exists(cand):
            path = cand
            break
    if not path:
        return []
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        mtime = 0
    key = "dsh::" + path
    hit = _msg_cache.get(key)
    if hit and hit[0] == mtime:
        return hit[1]

    raw = b""
    try:
        import subprocess
        raw = subprocess.run(["zstd", "-dc", path], capture_output=True, timeout=20).stdout
    except Exception:
        raw = b""
    events = []
    for line in raw.decode("utf-8", "replace").splitlines():
        if len(line) < 3:
            continue
        try:
            e = json.loads(line)
        except Exception:
            continue
        if isinstance(e, dict):
            events.append(e)
    _msg_cache[key] = (mtime, events)
    return events


def parse_dsh_sessions():
    out = []
    for cf in iter_dsh_cache():
        sid = os.path.basename(cf)[:-5]
        try:
            meta = _dsh_meta(cf)
        except Exception:
            continue
        s = _blank_session(sid, "dsh", cf)
        try:
            s["mtime"] = os.path.getmtime(cf)
        except OSError:
            s["mtime"] = 0
        s["title"] = meta["title"]
        s["cwd"] = meta["cwd"]
        s["project"] = project_label(s["cwd"], "dsh")
        s["startedAt"] = meta["createdAt"] or None
        s["input"] = meta["uncached"]
        s["output"] = meta["output"]
        s["cache_read"] = meta["cache_read"]
        s["cache_create"] = meta["cache_write"]
        s["total"] = meta["uncached"] + meta["output"] + meta["cache_read"] + meta["cache_write"]
        s["rounds"] = meta["turns"]
        # 没有 sessionStats 的会话，数 assistant/message 事件
        ev = _dsh_events(sid)
        if not s["rounds"] or not s["total"]:
            calls = sum(1 for e in ev if e.get("type") == "assistant/message")
            msgs = sum(1 for e in ev if e.get("type") in ("user/message", "assistant/message"))
            s["rounds"] = s["rounds"] or calls
            s["messages"] = msgs
            if not s["total"]:
                for e in ev:
                    if e.get("type") != "assistant/message":
                        continue
                    u = (e.get("data") or {}).get("usage") or {}
                    s["input"] += nn(u.get("inputTokens"))
                    s["output"] += nn(u.get("outputTokens"))
                    s["cache_read"] += nn(u.get("cacheReadTokens"))
                    s["cache_create"] += nn(u.get("cacheWriteTokens"))
                    s["total"] += nn(u.get("totalTokens"))
        if s["total"] or s["rounds"]:
            model = "deepseek-harness"
            for e in ev:
                if e.get("type") == "assistant/message":
                    m = (((e.get("data") or {}).get("message") or {}).get("source") or {}).get("model")
                    if m:
                        model = m
                        break
            s["models"][model] = {"tokens": s["total"], "rounds": s["rounds"]}
        s["daily_usage"] = []
        for event in ev:
            if event.get("type") != "assistant/message":
                continue
            u = (event.get("data") or {}).get("usage") or {}
            amount = nn(u.get("totalTokens")) or sum(nn(u.get(k)) for k in ("inputTokens", "outputTokens", "cacheReadTokens", "cacheWriteTokens"))
            s["daily_usage"].append((nn(event.get("time")) or _iso_ms(event.get("time")), amount))
        ended = s.get("mtime")
        if ended:
            s["endedAt"] = int(ended * 1000)
        out.append(s)
    return out


def parse_dsh_messages(sid):
    out = []
    for e in _dsh_events(sid):
        t = e.get("type")
        data = e.get("data") or {}
        if t == "user/message":
            src = (data.get("source") or {}).get("kind")
            if src != "user":
                continue
            text = block_text(data.get("content")).strip()
            if not text:
                continue
            out.append({"role": "user", "text": text, "ts": nn(e.get("time"))})
        elif t == "assistant/message":
            msg = data.get("message") or {}
            text = block_text(msg.get("content")).strip()
            if not text:
                continue
            out.append({"role": "assistant", "text": text, "ts": nn(e.get("time"))})
    for m in out:
        if len(m["text"]) > MAX_CHARS:
            m["text"] = m["text"][:MAX_CHARS]
            m["truncated"] = True
        else:
            m["truncated"] = False
    return out[-200:]


_ANNOT_BLOCK_RE = re.compile(
    r"<response-annotations>\s*(\[[\s\S]*?\])\s*</response-annotations>"
)
_ANNOT_HEAD_RE = re.compile(r"^[\s\S]*?# Response annotations:")


def clean_codex_text(text):
    """剥掉 Codex「划选批注」类系统注入，还原用户真正输入的话。

    这种消息是 IDE 扩展拼出来的：开头一大段 '# Response annotations:' 说明，
    <response-annotations> 数组里每项 = 用户划选的上文(text) + 用户批注(annotation)，
    最后 '## My request:' 后面才是普通正文。全部直接展示会像乱码。
    """
    if "# Response annotations:" not in text:
        return text
    m = _ANNOT_BLOCK_RE.search(text)
    if not m:
        return text

    notes = []
    try:
        for a in json.loads(m.group(1)):
            sel = (a.get("text") or "").strip()
            cmt = (a.get("annotation") or "").strip()
            if sel and cmt:
                notes.append(f'批注上文「{sel}」：{cmt}')
            elif sel:
                notes.append(f'批注上文「{sel}」')
            elif cmt:
                notes.append(cmt)
    except Exception:
        pass

    # 数组之后的普通正文（去掉 '## My request:' 标记）
    rest = text[m.end():]
    rest = re.sub(r"^\s*##\s*My request:\s*", "", rest).strip()

    if notes:
        body = "\n".join(notes)
        if rest:
            body += "\n\n" + rest
        return body
    return rest or text


def parse_codex_messages(path):
    out = []
    try:
        fh = open(path, encoding="utf-8", errors="replace")
    except OSError:
        return out
    with fh:
        for line in fh:
            if len(line) < 3:
                continue
            try:
                d = json.loads(line)
            except Exception:
                continue
            if d.get("type") != "response_item":
                continue
            p = d.get("payload") or {}
            if p.get("type") != "message":
                continue
            role = p.get("role")
            if role not in ("user", "assistant"):
                continue
            md = p.get("internal_chat_message_metadata_passthrough") or {}
            if role == "user" and "user.text" not in (md.get("content_item_kinds") or []):
                continue
            # phase: commentary / final_answer 都是助手说的话，都要留
            text = clean_codex_text(block_text(p.get("content")).strip())
            if role == "assistant":
                # 助手按指令输出的内联标记，对人无意义
                text = re.sub(r"\s*:codex-annotation\{index=\"\d+\"\}", "", text).strip()
            if not text:
                continue
            cut = len(text) > MAX_CHARS
            out.append({
                "role": role,
                "text": text[:MAX_CHARS],
                "truncated": cut,
                "ts": _iso_ms(d.get("timestamp")),
            })
    return out[-200:]


def find_codex_file(session_id):
    if not session_id or "/" in session_id or ".." in session_id:
        return None
    hits = glob.glob(os.path.join(CODEX, "sessions", "**", f"*{session_id}.jsonl"),
                     recursive=True)
    return hits[0] if hits else None


def find_session_file(session_id):
    """按 sessionId 找到对应 JSONL"""
    if not session_id or "/" in session_id or ".." in session_id:
        return None
    pat = os.path.join(WORKBUDDY, "projects", "**", session_id + ".jsonl")
    hits = glob.glob(pat, recursive=True)
    return hits[0] if hits else None


_SYS_RE = re.compile(r"<system-reminder[\s\S]*?</system-reminder>", re.I)
_UQ_RE = re.compile(r"<user_query>([\s\S]*?)</user_query>", re.I)
_TS_DIR_RE = re.compile(r"^\d{4}-\d{2}-\d{2}-\d{2}-\d{2}-\d{2}$")
# 这些是运行时注入给模型的系统事件，不是用户说的话
_NOISE_MARKERS = ("<task-notification", "NOT USER INPUT", "<user-prompt-submit-hook")


def project_label(cwd, fallback):
    """把 WorkBuddy 自动创建的时间戳工作区换成可读名字"""
    if not cwd:
        return fallback
    cwd = cwd.rstrip("/")
    base = os.path.basename(cwd)
    parent = os.path.basename(os.path.dirname(cwd))
    if _TS_DIR_RE.match(base):
        return "临时工作区" if parent == "WorkBuddy" else (parent or fallback)
    return base or fallback


def clean_wb_text(text):
    """用户消息里塞了大量注入上下文，只取 <user_query> 正文"""
    m = _UQ_RE.search(text)
    text = m.group(1).strip() if m else _SYS_RE.sub("", text).strip()
    if any(k in text for k in _NOISE_MARKERS):
        return ""
    return text


def block_text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for b in content:
            if not isinstance(b, dict):
                continue
            if b.get("type") in ("input_text", "output_text", "text"):
                t = b.get("text")
                if isinstance(t, str) and t.strip():
                    parts.append(t)
        return "\n".join(parts)
    return ""


MAX_CHARS = 6000
_msg_cache = {}


def parse_messages(path):
    """解析单个会话的正文消息（只取 type=message）"""
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        mtime = 0
    hit = _msg_cache.get(path)
    if hit and hit[0] == mtime:
        return hit[1]

    title = None
    meta = {"count": 0}
    out = []
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if len(line) < 3:
                continue
            try:
                d = json.loads(line)
            except Exception:
                continue
            if not isinstance(d, dict):
                continue
            t = d.get("type")
            ts = d.get("timestamp")
            if t == "ai-title":
                tt = d.get("aiTitle") or d.get("title")
                if isinstance(tt, str) and tt.strip():
                    title = tt.strip()
                continue
            if t != "message":
                continue
            role = d.get("role")
            if role not in ("user", "assistant"):
                continue
            text = block_text(d.get("content"))
            if role == "user":
                text = clean_wb_text(text)
            else:
                text = text.strip()
                if text in ("Interrupted by user", ""):
                    continue
            if not text:
                continue
            cut = len(text) > MAX_CHARS
            out.append({
                "role": role,
                "text": text[:MAX_CHARS],
                "truncated": cut,
                "ts": ts if isinstance(ts, (int, float)) else 0,
            })
    out = out[-200:]
    meta["count"] = len(out)
    data = {"title": title, "messages": out, **meta}
    _msg_cache[path] = (mtime, data)
    return data


def get_messages(session_id, source=None):
    """按来源取会话正文；source 缺省时依次探测三个来源"""
    sources = [source] if source in ("workbuddy", "codex", "dsh") else ["workbuddy", "codex", "dsh"]

    if "workbuddy" in sources:
        path = find_session_file(session_id)
        if path:
            data = parse_messages(path)
            return {"source": "workbuddy", **data}

    if "codex" in sources:
        path = find_codex_file(session_id)
        if path:
            titles = codex_titles()
            return {
                "source": "codex",
                "title": titles.get(session_id),
                "messages": parse_codex_messages(path),
            }

    if "dsh" in sources:
        if dsh_session_dir(session_id):
            title = None
            cf = os.path.join(DSH, "storages", "session_projcache", "sessions", session_id + ".json")
            if os.path.exists(cf):
                try:
                    title = _dsh_meta(cf)["title"]
                except Exception:
                    title = None
            return {
                "source": "dsh",
                "title": title,
                "messages": parse_dsh_messages(session_id),
            }

    return None


# 模型名 → 看板上的智能体卡片
# 只保留「没有独立客户端」的模型（GLM 只能经 WorkBuddy 调用）。
# deepseek / gpt / claude 现在都有各自的客户端，卡片用客户端自己的数据，
# 因此从 WorkBuddy 路由出来的同名模型统一并入 WorkBuddy 的模型明细。
MODEL_RULES = (
    ("glm", "glm"),
    ("zhipu", "glm"),
)


def agent_for_model(model):
    """把模型归到 agent id；认不出来的算 WorkBuddy 自有模型"""
    m = (model or "").lower()
    for key, aid in MODEL_RULES:
        if key in m:
            return aid
    return "workbuddy"


def _sum(sessions):
    tot = {k: 0 for k in ("input", "cache_read", "cache_create", "output", "reasoning", "total")}
    rounds = 0
    for s in sessions:
        rounds += s["rounds"]
        for k in tot:
            tot[k] += s[k]
    return tot, rounds


def compute_all():
    wb_sessions = []
    for f in iter_session_files():
        s, rounds = parse_session_file(f)
        s["daily_usage"] = [(r["ts"], r["total"]) for r in rounds]
        s["source"] = "workbuddy"
        wb_sessions.append(s)

    titles = codex_titles()
    codex_sessions = []
    for f in iter_codex_files():
        codex_sessions.append(parse_codex_file(f, titles))

    dsh_sessions = parse_dsh_sessions()

    sessions = wb_sessions + codex_sessions + dsh_sessions
    sessions.sort(key=lambda s: s.get("endedAt") or s.get("mtime") or 0, reverse=True)

    per_day = defaultdict(int)
    today = datetime.now().strftime("%Y-%m-%d")
    tot, rounds_total = _sum(sessions)

    for session in sessions:
        remaining = session["total"]
        fallback = session.get("endedAt") or session.get("startedAt") or (session.get("mtime") or 0) * 1000
        for timestamp, amount in session.get("daily_usage", []):
            if not timestamp or not remaining:
                continue
            amount = min(amount, remaining)
            per_day[datetime.fromtimestamp(timestamp / 1000).strftime("%Y-%m-%d")] += amount
            remaining -= amount
        if remaining:
            day = datetime.fromtimestamp(fallback / 1000).strftime("%Y-%m-%d") if fallback else today
            per_day[day] += remaining

    days = dict(per_day)

    prompt_total = tot["input"] + tot["cache_read"] + tot["cache_create"]
    cache_hit = round(tot["cache_read"] / prompt_total * 100, 1) if prompt_total else 0.0

    # ---- 各智能体 ----
    def running_of(group, minutes=5):
        if not group:
            return False
        ref = max((g.get("endedAt") or (g.get("mtime") or 0) * 1000) for g in group)
        return bool(ref and (time.time() * 1000 - ref) < minutes * 60_000)

    agents_out = {}
    groups = (
        ("workbuddy", wb_sessions),
        ("codex", codex_sessions),
        ("deepseek", dsh_sessions),
    )
    for aid, group in groups:
        subtot, subrounds = _sum(group)
        models = {}
        for s in group:
            for m, v in s.get("models", {}).items():
                cur = models.setdefault(m, {"tokens": 0, "rounds": 0})
                cur["tokens"] += v["tokens"]
                cur["rounds"] += v["rounds"]
        agents_out[aid] = {
            "tokens": subtot["total"],
            "rounds": subrounds,
            "running": running_of(group),
            "via": None,
            "sessions": len(group),
            "models": [m for m, _ in sorted(models.items(), key=lambda kv: -kv[1]["tokens"])],
        }

    # WorkBuddy 内部路由出去、但没有独立客户端的模型（目前只有 GLM）
    wb_models = {}
    for s in wb_sessions:
        for m, v in s.get("models", {}).items():
            cur = wb_models.setdefault(m, {"tokens": 0, "rounds": 0})
            cur["tokens"] += v["tokens"]
            cur["rounds"] += v["rounds"]
    for m, v in wb_models.items():
        aid = agent_for_model(m)
        if aid == "workbuddy":
            continue
        node = agents_out.setdefault(aid, {
            "tokens": 0, "rounds": 0,
            "running": agents_out["workbuddy"]["running"],
            "via": "WorkBuddy", "sessions": 0, "models": [],
        })
        node["tokens"] += v["tokens"]
        node["rounds"] += v["rounds"]
        node["models"].append(m)

    last_wb = wb_sessions[0] if wb_sessions else None

    usage = {
        "updatedAt": int(time.time() * 1000),
        "totals": {
            "today": per_day.get(today, 0),
            "all": tot["total"],
            "input": tot["input"],
            "output": tot["output"] + tot["reasoning"],
            "cached": tot["cache_read"] + tot["cache_create"],
            "cacheHit": cache_hit,
            "rounds": rounds_total,
            "sessions": len(sessions),
        },
        "daily": days,
        "agents": agents_out,
        "models": [
            {"model": m, "tokens": v["tokens"], "rounds": v["rounds"],
             "agent": agent_for_model(m)}
            for m, v in sorted(wb_models.items(), key=lambda kv: -kv[1]["tokens"])
        ],
        "agent": {
            "name": "WorkBuddy",
            "tokens": agents_out["workbuddy"]["tokens"],
            "rounds": agents_out["workbuddy"]["rounds"],
            "running": agents_out["workbuddy"]["running"],
            "lastTitle": (last_wb or {}).get("title"),
        },
    }

    session_list = [{
        "id": s["id"],
        "source": s["source"],
        "title": s["title"] or "未命名会话",
        "project": s["project"] or s["source"],
        "cwd": s["cwd"],
        "projectKey": os.path.realpath(s["cwd"]) if s["cwd"] and os.path.isabs(s["cwd"]) else None,
        "startedAt": s["startedAt"],
        "endedAt": s["endedAt"],
        "messages": s["messages"],
        "rounds": s["rounds"],
        "tokens": s["total"],
        "input": s["input"],
        "output": s["output"] + s["reasoning"],
        "cached": s["cache_read"] + s["cache_create"],
    } for s in sessions]

    return usage, session_list


def get_usage():
    with _lock:
        now = time.time()
        if _cache["data"] is None or now - _cache["at"] > CACHE_TTL:
            u, s = compute_all()
            _cache["data"] = u
            _cache2["data"] = s
            _cache["at"] = now
            _cache2["at"] = now
        return _cache["data"]


def get_sessions():
    with _lock:
        now = time.time()
        if _cache2["data"] is None or now - _cache2["at"] > CACHE_TTL:
            u, s = compute_all()
            _cache["data"] = u
            _cache2["data"] = s
            _cache["at"] = now
            _cache2["at"] = now
        return _cache2["data"]


def find_control_session(sid, source):
    if source == "codex":
        return find_codex_file(sid)
    if source == "dsh" and dsh_session_dir(sid):
        cache_file = os.path.join(DSH, "storages", "session_projcache", "sessions", sid + ".json")
        try:
            return _dsh_meta(cache_file)["cwd"]
        except (OSError, ValueError):
            return None
    return None


def resolve_new_workspace(project):
    if project == "":
        return ROOT
    if isinstance(project, str) and any(
        session["projectKey"] == project for session in get_sessions()
    ) and os.path.isdir(project) and os.path.realpath(project) == project:
        return project
    raise ControlError("invalid_project", "项目目录不可用，请刷新项目列表后重试。", 409)


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=ROOT, **kwargs)

    def end_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        if self.path.split("?", 1)[0] in STATIC_FILES:
            self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def _json(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def do_HEAD(self):
        self.do_GET()

    def _valid_host(self):
        # Literal private IPs support LAN/WireGuard, while rejecting DNS rebinding.
        try:
            host = urlsplit("//" + self.headers.get("Host", ""))
            if host.username or host.password or host.path or host.query or host.fragment or (host.port or 80) != self.server.server_port:
                return False
            return host.hostname == "localhost" or ipaddress.ip_address(host.hostname).is_private
        except (ValueError, TypeError):
            return False

    def _read_post(self):
        if not self._valid_host():
            raise ControlError("invalid_host", "访问地址无效。", 403)
        origin = self.headers.get("Origin")
        if (origin and origin != "http://" + self.headers.get("Host", "")) or self.headers.get("Sec-Fetch-Site") == "cross-site":
            raise ControlError("invalid_origin", "只接受当前看板页面发起的发送请求。", 403)
        token = self.headers.get("X-Agent-Phone-CSRF", "")
        if not secrets.compare_digest(token, CSRF_TOKEN):
            raise ControlError("invalid_csrf", "连接状态已更新，请刷新发送状态后重试。", 403)
        if self.headers.get("Content-Type", "").split(";", 1)[0].strip() != "application/json":
            raise ControlError("invalid_content_type", "发送请求必须使用 JSON。", 415)
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            raise ControlError("invalid_length", "请求长度无效。")
        if length <= 0 or length > 65536:
            raise ControlError("invalid_length", "发送请求为空或过大。", 413)
        self.connection.settimeout(15)
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except (ValueError, UnicodeError):
            raise ControlError("invalid_json", "发送请求不是有效的 JSON。")

    def do_POST(self):
        try:
            path = urlsplit(self.path).path
            if path not in ("/api/send", "/api/jobs/acknowledge", "/api/sessions/release"):
                raise ControlError("not_found", "没有这个接口。", 404)
            payload = self._read_post()
            if path == "/api/sessions/release":
                session = payload.get("session") if isinstance(payload, dict) else None
                source = payload.get("source", "codex") if isinstance(payload, dict) else "codex"
                self._json(get_control_service().release(session, source))
                return
            if path == "/api/jobs/acknowledge":
                if not isinstance(payload, dict) or not isinstance(payload.get("requestId"), str):
                    raise ControlError("invalid_id", "发送记录标识无效。")
                self._json({"job": get_control_service().acknowledge(payload["requestId"])})
                return
            job = get_control_service().submit(
                payload, find_control_session,
                resolve_new_workspace,
            )
            self._json({"job": job}, 202)
        except ControlError as exc:
            self._json({"error": {"code": exc.code, "message": exc.message}}, exc.status)
        except Exception:
            self._json({"error": {"code": "internal_error", "message": "网关暂时无法受理，请使用原请求编号确认结果。"}}, 500)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path.startswith("/api/") and not self._valid_host():
            self._json({"error": {"code": "invalid_host", "message": "访问地址无效。"}}, 403)
            return
        query = {}
        if "?" in self.path:
            for kv in self.path.split("?", 1)[1].split("&"):
                if "=" in kv:
                    k, v = kv.split("=", 1)
                    query[k] = v

        if path in ("/api/control", "/api/jobs"):
            try:
                service = get_control_service()
                if path == "/api/control":
                    self._json({"csrfToken": CSRF_TOKEN, "sources": service.capabilities()})
                else:
                    self._json({"job": service.get(query.get("id", ""))})
            except ControlError as exc:
                self._json({"error": {"code": exc.code, "message": exc.message}}, exc.status)
            except Exception:
                self._json({"error": {"code": "control_unavailable", "message": "发送状态暂时不可用，请稍后确认原请求结果。"}}, 503)
            return

        if path == "/api/usage":
            self._json(get_usage())
            return
        if path == "/api/sessions":
            self._json({"sessions": get_sessions()})
            return
        if path == "/api/messages":
            from urllib.parse import unquote
            sid = unquote(query.get("session", ""))
            src = unquote(query.get("source", "")) or None
            data = get_messages(sid, src)
            if data is None:
                self._json({"error": "session not found", "id": sid})
                return
            sess = next((s for s in get_sessions()
                         if s["id"] == sid and (not src or s.get("source") == src)), None)
            self._json({
                "session": sess or {"id": sid, "source": data.get("source")},
                "title": data.get("title") or (sess or {}).get("title"),
                "messages": data["messages"],
            })
            return
        # Never serve source, local configuration, Git metadata or directory listings.
        if path not in STATIC_FILES:
            self.send_error(404)
            return
        if self.command == "HEAD":
            super().do_HEAD()
        else:
            super().do_GET()

    def log_message(self, fmt, *args):
        pass


if __name__ == "__main__":
    print(f"agent-phone 网关: http://{HOST}:{PORT}  (静态 + /api/usage + /api/sessions)", flush=True)
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()

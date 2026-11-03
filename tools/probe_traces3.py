#!/usr/bin/env python3
"""全量提取 traces 里的 usage + 时间戳 + 模型"""
import json, glob, os, re
from datetime import datetime
from collections import defaultdict

home = os.path.expanduser("~/.workbuddy")

def deep_parse(o, depth=0):
    if depth > 8 or isinstance(o, (int, float, bool)) or o is None:
        return o
    if isinstance(o, str):
        s = o.strip()
        if s[:1] in "{[" and len(s) > 20:
            try:
                return deep_parse(json.loads(s), depth + 1)
            except Exception:
                return o
        return o
    if isinstance(o, dict):
        return {k: deep_parse(v, depth + 1) for k, v in o.items()}
    if isinstance(o, list):
        return [deep_parse(v, depth + 1) for v in o]
    return o

def find_usages(o, out):
    if isinstance(o, dict):
        u = o.get("usage")
        if isinstance(u, dict) and "prompt_tokens" in u:
            model = None
            # 在附近找 model 字段
            for k in ("model", "modelName", "model_name"):
                if isinstance(o.get(k), str):
                    model = o[k]; break
            out.append((u, model))
            return
        for v in o.values():
            find_usages(v, out)
    elif isinstance(o, list):
        for v in o:
            find_usages(v, out)

per_day = defaultdict(int)
per_model = defaultdict(int)
calls = 0
prompt = comp = cached = 0

for f in glob.glob(home + "/traces/*/*.jsonl"):
    raw = None
    started = None
    for l in open(f):
        try:
            d = json.loads(l)
        except Exception:
            continue
        if d.get("type") == "trace":
            started = (d.get("trace") or {}).get("startedAt")
        d2 = deep_parse(d)
        us = []
        find_usages(d2, us)
        for u, m in us:
            calls += 1
            p = u.get("prompt_tokens", 0)
            c = u.get("completion_tokens", 0)
            cd = (u.get("prompt_tokens_details") or {}).get("cached_tokens", 0) or 0
            prompt += p; comp += c; cached += cd
            per_model[m or "unknown"] += p + c
            # 时间：优先 span 的，否则 trace 的
            ts = None
            sp = d.get("span")
            if isinstance(sp, dict) and sp.get("startedAt"):
                ts = sp["startedAt"]
            if isinstance(ts, str):
                day = ts[:10]
            elif isinstance(ts, (int, float)):
                day = datetime.fromtimestamp(ts / 1000).strftime("%Y-%m-%d")
            elif isinstance(started, str):
                day = started[:10]
            else:
                day = datetime.now().strftime("%Y-%m-%d")
            per_day[day] += p + c

print("LLM 调用数:", calls)
print("prompt:", prompt, " completion:", comp, " cached:", cached)
print("缓存命中: %.1f%%" % (cached / prompt * 100 if prompt else 0))
print("按天:", dict(per_day))
print("按模型:", dict(per_model))

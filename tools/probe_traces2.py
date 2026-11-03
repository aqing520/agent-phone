#!/usr/bin/env python3
"""聚合所有 trace 的头部信息"""
import json, glob, os
from datetime import datetime

home = os.path.expanduser("~/.workbuddy")
tot_tokens = 0
rows = []
for f in glob.glob(home + "/traces/*/*.jsonl"):
    try:
        first = open(f).readline()
        d = json.loads(first)
    except Exception:
        continue
    t = d.get("trace") or {}
    md = t.get("metadata") or {}
    rows.append({
        "file": os.path.basename(f),
        "name": t.get("name"),
        "pid": t.get("workerPid"),
        "startedAt": t.get("startedAt"),
        "endedAt": t.get("endedAt"),
        "totalTokens": t.get("totalTokens"),
        "status": t.get("status"),
        "metaKeys": list(md.keys())[:10],
        "model": md.get("model") or md.get("modelName"),
    })
    tot_tokens += t.get("totalTokens") or 0

print("trace 数:", len(rows), " 总 token:", tot_tokens)
for r in rows:
    ts = r["startedAt"]
    when = str(ts)
    if isinstance(ts, (int, float)):
        when = datetime.fromtimestamp(ts/1000).strftime("%m-%d %H:%M")
    elif isinstance(ts, str):
        when = ts[:16]
    print(f"{when}  tok={r['totalTokens']}  {r['status']}  model={r['model']}  name={r['name']}")
print("metadata keys 样例:", rows[0]["metaKeys"] if rows else "-")

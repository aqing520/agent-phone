#!/usr/bin/env python3
"""按 providerData.model 归集真实用量，确认各家 agent 的占比"""
import json, glob, os, collections

def nn(v):
    try:
        n = int(v)
        return n if n > 0 else 0
    except (TypeError, ValueError):
        return 0

def norm(u):
    if not isinstance(u, dict):
        return 0
    if "inputTokens" in u:
        p = nn(u.get("inputTokens")); c = nn(u.get("outputTokens"))
        det = u.get("inputTokensDetails") or []
        cached = nn(det[0].get("cached_tokens")) if det else 0
    else:
        p = nn(u.get("prompt_tokens")); c = nn(u.get("completion_tokens"))
        pd = u.get("prompt_tokens_details") or {}
        cached = nn(pd.get("cached_tokens"))
    return p + c if (p + c) else 0

by_model = collections.Counter()
calls = collections.Counter()
by_day_model = collections.defaultdict(collections.Counter)

for f in glob.glob(os.path.expanduser("~/.workbuddy/projects/**/*.jsonl"), recursive=True):
    seen = set()
    for line in open(f, encoding="utf-8", errors="replace"):
        if '"providerData"' not in line:
            continue
        try:
            d = json.loads(line)
        except Exception:
            continue
        p = d.get("providerData") or {}
        if not isinstance(p, dict):
            continue
        raw = p.get("rawUsage") or p.get("usage")
        if not isinstance(raw, dict):
            continue
        mid = p.get("messageId")
        if not mid or mid in seen:
            continue
        seen.add(mid)
        model = p.get("model") or "auto"
        t = norm(raw)
        by_model[model] += t
        calls[model] += 1

print(f"{'model':28}{'calls':>8}{'tokens':>14}")
for m, t in by_model.most_common():
    print(f"{m:28}{calls[m]:>8}{t:>14,}")
print("合计:", f"{sum(by_model.values()):,}")

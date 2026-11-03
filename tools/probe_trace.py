#!/usr/bin/env python3
"""探测 WorkBuddy trace 文件结构"""
import json, glob, os, sys

home = os.path.expanduser("~/.workbuddy")
files = sorted(glob.glob(home + "/traces/*/*.jsonl"))
print("trace 文件数:", len(files))
f = files[0]
print("样本:", f)

for i, l in enumerate(open(f)):
    try:
        d = json.loads(l)
    except Exception as e:
        print(i, "parse error", e); continue
    print(i, "keys:", list(d.keys()))
    for k, v in d.items():
        if isinstance(v, dict):
            print("   ", k, "->", list(v.keys())[:14])
    if i >= 3:
        break

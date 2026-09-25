# -*- coding: utf-8 -*-
"""가지(top›sub)의 미집필 용어 재료 덤프. 사용: python dump_material.py "<top>" "<sub>" out.txt"""
import io, sys, json, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import config as C
from parse_master import parse_items16
top, sub, out = sys.argv[1], sys.argv[2], sys.argv[3]
master = io.open(C.MASTER_SRC, encoding="utf-8").read().split("\n")
s16 = next(i for i, l in enumerate(master) if l.startswith("## 16. "))
items16 = parse_items16([l for l in master[s16 + 1:] if not l.startswith("### ")], "", "")
E = json.load(io.open(C.WORK / "index.json", encoding="utf-8"))["entries"]
CX = json.load(io.open(C.WORK / "context.json", encoding="utf-8"))["terms"]
ks = [k for k, e in E.items() if e["top"] == top and e["sub"] == sub and k not in items16]
w = io.open(out, "w", encoding="utf-8", newline="\n")
w.write(f"{len(ks)}\n")
for n, k in enumerate(ks):
    e = E[k]
    w.write(f"#### [{n}] {e['term']}  [key={k}] secs={e.get('secs')} depth={e.get('depth')}\n")
    for m in (e.get("meanings") or []):
        w.write(f"   뜻(§{m['item']}): {m['meaning']}\n")
    for sk in (e.get("subknow") or []):
        w.write(f"   하위지식(§{sk['item']}) {sk['title']}: {' '.join(sk['lines'])[:300]}\n")
    if e.get("failures"):
        w.write(f"   failures={e['failures']}\n")
    cx = CX.get(k) or {}
    for kind in ("body", "ctx", "rows"):
        for u in (cx.get(kind) or [])[:3]:
            t = f"[§{u.get('sec')}] " + (u.get("text") or "") if isinstance(u, dict) else str(u)
            w.write(f"   {t[:300]}\n")
w.close()
print(out, len(ks))

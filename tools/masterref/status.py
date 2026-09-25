# -*- coding: utf-8 -*-
"""집필 진행 상태: 마스터의 F 집필 수·§16 블록 수, 배치 파일별 접합 여부, 다음 배치 id. 사용: python status.py"""
import io, re, sys, glob, json, pathlib, collections
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import config as C
import naming as N
from parse_master import parse_fblock, parse_items16, H4_F, FIELD

master = io.open(C.MASTER_SRC, encoding="utf-8").read().split("\n")
authored_f = set()
for i, l in enumerate(master):
    m = H4_F.match(l)
    if m:
        _, a, _ = parse_fblock(master, i + 1)
        if a: authored_f.add(m.group(1))
s16 = next((i for i, l in enumerate(master) if l.startswith("## 16. ")), None)
items16 = parse_items16([l for l in master[s16 + 1:] if not l.startswith("### ")], "", "") if s16 is not None else {}
E = json.load(io.open(C.WORK / "index.json", encoding="utf-8"))["entries"]
print(f"failures {len(authored_f)}/304 · terms {len(items16)}/{len(E)}")
# 배치 파일 접합 여부
for d, kind in ((C.EDIT14, "F"), (C.EDIT16, "T")):
    for f in sorted(glob.glob(str(d / "*.md"))):
        lines = io.open(f, encoding="utf-8").read().split("\n")
        if kind == "F":
            keys = [m.group(1) for l in lines for m in [H4_F.match(l)] if m]
            miss = [k for k in keys if k not in authored_f]
        else:
            keys = list(parse_items16([l for l in lines if not l.startswith("### ")], "", ""))
            miss = [k for k in keys if k not in items16]
        print(f"  {pathlib.Path(f).name}: {len(keys)} blocks, {'assembled' if not miss else f'NOT assembled ({len(miss)} missing)'}")
# 다음 실패 배치
nxt = next((n for n in range(1, 305) if f"F-{n:03d}" not in authored_f), None)
if nxt: print(f"next failure: F-{nxt:03d} (batch b{(nxt - 1) // 40 + 1:02d}: F-{(nxt - 1) // 40 * 40 + 1:03d}..F-{min((nxt - 1) // 40 * 40 + 40, 304):03d})")
# 다음 용어 가지
from build_index import TOP_ORDER
by_branch = collections.OrderedDict()
PRIO = ["Maro 고유"] + [t for t in TOP_ORDER if t != "Maro 고유"]   # 집필 순서: 프로젝트 고유 개념부터
for k, e in E.items(): by_branch.setdefault((PRIO.index(e["top"]), e["top"], e["sub"]), []).append(k)
for (i, top, sub), ks in sorted(by_branch.items(), key=lambda x: x[0][0]):
    todo = [k for k in ks if k not in items16]
    if todo:
        print(f"next terms: {top} › {sub} — {len(todo)}/{len(ks)} 미집필 (예: {', '.join(E[k]['display'] for k in todo[:5])})"); break

# -*- coding: utf-8 -*-
"""model.json → index.json (용어 정체성·파일명·표면형·등장 절·하위지식·관련 실패) + reports/"""
import io, re, sys, json, pathlib, collections
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import config as C
import naming as N

# build_taxonomy.py 의 TOP_ORDER/SUBS/classify 를 top-level 실행 없이 가져온다
_src = io.open(C.SCRATCH / "build_taxonomy.py", encoding="utf-8").read()
_ns = {"__name__": "bt"}
exec(_src[:_src.index("# ---------- 파싱 ----------")].replace("SRC, DST = sys.argv[1], sys.argv[2]", ""), _ns)
TOP_ORDER, SUBS, classify = _ns["TOP_ORDER"], _ns["SUBS"], _ns["classify"]

KO_EN = re.compile(r"^([가-힣][^()]*?)\s*\(([^()]+)\)$")


def item_to_section(key):
    """§13 item key → 절 번호('6.6') 또는 장('2')"""
    return key


def surfaces_for(display, mates_display):
    plain = display.replace("`", "").strip()
    surf = set(); code = set()
    is_code = display.startswith("`") and display.endswith("`") and display.count("`") == 2
    if is_code:
        code.add(plain)
        head = N.strip_trailing_group(plain).strip()
        if head != plain and re.match(r"^[A-Za-z_][\w:.<>]*$", head) and len(head) >= 4: code.add(head)
        m0 = re.match(r"^([A-Za-z_][\w]*)", head)
        if m0 and len(m0.group(1)) >= 5 and m0.group(1) != head and "::" in head: code.add(m0.group(1) + "::" + head.split("::")[-1]) if False else None
        # 식별자에 한글 없으면 텍스트 표면형으로도(예: MaroPump 를 백틱 없이 쓴 문장)
        if re.match(r"^[A-Za-z_][\w:.<>()]*$", plain) and len(plain) >= 4:
            surf.add(plain)
    else:
        surf.add(plain)
        m = KO_EN.match(plain)
        if m:
            ko, en = m.group(1).strip(), m.group(2).strip()
            if len(ko) >= 2: surf.add(ko)
            if re.match(r"^[\x20-\x7e]+$", en) and (re.search(r"[A-Z_.:]", en) or len(en) >= 7): surf.add(en)
        # 괄호 앞부분(영문/한글 혼합)
        m2 = re.match(r"^(.+?)\s*\([^()]*\)$", plain)
        if m2 and len(m2.group(1)) >= 3: surf.add(m2.group(1).strip())
    def ok(s):
        if s.lower() in C.STOPWORDS: return False
        if re.search(r"[가-힣]", s): return len(s) >= 3
        return len(s) >= 3
    surf = {s for s in surf if ok(s)}
    return sorted(surf), sorted(code)


def main():
    model = json.load(io.open(C.WORK / "model.json", encoding="utf-8"))
    entries = collections.OrderedDict()
    rows_seen = []
    for key, it in model["items13"].items():
        for row in it["terms"]:
            keys_in_row = []
            parts = [p.strip() for p in re.split(r"\s+/\s+", row["cells"][1])]
            split_ok = len(parts) == len(row["terms"]) and len(parts) > 1
            for ti, t in enumerate(row["terms"]):
                k = N.term_key(t)
                if not k: continue
                keys_in_row.append(k)
                if k not in entries:
                    top, sub = classify(row["cells"][2], t)
                    entries[k] = {"key": k, "term": t, "display": t.replace("`", "").strip(), "top": top, "sub": sub,
                                  "depth": row["depth"], "secs": [], "meanings": [], "mates": set(), "subknow": [],
                                  "failures": [], "aliases": set(), "explained_in": None}
                e = entries[k]
                if row["depth"] == "심화": e["depth"] = "심화"
                if key not in e["secs"]: e["secs"].append(key)
                e["meanings"].append({"item": key, "meaning": parts[ti] if split_ok else row["cells"][1], "cat": row["cells"][2], "depth": row["depth"], "ref": row["ref"]})
                if t.replace("`", "").strip() != e["display"]: e["aliases"].add(t.replace("`", "").strip())
                if row["ref"] and e["explained_in"] is None: e["explained_in"] = row["ref"]
            for k in keys_in_row:
                for k2 in keys_in_row:
                    if k2 != k: entries[k]["mates"].add(k2)
    for e in entries.values():
        if e["explained_in"] is None:
            deep = [m for m in e["meanings"] if m["depth"] == "심화"]
            e["explained_in"] = (max(deep, key=lambda m: len(m["meaning"])) if deep else e["meanings"][0])["item"]
    # 하위지식 매칭(같은 §13 항목 안, 토큰 겹침; SUBKNOW_MAP 우선)
    unmatched = []
    for key, it in model["items13"].items():
        item_keys = [N.term_key(t) for r in it["terms"] for t in r["terms"]]
        for sk in it["subknow"]:
            title = sk["title"].replace("`", "").lower()
            target = C.SUBKNOW_MAP.get((key, sk["title"]))
            cands = []
            if target and target in entries: cands = [target]
            else:
                def toks(s):
                    return {w for w in re.split(r"[^\w가-힣]+", s) if (len(w) >= 4 if re.match(r"^[\w]+$", w) and not re.search(r"[가-힣]", w) else len(w) >= 3)}
                ttoks = toks(title)
                for k in item_keys:
                    if k not in entries: continue
                    if k in title or title in k:
                        cands.append(k); continue
                    if ttoks & toks(k): cands.append(k)
                # 심화 우선
                deep = [k for k in cands if entries[k]["depth"] == "심화"]
                cands = deep or cands
            # 같은 행의 심화 동료 용어에도 붙인다(BoundedQueue / drop-oldest / drain() 처럼 한 행이 한 개념군)
            extra = []
            for k in cands:
                for mk in entries[k]["mates"]:
                    if mk in entries and mk in item_keys and entries[mk]["depth"] == "심화": extra.append(mk)
            cands = list(dict.fromkeys(cands + extra))
            if not cands:
                unmatched.append((key, sk["title"]))
            for k in cands:
                entries[k]["subknow"].append({"item": key, "title": sk["title"], "lines": sk["lines"]})
    # 파일명 (전역 유일)
    taken = N.existing_basenames()
    reserved = set()
    collisions = []
    for e in entries.values():
        fn = N.term_filename(e["term"])
        if fn.lower() in taken or fn.lower() in reserved:
            fn2 = f"{fn} ({e['sub']})"
            collisions.append((e["term"], fn, fn2)); fn = fn2
        assert fn.lower() not in reserved, fn
        reserved.add(fn.lower()); e["filename"] = fn
        N.check_name(fn)
        e["folder"] = f"{C.LAYER_NOTE}/{N.sanitize(e['top'])}/{N.branch_folder(e['sub'])}"
        e["surfaces"], e["code_forms"] = surfaces_for(e["term"], [])
        e["aliases"] = sorted((e["aliases"] | set(e["surfaces"]) | set(e["code_forms"])) - {e["display"]})
        e["mates"] = sorted(e["mates"])
    # 관련 실패
    sec_of_fail = {}
    for f in model["failures"]:
        refs = set(re.findall(r"§(\d+(?:\.\d+)*)", f["fields"].get("출처", "")))
        text = (f["title"] + " " + " ".join(f["fields"].values())).lower()
        sec_of_fail[f["id"]] = (refs, text)
    for e in entries.values():
        my = set()
        for s in e["secs"]:
            my.add(s); my.add(s.split(".")[0])
        forms = [s.lower() for s in e["surfaces"] + e["code_forms"]]
        for fid, (refs, text) in sec_of_fail.items():
            share = any(r == s or r.startswith(s + ".") or s.startswith(r + ".") for r in refs for s in my if "." in s or "." in r)
            if share and any(fm in text for fm in forms if len(fm) >= 3):
                e["failures"].append(fid)
    # 표면형 모호성
    surf_map = collections.defaultdict(list)
    for e in entries.values():
        for s in e["surfaces"]: surf_map[s].append(e["key"])
        for s in e["code_forms"]: surf_map["`" + s].append(e["key"])
    ambiguous = {s: ks for s, ks in surf_map.items() if len(ks) > 1}
    # 근사 중복 후보
    def loose(k): return re.sub(r"[\s·\-_()]+", "", re.sub(r"\(.*?\)", "", k))
    groups = collections.defaultdict(list)
    for k in entries: groups[loose(k)].append(k)
    merge_cands = [v for v in groups.values() if len(v) > 1]
    idx = {"entries": entries, "ambiguous": ambiguous, "unmatched_subknow": unmatched, "merge_candidates": merge_cands, "collisions": collisions}
    io.open(C.WORK / "index.json", "w", encoding="utf-8").write(json.dumps(idx, ensure_ascii=False, indent=1))
    C.REPORTS.mkdir(exist_ok=True)
    io.open(C.REPORTS / "ambiguous-surfaces.md", "w", encoding="utf-8").write("\n".join(f"- `{s}` → {ks}" for s, ks in sorted(ambiguous.items())))
    io.open(C.REPORTS / "subknow-unmatched.md", "w", encoding="utf-8").write("\n".join(f"- §13.{k}: {t}" for k, t in unmatched))
    io.open(C.REPORTS / "merge-candidates.md", "w", encoding="utf-8").write("\n".join(f"- {v}" for v in merge_cands))
    deep = sum(1 for e in entries.values() if e["depth"] == "심화")
    with_sk = sum(1 for e in entries.values() if e["subknow"])
    print(f"terms {len(entries)} (심화 {deep}, 하위지식 보유 {with_sk}) ambiguous surfaces {len(ambiguous)} unmatched subknow {len(unmatched)} merge cands {len(merge_cands)} collisions {len(collisions)}")


if __name__ == "__main__":
    main()

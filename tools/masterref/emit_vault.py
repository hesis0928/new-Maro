# -*- coding: utf-8 -*-
"""model.json + index.json → out/Master Reference/ (스테이징). 사용: python emit_vault.py [--only 6.6[,7.2]] [--clean]"""
import io, re, sys, json, pathlib, shutil, collections, datetime
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import config as C
import naming as N
from linkify import Linker, assert_clean, alias_safe
from textutil import unwrap

TODAY = datetime.date.today().isoformat()
_bt = io.open(C.SCRATCH / "build_taxonomy.py", encoding="utf-8").read()
_ns = {"__name__": "bt"}
exec(_bt[:_bt.index("# ---------- 파싱 ----------")].replace("SRC, DST = sys.argv[1], sys.argv[2]", ""), _ns)
TOP_ORDER, SUBS = _ns["TOP_ORDER"], _ns["SUBS"]


# ---------------- 유틸
def q(s):
    return json.dumps(str(s), ensure_ascii=False)


def fm(fields):
    """frontmatter 렌더. 값: str | int | list[str]"""
    out = ["---"]
    for k, v in fields.items():
        if v is None or v == [] or v == "": continue
        if isinstance(v, list): out.append(f"{k}: [{', '.join(q(x) for x in v)}]")
        elif isinstance(v, int): out.append(f"{k}: {v}")
        else: out.append(f"{k}: {q(v)}")
    out.append("---")
    return "\n".join(out)


def one_liner(lines, fallback=""):
    for i, l in enumerate(lines):
        if l.startswith("**한 줄 요약:**"):
            s = l[len("**한 줄 요약:**"):].strip()
            j = i + 1
            while j < len(lines) and lines[j].strip() and not lines[j].startswith(("**", "- ", "#", "|")):
                s += " " + lines[j].strip(); j += 1
            return s
    return fallback


def strip_summary(lines):
    """한 줄 요약 줄(과 이어진 줄)을 본문에서 제거하고 반환"""
    out = []; skip = False
    for l in lines:
        if l.startswith("**한 줄 요약:**"):
            skip = True; continue
        if skip:
            if l.strip() and not l.startswith(("**", "- ", "#", "|")): continue
            skip = False
        out.append(l)
    while out and out[0].strip() == "": out.pop(0)
    return out


def write(path: pathlib.Path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".md.tmp")
    io.open(tmp, "w", encoding="utf-8", newline="\n").write(text.rstrip("\n") + "\n")
    tmp.replace(path)


# ---------------- 메인
def main():
    only = None
    if "--only" in sys.argv:
        only = set(sys.argv[sys.argv.index("--only") + 1].split(","))
    if "--clean" in sys.argv and C.OUT.exists():
        shutil.rmtree(C.OUT)
    model = json.load(io.open(C.WORK / "model.json", encoding="utf-8"))
    index = json.load(io.open(C.WORK / "index.json", encoding="utf-8"))
    E = index["entries"]
    secs, subs, chaps, items, fails, fclasses = model["sections"], model["subsections"], model["chapters"], model["items13"], model["failures"], model["fail_classes"]
    ctxp = C.WORK / "context.json"
    context = json.load(io.open(ctxp, encoding="utf-8")) if ctxp.exists() else {"terms": {}, "failures": {}, "fail_terms": {}}
    items16 = model.get("items16", {})

    # ---- 이름/경로 결정
    taken = N.existing_basenames()
    sec_fn = {n: N.section_filename(n, s["heading"]) for n, s in secs.items()}
    sub_fn = {n: N.section_filename(n, s["heading"]) for n, s in subs.items()}
    ch_folder = {n: C.CHAPTER_TITLES[int(n)] for n in chaps}
    ch_hub = {n: f"Intro {ch_folder[n]}" for n in chaps}
    class_folder = {}; class_hub = {}
    for i, (code, title) in enumerate(C.FAIL_CLASSES, 1):
        num = f"14.{i}"; class_folder[num] = f"{i:02d} {code} {N.sanitize(title)}"; class_hub[num] = f"Intro {class_folder[num]}"
    fail_fn = {f["id"]: N.failure_filename(f["id"], f["title"]) for f in fails}
    cat_folder = {top: N.sanitize(top) for top in TOP_ORDER}
    cat_hub = {top: f"Intro {cat_folder[top]}" for top in TOP_ORDER}
    branch_hub = {}
    for (top, sub) in SUBS:
        base = f"Intro {N.branch_folder(sub)}"
        # 다른 카테고리에 같은 가지 이름이 있으면 부모 접미
        dup = sum(1 for (t2, s2) in SUBS if s2 == sub) > 1
        branch_hub[(top, sub)] = base if not dup and base.lower() not in taken else f"{base} ({N.sanitize(top)})"
    layer_hub = {"ref": f"Intro {C.LAYER_REF}", "note": f"Intro {C.LAYER_NOTE}", "fail": f"Intro {C.LAYER_FAIL}", "exc": f"Intro {C.LAYER_EXCERPT}"}
    targets = {"section": sec_fn, "subsection": sub_fn, "chapter": ch_hub, "failure": fail_fn, "failclass": class_hub,
               "fail_hub": layer_hub["fail"], "note_hub": layer_hub["note"]}
    L = Linker(index, targets)

    def sec_path(n):
        s = secs[n]; folder = C.OUT / C.LAYER_REF / ch_folder[str(s["chapter"])]
        if s["subsections"]: folder = folder / sec_fn[n]
        return folder / f"{sec_fn[n]}.md"

    def sub_path(n):
        s = subs[n]; return C.OUT / C.LAYER_REF / ch_folder[str(s["chapter"])] / sec_fn[s["parent"]] / f"{sub_fn[n]}.md"

    def term_path(k):
        e = E[k]; return C.OUT / e["folder"] / f"{e['filename']}.md"

    def fail_path(f):
        return C.OUT / C.LAYER_FAIL / class_folder[f["cls"]] / f"{fail_fn[f['id']]}.md"

    # ---- 필터
    def sec_in(n): return only is None or any(n == o or n.startswith(o + ".") for o in only)
    inc_secs = [n for n in secs if sec_in(n)]
    inc_subs = [n for n in subs if sec_in(subs[n]["parent"])]
    inc_terms = [k for k, e in E.items() if only is None or any(sec_in(s) for s in e["secs"])]
    inc_fails = [f for f in fails if only is None or any(sec_in(r) for r in re.findall(r"§(\d+(?:\.\d+)*)", f["fields"].get("출처", "")))]
    inc_chaps = sorted({str(secs[n]["chapter"]) for n in inc_secs} | ({"2"} if (only is None or "2" in (only or set())) else set()), key=int)
    written = collections.Counter()

    # ---- 절 노트
    def render_parts(parts, self_key=None, seen=None):
        out = []
        for p in parts:
            if p["kind"] == "text":
                out += unwrap(p["lines"]) + [""]
            elif p["kind"] == "inline":
                out += [f"## {p['heading']}", ""] + unwrap(p["lines"]) + [""]
        return out

    def render_item13(key, seen):
        it = items.get(key)
        if not it: return []
        out = []
        if it["context"]:
            out += ["## 문맥 풀이", ""] + unwrap(it["context"]) + [""]
        if it["terms"]:
            out += ["## 용어", ""]
            for row in it["terms"]:
                links = []
                for t in row["terms"]:
                    k = N.term_key(t)
                    if k in E:
                        disp = t.replace("`", "").strip()
                        fn = E[k]["filename"]
                        links.append(f"[[{fn}]]" if fn == disp else f"[[{fn}|{alias_safe(disp)}]]")
                    else:
                        links.append(t)
                depth = row["depth"] + (f" → §13.{row['ref']}" if row["ref"] else "")
                out.append(f"- {' / '.join(links)} ({row['cells'][2]} · {depth}) — {row['cells'][1]}")
            out.append("")
        if it["subknow"]:
            out += ["## 하위지식", ""]
            for sk in it["subknow"]:
                out += [f"**{sk['title']}:**"] + unwrap(sk["lines"]) + [""]
        if it["extref"]:
            out += ["## 외부 참조", ""] + unwrap(it["extref"]) + [""]
        return out

    for n in inc_secs:
        s = secs[n]; ch = str(s["chapter"])
        body_lines = [l for p in s["parts"] if p["kind"] == "text" for l in p["lines"]]
        summary = one_liner(body_lines, s["heading"].split(" — ")[-1])
        parts = [dict(p, lines=strip_summary(p["lines"])) if p["kind"] == "text" and p is s["parts"][0] else p for p in s["parts"]]
        body = [f"**한 줄 요약:** {summary}", ""] + render_parts(parts)
        body += render_item13(n, None)
        if s["subsections"]:
            body += ["## 하위 절", ""]
            for sn in s["subsections"]:
                sl = [l for p in subs[sn]["parts"] if p["kind"] == "text" for l in p["lines"]]
                body.append(f"- [[{sub_fn[sn]}|{alias_safe('§' + sn + ' ' + subs[sn]['heading'].split(' — ')[0].replace('`',''))}]] — {one_liner(sl, subs[sn]['heading'].split(' — ')[-1])}")
            body.append("")
        text = "\n".join(body)
        seen = set()
        text = L.link(text, None, seen, sec_fn[n])
        head = fm({"type": "section", "title": f"{n} {s['heading'].replace('`', '')}", "section": n, "chapter": int(ch),
                   "subsections": s["subsections"], "tags": ["maro/ref", f"maro/ch{int(ch):02d}"],
                   "source": f"docs/maro-master-reference.md §{n}" + (f", §13.{n}" if n in items else "")})
        assert_clean(text, sec_fn[n]); write(sec_path(n), head + "\n" + text); written["section"] += 1

    for n in inc_subs:
        s = subs[n]; ch = str(s["chapter"])
        body_lines = [l for p in s["parts"] if p["kind"] == "text" for l in p["lines"]]
        summary = one_liner(body_lines, s["heading"].split(" — ")[-1])
        parts = [dict(p, lines=strip_summary(p["lines"])) if p["kind"] == "text" and p is s["parts"][0] else p for p in s["parts"]]
        body = [f"**한 줄 요약:** {summary}", ""] + render_parts(parts)
        body += [f"**상위 절:** [[{sec_fn[s['parent']]}|§{s['parent']} {secs[s['parent']]['heading'].split(' — ')[0].replace('`','')}]]", ""]
        text = L.link("\n".join(body), None, set(), sub_fn[n])
        head = fm({"type": "subsection", "title": f"{n} {s['heading'].replace('`', '')}", "section": n, "parent": s["parent"], "chapter": int(ch),
                   "tags": ["maro/ref", f"maro/ch{int(ch):02d}"], "source": f"docs/maro-master-reference.md §{n}"})
        assert_clean(text, sub_fn[n]); write(sub_path(n), head + "\n" + text); written["subsection"] += 1

    # ---- 장 허브
    for ch in inc_chaps:
        c = chaps[ch]; intro = c["intro"]
        summary = one_liner(intro, c["title"].split(" — ")[0])
        body = [f"**한 줄 요약:** {summary}", ""] + unwrap(strip_summary(intro)) + [""]
        if ch == "2":
            body += render_item13("2", None)
        body += ["## 절", ""]
        for n in c["sections"]:
            if n in inc_secs:
                sl = [l for p in secs[n]["parts"] if p["kind"] == "text" for l in p["lines"]]
                body.append(f"- [[{sec_fn[n]}|§{n} {secs[n]['heading'].split(' — ')[0].replace('`','')}]] — {one_liner(sl, '')}")
        body.append("")
        text = L.link("\n".join(body), None, set(), ch_hub[ch])
        head = fm({"type": "chapter", "title": f"{ch}. {c['title'].replace('`', '')}", "chapter": int(ch), "tags": ["maro/ref", f"maro/ch{int(ch):02d}", "hub"],
                   "source": f"docs/maro-master-reference.md §{ch}"})
        write(C.OUT / C.LAYER_REF / ch_folder[ch] / f"{ch_hub[ch]}.md", head + "\n" + text); written["chapter"] += 1

    # ---- 공용: 발췌 렌더
    def unit_link(sec):
        """유닛의 절 번호 → (파일명, 표시 라벨)"""
        if sec in sec_fn: return sec_fn[sec], f"§{sec} {secs[sec]['heading'].split(' — ')[0].replace('`', '')}"
        if sec in sub_fn: return sub_fn[sec], f"§{sec} {subs[sec]['heading'].split(' — ')[0].replace('`', '')}"
        if sec in ch_hub: return ch_hub[sec], f"§{sec} {chaps[sec]['title'].split(' — ')[0].replace('`', '')}"
        return None, f"§{sec}"

    def render_units(units, group=True):
        """발췌 유닛 목록 → 불릿. group=True면 절별로 굵은 링크 머리줄을 둔다."""
        out = []; last = None
        for u in units:
            fn, label = unit_link(u["sec"])
            if group and u["sec"] != last:
                out.append(f"**[[{fn}|{alias_safe(label)}]]**" if fn else f"**{label}**")
                last = u["sec"]
            out.append(f"- {u['text']}")
        return out

    def render_authored(fields, order):
        out = []
        for lab in order:
            if lab in fields and fields[lab]:
                body = unwrap(fields[lab])
                if len(body) == 1 and not body[0].startswith(("- ", "```", "|", "1. ")):
                    out.append(f"**{lab}:** {body[0]}")
                else:
                    out.append(f"**{lab}:**"); out += body
                out.append("")
        return out

    # ---- 공용: 발췌 층(`Maro Excerpt/`) — 용어·실패 노트는 `## 발췌`에 출처 링크 + 상세 링크만 남기고 본문은 여기로 분리
    def excerpt_sections(cx, kind):
        """context 항목 → [(H2, 불릿들)]. 관련 실패/관련 용어는 소유 노트에 남으므로 제외."""
        out = []
        if cx["body"]:
            out.append(("본문 발췌" if kind == "term" else "출처 발췌", render_units(cx["body"])))
        if cx["ctx"]:
            ls = []
            for u in cx["ctx"]:
                fn, label = unit_link(u["sec"])
                ls.append(f"- {u['text']} ([[{fn}|{alias_safe(label)} 해설]])" if fn else f"- {u['text']}")
            out.append(("해설지 문맥", ls))
        rows = list(cx["rows"]) + (list(cx.get("chron", [])) if kind == "failure" else [])
        if rows:
            ls = []
            for u in rows:
                fn, label = unit_link(u["sec"])
                ls.append(f"- [[{fn}|{alias_safe(label)}]] · {u['text']}" if fn else f"- {label} · {u['text']}")
            out.append(("사전·규칙" if kind == "term" else "규칙·연대기", ls))
        if kind == "failure" and cx.get("mentions"):
            out.append(("언급 위치", render_units(cx["mentions"])))
        return out

    def excerpt_counts(cx, kind):
        c = collections.OrderedDict([("본문", len(cx["body"])), ("문맥", len(cx["ctx"])),
                                     ("규칙", len(cx["rows"]) + (len(cx.get("chron", [])) if kind == "failure" else 0))])
        if kind == "failure": c["언급"] = len(cx.get("mentions", []))
        return c

    def excerpt_sources(cx):
        """출처 절 링크 목록 — body → ctx → rows → chron → mentions 순으로 처음 나온 절만"""
        order = []
        for key in ("body", "ctx", "rows", "chron", "mentions"):
            for u in cx.get(key, []):
                if u["sec"] not in order: order.append(u["sec"])
        links = []
        for s in order:
            fn, _ = unit_link(s)
            links.append(f"[[{fn}|§{s}]]" if fn else f"§{s}")
        return links

    def excerpt_path(kind, e_or_f):
        if kind == "term":
            rel = pathlib.PurePosixPath(e_or_f["folder"]).relative_to(C.LAYER_NOTE)
            return C.OUT / C.LAYER_EXCERPT / "용어" / pathlib.Path(*rel.parts) / f"{e_or_f['filename']}{C.EXCERPT_SUFFIX}.md"
        return C.OUT / C.LAYER_EXCERPT / "실패" / class_folder[e_or_f["cls"]] / f"{fail_fn[e_or_f['id']]}{C.EXCERPT_SUFFIX}.md"

    def write_excerpt(owner_fn, display, kind, cx, path, self_key, meta):
        """발췌 노트 하나를 쓰고 (건수, 절별 건수, 출처 링크들)을 돌려준다"""
        secs_ = excerpt_sections(cx, kind); counts = excerpt_counts(cx, kind)
        n = sum(counts.values()); srcs = excerpt_sources(cx)
        owner_lk = f"[[{owner_fn}]]" if owner_fn == display else f"[[{owner_fn}|{alias_safe(display)}]]"
        body = [f"**한 줄 요약:** {owner_lk}의 기계 발췌 {n}건입니다 — " + " · ".join(f"{a} {b}" for a, b in counts.items()) +
                ". 출처: " + ", ".join(srcs), ""]
        for h2, ls in secs_: body += [f"## {h2}", ""] + ls + [""]
        body += ["---", "", f"**돌아가기:** {owner_lk}"]
        text = L.link("\n".join(body) + "\n", self_key, set(), path.stem, mode="first-per-note")
        fmh = fm(dict(meta, type="excerpt", title=path.stem, of=owner_fn, of_type=kind, excerpts=n,
                      tags=["maro/excerpt", f"excerpt/{kind}"], source="docs/maro-master-reference.md (기계 발췌; build_context.py)"))
        assert_clean(text, path.stem); write(path, fmh + "\n" + text); written["excerpt"] += 1
        return n, counts, srcs

    def excerpt_block(stem, n, counts, srcs):
        """소유 노트의 `## 발췌` 절"""
        detail = f"발췌 {n}건 (" + " · ".join(f"{a} {b}" for a, b in counts.items() if b) + ")"
        return ["## 발췌", "", "**출처:** " + ", ".join(srcs), f"**상세:** [[{stem}|{detail}]]", ""]

    # ---- 용어 노트
    for k in inc_terms:
        e = E[k]
        chain, prereq = SUBS.get((e["top"], e["sub"]), (e["sub"], ""))
        primary = next((m for m in e["meanings"] if m["item"] == e["explained_in"]), e["meanings"][0])
        cx = context["terms"].get(k, {"body": [], "ctx": [], "rows": []})
        expl = items16.get(k)
        head = [f"**한 줄 요약:** {primary['meaning']}", ""]
        head.append(f"**분류:** [[{cat_hub[e['top']]}|{e['top']}]] › [[{branch_hub[(e['top'], e['sub'])]}|{e['sub']}]]")
        if prereq: head.append(f"**필요 하위 개념:** {prereq}")
        head.append("")
        nex = len(cx["body"]) + len(cx["ctx"]) + len(cx["rows"])
        head += ["## 해설", ""]
        if expl and expl["fields"]:
            head += render_authored(expl["fields"], C.AUTHORED_T)
        else:
            head += ["_미작성 — §16 용어 해설 배치에서 채워집니다." + (" 발췌 노트(`## 발췌` → 상세)가 현재의 근거입니다._" if nex else "_"), ""]
        if e["subknow"]:
            head += ["## 하위지식", ""]
            for sk in e["subknow"]:
                tgt = sec_fn.get(sk["item"]) or ch_hub.get(sk["item"])
                head.append(f"- *{sk['title']}* ([[{tgt}|§{sk['item']}]])" if tgt else f"- *{sk['title']}*")
                for l in unwrap(sk["lines"]):
                    head.append(("    " + l) if l.strip() else "")
            head.append("")
        others = [m for m in e["meanings"] if m is not primary and m["meaning"] != primary["meaning"]]
        if others:
            head += ["## 문맥별 뜻", ""]
            for m in others:
                tgt = sec_fn.get(m["item"]) or ch_hub.get(m["item"])
                head.append(f"- [[{tgt}|§{m['item']}]] — {m['meaning']}" if tgt else f"- §{m['item']} — {m['meaning']}")
            head.append("")
        ex = []; exc_stem = None
        if nex:
            xp = excerpt_path("term", e); exc_stem = xp.stem
            n_, counts_, srcs_ = write_excerpt(e["filename"], e["display"], "term", cx, xp, k,
                                               {"term": e["display"], "category": e["top"], "branch": e["sub"], "sections": e["secs"]})
            ex += excerpt_block(exc_stem, n_, counts_, srcs_)
        fmap = {f["id"]: f for f in fails}
        if e["failures"]:
            ex += ["## 관련 실패", ""]
            for fid in e["failures"]:
                if fid not in fail_fn: continue
                f = fmap[fid]; fl = f["fields"]
                bits = [f"{lab}: {fl[lab]}" for lab in ("증상", "근본 원인", "해결/결정", "대체", "상태") if lab in fl]
                ex.append(f"- [[{fail_fn[fid]}|{fid} {alias_safe(f['title'].replace('`', ''))}]]" + (" — " + " · ".join(bits) if bits else ""))
            ex.append("")
        tail = ["## 연결", ""]
        appear = []
        for sn in e["secs"]:
            tgt = sec_fn.get(sn) or ch_hub.get(sn)
            appear.append(f"[[{tgt}|§{sn}]]" if tgt else f"§{sn}")
        tail.append(f"**등장 절:** {', '.join(appear)}")
        if e["mates"]:
            tail.append("**같은 행:** " + ", ".join((f"[[{E[m]['filename']}]]" if E[m]['filename'] == E[m]['display'] else f"[[{E[m]['filename']}|{alias_safe(E[m]['display'])}]]") for m in e["mates"] if m in E))
        if k in C.CROSS_VAULT_LINKS:
            tail.append(f"**같이 보기:** [[{C.CROSS_VAULT_LINKS[k]}]]")
        seen = set()
        text = L.link("\n".join(head) + "\n", k, seen, e["filename"])
        text += L.link("\n".join(ex) + "\n", k, seen, e["filename"], mode="first-per-note") if ex else ""
        text += L.link("\n".join(tail) + "\n", k, seen, e["filename"])
        fmh = fm({"type": "term", "title": e["display"], "term": e["display"], "aliases": e["aliases"], "category": e["top"], "branch": e["sub"],
                  "chain": f"{e['top']} > {chain} > 용어", "depth": e["depth"], "explained_in": e["explained_in"], "sections": e["secs"],
                  "failures": e["failures"], "authored": "true" if expl and expl["fields"] else "false", "excerpts": nex, "excerpt_note": exc_stem,
                  "tags": ["maro/term", C.CAT_TAGS[e["top"]], "depth/deep" if e["depth"] == "심화" else "depth/basic"] + (["authored"] if expl and expl["fields"] else []),
                  "source": "docs/maro-master-reference.md §13, §15" + (", §16" if expl else "")})
        assert_clean(text, e["filename"]); write(term_path(k), fmh + "\n" + text); written["term"] += 1

    # ---- 가지/카테고리 허브
    by_branch = collections.defaultdict(list)
    for k in inc_terms: by_branch[(E[k]["top"], E[k]["sub"])].append(k)
    for (top, sub), ks in by_branch.items():
        chain, prereq = SUBS.get((top, sub), (sub, ""))
        deep = sum(1 for k in ks if E[k]["depth"] == "심화")
        body = [f"**한 줄 요약:** {top} › {sub} 가지입니다 — 용어 {len(ks)}개(심화 {deep}개).", "",
                f"**사슬:** [[{cat_hub[top]}|{top}]] > {chain}", f"**필요 하위 개념:** {prereq}", "", "## 용어", ""]
        for k in ks:
            e = E[k]; m = e["meanings"][0]["meaning"]
            body.append(f"- {'★' if e['depth']=='심화' else '·'} [[{e['filename']}|{alias_safe(e['display'])}]] — {m[:80] + ('…' if len(m) > 80 else '')}")
        text = "\n".join(body) + "\n"
        head = fm({"type": "branch", "title": f"{top} › {sub}", "category": top, "branch": sub, "chain": f"{top} > {chain}", "prereq": prereq,
                   "count": len(ks), "tags": ["maro/term", C.CAT_TAGS[top], "hub"]})
        write(C.OUT / C.LAYER_NOTE / cat_folder[top] / N.branch_folder(sub) / f"{branch_hub[(top, sub)]}.md", head + "\n" + text); written["branch"] += 1
    by_cat = collections.defaultdict(list)
    for (top, sub) in by_branch: by_cat[top].append(sub)
    for top, subl in by_cat.items():
        n = sum(len(by_branch[(top, s)]) for s in subl); d = sum(1 for s in subl for k in by_branch[(top, s)] if E[k]["depth"] == "심화")
        body = [f"**한 줄 요약:** {top} 카테고리입니다 — 가지 {len(subl)}개, 용어 {n}개(심화 {d}개).", "", "## 가지", ""]
        for s in subl:
            body.append(f"- [[{branch_hub[(top, s)]}|{s}]] — 용어 {len(by_branch[(top, s)])}개 · 필요 하위 개념: {SUBS.get((top, s), (s, ''))[1]}")
        head = fm({"type": "category", "title": top, "category": top, "count": n, "tags": ["maro/term", C.CAT_TAGS[top], "hub"]})
        write(C.OUT / C.LAYER_NOTE / cat_folder[top] / f"{cat_hub[top]}.md", head + "\n" + "\n".join(body) + "\n"); written["category"] += 1

    # ---- 실패 노트 + 분류 허브
    by_class = collections.defaultdict(list)
    for f in inc_fails:
        cls = f["cls"]; by_class[cls].append(f)
        cx = context["failures"].get(f["id"], {"body": [], "ctx": [], "rows": [], "chron": [], "mentions": [], "terms": []})
        authored = f.get("authored", {})
        head = [f"**한 줄 요약:** {f['title']}", "", f"**분류:** [[{class_hub[cls]}|{f['code']} {dict(C.FAIL_CLASSES)[f['code']]}]]", "",
                "## 개요", ""]
        for lab, val in f["fields"].items():
            head.append(f"**{lab}:** {val}")
        head.append("")
        if authored:
            for lab in C.AUTHORED_F:
                if lab in authored and authored[lab]:
                    head += [f"## {lab}", ""] + unwrap(authored[lab]) + [""]
        else:
            nex0 = len(cx["body"]) + len(cx["ctx"]) + len(cx["rows"]) + len(cx["chron"]) + len(cx["mentions"])
            head += ["## 해설", "", "_미작성 — §14 집필 배치에서 발단·원인 해설·증거·해결책·교훈이 채워집니다." +
                     (" 발췌 노트(`## 발췌` → 상세)가 현재의 근거입니다._" if nex0 else "_"), ""]
        ex = []; exc_stem = None
        src_secs = [r for r in re.findall(r"§(\d+(?:\.\d+)*)", f["fields"].get("출처", "")) if not r.startswith("13.")]
        if cx["body"] or cx["ctx"] or cx["rows"] or cx["chron"] or cx["mentions"]:
            xp = excerpt_path("failure", f); exc_stem = xp.stem
            n_, counts_, srcs_ = write_excerpt(fail_fn[f["id"]], f"{f['id']} {f['title'].replace('`', '')}", "failure", cx, xp, None,
                                               {"id": f["id"], "class": f["code"], "sections": src_secs})
            ex += excerpt_block(exc_stem, n_, counts_, srcs_)
        if cx["terms"]:
            ex += ["## 관련 용어", ""]
            for k in cx["terms"]:
                if k not in E or E[k]["display"].lower() in C.STOPWORDS: continue
                e = E[k]; m = next((mm for mm in e["meanings"] if mm["item"] == e["explained_in"]), e["meanings"][0])["meaning"]
                lk = f"[[{e['filename']}]]" if e["filename"] == e["display"] else f"[[{e['filename']}|{alias_safe(e['display'])}]]"
                ex.append(f"- {lk} — {m}")
            ex.append("")
        seen = set()
        text = L.link("\n".join(head) + "\n", None, seen, fail_fn[f["id"]])
        text += L.link("\n".join(ex) + "\n", None, seen, fail_fn[f["id"]], mode="first-per-note") if ex else ""
        fmh = fm({"type": "failure", "title": f"{f['id']} {f['title']}", "id": f["id"], "class": f["code"], "class_name": dict(C.FAIL_CLASSES)[f["code"]],
                  "discovery": f["fields"].get("발견 경위", ""), "sections": src_secs, "authored": "true" if authored else "false", "excerpt_note": exc_stem,
                  "tags": ["maro/fail", f"fail/{f['code']}"] + (["authored"] if authored else []), "source": f"docs/maro-master-reference.md §{cls}"})
        assert_clean(text, fail_fn[f["id"]]); write(fail_path(f), fmh + "\n" + text); written["failure"] += 1
    for cls, fl in by_class.items():
        fc = fclasses[cls]
        body = [f"**한 줄 요약:** {fc['title']} — {len(fl)}건.", ""] + unwrap(fc.get("intro", [])) + ["", "## 항목", ""]
        for f in fl:
            body.append(f"- [[{fail_fn[f['id']]}|{f['id']}]] — {f['title']}")
        if fc.get("outro"):
            body += ["", "## 후속", ""] + unwrap(fc["outro"])
        head = fm({"type": "failclass", "title": fc["title"], "class": fc["code"], "count": len(fl), "tags": ["maro/fail", f"fail/{fc['code']}", "hub"]})
        write(C.OUT / C.LAYER_FAIL / class_folder[cls] / f"{class_hub[cls]}.md", head + "\n" + "\n".join(body) + "\n"); written["failclass"] += 1

    # ---- 층 허브 + 루트
    ref_body = ["**한 줄 요약:** 마스터 레퍼런스의 장·절 층입니다 — 기존 보관함의 `Camera/`처럼 문서 구조를 그대로 미러링하며, 절 노트의 용어는 `Maro Note/`의 개념 노트로, 실패 사례는 `Maro Failure/`로 링크됩니다.", "", "## 장", ""]
    for ch in inc_chaps:
        ref_body.append(f"- [[{ch_hub[ch]}|{ch_folder[ch]}]] — {one_liner(chaps[ch]['intro'], chaps[ch]['title'].split(' — ')[0].replace('`',''))}")
    write(C.OUT / C.LAYER_REF / f"{layer_hub['ref']}.md", fm({"type": "hub", "title": C.LAYER_REF, "tags": ["maro/ref", "hub"]}) + "\n" + "\n".join(ref_body) + "\n")
    note_body = ["**한 줄 요약:** 개념 사전 층입니다 — §15 분류 체계(11 카테고리 → 72 가지 → 용어)를 폴더로 옮겼고, 각 용어 노트는 뜻·사슬·필요 하위 개념·하위지식·등장 절·관련 실패를 담습니다.", ""]
    note_body += unwrap(model.get("ch15_intro", [])) + ["", "## 카테고리", ""]
    for top in TOP_ORDER:
        if top in by_cat: note_body.append(f"- [[{cat_hub[top]}|{top}]] — 가지 {len(by_cat[top])}개, 용어 {sum(len(by_branch[(top, s)]) for s in by_cat[top])}개")
    write(C.OUT / C.LAYER_NOTE / f"{layer_hub['note']}.md", fm({"type": "hub", "title": C.LAYER_NOTE, "tags": ["maro/term", "hub"]}) + "\n" + "\n".join(note_body) + "\n")
    fail_body = ["**한 줄 요약:** 실패·오류·폐기 카탈로그 층입니다 — 개발 전 기간의 버그·크래시·테스트 결함·플랫폼 한계·반증된 가설·폐기 기술을 분류별 폴더와 항목별 노트로 나눴습니다.", ""]
    fail_body += unwrap(model.get("ch14_intro", [])) + [""] + unwrap(fclasses.get("_legend", [])) + ["", "## 분류", ""]
    for cls in sorted(by_class, key=lambda x: int(x.split(".")[1])):
        fail_body.append(f"- [[{class_hub[cls]}|{class_folder[cls]}]] — {len(by_class[cls])}건")
    ft = L.link("\n".join(fail_body) + "\n", None, set())
    write(C.OUT / C.LAYER_FAIL / f"{layer_hub['fail']}.md", fm({"type": "hub", "title": C.LAYER_FAIL, "tags": ["maro/fail", "hub"]}) + "\n" + ft)
    n_exc_t = sum(1 for p in (C.OUT / C.LAYER_EXCERPT / "용어").rglob("*.md")) if (C.OUT / C.LAYER_EXCERPT / "용어").exists() else 0
    n_exc_f = sum(1 for p in (C.OUT / C.LAYER_EXCERPT / "실패").rglob("*.md")) if (C.OUT / C.LAYER_EXCERPT / "실패").exists() else 0
    exc_body = [f"**한 줄 요약:** 기계 발췌 층입니다 — 용어 노트 {n_exc_t}개, 실패 노트 {n_exc_f}개에 대해 마스터 레퍼런스에서 그 이름이 등장하는 문장·표 행·해설지 문맥을 `build_context.py`가 골라 모아 둔 노트들입니다. 목록은 두지 않습니다: 각 용어·실패 노트의 `## 발췌 → 상세` 링크로 들어옵니다.", "",
                "## 구성", "",
                f"- `용어/<카테고리>/<가지>/<용어>{C.EXCERPT_SUFFIX}.md` — `{C.LAYER_NOTE}/`의 폴더 구조를 그대로 미러링",
                f"- `실패/<분류>/<F-번호 제목>{C.EXCERPT_SUFFIX}.md` — `{C.LAYER_FAIL}/`의 분류 폴더를 그대로 미러링", "",
                "## 읽는 법", "",
                "- 발췌 노트의 절: 용어는 **본문 발췌 → 해설지 문맥 → 사전·규칙**, 실패는 **출처 발췌 → 해설지 문맥 → 규칙·연대기 → 언급 위치**. 절마다 굵은 링크 머리줄이 원천 절(§n.m) 노트를 엽니다.",
                "- 발췌는 기계가 골랐으므로 빗나간 문장이 섞일 수 있습니다. 해석은 소유 노트의 `## 해설`(집필)이 우선이며, 발췌는 그 근거·문맥입니다.",
                "- 맨 아래 **돌아가기**가 소유 노트로 되돌아갑니다."]
    write(C.OUT / C.LAYER_EXCERPT / f"{layer_hub['exc']}.md", fm({"type": "hub", "title": C.LAYER_EXCERPT, "tags": ["maro/excerpt", "hub"]}) + "\n" + "\n".join(exc_body) + "\n")
    root = ["**한 줄 요약:** Maro(Maya ↔ ROS 2) 프로젝트 마스터 레퍼런스의 Obsidian 판입니다 — 원천은 `Maya_Ros_Sim/docs/maro-master-reference.md`이며, 이 폴더의 노트는 전부 그 파일에서 생성됩니다(손으로 고치지 말고 원천을 고친 뒤 재생성).", "",
            f"**생성일:** {TODAY}", "", "## 층", "",
            f"- [[{layer_hub['ref']}|{C.LAYER_REF}]] — 장·절·소절 노트(문서 구조 미러링)",
            f"- [[{layer_hub['note']}|{C.LAYER_NOTE}]] — 개념 사전(§15 분류 체계 + §16 집필 해설)",
            f"- [[{layer_hub['fail']}|{C.LAYER_FAIL}]] — 실패·오류·폐기 카탈로그(§14)",
            f"- [[{layer_hub['exc']}|{C.LAYER_EXCERPT}]] — 용어·실패 노트별 기계 발췌(원문 문장·표 행·해설지 문맥)", "",
            "## 읽는 법", "",
            "- 절 노트 본문의 용어는 개념 노트로 링크됩니다. 개념 노트의 **등장 절**로 되돌아옵니다.",
            "- 소절 노트(파일 하나 = 소스 파일 하나)는 끝의 **상위 절**로 절 노트에 붙어 있습니다.",
            "- 용어·실패 노트의 `## 발췌`는 출처 절 링크와 **상세** 링크만 둡니다. 상세를 따라가면 발췌 노트가 열리고, 그 끝의 **돌아가기**로 돌아옵니다.",
            "- `§n.m` 표기는 원천 문서의 절 번호이며 링크로 그 절 노트를 엽니다."]
    write(C.OUT / f"{C.ROOT_HUB}.md", fm({"type": "hub", "title": C.ROOT_HUB, "tags": ["maro", "hub"]}) + "\n" + "\n".join(root) + "\n")
    written["hub"] += 4 + 1
    # ---- 개수 표
    counts = collections.Counter()
    for p in C.OUT.rglob("*.md"):
        counts[str(p.relative_to(C.OUT).parent).split("\\")[0].split("/")[0]] += 1
    C.REPORTS.mkdir(exist_ok=True)
    io.open(C.REPORTS / "counts.md", "w", encoding="utf-8").write("| 층/폴더 | 노트 수 |\n|---|---|\n" + "\n".join(f"| {k} | {v} |" for k, v in sorted(counts.items())) + f"\n| **합계** | {sum(counts.values())} |\n")
    print("written", dict(written), "total files", sum(1 for _ in C.OUT.rglob("*.md")))


if __name__ == "__main__":
    main()

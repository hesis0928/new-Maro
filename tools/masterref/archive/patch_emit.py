# -*- coding: utf-8 -*-
"""emit_vault.py: 용어·실패 노트 렌더러를 발췌·집필 골격으로 교체 (계획 2026-09-16)."""
import io
p = 'emit_vault.py'; s = io.open(p, encoding='utf-8').read()

# 0) unwrap → textutil
s = s.replace('from linkify import Linker, assert_clean, alias_safe\n',
              'from linkify import Linker, assert_clean, alias_safe\nfrom textutil import unwrap\n')
a = s.index('BLOCK_START = re.compile('); b = s.index('def one_liner(')
s = s[:a] + s[b:]

# 1) context.json 로드
s = s.replace('''    E = index["entries"]
    secs, subs, chaps, items, fails, fclasses = model["sections"], model["subsections"], model["chapters"], model["items13"], model["failures"], model["fail_classes"]''',
'''    E = index["entries"]
    secs, subs, chaps, items, fails, fclasses = model["sections"], model["subsections"], model["chapters"], model["items13"], model["failures"], model["fail_classes"]
    ctxp = C.WORK / "context.json"
    context = json.load(io.open(ctxp, encoding="utf-8")) if ctxp.exists() else {"terms": {}, "failures": {}, "fail_terms": {}}
    items16 = model.get("items16", {})''')

# 2) 용어 노트 렌더러 교체
t0 = s.index('    # ---- 용어 노트'); t1 = s.index('    # ---- 가지/카테고리 허브')
term_block = '''    # ---- 공용: 발췌 렌더
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
        head += ["## 해설", ""]
        if expl and expl["fields"]:
            head += render_authored(expl["fields"], C.AUTHORED_T)
        else:
            head += ["_미작성 — §16 용어 해설 배치에서 채워집니다. 아래 발췌·문맥이 현재의 근거입니다._", ""]
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
        ex = []
        if cx["body"]:
            ex += ["## 본문 발췌", ""] + render_units(cx["body"]) + [""]
        if cx["ctx"]:
            ex += ["## 해설지 문맥", ""]
            for u in cx["ctx"]:
                fn, label = unit_link(u["sec"])
                ex.append(f"- {u['text']} ([[{fn}|{alias_safe(label)} 해설]])" if fn else f"- {u['text']}")
            ex.append("")
        if cx["rows"]:
            ex += ["## 사전·규칙", ""]
            for u in cx["rows"]:
                fn, label = unit_link(u["sec"])
                ex.append(f"- [[{fn}|{alias_safe(label)}]] · {u['text']}" if fn else f"- {label} · {u['text']}")
            ex.append("")
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
        text = L.link("\\n".join(head) + "\\n", k, seen, e["filename"])
        text += L.link("\\n".join(ex) + "\\n", k, seen, e["filename"], mode="first-per-note") if ex else ""
        text += L.link("\\n".join(tail) + "\\n", k, seen, e["filename"])
        nex = len(cx["body"]) + len(cx["ctx"]) + len(cx["rows"])
        fmh = fm({"type": "term", "title": e["display"], "term": e["display"], "aliases": e["aliases"], "category": e["top"], "branch": e["sub"],
                  "chain": f"{e['top']} > {chain} > 용어", "depth": e["depth"], "explained_in": e["explained_in"], "sections": e["secs"],
                  "failures": e["failures"], "authored": "true" if expl and expl["fields"] else "false", "excerpts": nex,
                  "tags": ["maro/term", C.CAT_TAGS[e["top"]], "depth/deep" if e["depth"] == "심화" else "depth/basic"] + (["authored"] if expl and expl["fields"] else []),
                  "source": "docs/maro-master-reference.md §13, §15" + (", §16" if expl else "")})
        assert_clean(text, e["filename"]); write(term_path(k), fmh + "\\n" + text); written["term"] += 1

'''
s = s[:t0] + term_block + s[t1:]

# 3) 실패 노트 렌더러 교체
f0 = s.index('    # ---- 실패 노트 + 분류 허브'); f1 = s.index('    for cls, fl in by_class.items():')
fail_block = '''    # ---- 실패 노트 + 분류 허브
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
            head += ["## 해설", "", "_미작성 — §14 집필 배치에서 발단·원인 해설·증거·해결책·교훈이 채워집니다. 아래 발췌가 현재의 근거입니다._", ""]
        ex = []
        if cx["body"]:
            ex += ["## 출처 발췌", ""] + render_units(cx["body"]) + [""]
        if cx["ctx"]:
            ex += ["## 해설지 문맥", ""]
            for u in cx["ctx"]:
                fn, label = unit_link(u["sec"])
                ex.append(f"- {u['text']} ([[{fn}|{alias_safe(label)} 해설]])" if fn else f"- {u['text']}")
            ex.append("")
        if cx["rows"] or cx["chron"]:
            ex += ["## 규칙·연대기", ""]
            for u in cx["rows"] + cx["chron"]:
                fn, label = unit_link(u["sec"])
                ex.append(f"- [[{fn}|{alias_safe(label)}]] · {u['text']}" if fn else f"- {label} · {u['text']}")
            ex.append("")
        if cx["terms"]:
            ex += ["## 관련 용어", ""]
            for k in cx["terms"]:
                if k not in E: continue
                e = E[k]; m = next((mm for mm in e["meanings"] if mm["item"] == e["explained_in"]), e["meanings"][0])["meaning"]
                ex.append(f"- [[{e['filename']}|{alias_safe(e['display'])}]] — {m}")
            ex.append("")
        if cx["mentions"]:
            ex += ["## 언급 위치", ""] + render_units(cx["mentions"]) + [""]
        seen = set()
        text = L.link("\\n".join(head) + "\\n", None, seen, fail_fn[f["id"]])
        text += L.link("\\n".join(ex) + "\\n", None, seen, fail_fn[f["id"]], mode="first-per-note") if ex else ""
        src_secs = [r for r in re.findall(r"§(\\d+(?:\\.\\d+)*)", f["fields"].get("출처", "")) if not r.startswith("13.")]
        fmh = fm({"type": "failure", "title": f"{f['id']} {f['title']}", "id": f["id"], "class": f["code"], "class_name": dict(C.FAIL_CLASSES)[f["code"]],
                  "discovery": f["fields"].get("발견 경위", ""), "sections": src_secs, "authored": "true" if authored else "false",
                  "tags": ["maro/fail", f"fail/{f['code']}"] + (["authored"] if authored else []), "source": f"docs/maro-master-reference.md §{cls}"})
        assert_clean(text, fail_fn[f["id"]]); write(fail_path(f), fmh + "\\n" + text); written["failure"] += 1
'''
s = s[:f0] + fail_block + s[f1:]

# 4) 분류 허브에 outro
s = s.replace('''        for f in fl:
            body.append(f"- [[{fail_fn[f['id']]}|{f['id']}]] — {f['title']}")
        head = fm({"type": "failclass"''', '''        for f in fl:
            body.append(f"- [[{fail_fn[f['id']]}|{f['id']}]] — {f['title']}")
        if fc.get("outro"):
            body += ["", "## 후속", ""] + unwrap(fc["outro"])
        head = fm({"type": "failclass"''')
io.open(p, 'w', encoding='utf-8', newline='\n').write(s)
print('patched')

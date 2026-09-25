# -*- coding: utf-8 -*-
"""model.json + index.json → work/context.json : 용어/실패마다 마스터 원문에서 발췌한 문맥.
- 코퍼스 단위(Unit): 절·소절 본문의 불릿 1줄 / 문단 문장 / 표 행(§9·§10·§11은 kind 구분), §13 문맥 풀이 불릿(ctx)
- 용어: surfaces(평문, linkify.form_at 경계) + code_forms(백틱 스팬 정확/머리 일치)로 매칭. explained_in 절 우선. 상한 config.EXCERPT_CAPS
- 실패: 제목+원본 필드의 백틱 스팬(식별자) + 관련 용어 표면형으로 출처 절 범위 매칭, 점수=적중 식별자 수. F-id 언급 전역 수집
사용: python build_context.py"""
import io, re, sys, json, pathlib, collections
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import config as C
import naming as N
from textutil import unwrap, split_sentences, norm_key
from linkify import form_at

CODE = re.compile(r"`([^`\n]+)`")
BULLET = re.compile(r"^\s*(?:[-*+]|\d+\.)\s+")
LABEL = re.compile(r"^\*\*[^*]+:\*\*\s*")


def head_of(span):
    h = N.strip_trailing_group(span).strip()
    h = re.sub(r"<.*>$", "", h).strip()
    return h


class Corpus:
    def __init__(self, model):
        self.units = []          # dict(sec, kind, text, bt, ord)
        self.by_sec = collections.defaultdict(list)
        self.model = model
        secs, subs = model["sections"], model["subsections"]
        for n, s in secs.items():
            self._add_parts(n, s["parts"], self._row_kind(n))
        for n, s in subs.items():
            self._add_parts(n, s["parts"], "row")
        for key, it in model["items13"].items():
            for l in unwrap(it["context"]):
                t = BULLET.sub("", l).strip()
                if len(t) > 12: self._push(key, "ctx", t)

    @staticmethod
    def _row_kind(n):
        ch = n.split(".")[0]
        return {"9": "row9", "10": "row10", "11": "row11"}.get(ch, "row")

    def _push(self, sec, kind, text):
        u = {"sec": sec, "kind": kind, "text": text, "bt": sorted({m.group(1).strip() for m in CODE.finditer(text)}), "ord": len(self.units)}
        self.units.append(u); self.by_sec[sec].append(u["ord"])

    def _add_parts(self, n, parts, row_kind):
        lines = []
        for p in parts:
            if p["kind"] == "text": lines += p["lines"] + [""]
            elif p["kind"] == "inline": lines += [f"#### {p['heading']}", ""] + p["lines"] + [""]
        lines = unwrap(lines)
        in_fence = False
        for i, l in enumerate(lines):
            if l.strip().startswith("```"): in_fence = not in_fence; continue
            if in_fence or not l.strip() or l.startswith("#"): continue
            if l.startswith("**한 줄 요약:**"): continue
            if l.startswith("|"):
                nxt = lines[i + 1] if i + 1 < len(lines) else ""
                if re.match(r"^\|\s*-", l) or re.match(r"^\|\s*-", nxt): continue     # 구분선/헤더 행
                cells = [c.strip() for c in re.split(r"(?<!\\)\|", l.strip())[1:-1]]
                t = " · ".join(c for c in cells if c)
                if len(t) > 12: self._push(n, row_kind, t)
                continue
            if BULLET.match(l):
                t = BULLET.sub("", l).strip()
                if len(t) > 12: self._push(n, "bullet", t)
                continue
            for s in split_sentences(l):
                if len(s) > 12: self._push(n, "sent", s)


GENERIC = {"maya", "windows", "dll", "ros", "ros 2", "python", "c++", "qt", "cmake", "embree", "vcpkg", "test", "tests", "mll", "exe",
           "mayapy", "plugin", "maro", "linux", "msvc", "visual", "studio", "phase", "task", "finding", "review", "spec", "plan", "file",
           "true", "false", "none", "null", "kernel32", "api", "sdk", "devkit", "release", "debug"}

IDENT_TOK = re.compile(r"[A-Za-z_][\w:.]*(?:\(\))?")
KO_TOK = re.compile(r"[가-힣]{2,}")


def display_tokens(display):
    """서술형 용어의 유의미 토큰: 식별자(4자 이상, `()` 허용)와 한글 단어(2자 이상). 일반어는 STOPWORDS로 제외."""
    toks = []
    for m in IDENT_TOK.finditer(display):
        t = m.group(0)
        if len(t.rstrip("()")) >= 4 and t.lower() not in C.STOPWORDS: toks.append(("id", t))
    for m in KO_TOK.finditer(display):
        if m.group(0) not in ("이유", "경우", "때문", "위해", "대한", "대해", "이후", "이전", "전체", "관련"): toks.append(("ko", m.group(0)))
    return toks


def token_score(u, toks):
    n = 0
    for kind, t in toks:
        if kind == "id":
            h = head_of(t)
            if any(sp == t or sp == h or head_of(sp) == h for sp in u["bt"]) or re.search(r"(?<![A-Za-z0-9_])" + re.escape(h) + r"(?![A-Za-z0-9_])", u["text"]):
                n += 1
        else:
            m = re.search(re.escape(t), u["text"])
            if m and form_at(u["text"], m.start(), m.end(), t): n += 1
    return n


def scope_sections(model, item_key):
    """§13 항목 키(절 번호 또는 장 번호) → 본문 검색 범위(절 + 그 소절들)"""
    secs, subs = model["sections"], model["subsections"]
    if item_key in secs:
        return [item_key] + secs[item_key]["subsections"]
    if item_key in subs:
        return [item_key]
    if item_key in model["chapters"]:
        out = []
        for n in model["chapters"][item_key]["sections"]:
            out += [n] + secs[n]["subsections"]
        return out
    return []


def main():
    model = json.load(io.open(C.WORK / "model.json", encoding="utf-8"))
    index = json.load(io.open(C.WORK / "index.json", encoding="utf-8"))
    E = index["entries"]; amb = set(index.get("ambiguous", {}))
    corpus = Corpus(model); U = corpus.units
    caps = C.EXCERPT_CAPS

    # ---- 표면형 → 적중 유닛 (한 번의 스캔)
    def plain_forms(e):
        """발췌 매칭용 평문 표면형: 링크용 surfaces보다 관대하다(2자 한글 display도 허용 — 절 범위 안에서만 쓰이므로)"""
        fs = list(e["surfaces"]) + [a for a in e["aliases"] if not a.startswith("`")]
        d = e["display"]
        fs.append(d)
        # `한글(English)` / `X(설명)` 꼴은 괄호 앞 머리도 표면형으로(한글 2자 이상, ASCII는 4자 이상 또는 대문자 약어 2자 이상)
        m = re.match(r"^(.+?)\s*\(([^()]*)\)$", d)
        if m:
            fs.append(m.group(1).strip())
            en = m.group(2).strip()
            if re.match(r"^[\x20-\x7e]+$", en) and (len(en) >= 6 or re.match(r"^[A-Z][A-Z0-9_]+$", en)): fs.append(en)
        out = []
        for f in fs:
            f = f.strip()
            if not f: continue
            ko = bool(re.search("[가-힣]", f))
            if ko and len(f) < 2: continue
            if not ko and not (len(f) >= 4 or re.match(r"^[A-Z][A-Z0-9_]+$", f) and len(f) >= 2): continue
            if f.lower() in C.STOPWORDS: continue
            if f not in out: out.append(f)
        return out
    surf_owner = {}
    for k, e in E.items():
        for s in plain_forms(e):
            if s in amb and C.PREFER.get(s) != k: continue
            surf_owner.setdefault(s, k)
    forms = sorted(surf_owner, key=len, reverse=True)
    rx = re.compile("|".join(re.escape(f) for f in forms))
    surf_hits = collections.defaultdict(list)   # form -> [unit ord]
    code_hits = collections.defaultdict(list)   # span/head -> [unit ord]
    fid_hits = collections.defaultdict(list)    # F-### -> [unit ord]
    for u in U:
        plain = u["text"]          # 코드 스팬 안도 훑는다(`File > Optimize Scene Size`처럼 백틱 안에 든 평문 표면형) — 경계는 form_at이 지킨다
        seen_forms = set()
        for m in rx.finditer(plain):
            f = m.group(0)
            if f in seen_forms or not form_at(plain, m.start(), m.end(), f): continue
            seen_forms.add(f); surf_hits[f].append(u["ord"])
        for sp in u["bt"]:
            code_hits[sp].append(u["ord"])
            h = head_of(sp)
            if h != sp and len(h) >= 4: code_hits[h].append(u["ord"])
        for fid in set(re.findall(r"\bF-\d{3}\b", u["text"])):
            fid_hits[fid].append(u["ord"])

    def sec_order(item_key, e):
        prim = scope_sections(model, e["explained_in"])
        rest = []
        for s in e["secs"]:
            if s == e["explained_in"]: continue
            rest += [x for x in scope_sections(model, s) if x not in prim and x not in rest]
        return prim, rest

    def pick(cands, cap, taken):
        out = []
        for o in cands:
            u = U[o]; nk = norm_key(u["text"])
            if nk in taken: continue
            taken.add(nk); out.append({"sec": u["sec"], "kind": u["kind"], "text": u["text"]})
            if len(out) >= cap: break
        return out

    # ---- 용어
    ctx_terms = collections.OrderedDict(); empty_terms = []
    for k, e in E.items():
        hits = set()
        for f in plain_forms(e):
            if surf_owner.get(f) == k: hits.update(surf_hits.get(f, []))
        ident_like = [f for f in plain_forms(e) if re.match(r"^[A-Za-z_][\w:.<>()/\-]*$", f)]
        for cf in list(e["code_forms"]) + ident_like:
            hits.update(code_hits.get(cf, []))
            h = head_of(cf)
            if h != cf and len(h) >= 4: hits.update(code_hits.get(h, []))
        prim, rest = sec_order(k, e)
        if not hits:
            # 2차: 서술형 용어("bookPaths() 선초기화", "필터 → 접기 → 상한")는 토큰 조합으로 자기 절 안에서만 찾는다
            toks = display_tokens(e["display"])
            if toks:
                need = 1 if any(kind == "id" for kind, _ in toks) else min(2, len(toks))
                scope_units = [o for sec in prim + rest for o in corpus.by_sec.get(sec, []) if U[o]["kind"] in ("bullet", "sent", "row", "ctx")]
                scored = []
                for o in scope_units:
                    n = token_score(U[o], toks)
                    if n >= need: scored.append((-n, o))
                hits = {o for _, o in sorted(scored)}
        meanings_nk = {norm_key(m["meaning"]) for m in e["meanings"]}
        taken = set(meanings_nk) | {norm_key(e["display"])}
        hub_stop = e["display"] in C.HUB_STOPLIST
        body_cap = caps["hub_stop"] if hub_stop else caps["term_body"]
        def in_secs(secl, kinds):
            return sorted((o for o in hits if U[o]["sec"] in secl and U[o]["kind"] in kinds), key=lambda o: (secl.index(U[o]["sec"]), o))
        body_kinds = {"bullet", "sent", "row"}
        body = pick(in_secs(prim, body_kinds), body_cap, taken)
        if not hub_stop and len(body) < caps["term_body"]:
            body += pick(in_secs(rest, body_kinds), caps["term_body"] - len(body), taken)
        if not hub_stop and len(body) < caps["term_body_other"]:
            # 등장 절 밖의 언급(문서 순서) — 개요 장에서만 정의된 용어가 실제로 다뤄지는 절을 잡는다
            others = sorted(o for o in hits if U[o]["kind"] in body_kinds and U[o]["sec"] not in prim and U[o]["sec"] not in rest)
            body += pick(others, caps["term_body_other"] - len(body), taken)
        ctx = pick(in_secs(list(dict.fromkeys([e["explained_in"]] + e["secs"])), {"ctx"}), caps["term_ctx"], taken)
        rows = pick(sorted((o for o in hits if U[o]["kind"] == "row11"), key=lambda o: o), caps["row11"], taken)
        rows += pick(sorted((o for o in hits if U[o]["kind"] == "row10"), key=lambda o: o), caps["row10"], taken)
        ctx_terms[k] = {"body": body, "ctx": ctx, "rows": rows, "n_hits": len(hits)}
        if not body and not ctx and not rows: empty_terms.append(k)

    # ---- 실패
    fail_terms = collections.defaultdict(list)
    for k, e in E.items():
        for fid in e["failures"]: fail_terms[fid].append(k)
    ctx_fails = collections.OrderedDict(); empty_fails = []
    secs = model["sections"]
    for f in model["failures"]:
        fid = f["id"]
        idents = set()
        for txt in [f["title"]] + [v for lab, v in f["fields"].items()]:
            for m in CODE.finditer(txt):
                sp = m.group(1).strip()
                if len(sp) < 4 or re.fullmatch(r"[\d.,\-:]+", sp) or sp.startswith(".") or sp.lower() in GENERIC: continue
                idents.add(sp); h = head_of(sp)
                if h != sp and len(h) >= 4: idents.add(h)
        # 관련 용어 표면형은 식별자가 하나도 없는 실패(52건)에서만 보조로 쓴다 — 'FAIL' 같은 일반어가 점수를 오염시킨다
        tsurf = set()
        if not idents:
            for k in fail_terms.get(fid, []):
                for s in E[k]["surfaces"]:
                    if surf_owner.get(s) == k and len(s) >= 5: tsurf.add(s)
        # 출처 범위
        scope = []
        for r in re.findall(r"§(\d+(?:\.\d+)*)", f["fields"].get("출처", "")):
            if r.startswith("13."):
                scope += scope_sections(model, r[3:])
            elif r.startswith("14") or r.startswith("15"):
                continue
            else:
                scope += scope_sections(model, r)
        scope = list(dict.fromkeys(scope))
        ctx_keys = list(dict.fromkeys([r[3:] if r.startswith("13.") else (r if r in model["items13"] else ".".join(r.split(".")[:2]))
                                       for r in re.findall(r"§(\d+(?:\.\d+)*)", f["fields"].get("출처", "")) if not r.startswith(("14", "15"))]))
        # 제목·필드의 서술 토큰(식별자·한글 단어)도 보조 점수 — 백틱 식별자 적중은 2점, 토큰은 1점
        ftoks = [t for t in display_tokens(f["title"] + " " + " ".join(f["fields"].get(l, "") for l in ("근본 원인", "증상")))
                 if not (t[0] == "id" and (t[1] in idents or head_of(t[1]) in idents))]
        ftoks = [t for t in dict.fromkeys(ftoks) if t[1].lower() not in GENERIC][:12]
        def score(o):
            u = U[o]; n = 0
            n += 2 * sum(1 for sp in u["bt"] if sp in idents or head_of(sp) in idents)
            low = CODE.sub(" ", u["text"])
            n += 2 * sum(1 for s in tsurf if s in low)
            n += token_score(u, ftoks)
            return n
        def ranked(pool):
            sc = [(score(o), o) for o in pool]
            # 식별자 적중(2점 이상) 또는 서술 토큰 2개 이상
            sc = [(s, o) for s, o in sc if s >= 2]
            return [o for s, o in sorted(sc, key=lambda x: (-x[0], x[1]))]
        taken = {norm_key(f["title"])} | {norm_key(v) for v in f["fields"].values()}
        body_pool = [o for s in scope for o in corpus.by_sec.get(s, []) if U[o]["kind"] in ("bullet", "sent", "row")]
        body = pick(ranked(body_pool), caps["fail_body"], taken)
        ctx_pool = [o for key in ctx_keys for o in corpus.by_sec.get(key, []) if U[o]["kind"] == "ctx"]
        ctx = pick(ranked(ctx_pool), caps["fail_ctx"], taken)
        rows = pick(ranked([u["ord"] for u in U if u["kind"] == "row10"]), caps["fail_row10"], taken)
        chron = pick(ranked([u["ord"] for u in U if u["kind"] in ("row9", "bullet", "sent") and u["sec"].startswith("9.")]), caps["fail_row9"], taken)
        mentions = pick(sorted(fid_hits.get(fid, [])), caps["fail_mentions"], taken)
        ctx_fails[fid] = {"body": body, "ctx": ctx, "rows": rows, "chron": chron, "mentions": mentions,
                          "terms": fail_terms.get(fid, []), "idents": sorted(idents)}
        if not body and not ctx and not mentions: empty_fails.append(fid)

    out = {"terms": ctx_terms, "failures": ctx_fails, "fail_terms": fail_terms,
           "stats": {"units": len(U), "terms_empty": len(empty_terms), "fails_empty": len(empty_fails)}}
    io.open(C.WORK / "context.json", "w", encoding="utf-8").write(json.dumps(out, ensure_ascii=False, indent=1))
    C.REPORTS.mkdir(exist_ok=True)
    io.open(C.REPORTS / "context-empty.md", "w", encoding="utf-8").write(
        f"# 발췌 0건\n\n## 용어 ({len(empty_terms)})\n" + "\n".join(f"- {E[k]['display']} ({k}; secs {E[k]['secs']})" for k in empty_terms) +
        f"\n\n## 실패 ({len(empty_fails)})\n" + "\n".join(f"- {fid}" for fid in empty_fails) + "\n")
    tb = [len(v["body"]) for v in ctx_terms.values()]; fb = [len(v["body"]) for v in ctx_fails.values()]
    print(f"units {len(U)} | terms: empty {len(empty_terms)}, avg body {sum(tb)/len(tb):.1f} | failures: empty {len(empty_fails)}, avg body {sum(fb)/len(fb):.1f}")


if __name__ == "__main__":
    main()

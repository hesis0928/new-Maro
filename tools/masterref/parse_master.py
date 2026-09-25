# -*- coding: utf-8 -*-
"""work/master.edited.md → work/model.json
chapters / sections(parts: text|inline|own) / subsections / items13(context, terms, subknow, extref) / failures / fail_classes / ch14_intro / ch15_intro"""
import io, re, sys, json, pathlib, collections
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import config as C

H2 = re.compile(r"^## (\d+)\. (.+)$")
H3 = re.compile(r"^### (\d+\.\d+) (.+)$")
H3_13 = re.compile(r"^### 13\.(\d+(?:\.\d+)?) (.+)$")
H4 = re.compile(r"^#### (.+)$")
H4_NUM = re.compile(r"^#### (\d+\.\d+\.\d+) (.+)$")
H4_F = re.compile(r"^#### (F-\d{3}) (.+)$")


def split_row(line):
    # 셀 안의 `\|`(GFM 이스케이프)는 원문 `|`로 되돌린다 — 노트 본문·파일명·표면형은 마크다운 표 밖에서 쓰인다
    return [c.strip().replace("\\|", "|") for c in re.split(r"(?<!\\)\|", line.strip())[1:-1]]


def parse_parts(lines):
    """절/소절 본문을 text|inline 파트로. own-note(#### N.M.K)는 호출자가 잘라 넘긴다."""
    parts = []; cur = {"kind": "text", "lines": []}
    for l in lines:
        m = H4.match(l)
        if m and not H4_NUM.match(l):
            if cur["lines"]: parts.append(cur)
            cur = {"kind": "inline", "heading": m.group(1).strip(), "lines": []}
            continue
        cur["lines"].append(l)
    if cur["lines"] or cur["kind"] == "inline": parts.append(cur)
    # 앞뒤 공백 정리
    for p in parts:
        while p["lines"] and p["lines"][0].strip() == "": p["lines"].pop(0)
        while p["lines"] and p["lines"][-1].strip() == "": p["lines"].pop()
    return [p for p in parts if p["lines"] or p["kind"] == "inline"]


def parse_section_block(lines):
    """### N.M 블록(헤딩 제외) → (parts with own refs, subsections dict)"""
    parts = []; subs = collections.OrderedDict()
    buf = []; cur_sub = None
    def flush_buf():
        nonlocal buf
        if cur_sub is None:
            parts.extend(parse_parts(buf))
        else:
            subs[cur_sub]["parts"] = parse_parts(buf)
        buf = []
    for l in lines:
        m = H4_NUM.match(l)
        if m:
            flush_buf()
            cur_sub = m.group(1)
            subs[cur_sub] = {"num": cur_sub, "heading": m.group(2).strip(), "parts": []}
            parts.append({"kind": "own", "num": cur_sub})
            continue
        buf.append(l)
    flush_buf()
    # 보강 참조 줄 분리
    for p in parts:
        if p["kind"] == "text":
            p["lines"] = [x for x in p["lines"] if not x.startswith("> 보강 참조")]
    parts = [p for p in parts if p["kind"] != "text" or p["lines"]]
    return parts, subs


def parse_item13(lines):
    """§13 항목 본문 → context(lines), terms(rows), subknow(list), extref(lines)"""
    ctx = []; terms = []; subknow = []; ext = []
    mode = "ctx"; cur_sk = None
    for l in lines:
        if l.startswith("| 용어") or re.match(r"^\|\s*-", l):
            mode = "table"; continue
        if mode == "table" and l.startswith("|"):
            cells = split_row(l)
            if len(cells) >= 4:
                depth_cell = cells[3]
                depth = "심화" if depth_cell.startswith("심화") else "개념"
                mref = re.search(r"§13\.(\d+(?:\.\d+)?)", depth_cell)
                terms.append({"cells": cells[:4], "terms": [t.strip() for t in re.split(r"\s+/\s+", cells[0]) if t.strip()],
                              "depth": depth, "ref": mref.group(1) if mref else None})
            continue
        if mode == "table" and not l.startswith("|"):
            mode = "after"
        msk = re.match(r"^\*\*하위지식 — (.+?):\*\*\s*(.*)$", l)
        if msk:
            cur_sk = {"title": msk.group(1).strip(), "lines": ([msk.group(2)] if msk.group(2).strip() else [])}
            subknow.append(cur_sk); mode = "sk"; continue
        if l.startswith("**외부 참조:**"):
            mode = "ext"; rest = l[len("**외부 참조:**"):].strip()
            if rest: ext.append(rest)
            continue
        if mode == "ctx":
            ctx.append(l)
        elif mode == "sk":
            cur_sk["lines"].append(l)
        elif mode == "ext":
            ext.append(l)
        elif mode == "after":
            # 표 뒤 첫 텍스트(하위지식/외부 참조 라벨 전) — 드물게 존재하면 ctx 꼬리로
            if l.strip(): ctx.append(l)
    def clean(ls):
        while ls and ls[0].strip() == "": ls.pop(0)
        while ls and ls[-1].strip() == "": ls.pop()
        return ls
    ctx = clean(ctx)
    if ctx and ctx[0].startswith("**문맥 풀이:**"):
        rest = ctx[0][len("**문맥 풀이:**"):].strip()
        ctx = ([rest] if rest else []) + ctx[1:]
    for sk in subknow: sk["lines"] = clean(sk["lines"])
    return ctx, terms, subknow, clean(ext)


FIELD = re.compile(r"^\*\*([^*]+?):\*\*\s*(.*)$")
ALL_F_LABELS = set(C.ORIG_F_LABELS) | set(C.AUTHORED_F)


def clean_lines(ls):
    ls = list(ls)
    while ls and ls[0].strip() == "": ls.pop(0)
    while ls and ls[-1].strip() == "": ls.pop()
    return ls


def parse_fblock(body, j):
    """`#### F-###` 다음 줄부터. 열 0 `**라벨:**` — 뒤에 내용이 있으면 한 줄 필드(이어지는 비공백 줄은 공백으로 이어 붙임),
    비어 있으면 다중 행 필드(다음 열-0 라벨/#### /### /--- 까지 원문 줄 그대로). 알려진 라벨 밖의 라벨이나 `---`가 나오면
    블록이 끝난 것(§14 끝의 트레일러 등). 반환 (fields, authored, next_j)."""
    fields = collections.OrderedDict(); authored = collections.OrderedDict()
    cur = None; multi = False
    while j < len(body):
        l = body[j]
        if H4_F.match(l) or l.startswith("### ") or l.startswith("## ") or l.strip() == "---":
            break
        mm = FIELD.match(l)
        if mm:
            label, rest = mm.group(1).strip(), mm.group(2).strip()
            if label not in ALL_F_LABELS:
                break                       # 블록 밖 텍스트(outro)
            if rest:
                fields[label] = rest; cur = label; multi = False
            else:
                authored[label] = []; cur = label; multi = True
        elif multi:
            authored[cur].append(l)
        elif l.strip() and cur is not None:
            fields[cur] += " " + l.strip()
        j += 1
    for k in authored: authored[k] = clean_lines(authored[k])
    return fields, authored, j


def parse_items16(body, num, title):
    """§16 `### 16.N <카테고리>` 본문 → {term_key: {term, heading, category, fields: OrderedDict[label, lines]}}"""
    import naming as N
    out = collections.OrderedDict(); j = 0
    while j < len(body):
        m = H4.match(body[j])
        if not m: j += 1; continue
        heading = m.group(1).strip(); j += 1
        fields = collections.OrderedDict(); cur = None
        while j < len(body) and not H4.match(body[j]):
            mm = FIELD.match(body[j])
            if mm and mm.group(1).strip() in C.AUTHORED_T:
                cur = mm.group(1).strip(); fields[cur] = []
                if mm.group(2).strip(): fields[cur].append(mm.group(2).strip())
            elif cur is not None:
                fields[cur].append(body[j])
            j += 1
        for k in fields: fields[k] = clean_lines(fields[k])
        out[N.term_key(heading)] = {"term": heading, "heading": heading, "category": title, "cat_num": num, "fields": fields}
    return out


def main():
    text = io.open(C.WORK / "master.edited.md", encoding="utf-8").read()
    L = text.split("\n")
    model = {"chapters": collections.OrderedDict(), "sections": collections.OrderedDict(), "subsections": collections.OrderedDict(),
             "items13": collections.OrderedDict(), "items16": collections.OrderedDict(), "failures": [], "fail_classes": collections.OrderedDict(),
             "ch14_intro": [], "ch15_intro": [], "ch16_intro": [], "header": []}
    # 헤더(제목~목차 전)
    i = 0
    while i < len(L) and not L[i].startswith("## 목차"):
        model["header"].append(L[i]); i += 1
    # 헤딩 인덱스
    heads = []
    for n, l in enumerate(L):
        if l.startswith("## ") or l.startswith("### "):
            heads.append((n, l))
    heads.append((len(L), None))
    cur_ch = None; cur_fail_class = None
    for k in range(len(heads) - 1):
        n, l = heads[k]; end = heads[k + 1][0]
        body = L[n + 1:end]
        m2 = H2.match(l)
        if m2:
            ch = int(m2.group(1)); cur_ch = ch
            intro = [x for x in body]
            while intro and intro[-1].strip() == "": intro.pop()
            while intro and intro[0].strip() == "": intro.pop(0)
            intro = [x for x in intro if not x.startswith("> 보강 참조")]
            if ch <= 12:
                model["chapters"][str(ch)] = {"num": ch, "title": m2.group(2).strip(), "intro": intro, "sections": []}
            elif ch == 14:
                model["ch14_intro"] = intro
            elif ch == 15:
                model["ch15_intro"] = intro
            elif ch == 16:
                model["ch16_intro"] = intro
            continue
        m13 = H3_13.match(l)
        if m13 and cur_ch == 13:
            key = m13.group(1)
            ctx, terms, sk, ext = parse_item13(body)
            model["items13"][key] = {"key": key, "heading": m13.group(2).strip(), "context": ctx, "terms": terms, "subknow": sk, "extref": ext}
            continue
        m3 = H3.match(l)
        if m3 and cur_ch is not None and cur_ch <= 12:
            num = m3.group(1)
            parts, subs = parse_section_block(body)
            model["sections"][num] = {"num": num, "chapter": cur_ch, "heading": m3.group(2).strip(), "parts": parts, "subsections": list(subs.keys())}
            model["chapters"][str(cur_ch)]["sections"].append(num)
            for sn, sd in subs.items():
                sd["parent"] = num; sd["chapter"] = cur_ch
                model["subsections"][sn] = sd
            continue
        if m3 and cur_ch == 14:
            num = m3.group(1)
            if num == "14.0":
                model["fail_classes"]["_legend"] = body
                continue
            code = m3.group(2).split(" — ")[0].strip()
            cur_fail_class = num
            model["fail_classes"][num] = {"num": num, "code": code, "title": m3.group(2).strip(), "intro": [], "ids": []}
            # F 블록 파싱
            j = 0; intro = []; outro = []; seen_block = False
            while j < len(body):
                mf = H4_F.match(body[j])
                if mf:
                    seen_block = True
                    fid, title = mf.group(1), mf.group(2).strip()
                    fields, authored, j = parse_fblock(body, j + 1)
                    model["failures"].append({"id": fid, "title": title, "cls": num, "code": code, "fields": fields, "authored": authored})
                    model["fail_classes"][num]["ids"].append(fid)
                else:
                    (outro if seen_block else intro).append(body[j]); j += 1
            while intro and intro[-1].strip() == "": intro.pop()
            model["fail_classes"][num]["intro"] = [x for x in intro if x.strip()]
            model["fail_classes"][num]["outro"] = clean_lines(outro)
            continue
        if m3 and cur_ch == 16:
            num = m3.group(1)
            for key, blk in parse_items16(body, num, m3.group(2).strip()).items():
                if key in model["items16"]:
                    raise SystemExit(f"§16 duplicate term block: {blk['heading']} ({key})")
                model["items16"][key] = blk
            continue
    io.open(C.WORK / "model.json", "w", encoding="utf-8").write(json.dumps(model, ensure_ascii=False, indent=1))
    print(f"chapters {len(model['chapters'])} sections {len(model['sections'])} subsections {len(model['subsections'])} "
          f"items13 {len(model['items13'])} failures {len(model['failures'])} classes {len(model['fail_classes'])-1}")
    nterms = sum(len(r["terms"]) for it in model["items13"].values() for r in it["terms"])
    nsk = sum(len(it["subknow"]) for it in model["items13"].values())
    nauth = sum(1 for f in model["failures"] if f["authored"])
    print("term cells", nterms, "subknow blocks", nsk, "| authored failures", nauth, "items16", len(model["items16"]))


if __name__ == "__main__":
    main()

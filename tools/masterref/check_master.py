# -*- coding: utf-8 -*-
"""편집본 검사. (1) 계약: §13 89 / F 304 / 보강 참조 89 / >4열 표 0 / 목차=헤딩 / §참조 실재.
(2) 사실 보존: 블록(장 도입·절)마다 원천(master.v0)의 백틱 스팬(다중집합)·URL·§참조·F-ID·2자리 이상 숫자·따옴표 문자열이
    편집본 같은 블록에 남아 있는가. 길이 비율 ≥ 0.85.
(3) 편집된 블록 형식: 절/소절 본문 첫 줄 `**한 줄 요약:**`.
사용: python check_master.py [edited=work/master.edited.md] [--only 6.6,13.6.6] [--edited-keys]"""
import io, re, sys, collections, pathlib, json
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import config as C
from assemble_master import blocks_of, HEAD

FENCE = re.compile(r"^```")


def facts(block_lines):
    text = "\n".join(block_lines)
    # 펜스 블록은 통째로 하나의 사실(공백 정규화)로 세고 본문에서 뺀다 — ``` 가 인라인 백틱 짝을 흐트러뜨리므로
    fences = [re.sub(r"\s+", " ", f) for f in re.findall(r"```.*?```", text, re.S)]
    text = re.sub(r"```.*?```", " ", text, flags=re.S)
    # 하드 랩을 풀어 줄바꿈에 걸친 코드 스팬/따옴표가 양쪽에서 같은 문자열이 되게 한다
    text = re.sub(r"\s*\n\s*", " ", text)
    # 코드 스팬은 공백 무시 비교 — 원천의 하드 랩 자리("X/\nY" → "X/ Y")가 편집본에 강제되지 않게
    bt = collections.Counter(re.sub(r"\s+", "", m.group(1)) for m in re.finditer(r"`([^`]+)`", text))
    for f in fences: bt[f] += 1
    urls = set(re.findall(r"https?://[^\s)>\]]+", text))
    refs = set(re.findall(r"§\d+(?:\.\d+)*", text))
    fids = set(re.findall(r"\bF-\d{3}\b", text))
    nums = collections.Counter(re.findall(r"(?<![\w.])\d[\d,]{1,}(?:\.\d+)?(?![\w])", text))
    # 따옴표 문장: 코드 스팬을 제거한 뒤 "…"(4~120자, 한글 포함) 만 — 코드의 "world" 류는 백틱 검사가 이미 지킨다
    plain = re.sub(r"`[^`]+`", "", text)
    quotes = set(re.sub(r"\s+", "", q) for q in re.findall(r"[\"“]([^\"”]{1,120})[\"”]", plain)
                 if len(q) >= 4 and re.search(r"[가-힣]", q) and not re.search(r"\*\*|#|(^|\s)- |\|", q))
    return bt, urls, refs, fids, nums, quotes, len(text)


def compare(key, src, dst):
    sb, su, sr, sf, sn, sq, sl = facts(src)
    db, du, dr, df, dn, dq, dl = facts(dst)
    probs = []
    miss_bt = sb - db
    if miss_bt: probs.append(f"백틱 누락 {sum(miss_bt.values())}: {list(miss_bt.items())[:8]}")
    if su - du: probs.append(f"URL 누락: {sorted(su - du)[:5]}")
    if sr - dr: probs.append(f"§참조 누락: {sorted(sr - dr)[:10]}")
    if sf - df: probs.append(f"F-ID 누락: {sorted(sf - df)[:10]}")
    miss_n = sn - dn
    if miss_n: probs.append(f"숫자 누락 {sum(miss_n.values())}: {list(miss_n.items())[:10]}")
    if sq - dq: probs.append(f"따옴표 문장 누락: {[q[:30] for q in sorted(sq - dq)][:5]}")
    if dl < 0.85 * sl: probs.append(f"길이 {dl}/{sl} = {dl/sl:.2f} < 0.85")
    return probs


def _fblocks(text):
    """{F-id: (title, fields, authored)} — parse_master.parse_fblock 재사용"""
    from parse_master import parse_fblock, H4_F
    L = text.split("\n"); out = {}
    for i, l in enumerate(L):
        m = H4_F.match(l)
        if m:
            fields, authored, _ = parse_fblock(L, i + 1)
            out[m.group(1)] = (m.group(2).strip(), fields, authored)
    return out


def check_authored_blocks(src_text, dst_text):
    """§14: 원본 필드는 기준선과 바이트 동일, 집필 라벨은 집합 안·비어 있지 않음. §16: 헤딩이 전부 index 용어로 해석, 중복 0."""
    import naming as N
    ok = True
    sb, db = _fblocks(src_text), _fblocks(dst_text)
    n_auth = 0
    for fid, (title, fields, authored) in db.items():
        if fid in sb:
            st, sf, _ = sb[fid]
            if st != title: print(f"  FAIL {fid} 제목 변경: {st!r} → {title!r}"); ok = False
            if dict(sf) != dict(fields): print(f"  FAIL {fid} 원본 필드 변경: {[k for k in set(sf) | set(fields) if sf.get(k) != fields.get(k)]}"); ok = False
        for lab, lines in authored.items():
            if lab not in C.AUTHORED_F: print(f"  FAIL {fid} 미지 집필 라벨 {lab!r}"); ok = False
            if not lines: print(f"  FAIL {fid} 빈 집필 필드 {lab!r}"); ok = False
            for l in lines:
                if l.startswith("#### ") or "[[" in l: print(f"  FAIL {fid} 집필 본문에 금지 구문: {l[:60]!r}"); ok = False
        if authored: n_auth += 1
    m16 = re.search(r"^## 16\. .*$", dst_text, re.M)
    n16 = 0; dup = []
    if m16:
        sec16 = dst_text[m16.end():]
        idx_path = C.WORK / "index.json"
        keys = set(json.load(io.open(idx_path, encoding="utf-8"))["entries"]) if idx_path.exists() else set()
        seen = set(); unknown = []
        for h in re.findall(r"^#### (.+)$", sec16, re.M):
            k = N.term_key(h); n16 += 1
            if k in seen: dup.append(h)
            seen.add(k)
            if keys and k not in keys: unknown.append(h)
        if dup: print(f"  FAIL §16 중복 용어 블록: {dup[:5]}"); ok = False
        if unknown: print(f"  FAIL §16 미지 용어 헤딩: {unknown[:5]}"); ok = False
    print(f"[집필] F 집필 {n_auth}/{len(db)}  §16 블록 {n16}")
    return ok


def main():
    argv = sys.argv[1:]
    args = [a for i, a in enumerate(argv) if not a.startswith("--") and (i == 0 or argv[i - 1] != "--only")]
    edited_path = pathlib.Path(args[0]) if args else C.WORK / "master.edited.md"
    only = None
    if "--only" in sys.argv:
        only = set(sys.argv[sys.argv.index("--only") + 1].split(","))
    base = pathlib.Path(sys.argv[sys.argv.index("--base") + 1]) if "--base" in sys.argv else C.WORK / "master.v1.md"
    if not base.exists(): base = C.WORK / "master.v0.md"
    src_text = io.open(base, encoding="utf-8").read()
    dst_text = io.open(edited_path, encoding="utf-8").read()
    sl, sidx = blocks_of(src_text); dl, didx = blocks_of(dst_text)
    ok = True
    # (1) 계약
    n13 = len(re.findall(r"^### 13\.\d+(?:\.\d+)? ", dst_text, re.M))
    nF = len(re.findall(r"^#### F-\d{3} ", dst_text, re.M))
    nptr = len(re.findall(r"^> 보강 참조 → §13", dst_text, re.M))
    wide = 0
    for i, l in enumerate(dl):
        if l.startswith("|") and i + 1 < len(dl) and re.match(r"^\|\s*-", dl[i + 1]):
            if len(re.split(r"(?<!\\)\|", l.strip())[1:-1]) > 4: wide += 1
    heads = set(re.findall(r"^#{2,4} (\d+(?:\.\d+)*)[. ]", dst_text, re.M))
    bad_refs = sorted({r for r in re.findall(r"§(\d+(?:\.\d+)+)", dst_text) if r not in heads and not (r.count(".") == 2 and ".".join(r.split(".")[:2]) in heads and not r.startswith("13."))})
    print(f"[계약] §13 {n13}/89  F {nF}/304  보강참조 {nptr}/89  >4열표 {wide}  없는 §참조 {bad_refs[:10]}")
    ok &= (n13 == 89 and nF == 304 and nptr == 89 and wide == 0 and not bad_refs)
    ok &= check_authored_blocks(src_text, dst_text)
    # (2)(3) 블록별
    changed = [k for k in didx if k in sidx and dl[didx[k][0]:didx[k][1]] != sl[sidx[k][0]:sidx[k][1]]]
    if only: changed = [k for k in changed if k.split(":")[1] in only]
    print(f"[블록] 변경된 블록 {len(changed)}개 검사")
    for k in changed:
        if k.split(":")[1].split(".")[0] in ("15", "16"):
            # §15는 sec15.py가 index.json(§13 용어 표)에서 통째로 재생성 — 원천 대비 사실 보존 검사 대상이 아니다(diff15.py로 용어 집합 대조)
            print(f"  {k:12} REGEN(skip)"); continue
        probs = compare(k, sl[sidx[k][0]:sidx[k][1]], dl[didx[k][0]:didx[k][1]])
        body = dl[didx[k][0]:didx[k][1]]
        # 형식: 헤딩(+보강 참조 줄) 다음 첫 비공백 줄이 한 줄 요약 (### 절만; 장 도입은 면제)
        if k.startswith("###:") and not k.startswith("###:13.") and not k.startswith("###:14.") and not k.startswith("###:15."):
            j = 1
            while j < len(body) and (body[j].strip() == "" or body[j].startswith("> 보강 참조")): j += 1
            if j >= len(body) or not body[j].startswith("**한 줄 요약:**"):
                probs.append("첫 본문 줄이 **한 줄 요약:** 이 아님")
            # #### own-note(번호형)도 한 줄 요약
            for t, l in enumerate(body):
                if re.match(r"^#### \d+\.\d+\.\d+ ", l):
                    u = t + 1
                    while u < len(body) and body[u].strip() == "": u += 1
                    if u >= len(body) or not body[u].startswith("**한 줄 요약:**"):
                        probs.append(f"소절 {l[5:30]}… 첫 줄이 **한 줄 요약:** 이 아님")
        status = "OK" if not probs else "FAIL"
        if probs: ok = False
        print(f"  {k:12} {status}" + ("" if not probs else "\n    - " + "\n    - ".join(probs)))
    if "--edited-keys" in sys.argv: print(changed)
    print("ALL OK" if ok else "FAIL")


if __name__ == "__main__":
    main()

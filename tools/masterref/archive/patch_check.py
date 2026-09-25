# -*- coding: utf-8 -*-
import io
p = 'check_master.py'; s = io.open(p, encoding='utf-8').read()
old = '''    src_text = io.open(C.WORK / "master.v0.md", encoding="utf-8").read()
    dst_text = io.open(edited_path, encoding="utf-8").read()'''
new = '''    base = pathlib.Path(sys.argv[sys.argv.index("--base") + 1]) if "--base" in sys.argv else C.WORK / "master.v1.md"
    if not base.exists(): base = C.WORK / "master.v0.md"
    src_text = io.open(base, encoding="utf-8").read()
    dst_text = io.open(edited_path, encoding="utf-8").read()'''
assert old in s; s = s.replace(old, new)
old2 = '''    print(f"[계약] §13 {n13}/89  F {nF}/304  보강참조 {nptr}/89  >4열표 {wide}  없는 §참조 {bad_refs[:10]}")
    ok &= (n13 == 89 and nF == 304 and nptr == 89 and wide == 0 and not bad_refs)'''
new2 = '''    print(f"[계약] §13 {n13}/89  F {nF}/304  보강참조 {nptr}/89  >4열표 {wide}  없는 §참조 {bad_refs[:10]}")
    ok &= (n13 == 89 and nF == 304 and nptr == 89 and wide == 0 and not bad_refs)
    ok &= check_authored_blocks(src_text, dst_text)'''
assert old2 in s; s = s.replace(old2, new2)
old3 = '''        if k.split(":")[1].split(".")[0] == "15":'''
new3 = '''        if k.split(":")[1].split(".")[0] in ("15", "16"):'''
assert old3 in s; s = s.replace(old3, new3)
helper = '''

def _fblocks(text):
    """{F-id: (title, fields, authored)} — parse_master.parse_fblock 재사용"""
    from parse_master import parse_fblock, H4_F
    L = text.split("\\n"); out = {}
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
    m16 = re.search(r"^## 16\\. .*$", dst_text, re.M)
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
'''
s = s.replace("\n\ndef main():", helper + "\n\ndef main():")
s = s.replace("import io, re, sys, collections, pathlib", "import io, re, sys, collections, pathlib, json")
io.open(p, 'w', encoding='utf-8', newline='\n').write(s)
print('ok')

# -*- coding: utf-8 -*-
"""edit16/*.md (용어 해설 배치) ⊕ 마스터의 기존 §16 → §16 통째 재생성 → work/master.edited.md.
배치 파일: `#### <용어 원문>` + 집필 필드(`**직관:**`/`**동작:**`/`**증거:**`/`**함정:**`/`**교훈:**`, 다중 행).
키 = naming.term_key(헤딩) — index.json 엔트리에 있어야 한다(없으면 오류). 정본 헤딩은 index의 e["term"]으로 정규화.
순서: §15.1 카테고리(TOP_ORDER) → 가지 → index 삽입 순. 사용: python assemble_terms.py [--toc] [--src PATH]"""
import io, re, sys, glob, json, pathlib, collections
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import config as C
import naming as N
from parse_master import parse_items16, H4
from assemble_master import regen_toc
from build_index import TOP_ORDER

H2_16 = re.compile(r"^## 16\. ")


def blocks_from(lines):
    """§16 본문(장 헤딩 제외)이든 배치 파일이든 → {key: fields}; `### ` 카테고리 헤딩은 무시"""
    out = collections.OrderedDict()
    body = [l for l in lines if not l.startswith("### ") and not H2_16.match(l)]
    for k, blk in parse_items16(body, "", "").items():
        if not blk["fields"]: raise SystemExit(f"empty term block: {blk['heading']}")
        out[k] = blk["fields"]
    return out


def render_sec16(E, blocks):
    n = len(blocks)
    out = ["## 16. 용어 해설 — 직관·동작·예시·관련 코드·증거·함정", "",
           f"**한 줄 요약:** §15의 용어마다 \"왜 이런 개념이 필요한가\"(직관), \"실제로 어떻게 움직이는가\"(동작), \"어떻게 쓰이는가\"(예시), "
           f"\"어느 파일이 구현·검증하는가\"(관련 코드), \"이 저장소의 어디가 그 증거인가\"(증거), \"어디서 넘어지는가\"(함정)를 집필한 해설입니다 — "
           f"현재 {n:,}/{len(E):,}개. 보관함 `Maro Note/`의 각 용어 노트 `## 해설`이 이 블록에서 생성됩니다.", ""]
    by_top = collections.OrderedDict((t, collections.OrderedDict()) for t in TOP_ORDER)
    for k, e in E.items():
        if k in blocks: by_top[e["top"]].setdefault(e["sub"], []).append(k)
    for i, top in enumerate(TOP_ORDER, 1):
        subs = by_top[top]
        total = sum(len(v) for v in subs.values())
        if not total: continue          # 집필된 용어가 없는 카테고리는 아직 싣지 않는다
        out.append(f"### 16.{i} {top} ({total}개)"); out.append("")
        for sub, keys in subs.items():
            out.append(f"<!-- 가지: {sub} -->"); out.append("")
            for k in keys:
                out.append(f"#### {E[k]['term']}")
                fields = blocks[k]
                for lab in C.AUTHORED_T:
                    if lab in fields and fields[lab]:
                        out.append(f"**{lab}:**"); out += fields[lab]
                out.append("")
    return out


def main():
    src = pathlib.Path(sys.argv[sys.argv.index("--src") + 1]) if "--src" in sys.argv else C.MASTER_SRC
    text = io.open(src, encoding="utf-8").read()
    E = json.load(io.open(C.WORK / "index.json", encoding="utf-8"))["entries"]
    L = text.split("\n")
    # 기존 §16 범위
    s16 = next((i for i, l in enumerate(L) if H2_16.match(l)), None)
    existing = collections.OrderedDict()
    if s16 is not None:
        e16 = next((i for i in range(s16 + 1, len(L)) if re.match(r"^## \d+\. ", L[i])), len(L))
        existing = blocks_from(L[s16 + 1:e16])
    else:
        e16 = None
    files = 0; added = 0
    for f in sorted(glob.glob(str(C.EDIT16 / "*.md"))):
        files += 1
        for k, fields in blocks_from(io.open(f, encoding="utf-8").read().split("\n")).items():
            if k not in E: raise SystemExit(f"{f}: unknown term key {k!r} — index.json 에 없는 용어")
            for lab in fields:
                if lab not in C.AUTHORED_T: raise SystemExit(f"{f}: {k!r} unknown label {lab!r}")
                for l in fields[lab]:
                    if l.startswith("#### ") or "[[" in l: raise SystemExit(f"{f}: {k!r} forbidden syntax in {lab}: {l[:60]!r}")
            if k not in existing: added += 1
            existing[k] = fields
    sec = render_sec16(E, existing)
    if s16 is None and not existing:
        out = text.rstrip("\n") + "\n"
        if "--toc" in sys.argv: out = regen_toc(out)
        io.open(C.WORK / "master.edited.md", "w", encoding="utf-8", newline="\n").write(out)
        print("§16: no term blocks yet — master copied unchanged"); return
    if s16 is None:
        # §15 끝(파일 끝) 뒤에 붙인다
        while L and L[-1].strip() == "": L.pop()
        L = L + ["", "---", ""] + sec
    else:
        L[s16:e16] = sec + [""]
    out = "\n".join(L).rstrip("\n") + "\n"
    if "--toc" in sys.argv: out = regen_toc(out)
    io.open(C.WORK / "master.edited.md", "w", encoding="utf-8", newline="\n").write(out)
    print(f"§16: {len(existing)} term blocks ({added} new from {files} batch files) -> work/master.edited.md {out.count(chr(10)) + 1} lines")


if __name__ == "__main__":
    main()

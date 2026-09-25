# -*- coding: utf-8 -*-
"""edit/*.md 의 교체 블록을 master.v0.md 에 접합 → work/master.edited.md.
블록 단위: `## N. ` 장 도입(다음 ###/## 전까지) 또는 `### N.M ` 절(다음 ###/## 전까지, #### 포함).
chunk 파일은 여러 블록을 순서 무관하게 담을 수 있다. 같은 헤딩 번호가 뒤 chunk에 다시 나오면 뒤가 이긴다.
사용: python assemble_master.py [--toc]"""
import io, re, sys, glob, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import config as C

HEAD = re.compile(r"^(##|###) (\d+(?:\.\d+)*)[. ]")


def blocks_of(text):
    """{key: (start, end)} key = '##:6' 장 도입 / '###:6.6' 절. 장 도입은 다음 ### 또는 ## 까지."""
    lines = text.split("\n"); idx = {}; heads = []
    for i, l in enumerate(lines):
        m = HEAD.match(l)
        if m: heads.append((i, m.group(1), m.group(2)))
    for n, (i, lvl, num) in enumerate(heads):
        end = heads[n + 1][0] if n + 1 < len(heads) else len(lines)
        key = f"{lvl}:{num}"
        if key in idx:  # 같은 절 번호가 둘(예: 6.6 원문과 13.6.6은 번호가 다르므로 없음)
            raise SystemExit(f"duplicate heading {key}")
        idx[key] = (i, end)
    return lines, idx


def main():
    text = io.open(C.WORK / "master.v0.md", encoding="utf-8").read()
    lines, idx = blocks_of(text)
    replaced = []
    for f in sorted(glob.glob(str(C.EDIT / "*.md"))):
        etext = io.open(f, encoding="utf-8").read()
        elines, eidx = blocks_of(etext)
        for key, (s, e) in eidx.items():
            if key not in idx:
                raise SystemExit(f"{f}: heading {key} not in master")
            replaced.append((key, f, elines[s:e]))
    # 뒤에서부터 교체(인덱스 보존)
    repl = {}
    for key, f, body in replaced: repl[key] = (f, body)
    for key in sorted(repl, key=lambda k: idx[k][0], reverse=True):
        s, e = idx[key]; f, body = repl[key]
        # 블록 끝 공백 줄 정규화: 정확히 한 줄 비움
        while body and body[-1].strip() == "": body.pop()
        body = body + [""]
        lines[s:e] = body
    out = "\n".join(lines)
    if "--toc" in sys.argv:
        out = regen_toc(out)
    io.open(C.WORK / "master.edited.md", "w", encoding="utf-8", newline="\n").write(out)
    print(f"assembled {len(repl)} blocks from {len(set(f for f,_ in repl.values()))} chunk files ->", C.WORK / "master.edited.md", out.count("\n") + 1, "lines")


def regen_toc(txt):
    def slug(h):
        s = h.strip().lower(); s = re.sub(r"[`*_]", "", s); s = re.sub(r"[^\w\s\-가-힣]", "", s)
        return re.sub(r"\s+", "-", s.strip())
    m = re.search(r"^## 목차\n.*?(?=^## )", txt, re.M | re.S)
    toc = ["## 목차", ""]
    for hm in re.finditer(r"^(##|###) (.+)$", txt, re.M):
        level, title = hm.group(1), hm.group(2).strip()
        if title.startswith("목차"): continue
        toc.append(("- " if level == "##" else "  - ") + f"[{title}](#{slug(title)})")
    toc.append("")
    return txt[:m.start()] + "\n".join(toc) + "\n" + txt[m.end():]


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""edit14/*.md (집필 배치) → 리포 마스터의 §14 F-블록에 집필 필드를 접합 → work/master.edited.md.
배치 파일: `#### F-### 제목` + 집필 필드(`**발단:**` 등, 다중 행)만. 원본 6필드는 마스터 것을 그대로 쓴다(배치에 있으면 같아야 함).
같은 F-id가 여러 배치에 있으면 뒤(파일명 정렬)가 이긴다. 멱등. 사용: python assemble_failures.py [--toc] [--src PATH]"""
import io, re, sys, glob, pathlib, collections
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import config as C
from parse_master import parse_fblock, H4_F, FIELD
from assemble_master import regen_toc


def batch_blocks(path):
    """배치 파일 → {fid: (title, fields, authored)}"""
    L = io.open(path, encoding="utf-8").read().split("\n")
    out = collections.OrderedDict()
    for i, l in enumerate(L):
        m = H4_F.match(l)
        if m:
            fields, authored, _ = parse_fblock(L, i + 1)
            out[m.group(1)] = (m.group(2).strip(), fields, authored)
    return out


def render_block(heading, fields, authored):
    out = [heading]
    for lab, val in fields.items(): out.append(f"**{lab}:** {val}")
    if authored:
        out.append("")
        for lab in C.AUTHORED_F:
            if lab in authored and authored[lab]:
                out.append(f"**{lab}:**"); out += authored[lab]
    out.append("")
    return out


def main():
    src = pathlib.Path(sys.argv[sys.argv.index("--src") + 1]) if "--src" in sys.argv else C.MASTER_SRC
    text = io.open(src, encoding="utf-8").read()
    L = text.split("\n")
    # 마스터의 F-블록 위치
    spans = collections.OrderedDict()
    for i, l in enumerate(L):
        m = H4_F.match(l)
        if m:
            fields, authored, j = parse_fblock(L, i + 1)
            spans[m.group(1)] = (i, j, l, fields, authored)
    overlay = collections.OrderedDict(); files = 0
    for f in sorted(glob.glob(str(C.EDIT14 / "*.md"))):
        files += 1
        for fid, (title, fields, authored) in batch_blocks(f).items():
            if fid not in spans: raise SystemExit(f"{f}: {fid} not in master")
            mtitle = spans[fid][2][len(f"#### {fid} "):].strip()
            if title != mtitle: raise SystemExit(f"{f}: {fid} title mismatch: batch {title!r} vs master {mtitle!r}")
            mfields = spans[fid][3]
            for lab, val in fields.items():
                if mfields.get(lab) != val: raise SystemExit(f"{f}: {fid} original field {lab!r} differs from master — batch must not change it")
            if not authored: raise SystemExit(f"{f}: {fid} has no authored fields")
            overlay[fid] = (f, authored)
    # 뒤에서부터 교체
    for fid in sorted(overlay, key=lambda x: spans[x][0], reverse=True):
        i, j, heading, fields, _ = spans[fid]
        # j 는 블록 끝(다음 #### / 라벨 밖 텍스트 / --- 의 인덱스). 그 앞의 빈 줄까지 블록에 포함시켜 정확히 한 줄 비우기
        L[i:j] = render_block(heading, fields, overlay[fid][1])
    out = "\n".join(L)
    if "--toc" in sys.argv: out = regen_toc(out)
    io.open(C.WORK / "master.edited.md", "w", encoding="utf-8", newline="\n").write(out)
    n_auth = sum(1 for fid, (i, j, h, f, a) in spans.items() if a or fid in overlay)
    print(f"assembled {len(overlay)} authored F-blocks from {files} batch files; authored total {n_auth}/{len(spans)} -> work/master.edited.md {out.count(chr(10)) + 1} lines")


if __name__ == "__main__":
    main()

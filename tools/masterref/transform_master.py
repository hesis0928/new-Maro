# -*- coding: utf-8 -*-
"""S2~S6 기계 변환: 원천 → work/master.v0.md (멱등).
S2 §13 라벨 통일 / S3 파일형 #### 번호 부여 / S4 §14 표→블록 / S5 §15 재생성(4열) / S6 >4열 표→불릿.
S1(unwrap)은 방출 단계, S7(목차)은 assemble 단계."""
import io, re, sys, subprocess, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import config as C

FILE_LIKE_HEAD = re.compile(r"^(?:src/)?(?:[\w\-]+/)*[\w\-]+(?:\.[\w\-]+)*?(?:\.\{h,cpp\}|\.(?:h|cpp|py|txt|json|ps1|mod|bak))(?!\w)")


def split_row(line):
    return [c.strip() for c in re.split(r"(?<!\\)\|", line.strip())[1:-1]]


def s2_labels(lines):
    out = []
    for l in lines:
        l = l.replace("**문맥 풀이.**", "**문맥 풀이:**").replace("**외부 참조·보완.**", "**외부 참조:**")
        l = re.sub(r"\*\*하위지식 — (.+?)\.\*\*", r"**하위지식 — \1:**", l)
        out.append(l)
    return out


def s3_number_subsections(lines):
    out = []; sec = None; k = 0; numbered_seen = False; assigned = 0
    for l in lines:
        m = re.match(r"^### (\d+\.\d+) ", l)
        if m:
            sec = m.group(1); k = 0; numbered_seen = False
        if l.startswith("#### ") and sec and not sec.startswith(("13.", "14.", "15.")):
            h = l[5:]
            mn = re.match(r"^(\d+)\.(\d+)\.(\d+) ", h)
            if mn:
                k = int(mn.group(3)); numbered_seen = True
            elif FILE_LIKE_HEAD.match(h.replace("`", "")):
                assert not numbered_seen, (sec, h)
                k += 1; assigned += 1
                l = f"#### {sec}.{k} {h}"
        out.append(l)
    print("S3 numbered", assigned)
    return out


def s4_failures_to_blocks(lines):
    out = []; i = 0; blocks = 0; in14 = False
    while i < len(lines):
        l = lines[i]
        if l.startswith("## "): in14 = l.startswith("## 14. ")
        if in14 and l.startswith("| ID |") and i + 1 < len(lines) and re.match(r"^\|\s*-", lines[i + 1]):
            header = split_row(l)
            j = i + 2
            while j < len(lines) and lines[j].startswith("|"):
                cells = split_row(lines[j])
                assert len(cells) == len(header), (lines[j][:80], len(cells), len(header))
                cells = [c.replace("\\|", "|") for c in cells]
                fid, title = cells[0], cells[1]
                out.append(f"#### {fid} {title}")
                for h, c in zip(header[2:], cells[2:]):
                    out.append(f"**{h}:** {c}")
                out.append("")
                blocks += 1; j += 1
            i = j; continue
        out.append(l); i += 1
    print("S4 failure blocks", blocks)
    return out


def s6_wide_tables(lines):
    out = []; i = 0; conv = 0; sec = "0"
    while i < len(lines):
        l = lines[i]
        m = re.match(r"^##+ (\d+(?:\.\d+)*)", l)
        if m: sec = m.group(1)
        if l.startswith("|") and i + 1 < len(lines) and re.match(r"^\|\s*-", lines[i + 1]) and not sec.startswith(("13.", "14.", "15.")):
            header = split_row(l)
            if len(header) > 4:
                j = i + 2
                while j < len(lines) and lines[j].startswith("|"):
                    cells = split_row(lines[j])
                    first = cells[0]
                    rest = "; ".join(f"{h}: {c}" for h, c in zip(header[1:], cells[1:]) if c)
                    out.append(f"- **{first}** — {rest}")
                    j += 1
                conv += 1; i = j; continue
        out.append(l); i += 1
    print("S6 wide tables converted", conv)
    return out


def s8_bulletize_context(lines):
    """§13 항목의 `**문맥 풀이:** 문단` → 라벨 줄 + 문장별 불릿."""
    out = []; i = 0; n = 0
    while i < len(lines):
        l = lines[i]
        if l.startswith("**문맥 풀이:** ") and not l[len("**문맥 풀이:** "):].startswith("- "):
            para = [l[len("**문맥 풀이:** "):].strip()]
            j = i + 1
            while j < len(lines) and lines[j].strip() and not lines[j].startswith(("|", "- ", "**", "#")):
                para.append(lines[j].strip()); j += 1
            text = " ".join(para)
            sents = re.split(r"(?<=[다요음임됨함]\.)\s+(?=[\"“(\[`A-Za-z가-힣0-9*])", text)
            out.append("**문맥 풀이:**")
            out.extend("- " + x.strip() for x in sents if x.strip())
            n += 1; i = j; continue
        out.append(l); i += 1
    print("S8 bulletized context", n)
    return out


def s5_regen_15(text):
    sp = C.SCRATCH
    r = subprocess.run([sys.executable, str(sp / "build_taxonomy.py"), str(sp / "terms-collected.md"), str(sp / "chunk-15.md")],
                       capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stderr
    new15 = io.open(sp / "chunk-15.md", encoding="utf-8").read()
    cut = text.index("\n---\n\n## 15. ")
    print("S5 §15 regenerated")
    return text[:cut] + new15


def verify(text):
    L = text.split("\n")
    n13 = len(re.findall(r"^### 13\.\d+(?:\.\d+)? ", text, re.M))
    nF = len(re.findall(r"^#### F-\d{3} ", text, re.M))
    nptr = len(re.findall(r"^> 보강 참조 → §13", text, re.M))
    wide = 0; i = 0
    while i < len(L):
        if L[i].startswith("|") and i + 1 < len(L) and re.match(r"^\|\s*-", L[i + 1]):
            if len(split_row(L[i])) > 4: wide += 1
        i += 1
    tables_rows_F = len(re.findall(r"^\| F-\d{3} \|", text, re.M))
    print(f"verify: §13 items {n13} / F blocks {nF} / F rows left {tables_rows_F} / 보강 참조 {nptr} / wide tables {wide}")
    assert n13 == 89 and nF == 304 and tables_rows_F == 0 and nptr == 89 and wide == 0


def main():
    text = io.open(C.MASTER_SRC, encoding="utf-8").read()
    text = s5_regen_15(text)
    lines = text.split("\n")
    lines = s2_labels(lines)
    lines = s3_number_subsections(lines)
    lines = s4_failures_to_blocks(lines)
    lines = s6_wide_tables(lines)
    lines = s8_bulletize_context(lines)
    lines = s9_escape_pipes(lines)
    text = "\n".join(lines)
    verify(text)
    C.WORK.mkdir(parents=True, exist_ok=True)
    io.open(C.WORK / "master.v0.md", "w", encoding="utf-8", newline="\n").write(text)
    print("wrote", C.WORK / "master.v0.md", text.count("\n") + 1, "lines")


if __name__ == "__main__":
    main()

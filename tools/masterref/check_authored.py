# -*- coding: utf-8 -*-
"""집필 배치 검사 — 구조 + 사실 대조. 사용: python check_authored.py edit14/b01.md [edit16/x.md ...] [--strict]
구조: 라벨 집합, 키 존재(F-id / term_key), 중복, `[[` 금지, 열 0 잡 라벨 금지, 빈 필드 금지.
사실(ERROR): `§ref` → 마스터 헤딩 / `F-###` → 모델 / 경로형 백틱 → 리포 파일(줄 번호 ≤ 줄수) / 식별자형 백틱 → 마스터 스팬 ∪ 리포 심볼.
사실(WARN): 그 밖의 백틱 스팬 → 마스터 부분 문자열 / 2자리 이상 숫자 → 마스터 ∪ 리포 파일. allow.txt(`F-003: tbb12.dll`)로 허용.
exit 1 = 오류 있음(--strict 면 경고도 오류)."""
import io, re, sys, json, pathlib, collections
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import config as C
import naming as N
from parse_master import parse_fblock, parse_items16, H4_F, H4, FIELD

CODE = re.compile(r"`([^`\n]+)`")
PATHLIKE = re.compile(r"^(?:[\w.\-]+[/\\])*[\w.\-]+\.(?:h|hpp|cpp|c|py|ps1|txt|json|md|cmake|mel|xml|yml|yaml|bat|mod|ini)(?::(\d+)(?:-(\d+))?)?$")
IDENTLIKE = re.compile(r"^[A-Za-z_][\w:.<>]*(?:\(.*\))?$")
REPO = C.MASTER_SRC.parents[1]


_GG = {}
def git_grep(needle, word=False):
    """리포 작업 트리에서 리터럴 검색(캐시). 마스터에 없는 스팬의 마지막 근거 확인."""
    import subprocess
    key = (needle, word)
    if key not in _GG:
        args = ["git", "grep", "-qF"] + (["-w"] if word else []) + ["--", needle]
        try:
            _GG[key] = subprocess.run(args + [], cwd=str(REPO), capture_output=True).returncode == 0
        except OSError:
            _GG[key] = False
    return _GG[key]


def load_allow(edit_dir):
    p = edit_dir / "allow.txt"; allow = collections.defaultdict(set)
    if p.exists():
        for l in io.open(p, encoding="utf-8"):
            if ":" in l and not l.startswith("#"):
                k, v = l.split(":", 1); allow[k.strip()].add(v.strip())
    return allow


def main():
    strict = "--strict" in sys.argv
    files = [a for a in sys.argv[1:] if not a.startswith("--")]
    master = io.open(C.MASTER_SRC, encoding="utf-8").read()
    master_nows = re.sub(r"\s+", "", master)
    heads = set(re.findall(r"^#{2,4} (\d+(?:\.\d+)*)[. ]", master, re.M))
    fids = set(re.findall(r"^#### (F-\d{3}) ", master, re.M))
    mspans = {re.sub(r"\s+", "", m.group(1)) for m in CODE.finditer(master)}
    mheads = {N.strip_trailing_group(s) for s in mspans}
    mnums = set(re.findall(r"(?<![\w.])\d[\d,]{1,}(?:\.\d+)?(?![\w])", master))
    E = json.load(io.open(C.WORK / "index.json", encoding="utf-8"))["entries"]
    sym_path = C.WORK / "symbols.json"
    sym = json.load(io.open(sym_path, encoding="utf-8")) if sym_path.exists() else {"files": {}, "idents": [], "joined": []}
    sfiles = sym["files"]; sidents = set(sym["idents"]) | set(sym["joined"])
    total_err = total_warn = 0
    reports = []
    for f in files:
        f = pathlib.Path(f); lines = io.open(f, encoding="utf-8").read().split("\n")
        is14 = f.parent.name == "edit14" or any(H4_F.match(l) for l in lines)
        allow = load_allow(f.parent)
        blocks = collections.OrderedDict()
        if is14:
            for i, l in enumerate(lines):
                m = H4_F.match(l)
                if m:
                    fields, authored, _ = parse_fblock(lines, i + 1)
                    blocks[m.group(1)] = ("F", l, fields, authored)
        else:
            for k, blk in parse_items16([l for l in lines if not l.startswith("### ")], "", "").items():
                blocks[k] = ("T", blk["heading"], {}, blk["fields"])
        rep = [f"# check_authored — {f.name}", ""]
        n_err = n_warn = 0; seen = set()
        for key, (kind, heading, fields, authored) in blocks.items():
            errs = []; warns = []
            if key in seen: errs.append("중복 블록")
            seen.add(key)
            if kind == "F" and key not in fids: errs.append("마스터에 없는 F-id")
            if kind == "T" and key not in E: errs.append(f"index에 없는 용어 키 {key!r}")
            labels = C.AUTHORED_F if kind == "F" else C.AUTHORED_T
            if not authored: errs.append("집필 필드 없음")
            for lab, body in authored.items():
                if lab not in labels: errs.append(f"미지 라벨 {lab!r}")
                if not body: errs.append(f"빈 필드 {lab!r}")
                for l in body:
                    if "[[" in l: errs.append(f"위키링크 금지: {l[:50]!r}")
                    if l.startswith("#### "): errs.append(f"본문 안 #### 금지: {l[:50]!r}")
                    mm = FIELD.match(l)
                    if mm and mm.group(1).strip() not in labels: errs.append(f"열 0 잡 라벨 {mm.group(1)!r}")
            text = "\n".join(l for body in authored.values() for l in body)
            # `예시` 필드의 씬 오브젝트 이름(소문자 시작, 단순 식별자)은 예시용 가명일 수 있다 -> ERROR 대신 WARN
            ex_text = re.sub(r"```.*?```", " ", "\n".join(authored.get("예시", [])), flags=re.S)
            ex_names = {m.group(1).strip() for m in CODE.finditer(ex_text)}
            fences = re.findall(r"```.*?```", text, re.S); text_nf = re.sub(r"```.*?```", " ", text, flags=re.S)
            # §참조
            for r in set(re.findall(r"§(\d+(?:\.\d+)+)", text_nf)):
                okref = r in heads or (r.count(".") == 2 and ".".join(r.split(".")[:2]) in heads and not r.startswith("13."))
                if not okref: errs.append(f"없는 §참조 §{r}")
            for r in set(re.findall(r"§(\d+)(?![\d.])", text_nf)):
                if r not in heads: errs.append(f"없는 §참조 §{r}")
            for fid in set(re.findall(r"\bF-\d{3}\b", text_nf)):
                if fid not in fids: errs.append(f"없는 F-id {fid}")
            # 백틱 스팬. `:N-M` 꼴은 같은 줄의 앞선 경로 스팬에 대한 줄 번호로 본다
            line_refs = []
            for ln in text_nf.split("\n"):
                last_path = None
                for m in CODE.finditer(ln):
                    sp = m.group(1).strip()
                    if PATHLIKE.match(sp): last_path = re.sub(r":\d+(?:-\d+)?$", "", sp).replace("\\", "/")
                    elif re.fullmatch(r":\d+(?:-\d+)?", sp): line_refs.append((last_path, sp))
            for path, sp in line_refs:
                if path is None:
                    if sp not in mspans: warns.append(f"줄 참조 `{sp}` 앞에 경로 스팬이 없고 마스터에도 없음")
                    continue                       # 마스터 §의 `:N-M` 표기를 그대로 인용한 것
                cand = [p for p in sfiles if p == path or p.endswith("/" + path)]
                if not cand: continue
                hi = int(sp[1:].split("-")[-1])
                if hi > max(sfiles[p] for p in cand): errs.append(f"`{path}` `{sp}` 줄 번호가 파일 줄수({max(sfiles[p] for p in cand)})를 넘음")
            for sp in {m.group(1).strip() for m in CODE.finditer(text_nf)}:
                if sp in allow.get(key, set()): continue
                if re.fullmatch(r":\d+(?:-\d+)?", sp): continue
                spn = re.sub(r"\s+", "", sp)
                pm = PATHLIKE.match(sp)
                if pm:
                    path = re.sub(r":\d+(?:-\d+)?$", "", sp).replace("\\", "/")
                    cand = [p for p in sfiles if p == path or p.endswith("/" + path)]
                    if not cand:
                        if spn in mspans or spn in master_nows: pass          # 외부 파일(devkit/SDK/Maya)이라 마스터가 언급한 것으로 충분
                        elif git_grep(sp): pass
                        else: errs.append(f"경로 `{sp}` 리포·마스터 모두에 없음")
                    elif pm.group(1):
                        ln = int(pm.group(1)); ln2 = int(pm.group(2) or ln)
                        if ln2 > max(sfiles[p] for p in cand): errs.append(f"`{sp}` 줄 번호가 파일 줄수({max(sfiles[p] for p in cand)})를 넘음")
                    continue
                if IDENTLIKE.match(sp):
                    head = N.strip_trailing_group(sp)
                    parts = re.split(r"::|\.", head)
                    if spn in mspans or head in mheads or head in sidents or parts[-1] in sidents or all(p in sidents for p in parts if p):
                        continue
                    if git_grep(head): continue
                    if sp in ex_names and re.fullmatch(r"[a-z][A-Za-z0-9_]*", head):
                        warns.append(f"예시 이름 `{sp}` 마스터·리포에 없음(가명이면 무방)")
                    else:
                        errs.append(f"식별자 `{sp}` 마스터·리포 어디에도 없음")
                    continue
                if spn not in mspans and spn not in master_nows and not git_grep(sp):
                    warns.append(f"스팬 `{sp}` 마스터·리포에 없음")
            for num in set(re.findall(r"(?<![\w.§F:\-])\d(?:[\d,]*\d)?(?:\.\d+)?(?![\w])", text_nf)):
                if len(num) < 2: continue
                if num not in mnums and num not in master and not git_grep(num, word=True): warns.append(f"숫자 {num} 마스터·리포에 없음")
            n_err += len(errs); n_warn += len(warns)
            if errs or warns:
                rep.append(f"## {key} {heading[:60]}")
                rep += [f"- ERROR {e}" for e in errs] + [f"- WARN {w}" for w in warns] + [""]
        total_err += n_err; total_warn += n_warn
        rep.insert(2, f"blocks {len(blocks)} · errors {n_err} · warnings {n_warn}\n")
        C.REPORTS.mkdir(exist_ok=True)
        io.open(C.REPORTS / f"authored-{f.stem}.md", "w", encoding="utf-8").write("\n".join(rep))
        print(f"{f.name}: blocks {len(blocks)} errors {n_err} warnings {n_warn} -> reports/authored-{f.stem}.md")
        for l in rep[3:]:
            if l.startswith(("## ", "- ERROR")) or (strict and l.startswith("- WARN")): print("  " + l)
    bad = total_err > 0 or (strict and total_warn > 0)
    print("FAIL" if bad else "OK")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()

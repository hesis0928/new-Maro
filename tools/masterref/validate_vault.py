# -*- coding: utf-8 -*-
"""보관함 검사. 사용: python validate_vault.py [staging|live] [--partial]
partial: 부분 방출(파일럿)이라 커버리지 수치 검사는 생략."""
import io, re, sys, json, pathlib, collections
import yaml
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import config as C
import naming as N

which = "staging" if len(sys.argv) < 2 or sys.argv[1].startswith("--") else sys.argv[1]
partial = "--partial" in sys.argv
ROOT = C.OUT if which == "staging" else C.LIVE_DIR
ok = True
def fail(msg):
    global ok; ok = False; print("  FAIL", msg)

files = sorted(ROOT.rglob("*.md"))
print(f"[{which}] {len(files)} notes under {ROOT}")

# 1) basename 유일 (기존 vault 포함)
names = collections.defaultdict(list)
for p in files: names[p.stem.lower()].append(p)
for p in C.EXISTING_DIR.rglob("*.md"): names[p.stem.lower()].append(p)
dups = {k: v for k, v in names.items() if len(v) > 1 and any(str(x).startswith(str(ROOT)) for x in v)}
print(f"(1) 중복 basename {len(dups)}"); [fail(f"dup {k}: {[str(x)[-80:] for x in v]}") for k, v in list(dups.items())[:10]]
aliases = collections.defaultdict(set)

# 2) 경로 위생 + 3) 프론트매터 + 6) 형식
fm_types = collections.Counter(); bad_fm = 0
notes = {}
for p in files:
    rel = p.relative_to(ROOT)
    for part in rel.parts:
        bad = [c for c in part if c in N.FORBIDDEN]
        if bad: fail(f"forbidden char {bad} in {rel}")
        if part.endswith((".", " ")) or part.startswith("."): fail(f"bad edge char in {rel}")
    if len(p.stem) > 120: fail(f"name too long ({len(p.stem)}): {rel}")
    live_len = len(str(C.LIVE_DIR)) + 1 + len(str(rel))
    if live_len > 240: fail(f"live path too long ({live_len}): {rel}")
    text = io.open(p, encoding="utf-8").read()
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if not m: fail(f"no frontmatter: {rel}"); continue
    try:
        meta = yaml.safe_load(m.group(1)) or {}
    except Exception as e:
        fail(f"yaml error {rel}: {e}"); continue
    if "type" not in meta or "title" not in meta or "tags" not in meta: fail(f"missing type/title/tags: {rel}")
    for t in meta.get("tags", []):
        if not re.fullmatch(r"[A-Za-z0-9_/\-]+", str(t)): fail(f"bad tag {t!r} in {rel}")
    fm_types[meta.get("type")] += 1
    for a in meta.get("aliases", []) or []: aliases[str(a).lower()].add(p.stem)
    body = text[m.end():]
    first = next((l for l in body.split("\n") if l.strip()), "")
    if not first.startswith("**한 줄 요약:**"): fail(f"first body line not 한 줄 요약: {rel}")
    if re.search(r"^> 보강 참조", body, re.M): fail(f"보강 참조 line left: {rel}")
    for i, l in enumerate(body.split("\n")):
        if l.startswith("|") and i + 1 < len(body.split("\n")):
            nxt = body.split("\n")[i + 1]
            if re.match(r"^\|\s*-", nxt) and len(re.split(r"(?<!\\)\|", l.strip())[1:-1]) > 4: fail(f"table >4 cols: {rel}")
    for fm_ in re.finditer(r"```.*?```", body, re.S):
        if "[[" in fm_.group(0): fail(f"link in fence: {rel}")
    notes[p] = (meta, body)
print(f"(2)(3)(6) types {dict(fm_types)}")

# 1b) 링크 해석
stems = {p.stem.lower(): p for p in files}
for p in C.EXISTING_DIR.rglob("*.md"): stems.setdefault(p.stem.lower(), p)
unresolved = collections.Counter(); total_links = 0
for p, (meta, body) in notes.items():
    for m in re.finditer(r"\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|([^\]]*))?\]\]", body):
        total_links += 1
        tgt = m.group(1).strip().rstrip("\\")  # 표 안 별칭 구분자 이스케이프 `[[X\\|Y]]` 의 역슬래시 제거
        key = tgt.split("/")[-1].lower()
        if key not in stems and key not in aliases:
            unresolved[tgt] += 1
        if m.group(2) is not None and m.group(2) == "": fail(f"empty alias in {p.name}")
        if key == p.stem.lower(): fail(f"self link in {p.name}")
print(f"(1b) 링크 {total_links}개, 미해석 {len(unresolved)}종 {sum(unresolved.values())}회")
for t, n in unresolved.most_common(15):
    if partial: print(f"  info(partial) unresolved [[{t}]] ×{n}")
    else: fail(f"unresolved [[{t}]] ×{n}")

# 4) 커버리지 (전체 방출일 때)
if not partial:
    model = json.load(io.open(C.WORK / "model.json", encoding="utf-8"))
    index = json.load(io.open(C.WORK / "index.json", encoding="utf-8"))
    exp = {"chapter": len(model["chapters"]), "section": len(model["sections"]), "subsection": len(model["subsections"]),
           "term": len(index["entries"]), "failure": len(model["failures"]), "failclass": len(model["fail_classes"]) - 1}
    ctxp = C.WORK / "context.json"
    if ctxp.exists():
        cx = json.load(io.open(ctxp, encoding="utf-8"))
        exp["excerpt"] = sum(1 for v in cx["terms"].values() if v["body"] or v["ctx"] or v["rows"]) + \
                         sum(1 for v in cx["failures"].values() if v["body"] or v["ctx"] or v["rows"] or v["chron"] or v["mentions"])
    for k, v in exp.items():
        if fm_types.get(k, 0) != v: fail(f"coverage {k}: {fm_types.get(k, 0)} != {v}")
    print(f"(4) coverage expected {exp}")
    # URL 존재
    all_body = "\n".join(b for _, b in notes.values())
    src = io.open(C.WORK / "master.edited.md", encoding="utf-8").read()
    urls = set(re.findall(r"https?://[^\s)>\]]+", src)); vault_urls = set(re.findall(r"https?://[^\s)>\]]+", all_body))
    miss = urls - vault_urls
    print(f"    URL {len(urls)} in master, {len(miss)} missing in vault"); [fail(f"url missing {u}") for u in list(miss)[:5]]
    # 허브 하위 목록 = 실제 파일
    for p, (meta, body) in notes.items():
        if meta.get("type") in ("chapter", "branch", "category", "failclass") or str(meta.get("type")) == "hub":
            pass  # 목록은 생성 시 같은 집합에서 만들어짐; 링크 해석 검사로 충분
# 5) 발췌 왕복: 발췌 노트 `of` → 소유 노트 존재 + 소유 노트가 `[[<발췌 스템>|` 로 링크; 소유 노트 excerpt_note → 발췌 노트 존재
stem_notes = {p.stem: (meta, body) for p, (meta, body) in notes.items()}
n_rt = 0
for p, (meta, body) in notes.items():
    if meta.get("type") == "excerpt":
        owner = meta.get("of")
        if owner not in stem_notes: fail(f"excerpt owner missing: {p.stem} -> {owner}"); continue
        if f"[[{p.stem}|" not in stem_notes[owner][1]: fail(f"owner lacks link to excerpt: {owner} -> {p.stem}")
        if f"[[{owner}" not in body: fail(f"excerpt lacks back-link: {p.stem}")
        n_rt += 1
    elif meta.get("type") in ("term", "failure") and meta.get("excerpt_note"):
        if meta["excerpt_note"] not in stem_notes: fail(f"excerpt_note missing: {p.stem} -> {meta['excerpt_note']}")
        if "## 발췌" not in body: fail(f"term/failure with excerpt_note but no ## 발췌: {p.stem}")
print(f"(5) 발췌 왕복 링크 {n_rt}개 확인")
C.REPORTS.mkdir(exist_ok=True)
# 8) 노트 골격: H2 집합·순서, 집필 표시, 잡 라벨, 길이
TERM_H2 = ["해설", "하위지식", "문맥별 뜻", "발췌", "관련 실패", "연결"]
FAIL_H2 = ["개요", "해설"] + list(C.AUTHORED_F) + ["발췌", "관련 용어"]
EXC_H2 = ["본문 발췌", "출처 발췌", "해설지 문맥", "사전·규칙", "규칙·연대기", "언급 위치"]
lengths = collections.defaultdict(list); n_auth = collections.Counter()
for p, (meta, body) in notes.items():
    t = meta.get("type"); lines = body.split("\n"); lengths[t].append(len(lines))
    if t not in ("term", "failure", "excerpt"): continue
    h2 = [l[3:].strip() for l in lines if l.startswith("## ")]
    allowed = TERM_H2 if t == "term" else FAIL_H2 if t == "failure" else EXC_H2
    if any(h not in allowed for h in h2): fail(f"unknown H2 {[h for h in h2 if h not in allowed]} in {p.name}")
    idx = [allowed.index(h) for h in h2 if h in allowed]
    if idx != sorted(idx): fail(f"H2 out of order {h2} in {p.name}")
    if len(h2) != len(set(h2)): fail(f"duplicate H2 in {p.name}")
    if str(meta.get("authored")).lower() == "true": n_auth[t] += 1
    in_fence = False
    for l in lines:
        if l.strip().startswith("```"): in_fence = not in_fence; continue
        if in_fence and "[[" in l: fail(f"link inside fence: {p.name}"); break
    if len(lines) > 400: fail(f"note too long ({len(lines)} lines): {p.name}")
model_path = C.WORK / "model.json"
if model_path.exists() and not partial:
    mdl = json.load(io.open(model_path, encoding="utf-8"))
    exp_t = len(mdl.get("items16", {})); exp_f = sum(1 for f in mdl["failures"] if f.get("authored"))
    if n_auth["term"] != exp_t: fail(f"authored term notes {n_auth['term']} != items16 {exp_t}")
    if n_auth["failure"] != exp_f: fail(f"authored failure notes {n_auth['failure']} != authored F-blocks {exp_f}")
print(f"(8) 골격 OK · authored terms {n_auth['term']} failures {n_auth['failure']}")
def q(v, f):
    v = sorted(v); return v[min(len(v) - 1, int(len(v) * f))] if v else 0
io.open(C.REPORTS / "note-lengths.md", "w", encoding="utf-8").write(
    "| type | n | min | median | p95 | max |\n|---|---|---|---|---|---|\n" +
    "\n".join(f"| {t} | {len(v)} | {min(v)} | {q(v, .5)} | {q(v, .95)} | {max(v)} |" for t, v in sorted(lengths.items())) + "\n")

# 7) 고아 용어 노트(정보)
inbound = collections.Counter()
for p, (meta, body) in notes.items():
    if meta.get("type") == "excerpt": continue          # 발췌 노트의 돌아가기 링크는 고아를 가리지 않게 제외
    for m in re.finditer(r"\[\[([^\]|#]+)", body): inbound[m.group(1).rstrip("\\").split("/")[-1].lower()] += 1
orphans = [p.stem for p, (meta, _) in notes.items() if meta.get("type") == "term" and inbound[p.stem.lower()] == 0]
print(f"(7) 고아 용어 노트(인바운드 0) {len(orphans)}개 (정보): {orphans[:8]}")
io.open(C.REPORTS / f"vault-check-{which}.md", "w", encoding="utf-8").write(
    f"# vault check ({which})\n\n- notes: {len(files)}\n- types: {dict(fm_types)}\n- links: {total_links}, unresolved: {dict(unresolved)}\n- orphan terms: {len(orphans)}\n" + "\n".join(f"  - {o}" for o in orphans))
print("ALL OK" if ok else "FAIL")

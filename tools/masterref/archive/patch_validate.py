# -*- coding: utf-8 -*-
import io
p='validate_vault.py'; s=io.open(p,encoding='utf-8').read()
old='''# 7) 고아 용어 노트(정보)'''
new='''# 8) 노트 골격: H2 집합·순서, 집필 표시, 잡 라벨, 길이
TERM_H2 = ["해설", "하위지식", "문맥별 뜻", "본문 발췌", "해설지 문맥", "사전·규칙", "관련 실패", "연결"]
FAIL_H2 = ["개요", "해설"] + list(C.AUTHORED_F) + ["출처 발췌", "해설지 문맥", "규칙·연대기", "관련 용어", "언급 위치"]
lengths = collections.defaultdict(list); n_auth = collections.Counter()
for p, (meta, body) in notes.items():
    t = meta.get("type"); lines = body.split("\\n"); lengths[t].append(len(lines))
    if t not in ("term", "failure"): continue
    h2 = [l[3:].strip() for l in lines if l.startswith("## ")]
    allowed = TERM_H2 if t == "term" else FAIL_H2
    if any(h not in allowed for h in h2): fail(f"unknown H2 {[h for h in h2 if h not in allowed]} in {p.name}")
    idx = [allowed.index(h) for h in h2 if h in allowed]
    if idx != sorted(idx): fail(f"H2 out of order {h2} in {p.name}")
    if len(h2) != len(set(h2)): fail(f"duplicate H2 in {p.name}")
    if str(meta.get("authored")).lower() == "true": n_auth[t] += 1
    if "[[" in body and re.search(r"```[^`]*\\[\\[", body): fail(f"link inside fence: {p.name}")
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
    "| type | n | min | median | p95 | max |\\n|---|---|---|---|---|---|\\n" +
    "\\n".join(f"| {t} | {len(v)} | {min(v)} | {q(v, .5)} | {q(v, .95)} | {max(v)} |" for t, v in sorted(lengths.items())) + "\\n")

# 7) 고아 용어 노트(정보)'''
assert old in s; s=s.replace(old,new,1)
s=s.replace('C.REPORTS.mkdir(exist_ok=True)\nio.open(C.REPORTS / f"vault-check-{which}.md"', 'io.open(C.REPORTS / f"vault-check-{which}.md"')
s=s.replace('# 8) 노트 골격', 'C.REPORTS.mkdir(exist_ok=True)\n# 8) 노트 골격')
io.open(p,'w',encoding='utf-8',newline='\n').write(s); print('ok')

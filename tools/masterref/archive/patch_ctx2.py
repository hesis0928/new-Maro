# -*- coding: utf-8 -*-
import io
p = 'build_context.py'; s = io.open(p, encoding='utf-8').read()
old = '''        fs = list(e["surfaces"]) + [a for a in e["aliases"] if not a.startswith("`")]
        d = e["display"]
        if re.search("[가-힣]", d) and len(d) >= 2: fs.append(d)
        elif len(d) >= 3: fs.append(d)
        out = []
        for f in fs:
            if len(f) < 2 or (not re.search("[가-힣]", f) and len(f) < 3): continue
            if f.lower() in C.STOPWORDS: continue
            if f not in out: out.append(f)
        return out'''
new = '''        fs = list(e["surfaces"]) + [a for a in e["aliases"] if not a.startswith("`")]
        d = e["display"]
        fs.append(d)
        # `한글(English)` / `X(설명)` 꼴은 괄호 앞 머리도 표면형으로(한글 2자 이상, ASCII는 4자 이상 또는 대문자 약어 2자 이상)
        m = re.match(r"^(.+?)\\s*\\(([^()]*)\\)$", d)
        if m:
            fs.append(m.group(1).strip())
            en = m.group(2).strip()
            if re.match(r"^[\\x20-\\x7e]+$", en) and (len(en) >= 6 or re.match(r"^[A-Z][A-Z0-9_]+$", en)): fs.append(en)
        out = []
        for f in fs:
            f = f.strip()
            if not f: continue
            ko = bool(re.search("[가-힣]", f))
            if ko and len(f) < 2: continue
            if not ko and not (len(f) >= 4 or re.match(r"^[A-Z][A-Z0-9_]+$", f) and len(f) >= 2): continue
            if f.lower() in C.STOPWORDS: continue
            if f not in out: out.append(f)
        return out'''
assert old in s; s = s.replace(old, new)
old2 = '''        body = pick(in_secs(prim, body_kinds), body_cap, taken)
        if not hub_stop and len(body) < caps["term_body"]:
            body += pick(in_secs(rest, body_kinds), caps["term_body"] - len(body), taken)'''
new2 = '''        body = pick(in_secs(prim, body_kinds), body_cap, taken)
        if not hub_stop and len(body) < caps["term_body"]:
            body += pick(in_secs(rest, body_kinds), caps["term_body"] - len(body), taken)
        if not hub_stop and len(body) < caps["term_body_other"]:
            # 등장 절 밖의 언급(문서 순서) — 개요 장에서만 정의된 용어가 실제로 다뤄지는 절을 잡는다
            others = sorted(o for o in hits if U[o]["kind"] in body_kinds and U[o]["sec"] not in prim and U[o]["sec"] not in rest)
            body += pick(others, caps["term_body_other"] - len(body), taken)'''
assert old2 in s; s = s.replace(old2, new2)
io.open(p, 'w', encoding='utf-8', newline='\n').write(s)
c = 'config.py'; t = io.open(c, encoding='utf-8').read()
t = t.replace('EXCERPT_CAPS = {"term_body": 12, "term_body_primary_min": 6,', 'EXCERPT_CAPS = {"term_body": 12, "term_body_other": 8, "term_body_primary_min": 6,')
io.open(c, 'w', encoding='utf-8', newline='\n').write(t)
print('ok')

# -*- coding: utf-8 -*-
import io
p = 'build_context.py'; s = io.open(p, encoding='utf-8').read()
old = '''        ctx = pick(in_secs(list(dict.fromkeys([e["explained_in"]] + e["secs"])), {"ctx"}), caps["term_ctx"], taken)'''
new = '''        if not hits:
            # 2차: 서술형 용어("bookPaths() 선초기화", "필터 → 접기 → 상한")는 토큰 조합으로 자기 절 안에서만 찾는다
            toks = display_tokens(e["display"])
            if toks:
                need = min(2, len(toks))
                scope_units = [o for sec in prim + rest for o in corpus.by_sec.get(sec, []) if U[o]["kind"] in ("bullet", "sent", "row", "ctx")]
                scored = []
                for o in scope_units:
                    n = token_score(U[o], toks)
                    if n >= need: scored.append((-n, o))
                hits = {o for _, o in sorted(scored)}
        ctx = pick(in_secs(list(dict.fromkeys([e["explained_in"]] + e["secs"])), {"ctx"}), caps["term_ctx"], taken)'''
assert old in s; s = s.replace(old, new)
helpers = '''

IDENT_TOK = re.compile(r"[A-Za-z_][\\w:.]*(?:\\(\\))?")
KO_TOK = re.compile(r"[가-힣]{2,}")


def display_tokens(display):
    """서술형 용어의 유의미 토큰: 식별자(4자 이상, `()` 허용)와 한글 단어(2자 이상). 일반어는 STOPWORDS로 제외."""
    toks = []
    for m in IDENT_TOK.finditer(display):
        t = m.group(0)
        if len(t.rstrip("()")) >= 4 and t.lower() not in C.STOPWORDS: toks.append(("id", t))
    for m in KO_TOK.finditer(display):
        if m.group(0) not in ("이유", "경우", "때문", "위해", "대한", "대해", "이후", "이전", "전체", "관련"): toks.append(("ko", m.group(0)))
    return toks


def token_score(u, toks):
    n = 0
    for kind, t in toks:
        if kind == "id":
            h = head_of(t)
            if any(sp == t or sp == h or head_of(sp) == h for sp in u["bt"]) or re.search(r"(?<![A-Za-z0-9_])" + re.escape(h) + r"(?![A-Za-z0-9_])", u["text"]):
                n += 1
        else:
            m = re.search(re.escape(t), u["text"])
            if m and form_at(u["text"], m.start(), m.end(), t): n += 1
    return n
'''
s = s.replace('''

def scope_sections(model, item_key):''', helpers + '''

def scope_sections(model, item_key):''')
io.open(p, 'w', encoding='utf-8', newline='\n').write(s)
print('ok')

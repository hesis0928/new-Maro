# -*- coding: utf-8 -*-
import io, re

def sub(path, old, new, must=True):
    s = io.open(path, encoding="utf-8").read()
    if old not in s:
        if must: raise SystemExit(f"NOT FOUND in {path}: {old[:60]!r}")
        return
    s = s.replace(old, new, 1); io.open(path, "w", encoding="utf-8").write(s); print("patched", path)

# ---- naming.py
sub("naming.py",
'''def term_key(t: str) -> str:
    s = re.sub(r"\\s+", " ", t.replace("`", "").strip().lower())
    s2 = re.sub(r"\\(.*?\\)$", "", s).strip()
    k = s2 if s2 else s
    return C.MERGES.get(k, k)''',
'''def strip_trailing_group(s: str) -> str:
    """끝의 (…)/{…} 인자 그룹 하나를 떼어낸다 — 머리(그 앞)에 괄호가 없을 때만."""
    if not s or s[-1] not in ")}": return s
    close = s[-1]; opn = "(" if close == ")" else "{"
    depth = 0
    for i in range(len(s) - 1, -1, -1):
        if s[i] == close: depth += 1
        elif s[i] == opn:
            depth -= 1
            if depth == 0:
                head = s[:i].rstrip()
                if head and not re.search(r"[(){}]", head): return head
                return s
    return s


def term_key(t: str) -> str:
    s = re.sub(r"\\s+", " ", t.replace("`", "").strip().lower())
    s2 = strip_trailing_group(s).strip()
    k = s2 if s2 else s
    return C.MERGES.get(k, k)''')

sub("naming.py",
'''    s = sanitize(term)
    s = re.sub(r"(\\w+)\\.h ／ \\1\\.cpp", r"\\1.{h,cpp}", s)''',
'''    s = sanitize(term)
    s = re.sub(r"(\\w+)\\.h ／ \\1\\.cpp", r"\\1.{h,cpp}", s)
    # 식별자 머리만 남긴다: `foo(args)` → foo, `Foo{…}` → Foo, `foo — 설명` → foo (머리가 식별자형일 때)
    head = s.split(" — ")[0].strip()
    head2 = strip_trailing_group(head).strip()
    if head2 and re.match(r"^[A-Za-z_][\\w：.〈〉<>\\-]*$", head2) and len(head2) >= 3:
        s = head2''')

# ---- build_index.py
sub("build_index.py",
'''            if re.search(r"[A-Z_.:]", en) or len(en) >= 7: surf.add(en)''',
'''            if re.match(r"^[\\x20-\\x7e]+$", en) and (re.search(r"[A-Z_.:]", en) or len(en) >= 7): surf.add(en)''')

sub("build_index.py",
'''    if is_code:
        code.add(plain)''',
'''    if is_code:
        code.add(plain)
        head = N.strip_trailing_group(plain).strip()
        if head != plain and re.match(r"^[A-Za-z_][\\w:.<>]*$", head) and len(head) >= 4: code.add(head)''')

sub("build_index.py",
'''    surf = {s for s in surf if len(s) >= 2 and not (len(s) == 1) and s.lower() not in C.STOPWORDS and not re.fullmatch(r"[가-힣]", s)}''',
'''    def ok(s):
        if s.lower() in C.STOPWORDS: return False
        return len(s) >= 3
    surf = {s for s in surf if ok(s)}''')

# ---- linkify.py
sub("linkify.py",
'''                    if C.CODE_ALIAS_STYLE == "backtick": out.append(f"[[{fn}|`{inner}`]]")
                    else: out.append(f"[[{fn}|{inner}]]")''',
'''                    if C.CODE_ALIAS_STYLE == "backtick": out.append(f"[[{fn}|`{inner}`]]")
                    elif fn == inner: out.append(f"[[{fn}]]")
                    else: out.append(f"[[{fn}|{inner}]]")''')
print("done")

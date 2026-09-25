# -*- coding: utf-8 -*-
"""파일명 유도 + 보관함 전역 충돌 검사."""
import re, unicodedata, pathlib
import config as C

FW = {'/': '／', '\\': '＼', ':': '：', '*': '＊', '?': '？', '"': "'", '<': '〈', '>': '〉',
      '|': '｜', '#': '＃', '^': '＾', '[': '［', ']': '］'}
FORBIDDEN = set(FW.keys())
FILE_LIKE = re.compile(r"^[\w.\-]+\.(h|cpp|py|txt|json|ps1|md|mod|cmake|bak|\{h,cpp\})\b|^CMakeLists\.txt|^[\w\-]+\.\{h,cpp\}")


def sanitize(s: str) -> str:
    s = unicodedata.normalize("NFC", s.replace("`", ""))
    s = re.sub(r"\s+", " ", s).strip()
    s = "".join(FW.get(c, c) for c in s)
    s = re.sub(r"^\.+", "", s).rstrip(". ")
    return s


def strip_trailing_group(s: str) -> str:
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
    s = re.sub(r"\s+", " ", t.replace("`", "").strip().lower())
    s2 = strip_trailing_group(s).strip()
    k = s2 if s2 else s
    return C.MERGES.get(k, k)


def term_filename(term: str) -> str:
    if term in C.TERM_FILENAME_OVERRIDES:
        return C.TERM_FILENAME_OVERRIDES[term]
    s = sanitize(term)
    s = re.sub(r"(\w+)\.h ／ \1\.cpp", r"\1.{h,cpp}", s)
    # 식별자 머리만 남긴다: `foo(args)` → foo, `Foo{…}` → Foo, `foo — 설명` → foo (머리가 식별자형일 때)
    head = s.split(" — ")[0].strip()
    head2 = strip_trailing_group(head).strip()
    if head2 and re.match(r"^[A-Za-z_][\w：.〈〉<>\-]*$", head2) and len(head2) >= 3:
        s = head2
    if len(s) > C.TERM_NAME_MAX:
        s = s[:C.TERM_NAME_MAX].rsplit(" ", 1)[0]
    return s


def section_filename(num: str, heading: str) -> str:
    if num in C.SECTION_TITLE_OVERRIDES:
        return C.SECTION_TITLE_OVERRIDES[num]
    t = heading.replace("`", "")
    t = re.sub(r"\s*\(\s*[\d,+~. ]*\s*줄[^)]*\)", "", t)          # (275줄), (74+356줄), (1,241줄 — 최대)
    t = re.sub(r"\s*\((\d+)\)\s*$", "", t)                          # (35개) 류 꼬리
    left, sep, right = t.partition(" — ")
    title = left.strip()
    if sep and FILE_LIKE.match(title):
        title = f"{title} — {right.strip()}"
    title = sanitize(title)
    if len(title) > C.SECTION_NAME_MAX:
        title = title[:C.SECTION_NAME_MAX].rsplit(" ", 1)[0]
    n = num
    if C.PAD_MINOR:
        a, b = num.split(".", 1)
        n = f"{a}.{int(b.split('.')[0]):02d}" + ("." + b.split(".", 1)[1] if "." in b else "")
    return f"{n} {title}"


def failure_filename(fid: str, title: str) -> str:
    t = sanitize(title)
    if len(t) > C.FAIL_NAME_MAX:
        t = t[:C.FAIL_NAME_MAX].rsplit(" ", 1)[0]
    return f"{fid} {t}"


def hub_filename(display: str, parent: str, taken: set) -> str:
    base = f"Intro {display}"
    return base if base.lower() not in taken else f"{base} ({parent})"


def branch_folder(branch: str) -> str:
    return sanitize(C.BRANCH_FOLDER_OVERRIDES.get(branch, branch))


def existing_basenames() -> set:
    """기존 vault(Maya Ver-2026.1)의 basename(소문자) — 충돌 금지 집합."""
    names = set()
    for p in C.EXISTING_DIR.rglob("*.md"):
        names.add(p.stem.lower())
    return names


def check_name(name: str):
    bad = [c for c in name if c in FORBIDDEN]
    assert not bad, (name, bad)
    assert not name.endswith((".", " ")) and not name.startswith("."), name
    assert len(name) <= 255, name
    return True

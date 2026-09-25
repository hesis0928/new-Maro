# -*- coding: utf-8 -*-
"""본문에 위키링크를 넣는다.
패스 A: §참조·F-ID → 절/장/실패 노트.  패스 B: 용어 표면형(텍스트) + 코드 스팬(정확 일치) → 용어 노트.
세그먼트: 펜스, 인라인 코드, 기존 [[…]], URL, 헤딩, 라벨(**…:**), 표 구분선은 건드리지 않는다."""
import re, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import config as C

HANGUL = "가-힣"


def alias_safe(s: str) -> str:
    """위키링크 별칭에 들어가면 파싱이 깨지는 문자 치환"""
    return s.replace("]", "］").replace("[", "［").replace("|", "｜")


class Linker:
    def __init__(self, index, targets):
        """index: index.json entries; targets: {'section': {num: basename}, 'chapter': {n: basename}, 'failure': {fid: basename},
        'failclass': {num: basename}, 'note_hub': basename}"""
        self.entries = index["entries"]; self.t = targets
        # 표면형 → (key)
        surf = {}; code = {}
        amb = index.get("ambiguous", {})
        for k, e in self.entries.items():
            for s in e["surfaces"]:
                if s in amb:
                    pref = C.PREFER.get(s)
                    if pref != k: continue
                if s in surf and surf[s] != k: continue
                surf[s] = k
            for s in e["code_forms"]:
                key = "`" + s
                if key in amb:
                    pref = C.PREFER.get(s)
                    if pref != k: continue
                code[s] = k
        # 짧고 흔한 단어 제거
        self.surf = {s: k for s, k in surf.items() if len(s) >= 2}
        self.code = code
        forms = sorted(self.surf.keys(), key=len, reverse=True)
        self.rx = re.compile("|".join(re.escape(f) for f in forms)) if forms else None
        self.hub_stop = set(C.HUB_STOPLIST)

    # ---- 패스 A
    def link_refs(self, text, self_key=None, self_name=None):
        t = self.t
        def wrap(fn, alias):
            return m_group0 if fn == self_name else f"[[{fn}|{alias}]]"
        def sec_link(m):
            nonlocal m_group0
            m_group0 = m.group(0)
            num = m.group(1)
            if num.startswith("13.") and num.count(".") >= 1:
                target = num[3:]
                if target in t["section"]: return wrap(t["section"][target], f"§{num} 해설")
                if target in t["chapter"]: return wrap(t["chapter"][target], f"§{num} 해설")
                return m.group(0)
            if num.startswith("14"):
                if num in t["failclass"]: return wrap(t["failclass"][num], f"§{num}")
                return wrap(t["fail_hub"], f"§{num}")
            if num.startswith("15"): return wrap(t["note_hub"], f"§{num}")
            if num in t["section"]: return wrap(t["section"][num], f"§{num}")
            if num in t["subsection"]: return wrap(t["subsection"][num], f"§{num}")
            parts = num.split(".")
            if len(parts) >= 3 and ".".join(parts[:2]) in t["section"]: return wrap(t["section"][".".join(parts[:2])], f"§{num}")
            if parts[0] in t["chapter"]: return wrap(t["chapter"][parts[0]], f"§{num}")
            return m.group(0)
        m_group0 = ""
        out = []
        for seg, kind in self.segments(text):
            if kind == "text":
                seg = re.sub(r"§(\d+(?:\.\d+)*)", sec_link, seg)
                seg = re.sub(r"(?<![\w\[|])F-(\d{3})(?!\d)", lambda m: f"[[{t['failure'][m.group(0)]}|{m.group(0)}]]" if m.group(0) in t["failure"] and t["failure"][m.group(0)] != self_name else m.group(0), seg)
            out.append(seg)
        return "".join(out)

    # ---- 세그먼트
    SEG = re.compile(r"(```.*?```|`[^`\n]*`|\[\[.*?\]\]|https?://[^\s)>\]]+|\*\*[^*\n]+?:\*\*)", re.S)

    def segments(self, text):
        pos = 0
        for m in self.SEG.finditer(text):
            if m.start() > pos: yield text[pos:m.start()], "text"
            s = m.group(0)
            kind = "fence" if s.startswith("```") else "code" if s.startswith("`") else "link" if s.startswith("[[") else "url" if s.startswith("http") else "label"
            yield s, kind
            pos = m.end()
        if pos < len(text): yield text[pos:], "text"

    # ---- 패스 B
    def link_terms(self, text, self_key=None, per_note_seen=None, mode=None):
        if self.rx is None: return text
        seen = per_note_seen if per_note_seen is not None else set()
        out = []
        for seg, kind in self.segments(text):
            if kind == "code":
                inner = seg[1:-1]
                k = self.code.get(inner)
                if k and k != self_key:
                    fn = self.entries[k]["filename"]
                    if C.CODE_ALIAS_STYLE == "backtick": out.append(f"[[{fn}|`{inner}`]]")
                    elif fn == inner: out.append(f"[[{fn}]]")
                    else: out.append(f"[[{fn}|{alias_safe(inner)}]]")
                    continue
                out.append(seg); continue
            if kind != "text":
                out.append(seg); continue
            # 헤딩 줄은 건너뜀
            lines = seg.split("\n")
            for li, line in enumerate(lines):
                if line.startswith("#"):
                    continue
                lines[li] = self._link_line(line, self_key, seen, mode)
            out.append("\n".join(lines))
        return "".join(out)

    def _link_line(self, line, self_key, seen, mode=None):
        mode = mode or C.LINK_MODE
        res = []; pos = 0
        for m in self.rx.finditer(line):
            s, e = m.start(), m.end(); form = m.group(0)
            if not form_at(line, s, e, form): continue
            if s < pos: continue
            k = self.surf[form]
            if k == self_key: continue
            if k in seen and (form in self.hub_stop or mode == "first-per-note"): continue
            seen.add(k)
            fn = self.entries[k]["filename"]
            res.append(line[pos:s])
            res.append(f"[[{fn}]]" if fn == form else f"[[{fn}|{alias_safe(form)}]]")
            pos = e
        res.append(line[pos:])
        return "".join(res)

    def link(self, text, self_key=None, seen=None, self_name=None, mode=None):
        """mode: None → config.LINK_MODE("all"), "first-per-note" → 같은 용어는 노트당 한 번만(발췌 절의 링크 폭발 방지)"""
        return table_pipes(self.link_terms(self.link_refs(text, self_key, self_name), self_key, seen, mode))


def form_at(line, s, e, form):
    """표면형 `form`이 line[s:e]에서 독립된 단어로 서 있는가 — 링크와 발췌 매칭이 같은 규칙을 쓴다.
    ASCII 표면형: 양쪽이 비단어 문자. 한글 포함 표면형: 앞만 비한글·비단어(조사 허용). 대괄호에 붙은 것은 제외."""
    before = line[s - 1] if s > 0 else " "
    after = line[e] if e < len(line) else " "
    if before in "[]" or after in "[]": return False
    if not re.search(f"[{HANGUL}]", form):
        # ASCII 표면형: 양옆이 ASCII 단어 문자가 아니어야 한다. 한글 조사는 바로 붙어도 됨("CARLA처럼", "PySide6로") —
        # 파이썬 \w 는 한글도 포함하므로 여기서는 ASCII 범위만 본다
        return not (re.match(r"[A-Za-z0-9_]", before) or re.match(r"[A-Za-z0-9_]", after))
    return not re.match(f"[{HANGUL}\\w]", before)


def table_pipes(text):
    """표 행(`|`로 시작) 안의 위키링크 별칭 구분자 `|` 는 Obsidian 표에서 `\\|` 로 이스케이프해야 셀이 갈라지지 않는다."""
    out = []
    for line in text.split("\n"):
        if line.startswith("|"):
            line = re.sub(r"\[\[([^\]|]+)\|([^\]]+)\]\]", lambda m: "[[" + m.group(1) + "\\|" + m.group(2) + "]]", line)
        out.append(line)
    return "\n".join(out)


def assert_clean(text, path=""):
    # 펜스 안 [[ 금지, 빈 별칭 금지
    for m in re.finditer(r"```.*?```", text, re.S):
        assert "[[" not in m.group(0), f"link inside fence: {path}"
    assert "|]]" not in text, f"empty alias: {path}"

# -*- coding: utf-8 -*-
import io
def sub(path, old, new):
    s = io.open(path, encoding="utf-8").read()
    if old not in s: raise SystemExit(f"NOT FOUND in {path}: {old[:70]!r}")
    io.open(path, "w", encoding="utf-8").write(s.replace(old, new, 1)); print("patched", path)

# linkify: self_name 지원
sub("linkify.py", '''    def link_refs(self, text, self_key=None):
        t = self.t
        def sec_link(m):
            num = m.group(1)''', '''    def link_refs(self, text, self_key=None, self_name=None):
        t = self.t
        def wrap(fn, alias):
            return m_group0 if fn == self_name else f"[[{fn}|{alias}]]"
        def sec_link(m):
            nonlocal m_group0
            m_group0 = m.group(0)
            num = m.group(1)''')
sub("linkify.py", '''            if num.startswith("13.") and num.count(".") >= 1:
                target = num[3:]
                if target in t["section"]: return f"[[{t['section'][target]}|§{num} 해설]]"
                if target in t["chapter"]: return f"[[{t['chapter'][target]}|§{num} 해설]]"
                return m.group(0)
            if num.startswith("14"):
                if num in t["failclass"]: return f"[[{t['failclass'][num]}|§{num}]]"
                return f"[[{t['fail_hub']}|§{num}]]"
            if num.startswith("15"): return f"[[{t['note_hub']}|§{num}]]"
            if num in t["section"]: return f"[[{t['section'][num]}|§{num}]]"
            if num in t["subsection"]: return f"[[{t['subsection'][num]}|§{num}]]"
            parts = num.split(".")
            if len(parts) >= 3 and ".".join(parts[:2]) in t["section"]: return f"[[{t['section']['.'.join(parts[:2])]}|§{num}]]"
            if parts[0] in t["chapter"]: return f"[[{t['chapter'][parts[0]]}|§{num}]]"
            return m.group(0)
        out = []''', '''            if num.startswith("13.") and num.count(".") >= 1:
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
        out = []''')
sub("linkify.py", '''                seg = re.sub(r"(?<![\\w\\[|])F-(\\d{3})(?!\\d)", lambda m: f"[[{t['failure'][m.group(0)]}|{m.group(0)}]]" if m.group(0) in t["failure"] else m.group(0), seg)''',
'''                seg = re.sub(r"(?<![\\w\\[|])F-(\\d{3})(?!\\d)", lambda m: f"[[{t['failure'][m.group(0)]}|{m.group(0)}]]" if m.group(0) in t["failure"] and t["failure"][m.group(0)] != self_name else m.group(0), seg)''')
sub("linkify.py", '''    def link(self, text, self_key=None, seen=None):
        return self.link_terms(self.link_refs(text, self_key), self_key, seen)''',
'''    def link(self, text, self_key=None, seen=None, self_name=None):
        return self.link_terms(self.link_refs(text, self_key, self_name), self_key, seen)''')

# emit: self_name 전달
sub("emit_vault.py", '''        text = L.link(text, None, seen)
        head = fm({"type": "section",''', '''        text = L.link(text, None, seen, sec_fn[n])
        head = fm({"type": "section",''')
sub("emit_vault.py", '''        text = L.link("\\n".join(body), None, set())
        head = fm({"type": "subsection",''', '''        text = L.link("\\n".join(body), None, set(), sub_fn[n])
        head = fm({"type": "subsection",''')
sub("emit_vault.py", '''        text = L.link("\\n".join(body), None, set())
        head = fm({"type": "chapter",''', '''        text = L.link("\\n".join(body), None, set(), ch_hub[ch])
        head = fm({"type": "chapter",''')
sub("emit_vault.py", '''        text = L.link("\\n".join(body) + "\\n", k, set())
        head = fm({"type": "term",''', '''        text = L.link("\\n".join(body) + "\\n", k, set(), e["filename"])
        head = fm({"type": "term",''')
sub("emit_vault.py", '''        text = L.link("\\n".join(body) + "\\n", None, set())
        head = fm({"type": "failure",''', '''        text = L.link("\\n".join(body) + "\\n", None, set(), fail_fn[f["id"]])
        head = fm({"type": "failure",''')

# validate: 경로 길이는 라이브 경로 기준, partial이면 미해석 링크는 정보
sub("validate_vault.py", '''    if len(str(p)) > 240: fail(f"path too long ({len(str(p))}): {rel}")''',
'''    live_len = len(str(C.LIVE_DIR)) + 1 + len(str(rel))
    if live_len > 240: fail(f"live path too long ({live_len}): {rel}")''')
sub("validate_vault.py", '''for t, n in unresolved.most_common(15): fail(f"unresolved [[{t}]] ×{n}")''',
'''for t, n in unresolved.most_common(15):
    if partial: print(f"  info(partial) unresolved [[{t}]] ×{n}")
    else: fail(f"unresolved [[{t}]] ×{n}")''')
print("done")

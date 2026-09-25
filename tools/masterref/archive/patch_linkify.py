# -*- coding: utf-8 -*-
import io, re
p = 'linkify.py'; s = io.open(p, encoding='utf-8').read()

# 1) _link_line: 경계 판정을 form_at()으로, mode 인자 추가
start = s.index("    def _link_line(self, line, self_key, seen):")
end = s.index("            fn = self.entries[k][\"filename\"]", start)
new_head = '''    def _link_line(self, line, self_key, seen, mode=None):
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
'''
s = s[:start] + new_head + s[end:]

s = s.replace("    def link_terms(self, text, self_key=None, per_note_seen=None):",
              "    def link_terms(self, text, self_key=None, per_note_seen=None, mode=None):")
s = s.replace("                lines[li] = self._link_line(line, self_key, seen)",
              "                lines[li] = self._link_line(line, self_key, seen, mode)")
old4 = '''    def link(self, text, self_key=None, seen=None, self_name=None):
        return table_pipes(self.link_terms(self.link_refs(text, self_key, self_name), self_key, seen))'''
new4 = '''    def link(self, text, self_key=None, seen=None, self_name=None, mode=None):
        """mode: None → config.LINK_MODE("all"), "first-per-note" → 같은 용어는 노트당 한 번만(발췌 절의 링크 폭발 방지)"""
        return table_pipes(self.link_terms(self.link_refs(text, self_key, self_name), self_key, seen, mode))


def form_at(line, s, e, form):
    """표면형 `form`이 line[s:e]에서 독립된 단어로 서 있는가 — 링크와 발췌 매칭이 같은 규칙을 쓴다.
    ASCII 표면형: 양쪽이 비단어 문자. 한글 포함 표면형: 앞만 비한글·비단어(조사 허용). 대괄호에 붙은 것은 제외."""
    before = line[s - 1] if s > 0 else " "
    after = line[e] if e < len(line) else " "
    if before in "[]" or after in "[]": return False
    if not re.search("[" + HANGUL + "]", form):
        return not (re.match(r"\\w", before) or re.match(r"\\w", after))
    return not re.match("[" + HANGUL + r"\\w]", before)'''
assert old4 in s; s = s.replace(old4, new4)
io.open(p, 'w', encoding='utf-8', newline='\n').write(s)
print("patched")

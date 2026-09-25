# -*- coding: utf-8 -*-
import io
def sub(path, old, new):
    s = io.open(path, encoding="utf-8").read()
    if old not in s: raise SystemExit(f"NOT FOUND in {path}: {old[:70]!r}")
    io.open(path, "w", encoding="utf-8").write(s.replace(old, new, 1)); print("patched", path)

# 1) 링크 세그먼트: 첫 ]] 까지 (별칭에 ] 가 있어도)
sub("linkify.py", r'''    SEG = re.compile(r"(```.*?```|`[^`\n]*`|\[\[[^\]]*\]\]|https?://[^\s)>\]]+|\*\*[^*\n]+?:\*\*)", re.S)''',
                  r'''    SEG = re.compile(r"(```.*?```|`[^`\n]*`|\[\[.*?\]\]|https?://[^\s)>\]]+|\*\*[^*\n]+?:\*\*)", re.S)''')
# 별칭 위생 함수
sub("linkify.py", '''HANGUL = "가-힣"
''', '''HANGUL = "가-힣"


def alias_safe(s: str) -> str:
    """위키링크 별칭에 들어가면 파싱이 깨지는 문자 치환"""
    return s.replace("]", "］").replace("[", "［").replace("|", "｜")
''')
sub("linkify.py", '''            res.append(f"[[{fn}]]" if fn == form else f"[[{fn}|{form}]]")''',
                  '''            res.append(f"[[{fn}]]" if fn == form else f"[[{fn}|{alias_safe(form)}]]")''')
sub("linkify.py", '''                    elif fn == inner: out.append(f"[[{fn}]]")
                    else: out.append(f"[[{fn}|{inner}]]")''',
                  '''                    elif fn == inner: out.append(f"[[{fn}]]")
                    else: out.append(f"[[{fn}|{alias_safe(inner)}]]")''')
# emit: 용어 불릿 별칭 위생
sub("emit_vault.py", '''from linkify import Linker, assert_clean''', '''from linkify import Linker, assert_clean, alias_safe''')
sub("emit_vault.py", '''                        links.append(f"[[{fn}]]" if fn == disp else f"[[{fn}|{disp}]]")''',
                     '''                        links.append(f"[[{fn}]]" if fn == disp else f"[[{fn}|{alias_safe(disp)}]]")''')
sub("emit_vault.py", '''                body.append(f"- [[{sub_fn[sn]}|§{sn} {subs[sn]['heading'].split(' — ')[0].replace('`','')}]] — {one_liner(sl, subs[sn]['heading'].split(' — ')[-1])}")''',
                     '''                body.append(f"- [[{sub_fn[sn]}|{alias_safe('§' + sn + ' ' + subs[sn]['heading'].split(' — ')[0].replace('`',''))}]] — {one_liner(sl, subs[sn]['heading'].split(' — ')[-1])}")''')
sub("emit_vault.py", '''            body.append("**같은 행:** " + ", ".join(f"[[{E[m]['filename']}|{E[m]['display']}]]" for m in e["mates"] if m in E))''',
                     '''            body.append("**같은 행:** " + ", ".join((f"[[{E[m]['filename']}]]" if E[m]['filename'] == E[m]['display'] else f"[[{E[m]['filename']}|{alias_safe(E[m]['display'])}]]") for m in e["mates"] if m in E))''')
sub("emit_vault.py", '''            body.append(f"- {'★' if e['depth']=='심화' else '·'} [[{e['filename']}|{e['display']}]] — {m[:80] + ('…' if len(m) > 80 else '')}")''',
                     '''            body.append(f"- {'★' if e['depth']=='심화' else '·'} [[{e['filename']}|{alias_safe(e['display'])}]] — {m[:80] + ('…' if len(m) > 80 else '')}")''')

# 5) 행의 뜻을 ' / ' 로 용어 수만큼 나눠 배정 + 6) aliases 집합 연산 + 7) explained_in = 심화 행 우선
sub("build_index.py", '''            keys_in_row = []
            for t in row["terms"]:''', '''            keys_in_row = []
            parts = [p.strip() for p in re.split(r"\\s+/\\s+", row["cells"][1])]
            split_ok = len(parts) == len(row["terms"]) and len(parts) > 1
            for ti, t in enumerate(row["terms"]):''')
sub("build_index.py", '''                e["meanings"].append({"item": key, "meaning": row["cells"][1], "cat": row["cells"][2], "depth": row["depth"], "ref": row["ref"]})''',
                      '''                e["meanings"].append({"item": key, "meaning": parts[ti] if split_ok else row["cells"][1], "cat": row["cells"][2], "depth": row["depth"], "ref": row["ref"]})''')
sub("build_index.py", '''    for e in entries.values():
        if e["explained_in"] is None: e["explained_in"] = e["secs"][0]''',
                      '''    for e in entries.values():
        if e["explained_in"] is None:
            deep = [m for m in e["meanings"] if m["depth"] == "심화"]
            e["explained_in"] = (max(deep, key=lambda m: len(m["meaning"])) if deep else e["meanings"][0])["item"]''')
sub("build_index.py", '''        e["aliases"] = sorted(e["aliases"] | set(e["surfaces"]) | set(e["code_forms"]) - {e["display"]})''',
                      '''        e["aliases"] = sorted((e["aliases"] | set(e["surfaces"]) | set(e["code_forms"])) - {e["display"]})''')
print("done")

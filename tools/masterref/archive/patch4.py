# -*- coding: utf-8 -*-
import io
def sub(path, old, new):
    s = io.open(path, encoding="utf-8").read()
    if old not in s: raise SystemExit(f"NOT FOUND in {path}: {old[:70]!r}")
    io.open(path, "w", encoding="utf-8").write(s.replace(old, new, 1)); print("patched", path)

sub("check_master.py", '''    text = "\\n".join(block_lines)
    # 하드 랩을 풀어 줄바꿈에 걸친 코드 스팬/따옴표가 양쪽에서 같은 문자열이 되게 한다
    text = re.sub(r"\\s*\\n\\s*", " ", text)
    # 펜스 안은 그대로 포함(사실이므로)
    bt = collections.Counter(re.sub(r"\\s+", " ", m.group(1)).strip() for m in re.finditer(r"`([^`]+)`", text))''',
'''    text = "\\n".join(block_lines)
    # 펜스 블록은 통째로 하나의 사실(공백 정규화)로 세고 본문에서 뺀다 — ``` 가 인라인 백틱 짝을 흐트러뜨리므로
    fences = [re.sub(r"\\s+", " ", f) for f in re.findall(r"```.*?```", text, re.S)]
    text = re.sub(r"```.*?```", " ", text, flags=re.S)
    # 하드 랩을 풀어 줄바꿈에 걸친 코드 스팬/따옴표가 양쪽에서 같은 문자열이 되게 한다
    text = re.sub(r"\\s*\\n\\s*", " ", text)
    bt = collections.Counter(re.sub(r"\\s+", " ", m.group(1)).strip() for m in re.finditer(r"`([^`]+)`", text))
    for f in fences: bt[f] += 1''')
print("done")

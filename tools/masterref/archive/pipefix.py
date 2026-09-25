# -*- coding: utf-8 -*-
"""표 행(`|`로 시작하는 줄) 안의 인라인 코드 스팬 속 `|` 를 `\\|` 로 이스케이프한다(GFM 표 규칙; parse_master 셀 분리도 이에 기댄다).
사용: python pipefix.py --scan FILE...   (건수만)
      python pipefix.py --fix  FILE...   (제자리 수정)"""
import io, re, sys

CODE = re.compile(r"`[^`\n]+`")


def fix_line(line):
    if not line.startswith("|"): return line, 0
    n = 0
    def repl(m):
        nonlocal n
        s = m.group(0)
        # 이미 이스케이프된 것은 건드리지 않는다
        s2 = re.sub(r"(?<!\\)\|", r"\\|", s)
        n += s2.count("\\|") - s.count("\\|")
        return s2
    return CODE.sub(repl, line), n


def process(path, fix):
    text = io.open(path, encoding="utf-8").read()
    out, total = [], 0
    for line in text.split("\n"):
        l2, n = fix_line(line)
        out.append(l2); total += n
    if fix and total:
        io.open(path, "w", encoding="utf-8", newline="\n").write("\n".join(out))
    return total


if __name__ == "__main__":
    mode = sys.argv[1]; files = sys.argv[2:]
    for f in files:
        n = process(f, mode == "--fix")
        print(f"{f}: {n}")

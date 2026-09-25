# -*- coding: utf-8 -*-
"""§14의 잘못된 두 행(셀 안 '|' 미이스케이프)을 원천에서 고친다. 멱등."""
import io, sys
sys.path.insert(0, __file__.rsplit("\\", 1)[0])
import config as C
s = io.open(C.MASTER_SRC, encoding="utf-8").read()
fixes = [
    ('반환 이름 `split("|")[-1]` + 알려진 부모로 재구성 | §10.9 |', '반환 이름 `split("\\|")[-1]` + 알려진 부모로 재구성 | §10.9 |'),
    ('| F-197 | `asin` 반각 구현 통과 | `|angle|>π` 미검 |', '| F-197 | `asin` 반각 구현 통과 | `\\|angle\\|>π` 미검 |'),
]
n = 0
for a, b in fixes:
    if a in s:
        assert s.count(a) == 1, a
        s = s.replace(a, b); n += 1
io.open(C.MASTER_SRC, "w", encoding="utf-8", newline="\n").write(s)
print("fixed", n)

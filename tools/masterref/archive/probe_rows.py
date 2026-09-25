# -*- coding: utf-8 -*-
import re, io, sys
sys.path.insert(0, __file__.rsplit("\\", 1)[0])
import config as C
L = io.open(C.MASTER_SRC, encoding="utf-8").read().split("\n")
for i, l in enumerate(L, 1):
    if re.match(r"^\| F-\d{3} \|", l):
        cells = re.split(r"(?<!\\)\|", l.strip())[1:-1]
        n = len(cells)
        if n not in (8, 6, 4):
            print(i, n, l[:200])

# -*- coding: utf-8 -*-
import io, re


def terms(path):
    t = io.open(path, encoding='utf-8').read()
    m = re.search(r'^### 15\.2.*?$', t, re.M); s = t[m.end():]
    e = re.search(r'^### 15\.3', s, re.M); s = s[:e.start()]
    rows = [l for l in s.split('\n') if l.startswith('| ') and not l.startswith('| 용어')]
    return [re.split(r'(?<!\\)\|', l)[1].strip() for l in rows]


old = terms('work/master.v0.md'); new = terms('work/master.edited.md')
print(len(old), len(new))
so, sn = set(old), set(new)
print('old-only', len(so - sn)); print(sorted(so - sn)[:60])
print('new-only', len(sn - so)); print(sorted(sn - so)[:60])

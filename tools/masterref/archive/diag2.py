import io,sys,json,collections
sys.path.insert(0,'.')
import config as C, naming as N
from parse_master import parse_items16
import re
lines=io.open('work/master.edited.md',encoding='utf-8').read().split("\n")
# locate §16
i=[k for k,l in enumerate(lines) if l.startswith("## 16. ")][0]
body=[l for l in lines[i:] if not l.startswith("### ") and not l.startswith("## 16. ")]
items=parse_items16(body,"","")
print('parsed',len(items))
heads=[l for l in lines[i:] if l.startswith("#### ")]
print('h4',len(heads))
keys=[N.term_key(h[5:]) for h in heads]
dup=[k for k,c in collections.Counter(keys).items() if c>1]
print('dup keys',len(dup),dup[:20])

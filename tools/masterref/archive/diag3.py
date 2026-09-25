import io,sys,json,collections
sys.path.insert(0,'.')
import config as C, naming as N
lines=io.open(str(C.MASTER_SRC),encoding='utf-8').read().split("\n")
i=[k for k,l in enumerate(lines) if l.startswith("## 16. ")][0]
heads=[l for l in lines[i:] if l.startswith("#### ")]
print('repo master h4', len(heads))
idx=json.load(io.open('work/index.json',encoding='utf-8'))
E=idx['entries'] if 'entries' in idx else idx
keys=[N.term_key(h[5:]) for h in heads]
missing=[k for k in keys if k not in E]
print('keys not in index:', len(missing), missing[:25])

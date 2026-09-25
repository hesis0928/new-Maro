import io,sys,collections
src=io.open('status.py',encoding='utf-8').read()
head=src.split('# 배치 파일 접합 여부')[0]
exec(compile(head,'status.py','exec'))
top=sys.argv[1]
by=collections.OrderedDict()
for k,e in E.items():
    if e['top']==top: by.setdefault(e['sub'],[]).append(k)
for sub,ks in by.items():
    todo=[k for k in ks if k not in items16]
    print(len(todo),len(ks),sub)

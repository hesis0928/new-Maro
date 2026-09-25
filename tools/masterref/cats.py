import io,sys,collections
src=io.open('status.py',encoding='utf-8').read()
head=src.split('# 배치 파일 접합 여부')[0]
exec(compile(head,'status.py','exec'))
tops=collections.OrderedDict()
for k,e in E.items():
    tops.setdefault(e['top'],[0,0])
    tops[e['top']][1]+=1
    if k not in items16: tops[e['top']][0]+=1
for t,(todo,tot) in tops.items(): print(todo,tot,repr(t))

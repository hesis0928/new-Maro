# -*- coding: utf-8 -*-
import io
p='build_context.py'; s=io.open(p,encoding='utf-8').read()
old='''    surf_owner = {}
    for k, e in E.items():
        for s in e["surfaces"] + [a for a in e["aliases"] if not a.startswith("`")]:
            if len(s) < 3 or (not re.search("[가-힣]", s) and len(s) < 4): continue
            if s in amb and C.PREFER.get(s) != k: continue
            surf_owner.setdefault(s, k)'''
new='''    def plain_forms(e):
        """발췌 매칭용 평문 표면형: 링크용 surfaces보다 관대하다(2자 한글 display도 허용 — 절 범위 안에서만 쓰이므로)"""
        fs = list(e["surfaces"]) + [a for a in e["aliases"] if not a.startswith("`")]
        d = e["display"]
        if re.search("[가-힣]", d) and len(d) >= 2: fs.append(d)
        elif len(d) >= 3: fs.append(d)
        out = []
        for f in fs:
            if len(f) < 2 or (not re.search("[가-힣]", f) and len(f) < 3): continue
            if f.lower() in C.STOPWORDS: continue
            if f not in out: out.append(f)
        return out
    surf_owner = {}
    for k, e in E.items():
        for s in plain_forms(e):
            if s in amb and C.PREFER.get(s) != k: continue
            surf_owner.setdefault(s, k)'''
assert old in s; s=s.replace(old,new)
old2='''        for f in e["surfaces"] + [a for a in e["aliases"] if not a.startswith("`")]:
            if surf_owner.get(f) == k: hits.update(surf_hits.get(f, []))'''
new2='''        for f in plain_forms(e):
            if surf_owner.get(f) == k: hits.update(surf_hits.get(f, []))'''
assert old2 in s; s=s.replace(old2,new2)
old3='''        tsurf = set()
        for k in fail_terms.get(fid, []):
            for s in E[k]["surfaces"]:
                if surf_owner.get(s) == k and len(s) >= 4: tsurf.add(s)'''
new3='''        # 관련 용어 표면형은 식별자가 하나도 없는 실패(52건)에서만 보조로 쓴다 — 'FAIL' 같은 일반어가 점수를 오염시킨다
        tsurf = set()
        if not idents:
            for k in fail_terms.get(fid, []):
                for s in E[k]["surfaces"]:
                    if surf_owner.get(s) == k and len(s) >= 5: tsurf.add(s)'''
assert old3 in s; s=s.replace(old3,new3)
io.open(p,'w',encoding='utf-8',newline='\n').write(s); print('ok')

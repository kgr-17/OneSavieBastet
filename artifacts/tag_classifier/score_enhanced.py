import json, io, re
from collections import Counter, defaultdict
def norm(s): return re.sub(r'\s+',' ',str(s)).strip().lower()
hold=json.load(io.open('artifacts/tag_classifier/holdout.json',encoding='utf-8'))
enh=json.load(io.open('artifacts/tag_classifier/holdout_enhanced.json',encoding='utf-8'))
canon=json.load(io.open('artifacts/tag_classifier/canon_holdout.json',encoding='utf-8'))
def plur(items):
    items=[norm(x) for x in items if x]; return Counter(items).most_common(1)[0][0] if items else None
def evalsrc(src):
    te=se=0;n=len(hold); pertag=defaultdict(lambda:[0,0])
    for h in hold:
        vs=src.get(str(h['id'])) or src.get(h['id']) or []
        pt=plur([v['tag'] for v in vs]); ps=plur([v['subtag'] for v in vs])
        tt=norm(h['truth_tag'][0]) if h['truth_tag'] else None
        if tt:
            pertag[tt][1]+=1
            if pt==tt: te+=1; pertag[tt][0]+=1
        if h['truth_subtag'] and ps==norm(h['truth_subtag'][0]): se+=1
    return 100*te/n,100*se/n,pertag
ct,cs,cp=evalsrc(canon); et,es,ep=evalsrc(enh)
print('=== ENHANCED (canonical+targeted few-shot+rules) vs canonical baseline ===')
print(f'              TAG    SUBTAG')
print(f'  canonical : {ct:.0f}%    {cs:.0f}%')
print(f'  ENHANCED  : {et:.0f}%    {es:.0f}%')
print(f'  delta     : {et-ct:+.0f}pp   {es-cs:+.0f}pp')
print(f'\n=== confusable-tag accuracy: canonical -> ENHANCED ===')
for tag in ['dos','access control','input validation','logic error','accounting error']:
    c0,n0=cp[tag]; c1,n1=ep[tag]
    if n0>=4: print(f'  {tag:20}: {100*c0//n0:3d}% -> {100*c1//n1:3d}%  ({c1}/{n1})')
print('\n  VERDICT:', 'ENHANCED WINS -> apply' if (et+es)>(ct+cs)+1 else 'no win')

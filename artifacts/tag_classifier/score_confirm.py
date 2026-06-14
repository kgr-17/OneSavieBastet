import json, io, re
from collections import Counter
def norm(s): return re.sub(r'\s+',' ',str(s).split(',')[0]).strip().lower()
hold=json.load(io.open('artifacts/tag_classifier/holdout.json',encoding='utf-8'))
res=json.load(io.open('artifacts/tag_classifier/confirm.json',encoding='utf-8'))
def plur(items):
    items=[norm(x) for x in items if x]; return Counter(items).most_common(1)[0][0] if items else None
def tagacc(byPid):
    c=sum(1 for h in hold if h['truth_tag'] and plur([v['tag'] for v in (byPid.get(str(h['id'])) or byPid.get(h['id']) or [])])==norm(h['truth_tag'][0]))
    return 100*c/len(hold)
def subacc(byPid):
    c=sum(1 for h in hold if h['truth_subtag'] and plur([v['subtag'] for v in (byPid.get(str(h['id'])) or byPid.get(h['id']) or [])])==norm(h['truth_subtag'][0]))
    return 100*c/len(hold)
st=tagacc(res['shortlist']); ss=subacc(res['shortlist'])
mt=tagacc(res['maxcontext']); ms=subacc(res['maxcontext'])
print('=== 3-pass CONFIRMATION (baselines: canonical 3p = 61% tag / 51% subtag) ===')
print(f'  shortlist : TAG {st:.0f}%  SUBTAG {ss:.0f}%')
print(f'  maxcontext: TAG {mt:.0f}%  SUBTAG {ms:.0f}%')
best_tag=max(st,mt,61); best_sub=max(ss,ms,51)
print(f'\n  best TAG strategy: {"shortlist" if st>=mt else "maxcontext"} ({max(st,mt):.0f}%) vs canonical 61%')
print(f'  best SUBTAG strategy: {"maxcontext" if ms>=ss else "shortlist"} ({max(ss,ms):.0f}%) vs canonical 51%')
print(f'\n  VERDICT: {"CONFIRMED - build v16 (shortlist tags + maxcontext subtags)" if (max(st,mt)>62 or max(ss,ms)>52) else "single-pass was noise - canonical stays best"}')

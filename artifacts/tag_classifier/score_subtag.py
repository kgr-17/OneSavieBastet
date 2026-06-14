import json, io, re
from collections import Counter
def norm(s): return re.sub(r'\s+',' ',str(s).split(',')[0]).strip().lower()
hold=json.load(io.open('artifacts/tag_classifier/holdout.json',encoding='utf-8'))
spec=json.load(io.open('artifacts/tag_classifier/subtag_spec.json',encoding='utf-8'))
conf=json.load(io.open('artifacts/tag_classifier/confirm.json',encoding='utf-8'))
def plur(items):
    items=[norm(x) for x in items if x]; return Counter(items).most_common(1)[0][0] if items else None
n=len(hold); spec_ok=0; base_ok=0; spec_ok_tagright=0; tagright=0
for h in hold:
    ts=norm(h['truth_subtag'][0]) if h['truth_subtag'] else None
    tt=norm(h['truth_tag'][0]) if h['truth_tag'] else None
    # specialist subtag
    sp=plur(spec.get(str(h['id'])) or spec.get(h['id']) or [])
    # maxcontext baseline subtag
    mv=conf['maxcontext'].get(str(h['id'])) or conf['maxcontext'].get(h['id']) or []
    mb=plur([v['subtag'] for v in mv]); mtag=plur([v['tag'] for v in mv])
    if ts and sp==ts: spec_ok+=1
    if ts and mb==ts: base_ok+=1
    if tt and mtag==tt:
        tagright+=1
        if ts and sp==ts: spec_ok_tagright+=1
print('=== SUBTAG specialist vs maxcontext baseline (subtag) ===')
print(f'  maxcontext subtag : {100*base_ok/n:.0f}%')
print(f'  SPECIALIST subtag : {100*spec_ok/n:.0f}%')
print(f'  specialist subtag WHEN tag is correct: {100*spec_ok_tagright/tagright:.0f}% ({spec_ok_tagright}/{tagright})')
print(f'\n  VERDICT: {"SPECIALIST WINS - build v17 (maxcontext tags + specialist subtags)" if spec_ok>base_ok+1 else "no subtag win - 51% is the subtag ceiling"}')

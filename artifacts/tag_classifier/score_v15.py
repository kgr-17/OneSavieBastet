import json, io, re
from collections import Counter
def norm(s): return re.sub(r'\s+',' ',str(s)).strip().lower()
hold=json.load(io.open('artifacts/tag_classifier/holdout.json',encoding='utf-8'))
byPid=json.load(io.open('artifacts/tag_classifier/v15_holdout.json',encoding='utf-8'))
def plur(items):
    items=[x for x in items if x]
    return Counter(items).most_common(1)[0][0] if items else None
def fs(pred,truth):  # set field score
    ts={norm(x) for x in truth if str(x).strip()}; ps={norm(pred)} if pred else set()
    if not ts: return 0.0
    return max(0.0,(len(ps&ts)-0.5*len(ps-ts))/len(ts))
n=len(hold); te=se=0; tf=sf=0.0; miss=0
for h in hold:
    vs=byPid.get(str(h['id'])) or byPid.get(h['id']) or []
    if not vs: miss+=1
    pt=plur([v['tag'] for v in vs]); ps=plur([v['subtag'] for v in vs])
    if h['truth_tag'] and pt==norm(h['truth_tag'][0]): te+=1
    if h['truth_subtag'] and ps==norm(h['truth_subtag'][0]): se+=1
    tf+=fs(pt,h['truth_tag']); sf+=fs(ps,h['truth_subtag'])
print(f'received {n-miss}/{n}')
print('=== v15 improved classifier (3-pass plurality) on holdout ===')
print(f'              TAG        SUBTAG')
print(f'  naive-NN    24%        11%')
print(f'  generic 3p  59%        43%')
print(f'  v15 (two-stage+rich): TAG {100*te/n:.0f}%   SUBTAG {100*se/n:.0f}%')
print(f'  v15 field-score/finding: TAG {tf/n:.3f}  SUBTAG {sf/n:.3f}')
print(f'\n  >>> {"v15 WINS - apply to test, build v15" if (te/n>0.60 or se/n>0.46) else "no clear win over generic - subtag likely at ceiling"}')

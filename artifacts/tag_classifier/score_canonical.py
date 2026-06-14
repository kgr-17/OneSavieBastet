import json, io, re
from collections import Counter
def norm(s): return re.sub(r'\s+',' ',str(s)).strip().lower()
hold=json.load(io.open('artifacts/tag_classifier/holdout.json',encoding='utf-8'))
canon=json.load(io.open('artifacts/tag_classifier/holdout_canonical.json',encoding='utf-8'))
aligned={c['id']:c['aligned'] for c in canon}
byPid=json.load(io.open('artifacts/tag_classifier/canon_holdout.json',encoding='utf-8'))
def plur(items):
    items=[norm(x) for x in items if x]; return Counter(items).most_common(1)[0][0] if items else None
def acc(subset):
    te=se=0; n=0
    for h in subset:
        n+=1; vs=byPid.get(str(h['id'])) or byPid.get(h['id']) or []
        pt=plur([v['tag'] for v in vs]); ps=plur([v['subtag'] for v in vs])
        if h['truth_tag'] and pt==norm(h['truth_tag'][0]): te+=1
        if h['truth_subtag'] and ps==norm(h['truth_subtag'][0]): se+=1
    return (100*te/n if n else 0),(100*se/n if n else 0),n
allt,alls,n=acc(hold)
at,as_,na=acc([h for h in hold if aligned.get(h['id'])])
print('=== classify-from-CANONICAL-text (3-pass) vs generic short-desc ===')
print(f'  generic (short desc): TAG 59% / SUBTAG 43%')
print(f'  canonical ALL {n}:    TAG {allt:.0f}% / SUBTAG {alls:.0f}%')
print(f'  canonical ALIGNED {na} (real report text): TAG {at:.0f}% / SUBTAG {as_:.0f}%')
print(f'\n  >>> {"CANONICAL WINS on aligned rows -> use full report text for test classification" if at>61 else "no meaningful lift -> 59% is a true labeling-ambiguity ceiling, need teammate gold"}')

import json, io, re
from collections import Counter
def norm(s): return re.sub(r'\s+',' ',str(s)).strip().lower()
hold=json.load(io.open('artifacts/tag_classifier/holdout.json',encoding='utf-8'))
p1={p['id']:p for p in json.load(io.open('artifacts/tag_classifier/predictions.json',encoding='utf-8'))}  # pass1
extra=json.load(io.open('artifacts/tag_classifier/holdout_5pass.json',encoding='utf-8'))  # passes 2-5 byPid
# build 5 votes per id
votes={}
for h in hold:
    i=h['id']; v=[]
    if i in p1: v.append({'tag':p1[i]['tag'],'subtag':p1[i]['subtag']})
    for x in extra.get(str(i),extra.get(i,[])): v.append(x)
    votes[i]=v
def plur(items):
    if not items: return None
    return Counter(items).most_common(1)[0][0]
def acc(k):
    t=s=n=0
    for h in hold:
        n+=1; vs=votes[h['id']][:k]
        pt=plur([norm(x['tag']) for x in vs]); ps=plur([norm(x['subtag']) for x in vs])
        if h['truth_tag'] and pt==norm(h['truth_tag'][0]): t+=1
        if h['truth_subtag'] and ps==norm(h['truth_subtag'][0]): s+=1
    return 100*t/n,100*s/n
print('=== self-consistency curve (plurality of k passes) ===')
print(f'  naive-NN baseline: TAG 24% / SUBTAG 11%')
for k in [1,3,5]:
    t,s=acc(k); print(f'  {k}-pass plurality: TAG {t:.0f}% / SUBTAG {s:.0f}%')
print(f'\n  v13 used 3-pass. If 5-pass > 3-pass meaningfully, v15 is verified-better.')

import csv, json, io, re
from collections import Counter
byPid=json.load(io.open('artifacts/tag_classifier/maxcontext_apply.json',encoding='utf-8'))
vocab=json.load(io.open('artifacts/tag_classifier/vocab.json',encoding='utf-8'))
tagset={re.sub(r'\s+',' ',t).strip().lower():t for t in vocab['tags']}
subset={re.sub(r'\s+',' ',t).strip().lower():t for t in vocab['subtags']}
def ct(t): return tagset.get(re.sub(r'\s+',' ',str(t)).strip().lower(),str(t).strip())
def cs(s): return subset.get(re.sub(r'\s+',' ',str(s)).strip().lower(),str(s).strip())
def maj(items):
    c=Counter(items); top,n=c.most_common(1)[0]
    return top if (n>=2 and n>=0.6*len(items)) else None
v11=list(csv.DictReader(io.open('outputs/submission_c4_v11.csv',encoding='utf-8')))
tchg=schg=0
for row in v11:
    votes=byPid.get(str(row['Property'])) or byPid.get(row['Property'])
    if not votes: continue
    mt=maj([ct(v['tag']) for v in votes]); ms=maj([cs(v['subtag']) for v in votes])
    if mt and mt.lower()!=row['tag'].strip().lower(): row['tag']=mt; tchg+=1
    if ms and ms.lower()!=row['subtag'].strip().lower(): row['subtag']=ms; schg+=1
assert len(v11)==400
out='outputs/submission_c4_v16_maxcontext.csv'
with open(out,'w',newline='',encoding='utf-8') as f:
    w=csv.DictWriter(f,fieldnames=['Property','repo_path','severity','tag','subtag','description'])
    w.writeheader(); w.writerows(v11)
import hashlib
from collections import Counter as C
c0=C(r['repo_path'] for r in csv.DictReader(io.open('outputs/submission_c4_v11.csv',encoding='utf-8')))
c1=C(r['repo_path'] for r in v11)
v15={r['Property']:r for r in csv.DictReader(io.open('outputs/submission_c4_v15_canonical.csv',encoding='utf-8'))}
dt=sum(1 for r in v11 if r['tag'].strip().lower()!=v15[r['Property']]['tag'].strip().lower())
ds=sum(1 for r in v11 if r['subtag'].strip().lower()!=v15[r['Property']]['subtag'].strip().lower())
print(f'WROTE {out}')
print(f'  maxcontext overrides vs v11: tag {tchg} / subtag {schg}')
print(f'  differs from v15_canonical (471): tag {dt} rows / subtag {ds} rows')
print(f'  per-repo counts identical: {c0==c1} | sha {hashlib.sha256(open(out,"rb").read()).hexdigest()[:12]}')

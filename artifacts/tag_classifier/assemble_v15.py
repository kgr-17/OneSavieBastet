import csv, json, io, re
from collections import Counter
byPid=json.load(io.open('artifacts/tag_classifier/canon_apply.json',encoding='utf-8'))
vocab=json.load(io.open('artifacts/tag_classifier/vocab.json',encoding='utf-8'))
tagset={re.sub(r'\s+',' ',t).strip().lower():t for t in vocab['tags']}
subset={re.sub(r'\s+',' ',t).strip().lower():t for t in vocab['subtags']}
def ct(t): return tagset.get(re.sub(r'\s+',' ',str(t)).strip().lower(),str(t).strip())
def cs(s): return subset.get(re.sub(r'\s+',' ',str(s)).strip().lower(),str(s).strip())
# base = v11 (so canonical classifier fully replaces short-desc overrides on guessed rows)
v11=list(csv.DictReader(io.open('outputs/submission_c4_v11.csv',encoding='utf-8')))
def majority(items):
    c=Counter(items); top,n=c.most_common(1)[0]
    return top if (n>=2 and n>=0.6*len(items)) else None
tag_chg=sub_chg=0
for row in v11:
    votes=byPid.get(str(row['Property'])) or byPid.get(row['Property'])
    if not votes: continue
    mt=majority([ct(v['tag']) for v in votes]); ms=majority([cs(v['subtag']) for v in votes])
    if mt and mt.lower()!=row['tag'].strip().lower(): row['tag']=mt; tag_chg+=1
    if ms and ms.lower()!=row['subtag'].strip().lower(): row['subtag']=ms; sub_chg+=1
assert len(v11)==400
out='outputs/submission_c4_v15_canonical.csv'
with open(out,'w',newline='',encoding='utf-8') as f:
    w=csv.DictWriter(f,fieldnames=['Property','repo_path','severity','tag','subtag','description'])
    w.writeheader(); w.writerows(v11)
import hashlib
from collections import Counter as C
c0=C(r['repo_path'] for r in csv.DictReader(io.open('outputs/submission_c4_v11.csv',encoding='utf-8')))
c1=C(r['repo_path'] for r in v11)
# how many differ from v13?
v13={r['Property']:r for r in csv.DictReader(io.open('outputs/submission_c4_v13_retag.csv',encoding='utf-8'))}
difft=sum(1 for r in v11 if r['tag'].strip().lower()!=v13[r['Property']]['tag'].strip().lower())
diffs=sum(1 for r in v11 if r['subtag'].strip().lower()!=v13[r['Property']]['subtag'].strip().lower())
print(f'WROTE {out}')
print(f'  canonical overrides vs v11: tag {tag_chg} / subtag {sub_chg}')
print(f'  differs from v13: tag {difft} rows / subtag {diffs} rows  (the canonical refinement)')
print(f'  per-repo counts identical: {c0==c1}')
print(f'  sha256: {hashlib.sha256(open(out,"rb").read()).hexdigest()[:16]}')

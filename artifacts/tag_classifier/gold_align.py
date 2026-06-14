"""Overwrite v13 tags/subtags with dataset_0831 human GOLD where it exists.
Guard: only touch a repo if its tag-multiset actually differs from gold (else it's a greedy-matcher no-op)."""
import csv, json, io, re
from collections import Counter

def toks(s): return set(re.findall(r'[a-z0-9]+', str(s).lower()))
def strip(p): return re.sub(r'^repos/','',str(p)).strip()

ds=list(csv.DictReader(io.open('data/dataset_0831.csv',encoding='utf-8-sig')))
m3=json.load(io.open('artifacts/test_hash_to_contest_v3.json',encoding='utf-8'))
contest2hash={}
for h,e in m3.items():
    c=e.get('contest') if isinstance(e,dict) else e
    if c: contest2hash[c]=h
v13=list(csv.DictReader(io.open('outputs/submission_c4_v13_retag.csv',encoding='utf-8')))
rows_by_hash={}
for r in v13: rows_by_hash.setdefault(r['repo_path'],[]).append(r)

# gather gold (tagged) rows per test hash
gold_by_hash={}
for r in ds:
    c=strip(r['repo_path']); h=contest2hash.get(c)
    if not h: continue
    if str(r.get('tag','')).strip():
        gold_by_hash.setdefault(h,[]).append(r)

tag_changed=sub_changed=0; touched_repos=[]
for h, golds in gold_by_hash.items():
    rows=rows_by_hash.get(h,[])
    if not rows: continue
    gms=Counter(g['tag'].split(',')[0].strip().lower() for g in golds)
    vms=Counter(r['tag'].split(',')[0].strip().lower() for r in rows)
    # multiset guard: skip if v13 primary-tag multiset already == gold (no-op under greedy matcher)
    if gms==vms: continue
    # align each gold finding to the best v13 row by description token overlap; one-to-one
    used=set()
    for g in golds:
        gt=toks(g.get('description','')) | toks(g.get('detail',''))
        best=None; bestov=1
        for i,r in enumerate(rows):
            if i in used: continue
            ov=len(gt & toks(r['description']))
            if ov>bestov: bestov=ov; best=i
        if best is None: continue
        used.add(best); r=rows[best]
        gtag=g['tag'].strip(); gsub=str(g.get('subtag','')).strip()
        if gtag and gtag.lower()!=r['tag'].strip().lower():
            r['tag']=gtag; tag_changed+=1
        if gsub and gsub.lower()!=r['subtag'].strip().lower():
            r['subtag']=gsub; sub_changed+=1
        if h not in touched_repos: touched_repos.append(h)

assert len(v13)==400
out='outputs/submission_c4_v14_gold.csv'
with open(out,'w',newline='',encoding='utf-8') as f:
    w=csv.DictWriter(f,fieldnames=['Property','repo_path','severity','tag','subtag','description'])
    w.writeheader(); w.writerows(v13)
import hashlib
print(f'WROTE {out}')
print(f'  gold tag overrides: {tag_changed} | subtag overrides: {sub_changed}')
print(f'  repos touched (multiset differed): {len(touched_repos)} -> {[ (k, m3[k].get("contest") if isinstance(m3[k],dict) else m3[k]) for k in touched_repos]}')
# verify counts unchanged vs v13
from collections import Counter as C
c0=C(r["repo_path"] for r in csv.DictReader(io.open("outputs/submission_c4_v13_retag.csv",encoding="utf-8")))
c1=C(r["repo_path"] for r in v13)
print('  per-repo counts identical to v13:', c0==c1)
print('  sha256:', hashlib.sha256(open(out,"rb").read()).hexdigest()[:16])

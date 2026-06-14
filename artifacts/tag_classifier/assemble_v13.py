import csv, json, io, re
from collections import Counter

byPid = json.load(io.open('artifacts/tag_classifier/predictions_apply.json', encoding='utf-8'))
vocab = json.load(io.open('artifacts/tag_classifier/vocab.json', encoding='utf-8'))
tagset = {re.sub(r'\s+',' ',t).strip().lower(): t for t in vocab['tags']}
subset = {re.sub(r'\s+',' ',t).strip().lower(): t for t in vocab['subtags']}
def canon_tag(t):
    k=re.sub(r'\s+',' ',str(t)).strip().lower(); return tagset.get(k, str(t).strip())
def canon_sub(s):
    k=re.sub(r'\s+',' ',str(s)).strip().lower(); return subset.get(k, str(s).strip())

v11 = list(csv.DictReader(io.open('outputs/submission_c4_v11.csv', encoding='utf-8')))

def majority(items):
    c = Counter(items)
    top, n = c.most_common(1)[0]
    return top if (n >= 2 and n >= 0.6 * len(items)) else None

tag_changed = sub_changed = 0
for row in v11:
    pid = row['Property']
    votes = byPid.get(str(pid)) or byPid.get(int(pid)) or byPid.get(pid)
    if not votes:
        continue
    tags = [canon_tag(v['tag']) for v in votes]
    subs = [canon_sub(v['subtag']) for v in votes]
    mt = majority(tags)   # clear >=2/3 majority
    ms = majority(subs)
    if mt and mt.lower() != row['tag'].strip().lower():
        row['tag'] = mt; tag_changed += 1
    if ms and ms.lower() != row['subtag'].strip().lower():
        row['subtag'] = ms; sub_changed += 1

# sanity: still 400 rows, counts unchanged
assert len(v11) == 400
out = 'outputs/submission_c4_v13_retag.csv'
with open(out, 'w', newline='', encoding='utf-8') as f:
    w = csv.DictWriter(f, fieldnames=['Property','repo_path','severity','tag','subtag','description'])
    w.writeheader(); w.writerows(v11)
import hashlib
print(f'WROTE {out}')
print(f'  tag overrides (>=2/3 ensemble agree & differs from v11): {tag_changed}')
print(f'  subtag overrides: {sub_changed}')
print(f'  rows unchanged: {400 - tag_changed} (tag)')
print(f'  sha256: {hashlib.sha256(open(out,"rb").read()).hexdigest()[:16]}')
# per-repo count unchanged check
from collections import Counter as C
c0=C(r["repo_path"] for r in csv.DictReader(io.open("outputs/submission_c4_v11.csv",encoding="utf-8")))
c1=C(r["repo_path"] for r in v11)
print('  per-repo counts identical to v11:', c0==c1)

"""Build a candidate from the OneSavie-rubric code classification: apply high-conf
(>=0.8) corrections onto the v50 base (current best 481.21), hp rows protected.
Then it's scored by local_eval.py against independent gold before any submit.
"""
import csv, json, re
from collections import Counter

ROOT = '/Users/yixuliu/OneSavieBastet'


def n1(s):
    return re.sub(r'\s+', ' ', str(s).split(',')[0]).strip().lower()


vocab = json.load(open(f'{ROOT}/artifacts/tag_classifier/vocab.json'))
tcanon = {n1(t): t for t in vocab['tags']}
scanon = {re.sub(r'\s+', ' ', t).strip().lower(): t for t in vocab['subtags']}
ct = lambda t: tcanon.get(n1(t), str(t).strip())
cs = lambda s: scanon.get(re.sub(r'\s+', ' ', str(s)).strip().lower(), str(s).strip())

preds = {str(p['id']): p for p in json.load(open(f'{ROOT}/finetune/teacher/rubric_preds.json'))}
base = list(csv.DictReader(open(f'{ROOT}/outputs/submission_c4_v50_v49_plus216.csv', encoding='utf-8-sig')))
bd = {r['Property']: r for r in base}
v34 = {r['Property']: r for r in csv.DictReader(open(f'{ROOT}/data_history/submission_c4_v34_teacher_all_479.27.csv', encoding='utf-8-sig'))}
ref = {r['Property']: r for r in csv.DictReader(open(f'{ROOT}/data_history/submission_c4_v34_teacher_all_retagged_correction_hp_479.96.csv', encoding='utf-8-sig'))}
hp = {p for p in ref if n1(ref[p]['tag']) != n1(v34[p]['tag']) or n1(ref[p]['subtag']) != n1(v34[p]['subtag'])}

CONF = 0.80
cand = [dict(r) for r in base]
tc = sc = 0
changes = []
for r in cand:
    P = r['Property']
    p = preds.get(P)
    if not p or P in hp:
        continue
    try:
        c = float(p.get('confidence', 0))
    except Exception:
        c = 0
    if c < CONF:
        continue
    if n1(p['tag']) and n1(p['tag']) != n1(r['tag']):
        changes.append((P, r['tag'], ct(p['tag'])))
        r['tag'] = ct(p['tag']); tc += 1
    if n1(p['subtag']) and n1(p['subtag']) != n1(r['subtag']):
        r['subtag'] = cs(p['subtag']); sc += 1
out = f'{ROOT}/outputs/submission_c4_v53_rubric.csv'
w = csv.DictWriter(open(out, 'w', newline='', encoding='utf-8'),
                   fieldnames=['Property', 'repo_path', 'severity', 'tag', 'subtag', 'description'])
w.writeheader(); w.writerows(cand)
dist = Counter(n1(r['tag']) for r in cand if r['tag'].strip())
nt = sum(dist.values())
print(f"rubric preds: {len(preds)}/289")
print(f"v53 = v50 + {tc} tag + {sc} subtag rubric corrections (conf>=0.8, hp protected) -> {out}")
print(f"DoS share: {100*dist.get('dos',0)/nt:.1f}% (gold 20.1, base 19.8)")
print("sample tag corrections:")
for P, old, new in changes[:12]:
    print(f"  pid {P}: {old} -> {new}")

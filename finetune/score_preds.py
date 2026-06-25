"""Grade a workflow's holdout predictions vs truth (majority-vote over any passes).
Usage: python score_preds.py <workflow_output_file> [label]
"""
import json, re, sys
from collections import Counter, defaultdict

ROOT = '/Users/yixuliu/OneSavieBastet'


def norm(s):
    return re.sub(r'\s+', ' ', str(s).split(',')[0]).strip().lower()


truth = {str(t['id']): t for t in json.load(open(f'{ROOT}/finetune/teacher/holdout_truth.json'))}

raw = open(sys.argv[1]).read()
i = raw.find('{')
obj = json.loads(raw[i:])
res = obj.get('result', obj)
preds = res['preds']

bytag, bysub = defaultdict(list), defaultdict(list)
for p in preds:
    bytag[str(p['id'])].append(norm(p['tag']))
    bysub[str(p['id'])].append(norm(p['subtag']))


def maj(xs):
    return Counter(xs).most_common(1)[0][0] if xs else ''


tc = sc = n = 0
for tid, t in truth.items():
    if tid not in bytag:
        continue
    n += 1
    tc += int(maj(bytag[tid]) == norm(t['tag']))
    sc += int(maj(bysub[tid]) == norm(t['subtag']))
label = sys.argv[2] if len(sys.argv) > 2 else 'model'
print(f"{label}: n={n}/153  TAG {100*tc/n:.1f}  SUB {100*sc/n:.1f}   (maxcontext 72.5 / 56.2)")

"""Score the strong-LLM teacher on the holdout (vs maxcontext 72.5/56.2) and
build aggressive relabel submissions from its 289-row test predictions.
Input: finetune/teacher/result.json = {holdout:[{id,tag,subtag}], test:[...]}.
"""
import csv, json, re, sys
from collections import Counter

ROOT = '/Users/yixuliu/OneSavieBastet'


def norm(s):
    return re.sub(r'\s+', ' ', str(s).split(',')[0]).strip().lower()


res = json.load(open(f'{ROOT}/finetune/teacher/result.json'))
truth = {str(t['id']): t for t in json.load(open(f'{ROOT}/finetune/teacher/holdout_truth.json'))}
hold_pred = {str(p['id']): p for p in res['holdout']}
test_pred = {str(p['id']): p for p in res['test']}

# --- holdout accuracy (score_confirm metric) ---
tc = sc = n = 0
for tid, t in truth.items():
    p = hold_pred.get(tid)
    if not p:
        continue
    n += 1
    tc += int(norm(p['tag']) == norm(t['tag']))
    sc += int(norm(p['subtag']) == norm(t['subtag']))
print(f"=== TEACHER on holdout (n={n}/153) ===")
print(f"  TAG  {100*tc/n:.1f}   (maxcontext 72.5)")
print(f"  SUB  {100*sc/n:.1f}   (maxcontext 56.2)")
print(f"  coverage: {len(hold_pred)}/153 holdout, {len(test_pred)}/289 test predicted")

# --- build aggressive variants on ee25fix base ---
base = list(csv.DictReader(open(f'{ROOT}/outputs/submission_c4_v16_ee25fix.csv', encoding='utf-8-sig')))
vocab = json.load(open(f'{ROOT}/artifacts/tag_classifier/vocab.json'))
tagcanon = {norm(t): t for t in vocab['tags']}
subcanon = {re.sub(r'\s+', ' ', t).strip().lower(): t for t in vocab['subtags']}


def canon_tag(t):
    return tagcanon.get(norm(t), str(t).strip())


def canon_sub(s):
    return subcanon.get(re.sub(r'\s+', ' ', str(s)).strip().lower(), str(s).strip())


def build(name, mode):
    rows = [dict(r) for r in base]
    tchg = schg = 0
    for r in rows:
        p = test_pred.get(r['Property'])
        if not p:
            continue
        nt, ns = canon_tag(p['tag']), canon_sub(p['subtag'])
        if mode in ('all', 'tag') and nt and norm(nt) != norm(r['tag']):
            r['tag'] = nt; tchg += 1
        if mode in ('all', 'subtag') and ns and norm(ns) != norm(r['subtag']):
            r['subtag'] = ns; schg += 1
    out = f'{ROOT}/outputs/{name}.csv'
    with open(out, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=['Property', 'repo_path', 'severity', 'tag', 'subtag', 'description'])
        w.writeheader(); w.writerows(rows)
    c0 = Counter(r['repo_path'] for r in base); c1 = Counter(r['repo_path'] for r in rows)
    print(f"  {name}: tag {tchg} / subtag {schg} changes | counts_ok={c0==c1}")
    return out


print("\n=== aggressive variants (base=ee25fix 475.07) ===")
build('submission_c4_v34_teacher_all', 'all')
build('submission_c4_v35_teacher_tagonly', 'tag')
build('submission_c4_v36_teacher_subonly', 'subtag')

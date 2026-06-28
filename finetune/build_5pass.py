"""Build relabel candidates from the 5-pass teacher ensemble on top of the 479.96
base (= v34 + 13 human hand-corrections). Apply majority-vote corrections where
>=thr/5 passes agree AND differ from the base — but NEVER override the 13 human
hand-corrected rows (the human beat the model there, worth +0.68). Holds for review.
"""
import csv, json, re
from collections import Counter, defaultdict

ROOT = '/Users/yixuliu/OneSavieBastet'


def n1(s):
    return re.sub(r'\s+', ' ', str(s).split(',')[0]).strip().lower()


preds = json.load(open(f'{ROOT}/finetune/teacher/5pass_preds.json'))
vocab = json.load(open(f'{ROOT}/artifacts/tag_classifier/vocab.json'))
tcanon = {n1(t): t for t in vocab['tags']}
scanon = {re.sub(r'\s+', ' ', t).strip().lower(): t for t in vocab['subtags']}
ct = lambda t: tcanon.get(n1(t), str(t).strip())
cs = lambda s: scanon.get(re.sub(r'\s+', ' ', str(s)).strip().lower(), str(s).strip())

# the 13 human hand-corrected rows (hp vs v34) — protect these
hp = {r['Property']: r for r in csv.DictReader(open(f'{ROOT}/outputs/base_479.96.csv', encoding='utf-8-sig'))}
v34 = {r['Property']: r for r in csv.DictReader(open(f'{ROOT}/data_history/submission_c4_v34_teacher_all_479.27.csv', encoding='utf-8-sig'))}
prot_tag = {p for p in hp if n1(hp[p]['tag']) != n1(v34[p]['tag'])}
prot_sub = {p for p in hp if n1(hp[p]['subtag']) != n1(v34[p]['subtag'])}
print(f"protected human-corrected rows: {len(prot_tag)} tag, {len(prot_sub)} subtag")

tv, sv = defaultdict(list), defaultdict(list)
for p in preds:
    tv[str(p['id'])].append(n1(p['tag']))
    sv[str(p['id'])].append(n1(p['subtag']))


def maj(xs):
    top, n = Counter(xs).most_common(1)[0]
    return top, n


base = list(csv.DictReader(open(f'{ROOT}/outputs/base_479.96.csv', encoding='utf-8-sig')))


def build(name, thr):
    rows = [dict(r) for r in base]
    tc = sc = 0
    for r in rows:
        p = r['Property']
        if p in tv and p not in prot_tag:
            t, n = maj(tv[p])
            if n >= thr and t != n1(r['tag']):
                r['tag'] = ct(t); tc += 1
        if p in sv and p not in prot_sub:
            s, n = maj(sv[p])
            if n >= thr and s != n1(r['subtag']):
                r['subtag'] = cs(s); sc += 1
    out = f'{ROOT}/outputs/{name}.csv'
    w = csv.DictWriter(open(out, 'w', newline='', encoding='utf-8'),
                       fieldnames=['Property', 'repo_path', 'severity', 'tag', 'subtag', 'description'])
    w.writeheader(); w.writerows(rows)
    print(f"{name}: {tc} tag + {sc} subtag corrections vs 479.96 base (>= {thr}/5 consensus, hp rows protected)")


print(f"5-pass coverage: {len(tv)} rows, votes/row ~ {len(preds)/max(1,len(tv)):.1f}")
build('submission_c4_v43_5pass_unanimous', 5)
build('submission_c4_v44_5pass_ge4', 4)
build('submission_c4_v45_5pass_ge3', 3)

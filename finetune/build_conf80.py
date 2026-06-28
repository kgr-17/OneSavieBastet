"""Confidence-gated relabel: apply a correction to the 479.96 base only when
>80% of the 6 model opinions (5 teacher passes + source-code) agree on a label
different from the current best. hp rows protected. Plus a DoS-skew sanity check.
"""
import csv, json, re
from collections import Counter, defaultdict

ROOT = '/Users/yixuliu/OneSavieBastet'


def n1(s):
    return re.sub(r'\s+', ' ', str(s).split(',')[0]).strip().lower()


vocab = json.load(open(f'{ROOT}/artifacts/tag_classifier/vocab.json'))
tcanon = {n1(t): t for t in vocab['tags']}
scanon = {re.sub(r'\s+', ' ', t).strip().lower(): t for t in vocab['subtags']}
ct = lambda t: tcanon.get(n1(t), str(t).strip())
cs = lambda s: scanon.get(re.sub(r'\s+', ' ', str(s)).strip().lower(), str(s).strip())

base = list(csv.DictReader(open(f'{ROOT}/outputs/base_479.96.csv', encoding='utf-8-sig')))
bd = {r['Property']: r for r in base}
v34 = {r['Property']: r for r in csv.DictReader(open(f'{ROOT}/data_history/submission_c4_v34_teacher_all_479.27.csv', encoding='utf-8-sig'))}
hp = {p for p in bd if n1(bd[p]['tag']) != n1(v34[p]['tag']) or n1(bd[p]['subtag']) != n1(v34[p]['subtag'])}

preds = json.load(open(f'{ROOT}/finetune/teacher/5pass_preds.json'))
sc = {str(p['id']): p for p in json.load(open(f'{ROOT}/finetune/teacher/srccode_test_preds.json'))}
tvotes, svotes = defaultdict(list), defaultdict(list)
for p in preds:
    tvotes[str(p['id'])].append(n1(p['tag']))
    svotes[str(p['id'])].append(n1(p['subtag']))
for P, p in sc.items():
    tvotes[P].append(n1(p['tag']))
    svotes[P].append(n1(p['subtag']))


def conf(votes):
    if not votes:
        return None, 0.0
    lab, n = Counter(votes).most_common(1)[0]
    return lab, n / len(votes)


THRESH = 0.80
rows = [dict(r) for r in base]
tc = scnt = c6 = 0
for r in rows:
    P = r['Property']
    if P in hp:
        continue
    lt, ctf = conf(tvotes.get(P, []))
    if lt and ctf > THRESH and lt != n1(r['tag']):
        r['tag'] = ct(lt); tc += 1
        if ctf == 1.0:
            c6 += 1
    ls, csf = conf(svotes.get(P, []))
    if ls and csf > THRESH and ls != n1(r['subtag']):
        r['subtag'] = cs(ls); scnt += 1

out = f'{ROOT}/outputs/submission_c4_v48_conf80.csv'
w = csv.DictWriter(open(out, 'w', newline='', encoding='utf-8'),
                   fieldnames=['Property', 'repo_path', 'severity', 'tag', 'subtag', 'description'])
w.writeheader(); w.writerows(rows)

dist = Counter(n1(r['tag']) for r in rows if r['tag'].strip())
n = sum(dist.values())
dos = 100 * dist.get('dos', 0) / n
verdict = 'OVER-tags DoS (regression risk, like v46)' if dos > 20.5 else 'calibrated'
print(f"v48_conf80: {tc} tag + {scnt} subtag corrections vs 479.96 base (>80% of 6 votes agree; hp protected)")
print(f"  tag corrections: {c6} are 6/6 unanimous, {tc - c6} are 5/6")
print(f"  resulting DoS share: {dos:.1f}% (gold 20.1, base 19.8) -> {verdict}")

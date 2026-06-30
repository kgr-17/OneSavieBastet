"""Apply fresh git-correct report-grounded tag/subtag corrections to the v59 best
base. Conservative: only confidence >= THRESH and differs from current; protect
git-fixed + gold rows; DoS-skew guard (the failure mode of v46/v48).
"""
import csv, json, re, sys
from collections import Counter

ROOT = '/Users/yixuliu/OneSavieBastet'
THRESH = float(sys.argv[1]) if len(sys.argv) > 1 else 0.85


def n1(s):
    return re.sub(r'\s+', ' ', str(s).split(',')[0]).strip().lower()


vocab = json.load(open(f'{ROOT}/artifacts/tag_classifier/vocab.json'))
tcanon = {n1(t): t for t in vocab['tags']}
scanon = {re.sub(r'\s+', ' ', t).strip().lower(): t for t in vocab['subtags']}
ct = lambda t: tcanon.get(n1(t), str(t).strip())
cs = lambda s: scanon.get(re.sub(r'\s+', ' ', str(s)).strip().lower(), str(s).strip())

preds = {str(p['id']): p for p in json.load(open(f'{ROOT}/finetune/teacher/gittag_preds.json'))}
base = list(csv.DictReader(open(f'{ROOT}/outputs/submission_c4_v59_gitfix_descrewrite.csv', encoding='utf-8-sig')))
PROTECT = {'158', '160', '211', '215', '220', '227', '229', '216', '286', '309'}

out = [dict(r) for r in base]
tchg = schg = 0
changes = []
for r in out:
    P = r['Property']
    p = preds.get(P)
    if not p or P in PROTECT:
        continue
    try:
        c = float(p.get('confidence', 0))
    except Exception:
        c = 0
    if c < THRESH:
        continue
    if n1(p['tag']) and n1(p['tag']) != n1(r['tag']):
        changes.append((P, r['tag'], ct(p['tag']), round(c, 2)))
        r['tag'] = ct(p['tag']); tchg += 1
    if n1(p['subtag']) and n1(p['subtag']) != n1(r['subtag']):
        r['subtag'] = cs(p['subtag']); schg += 1

out_path = f'{ROOT}/outputs/submission_c4_v63_gittag.csv'
w = csv.DictWriter(open(out_path, 'w', newline='', encoding='utf-8'),
                   fieldnames=['Property', 'repo_path', 'severity', 'tag', 'subtag', 'description'])
w.writeheader(); w.writerows(out)

dist = Counter(n1(r['tag']) for r in out if r['tag'].strip())
nt = sum(dist.values())
dos = 100 * dist.get('dos', 0) / nt
print(f"v63 git-correct tag pass (conf>={THRESH}): {tchg} tag + {schg} subtag corrections vs v59")
print(f"  DoS share: {dos:.1f}% (gold 20.1, v59 ~19.8) -> {'OVER-tags DoS (risk, like v46/v48)' if dos > 21 else 'calibrated OK'}")
print(f"  sample tag corrections:")
for P, o, nw, c in changes[:12]:
    print(f"    P{P}: {o} -> {nw} (conf {c})")

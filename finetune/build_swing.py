"""Aggressive coverage swing on the v58 git-fix base: drop the N lowest-value rows
(lowest canonical match = likely version-drift/weak, NOT the git-fixed or gold rows)
and add N classified canonical findings to the deepest-deficit repos.
"""
import csv, json, re, sys
from collections import defaultdict, Counter

ROOT = '/Users/yixuliu/OneSavieBastet'
N = int(sys.argv[1]) if len(sys.argv) > 1 else 18


def n1(s):
    return re.sub(r'\s+', ' ', str(s).split(',')[0]).strip().lower()


vocab = json.load(open(f'{ROOT}/artifacts/tag_classifier/vocab.json'))
tcanon = {n1(t): t for t in vocab['tags']}
scanon = {re.sub(r'\s+', ' ', t).strip().lower(): t for t in vocab['subtags']}
ct = lambda t: tcanon.get(n1(t), str(t).strip())
cs = lambda s: scanon.get(re.sub(r'\s+', ' ', str(s)).strip().lower(), str(s).strip())

pool = json.load(open(f'{ROOT}/finetune/teacher/swing_pool.json'))
adds_all = pool['adds']
preds = {p['idx']: p for p in json.load(open(f'{ROOT}/finetune/teacher/swing_preds.json'))}
for i, a in enumerate(adds_all):
    a['tag'] = preds.get(i, {}).get('tag', 'Logic error')
    a['subtag'] = preds.get(i, {}).get('subtag', 'Bad Condition')

# PROTECT: git-fixed rows + gold rows + best report-grounded rows
PROTECT = {'158', '160', '211', '215', '220', '227', '229',  # v58 git-fix
           '216', '286', '309',                                # gold
           '186', '313', '276', '205', '262', '288', '245'}    # strong report-grounded
# NEVER empty a repo: count rows per repo, only drop from repos with >=3 rows
_base = list(csv.DictReader(open(f'{ROOT}/outputs/submission_c4_v58_gitfix.csv', encoding='utf-8-sig')))
_repo_of = {r['Property']: r['repo_path'] for r in _base}
_rc = Counter(r['repo_path'] for r in _base)
drop_props, _per_repo_drops = [], Counter()
for d in pool['drops']:
    P = d[0]
    if P in PROTECT:
        continue
    h = _repo_of.get(P)
    # keep at least 2 rows per repo after dropping
    if _rc[h] - _per_repo_drops[h] <= 2:
        continue
    drop_props.append(P); _per_repo_drops[h] += 1
    if len(drop_props) >= N:
        break

# adds: prefer High severity, diversify across deficit contests, cap popcorn
adds = sorted(adds_all, key=lambda a: (a['severity'] != 'High',))
pick, per = [], Counter()
for a in adds:
    if per[a['contest']] >= 14:
        continue
    pick.append(a); per[a['contest']] += 1
    if len(pick) >= N:
        break

base = list(csv.DictReader(open(f'{ROOT}/outputs/submission_c4_v58_gitfix.csv', encoding='utf-8-sig')))
out = [dict(r) for r in base if r['Property'] not in set(drop_props)]
for a, P in zip(pick, sorted(drop_props, key=int)):
    out.append({'Property': P, 'repo_path': a['hash'], 'severity': a['severity'],
                'tag': ct(a['tag']), 'subtag': cs(a['subtag']), 'description': a['desc'][:450]})
out.sort(key=lambda r: int(r['Property']))
o = f'{ROOT}/outputs/submission_c4_v60_bigswing.csv'
w = csv.DictWriter(open(o, 'w', newline='', encoding='utf-8'),
                   fieldnames=['Property', 'repo_path', 'severity', 'tag', 'subtag', 'description'])
w.writeheader(); w.writerows(out)
print(f"v60 BIG SWING: dropped {len(drop_props)} lowest-value rows, added {len(pick)} canonical findings")
print(f"  drops: {sorted(drop_props, key=int)}")
print(f"  adds by contest: {dict(Counter(a['contest'] for a in pick))}")
print(f"  rows={len(out)}")

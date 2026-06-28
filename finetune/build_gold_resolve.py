"""Auto-resolve the clear gold matches in the tight sheet:
for each guessed row whose contest has dataset_0831 gold, if a gold option's
primary subtag corroborates the row (== current or teacher subtag) and the gold
TAG differs from current, apply the gold tag (proven v33 method). Protect the 13
validated hp corrections (flag gold-vs-human conflicts instead of overriding).
Builds a verifiable gold-backed candidate + shrinks the human list to the rest.
"""
import csv, json, re, os
from collections import Counter, defaultdict

ROOT = '/Users/yixuliu/OneSavieBastet'


def n1(s):
    return re.sub(r'\s+', ' ', str(s).split(',')[0]).strip().lower()


def pk(c):
    c = re.sub(r'^\s*20\d\d-\d\d-', '', str(c).strip().lower())
    t = [x for x in re.split(r'[-_]', c) if x]
    return t[0] if t else ''


def audit_of(rp):
    for seg in str(rp).replace('\\', '/').split('/'):
        if len(seg) >= 7 and seg[:2] == '20' and '-' in seg:
            return seg
    return ''


vocab = json.load(open(f'{ROOT}/artifacts/tag_classifier/vocab.json'))
tcanon = {n1(t): t for t in vocab['tags']}
scanon = {re.sub(r'\s+', ' ', t).strip().lower(): t for t in vocab['subtags']}
ct = lambda t: tcanon.get(n1(t), str(t).strip())

base_rows = list(csv.DictReader(open(f'{ROOT}/outputs/base_479.96.csv', encoding='utf-8-sig')))
base = {r['Property']: r for r in base_rows}
v34 = {r['Property']: r for r in csv.DictReader(open(f'{ROOT}/data_history/submission_c4_v34_teacher_all_479.27.csv', encoding='utf-8-sig'))}
hp_rows = {p for p in base if n1(base[p]['tag']) != n1(v34[p]['tag']) or n1(base[p]['subtag']) != n1(v34[p]['subtag'])}
sheet = {r['Property']: r for r in csv.DictReader(open(f'{ROOT}/artifacts/teammate_labeling_sheet.csv', encoding='utf-8-sig'))}
preds = json.load(open(f'{ROOT}/finetune/teacher/5pass_preds.json'))
tsub = defaultdict(list)
for p in preds:
    tsub[str(p['id'])].append(n1(p['subtag']))

ds = [r for r in csv.DictReader(open(f'{ROOT}/data/dataset_0831.csv', encoding='utf-8-sig'))
      if r['status'].strip() == 'Done' and r['tag'].strip() and r['subtag'].strip()]
gold = defaultdict(list)
for r in ds:
    gold[pk(audit_of(r['repo_path']))].append((r['tag'].strip(), r['subtag'].strip()))

resolved, conflicts, used = {}, [], defaultdict(set)
for P, srow in sheet.items():
    contest = srow.get('contest', '').strip()
    if not contest or contest == '(unmapped)' or P not in base:
        continue
    golds = gold.get(pk(contest))
    if not golds:
        continue
    cur_t, cur_s = n1(base[P]['tag']), n1(base[P]['subtag'])
    tsubmaj = Counter(tsub.get(P, [])).most_common(1)[0][0] if tsub.get(P) else ''
    # find a gold option whose subtag corroborates this row (matches current OR teacher subtag)
    for i, (gt, gs) in enumerate(golds):
        if i in used[pk(contest)]:
            continue
        if n1(gs) in (cur_s, tsubmaj) and n1(gt) != cur_t:
            used[pk(contest)].add(i)
            if P in hp_rows:
                conflicts.append((P, base[P]['tag'], ct(gt), gs))   # gold disagrees with human hp -> flag, don't auto-apply
            else:
                resolved[P] = (ct(gt), gs)
            break

# build candidate: base + auto-resolved gold (non-hp rows only)
cand = [dict(r) for r in base_rows]
for r in cand:
    if r['Property'] in resolved:
        r['tag'], r['subtag'] = resolved[r['Property']]
out = f'{ROOT}/outputs/submission_c4_v47_goldresolve.csv'
w = csv.DictWriter(open(out, 'w', newline='', encoding='utf-8'),
                   fieldnames=['Property', 'repo_path', 'severity', 'tag', 'subtag', 'description'])
w.writeheader(); w.writerows(cand)

print(f"AUTO-RESOLVED (gold-backed, subtag-corroborated, non-hp): {len(resolved)} rows -> {out}")
for P, (gt, gs) in sorted(resolved.items(), key=lambda x: int(x[0])):
    print(f"  pid {P} [{sheet[P]['contest']}]: {base[P]['tag']!r}/{base[P]['subtag']!r} -> {gt!r}/{gs!r}")
print(f"\nGOLD-vs-HUMAN CONFLICTS (gold disagrees with a validated hp correction -> YOUR call, not auto-applied): {len(conflicts)}")
for P, cur, gt, gs in conflicts:
    print(f"  pid {P} [{sheet[P]['contest']}]: current(hp)={cur!r}  vs  gold={gt!r}/{gs!r}")
print(f"\nv47 candidate = 479.96 base + {len(resolved)} verified-gold corrections (pure-label).")
print(f"Remaining human-pick rows (report-only, no gold) stay in GOLD_SHEET_TIGHT.csv.")

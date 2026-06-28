"""Cross-method consensus candidate (the most defensible, for scarce submissions).
For each guessed row, gather the tag proposed by 3 INDEPENDENT methods:
  M1 report-grounded (read the C4 report)   -- proven +1.24 live
  M2 rubric code-detection (OneSavie criteria + code)
  M3 dataset_0831 human gold (subtag-aligned)
Apply a correction to v50 ONLY when >=2 independent methods AGREE on a tag that
differs from the current best (and hp rows protected). Maximally conservative ->
each change has multi-method support. Then local_eval gates it vs v50 on gold.
"""
import csv, json, re
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
cs = lambda s: scanon.get(re.sub(r'\s+', ' ', str(s)).strip().lower(), str(s).strip())

base = list(csv.DictReader(open(f'{ROOT}/outputs/submission_c4_v50_v49_plus216.csv', encoding='utf-8-sig')))
bd = {r['Property']: r for r in base}
v34 = {r['Property']: r for r in csv.DictReader(open(f'{ROOT}/data_history/submission_c4_v34_teacher_all_479.27.csv', encoding='utf-8-sig'))}
ref = {r['Property']: r for r in csv.DictReader(open(f'{ROOT}/data_history/submission_c4_v34_teacher_all_retagged_correction_hp_479.96.csv', encoding='utf-8-sig'))}
hp = {p for p in ref if n1(ref[p]['tag']) != n1(v34[p]['tag']) or n1(ref[p]['subtag']) != n1(v34[p]['subtag'])}
sheet = {r['Property']: r for r in csv.DictReader(open(f'{ROOT}/artifacts/teammate_labeling_sheet.csv', encoding='utf-8-sig'))}

# M1 report-grounded (both passes), conf>=0.8
M1 = {}
for f in ['report_grounded_preds.json', 'report_grounded_preds2.json']:
    for p in json.load(open(f'{ROOT}/finetune/teacher/{f}')):
        try:
            c = float(p.get('confidence', 0))
        except Exception:
            c = 0
        if c >= 0.8:
            M1[str(p['Property'])] = (n1(p['tag']), p['tag'], p['subtag'])

# M2 rubric code-detection (use full set if present, else partial), conf>=0.8
import os
rub_path = f'{ROOT}/finetune/teacher/rubric_preds.json'
if not os.path.exists(rub_path):
    rub_path = f'{ROOT}/finetune/teacher/rubric_preds_partial.json'
M2 = {}
for p in json.load(open(rub_path)):
    try:
        c = float(p.get('confidence', 0))
    except Exception:
        c = 0
    if c >= 0.8:
        M2[str(p['id'])] = (n1(p['tag']), p['tag'], p['subtag'])

# M3 dataset_0831 gold (subtag-aligned to current)
ds = [r for r in csv.DictReader(open(f'{ROOT}/data/dataset_0831.csv', encoding='utf-8-sig'))
      if r['status'].strip() == 'Done' and r['tag'].strip() and r['subtag'].strip()]
gold = defaultdict(list)
for r in ds:
    gold[pk(audit_of(r['repo_path']))].append((r['tag'].strip(), r['subtag'].strip()))
M3 = {}
for P, srow in sheet.items():
    if P not in bd:
        continue
    cs_cur = n1(bd[P]['subtag'])
    for gt, gs in gold.get(pk(srow.get('contest', '')), []):
        if n1(gs) == cs_cur:
            M3[P] = (n1(gt), gt, gs)
            break

cand = [dict(r) for r in base]
applied, review = 0, []
for r in cand:
    P = r['Property']
    if P in hp:
        continue
    cur = n1(r['tag'])
    votes = []  # (tagnorm, tagstr, substr, method)
    for M, name in [(M1, 'report'), (M2, 'rubric'), (M3, 'gold')]:
        if P in M and M[P][0] != cur:
            votes.append((M[P][0], M[P][1], M[P][2], name))
    if not votes:
        continue
    agree = Counter(v[0] for v in votes)
    top, n = agree.most_common(1)[0]
    if n >= 2:   # >=2 independent methods agree on the SAME different tag
        win = [v for v in votes if v[0] == top][0]
        review.append({'Property': P, 'contest': sheet.get(P, {}).get('contest', ''),
                       'from': f"{r['tag']}/{r['subtag']}", 'to': f"{ct(win[1])}/{cs(win[2])}",
                       'methods': '+'.join(sorted(v[3] for v in votes if v[0] == top))})
        r['tag'] = ct(win[1]); r['subtag'] = cs(win[2]); applied += 1

out = f'{ROOT}/outputs/submission_c4_v54_crossmethod.csv'
w = csv.DictWriter(open(out, 'w', newline='', encoding='utf-8'),
                   fieldnames=['Property', 'repo_path', 'severity', 'tag', 'subtag', 'description'])
w.writeheader(); w.writerows(cand)
rw = csv.DictWriter(open(f'{ROOT}/labeling_handoff/CROSSMETHOD_REVIEW.csv', 'w', newline='', encoding='utf-8'),
                    fieldnames=['Property', 'contest', 'from', 'to', 'methods'])
rw.writeheader(); rw.writerows(review)
print(f"method coverage: M1 report={len(M1)} | M2 rubric={len(M2)} | M3 gold={len(M3)}")
print(f"v54 cross-method (>=2 independent methods agree, hp protected): {applied} corrections vs v50 -> {out}")
for r in review:
    print(f"  pid {r['Property']} [{r['contest']}] {r['from']} -> {r['to']}  ({r['methods']})")

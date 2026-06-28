"""Wider report-grounded pass: stack high-confidence (>=0.8) corrections from the
195-row report read onto the CURRENT BEST base (v50 = 481.21 + 216). Protect the
original 13 hp rows. Emit a review sheet with evidence + DoS-skew check.
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

preds = {str(p['Property']): p for p in json.load(open(f'{ROOT}/finetune/teacher/report_grounded_preds2.json'))}
BASE = f'{ROOT}/outputs/submission_c4_v50_v49_plus216.csv'
base = list(csv.DictReader(open(BASE, encoding='utf-8-sig')))
bd = {r['Property']: r for r in base}
v34 = {r['Property']: r for r in csv.DictReader(open(f'{ROOT}/data_history/submission_c4_v34_teacher_all_479.27.csv', encoding='utf-8-sig'))}
ee = {r['Property']: r for r in csv.DictReader(open(f'{ROOT}/outputs/submission_c4_v16_ee25fix.csv', encoding='utf-8-sig'))}
# original 13 human hand-corrected rows (vs v34, computed from the 479.96 ref)
ref = {r['Property']: r for r in csv.DictReader(open(f'{ROOT}/data_history/submission_c4_v34_teacher_all_retagged_correction_hp_479.96.csv', encoding='utf-8-sig'))}
hp = {p for p in ref if n1(ref[p]['tag']) != n1(v34[p]['tag']) or n1(ref[p]['subtag']) != n1(v34[p]['subtag'])}
sheet = {r['Property']: r for r in csv.DictReader(open(f'{ROOT}/artifacts/teammate_labeling_sheet.csv', encoding='utf-8-sig'))}

CONF = 0.80
review, tcorr, scorr = [], set(), set()
cand = [dict(r) for r in base]
cd = {r['Property']: r for r in cand}
for P, p in preds.items():
    if P not in cd or P in hp:
        continue
    try:
        c = float(p.get('confidence', 0))
    except Exception:
        c = 0
    if c < CONF:
        continue
    cur_t, cur_s = n1(cd[P]['tag']), n1(cd[P]['subtag'])
    newt, news = n1(p['tag']), n1(p['subtag'])
    changed = False
    if newt and newt != cur_t:
        review.append({'Property': P, 'contest': sheet.get(P, {}).get('contest', ''),
                       'current': f"{cd[P]['tag']}/{cd[P]['subtag']}", 'proposed': f"{ct(p['tag'])}/{cs(p['subtag'])}",
                       'confidence': c, 'evidence': str(p.get('evidence', ''))[:200]})
        cd[P]['tag'] = ct(p['tag']); tcorr.add(P); changed = True
    if news and news != cur_s:
        cd[P]['subtag'] = cs(p['subtag']); scorr.add(P)
        if not changed:
            review.append({'Property': P, 'contest': sheet.get(P, {}).get('contest', ''),
                           'current': f"{cd[P]['tag']}/{cur_s}", 'proposed': f"{cd[P]['tag']}/{cs(p['subtag'])}",
                           'confidence': c, 'evidence': str(p.get('evidence', ''))[:200]})

out = f'{ROOT}/outputs/submission_c4_v51_report_wider.csv'
w = csv.DictWriter(open(out, 'w', newline='', encoding='utf-8'),
                   fieldnames=['Property', 'repo_path', 'severity', 'tag', 'subtag', 'description'])
w.writeheader(); w.writerows(cand)

review.sort(key=lambda x: -x['confidence'])
rw = csv.DictWriter(open(f'{ROOT}/labeling_handoff/REPORT_WIDER_REVIEW.csv', 'w', newline='', encoding='utf-8'),
                    fieldnames=['Property', 'contest', 'current', 'proposed', 'confidence', 'evidence'])
rw.writeheader(); rw.writerows(review)

dist = Counter(n1(r['tag']) for r in cand if r['tag'].strip())
nt = sum(dist.values())
dos = 100 * dist.get('dos', 0) / nt
print(f"wider report preds: {len(preds)}/195")
print(f"NEW high-conf (>={CONF}) corrections on v50 base: {len(tcorr)} tag + {len(scorr)} subtag -> {out}")
print(f"DoS share after: {dos:.1f}% (gold 20.1, base 19.8) -> {'OVER-tags DoS (watch)' if dos > 21 else 'OK'}")
print(f"review: labeling_handoff/REPORT_WIDER_REVIEW.csv ({len(review)} rows)")
print("\ntop new corrections:")
for r in review[:14]:
    print(f"  pid {r['Property']} [{r['contest']}] {r['current']} -> {r['proposed']} (c={r['confidence']})")
    print(f"      {r['evidence'][:110]}")

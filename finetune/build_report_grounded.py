"""Build a report-grounded relabel candidate. Apply a correction to the 479.96
base only when the agent (reading the actual C4 report) is confident (>=0.8) the
report supports a tag DIFFERENT from current — and the row isn't a protected hp
row. Emits a REVIEW sheet with the report evidence quote per correction so every
change is human-verifiable. Includes a DoS-skew sanity check.
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

preds = {str(p['Property']): p for p in json.load(open(f'{ROOT}/finetune/teacher/report_grounded_preds.json'))}
base = list(csv.DictReader(open(f'{ROOT}/outputs/base_479.96.csv', encoding='utf-8-sig')))
bd = {r['Property']: r for r in base}
v34 = {r['Property']: r for r in csv.DictReader(open(f'{ROOT}/data_history/submission_c4_v34_teacher_all_479.27.csv', encoding='utf-8-sig'))}
hp = {p for p in bd if n1(bd[p]['tag']) != n1(v34[p]['tag']) or n1(bd[p]['subtag']) != n1(v34[p]['subtag'])}
sheet = {r['Property']: r for r in csv.DictReader(open(f'{ROOT}/artifacts/teammate_labeling_sheet.csv', encoding='utf-8-sig'))}

CONF = 0.80
tag_corr, sub_corr, conflicts, review = [], [], [], []
for P, p in preds.items():
    if P not in bd:
        continue
    try:
        c = float(p.get('confidence', 0))
    except Exception:
        c = 0
    cur_t, cur_s = n1(bd[P]['tag']), n1(bd[P]['subtag'])
    newt, news = n1(p['tag']), n1(p['subtag'])
    tdiff = newt and newt != cur_t
    if c >= CONF and (tdiff or (news and news != cur_s)):
        rec = {'Property': P, 'contest': sheet.get(P, {}).get('contest', ''),
               'current': f"{bd[P]['tag']}/{bd[P]['subtag']}", 'proposed': f"{ct(p['tag'])}/{cs(p['subtag'])}",
               'confidence': c, 'hp_conflict': 'YES' if P in hp else '',
               'evidence': str(p.get('evidence', ''))[:200]}
        review.append(rec)
        if P not in hp:
            if tdiff:
                tag_corr.append(P)
            if news and news != cur_s:
                sub_corr.append(P)
        else:
            conflicts.append(P)

# build candidate: apply high-conf corrections on non-hp rows
cand = [dict(r) for r in base]
for r in cand:
    P = r['Property']
    p = preds.get(P)
    if not p or P in hp:
        continue
    try:
        c = float(p.get('confidence', 0))
    except Exception:
        c = 0
    if c >= CONF:
        if n1(p['tag']) and n1(p['tag']) != n1(r['tag']):
            r['tag'] = ct(p['tag'])
        if n1(p['subtag']) and n1(p['subtag']) != n1(r['subtag']):
            r['subtag'] = cs(p['subtag'])
out = f'{ROOT}/outputs/submission_c4_v49_report_grounded.csv'
w = csv.DictWriter(open(out, 'w', newline='', encoding='utf-8'),
                   fieldnames=['Property', 'repo_path', 'severity', 'tag', 'subtag', 'description'])
w.writeheader(); w.writerows(cand)

review.sort(key=lambda x: -x['confidence'])
rw = csv.DictWriter(open(f'{ROOT}/labeling_handoff/REPORT_GROUNDED_REVIEW.csv', 'w', newline='', encoding='utf-8'),
                    fieldnames=['Property', 'contest', 'current', 'proposed', 'confidence', 'hp_conflict', 'evidence'])
rw.writeheader(); rw.writerows(review)

dist = Counter(n1(r['tag']) for r in cand if r['tag'].strip())
ntot = sum(dist.values())
dos = 100 * dist.get('dos', 0) / ntot
print(f"report-grounded preds: {len(preds)}/65")
print(f"high-confidence (>={CONF}) corrections applied (non-hp): {len(set(tag_corr))} tag + {len(set(sub_corr))} subtag -> {out}")
print(f"hp conflicts (report disagrees with human pass, FLAGGED not applied): {len(set(conflicts))}")
print(f"DoS share after: {dos:.1f}% (gold 20.1, base 19.8) -> {'OVER-tags DoS (risk)' if dos > 20.6 else 'calibrated OK'}")
print(f"\nREVIEW sheet (every change with report evidence): labeling_handoff/REPORT_GROUNDED_REVIEW.csv ({len(review)} rows)")
print("\ntop corrections by confidence:")
for r in review[:12]:
    print(f"  pid {r['Property']} [{r['contest']}] {r['current']} -> {r['proposed']} (c={r['confidence']}{' HP-CONFLICT' if r['hp_conflict'] else ''})")
    print(f"      evidence: {r['evidence'][:120]}")

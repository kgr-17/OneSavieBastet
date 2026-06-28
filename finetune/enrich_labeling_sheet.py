"""Exp B: enriched gold-labeling sheet. For each guessed test row, show the
current best (479.96) label + the 5-pass teacher vote distribution + source-code
+ description, sorted by ENSEMBLE UNCERTAINTY (where the 5 passes split most =
hardest = highest-value human pick). Filling FINAL_ resolves the ambiguity.
"""
import csv, json, re
from collections import Counter, defaultdict

ROOT = '/Users/yixuliu/OneSavieBastet'


def n1(s):
    return re.sub(r'\s+', ' ', str(s).split(',')[0]).strip().lower()


preds = json.load(open(f'{ROOT}/finetune/teacher/5pass_preds.json'))
sc = {str(p['id']): p for p in json.load(open(f'{ROOT}/finetune/teacher/srccode_test_preds.json'))}
base = {r['Property']: r for r in csv.DictReader(open(f'{ROOT}/outputs/base_479.96.csv', encoding='utf-8-sig'))}
sheet = list(csv.DictReader(open(f'{ROOT}/artifacts/teammate_labeling_sheet.csv', encoding='utf-8-sig')))

tv, sv = defaultdict(list), defaultdict(list)
for p in preds:
    tv[str(p['id'])].append(p['tag'])
    sv[str(p['id'])].append(p['subtag'])


def dist(xs):
    c = Counter(n1(x) for x in xs)
    return ', '.join(f"{t}:{n}" for t, n in c.most_common()), (c.most_common(1)[0][1] / len(xs) if xs else 1)


rows = []
for r in sheet:
    P = r['Property']
    td, tconf = dist(tv.get(P, []))
    sd, sconf = dist(sv.get(P, []))
    rows.append({
        'Property': P, 'contest': r.get('contest', ''), 'severity': r.get('severity', ''),
        'best_tag(479.96)': base.get(P, {}).get('tag', ''),
        'tag_votes(5pass)': td, 'tag_conf': round(tconf, 2),
        'srccode_tag': sc.get(P, {}).get('tag', ''),
        'best_subtag(479.96)': base.get(P, {}).get('subtag', ''),
        'subtag_votes(5pass)': sd, 'subtag_conf': round(sconf, 2),
        'FINAL_tag': '', 'FINAL_subtag': '',
        'description': ' '.join(str(r.get('description', '')).split())[:400],
    })
# hardest first: lowest combined confidence (most split)
rows.sort(key=lambda x: x['tag_conf'] + x['subtag_conf'])
cols = ['Property', 'contest', 'severity', 'best_tag(479.96)', 'tag_votes(5pass)', 'tag_conf', 'srccode_tag',
        'best_subtag(479.96)', 'subtag_votes(5pass)', 'subtag_conf', 'FINAL_tag', 'FINAL_subtag', 'description']
import os
os.makedirs(f'{ROOT}/labeling_handoff', exist_ok=True)
out = f'{ROOT}/labeling_handoff/GOLD_SHEET_ENRICHED.csv'
w = csv.DictWriter(open(out, 'w', newline='', encoding='utf-8'), fieldnames=cols)
w.writeheader(); w.writerows(rows)
split = sum(1 for r in rows if r['tag_conf'] < 0.6)
print(f"WROTE {out} ({len(rows)} rows)")
print(f"  rows where the 5 passes SPLIT on tag (<60% agree): {split} = the human-pick priority")
print(f"  fully-unanimous tag rows (5/5): {sum(1 for r in rows if r['tag_conf']==1.0)} (trust)")

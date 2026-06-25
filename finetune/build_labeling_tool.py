"""Exp1: enriched gold-labeling tool. For each guessed test row, gather candidate
(tag, subtag) from 3 independent sources -- maxcontext (ee25fix), the fresh Opus
teacher, and the original team guess -- plus description/severity. Sort by
disagreement (most ambiguous first) so humans label where it matters. Filling the
FINAL_ columns with gold is the validated path to 500 (oracle: hard rows 49->69%).
"""
import csv, json, re

ROOT = '/Users/yixuliu/OneSavieBastet'


def n1(s):
    return re.sub(r'\s+', ' ', str(s).split(',')[0]).strip().lower()


ee = {r['Property']: r for r in csv.DictReader(open(f'{ROOT}/outputs/submission_c4_v16_ee25fix.csv', encoding='utf-8-sig'))}
teacher = {str(p['id']): p for p in json.load(open(f'{ROOT}/finetune/teacher/result.json'))['test']}
sheet = list(csv.DictReader(open(f'{ROOT}/artifacts/teammate_labeling_sheet.csv', encoding='utf-8-sig')))

rows = []
for r in sheet:
    P = r['Property']
    mc = ee.get(P, {})
    tc = teacher.get(P, {})
    cand_tags = {n1(mc.get('tag', '')), n1(tc.get('tag', '')), n1(r.get('our_tag', ''))} - {''}
    cand_subs = {n1(mc.get('subtag', '')), n1(tc.get('subtag', '')), n1(r.get('our_subtag', ''))} - {''}
    rows.append({
        'Property': P, 'contest': r.get('contest', ''), 'severity': r.get('severity', ''),
        'tag_disagree': len(cand_tags), 'subtag_disagree': len(cand_subs),
        'maxcontext_tag': mc.get('tag', ''), 'maxcontext_subtag': mc.get('subtag', ''),
        'teacher_tag': tc.get('tag', ''), 'teacher_subtag': tc.get('subtag', ''),
        'guess_tag': r.get('our_tag', ''), 'guess_subtag': r.get('our_subtag', ''),
        'FINAL_tag (fill if all wrong)': '', 'FINAL_subtag (fill if all wrong)': '',
        'description': ' '.join(str(r.get('description', '')).split())[:400],
    })

# sort: biggest disagreement first (the hard, high-value rows)
rows.sort(key=lambda x: (x['tag_disagree'], x['subtag_disagree']), reverse=True)
cols = ['Property', 'contest', 'severity', 'tag_disagree', 'subtag_disagree',
        'maxcontext_tag', 'teacher_tag', 'guess_tag',
        'maxcontext_subtag', 'teacher_subtag', 'guess_subtag',
        'FINAL_tag (fill if all wrong)', 'FINAL_subtag (fill if all wrong)', 'description']
out = f'{ROOT}/labeling_handoff/GOLD_LABELING_SHEET.csv'
import os
os.makedirs(f'{ROOT}/labeling_handoff', exist_ok=True)
with open(out, 'w', newline='', encoding='utf-8') as f:
    w = csv.DictWriter(f, fieldnames=cols)
    w.writeheader()
    w.writerows(rows)

hard3 = sum(1 for r in rows if r['tag_disagree'] == 3)
hard2 = sum(1 for r in rows if r['tag_disagree'] == 2)
agree = sum(1 for r in rows if r['tag_disagree'] == 1)
print(f"WROTE {out} ({len(rows)} rows)")
print(f"  all-3-models-DISAGREE on tag: {hard3}  (hardest -> label first)")
print(f"  2 distinct tags: {hard2}")
print(f"  all-3-agree on tag: {agree}  (trust, skip)")
print(f"  => actionable human-labeling target = {hard3+hard2} rows where models disagree")

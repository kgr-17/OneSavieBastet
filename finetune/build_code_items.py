"""Exp2: build code-augmented item sets for the LLM source-code classifier.
holdout (153, train repos) for validation; test (289, test repos) for relabel.
Each item = {id, severity, description(clean), code}.
"""
import csv, json
from extract_finding_code import extract, clean_desc

ROOT = '/Users/yixuliu/OneSavieBastet'
TRAIN = f'{ROOT}/data/train'
TEST = f'{ROOT}/data/test'

# holdout: id, repo, severity, description from holdout.json
holdout = json.load(open(f'{ROOT}/finetune/data/holdout.json'))
hi = []
nocode_h = 0
for h in holdout:
    code = extract(TRAIN, h['repo'], h['text'])
    if not code:
        nocode_h += 1
    hi.append({'id': str(h['id']), 'severity': h['severity'],
               'description': clean_desc(h['text'])[:600], 'code': code[:6000]})
json.dump(hi, open(f'{ROOT}/finetune/teacher/holdout_code_items.json', 'w'), ensure_ascii=False)

# test: Property, repo_path (hash), severity, description
ee = {r['Property']: r for r in csv.DictReader(open(f'{ROOT}/outputs/submission_c4_v16_ee25fix.csv', encoding='utf-8-sig'))}
sheet = list(csv.DictReader(open(f'{ROOT}/artifacts/teammate_labeling_sheet.csv', encoding='utf-8-sig')))
ti = []
nocode_t = 0
for r in sheet:
    P = r['Property']
    h = ee.get(P, {}).get('repo_path', '')
    code = extract(TEST, h, r.get('description', ''))
    if not code:
        nocode_t += 1
    ti.append({'id': P, 'severity': r.get('severity', ''),
               'description': clean_desc(r.get('description', ''))[:600], 'code': code[:6000]})
json.dump(ti, open(f'{ROOT}/finetune/teacher/test_code_items.json', 'w'), ensure_ascii=False)

print(f"holdout_code_items: {len(hi)} ({nocode_h} without code)")
print(f"test_code_items: {len(ti)} ({nocode_t} without code)")
import statistics
print(f"median code chars holdout: {int(statistics.median(len(x['code']) for x in hi))}")
print(f"median code chars test: {int(statistics.median(len(x['code']) for x in ti))}")

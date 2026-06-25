"""Build the strong-LLM teacher context (taxonomy + curated 98-shot) and the
item sets to classify: 153 holdout (for validation vs 72.5/56.2) and the 289
guessed test rows (for an aggressive relabel). Writes to finetune/teacher/.
"""
import csv, json, os

ROOT = '/Users/yixuliu/OneSavieBastet'
OUT = f'{ROOT}/finetune/teacher'
os.makedirs(OUT, exist_ok=True)

tag2sub = json.load(open(f'{ROOT}/artifacts/tag_classifier/tag2sub.json'))
fewshot = json.load(open(f'{ROOT}/artifacts/tag_classifier/fewshot_targeted.json'))

lines = []
lines.append("You are an expert smart-contract security auditor labeling findings with the OneSavie/DeFiHackLabs taxonomy.")
lines.append("Pick the SINGLE best primary TAG (and SUBTAG from that tag's allowed list). Match the labelers' conventions exactly.\n")
lines.append("=== TAXONOMY: tag -> allowed subtags ===")
for tag, subs in tag2sub.items():
    lines.append(f"- {tag}: {', '.join(subs)}")
lines.append(f"\n=== {len(fewshot)} LABELED EXAMPLES (the convention to imitate) ===")
for ex in fewshot:
    d = ' '.join(str(ex['description']).split())[:240]
    lines.append(f"DESC: {d}\n -> TAG: {ex['tag']} | SUBTAG: {ex['subtag']}")
context = '\n'.join(lines)
open(f'{OUT}/context.txt', 'w', encoding='utf-8').write(context)

# holdout items (id, severity, description) — truth kept separate for scoring
holdout = json.load(open(f'{ROOT}/finetune/data/holdout.json'))
hi = [{'id': h['id'], 'severity': h['severity'], 'description': h['text']} for h in holdout]
json.dump(hi, open(f'{OUT}/holdout_items.json', 'w'), ensure_ascii=False)
json.dump([{'id': h['id'], 'tag': h['tag_primary'], 'subtag': h['subtag_primary']} for h in holdout],
          open(f'{OUT}/holdout_truth.json', 'w'), ensure_ascii=False)

# test items (the 289 guessed rows): Property, severity, description, current maxcontext label
sheet = list(csv.DictReader(open(f'{ROOT}/artifacts/teammate_labeling_sheet.csv', encoding='utf-8-sig')))
v16 = {r['Property']: r for r in csv.DictReader(open(f'{ROOT}/outputs/submission_c4_v16_ee25fix.csv', encoding='utf-8-sig'))}
ti = []
for r in sheet:
    P = r['Property']
    ti.append({'id': P, 'severity': r.get('severity', ''), 'description': r.get('description', ''),
               'mc_tag': v16.get(P, {}).get('tag', ''), 'mc_subtag': v16.get(P, {}).get('subtag', '')})
json.dump(ti, open(f'{OUT}/test_items.json', 'w'), ensure_ascii=False)

print(f"context.txt: {len(context)} chars | tags={len(tag2sub)} | fewshot={len(fewshot)}")
print(f"holdout_items: {len(hi)} | test_items: {len(ti)}")

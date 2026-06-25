"""Identify which dataset_0831 audits overlap the 153-row holdout, so we can
exclude those whole audits from the expanded training pool (repo-disjoint
integrity). Self-contained: uses semantic nearest-neighbor between holdout
descriptions and ALL dataset_0831 rows (Done+TODO) to identify holdout
protocols even when wording/language differs.
"""
import csv, json, re
import numpy as np
from collections import Counter
from sentence_transformers import SentenceTransformer

ROOT = '/Users/yixuliu/OneSavieBastet'


def audit_of(rp):
    for seg in str(rp).replace('\\', '/').split('/'):
        if len(seg) >= 7 and seg[:2] == '20' and '-' in seg:
            return seg
    return ''


ds = list(csv.DictReader(open(f'{ROOT}/data/dataset_0831.csv', encoding='utf-8-sig')))
hold = json.load(open(f'{ROOT}/finetune/data/holdout.json'))
for r in ds:
    r['audit'] = audit_of(r['repo_path'])

done = [r for r in ds if r['status'].strip() == 'Done' and r['tag'].strip()
        and r['subtag'].strip() and r['description'].strip()]
print(f'dataset_0831: {len(ds)} rows | Done usable: {len(done)}')
print(f'distinct audits among Done usable: {len(set(r["audit"] for r in done))}')
print('top Done audits:', Counter(r['audit'] for r in done).most_common(8))

enc = SentenceTransformer('BAAI/bge-small-en-v1.5', device='cpu')
ds_text = [r['description'] for r in ds]
E_ds = enc.encode(ds_text, normalize_embeddings=True, batch_size=64, show_progress_bar=False)
E_ho = enc.encode([h['text'] for h in hold], normalize_embeddings=True, batch_size=64, show_progress_bar=False)

sims = E_ho @ E_ds.T            # 153 x 4401
nn = sims.argmax(1)
nn_sim = sims.max(1)
matched_audits = Counter()
for i, h in enumerate(hold):
    a = ds[nn[i]]['audit']
    matched_audits[a] += 1

print('\nholdout->dataset_0831 nearest-neighbor cosine distribution:')
for thr in (0.95, 0.90, 0.85, 0.80, 0.75, 0.70):
    print(f'  >= {thr}: {int((nn_sim >= thr).sum())}/153 holdout findings')

# audits implicated at a given threshold
for thr in (0.85, 0.80, 0.75):
    auds = sorted(set(ds[nn[i]]['audit'] for i in range(len(hold)) if nn_sim[i] >= thr and ds[nn[i]]['audit']))
    done_hit = sum(1 for r in done if r['audit'] in auds)
    print(f'\nthreshold {thr}: {len(auds)} holdout audits implicated; '
          f'{done_hit} Done rows would be excluded')
    print('  audits:', auds)

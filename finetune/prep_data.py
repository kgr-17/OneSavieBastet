"""Build leakage-safe train/holdout splits + normalized label vocab for the
fine-tuning experiments. Mirrors artifacts/tag_classifier/prep.py EXACTLY
(seed 1337, 30% of repos held out) so accuracy is comparable to the
maxcontext benchmark (tag 72.5 / subtag 56.2 on these same 153 findings).

Metric alignment: score_confirm.py compares norm(pred)==norm(truth[0]) where
norm = first comma-label, whitespace-collapsed, lowercased. So we store the
normalized PRIMARY label (first listed) plus the full normalized label set.
"""
import csv, json, random, re, os

ROOT = '/Users/yixuliu/OneSavieBastet'
os.makedirs(f'{ROOT}/finetune/data', exist_ok=True)


def norm(s):
    return re.sub(r'\s+', ' ', str(s).split(',')[0]).strip().lower()


def normlabs(v, key):
    out = []
    for p in str(v.get(key, '')).split(','):
        p = re.sub(r'\s+', ' ', p).strip().lower()
        if p:
            out.append(p)
    return out


tr = list(csv.DictReader(open(f'{ROOT}/train.csv', encoding='utf-8-sig')))
repos = sorted(set(r['repo_path'] for r in tr))
random.Random(1337).shuffle(repos)
k = int(len(repos) * 0.3)
hold = set(repos[:k])
trn = [r for r in tr if r['repo_path'] not in hold]
hld = [r for r in tr if r['repo_path'] in hold]


def rec(r):
    return {
        'text': r['description'],
        'repo': r['repo_path'],
        'severity': r['severity'],
        'tag_primary': norm(r['tag']),
        'subtag_primary': norm(r['subtag']),
        'tags': normlabs(r, 'tag'),
        'subtags': normlabs(r, 'subtag'),
    }


train = [rec(r) for r in trn]
holdout = [{**rec(r), 'id': i} for i, r in enumerate(hld)]

# label vocab from TRAIN only (model can only learn/predict labels it has seen)
tagset = sorted(set(t for r in train for t in r['tags']))
subset = sorted(set(s for r in train for s in r['subtags']))

json.dump(train, open(f'{ROOT}/finetune/data/train.json', 'w'), ensure_ascii=False)
json.dump(holdout, open(f'{ROOT}/finetune/data/holdout.json', 'w'), ensure_ascii=False)
json.dump({'tags': tagset, 'subtags': subset},
          open(f'{ROOT}/finetune/data/labels.json', 'w'), ensure_ascii=False)

# how many holdout primaries are even reachable (in train vocab)?
tag_reach = sum(1 for h in holdout if h['tag_primary'] in set(tagset))
sub_reach = sum(1 for h in holdout if h['subtag_primary'] in set(subset))
print(f'train={len(train)} holdout={len(holdout)} tags={len(tagset)} subtags={len(subset)}')
print(f'holdout tag_primary reachable in train vocab: {tag_reach}/153 ({100*tag_reach/153:.1f}%)')
print(f'holdout subtag_primary reachable in train vocab: {sub_reach}/153 ({100*sub_reach/153:.1f}%)')
print(f'  -> these reach %s are the HARD CEILING for any train-only classifier')

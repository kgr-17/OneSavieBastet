"""Shared eval metric — replicates artifacts/tag_classifier/score_confirm.py:
tag/subtag accuracy = fraction of the 153 holdout findings whose predicted
PRIMARY label (normalized: first comma-label, ws-collapsed, lowercased) exactly
equals the truth primary label. Denominator = holdout rows that have a truth
label (all 153). Benchmark to beat: maxcontext tag 72.5 / subtag 56.2.
"""
import json, re

ROOT = '/Users/yixuliu/OneSavieBastet'


def norm(s):
    return re.sub(r'\s+', ' ', str(s).split(',')[0]).strip().lower()


def load():
    train = json.load(open(f'{ROOT}/finetune/data/train.json'))
    holdout = json.load(open(f'{ROOT}/finetune/data/holdout.json'))
    labels = json.load(open(f'{ROOT}/finetune/data/labels.json'))
    return train, holdout, labels


def accuracy(holdout, preds, field):
    """preds: list aligned with holdout, each the predicted PRIMARY label string."""
    key = 'tag_primary' if field == 'tag' else 'subtag_primary'
    c = n = 0
    for h, p in zip(holdout, preds):
        if not h[key]:
            continue
        n += 1
        c += int(norm(p) == norm(h[key]))
    return 100.0 * c / n if n else 0.0


BENCH = {'tag': 72.5, 'subtag': 56.2}  # maxcontext on this exact holdout

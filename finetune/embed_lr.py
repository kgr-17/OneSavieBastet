"""Frozen pretrained sentence embeddings + sample-efficient linear head.
Leverages transformer pretraining (semantic generalization TF-IDF lacks) while
avoiding the overfit risk of full fine-tuning on only 344 examples.

Compares several embedders x {LogReg, cosine-kNN} for primary tag/subtag,
reported vs maxcontext 72.5 / 56.2 on the same 153-row holdout.
"""
import json, os, numpy as np, torch
from sentence_transformers import SentenceTransformer
from sklearn.linear_model import LogisticRegression
from sklearn.neighbors import KNeighborsClassifier
from eval_common import load, accuracy, norm, BENCH

train, holdout, labels = load()
DEV = 'mps' if torch.backends.mps.is_available() else 'cpu'

EMBEDDERS = [
    'BAAI/bge-small-en-v1.5',
    'BAAI/bge-base-en-v1.5',
    'sentence-transformers/all-mpnet-base-v2',
    'intfloat/e5-base-v2',
]


def texts(rows, with_sev=False):
    if with_sev:
        return [f"severity {r['severity']}. {r['text']}" for r in rows]
    return [r['text'] for r in rows]


results = {}
print(f"{'embedder':<40}{'head':<12}{'sev':<5}{'tag':>7}{'subtag':>9}")
print('-' * 75)

for name in EMBEDDERS:
    try:
        enc = SentenceTransformer(name, device=DEV)
    except Exception as e:
        print(f'{name:<40} LOAD FAIL {str(e)[:30]}')
        continue
    for with_sev in (False, True):
        Etr = enc.encode(texts(train, with_sev), normalize_embeddings=True, batch_size=32)
        Eho = enc.encode(texts(holdout, with_sev), normalize_embeddings=True, batch_size=32)
        for head in ('lr', 'knn'):
            row = {}
            for field, key in [('tag', 'tag_primary'), ('subtag', 'subtag_primary')]:
                ytr = [r[key] for r in train]
                if head == 'lr':
                    clf = LogisticRegression(max_iter=4000, C=12.0, class_weight='balanced')
                else:
                    clf = KNeighborsClassifier(n_neighbors=7, metric='cosine', weights='distance')
                clf.fit(Etr, ytr)
                preds = list(clf.predict(Eho))
                row[field] = accuracy(holdout, preds, field)
            tag = f"{name.split('/')[-1]:<40}"
            print(f"{tag}{head:<12}{str(with_sev):<5}{row['tag']:>7.1f}{row['subtag']:>9.1f}")
            results[f'{name}|{head}|sev={with_sev}'] = row

json.dump(results, open(os.path.join(os.path.dirname(__file__), 'results_embed.json'), 'w'), indent=2)
best_tag = max(results.items(), key=lambda kv: kv[1]['tag'])
best_sub = max(results.items(), key=lambda kv: kv[1]['subtag'])
print('-' * 75)
print(f"BEST tag   : {best_tag[1]['tag']:.1f}  ({best_tag[0]})   vs maxcontext 72.5")
print(f"BEST subtag: {best_sub[1]['subtag']:.1f}  ({best_sub[0]})   vs maxcontext 56.2")

"""Build a leakage-safe EXPANDED training pool (train_nonholdout + dataset_0831
Done), with audit-level exclusion of holdout protocols, then re-run the fast
classifiers to see whether more gold data closes the gap to maxcontext 72.5/56.2.

Leakage guard:
  - map each holdout repo -> its audit by majority NN over its findings (cos>=0.78)
  - drop all dataset_0831 Done rows from those audits
  - row-level backstop: drop any Done row that is a near-dup (cos>=0.92) of a holdout finding
Writes finetune/data/train_expanded.json for the encoder fine-tune.
"""
import csv, json, re, os
import numpy as np
from collections import Counter, defaultdict
from sentence_transformers import SentenceTransformer
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline, FeatureUnion
from eval_common import load, accuracy, norm, BENCH

ROOT = '/Users/yixuliu/OneSavieBastet'
train_base, holdout, labels = load()


def normlabs(s):
    return [p for p in (re.sub(r'\s+', ' ', x).strip().lower() for x in str(s).split(',')) if p]


def audit_of(rp):
    for seg in str(rp).replace('\\', '/').split('/'):
        if len(seg) >= 7 and seg[:2] == '20' and '-' in seg:
            return seg
    return ''


ds = list(csv.DictReader(open(f'{ROOT}/data/dataset_0831.csv', encoding='utf-8-sig')))
for r in ds:
    r['audit'] = audit_of(r['repo_path'])
done = [r for r in ds if r['status'].strip() == 'Done' and r['tag'].strip()
        and r['subtag'].strip() and r['description'].strip()]

enc = SentenceTransformer('BAAI/bge-small-en-v1.5', device='cpu')
E_ho = enc.encode([h['text'] for h in holdout], normalize_embeddings=True, batch_size=64, show_progress_bar=False)
E_ds = enc.encode([r['description'] for r in ds], normalize_embeddings=True, batch_size=64, show_progress_bar=False)

# holdout repo -> audit (majority NN audit among its findings with cos>=0.78)
sims = E_ho @ E_ds.T
nn, nn_sim = sims.argmax(1), sims.max(1)
repo_audit_votes = defaultdict(Counter)
for i, h in enumerate(holdout):
    if nn_sim[i] >= 0.78 and ds[nn[i]]['audit']:
        repo_audit_votes[h['repo']][ds[nn[i]]['audit']] += 1
holdout_audits = set()
for repo, votes in repo_audit_votes.items():
    holdout_audits.add(votes.most_common(1)[0][0])
print(f'holdout repos mapped to audits: {len(holdout_audits)} of 16 holdout repos')
print('  excluded audits:', sorted(holdout_audits))

# row-level near-dup backstop
E_done = enc.encode([r['description'] for r in done], normalize_embeddings=True, batch_size=64, show_progress_bar=False)
dup_sim = (E_done @ E_ho.T).max(1)

kept_done = []
excl_audit = excl_dup = 0
for r, ds_dup in zip(done, dup_sim):
    if r['audit'] in holdout_audits:
        excl_audit += 1; continue
    if ds_dup >= 0.92:
        excl_dup += 1; continue
    kept_done.append(r)
print(f'dataset_0831 Done usable: {len(done)} -> kept {len(kept_done)} '
      f'(excluded {excl_audit} by audit, {excl_dup} by near-dup)')

# build expanded pool; dedup by normalized description vs base + within
seen = set(norm(r['text']) + '||' for r in train_base)  # base descs
exp_extra = []
for r in kept_done:
    key = re.sub(r'\s+', ' ', r['description']).strip().lower()[:200]
    if key in seen:
        continue
    seen.add(key)
    tags, subs = normlabs(r['tag']), normlabs(r['subtag'])
    if not tags or not subs:
        continue
    exp_extra.append({'text': r['description'], 'repo': r['audit'], 'severity': r['severity'],
                      'tag_primary': tags[0], 'subtag_primary': subs[0],
                      'tags': tags, 'subtags': subs})
train_exp = train_base + exp_extra
json.dump(train_exp, open(f'{ROOT}/finetune/data/train_expanded.json', 'w'), ensure_ascii=False)
print(f'\nEXPANDED POOL: {len(train_base)} base + {len(exp_extra)} new = {len(train_exp)} rows')

# per-class coverage
def cls_cov(rows, key):
    return Counter(r[key] for r in rows)
tb = cls_cov(train_base, 'tag_primary'); te = cls_cov(train_exp, 'tag_primary')
print(f'tag classes: base {len(tb)} -> expanded {len(te)} | '
      f'subtag classes: {len(cls_cov(train_base,"subtag_primary"))} -> {len(cls_cov(train_exp,"subtag_primary"))}')


def feats():
    return FeatureUnion([
        ('w', TfidfVectorizer(analyzer='word', ngram_range=(1, 2), min_df=2, sublinear_tf=True)),
        ('c', TfidfVectorizer(analyzer='char_wb', ngram_range=(3, 5), min_df=2, sublinear_tf=True))])


def run_tfidf(train_rows):
    out = {}
    for field, key in [('tag', 'tag_primary'), ('subtag', 'subtag_primary')]:
        pipe = Pipeline([('f', feats()), ('lr', LogisticRegression(max_iter=3000, C=8, class_weight='balanced'))])
        pipe.fit([r['text'] for r in train_rows], [r[key] for r in train_rows])
        preds = list(pipe.predict([h['text'] for h in holdout]))
        out[field] = accuracy(holdout, preds, field)
    return out


def run_embed(train_rows):
    Etr = enc.encode([r['text'] for r in train_rows], normalize_embeddings=True, batch_size=64, show_progress_bar=False)
    out = {}
    for field, key in [('tag', 'tag_primary'), ('subtag', 'subtag_primary')]:
        clf = LogisticRegression(max_iter=4000, C=12, class_weight='balanced')
        clf.fit(Etr, [r[key] for r in train_rows])
        preds = list(clf.predict(E_ho))
        out[field] = accuracy(holdout, preds, field)
    return out


print(f"\n{'approach':<28}{'pool':>7}{'tag':>8}{'subtag':>9}")
print('-' * 54)
for name, fn in [('tfidf+LR', run_tfidf), ('bge-small+LR', run_embed)]:
    rb = fn(train_base); re_ = fn(train_exp)
    print(f"{name+' (344)':<28}{len(train_base):>7}{rb['tag']:>8.1f}{rb['subtag']:>9.1f}")
    print(f"{name+' (expanded)':<28}{len(train_exp):>7}{re_['tag']:>8.1f}{re_['subtag']:>9.1f}")
print('-' * 54)
print('maxcontext benchmark           tag 72.5  subtag 56.2')

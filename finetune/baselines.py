"""Fast, CPU-only classical baselines (floor reference for the fine-tuning effort).
Reports tag/subtag PRIMARY-label accuracy on the 153-row holdout vs maxcontext 72.5/56.2.

Models:
  - TF-IDF (word 1-2gram + char 3-5gram) -> Logistic Regression (single-label, primary)
  - same, with severity prepended to text
  - Linear SVM variant
"""
import json
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.svm import LinearSVC
from sklearn.pipeline import Pipeline, FeatureUnion
from eval_common import load, accuracy, BENCH

train, holdout, labels = load()


def make_text(rows, with_sev=False):
    if with_sev:
        return [f"severity {r['severity']}. {r['text']}" for r in rows]
    return [r['text'] for r in rows]


def word_char_features():
    return FeatureUnion([
        ('w', TfidfVectorizer(analyzer='word', ngram_range=(1, 2), min_df=2, sublinear_tf=True)),
        ('c', TfidfVectorizer(analyzer='char_wb', ngram_range=(3, 5), min_df=2, sublinear_tf=True)),
    ])


def run(clf_name, with_sev):
    Xtr = make_text(train, with_sev)
    Xho = make_text(holdout, with_sev)
    out = {}
    for field, key in [('tag', 'tag_primary'), ('subtag', 'subtag_primary')]:
        ytr = [r[key] for r in train]
        if clf_name == 'lr':
            clf = LogisticRegression(max_iter=3000, C=8.0, class_weight='balanced')
        else:
            clf = LinearSVC(C=1.0, class_weight='balanced')
        pipe = Pipeline([('feat', word_char_features()), ('clf', clf)])
        pipe.fit(Xtr, ytr)
        preds = list(pipe.predict(Xho))
        out[field] = accuracy(holdout, preds, field)
    return out


print(f"{'model':<34}{'tag':>8}{'subtag':>9}   vs maxcontext (72.5 / 56.2)")
print('-' * 70)
configs = [
    ('tfidf+LR', 'lr', False),
    ('tfidf+LR +severity', 'lr', True),
    ('tfidf+LinearSVC', 'svm', False),
    ('tfidf+LinearSVC +severity', 'svm', True),
]
results = {}
for name, clf, sev in configs:
    r = run(clf, sev)
    results[name] = r
    dt = r['tag'] - BENCH['tag']
    ds = r['subtag'] - BENCH['subtag']
    print(f"{name:<34}{r['tag']:>7.1f}{r['subtag']:>9.1f}   "
          f"(tag {dt:+.1f}, subtag {ds:+.1f})")

json.dump(results, open(f'{__import__("os").path.dirname(__file__)}/results_baselines.json', 'w'), indent=2)
print('\nBenchmark to beat: tag 72.5 / subtag 56.2 (maxcontext LLM, same 153-row holdout)')

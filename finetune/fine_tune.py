"""Full encoder fine-tuning for primary tag/subtag classification.
Parametrized via env:
  FT_TRAIN  = path to train json (default finetune/data/train.json)
  FT_MODELS = comma-sep HF model ids (default bert/deberta-small/codebert)
  FT_TAG    = output suffix (default 'base')
Epoch chosen by a repo-disjoint inner-val (never the holdout). Accuracy on the
same 153-row holdout vs maxcontext 72.5 / 56.2. Per-holdout preds saved.
"""
import json, os, random
import numpy as np, torch
from datasets import Dataset
from transformers import (AutoTokenizer, AutoModelForSequenceClassification,
                          TrainingArguments, Trainer, DataCollatorWithPadding,
                          EarlyStoppingCallback)
from sklearn.metrics import f1_score
from eval_common import load, accuracy, norm, BENCH

os.environ['TOKENIZERS_PARALLELISM'] = 'false'
HERE = os.path.dirname(__file__)
_, holdout, labels = load()
TRAIN = os.environ.get('FT_TRAIN', f'{HERE}/data/train.json')
train_rows = json.load(open(TRAIN))
MODELS = os.environ.get('FT_MODELS', 'bert-base-uncased,microsoft/deberta-v3-small,microsoft/codebert-base').split(',')
TAG = os.environ.get('FT_TAG', 'base')
FIELDS = [('tag', 'tag_primary'), ('subtag', 'subtag_primary')]
MAXLEN = int(os.environ.get('FT_MAXLEN', '320'))
BATCH = int(os.environ.get('FT_BATCH', '16'))
GRADCKPT = os.environ.get('FT_GRADCKPT', '0') == '1'
print(f'[fine_tune] train={TRAIN} ({len(train_rows)} rows) models={MODELS} tag={TAG}', flush=True)


def inner_split(rows, frac=0.15, seed=1337):
    repos = sorted(set(r.get('repo', '') for r in rows))
    random.Random(seed).shuffle(repos)
    k = max(1, int(len(repos) * frac))
    val = set(repos[:k])
    tr = [r for r in rows if r.get('repo', '') not in val]
    va = [r for r in rows if r.get('repo', '') in val]
    return (tr, va) if va else (rows[:-20], rows[-20:])


def run(model_name, field, key):
    classes = sorted(set(r[key] for r in train_rows))
    l2i = {c: i for i, c in enumerate(classes)}
    i2l = {i: c for c, i in l2i.items()}
    tok = AutoTokenizer.from_pretrained(model_name)

    def to_ds(rows):
        d = tok([r['text'] for r in rows], truncation=True, max_length=MAXLEN)
        d['labels'] = [l2i[r[key]] for r in rows]
        return Dataset.from_dict(d)

    itr, iva = inner_split(train_rows)
    model = AutoModelForSequenceClassification.from_pretrained(
        model_name, num_labels=len(classes), id2label=i2l, label2id=l2i)
    if GRADCKPT:
        model.gradient_checkpointing_enable()

    def compute_metrics(ep):
        p = np.argmax(ep[0], axis=-1)
        return {'f1': f1_score(ep[1], p, average='macro', zero_division=0)}

    args = TrainingArguments(
        output_dir=f'/tmp/ft_{TAG}_{field}_{model_name.split("/")[-1]}',
        num_train_epochs=15, per_device_train_batch_size=BATCH,
        per_device_eval_batch_size=32, learning_rate=2e-5, weight_decay=0.01,
        warmup_steps=30, eval_strategy='epoch', save_strategy='epoch',
        load_best_model_at_end=True, metric_for_best_model='f1',
        greater_is_better=True, logging_strategy='no', report_to=[],
        save_total_limit=1, seed=1337, disable_tqdm=True)
    trainer = Trainer(model=model, args=args, train_dataset=to_ds(itr), eval_dataset=to_ds(iva),
                      data_collator=DataCollatorWithPadding(tok), compute_metrics=compute_metrics,
                      callbacks=[EarlyStoppingCallback(early_stopping_patience=3)])
    trainer.train()
    dho = Dataset.from_dict(tok([h['text'] for h in holdout], truncation=True, max_length=MAXLEN))
    preds = [i2l[int(i)] for i in np.argmax(trainer.predict(dho).predictions, axis=-1)]
    return accuracy(holdout, preds, field), preds


results, all_preds = {}, {}
print(f"{'model':<26}{'field':<8}{'acc':>7}   vs maxcontext", flush=True)
print('-' * 56, flush=True)
for m in MODELS:
    m = m.strip()
    for field, key in FIELDS:
        try:
            acc, preds = run(m, field, key)
            results[f'{m}|{field}'] = acc
            all_preds[f'{m}|{field}'] = preds
            print(f"{m.split('/')[-1]:<26}{field:<8}{acc:>6.1f}   ({acc - BENCH[field]:+.1f} vs {BENCH[field]})", flush=True)
        except Exception as e:
            print(f"{m.split('/')[-1]:<26}{field:<8} FAIL {str(e)[:60]}", flush=True)

json.dump(results, open(f'{HERE}/results_finetune_{TAG}.json', 'w'), indent=2)
json.dump(all_preds, open(f'{HERE}/preds_finetune_{TAG}.json', 'w'))
print('-' * 56)
print('Benchmark: maxcontext tag 72.5 / subtag 56.2')
if results:
    print(f"BEST: tag {max((v for k,v in results.items() if k.endswith('tag')), default=0):.1f} / "
          f"subtag {max((v for k,v in results.items() if k.endswith('subtag')), default=0):.1f}")

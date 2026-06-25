# Bastet tag/subtag encoder fine-tuning sweep (Kaggle GPU).
# Best-case discriminative test vs maxcontext LLM (tag 72.5 / subtag 56.2) on the
# identical 153-row holdout. Strong small encoders x {base 344, expanded 559 pool}.
import os, subprocess, sys
# Kaggle 'latest' ships torch cu128 (supports sm_70+) but frequently assigns a
# Tesla P100 (sm_60) -> "no kernel image available". Pin a cu121 torch whose
# wheels include sm_60 so training runs on either P100 or T4.
def _gpu_name():
    try:
        return subprocess.run(['nvidia-smi', '--query-gpu=name', '--format=csv,noheader'],
                              capture_output=True, text=True).stdout
    except Exception:
        return ''
# IMPORTANT: detect via nvidia-smi WITHOUT importing torch first, so the
# reinstalled wheel is what the later `import torch` actually loads.
if 'P100' in _gpu_name():
    print('P100 detected -> pinning cu121 torch (sm_60 support)', flush=True)
    subprocess.run([sys.executable, '-m', 'pip', 'install', '-q', '--force-reinstall',
                    'torch==2.4.1', 'torchvision==0.19.1',
                    '--index-url', 'https://download.pytorch.org/whl/cu121'], check=False)

import json, random, re, glob
import numpy as np, torch
from datasets import Dataset
from transformers import (AutoTokenizer, AutoModelForSequenceClassification,
                          TrainingArguments, Trainer, DataCollatorWithPadding,
                          EarlyStoppingCallback)
import transformers
from sklearn.metrics import f1_score

OUT = '/kaggle/working'
print('torch', torch.__version__, 'cuda', torch.cuda.is_available(), '| transformers', transformers.__version__)
FP16 = torch.cuda.is_available() and torch.cuda.get_device_capability()[0] >= 7  # fp16 only on T4+ (not P100)
print('fp16:', FP16, '| device:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'cpu')
print('input dirs:', os.listdir('/kaggle/input') if os.path.isdir('/kaggle/input') else 'NO /kaggle/input')
_cands = glob.glob('/kaggle/input/**/holdout.json', recursive=True)
assert _cands, f"holdout.json not found; /kaggle/input/** = {glob.glob('/kaggle/input/**', recursive=True)[:30]}"
IN = os.path.dirname(_cands[0])
print('IN =', IN)


def ensure_safetensors(name):
    """transformers refuses .bin unless torch>=2.6, but P100 needs torch 2.4.1.
    Convert .bin->safetensors locally (we control torch.load) to bypass the block."""
    from huggingface_hub import snapshot_download
    from safetensors.torch import save_file
    d = snapshot_download(name)
    if glob.glob(f'{d}/*.safetensors'):
        return d
    bins = sorted(glob.glob(f'{d}/pytorch_model*.bin'))
    if not bins:
        return d
    sd = {}
    for b in bins:
        sd.update(torch.load(b, map_location='cpu', weights_only=True))
    sd = {k: v.contiguous() for k, v in sd.items() if torch.is_tensor(v)}
    save_file(sd, f'{d}/model.safetensors')
    print(f'  converted {name} .bin -> safetensors ({len(sd)} tensors)', flush=True)
    return d


def norm(s):
    return re.sub(r'\s+', ' ', str(s).split(',')[0]).strip().lower()


holdout = json.load(open(f'{IN}/holdout.json'))
POOLS = {'base': json.load(open(f'{IN}/train.json')),
         'expanded': json.load(open(f'{IN}/train_expanded.json'))}
print('holdout', len(holdout), '| base', len(POOLS['base']), '| expanded', len(POOLS['expanded']))


def accuracy(preds, field):
    key = 'tag_primary' if field == 'tag' else 'subtag_primary'
    c = n = 0
    for h, p in zip(holdout, preds):
        if not h[key]:
            continue
        n += 1
        c += int(norm(p) == norm(h[key]))
    return 100.0 * c / n


def inner_split(rows, frac=0.15, seed=1337):
    repos = sorted(set(r.get('repo', '') for r in rows))
    random.Random(seed).shuffle(repos)
    k = max(1, int(len(repos) * frac))
    val = set(repos[:k])
    tr = [r for r in rows if r.get('repo', '') not in val]
    va = [r for r in rows if r.get('repo', '') in val]
    return (tr, va) if va else (rows[:-20], rows[-20:])


MAXLEN = 320
# order matters: most informative first (incremental result writes survive timeouts)
JOBS = [
    ('microsoft/deberta-v3-base', 'expanded'),
    ('microsoft/deberta-v3-base', 'base'),
    ('answerdotai/ModernBERT-base', 'expanded'),
]
FIELDS = [('tag', 'tag_primary'), ('subtag', 'subtag_primary')]


def run(model_name, pool_rows, field, key):
    classes = sorted(set(r[key] for r in pool_rows))
    l2i = {c: i for i, c in enumerate(classes)}
    i2l = {i: c for c, i in l2i.items()}
    tok = AutoTokenizer.from_pretrained(model_name)

    def to_ds(rows):
        d = tok([r['text'] for r in rows], truncation=True, max_length=MAXLEN)
        d['labels'] = [l2i[r[key]] for r in rows]
        return Dataset.from_dict(d)

    itr, iva = inner_split(pool_rows)
    extra = {'reference_compile': False} if 'ModernBERT' in model_name else {}
    model = AutoModelForSequenceClassification.from_pretrained(
        ensure_safetensors(model_name), num_labels=len(classes),
        id2label=i2l, label2id=l2i, **extra)
    big = 'large' in model_name
    if big:
        model.gradient_checkpointing_enable()
    # deberta-v3 collapses to majority class at lr 2e-5 on small data; needs lower lr + more warmup
    is_deberta = 'deberta' in model_name
    lr = 7e-6 if is_deberta else (1e-5 if big else 2e-5)
    warm = 80 if is_deberta else 30

    def cm(ep):
        p = np.argmax(ep[0], axis=-1)
        return {'f1': f1_score(ep[1], p, average='macro', zero_division=0)}

    base = dict(
        output_dir=f'/tmp/{field}', num_train_epochs=18,
        per_device_train_batch_size=8 if big else 16, per_device_eval_batch_size=64,
        learning_rate=lr, weight_decay=0.01, warmup_steps=warm,
        save_strategy='epoch', load_best_model_at_end=True,
        metric_for_best_model='f1', greater_is_better=True, logging_strategy='no',
        report_to=[], save_total_limit=1, seed=1337, disable_tqdm=True, fp16=FP16)
    try:
        args = TrainingArguments(eval_strategy='epoch', **base)
    except TypeError:
        args = TrainingArguments(evaluation_strategy='epoch', **base)
    tr = Trainer(model=model, args=args, train_dataset=to_ds(itr), eval_dataset=to_ds(iva),
                 data_collator=DataCollatorWithPadding(tok), compute_metrics=cm,
                 callbacks=[EarlyStoppingCallback(early_stopping_patience=3)])
    tr.train()
    dho = Dataset.from_dict(tok([h['text'] for h in holdout], truncation=True, max_length=MAXLEN))
    preds = [i2l[int(i)] for i in np.argmax(tr.predict(dho).predictions, axis=-1)]
    return accuracy(preds, field), preds


results, preds_all = {}, {}
for model_name, pool in JOBS:
    for field, key in FIELDS:
        tagk = f'{model_name}|{pool}|{field}'
        try:
            acc, preds = run(model_name, POOLS[pool], field, key)
            results[tagk] = round(acc, 2)
            preds_all[tagk] = preds
            print('OK', tagk, round(acc, 1), flush=True)
        except Exception as e:
            results[tagk] = f'FAIL {str(e)[:90]}'
            print('FAIL', tagk, str(e)[:90], flush=True)
        json.dump(results, open(f'{OUT}/results.json', 'w'), indent=2)
        json.dump(preds_all, open(f'{OUT}/preds.json', 'w'))
        torch.cuda.empty_cache()

results['_benchmark'] = {'maxcontext_tag': 72.5, 'maxcontext_subtag': 56.2}
json.dump(results, open(f'{OUT}/results.json', 'w'), indent=2)
print('DONE')
print(json.dumps(results, indent=2))

import json, io, sys, csv, re
from collections import Counter

def norm(s): return re.sub(r'\s+',' ',str(s)).strip().lower()

hold = json.load(io.open('artifacts/tag_classifier/holdout.json', encoding='utf-8'))
preds = json.load(io.open('artifacts/tag_classifier/predictions.json', encoding='utf-8'))
pred_by_id = {p['id']: p for p in preds}

def field_score(pred_labels, truth_labels):
    ts=set(norm(x) for x in truth_labels if str(x).strip())
    ps=set(norm(x) for x in pred_labels if str(x).strip())
    if not ts: return 0.0
    tp=len(ps&ts); fp=len(ps-ts)
    return max(0.0,(tp-0.5*fp)/len(ts))

# naive BGE-NN baseline (recompute, same split)
import csv as _csv, random
tr=list(_csv.DictReader(open('train.csv',encoding='utf-8-sig')))
repos=sorted(set(r['repo_path'] for r in tr)); random.Random(1337).shuffle(repos)
k=int(len(repos)*0.3); hold_repos=set(repos[:k])
trn=[r for r in tr if r['repo_path'] not in hold_repos]
from sentence_transformers import SentenceTransformer
m=SentenceTransformer('BAAI/bge-large-en-v1.5')
import numpy as np
tre=m.encode([r['description'] for r in trn],normalize_embeddings=True)
hle=m.encode([h['description'] for h in hold],normalize_embeddings=True)
nn=(hle@tre.T).argmax(axis=1)
def labs(v): return [p.strip() for p in str(v).split(',') if p.strip()]

n=len(hold)
tag_exact_llm=tag_exact_naive=sub_exact_llm=sub_exact_naive=0
tagF_llm=tagF_naive=subF_llm=subF_naive=0.0
missing=0
for i,h in enumerate(hold):
    tt=h['truth_tag']; ts=h['truth_subtag']
    # naive
    ntag=labs(trn[nn[i]]['tag']); nsub=labs(trn[nn[i]]['subtag'])
    # llm
    p=pred_by_id.get(h['id'])
    if not p: missing+=1; ptag=[]; psub=[]
    else: ptag=[p['tag']]; psub=[p['subtag']]
    if tt and norm(ptag[0] if ptag else '')==norm(tt[0]): tag_exact_llm+=1
    if tt and norm(ntag[0] if ntag else '')==norm(tt[0]): tag_exact_naive+=1
    if ts and ptag and norm(psub[0] if psub else '')==norm(ts[0]): sub_exact_llm+=1
    if ts and norm(nsub[0] if nsub else '')==norm(ts[0]): sub_exact_naive+=1
    tagF_llm+=field_score(ptag,tt); tagF_naive+=field_score(ntag,tt)
    subF_llm+=field_score(psub,ts); subF_naive+=field_score(nsub,ts)

print(f'predictions received: {n-missing}/{n} (missing {missing})')
print(f'\n=== EXACT primary-match accuracy ===')
print(f'  TAG    : LLM {100*tag_exact_llm/n:.0f}%   vs naive-NN {100*tag_exact_naive/n:.0f}%')
print(f'  SUBTAG : LLM {100*sub_exact_llm/n:.0f}%   vs naive-NN {100*sub_exact_naive/n:.0f}%')
print(f'\n=== FIELD-SCORE per finding (competition scoring, set-based) ===')
print(f'  TAG    : LLM {tagF_llm/n:.3f}   vs naive {tagF_naive/n:.3f}   gain {(tagF_llm-tagF_naive)/n:+.3f}/finding')
print(f'  SUBTAG : LLM {subF_llm/n:.3f}   vs naive {subF_naive/n:.3f}   gain {(subF_llm-subF_naive)/n:+.3f}/finding')
gain=(tagF_llm-tagF_naive+subF_llm-subF_naive)/n
print(f'\n  COMBINED tag+subtag gain: {gain:+.3f} per finding')
print(f'  >>> projected on ~150 guessed-tag test rows: {gain*150:+.0f} pts | on all 400: {gain*400:+.0f} pts')

import json, io, re, csv, random
from collections import Counter
import numpy as np
def norm(s): return re.sub(r'\s+',' ',str(s)).strip().lower()
hold=json.load(io.open('artifacts/tag_classifier/holdout.json',encoding='utf-8'))
gen ={p['id']:p for p in json.load(io.open('artifacts/tag_classifier/predictions.json',encoding='utf-8'))}     # generic few-shot
ret ={p['id']:p for p in json.load(io.open('artifacts/tag_classifier/predictions_retrieval.json',encoding='utf-8'))}
n=len(hold)
def acc(src):
    t=sum(1 for h in hold if h['truth_tag'] and src.get(h['id']) and norm(src[h['id']]['tag'])==norm(h['truth_tag'][0]))
    s=sum(1 for h in hold if h['truth_subtag'] and src.get(h['id']) and norm(src[h['id']]['subtag'])==norm(h['truth_subtag'][0]))
    return 100*t/n, 100*s/n
gt,gs=acc(gen); rt,rs=acc(ret)
print('=== TAG / SUBTAG exact accuracy on holdout ===')
print(f'  naive-NN baseline : TAG 24% / SUBTAG 11%')
print(f'  generic few-shot  : TAG {gt:.0f}% / SUBTAG {gs:.0f}%')
print(f'  RETRIEVAL few-shot: TAG {rt:.0f}% / SUBTAG {rs:.0f}%')
print(f'\n  retrieval vs generic: TAG {rt-gt:+.0f}pp  SUBTAG {rs-gs:+.0f}pp')
print('  >>> ' + ('RETRIEVAL WINS - use it for v14' if rt>gt+1 else 'no clear win - keep generic 3-pass'))

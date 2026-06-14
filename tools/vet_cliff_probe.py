import csv, sys, io, statistics, random
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
from sentence_transformers import SentenceTransformer
import numpy as np
m = SentenceTransformer('BAAI/bge-large-en-v1.5', local_files_only=True)
def emb(t): return m.encode(t, normalize_embeddings=True)
def cos(a,b): return float(np.dot(a,b))

rows = list(csv.DictReader(open('train.csv', encoding='utf-8')))
truths = [r['description'].strip() for r in rows if r['description'].strip()]
random.seed(7)

# Realistic: pred is a paraphrase of truth at varying fidelity. Approximate a
# "verbose" pred by truth + extra true detail, vs a "short" pred = truncated truth.
# We do NOT have separate canonical bodies, so the cleanest test of the exploit's
# mechanism is: starting from truncated (short) text, does restoring full length help,
# and does generic verbosity beyond the truth's own content help or hurt.

PAD_GENERIC = (" Specifically, the vulnerability arises because the affected function does not "
    "validate state transitions correctly, allowing an attacker to repeatedly call it and "
    "drain protocol funds, resulting in permanent loss for users and breaking core accounting invariants.")

near = []  # cosines in the cliff zone
for t in random.sample(truths, 120):
    w = t.split()
    if len(w) < 20: continue
    full = t
    short = ' '.join(w[:max(6,len(w)//3)])  # aggressive truncation ~1/3
    te = emb([full])[0]
    se = emb([short])[0]
    # pred against a DIFFERENT but same-tag-ish truth would be the real case; here
    # measure self-fidelity loss from truncation (upper bound on truncation harm)
    c_full = 1.0
    c_short = cos(te, se)
    # verbose-beyond-truth
    c_pad = cos(te, emb([full + PAD_GENERIC])[0])
    near.append((c_full, c_short, c_pad))

cs = [x[1] for x in near]; cp=[x[2] for x in near]
print(f'n={len(near)} truths >=20w')
print(f'truncate-to-third: mean cos to full-truth={statistics.mean(cs):.3f}  pct dropping below 0.7={100*sum(1 for x in cs if x<0.7)/len(cs):.0f}%')
print(f'full+generic-verbose-pad vs truth: mean={statistics.mean(cp):.3f}  (vs self=1.000, so pad COSTS {1-statistics.mean(cp):.3f})')

# Cliff-crossing count for truncation specifically
crossed = sum(1 for x in cs if x < 0.7)
print(f'Rows where AGGRESSIVE truncation alone pushed a perfect match below 0.7: {crossed}/{len(cs)}')

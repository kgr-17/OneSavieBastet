import csv, sys, io, statistics, random
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
from sentence_transformers import SentenceTransformer
import numpy as np

m = SentenceTransformer('BAAI/bge-large-en-v1.5', local_files_only=True)

def emb(texts):
    return m.encode(texts, normalize_embeddings=True)

def cos(a, b):
    return float(np.dot(a, b))

rows = list(csv.DictReader(open('train.csv', encoding='utf-8')))
truths = [r['description'].strip() for r in rows if r['description'].strip()]
random.seed(1337)
sample = random.sample(truths, 80)

# Generic verbose boilerplate padding to test "more detail helps" claim
PAD = (" The root cause of this issue lies in the contract logic. An attacker can exploit "
       "this vulnerability to manipulate state and cause loss of funds. The affected function "
       "fails to properly validate inputs and enforce the required invariants, leading to an "
       "incorrect computation that impacts user balances and protocol accounting under certain conditions.")

# Specific (fake but plausible) function-name padding
NAMEPAD = (" The function _updateRewards in the StakingRewards contract calls safeTransferFrom "
           "without checking the return value, and rewardPerToken() is computed before "
           "totalSupply is updated in the deposit() and withdraw() paths.")

results = {'self':[], 'pad_generic':[], 'pad_names':[], 'trunc16':[], 'trunc8':[]}
THRESH = 0.7

for t in sample:
    words = t.split()
    variants = {
        'self': t,
        'pad_generic': t + PAD,
        'pad_names': t + NAMEPAD,
        'trunc16': ' '.join(words[:16]),
        'trunc8': ' '.join(words[:8]),
    }
    te = emb([t])[0]
    ve = emb(list(variants.values()))
    for (k,_),e in zip(variants.items(), ve):
        results[k].append(cos(te, e))

print('=== Cosine of VARIANT vs its OWN truth (mean / %>0.7) ===')
for k,v in results.items():
    print(f'  {k:12s}: mean={statistics.mean(v):.3f}  pct>0.7={100*sum(1 for x in v if x>THRESH)/len(v):.0f}%')

# The REAL competition question: pred is NOT identical to truth. Simulate a
# "canonical short summary" pred vs "verbose canonical body" pred, both DIFFERENT
# from truth, by using a DIFFERENT finding's text as a stand-in paraphrase distance.
# Better: measure whether ADDING generic verbosity to a genuine-but-imperfect pred
# raises or lowers cosine to truth. Use cross pairs: pred = truth_j (j!=i) as a
# noisy proxy, then test pad effect.
print()
print('=== Pad effect on NON-identical preds (cross-finding proxy) ===')
base=[]; padded_g=[]; padded_n=[]
for i in range(0, 60, 2):
    t = sample[i]; p = sample[i+1]  # mismatched pred
    te = emb([t])[0]
    pe = emb([p, p+PAD, p+NAMEPAD])
    base.append(cos(te, pe[0]))
    padded_g.append(cos(te, pe[1]))
    padded_n.append(cos(te, pe[2]))
print(f'  base mismatch mean={statistics.mean(base):.3f}')
print(f'  +generic pad mean={statistics.mean(padded_g):.3f}  (delta {statistics.mean(padded_g)-statistics.mean(base):+.3f})')
print(f'  +name pad    mean={statistics.mean(padded_n):.3f}  (delta {statistics.mean(padded_n)-statistics.mean(base):+.3f})')

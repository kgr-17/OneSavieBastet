"""
Per-test-HASH analysis (the scorer keys on repo_path == test hash).
For each hash we know teammate's n_pred. The PER-HASH ground-truth count is unknown,
but dataset_0831 gives the per-AUDIT count. For audits with 1 hash, per-hash truth = audit count.
For gro (2 hashes, audit count 10) the split is unknown -> flag as uncertain.

We classify each teammate hash into:
  SAFE-COVERED : audit in 0831, single hash, n_pred <= audit_count  (no penalty, possibly deficit)
  OVER-COVERED : audit in 0831, single hash, n_pred > audit_count   (penalty!)
  UNCERTAIN    : gro dual-hash
  UNCOVERED    : audit NOT in 0831 at all (Rage Trade, Arrakis, sherlock-unknown, ...)
                 -> per FACTS these repos ARE in the test but annotation team logged 0 findings
                    for them in THIS 0831 snapshot. Whether they are in TRUTH is the key risk.
"""
import pandas as pd, json, os, sys
sys.stdout.reconfigure(encoding='utf-8')

ROOT = r'c:/OneSavieBastet'
m = json.load(open(os.path.join(ROOT,'artifacts/test_hash_to_contest_v3.json')))
t = pd.read_csv(os.path.join(ROOT,'outputs/submission_teammate442.csv'))
d = pd.read_csv(os.path.join(ROOT,'data/dataset_0831.csv'), encoding='utf-8-sig')

def audit_of(p):
    if not isinstance(p,str): return None
    parts = p.replace('\\','/').split('/')
    for seg in parts:
        if len(seg)>=7 and seg[0:2]=='20' and '-' in seg:
            return seg
    return parts[-1] if parts else None
d['audit'] = d['repo_path'].map(audit_of)
ds_counts = d['audit'].value_counts().to_dict()

from collections import defaultdict
c2h = defaultdict(list)
for k,v in m.items():
    c2h[v.get('contest')].append(k)

tm_by_hash = t['repo_path'].value_counts().to_dict()

print(f'{"hash":14s} {"contest":26s} {"npred":>5s} {"0831":>5s} {"class":12s}')
buckets = defaultdict(list)
for h, npred in sorted(tm_by_hash.items(), key=lambda x:-x[1]):
    info = m.get(h, {})
    c = info.get('contest')
    if c is None:
        cls='UNCOVERED'; truth='?'
        label = info.get('title_hint') or 'sherlock-unknown'
    elif c not in ds_counts:
        cls='UNCOVERED'; truth=0; label=c
    elif len(c2h[c])>1:
        cls='UNCERTAIN(split)'; truth=ds_counts[c]; label=c
    else:
        truth=ds_counts[c]; label=c
        cls = 'OVER-COVERED' if npred>truth else ('DEFICIT' if npred<truth else 'EXACT')
    buckets[cls].append((h,label,npred,truth))
    print(f'{h:14s} {str(label)[:26]:26s} {npred:5d} {str(truth):>5s} {cls:12s}')

print()
print('='*60)
print('SUMMARY BY CLASS')
print('='*60)
for cls in ['EXACT','DEFICIT','OVER-COVERED','UNCERTAIN(split)','UNCOVERED']:
    items = buckets.get(cls,[])
    nrows = sum(x[2] for x in items)
    print(f'{cls:18s}: {len(items):2d} hashes, {nrows:3d} teammate rows')

# the actionable reclaim pool = UNCOVERED rows (score ~0 if not in truth)
unc = buckets.get('UNCOVERED',[])
unc_rows = sum(x[2] for x in unc)
print()
print(f'RECLAIM POOL (UNCOVERED rows, score ~0 if absent from truth): {unc_rows} rows across {len(unc)} hashes')
print('  These are the lowest-risk rows to DROP (if uncovered repos are truly not in truth).')
print()
# deficit headroom
defi = buckets.get('DEFICIT',[])
defi_room = sum(x[3]-x[2] for x in defi)
print(f'DEFICIT headroom (covered repos under truth count): {defi_room} rows of room across {len(defi)} hashes')
print('Top deficit targets:')
for h,label,npred,truth in sorted(defi,key=lambda x:-(x[3]-x[2]))[:8]:
    print(f'  {label:24s} +{truth-npred} room (pred {npred} / truth {truth})')

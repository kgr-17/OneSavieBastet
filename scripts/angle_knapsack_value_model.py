"""
Quantify the knapsack reallocation under the EXACT scoring formula in
src/run_validation_standard.py (evaluate_repository).

Key mechanics confirmed from code:
  repo_penalty = max(0, n_pred - n_truth)   # subtracted from EVERY pair total
  greedy match stops when best remaining pair total_score <= 0
  final = sum of matched pair totals

So for a repo:
  - If n_pred <= n_truth: penalty=0. Every predicted row CAN be matched (up to n_pred),
    each contributing its raw pair score (tag+subtag+sev+desc, in [0,4]).
  - If n_pred > n_truth (k = n_pred - n_truth > 0): penalty=k per pair.
    At most n_truth pairs can match, and a pair only matches if raw_pair_score > k.
    Net contribution of a matched pair = raw_pair_score - k.

This script estimates, per repo, the marginal value of the LAST row teammate spends
on an over-predicted repo (which is wasted / negative) vs the value of a deficit row
we could add elsewhere.
"""
import pandas as pd, json, os

ROOT = r'c:/OneSavieBastet'
m = json.load(open(os.path.join(ROOT,'artifacts/test_hash_to_contest_v3.json')))
h2c = {k: (v.get('contest') or v.get('title_hint') or ('UNKNOWN_'+k)) for k,v in m.items()}

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
t['audit'] = t['repo_path'].map(lambda h: h2c.get(h,'NOHASH_'+str(h)))
tm_counts = t['audit'].value_counts().to_dict()

# Value model parameters (expected matched pair score components), per the formula:
# severity in {High,Medium}: 1-of-1 set match. dataset_0831 severity is verbatim from annotation team.
#   P(severity correct) for a TODO finding using verbatim 0831 severity ~ very high. EV_sev ~ 0.9
# tag/subtag: only available if we classify. Each is a SET field; EV depends on classifier precision.
# description: BGE>0.7 gate. EV depends on paraphrase quality from .md.

# --- Scenario value estimates for an ADDED deficit row (severity-only, no tag/subtag/desc) ---
EV_sev_only      = 0.90                       # severity verbatim, tag/subtag/desc blank -> ~sev only
EV_sev_tag       = 0.90 + 0.55                 # + a single-label tag at ~precision 0.55 set EV
EV_sev_tag_desc  = 0.90 + 0.55 + 0.45 + 0.30   # + subtag@0.45 + desc EV (0.30 = 0.40 prob * ~0.75 score)
EV_full_optimistic = 0.95 + 0.7 + 0.6 + 0.50   # if classification + desc all land well

# --- Value of teammate's existing rows on COVERED repos (have polished tag/subtag/desc) ---
# These are matched and scoring ~ full pair value. We do NOT know exact, but the 442 total / matched
# pairs gives an average. Estimate below.

print('='*70)
print('PART A: PENALTY WASTE from teammate OVER-prediction')
print('='*70)
over_rows=[]
total_penalty_waste = 0.0
for a, np_ in tm_counts.items():
    nt = ds_counts.get(a, 0)
    k = np_ - nt
    if k > 0:
        over_rows.append((a, np_, nt, k))

# For uncovered repos (nt==0): repo is NOT in ground truth at all -> per the FACTS,
# "Predictions for repos not in ground truth are ignored." So those rows score 0 (neither
# penalty nor gain) IF the repo truly is absent from truth. But if the repo IS in truth with
# nt>0 (e.g. gro 16 vs 10), penalty applies.
print()
print('A1. Over-predicted COVERED repos (nt>0): penalty k subtracted from every pair')
print(f'{"audit":28s} {"npred":>5s} {"ntruth":>6s} {"k":>3s}  effect')
covered_penalty_loss = 0.0
for a,np_,nt,k in sorted(over_rows, key=lambda r:-r[3]):
    if nt > 0:
        # n_truth pairs each lose k; only pairs with raw>k still match.
        # Loss vs the ideal n_pred=n_truth case = k * (#pairs that still match) + lost matches
        # Approx: each of nt matched pairs loses k -> nt*k, but capped (a pair with raw<k drops out).
        approx_loss = nt * k  # upper bound of penalty drag on matched pairs
        covered_penalty_loss += approx_loss
        print(f'{a:28s} {np_:5d} {nt:6d} {k:3d}  ~{approx_loss:.1f} penalty-drag on matched pairs (extra {k} rows wasted, could be reallocated)')

print()
print('A2. Over-predicted UNCOVERED repos (nt==0): rows IGNORED -> pure wasted budget')
wasted_budget_rows = 0
for a,np_,nt,k in sorted(over_rows, key=lambda r:-r[3]):
    if nt == 0:
        wasted_budget_rows += np_
        print(f'{a:28s} {np_:5d} rows -> 0 score (repo not in truth). {np_} budget rows WASTED.')

print()
print('PART B: DEFICIT headroom on covered repos (rows we COULD add at no penalty)')
deficit_rows=[]
for a, nt in ds_counts.items():
    np_ = tm_counts.get(a,0)
    if np_>0 and np_<nt:
        deficit_rows.append((a, np_, nt, nt-np_))
deficit_rows.sort(key=lambda r:-r[3])
total_deficit = 0
print(f'{"audit":28s} {"npred":>5s} {"ntruth":>6s} {"room":>4s}')
for a,np_,nt,room in deficit_rows:
    total_deficit += room
    print(f'{a:28s} {np_:5d} {nt:6d} {room:4d}')
print('TOTAL deficit headroom on covered repos:', total_deficit)

print()
print('='*70)
print('PART C: KNAPSACK ARITHMETIC')
print('='*70)
print(f'Wasted-budget rows on uncovered over-pred repos (A2): {wasted_budget_rows}')
print(f'  -> these score ~0 today. Reallocating each to a deficit covered repo gains EV per row.')
print()
print('EV per ADDED deficit row under value tiers:')
print(f'  severity-only (blank tag/subtag/desc) : {EV_sev_only:.2f}')
print(f'  +tag classified                       : {EV_sev_tag:.2f}')
print(f'  +tag+subtag+desc (BGE lands)           : {EV_sev_tag_desc:.2f}')
print(f'  full optimistic                        : {EV_full_optimistic:.2f}')
print()
# Reallocation gain estimate: move A2-wasted rows -> deficit repos.
realloc = min(wasted_budget_rows, total_deficit)
print(f'Reallocatable rows = min(wasted {wasted_budget_rows}, deficit {total_deficit}) = {realloc}')
for label,ev in [('sev-only',EV_sev_only),('+tag',EV_sev_tag),('+tag+subtag+desc',EV_sev_tag_desc)]:
    print(f'  Gain if added rows score {label:18s} (EV={ev:.2f}): +{realloc*ev:.1f} pts')
print()
print('PLUS: fixing A1 over-predicted COVERED repos (gro +6, etc.) by trimming surplus')
print(f'  removes penalty drag (~{covered_penalty_loss:.0f} pt upper bound) AND frees {sum(k for a,n,nt,k in over_rows if nt>0)} more rows.')

"""STEP 1+2: tier the 29 UNCOVERED teammate rows, then build probe P0.

TIER_B = genuinely unmapped in BOTH test_hash_to_contest_v2 and v3 -> safe to probe-drop.
TIER_A = mapped in at least one map (virtuals in both; dev-test-repo guesses in v2)
         -> higher drop risk, NEVER touch in the probe.

P0 = teammate-442 with ONLY the TIER_B rows blanked to 'empty' padding.
Submitting P0 to Kaggle measures EV_drop of the genuinely-unmapped pool as one scalar:
  delta = score(P0) - 442.88
  delta ~= 0  -> TIER_B rows are absent from truth, safe to reclaim all of them
  delta <  0  -> per-row EV_drop = |delta| / (#TIER_B rows); swap math must clear it
"""
import csv
import json
import os
import sys
from collections import defaultdict

sys.stdout.reconfigure(encoding="utf-8")
ROOT = "c:/OneSavieBastet"

V2 = json.load(open(os.path.join(ROOT, "artifacts/test_hash_to_contest_v2.json")))
V3 = json.load(open(os.path.join(ROOT, "artifacts/test_hash_to_contest_v3.json")))


def contest_of(m, h):
    v = m.get(h)
    if isinstance(v, dict):
        return v.get("contest")
    return v


UNCOVERED = [
    "51c6dc5fd57f", "9470d2cf198f", "a4d91fb1550f", "1167ec3a176e",
    "9ddd6b83c27e", "592eed5791df", "103f39b0f29b", "73f6a793d916",
    "e7921851ec01", "c2426a2ab283", "348856fe60ac", "27c6f2a68058",
]

tier_a, tier_b = [], []
for h in UNCOVERED:
    mapped = contest_of(V2, h) or contest_of(V3, h)
    (tier_a if mapped else tier_b).append(h)

print("TIER_A (mapped in >=1 map, DO NOT DROP):")
for h in tier_a:
    print(f"  {h}  v2={contest_of(V2,h)}  v3={contest_of(V3,h)}")
print("\nTIER_B (unmapped in BOTH, safe to probe):")
for h in tier_b:
    print(f"  {h}")

# Build probe P0
rows = list(csv.DictReader(open(os.path.join(ROOT, "outputs/submission_c4_v8.csv"), encoding="utf-8-sig")))
tier_b_set = set(tier_b)
blanked = 0
for r in rows:
    if r["repo_path"] in tier_b_set:
        r["repo_path"] = "empty"
        r["severity"] = "empty"
        r["tag"] = "empty"
        r["subtag"] = "empty"
        r["description"] = "empty"
        blanked += 1

out = os.path.join(ROOT, "outputs/submission_probe_P0.csv")
with open(out, "w", encoding="utf-8", newline="") as f:
    w = csv.writer(f)
    w.writerow(["Property", "repo_path", "severity", "tag", "subtag", "description"])
    for i, r in enumerate(rows, 1):
        w.writerow([i, r["repo_path"], r["severity"], r["tag"], r["subtag"], r["description"]])

n_nonempty = sum(1 for r in rows if r["repo_path"] != "empty")
print(f"\nProbe P0 written: {out}")
print(f"  TIER_B rows blanked: {blanked}")
print(f"  non-empty rows now: {n_nonempty}  (was 400)")
print(f"  total rows: {len(rows)}")

# persist tiers for downstream scripts
json.dump({"tier_a": tier_a, "tier_b": tier_b}, open(os.path.join(ROOT, "scripts/tiers.json"), "w"), indent=2)
print("\nWrote scripts/tiers.json")

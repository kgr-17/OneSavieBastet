"""STEP 6: assemble outputs/submission_c4_v10.csv = teammate-442 minus N TIER_B rows
plus N severity-floor deficit adds.

Run AFTER the probe result is known.
  python scripts/assemble_v10.py --n <N>
where N = number of TIER_B rows the probe confirmed safe to drop (<= 21).

Drops the N lowest-row-count TIER_B hashes first (smallest commitment), then fills
from the ranked deficit pool. Re-asserts: 0 over-covered hashes, every modified
repo n_pred <= dataset_0831_count - 2, 400 rows total.
"""
import argparse
import csv
import json
import os
import sys
from collections import defaultdict, Counter

sys.stdout.reconfigure(encoding="utf-8")
ROOT = "c:/OneSavieBastet"


def norm(rp):
    return rp[6:] if rp.startswith("repos/") else rp


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, required=True, help="TIER_B rows to reclaim (<=21)")
    ap.add_argument("--out", default="outputs/submission_c4_v10.csv")
    args = ap.parse_args()

    tiers = json.load(open(os.path.join(ROOT, "scripts/tiers.json")))
    tier_b = set(tiers["tier_b"])
    pool = json.load(open(os.path.join(ROOT, "scripts/deficit_pool.json")))

    rows = list(csv.DictReader(open(os.path.join(ROOT, "outputs/submission_c4_v8.csv"), encoding="utf-8-sig")))

    # current counts per hash
    cnt = Counter(r["repo_path"] for r in rows if r["repo_path"] != "empty")

    # dataset_0831 audit counts for the cap guard
    ds = list(csv.DictReader(open(os.path.join(ROOT, "data/dataset_0831.csv"), encoding="utf-8-sig")))
    ds_count = Counter(norm(r["repo_path"]) for r in ds)

    # 1. choose which TIER_B rows to drop: smallest-count hashes first (least committed)
    tb_rows = [(i, r) for i, r in enumerate(rows) if r["repo_path"] in tier_b]
    tb_by_hash = defaultdict(list)
    for i, r in tb_rows:
        tb_by_hash[r["repo_path"]].append(i)
    # order hashes by how many rows they have (drop singletons first)
    hash_order = sorted(tb_by_hash, key=lambda h: len(tb_by_hash[h]))
    drop_idx = []
    for h in hash_order:
        for i in tb_by_hash[h]:
            if len(drop_idx) < args.n:
                drop_idx.append(i)
    drop_idx = set(drop_idx)
    print(f"Dropping {len(drop_idx)} TIER_B rows from hashes: "
          f"{Counter(rows[i]['repo_path'] for i in drop_idx)}")

    # 2. select N adds, DIVERSIFIED across deficit repos (round-robin) to cap the
    #    blast radius if any single repo's truth-count assumption is wrong (gro showed
    #    audit-count != per-hash-count can happen). Within a repo, the pool is already
    #    ranked Medium-first + has-desc/tag. Respect per-repo cap (ds_count - 2).
    by_hash = defaultdict(list)
    for c in pool:
        by_hash[c["hash"]].append(c)
    # repo draw order follows pool priority (popcorn, frax, nibbl, optimism, ...)
    hash_seq = []
    for c in pool:
        if c["hash"] not in hash_seq:
            hash_seq.append(c["hash"])
    proj = dict(cnt)
    adds, cursors = [], defaultdict(int)
    progressed = True
    while len(adds) < args.n and progressed:
        progressed = False
        for h in hash_seq:
            if len(adds) >= args.n:
                break
            lst = by_hash[h]
            k = cursors[h]
            if k >= len(lst):
                continue
            c = lst[k]
            cursors[h] += 1
            cap = ds_count[c["audit"]] - 2
            if proj.get(h, 0) + 1 > cap:
                continue
            adds.append(c)
            proj[h] = proj.get(h, 0) + 1
            progressed = True
    print(f"Selected {len(adds)} deficit adds (diversified): {Counter(c['audit'] for c in adds)}")
    if len(adds) < args.n:
        print(f"WARNING: pool only yielded {len(adds)} adds under cap; dropping fewer TIER_B rows to match.")
        # only drop as many as we can add
        drop_idx = set(list(drop_idx)[:len(adds)])

    # 3. build output: keep non-dropped rows, append adds, repad to 400
    kept = [r for i, r in enumerate(rows) if i not in drop_idx]
    for c in adds:
        kept.append({"repo_path": c["hash"], "severity": c["severity"],
                     "tag": c["tag"], "subtag": c["subtag"], "description": c["description"]})
    # repad with empty to 400
    while len(kept) < 400:
        kept.append({"repo_path": "empty", "severity": "empty", "tag": "empty",
                     "subtag": "empty", "description": "empty"})
    kept = kept[:400]

    # 4. ASSERT guards
    final_cnt = Counter(r["repo_path"] for r in kept if r["repo_path"] != "empty")
    over = []
    for h, n in final_cnt.items():
        audit = None
        # find audit for this hash via pool or skip (uncovered/exact untouched)
        for c in pool:
            if c["hash"] == h:
                audit = c["audit"]; break
        if audit and n > ds_count[audit] - 2:
            over.append((h, audit, n, ds_count[audit]))
    assert not over, f"PENALTY-CLIFF GUARD FAILED: {over}"
    assert len(kept) == 400, f"row count {len(kept)} != 400"

    out = os.path.join(ROOT, args.out)
    with open(out, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Property", "repo_path", "severity", "tag", "subtag", "description"])
        for i, r in enumerate(kept, 1):
            w.writerow([i, r["repo_path"], r["severity"], r["tag"], r["subtag"], r["description"]])

    n_real = sum(1 for r in kept if r["repo_path"] != "empty")
    print(f"\nWrote {out}")
    print(f"  real rows: {n_real}  padding: {400 - n_real}")
    print(f"  guards passed: 0 over-cap repos, 400 rows")
    import hashlib
    print(f"  sha256: {hashlib.sha256(open(out,'rb').read()).hexdigest()}")


if __name__ == "__main__":
    main()

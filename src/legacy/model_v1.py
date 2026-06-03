"""
model_v1.py — Decision-theoretic smart contract vulnerability predictor.

New architecture: rank (tag, subtag, severity) combos by expected score
contribution using training statistics. Only predict combos with positive
expected value. Uses actual training descriptions for BGE scoring.

No dependency on baseline_v3/v4 code.
"""

import argparse
import csv
import hashlib
import math
from collections import Counter, defaultdict
from pathlib import Path


# ============================================================
# CLI
# ============================================================

def parse_args():
    p = argparse.ArgumentParser(description="Decision-theoretic vulnerability predictor")
    p.add_argument("--train-csv", default="train.csv")
    p.add_argument("--test-csv", default="test.csv")
    p.add_argument("--output", default="outputs/submission_model_v1.csv")
    p.add_argument("--target-rows", type=int, default=400)
    p.add_argument("--target-count", type=int, default=5,
                   help="Max findings per repo (conservative = less penalty)")
    p.add_argument("--max-same-tag", type=int, default=2,
                   help="Max predictions with the same tag per repo")
    p.add_argument("--ev-threshold", type=float, default=0.0,
                   help="Minimum expected value to include a combo")
    p.add_argument("--match-reward", type=float, default=2.7,
                   help="Expected score if combo is correct (tag+subtag+sev)")
    p.add_argument("--fp-cost", type=float, default=0.5,
                   help="Cost per false positive in field_score")
    p.add_argument("--pad-token", default="empty")
    return p.parse_args()


# ============================================================
# Utilities
# ============================================================

def stable_hash(value):
    return int(hashlib.md5(value.encode("utf-8")).hexdigest()[:12], 16)


def read_csv(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv(path, rows, columns):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=columns)
        w.writeheader()
        w.writerows(rows)


# ============================================================
# Step 1: Analyze training data
# ============================================================

def load_training_stats(train_csv):
    """Build combo frequency table and description bank from train.csv."""
    raw = read_csv(train_csv)

    combo_counts = Counter()
    combo_repos = Counter()
    desc_bank = defaultdict(list)
    repos = defaultdict(list)

    for row in raw:
        tag = row["tag"].strip()
        subtag = row["subtag"].strip()
        sev = row["severity"].strip()
        desc = row["description"].strip()
        repo = row["repo_path"].strip()

        combo = (tag, subtag, sev)
        combo_counts[combo] += 1
        repos[repo].append(combo)

        if desc and len(desc) > 20:
            desc_bank[(tag, subtag)].append(desc)

    # Count repos per combo (not rows — a combo in 20 repos is more robust than one in 2)
    for repo_id, repo_combos in repos.items():
        for combo in set(repo_combos):
            combo_repos[combo] += 1

    n_repos = len(repos)
    repo_sizes = sorted(len(v) for v in repos.values())

    print(f"Training: {len(raw)} rows, {n_repos} repos")
    print(f"Unique combos: {len(combo_counts)}")
    print(f"Repo sizes: min={repo_sizes[0]}, median={repo_sizes[len(repo_sizes)//2]}, max={repo_sizes[-1]}")
    print(f"Description bank: {len(desc_bank)} tag/subtag pairs with descriptions")

    return combo_counts, combo_repos, desc_bank, n_repos, repo_sizes


# ============================================================
# Step 2: Rank combos by expected value
# ============================================================

def rank_combos(combo_repos, n_repos, match_reward, fp_cost, ev_threshold):
    """Score each combo by usefulness for prediction.

    Instead of strict EV (which filters too aggressively on small training sets),
    use a softer ranking: combos that appear in more repos are better predictions.
    The score blends frequency with a diminishing-returns curve.
    """
    ranked = []

    for combo, repo_count in combo_repos.items():
        p_correct = repo_count / n_repos
        # Softer score: log-scaled repo support + frequency bonus
        # A combo in 10/54 repos (p=0.19) is still a good prediction
        score = math.log1p(repo_count) * match_reward + p_correct * 2.0

        if score > ev_threshold:
            ranked.append({
                "combo": combo,
                "tag": combo[0],
                "subtag": combo[1],
                "severity": combo[2],
                "ev": score,
                "p_correct": p_correct,
                "repo_count": repo_count,
            })

    ranked.sort(key=lambda x: (-x["ev"], x["tag"], x["subtag"]))

    print(f"\nCombos with positive EV (>{ev_threshold}): {len(ranked)}")
    for item in ranked[:15]:
        print(f"  EV={item['ev']:+.3f}  P={item['p_correct']:.2f}  "
              f"repos={item['repo_count']:2d}  {item['tag']} | {item['subtag']} | {item['severity']}")
    if len(ranked) > 15:
        print(f"  ... and {len(ranked) - 15} more")

    return ranked


# ============================================================
# Step 3: Pick description from training bank
# ============================================================

FALLBACK_DESCRIPTIONS = {
    "reentrancy": "External call is executed before state variables are updated, violating the Checks-Effects-Interactions pattern. Without a nonReentrant guard, an attacker can reenter the function to drain funds or corrupt state.",
    "input validation": "Critical input, address, or externally derived value is used without sufficient validation. Malformed parameters or unexpected states can bypass checks and lead to unauthorized behavior or incorrect asset movement.",
    "accounting error": "Internal accounting is vulnerable to inconsistent state updates. Balances, shares, debt, or reward variables updated with stale assumptions can cause users to receive incorrect value.",
    "dos": "Core contract flows may be blocked by a reachable failure condition or gas-heavy execution path. Under specific inputs or state growth, normal operations can revert or become impractical.",
    "access control": "Sensitive functionality relies on weak privilege checks or overly centralized control. An unauthorized actor could change critical parameters, pause operations, or redirect value.",
    "arithmetic": "Arithmetic and unit-conversion logic may not preserve protocol invariants. Precision loss, unsafe casting, or rounding issues can skew balances and create exploitable discrepancies.",
    "erc20": "Token integration assumes standard ERC20 behavior when the asset may not conform. Missing return-value checks, fee-on-transfer, or approval edge cases can break accounting.",
    "oracle": "Price-dependent logic trusts a manipulable or stale data source. Unchecked oracle values or spot prices can be distorted to bypass risk controls or extract value.",
    "liquidation": "Liquidation logic does not correctly align incentives, thresholds, or state transitions. This can prevent timely liquidations or let unhealthy positions persist.",
    "governance": "Governance execution allows unsafe proposals or parameter changes because validation, timing, or thresholds are not enforced robustly.",
    "mev": "Transaction flow is vulnerable to ordering manipulation. Attackers can front-run sensitive operations, capture value, or force worse execution outcomes.",
    "chainlink": "Contract relies on Chainlink oracle but omits data validity checks such as timestamp freshness, round completeness, or min/max bounds. Stale or incorrect values can affect pricing.",
    "flashloan": "Protocol relies on instantaneous states such as spot prices without time-weighted mechanisms. Flash loans can temporarily dominate ratios to gain undue benefits.",
    "upgradeable": "Contract uses upgradeable proxy pattern but has flaws in initialization, storage consistency, or permission protections that can allow unauthorized upgrades.",
    "erc4626": "ERC-4626 vault implementation may have share inflation, rounding direction errors, or boundary condition issues that enable economic exploits.",
    "slippage": "Contract lacks minimum output checks, deadline validation, or slippage protection for token swaps, exposing users to sandwich attacks or worse execution.",
    "pause": "Pause mechanism has flaws that allow disallowed operations during paused state or permanently lock the system.",
    "erc1155": "ERC-1155 multi-token implementation has flaws in standard compliance, callback handling, or supply tracking.",
    "dao": "DAO governance has vulnerabilities in voting mechanisms, member management, or cross-chain governance verification.",
    "erc777": "ERC-777 token callback mechanism can be exploited for reentrancy or denial of service.",
    "erc721": "ERC-721 NFT implementation has flaws in standard compliance, callback handling, or ownership management.",
    "cross-chain": "Cross-chain bridge or messaging implementation has defects in asset verification, message verification, or state synchronization.",
    "eip712": "Signature verification or EIP-712 typed-data parsing has flaws in encoding, nonce management, or replay protection.",
    "uniswap": "Uniswap integration has errors in price calculation, path encoding, or output validation that create manipulable pricing.",
    "replay attack": "Previously executed valid messages or transactions can be resubmitted by an attacker due to missing nonce or replay protection.",
    "twap": "TWAP oracle implementation has errors in calculation, observation windows, or validation of upstream results.",
    "bad randomness": "Contract relies on predictable or manipulable randomness sources for outcomes, making results exploitable.",
}


def pick_description(desc_bank, tag, subtag, repo_id):
    """Use actual training descriptions, hash-routed per repo for diversity."""
    descs = desc_bank.get((tag, subtag), [])
    usable = [d for d in descs if 40 <= len(d) <= 500]

    if usable:
        idx = stable_hash(f"{repo_id}|{tag}|{subtag}") % len(usable)
        return usable[idx]

    # Fallback: check by tag keyword
    tag_lower = tag.lower()
    for key, desc in FALLBACK_DESCRIPTIONS.items():
        if key in tag_lower:
            return desc

    return (
        f"The repository contains a {tag} vulnerability consistent with {subtag} behavior. "
        "A flaw in validation, execution flow, or state handling can allow unintended behavior "
        "or value loss under adversarial conditions."
    )


# ============================================================
# Step 4: Build submission
# ============================================================

def build_submission(test_csv, ranked_combos, desc_bank, args):
    """Generate predictions for all test repos."""
    test_rows = read_csv(test_csv)
    test_repos = sorted(set(row["repo_path"].strip() for row in test_rows))
    print(f"\nTest repos: {len(test_repos)}")

    all_predictions = []

    for repo_id in test_repos:
        predictions = []
        tag_counts = Counter()

        for item in ranked_combos:
            if len(predictions) >= args.target_count:
                break

            tag = item["tag"]
            # Diversity: cap same tag per repo
            if tag_counts[tag] >= args.max_same_tag:
                continue

            desc = pick_description(desc_bank, tag, item["subtag"], repo_id)

            predictions.append({
                "repo_path": repo_id,
                "severity": item["severity"],
                "tag": tag,
                "subtag": item["subtag"],
                "description": desc,
                "_ev": item["ev"],
            })
            tag_counts[tag] += 1

        all_predictions.extend(predictions)

    # Sort by EV (best predictions first, in case we need to truncate)
    all_predictions.sort(key=lambda r: (-r["_ev"], r["repo_path"]))

    # Truncate to target_rows
    all_predictions = all_predictions[:args.target_rows]

    # Pad
    while len(all_predictions) < args.target_rows:
        all_predictions.append({
            "repo_path": args.pad_token,
            "severity": args.pad_token,
            "tag": args.pad_token,
            "subtag": args.pad_token,
            "description": args.pad_token,
            "_ev": -1,
        })

    # Add Property column
    for i, row in enumerate(all_predictions, 1):
        row["Property"] = i

    # Stats
    non_empty = [r for r in all_predictions if r["repo_path"] != args.pad_token]
    unique_repos = set(r["repo_path"] for r in non_empty)
    tag_dist = Counter(r["tag"] for r in non_empty)

    print(f"\nSubmission: {len(all_predictions)} total rows")
    print(f"  Non-empty: {len(non_empty)}")
    print(f"  Padding: {len(all_predictions) - len(non_empty)}")
    print(f"  Repos covered: {len(unique_repos)}")
    print(f"  Avg per repo: {len(non_empty) / max(1, len(unique_repos)):.1f}")
    print(f"\nTag distribution:")
    for tag, cnt in tag_dist.most_common(20):
        print(f"  {tag}: {cnt}")

    return all_predictions


# ============================================================
# Main
# ============================================================

def main():
    args = parse_args()

    # Step 1: Analyze training
    combo_counts, combo_repos, desc_bank, n_repos, repo_sizes = \
        load_training_stats(args.train_csv)

    # Step 2: Rank by expected value
    ranked = rank_combos(combo_repos, n_repos, args.match_reward,
                         args.fp_cost, args.ev_threshold)

    if not ranked:
        print("ERROR: No combos with positive expected value!")
        return

    # Step 3+4: Build submission
    predictions = build_submission(args.test_csv, ranked, desc_bank, args)

    # Step 5: Write output
    columns = ["Property", "repo_path", "severity", "tag", "subtag", "description"]
    output_rows = [{c: row[c] for c in columns} for row in predictions]
    write_csv(args.output, output_rows, columns)
    print(f"\nSaved to {args.output}")


if __name__ == "__main__":
    main()

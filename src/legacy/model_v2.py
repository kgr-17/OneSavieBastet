"""
model_v2.py — Archetype-routed smart contract vulnerability predictor.

Extends model_v1 with:
1. Archetype router: scans repo code for imports/keywords -> classifies into
   coarse project types -> adjusts combo weights per archetype.
2. Adaptive target_count: LOC/contract_count -> conservative per-repo count.
3. Three sparse rule bonuses (high-precision only).

Designed to run on Kaggle with repo code available, or locally without code
(falls back to model_v1 behavior with conservative tc=5).
"""

import argparse
import csv
import hashlib
import math
import os
import re
from collections import Counter, defaultdict
from pathlib import Path


# ============================================================
# CLI
# ============================================================

def parse_args():
    p = argparse.ArgumentParser(description="Archetype-routed vulnerability predictor")
    p.add_argument("--train-csv", default="train.csv")
    p.add_argument("--test-csv", default="test.csv")
    p.add_argument("--output", default="outputs/submission_model_v2.csv")
    p.add_argument("--target-rows", type=int, default=400)
    p.add_argument("--base-target-count", type=int, default=5,
                   help="Default findings per repo when no code signal available")
    p.add_argument("--max-target-count", type=int, default=8,
                   help="Hard cap on findings per repo")
    p.add_argument("--max-same-tag", type=int, default=2,
                   help="Max predictions with the same tag per repo")
    p.add_argument("--ev-threshold", type=float, default=0.0)
    p.add_argument("--match-reward", type=float, default=2.7)
    p.add_argument("--archetype-lift-weight", type=float, default=0.3,
                   help="Weight of archetype lift vs global prior (0=pure v1, 1=full lift)")
    p.add_argument("--train-repo-root", default="",
                   help="Directory containing extracted train repos (for calibration)")
    p.add_argument("--test-repo-root", default="",
                   help="Directory containing extracted test repos (for routing)")
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
# Step 1: Training data analysis (from model_v1)
# ============================================================

def load_training_stats(train_csv):
    """Build combo frequency table and description bank from train.csv."""
    raw = read_csv(train_csv)

    combo_counts = Counter()
    combo_repos = Counter()
    desc_bank = defaultdict(list)
    repos = defaultdict(list)
    tag_repos = defaultdict(set)

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

        for t in tag.split(","):
            t = t.strip()
            if t:
                tag_repos[t].add(repo)

    for repo_id, repo_combos in repos.items():
        for combo in set(repo_combos):
            combo_repos[combo] += 1

    n_repos = len(repos)
    repo_sizes = sorted(len(v) for v in repos.values())

    print(f"Training: {len(raw)} rows, {n_repos} repos")
    print(f"Unique combos: {len(combo_counts)}")
    print(f"Repo sizes: min={repo_sizes[0]}, median={repo_sizes[len(repo_sizes)//2]}, max={repo_sizes[-1]}")

    return {
        "combo_counts": combo_counts,
        "combo_repos": combo_repos,
        "desc_bank": desc_bank,
        "repos": repos,
        "tag_repos": tag_repos,
        "n_repos": n_repos,
        "repo_sizes": repo_sizes,
    }


def rank_combos(combo_repos, n_repos, match_reward, ev_threshold):
    """Global prior ranking — same as model_v1."""
    ranked = []
    for combo, repo_count in combo_repos.items():
        p_correct = repo_count / n_repos
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

    print(f"\nGlobal combos with EV>{ev_threshold}: {len(ranked)}")
    for item in ranked[:10]:
        print(f"  EV={item['ev']:+.3f}  P={item['p_correct']:.2f}  "
              f"repos={item['repo_count']:2d}  {item['tag']} | {item['subtag']} | {item['severity']}")
    if len(ranked) > 10:
        print(f"  ... and {len(ranked) - 10} more")
    return ranked


# ============================================================
# Step 2: Feature extraction from repo code
# ============================================================

SKIP_DIRS = {"node_modules", ".git", "artifacts", "cache", "typechain",
             "__MACOSX", "build", ".deps", "out", "lib", "forge-std"}

ARCHETYPE_KEYWORDS = {
    "defi_oracle": [
        "aggregatorv3", "chainlink", "pricefeed", "latestround",
        "getreserves", "slot0", "twap", "liquidat", "collateral",
        "healthfactor", "borrowrate", "lendingpool", "comptroller",
        "ctoken", "atoken", "borrow", "repay",
    ],
    "defi_amm": [
        "uniswap", "sushiswap", "pancake", "balancer", "curve",
        "addliquidity", "removeliquidity", "flashloan", "flash(",
        "amountoutmin", "deadline",
    ],
    "token_nft": [
        "erc721", "erc1155", "nonfungible", "tokenuri", "safemint",
        "onerc721received", "onerc1155received", "tokensreceived",
        "erc777",
    ],
    "governance": [
        "governor", "timelock", "proposal", "votingperiod", "quorum",
        "castvote", "governorsettings", "governorcounting",
    ],
    "vault_erc4626": [
        "erc4626", "converttoassets", "converttoshares",
        "totalsupply", "totalassets", "previewdeposit",
        "previewredeem",
    ],
    "upgradeable": [
        "upgradeable", "initializ", "uups", "transparentproxy",
        "proxyadmin", "implementation", "delegatecall",
    ],
}

IMPORT_FAMILIES = {
    "openzeppelin": ["@openzeppelin", "openzeppelin"],
    "uniswap": ["@uniswap", "uniswapv2", "uniswapv3"],
    "chainlink": ["@chainlink", "aggregatorv3interface"],
    "aave": ["aave", "ilendingpool", "iatoken"],
    "compound": ["compound", "ctoken", "comptroller"],
}

# Sparse rule patterns — only 3 high-precision rules
SPARSE_RULES = [
    {
        "name": "callback_no_guard",
        "combo": ("Reentrancy", "Violating CEI / Missing nonReentrant", "High"),
        "bonus": 0.2,
        "match": [r"onERC721Received", r"onERC1155Received", r"tokensReceived"],
        "must_not": [r"nonReentrant", r"ReentrancyGuard"],
    },
    {
        "name": "unbounded_loop",
        "combo": ("DoS", "Out of Gas", "Medium"),
        "bonus": 0.1,
        "match": [r"for\s*\([^)]*;\s*[^;]*<\s*\w+\.length"],
        "must_not": [],
    },
    {
        "name": "unsafe_transfer",
        "combo": ("ERC20", "Missing Return Check", "Medium"),
        "bonus": 0.1,
        "match": [r"\.transfer\s*\(", r"\.transferFrom\s*\("],
        "must_not": [r"safeTransfer", r"safeTransferFrom"],
    },
]


def extract_repo_features(repo_dir):
    """Lightweight code scanner. Returns feature dict or None if no code."""
    repo_path = Path(repo_dir)
    if not repo_path.is_dir():
        return None

    sol_files = 0
    total_loc = 0
    contract_count = 0
    imports = []
    code_lower = []
    code_raw = []
    byte_budget = 200_000
    bytes_read = 0

    for root, dirs, files in os.walk(repo_path):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for fname in files:
            if not fname.endswith(".sol"):
                continue
            sol_files += 1
            fpath = Path(root) / fname
            try:
                text = fpath.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            total_loc += text.count("\n") + 1
            contract_count += len(re.findall(
                r"\b(?:contract|library|interface)\s+\w+", text
            ))
            for line in text.splitlines():
                stripped = line.strip()
                if stripped.startswith("import"):
                    imports.append(stripped.lower())
            if bytes_read < byte_budget:
                chunk = text[:byte_budget - bytes_read]
                code_lower.append(chunk.lower())
                code_raw.append(chunk)
                bytes_read += len(chunk)

    if sol_files == 0:
        return None

    full_lower = "\n".join(code_lower)
    full_raw = "\n".join(code_raw)
    import_text = " ".join(imports)

    # Archetype keyword hits
    keyword_hits = {}
    for arch, keywords in ARCHETYPE_KEYWORDS.items():
        hits = sum(1 for kw in keywords if kw in full_lower)
        keyword_hits[arch] = hits

    # Import family detection
    matched_families = set()
    for family, markers in IMPORT_FAMILIES.items():
        if any(m in import_text for m in markers):
            matched_families.add(family)

    # Sparse rule flags
    rule_flags = {}
    for rule in SPARSE_RULES:
        has_match = any(re.search(p, full_raw, re.IGNORECASE) for p in rule["match"])
        has_block = rule["must_not"] and any(
            re.search(p, full_raw, re.IGNORECASE) for p in rule["must_not"]
        )
        rule_flags[rule["name"]] = has_match and not has_block

    return {
        "sol_file_count": sol_files,
        "total_loc": total_loc,
        "contract_count": contract_count,
        "import_families": matched_families,
        "keyword_hits": keyword_hits,
        "rule_flags": rule_flags,
    }


# ============================================================
# Step 3: Archetype classification
# ============================================================

def classify_archetype(features):
    """Classify repo into archetype distribution. Returns {archetype: confidence}."""
    if features is None:
        return {"generic": 1.0}

    dist = {}
    max_conf = 0.0

    for arch, keywords in ARCHETYPE_KEYWORDS.items():
        n_keywords = len(keywords)
        hits = features["keyword_hits"].get(arch, 0)
        signal = hits / n_keywords if n_keywords > 0 else 0.0

        # Import family boost
        family_map = {
            "defi_oracle": ["chainlink", "aave", "compound"],
            "defi_amm": ["uniswap"],
            "token_nft": [],
            "governance": [],
            "vault_erc4626": [],
            "upgradeable": ["openzeppelin"],
        }
        for fam in family_map.get(arch, []):
            if fam in features["import_families"]:
                signal += 0.3

        if signal >= 0.15:
            dist[arch] = min(signal, 1.0)
            max_conf = max(max_conf, dist[arch])

    # Always include generic with residual confidence
    dist["generic"] = max(0.2, 1.0 - max_conf)
    return dist


# ============================================================
# Step 4: Archetype calibration from training data
# ============================================================

def calibrate_archetypes(train_stats, train_repo_root):
    """Build archetype lift tables from training repos.

    Returns:
        archetype_lifts: {archetype: {combo: lift_value}}
        archetype_desc_bank: {archetype: {(tag,subtag): [descriptions]}}
    """
    repos = train_stats["repos"]
    combo_repos = train_stats["combo_repos"]
    n_repos = train_stats["n_repos"]
    desc_bank = train_stats["desc_bank"]

    # Classify each train repo
    arch_repos = defaultdict(list)  # archetype -> [repo_id]
    arch_combos = defaultdict(lambda: defaultdict(int))  # archetype -> combo -> count

    for repo_id in repos:
        repo_dir = os.path.join(train_repo_root, repo_id) if train_repo_root else ""
        features = extract_repo_features(repo_dir) if repo_dir else None
        arch_dist = classify_archetype(features)

        # Assign repo to dominant archetype(s)
        for arch, conf in arch_dist.items():
            if conf >= 0.15 or arch == "generic":
                arch_repos[arch].append(repo_id)
                for combo in set(repos[repo_id]):
                    arch_combos[arch][combo] += 1

    # Compute lifts with Laplace smoothing
    n_combos = len(combo_repos)
    alpha = 0.5
    archetype_lifts = {}

    for arch in arch_repos:
        n_arch = len(arch_repos[arch])
        if n_arch < 2:
            continue
        lifts = {}
        for combo in combo_repos:
            p_global = combo_repos[combo] / n_repos
            count_in_arch = arch_combos[arch].get(combo, 0)
            p_arch = (count_in_arch + alpha) / (n_arch + alpha * n_combos)
            lift = p_arch - p_global
            lift = max(-0.5, min(0.5, lift))  # cap
            if abs(lift) > 0.02:
                lifts[combo] = lift
        archetype_lifts[arch] = lifts

    # Build archetype-specific description banks
    archetype_desc_bank = defaultdict(lambda: defaultdict(list))
    raw_rows = read_csv(train_stats.get("_train_csv_path", "train.csv"))
    repo_to_arch = {}
    for arch, rlist in arch_repos.items():
        for rid in rlist:
            repo_to_arch.setdefault(rid, []).append(arch)

    for row in raw_rows:
        repo = row["repo_path"].strip()
        tag = row["tag"].strip()
        subtag = row["subtag"].strip()
        desc = row["description"].strip()
        if desc and len(desc) > 20:
            for arch in repo_to_arch.get(repo, ["generic"]):
                archetype_desc_bank[arch][(tag, subtag)].append(desc)

    # Print calibration summary
    print(f"\nArchetype calibration ({len(arch_repos)} archetypes):")
    for arch in sorted(arch_repos):
        n = len(arch_repos[arch])
        n_lifts = len(archetype_lifts.get(arch, {}))
        top_lifts = sorted(
            archetype_lifts.get(arch, {}).items(),
            key=lambda x: -x[1]
        )[:3]
        top_str = ", ".join(f"{c[0]}:{v:+.2f}" for c, v in top_lifts)
        print(f"  {arch}: {n} repos, {n_lifts} lifted combos. Top: {top_str}")

    return dict(archetype_lifts), dict(archetype_desc_bank)


# Hardcoded fallback lifts (from offline training analysis, used when no code available)
HARDCODED_LIFTS = {
    "defi_oracle": {
        ("Oracle", "Price Manipulation / Arbitrage opportunity", "High"): 0.3,
        ("Chainlink", "Stale / Incorrect Value", "Medium"): 0.25,
        ("Liquidation", "No Incentive to Liquidate", "Medium"): 0.2,
        ("Arithmetic", "Precision Loss", "Medium"): 0.15,
    },
    "defi_amm": {
        ("MEV", "Front Run", "Medium"): 0.3,
        ("Flashloan", "Price Manipulation", "High"): 0.25,
        ("Slippage", "Missing Slippage Check", "Medium"): 0.2,
    },
    "token_nft": {
        ("Reentrancy", "Violating CEI / Missing nonReentrant", "High"): 0.35,
        ("ERC721", "Not Following the Standard", "Medium"): 0.2,
        ("ERC1155", "Not Following the Standard", "Medium"): 0.15,
    },
    "governance": {
        ("Governance", "Bad Condition", "Medium"): 0.3,
        ("Access Control", "Centralization Risk", "Medium"): 0.2,
        ("DoS", "Bad Condition", "Medium"): 0.15,
    },
    "vault_erc4626": {
        ("ERC4626", "Inflation Attack", "High"): 0.3,
        ("Arithmetic", "Precision Loss", "Medium"): 0.2,
        ("Accounting Error", "State Update Inconsistency", "Medium"): 0.15,
    },
    "upgradeable": {
        ("Upgradeable", "Missing Initializer", "High"): 0.3,
        ("Access Control", "Centralization Risk", "Medium"): 0.2,
        ("Input Validation", "Invalid Validation", "Medium"): 0.1,
    },
}


# ============================================================
# Step 5: Adaptive target count
# ============================================================

def compute_target_count(features, archetype_dist, base_count, max_count):
    """Estimate appropriate number of findings for this repo.

    Conservative: penalty for overpredicting is 3-8x worse than underpredicting.
    """
    if features is None:
        return base_count

    loc = features["total_loc"]
    contracts = features["contract_count"]

    # LOC-based buckets
    if loc < 200:
        count = 3
    elif loc < 500:
        count = 4
    elif loc < 1500:
        count = 5
    elif loc < 4000:
        count = 6
    else:
        count = 7

    # Contract-count adjustment
    if contracts <= 2 and count > 4:
        count = 4
    elif contracts >= 10 and count < 6:
        count = 6

    # Archetype adjustment
    dominant = max(archetype_dist, key=archetype_dist.get)
    dominant_conf = archetype_dist[dominant]

    if dominant == "generic" and dominant_conf > 0.7:
        count = max(3, count - 1)
    elif dominant in ("defi_oracle", "token_nft", "governance") and dominant_conf > 0.5:
        count = min(max_count, count + 1)

    return max(3, min(count, max_count))


# ============================================================
# Step 6: Descriptions (extended from model_v1)
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


def pick_description(desc_bank, archetype_desc_bank, archetype_dist,
                     tag, subtag, repo_id):
    """Pick description, preferring same-archetype descriptions when available."""
    # 1. Try archetype-specific bank
    if archetype_desc_bank:
        dominant = max(archetype_dist, key=archetype_dist.get)
        arch_descs = archetype_desc_bank.get(dominant, {}).get((tag, subtag), [])
        usable = [d for d in arch_descs if 40 <= len(d) <= 500]
        if usable:
            idx = stable_hash(f"{repo_id}|{tag}|{subtag}|arch") % len(usable)
            return usable[idx]

    # 2. Global description bank
    descs = desc_bank.get((tag, subtag), [])
    usable = [d for d in descs if 40 <= len(d) <= 500]
    if usable:
        idx = stable_hash(f"{repo_id}|{tag}|{subtag}") % len(usable)
        return usable[idx]

    # 3. Fallback descriptions
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
# Step 7: Build submission
# ============================================================

def compute_sparse_bonus(combo, features):
    """Return bonus score from sparse rules. Only 3 rules, high precision."""
    if features is None:
        return 0.0
    bonus = 0.0
    for rule in SPARSE_RULES:
        if combo == rule["combo"] and features["rule_flags"].get(rule["name"], False):
            bonus += rule["bonus"]
    return bonus


def build_submission(test_csv, test_repo_root, global_ranked, archetype_lifts,
                     archetype_desc_bank, desc_bank, args):
    """Generate predictions for all test repos with archetype routing."""
    test_rows = read_csv(test_csv)
    test_repos = sorted(set(row["repo_path"].strip() for row in test_rows))
    print(f"\nTest repos: {len(test_repos)}")

    all_predictions = []
    repo_diagnostics = []

    for repo_id in test_repos:
        # Extract features if code available
        repo_dir = os.path.join(test_repo_root, repo_id) if test_repo_root else ""
        features = extract_repo_features(repo_dir) if repo_dir else None
        arch_dist = classify_archetype(features)
        target_count = compute_target_count(
            features, arch_dist, args.base_target_count, args.max_target_count
        )

        # Score all combos for this repo
        scored = []
        for item in global_ranked:
            combo = item["combo"]
            score = item["ev"]  # global prior

            # Archetype lift
            for arch, conf in arch_dist.items():
                lift = archetype_lifts.get(arch, {}).get(combo, 0.0)
                score += args.archetype_lift_weight * conf * lift

            # Sparse rule bonus
            score += compute_sparse_bonus(combo, features)
            scored.append((score, item))

        scored.sort(key=lambda x: -x[0])

        # Select top-N with diversity constraint
        predictions = []
        tag_counts = Counter()
        for score, item in scored:
            if len(predictions) >= target_count:
                break
            tag = item["tag"]
            if tag_counts[tag] >= args.max_same_tag:
                continue

            desc = pick_description(
                desc_bank, archetype_desc_bank, arch_dist,
                tag, item["subtag"], repo_id
            )
            predictions.append({
                "repo_path": repo_id,
                "severity": item["severity"],
                "tag": tag,
                "subtag": item["subtag"],
                "description": desc,
                "_score": score,
            })
            tag_counts[tag] += 1

        all_predictions.extend(predictions)

        dominant = max(arch_dist, key=arch_dist.get)
        repo_diagnostics.append({
            "repo_id": repo_id,
            "archetype": dominant,
            "confidence": arch_dist[dominant],
            "target_count": target_count,
            "actual_count": len(predictions),
            "loc": features["total_loc"] if features else 0,
            "contracts": features["contract_count"] if features else 0,
        })

    # Sort by score, truncate to target_rows
    all_predictions.sort(key=lambda r: (-r["_score"], r["repo_path"]))
    all_predictions = all_predictions[:args.target_rows]

    # Pad
    while len(all_predictions) < args.target_rows:
        all_predictions.append({
            "repo_path": args.pad_token,
            "severity": args.pad_token,
            "tag": args.pad_token,
            "subtag": args.pad_token,
            "description": args.pad_token,
            "_score": -1,
        })

    # Property column
    for i, row in enumerate(all_predictions, 1):
        row["Property"] = i

    # Diagnostics
    non_empty = [r for r in all_predictions if r["repo_path"] != args.pad_token]
    unique_repos = set(r["repo_path"] for r in non_empty)
    tag_dist = Counter(r["tag"] for r in non_empty)
    avg_per_repo = len(non_empty) / max(1, len(unique_repos))
    arch_dist_summary = Counter(d["archetype"] for d in repo_diagnostics)

    print(f"\nSubmission: {len(all_predictions)} total rows")
    print(f"  Non-empty: {len(non_empty)}")
    print(f"  Padding: {len(all_predictions) - len(non_empty)}")
    print(f"  Repos covered: {len(unique_repos)}")
    print(f"  Avg per repo: {avg_per_repo:.1f}")
    if avg_per_repo > 6.5:
        print(f"  WARNING: avg per repo > 6.5 — risk of over-reporting penalty")

    print(f"\nTag distribution:")
    for tag, cnt in tag_dist.most_common(20):
        print(f"  {tag}: {cnt}")

    print(f"\nArchetype distribution:")
    for arch, cnt in arch_dist_summary.most_common():
        print(f"  {arch}: {cnt} repos")

    print(f"\nPer-repo details (sample):")
    for d in repo_diagnostics[:10]:
        print(f"  {d['repo_id'][:12]}: arch={d['archetype']}, "
              f"tc={d['target_count']}, loc={d['loc']}, contracts={d['contracts']}")

    return all_predictions


# ============================================================
# Main
# ============================================================

def main():
    args = parse_args()

    # Step 1: Training stats
    train_stats = load_training_stats(args.train_csv)
    train_stats["_train_csv_path"] = args.train_csv

    # Step 2: Global combo ranking
    ranked = rank_combos(
        train_stats["combo_repos"], train_stats["n_repos"],
        args.match_reward, args.ev_threshold
    )
    if not ranked:
        print("ERROR: No combos with positive expected value!")
        return

    # Step 3: Archetype calibration
    if args.train_repo_root and os.path.isdir(args.train_repo_root):
        print(f"\nCalibrating archetypes from {args.train_repo_root}...")
        archetype_lifts, archetype_desc_bank = calibrate_archetypes(
            train_stats, args.train_repo_root
        )
    else:
        print("\nNo train repo code available — using hardcoded archetype lifts")
        archetype_lifts = HARDCODED_LIFTS
        archetype_desc_bank = {}

    # Step 4: Build submission
    predictions = build_submission(
        args.test_csv, args.test_repo_root, ranked,
        archetype_lifts, archetype_desc_bank, train_stats["desc_bank"], args
    )

    # Step 5: Write output
    columns = ["Property", "repo_path", "severity", "tag", "subtag", "description"]
    output_rows = [{c: row[c] for c in columns} for row in predictions]
    write_csv(args.output, output_rows, columns)
    print(f"\nSaved to {args.output}")


if __name__ == "__main__":
    main()

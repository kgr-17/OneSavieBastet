# baseline_v7: Compound tag combos from training added to prior pool
# vs baseline_v4:
#   25.4% of truth rows have compound tags (e.g., "DoS, Input Validation")
#   v4 only predicted 1 compound row → gets 0.5 tag_score on those instead of 1.0
#   v7 adds a compound_seed_pool with top compound combos, included per repo
#   with a bonus score to ensure they appear in predictions
import argparse
import csv
import hashlib
import math
import os
import re
from collections import Counter, defaultdict
from pathlib import Path


EMPTY_TOKEN = "empty"
DEFAULT_TARGET_ROWS = 400
DEFAULT_MAX_FINDINGS_PER_REPO = 10
DEFAULT_PRIOR_POOL_SIZE = 40
DEFAULT_TAG_DIVERSITY_BONUS = 0.02
DEFAULT_REPEAT_TAG_PENALTY = 0.01
DEFAULT_MIN_FINDINGS_PER_REPO = 5
DEFAULT_HIGH_SEVERITY_POOL_SIZE = 0
DEFAULT_HIGH_SEVERITY_POOL_BONUS = 0.0
DEFAULT_INTRINSIC_HIGH_SEVERITY_BONUS = 0.0
DEFAULT_SCAN_EXTENSIONS = {".sol", ".vy", ".ts", ".js"}
DEFAULT_TOP_K_SIMILAR = 3
DEFAULT_SIMILARITY_THRESHOLD = 0.08
DEFAULT_BYTE_LIMIT = 300000


FINGERPRINT_KEYWORDS = [
    "transfer",
    "transferfrom",
    "approve",
    "allowance",
    "mint",
    "burn",
    "swap",
    "deposit",
    "withdraw",
    "liquidat",
    "oracle",
    "proxy",
    "delegatecall",
    "selfdestruct",
    "onlyowner",
    "require",
    "revert",
    "balanceof",
    "totalsupply",
    "stake",
    "reward",
    "flash",
    "loan",
    "borrow",
    "collateral",
    "repay",
    "governance",
    "vote",
    "proposal",
    "timelock",
    "permit",
    "signature",
    "ecrecover",
    "nonce",
    "erc20",
    "erc721",
    "erc1155",
    "upgradeable",
    "initializ",
    "ownable",
    "pausable",
    "reentrancy",
    "safetransfer",
    "unchecked",
    "assembly",
]


OBSERVED_RULES = [
    {
        "name": "reentrancy_value_call",
        "tag": "Reentrancy",
        "subtag": "Violating CEI / Missing nonReentrant",
        "severity": "High",
        "patterns": [r"\.call\s*\{[^}]*value\s*:"],
        "must_not": [r"nonReentrant", r"ReentrancyGuard"],
    },
    {
        "name": "reentrancy_callback",
        "tag": "Reentrancy",
        "subtag": "Violating CEI / Missing nonReentrant",
        "severity": "Medium",
        "patterns": [r"onERC721Received", r"onERC1155Received", r"tokensReceived"],
        "must_not": [r"nonReentrant", r"ReentrancyGuard"],
    },
    {
        "name": "invalid_validation_address",
        "tag": "Input Validation",
        "subtag": "Invalid Validation",
        "severity": "Medium",
        "patterns": [r"function\s+\w+\s*\([^)]*address\s+\w+"],
        "must_not": [r"address\s*\(\s*0\s*\)", r"!=\s*address\s*\(\s*0\s*\)"],
    },
    {
        "name": "invalid_validation_signature",
        "tag": "Input Validation",
        "subtag": "Invalid Validation",
        "severity": "High",
        "patterns": [r"ecrecover\s*\("],
        "must_not": [r"!=\s*address\s*\(\s*0\s*\)", r"\bs\s*<=", r"\bv\s*=="],
    },
    {
        "name": "dos_out_of_gas",
        "tag": "DoS",
        "subtag": "Out of Gas",
        "severity": "Medium",
        "patterns": [r"for\s*\([^)]*;\s*[^;]*<\s*\w+\.length\s*;", r"while\s*\("],
        "must_not": [],
    },
    {
        "name": "dos_receive",
        "tag": "DoS",
        "subtag": "payable / receive()",
        "severity": "Medium",
        "patterns": [r"\breceive\s*\(\s*\)\s*external\s*payable", r"\bfallback\s*\(\s*\)\s*external\s*payable"],
        "must_not": [],
    },
    {
        "name": "access_control_centralized",
        "tag": "Access Control",
        "subtag": "Centralization Risk",
        "severity": "Medium",
        "patterns": [r"function\s+(?:set|update|change|pause|unpause|mint|burn|withdraw)\w*\s*\([^)]*\)\s*(?:public|external)"],
        "must_not": [r"onlyOwner", r"onlyAdmin", r"onlyRole", r"AccessControl", r"Ownable"],
    },
    {
        "name": "erc20_missing_return_check",
        "tag": "ERC20",
        "subtag": "Missing Return Check",
        "severity": "Medium",
        "patterns": [r"\.(?:transfer|transferFrom)\s*\("],
        "must_not": [r"safeTransfer", r"safeTransferFrom", r"require\s*\([^)]*\.(?:transfer|transferFrom)"],
    },
    {
        "name": "erc20_safe_approve",
        "tag": "ERC20",
        "subtag": "safeApprove",
        "severity": "Medium",
        "patterns": [r"\.approve\s*\("],
        "must_not": [r"safeApprove", r"forceApprove", r"\.approve\s*\([^)]*,\s*0\s*\)"],
    },
    {
        "name": "arithmetic_precision_loss",
        "tag": "Arithmetic",
        "subtag": "Precision Loss",
        "severity": "Medium",
        "patterns": [r"\/\s*\w+\s*\*", r"\b\d+\s*/\s*\w+\s*\*"],
        "must_not": [],
    },
    {
        "name": "oracle_price_manipulation",
        "tag": "Oracle",
        "subtag": "Price Manipulation / Arbitrage opportunity",
        "severity": "High",
        "patterns": [r"getReserves\s*\(", r"slot0\s*\(", r"balanceOf\s*\([^)]*\)\s*[*/]"],
        "must_not": [],
    },
    {
        "name": "mev_front_run",
        "tag": "MEV",
        "subtag": "Front Run",
        "severity": "Medium",
        "patterns": [r"swap\w*\([^)]*,\s*0\s*[,)]]", r"deadline\s*=\s*block\.timestamp", r"block\.timestamp\s*\+\s*\d+"],
        "must_not": [],
    },
]


def parse_args():
    parser = argparse.ArgumentParser(
        description="Generate a stronger Bastet baseline inspired by rule + similarity ideas."
    )
    parser.add_argument("--train-csv", default="train.csv")
    parser.add_argument("--test-csv", default="test.csv")
    parser.add_argument("--sample-submission", default="submission_example.csv")
    parser.add_argument("--output", default="outputs/submission_v7.csv")
    parser.add_argument("--train-repo-root", default="", help="Optional directory containing extracted train repos.")
    parser.add_argument("--test-repo-root", default="", help="Optional directory containing extracted test repos.")
    parser.add_argument(
        "--mode",
        choices=["prior", "similarity", "hybrid"],
        default="hybrid",
        help="Prior works from CSVs only. Similarity/Hybrid use repo folders when provided.",
    )
    parser.add_argument("--target-rows", type=int, default=DEFAULT_TARGET_ROWS)
    parser.add_argument("--max-findings-per-repo", type=int, default=DEFAULT_MAX_FINDINGS_PER_REPO)
    parser.add_argument("--prior-pool-size", type=int, default=DEFAULT_PRIOR_POOL_SIZE)
    parser.add_argument("--tag-diversity-bonus", type=float, default=DEFAULT_TAG_DIVERSITY_BONUS)
    parser.add_argument("--repeat-tag-penalty", type=float, default=DEFAULT_REPEAT_TAG_PENALTY)
    parser.add_argument("--min-findings-per-repo", type=int, default=DEFAULT_MIN_FINDINGS_PER_REPO)
    parser.add_argument("--high-severity-pool-size", type=int, default=DEFAULT_HIGH_SEVERITY_POOL_SIZE)
    parser.add_argument("--high-severity-pool-bonus", type=float, default=DEFAULT_HIGH_SEVERITY_POOL_BONUS)
    parser.add_argument("--intrinsic-high-severity-bonus", type=float, default=DEFAULT_INTRINSIC_HIGH_SEVERITY_BONUS)
    parser.add_argument("--top-k-similar", type=int, default=DEFAULT_TOP_K_SIMILAR)
    parser.add_argument("--similarity-threshold", type=float, default=DEFAULT_SIMILARITY_THRESHOLD)
    parser.add_argument("--pad-token", default=EMPTY_TOKEN)
    return parser.parse_args()


def load_csv_rows(path):
    with open(path, newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv_rows(path, rows, fieldnames):
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def stable_hash(value):
    digest = hashlib.md5(value.encode("utf-8")).hexdigest()
    return int(digest[:12], 16)


def split_labels(raw_value):
    return [part.strip() for part in str(raw_value).split(",") if part.strip()]


def normalize_description(text):
    return " ".join(str(text).replace("\r", " ").replace("\n", " ").split())


def make_description(tag, subtag):
    combined = f"{tag.lower()} {subtag.lower()}"

    if "reentrancy" in combined or "cei" in combined or "callback" in combined:
        return (
            "The repository likely allows external control flow to re-enter sensitive logic before state "
            "updates are finalized. If value transfers or callback-enabled token interactions occur before "
            "critical accounting changes, an attacker may repeat actions, bypass intended sequencing, or drain funds."
        )
    if "input validation" in combined or "invalid validation" in combined or "incorrect parameter" in combined:
        return (
            "A critical input, address, signature, or externally derived value may be used without sufficient "
            "validation. Malformed parameters or unexpected states can pass checks and lead to unauthorized "
            "behavior, broken execution paths, or incorrect asset movement."
        )
    if "accounting error" in combined or "state update inconsistency" in combined or "incorrect formula" in combined:
        return (
            "Internal accounting appears vulnerable to inconsistent state updates. If balances, shares, debt, "
            "or reward variables are updated with stale assumptions or in the wrong order, users can receive "
            "incorrect value and protocol accounting can drift from reality."
        )
    if "dos" in combined or "out of gas" in combined or "bad condition" in combined or "payable / receive()" in combined:
        return (
            "Core contract flows may be blocked by a reachable failure condition or a gas-heavy execution path. "
            "Under specific inputs or state growth, normal operations can revert or become impractical to execute, "
            "creating a denial-of-service risk for users."
        )
    if "access control" in combined or "centralization risk" in combined or "role takeover" in combined:
        return (
            "Sensitive functionality may rely on weak privilege checks or an overly centralized control path. "
            "An unauthorized actor, compromised privileged key, or excessive admin power could change critical "
            "parameters, pause operations, or redirect value in ways users cannot prevent."
        )
    if "arithmetic" in combined or "precision loss" in combined or "rounding error" in combined or "token decimal" in combined:
        return (
            "Arithmetic and unit-conversion logic may not preserve protocol invariants. Precision loss, unsafe "
            "casting, or rounding issues can skew balances, prices, or share accounting and create exploitable "
            "value discrepancies over time."
        )
    if "erc20" in combined or "missing return check" in combined or "fee on transfer" in combined or "safeapprove" in combined:
        return (
            "Token integration logic may assume standard ERC20 behavior when the asset does not behave as expected. "
            "Missing return-value checks, fee-on-transfer behavior, or approval edge cases can break accounting and "
            "leave transfers or approvals in an unsafe state."
        )
    if "oracle" in combined or "price manipulation" in combined or "stale value" in combined:
        return (
            "Price-dependent logic may trust a manipulable or stale data source. If the protocol consumes an unchecked "
            "oracle value or spot price, attackers can distort valuations, bypass risk controls, or extract value "
            "during sensitive operations."
        )
    if "liquidation" in combined:
        return (
            "Liquidation logic may not correctly align incentives, thresholds, or state transitions. This can prevent "
            "timely liquidations, mis-handle collateral and debt, or let unhealthy positions persist longer than intended."
        )
    if "governance" in combined:
        return (
            "Governance execution may allow unsafe proposals or parameter changes because validation, timing, or "
            "decision thresholds are not enforced robustly. This can let privileged actions proceed in ways that "
            "harm users or protocol solvency."
        )
    if "mev" in combined or "front run" in combined:
        return (
            "The transaction flow may be vulnerable to ordering manipulation. Attackers or searchers can front-run "
            "sensitive operations, capture value, or force worse execution outcomes for honest users."
        )

    return (
        f"The repository likely contains a {tag} issue consistent with {subtag} behavior. A flaw in validation, "
        "execution flow, or state handling can allow unintended behavior, blocked execution, or value loss under "
        "adversarial conditions."
    )


def pick_representative_description(descriptions, tag, subtag):
    if not descriptions:
        return make_description(tag, subtag)

    for description in sorted(descriptions, key=lambda item: (-len(item), item)):
        if 80 <= len(description) <= 420:
            return description

    first = descriptions[0]
    return first if len(first) <= 420 else make_description(tag, subtag)


def build_train_summary(train_rows, max_findings_per_repo, prior_pool_size, high_severity_pool_size):
    train_rows_by_repo = defaultdict(list)
    combo_counts = Counter()
    combo_repo_counts = Counter()
    tag_repo_counts = Counter()
    description_bank = defaultdict(list)

    for row in train_rows:
        repo_id = row["repo_path"].strip()
        tag = row["tag"].strip()
        subtag = row["subtag"].strip()
        severity = row["severity"].strip()
        description = normalize_description(row["description"])

        train_rows_by_repo[repo_id].append(row)
        combo = (tag, subtag, severity)
        combo_counts[combo] += 1
        if description:
            description_bank[combo].append(description)

    for rows in train_rows_by_repo.values():
        seen_combos = set()
        seen_tags = set()
        for row in rows:
            combo = (row["tag"].strip(), row["subtag"].strip(), row["severity"].strip())
            if combo not in seen_combos:
                combo_repo_counts[combo] += 1
                seen_combos.add(combo)
            for tag_token in split_labels(row["tag"]):
                seen_tags.add(tag_token)
        for tag_token in seen_tags:
            tag_repo_counts[tag_token] += 1

    repo_size_samples = [
        max(2, min(len(rows), max_findings_per_repo))
        for rows in train_rows_by_repo.values()
    ]

    combo_rankings = sorted(
        combo_counts,
        key=lambda combo: (
            -combo_repo_counts[combo],
            -combo_counts[combo],
            0 if combo[2] == "High" else 1,
            combo[0],
            combo[1],
        ),
    )

    def make_prior_item(combo):
        tag, subtag, severity = combo
        descriptions = description_bank[combo]
        return {
            "tag": tag,
            "subtag": subtag,
            "severity": severity,
            "support": combo_counts[combo],
            "repo_support": combo_repo_counts[combo],
            "description": pick_representative_description(descriptions, tag, subtag),
        }

    prior_pool = [make_prior_item(combo) for combo in combo_rankings[:prior_pool_size]]

    tag_seed_pool = []
    seeded_combos = set()
    for tag_token, _ in tag_repo_counts.most_common(16):
        added = 0
        for combo in combo_rankings:
            if combo in seeded_combos:
                continue
            if tag_token not in split_labels(combo[0]):
                continue
            tag_seed_pool.append(make_prior_item(combo))
            seeded_combos.add(combo)
            added += 1
            if added >= 2:
                break

    high_severity_pool = []
    if high_severity_pool_size > 0:
        for combo in combo_rankings:
            if combo[2] != "High":
                continue
            high_severity_pool.append(make_prior_item(combo))
            if len(high_severity_pool) >= high_severity_pool_size:
                break

    # v7: compound tag pool — combos where tag has a comma (e.g. "DoS, Input Validation")
    # 25.4% of training truth rows have compound tags; prior_pool has almost none.
    # Adding compound combos helps match those truth rows at full tag_score (1.0) vs partial (0.5).
    compound_seed_pool = []
    compound_seeded = set()
    for combo in combo_rankings:
        tag = combo[0]
        if "," not in tag:
            continue
        if combo in compound_seeded:
            continue
        compound_seed_pool.append(make_prior_item(combo))
        compound_seeded.add(combo)
        if len(compound_seed_pool) >= 15:
            break

    return {
        "rows_by_repo": train_rows_by_repo,
        "combo_counts": combo_counts,
        "combo_repo_counts": combo_repo_counts,
        "tag_repo_counts": tag_repo_counts,
        "prior_pool": prior_pool,
        "tag_seed_pool": tag_seed_pool,
        "high_severity_pool": high_severity_pool,
        "compound_seed_pool": compound_seed_pool,
        "repo_size_samples": repo_size_samples,
    }


def list_repo_files(repo_dir):
    files = []
    for root, _, filenames in os.walk(repo_dir):
        for filename in filenames:
            extension = Path(filename).suffix.lower()
            if extension in DEFAULT_SCAN_EXTENSIONS:
                files.append(Path(root) / filename)
    return sorted(files)


def load_repo_text(repo_dir, byte_limit=DEFAULT_BYTE_LIMIT):
    parts = []
    total = 0
    for path in list_repo_files(repo_dir):
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if not text:
            continue
        rel_name = path.name
        chunk = f"\n// FILE: {rel_name}\n{text}"
        parts.append(chunk)
        total += len(chunk)
        if total >= byte_limit:
            break
    return "\n".join(parts)


def get_code_fingerprint(code):
    code_lower = code.lower()
    return {keyword: code_lower.count(keyword) for keyword in FINGERPRINT_KEYWORDS}


def cosine_similarity(left, right):
    all_keys = set(left) | set(right)
    dot = sum(left.get(key, 0) * right.get(key, 0) for key in all_keys)
    mag_left = math.sqrt(sum(value * value for value in left.values()))
    mag_right = math.sqrt(sum(value * value for value in right.values()))
    if mag_left == 0 or mag_right == 0:
        return 0.0
    return dot / (mag_left * mag_right)


def load_repo_index(repo_ids, repo_root):
    if not repo_root:
        return {}, {}

    root_path = Path(repo_root)
    if not root_path.is_dir():
        return {}, {}

    text_by_repo = {}
    fingerprint_by_repo = {}
    for repo_id in repo_ids:
        repo_dir = root_path / repo_id
        if not repo_dir.is_dir():
            continue
        text = load_repo_text(repo_dir)
        if not text:
            continue
        text_by_repo[repo_id] = text
        fingerprint_by_repo[repo_id] = get_code_fingerprint(text)
    return text_by_repo, fingerprint_by_repo


def rule_matches_text(rule, repo_text):
    if not any(re.search(pattern, repo_text, re.IGNORECASE | re.DOTALL) for pattern in rule["patterns"]):
        return False
    if rule["must_not"] and any(re.search(pattern, repo_text, re.IGNORECASE | re.DOTALL) for pattern in rule["must_not"]):
        return False
    return True


def combo_matches_row(tag, subtag, row):
    return tag in split_labels(row["tag"]) and subtag in split_labels(row["subtag"])


def calibrate_rules(train_text_by_repo, train_rows_by_repo):
    if not train_text_by_repo:
        return {rule["name"] for rule in OBSERVED_RULES}

    kept = set()
    for rule in OBSERVED_RULES:
        hits = 0
        true_hits = 0
        for repo_id, repo_text in train_text_by_repo.items():
            if not rule_matches_text(rule, repo_text):
                continue
            hits += 1
            if any(combo_matches_row(rule["tag"], rule["subtag"], row) for row in train_rows_by_repo.get(repo_id, [])):
                true_hits += 1
        precision = true_hits / hits if hits else 0.0
        if hits >= 2 and precision >= 0.15:
            kept.add(rule["name"])
    return kept if kept else {rule["name"] for rule in OBSERVED_RULES[:6]}


def choose_target_count(repo_id, repo_size_samples, max_findings_per_repo, min_floor=1):
    """v7: min_floor parameter replaces the hard-coded max(3,...) floor.
    Allows small repos to get fewer predictions, reducing over-reporting penalty.
    min_floor is typically overridden by args.min_findings_per_repo in build_submission_rows.
    """
    if not repo_size_samples:
        return min(6, max_findings_per_repo)

    sorted_samples = sorted(repo_size_samples)
    index = stable_hash(repo_id) % len(sorted_samples)
    sampled = sorted_samples[index]

    if sampled <= 2:
        sampled += 1
    elif sampled <= 5:
        sampled += 1

    return max(min_floor, min(sampled, max_findings_per_repo))


def collect_similarity_candidates(
    test_fingerprint,
    train_fingerprints,
    train_rows_by_repo,
    combo_counts,
    top_k,
    threshold,
):
    candidates = []
    if not test_fingerprint or not train_fingerprints:
        return candidates, []

    scores = []
    for train_repo_id, train_fingerprint in train_fingerprints.items():
        similarity = cosine_similarity(test_fingerprint, train_fingerprint)
        if similarity > 0:
            scores.append((train_repo_id, similarity))

    scores.sort(key=lambda item: item[1], reverse=True)
    top_repos = [(repo_id, similarity) for repo_id, similarity in scores[:top_k] if similarity >= threshold]

    for train_repo_id, similarity in top_repos:
        for row in train_rows_by_repo.get(train_repo_id, []):
            tag = row["tag"].strip()
            subtag = row["subtag"].strip()
            severity = row["severity"].strip()
            description = normalize_description(row["description"])
            combo = (tag, subtag, severity)
            support = combo_counts.get(combo, 1)
            score = similarity * (1.0 + math.log1p(support))
            candidates.append(
                {
                    "tag": tag,
                    "subtag": subtag,
                    "severity": severity,
                    "description": description if description else make_description(tag, subtag),
                    "score": score,
                    "source": f"similarity:{train_repo_id}",
                }
            )

    return candidates, top_repos


def collect_rule_candidates(repo_text, calibrated_rule_names):
    candidates = []
    if not repo_text:
        return candidates

    for rule in OBSERVED_RULES:
        if rule["name"] not in calibrated_rule_names:
            continue
        if not rule_matches_text(rule, repo_text):
            continue
        candidates.append(
            {
                "tag": rule["tag"],
                "subtag": rule["subtag"],
                "severity": rule["severity"],
                "description": make_description(rule["tag"], rule["subtag"]),
                "score": 1.35 if rule["severity"] == "High" else 1.0,
                "source": f"rule:{rule['name']}",
            }
        )
    return candidates


def collect_prior_candidates(repo_id, train_summary, args):
    candidates = []
    prior_pool = train_summary["prior_pool"]
    tag_seed_pool = train_summary["tag_seed_pool"]
    high_severity_pool = train_summary["high_severity_pool"]
    compound_seed_pool = train_summary.get("compound_seed_pool", [])

    def append_candidate(item, index, source, source_bonus=0.0):
        score = 0.26 + math.log1p(item["repo_support"]) * 0.14 + math.log1p(item["support"]) * 0.05
        score += args.intrinsic_high_severity_bonus if item["severity"] == "High" else 0.0
        score += source_bonus
        score -= index * 0.0025
        candidates.append(
            {
                "tag": item["tag"],
                "subtag": item["subtag"],
                "severity": item["severity"],
                "description": item["description"],
                "score": score,
                "source": source,
            }
        )

    if prior_pool:
        offset = stable_hash(repo_id) % len(prior_pool)
        window = min(len(prior_pool), 30)
        stride = max(1, len(prior_pool) // max(1, window))
        for index in range(window):
            item = prior_pool[(offset + index * stride) % len(prior_pool)]
            append_candidate(item, index, "prior")

    if tag_seed_pool:
        offset = stable_hash(repo_id + ":tag") % len(tag_seed_pool)
        window = min(len(tag_seed_pool), 20)
        for index in range(window):
            item = tag_seed_pool[(offset + index) % len(tag_seed_pool)]
            append_candidate(item, index, "tag-seed", source_bonus=0.05)

    if high_severity_pool:
        offset = stable_hash(repo_id + ":high") % len(high_severity_pool)
        window = min(len(high_severity_pool), 10)
        for index in range(window):
            item = high_severity_pool[(offset + index) % len(high_severity_pool)]
            append_candidate(item, index, "high-severity", source_bonus=args.high_severity_pool_bonus)

    # v7: compound tag seed pool — adds top compound-tag combos for every repo.
    # ~25% of truth rows have compound tags (e.g., "DoS, Input Validation").
    # Predicting compound tags gives full tag_score (1.0) when truth matches,
    # vs 0.5 if only one component is predicted.
    if compound_seed_pool:
        for index, item in enumerate(compound_seed_pool):
            append_candidate(item, index, "compound-seed", source_bonus=0.03)

    return candidates


def merge_candidates(candidate_lists):
    merged = {}
    for candidate in candidate_lists:
        key = (candidate["tag"], candidate["subtag"], candidate["severity"])
        current = merged.get(key)
        if current is None or candidate["score"] > current["score"]:
            merged[key] = candidate
    return list(merged.values())


def rank_candidates(candidates):
    severity_order = {"High": 0, "Medium": 1}
    return sorted(
        candidates,
        key=lambda item: (
            -item["score"],
            severity_order.get(item["severity"], 2),
            item["tag"],
            item["subtag"],
        ),
    )


def candidate_tag_tokens(candidate):
    tags = split_labels(candidate["tag"])
    return tags if tags else [candidate["tag"]]


def pick_diverse_candidates(candidates, target_count, tag_diversity_bonus, repeat_tag_penalty):
    severity_order = {"High": 0, "Medium": 1}
    remaining = rank_candidates(candidates)
    selected = []
    seen_tags = Counter()
    seen_subtags = Counter()

    while remaining and len(selected) < target_count:
        best_index = 0
        best_key = None

        for index, candidate in enumerate(remaining):
            tag_tokens = candidate_tag_tokens(candidate)
            new_tag_count = sum(1 for tag in tag_tokens if seen_tags[tag] == 0)
            repeated_tag_count = sum(seen_tags[tag] for tag in tag_tokens)
            repeated_subtag_count = seen_subtags[candidate["subtag"]]
            adjusted_score = candidate["score"] + new_tag_count * tag_diversity_bonus
            adjusted_score -= repeated_tag_count * repeat_tag_penalty
            adjusted_score -= repeated_subtag_count * (repeat_tag_penalty * 0.6)
            if candidate["severity"] == "High" and new_tag_count:
                adjusted_score += 0.01

            key = (
                adjusted_score,
                new_tag_count,
                -repeated_tag_count,
                -repeated_subtag_count,
                -severity_order.get(candidate["severity"], 2),
                candidate["score"],
                candidate["tag"],
                candidate["subtag"],
            )
            if best_key is None or key > best_key:
                best_key = key
                best_index = index

        picked = remaining.pop(best_index)
        selected.append(picked)
        for tag in candidate_tag_tokens(picked):
            seen_tags[tag] += 1
        seen_subtags[picked["subtag"]] += 1

    return selected


def build_submission_rows(args, train_summary, test_repo_ids, train_text_by_repo, train_fingerprints, test_text_by_repo, test_fingerprints):
    all_rows = []
    calibrated_rule_names = calibrate_rules(train_text_by_repo, train_summary["rows_by_repo"])

    for repo_id in test_repo_ids:
        target_count = choose_target_count(
            repo_id,
            train_summary["repo_size_samples"],
            args.max_findings_per_repo,
            min_floor=args.min_findings_per_repo,
        )
        repo_text = test_text_by_repo.get(repo_id, "")
        repo_fingerprint = test_fingerprints.get(repo_id, {})

        candidate_pool = []
        similar_repos = []

        if args.mode in {"similarity", "hybrid"} and repo_text:
            similarity_candidates, similar_repos = collect_similarity_candidates(
                repo_fingerprint,
                train_fingerprints,
                train_summary["rows_by_repo"],
                train_summary["combo_counts"],
                args.top_k_similar,
                args.similarity_threshold,
            )
            candidate_pool.extend(similarity_candidates)
            candidate_pool.extend(collect_rule_candidates(repo_text, calibrated_rule_names))

            if similar_repos:
                top_similarity = similar_repos[0][1]
                if top_similarity >= 0.6:
                    target_count = min(args.max_findings_per_repo, target_count + 1)
                elif top_similarity < 0.2:
                    target_count = max(2, target_count - 1)

        if args.mode in {"prior", "hybrid"} or not candidate_pool:
            candidate_pool.extend(collect_prior_candidates(repo_id, train_summary, args))

        merged_candidates = merge_candidates(candidate_pool)
        picked = pick_diverse_candidates(merged_candidates, target_count, args.tag_diversity_bonus, args.repeat_tag_penalty)

        for candidate in picked:
            all_rows.append(
                {
                    "Property": 0,
                    "repo_path": repo_id,
                    "severity": candidate["severity"],
                    "tag": candidate["tag"],
                    "subtag": candidate["subtag"],
                    "description": candidate["description"],
                    "_score": candidate["score"],
                }
            )

    all_rows.sort(key=lambda row: (-row["_score"], row["repo_path"], row["tag"], row["subtag"]))
    all_rows = all_rows[: args.target_rows]

    while len(all_rows) < args.target_rows:
        all_rows.append(
            {
                "Property": 0,
                "repo_path": args.pad_token,
                "severity": args.pad_token,
                "tag": args.pad_token,
                "subtag": args.pad_token,
                "description": args.pad_token,
                "_score": -1.0,
            }
        )

    for index, row in enumerate(all_rows, start=1):
        row["Property"] = index

    return all_rows


def validate_output(rows, expected_columns, target_rows, pad_token):
    if len(rows) != target_rows:
        raise ValueError(f"Expected {target_rows} rows, found {len(rows)}")

    projected = [{column: row[column] for column in expected_columns} for row in rows]
    if list(projected[0].keys()) != expected_columns:
        raise ValueError("Column mismatch in generated rows.")

    non_empty_rows = [row for row in rows if row["repo_path"] != pad_token]
    unique_repos = sorted({row["repo_path"] for row in non_empty_rows})

    return {
        "total_rows": len(rows),
        "non_empty_rows": len(non_empty_rows),
        "empty_rows": len(rows) - len(non_empty_rows),
        "unique_predicted_repos": len(unique_repos),
    }


def main():
    args = parse_args()
    train_rows = load_csv_rows(args.train_csv)
    test_rows = load_csv_rows(args.test_csv)
    sample_rows = load_csv_rows(args.sample_submission)

    if not sample_rows:
        raise ValueError("Sample submission is empty.")

    expected_columns = list(sample_rows[0].keys())
    test_repo_ids = [row["repo_path"].strip() for row in test_rows if row.get("repo_path", "").strip()]
    train_repo_ids = sorted({row["repo_path"].strip() for row in train_rows if row.get("repo_path", "").strip()})

    train_summary = build_train_summary(train_rows, args.max_findings_per_repo, args.prior_pool_size, args.high_severity_pool_size)
    train_text_by_repo, train_fingerprints = load_repo_index(train_repo_ids, args.train_repo_root.strip())
    test_text_by_repo, test_fingerprints = load_repo_index(test_repo_ids, args.test_repo_root.strip())

    generated_rows = build_submission_rows(
        args,
        train_summary,
        test_repo_ids,
        train_text_by_repo,
        train_fingerprints,
        test_text_by_repo,
        test_fingerprints,
    )

    stats = validate_output(generated_rows, expected_columns, args.target_rows, args.pad_token)
    final_rows = [{column: row[column] for column in expected_columns} for row in generated_rows]
    write_csv_rows(args.output, final_rows, expected_columns)

    print("Baseline v4 submission generated successfully.")
    print(f"Output: {args.output}")
    print(f"Mode: {args.mode}")
    print(f"Train repos with code: {len(train_text_by_repo)}")
    print(f"Test repos with code: {len(test_text_by_repo)}")
    print(f"Predicted rows: {stats['non_empty_rows']}")
    print(f"Padding rows: {stats['empty_rows']}")
    print(f"Unique repos covered: {stats['unique_predicted_repos']}")
    print("Top prior templates used:")
    for item in train_summary["prior_pool"][:5]:
        print(f"  - [{item['severity']}] {item['tag']} | {item['subtag']} (repo_support={item['repo_support']}, row_support={item['support']})")
    print(f"Tag seed templates: {len(train_summary['tag_seed_pool'])}")
    print(f"High-severity templates: {len(train_summary['high_severity_pool'])}")


if __name__ == "__main__":
    main()

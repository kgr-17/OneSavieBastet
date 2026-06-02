import argparse
import csv
import os
import re
from collections import Counter
from pathlib import Path


EMPTY_TOKEN = "empty"
DEFAULT_TARGET_ROWS = 400
DEFAULT_FINDINGS_PER_REPO = 3
DEFAULT_TEMPLATE_POOL_SIZE = 8
DEFAULT_SCAN_EXTENSIONS = {".sol", ".vy", ".ts", ".js"}


HEURISTIC_RULES = [
    {
        "name": "reentrancy",
        "tag": "Reentrancy",
        "subtag": "Violating CEI / Missing nonReentrant",
        "severity": "High",
        "patterns": [r"\.call\s*\{[^}]*value\s*:", r"\.call\s*\("],
        "must_not": [r"nonReentrant", r"ReentrancyGuard"],
    },
    {
        "name": "input_validation",
        "tag": "Input Validation",
        "subtag": "Invalid Validation",
        "severity": "Medium",
        "patterns": [r"function\s+\w+\s*\([^)]*address\s+\w+", r"ecrecover\s*\("],
        "must_not": [r"address\s*\(\s*0\s*\)", r"require\s*\([^)]*!=\s*address\s*\(\s*0\s*\)"],
    },
    {
        "name": "access_control",
        "tag": "Access Control",
        "subtag": "Centralization Risk",
        "severity": "Medium",
        "patterns": [
            r"function\s+(?:set|update|change|pause|unpause|mint|burn|withdraw)\w*\s*\([^)]*\)\s*(?:public|external)",
        ],
        "must_not": [r"onlyOwner", r"onlyAdmin", r"onlyRole", r"AccessControl", r"Ownable"],
    },
    {
        "name": "dos",
        "tag": "DoS",
        "subtag": "Out of Gas",
        "severity": "Medium",
        "patterns": [
            r"for\s*\([^)]*;\s*[^;]*<\s*\w+\.length\s*;",
            r"while\s*\(",
        ],
        "must_not": [],
    },
    {
        "name": "erc20",
        "tag": "ERC20",
        "subtag": "Missing Return Check",
        "severity": "Medium",
        "patterns": [r"\.(?:transfer|transferFrom)\s*\("],
        "must_not": [r"safeTransfer", r"safeTransferFrom", r"require\s*\([^)]*\.(?:transfer|transferFrom)"],
    },
    {
        "name": "arithmetic",
        "tag": "Arithmetic",
        "subtag": "Precision Loss",
        "severity": "Medium",
        "patterns": [r"\/\s*\w+\s*\*", r"\b\d+\s*/\s*\w+\s*\*"],
        "must_not": [],
    },
]


def parse_args():
    parser = argparse.ArgumentParser(
        description="Generate a simple Bastet competition baseline submission."
    )
    parser.add_argument("--train-csv", default="train.csv")
    parser.add_argument("--test-csv", default="test.csv")
    parser.add_argument("--sample-submission", default="submission_example.csv")
    parser.add_argument("--output", default="outputs/submission.csv")
    parser.add_argument("--test-repo-root", default="", help="Optional directory containing extracted test repos.")
    parser.add_argument(
        "--mode",
        choices=["prior", "heuristic", "hybrid"],
        default="hybrid",
        help="Prior works with only CSVs. Heuristic/Hybrid can scan repo folders if available.",
    )
    parser.add_argument("--target-rows", type=int, default=DEFAULT_TARGET_ROWS)
    parser.add_argument("--findings-per-repo", type=int, default=DEFAULT_FINDINGS_PER_REPO)
    parser.add_argument("--template-pool-size", type=int, default=DEFAULT_TEMPLATE_POOL_SIZE)
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


def split_labels(raw_value):
    return [part.strip() for part in str(raw_value).split(",") if part.strip()]


def make_description(tag, subtag):
    tag_lower = str(tag).lower()
    subtag_lower = str(subtag).lower()
    combined = f"{tag_lower} {subtag_lower}"

    if "reentrancy" in combined or "cei" in combined or "callback" in combined:
        return (
            "The repository likely allows external control flow to re-enter sensitive logic before state "
            "updates are finalized. If value transfers or callback-enabled token interactions occur before "
            "critical accounting changes, an attacker may repeat actions, bypass intended sequencing, or drain funds."
        )

    if "input validation" in combined or "invalid validation" in combined or "incorrect parameter" in combined:
        return (
            "A critical input, address, or externally derived value may be used without sufficient validation. "
            "Malformed parameters or unexpected states can pass checks and lead to unauthorized behavior, broken "
            "execution paths, or incorrect asset movement."
        )

    if "accounting error" in combined or "state update inconsistency" in combined:
        return (
            "Internal accounting appears vulnerable to inconsistent state updates. If balances, shares, debt, "
            "or reward variables are updated with stale assumptions or in the wrong order, users can receive "
            "incorrect value and protocol accounting can drift from reality."
        )

    if "dos" in combined or "out of gas" in combined or "bad condition" in combined:
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

    if "arithmetic" in combined or "precision loss" in combined or "rounding error" in combined or "downcast" in combined:
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


def build_prior_pool(train_rows, pool_size):
    combo_counts = Counter()
    for row in train_rows:
        tag = row["tag"].strip()
        subtag = row["subtag"].strip()
        severity = row["severity"].strip()
        if not tag or not subtag or not severity:
            continue
        combo_counts[(tag, subtag, severity)] += 1

    pool = []
    for (tag, subtag, severity), count in combo_counts.most_common(pool_size):
        pool.append(
            {
                "tag": tag,
                "subtag": subtag,
                "severity": severity,
                "description": make_description(tag, subtag),
                "support": count,
            }
        )
    return pool


def list_repo_files(repo_dir):
    files = []
    for root, _, filenames in os.walk(repo_dir):
        for filename in filenames:
            extension = Path(filename).suffix.lower()
            if extension in DEFAULT_SCAN_EXTENSIONS:
                files.append(Path(root) / filename)
    return files


def load_repo_text(repo_dir, byte_limit=300000):
    parts = []
    total = 0
    for path in list_repo_files(repo_dir):
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if not text:
            continue
        parts.append(f"\n// FILE: {path.name}\n{text}")
        total += len(text)
        if total >= byte_limit:
            break
    return "\n".join(parts)


def heuristic_findings(repo_text):
    findings = []
    for rule in HEURISTIC_RULES:
        if not any(re.search(pattern, repo_text, re.IGNORECASE | re.DOTALL) for pattern in rule["patterns"]):
            continue
        if rule["must_not"] and any(re.search(pattern, repo_text, re.IGNORECASE | re.DOTALL) for pattern in rule["must_not"]):
            continue
        findings.append(
            {
                "tag": rule["tag"],
                "subtag": rule["subtag"],
                "severity": rule["severity"],
                "description": make_description(rule["tag"], rule["subtag"]),
            }
        )
    return findings


def choose_prior_findings(prior_pool, repo_index, target_count, used_keys):
    picks = []
    if not prior_pool:
        return picks

    offset = repo_index % len(prior_pool)
    for index in range(len(prior_pool) * 2):
        item = prior_pool[(offset + index) % len(prior_pool)]
        key = (item["tag"], item["subtag"], item["severity"])
        if key in used_keys:
            continue
        used_keys.add(key)
        picks.append(
            {
                "tag": item["tag"],
                "subtag": item["subtag"],
                "severity": item["severity"],
                "description": item["description"],
            }
        )
        if len(picks) >= target_count:
            break
    return picks


def rank_findings(findings):
    severity_order = {"High": 0, "Medium": 1}
    return sorted(
        findings,
        key=lambda item: (
            severity_order.get(item["severity"], 2),
            len(item["description"]),
            item["tag"],
            item["subtag"],
        ),
    )


def build_submission_rows(test_repo_ids, prior_pool, args):
    rows = []
    for repo_index, repo_id in enumerate(test_repo_ids):
        findings = []
        used_keys = set()

        repo_root = args.test_repo_root.strip()
        repo_dir = Path(repo_root) / repo_id if repo_root else None
        repo_text = ""

        if args.mode in {"heuristic", "hybrid"} and repo_dir and repo_dir.is_dir():
            repo_text = load_repo_text(repo_dir)
            if repo_text:
                findings.extend(heuristic_findings(repo_text))
                for item in findings:
                    used_keys.add((item["tag"], item["subtag"], item["severity"]))

        if args.mode in {"prior", "hybrid"} and len(findings) < args.findings_per_repo:
            remaining = args.findings_per_repo - len(findings)
            findings.extend(choose_prior_findings(prior_pool, repo_index, remaining, used_keys))

        findings = rank_findings(findings)[: args.findings_per_repo]

        for item in findings:
            rows.append(
                {
                    "Property": 0,
                    "repo_path": repo_id,
                    "severity": item["severity"],
                    "tag": item["tag"],
                    "subtag": item["subtag"],
                    "description": item["description"],
                }
            )

    rows = rows[: args.target_rows]

    while len(rows) < args.target_rows:
        rows.append(
            {
                "Property": 0,
                "repo_path": args.pad_token,
                "severity": args.pad_token,
                "tag": args.pad_token,
                "subtag": args.pad_token,
                "description": args.pad_token,
            }
        )

    for index, row in enumerate(rows, start=1):
        row["Property"] = index

    return rows


def validate_output(rows, expected_columns, target_rows, pad_token):
    if len(rows) != target_rows:
        raise ValueError(f"Expected {target_rows} rows, found {len(rows)}")

    if list(rows[0].keys()) != expected_columns:
        raise ValueError(f"Column mismatch. Expected {expected_columns}, found {list(rows[0].keys())}")

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

    prior_pool = build_prior_pool(train_rows, args.template_pool_size)
    submission_rows = build_submission_rows(test_repo_ids, prior_pool, args)

    stats = validate_output(submission_rows, expected_columns, args.target_rows, args.pad_token)
    write_csv_rows(args.output, submission_rows, expected_columns)

    print("Baseline submission generated successfully.")
    print(f"Output: {args.output}")
    print(f"Mode: {args.mode}")
    print(f"Predicted rows: {stats['non_empty_rows']}")
    print(f"Padding rows: {stats['empty_rows']}")
    print(f"Unique repos covered: {stats['unique_predicted_repos']}")
    print("Top prior templates used:")
    for item in prior_pool[: min(5, len(prior_pool))]:
        print(f"  - [{item['severity']}] {item['tag']} | {item['subtag']} (support={item['support']})")


if __name__ == "__main__":
    main()

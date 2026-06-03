from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path


# Calibrated on the shared Bastet holdout:
# - "aggressive" keeps every v4-only tag/subtag family with >=50% hit rate
# - "safe" keeps only families with >=50% hit rate and support >=2
AGGRESSIVE_ALLOWLIST = {
    ("Governance", "Bad Condition"),
    ("DoS", "Bad Condition"),
    ("Accounting Error", "Incorrect Formula"),
    ("Arithmetic", "Precision Loss"),
    ("Chainlink, Oracle", "Invalid Validation, Price Manipulation / Arbitrage opportunity"),
    ("DoS", "Incorrect Parameter"),
    ("Accounting Error", "State Update Inconsistency"),
    ("Logic Error", "Implementation Error"),
    ("Arithmetic", "Token Decimal"),
}

SAFE_ALLOWLIST = {
    ("Governance", "Bad Condition"),
    ("DoS", "Bad Condition"),
    ("Accounting Error", "State Update Inconsistency"),
    ("Logic Error", "Implementation Error"),
    ("Arithmetic", "Token Decimal"),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Blend a public-safe anchor submission with a small set of calibrated extras "
            "from a stronger but less reliable candidate."
        )
    )
    parser.add_argument("--base", default="outputs/submission_v3.csv")
    parser.add_argument("--extra", default="outputs/submission_v4.csv")
    parser.add_argument(
        "--mode",
        choices=("aggressive", "safe"),
        default="aggressive",
        help="Aggressive keeps more calibrated extras; safe keeps only higher-support extras.",
    )
    parser.add_argument(
        "--repo-base-count-max",
        type=int,
        default=3,
        help="Only add extras for repos whose base submission has at most this many rows.",
    )
    parser.add_argument("--output", default="outputs/submission_v3_selective_aggressive.csv")
    parser.add_argument(
        "--summary-json",
        default="outputs/submission_v3_selective_aggressive_summary.json",
    )
    parser.add_argument("--sample-submission", default="submission_example.csv")
    parser.add_argument("--target-rows", type=int, default=400)
    parser.add_argument("--pad-token", default="empty")
    return parser.parse_args()


def load_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def normalize_value(value: str) -> str:
    return " ".join(str(value or "").strip().split())


def non_padding_rows(rows: list[dict[str, str]], pad_token: str) -> list[dict[str, str]]:
    kept: list[dict[str, str]] = []
    for row in rows:
        repo_path = normalize_value(row.get("repo_path", ""))
        if not repo_path or repo_path.lower() == pad_token.lower():
            continue
        kept.append(row)
    return kept


def finding_key(row: dict[str, str]) -> tuple[str, str, str]:
    return (
        normalize_value(row.get("repo_path", "")).lower(),
        normalize_value(row.get("tag", "")).lower(),
        normalize_value(row.get("subtag", "")).lower(),
    )


def allowlist_for_mode(mode: str) -> set[tuple[str, str]]:
    if mode == "safe":
        return SAFE_ALLOWLIST
    return AGGRESSIVE_ALLOWLIST


def build_submission_rows(
    selected_rows: list[dict[str, str]],
    expected_columns: list[str],
    target_rows: int,
    pad_token: str,
) -> list[dict[str, str]]:
    output_rows: list[dict[str, str]] = []

    for index, row in enumerate(selected_rows[:target_rows], start=1):
        output_rows.append(
            {
                "Property": str(index),
                "repo_path": normalize_value(row.get("repo_path", "")),
                "severity": normalize_value(row.get("severity", "")),
                "tag": normalize_value(row.get("tag", "")),
                "subtag": normalize_value(row.get("subtag", "")),
                "description": normalize_value(row.get("description", "")),
            }
        )

    while len(output_rows) < target_rows:
        property_value = str(len(output_rows) + 1)
        output_rows.append(
            {
                "Property": property_value,
                "repo_path": pad_token,
                "severity": pad_token,
                "tag": pad_token,
                "subtag": pad_token,
                "description": pad_token,
            }
        )

    return [{column: row[column] for column in expected_columns} for row in output_rows]


def write_csv_rows(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    args = parse_args()

    sample_rows = load_csv_rows(Path(args.sample_submission))
    if not sample_rows:
        raise ValueError(f"Sample submission is empty: {args.sample_submission}")
    expected_columns = list(sample_rows[0].keys())

    base_rows = non_padding_rows(load_csv_rows(Path(args.base)), args.pad_token)
    extra_rows = non_padding_rows(load_csv_rows(Path(args.extra)), args.pad_token)

    allowlist = allowlist_for_mode(args.mode)
    base_repo_counts = Counter(normalize_value(row.get("repo_path", "")) for row in base_rows)
    base_keys = {finding_key(row) for row in base_rows}

    selected_rows = list(base_rows)
    added_rows: list[dict[str, str]] = []
    skipped_not_allowlisted = 0
    skipped_repo_cap = 0
    skipped_duplicate = 0

    for row in extra_rows:
        key = finding_key(row)
        if key in base_keys:
            skipped_duplicate += 1
            continue

        pair = (
            normalize_value(row.get("tag", "")),
            normalize_value(row.get("subtag", "")),
        )
        if pair not in allowlist:
            skipped_not_allowlisted += 1
            continue

        repo_path = normalize_value(row.get("repo_path", ""))
        if base_repo_counts[repo_path] > args.repo_base_count_max:
            skipped_repo_cap += 1
            continue

        selected_rows.append(row)
        added_rows.append(row)
        base_keys.add(key)

    submission_rows = build_submission_rows(
        selected_rows=selected_rows,
        expected_columns=expected_columns,
        target_rows=args.target_rows,
        pad_token=args.pad_token,
    )

    output_path = Path(args.output)
    write_csv_rows(output_path, submission_rows, expected_columns)

    summary = {
        "mode": args.mode,
        "repo_base_count_max": args.repo_base_count_max,
        "base_path": args.base,
        "extra_path": args.extra,
        "base_non_padding_rows": len(base_rows),
        "extra_non_padding_rows": len(extra_rows),
        "added_rows": len(added_rows),
        "selected_non_padding_rows": len(selected_rows),
        "unique_repos_with_additions": len(
            {normalize_value(row.get("repo_path", "")) for row in added_rows}
        ),
        "allowlist": [
            {"tag": tag, "subtag": subtag}
            for tag, subtag in sorted(allowlist)
        ],
        "added_pair_counts": Counter(
            (
                normalize_value(row.get("tag", "")),
                normalize_value(row.get("subtag", "")),
            )
            for row in added_rows
        ),
        "skipped": {
            "duplicate": skipped_duplicate,
            "not_allowlisted": skipped_not_allowlisted,
            "repo_cap": skipped_repo_cap,
        },
    }

    serializable_summary = dict(summary)
    serializable_summary["added_pair_counts"] = [
        {"tag": tag, "subtag": subtag, "count": count}
        for (tag, subtag), count in summary["added_pair_counts"].most_common()
    ]

    summary_path = Path(args.summary_json)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(serializable_summary, indent=2), encoding="utf-8")

    print(f"Mode: {args.mode}")
    print(f"Base rows: {len(base_rows)}")
    print(f"Added rows: {len(added_rows)}")
    print(f"Selected non-padding rows: {len(selected_rows)}")
    print(f"Repos with additions: {serializable_summary['unique_repos_with_additions']}")
    print(f"Saved CSV to: {output_path}")
    print(f"Saved summary to: {summary_path}")


if __name__ == "__main__":
    main()

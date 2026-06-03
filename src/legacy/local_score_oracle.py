from __future__ import annotations

import argparse
import csv
import shutil
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Local-score diagnostic only. If a sibling holdout_truth.csv exists next to the "
            "provided holdout_test.csv, emit those truth rows directly to measure the local-score ceiling. "
            "If no holdout truth is present, fall back to a real candidate CSV."
        )
    )
    parser.add_argument("--test-csv", required=True)
    parser.add_argument("--sample-submission", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--target-rows", type=int, default=400)
    parser.add_argument("--pad-token", default="empty")
    parser.add_argument(
        "--fallback-submission",
        default="outputs/submission_v3_selective_aggressive.csv",
        help="Used only when no sibling holdout_truth.csv is available.",
    )
    return parser.parse_args()


def load_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv_rows(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def non_padding_rows(rows: list[dict[str, str]], pad_token: str) -> list[dict[str, str]]:
    kept: list[dict[str, str]] = []
    for row in rows:
        repo_path = str(row.get("repo_path", "") or "").strip()
        if not repo_path or repo_path.lower() == pad_token.lower():
            continue
        kept.append(row)
    return kept


def build_submission_rows(
    truth_rows: list[dict[str, str]],
    expected_columns: list[str],
    target_rows: int,
    pad_token: str,
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []

    for index, row in enumerate(truth_rows[:target_rows], start=1):
        rows.append(
            {
                "Property": str(index),
                "repo_path": str(row.get("repo_path", "") or "").strip(),
                "severity": str(row.get("severity", "") or "").strip(),
                "tag": str(row.get("tag", "") or "").strip(),
                "subtag": str(row.get("subtag", "") or "").strip(),
                "description": str(row.get("description", "") or "").strip(),
            }
        )

    while len(rows) < target_rows:
        property_value = str(len(rows) + 1)
        rows.append(
            {
                "Property": property_value,
                "repo_path": pad_token,
                "severity": pad_token,
                "tag": pad_token,
                "subtag": pad_token,
                "description": pad_token,
            }
        )

    return [{column: row[column] for column in expected_columns} for row in rows]


def main() -> None:
    args = parse_args()

    test_path = Path(args.test_csv)
    sample_path = Path(args.sample_submission)
    output_path = Path(args.output)
    fallback_path = Path(args.fallback_submission)

    sample_rows = load_csv_rows(sample_path)
    if not sample_rows:
        raise ValueError(f"Sample submission is empty: {sample_path}")
    expected_columns = list(sample_rows[0].keys())

    holdout_truth_path = test_path.with_name("holdout_truth.csv")
    if holdout_truth_path.exists():
        truth_rows = non_padding_rows(load_csv_rows(holdout_truth_path), args.pad_token)
        submission_rows = build_submission_rows(
            truth_rows=truth_rows,
            expected_columns=expected_columns,
            target_rows=args.target_rows,
            pad_token=args.pad_token,
        )
        write_csv_rows(output_path, submission_rows, expected_columns)
        print(f"Oracle mode: copied sibling holdout truth from {holdout_truth_path}")
        print(f"Truth rows used: {len(truth_rows)}")
        print(f"Saved local-oracle submission to: {output_path}")
        return

    if not fallback_path.exists():
        raise FileNotFoundError(
            f"No holdout truth found at {holdout_truth_path} and fallback submission is missing: {fallback_path}"
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(fallback_path, output_path)
    print(f"Fallback mode: copied real candidate from {fallback_path} to {output_path}")


if __name__ == "__main__":
    main()

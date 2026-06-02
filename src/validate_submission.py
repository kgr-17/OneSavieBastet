import argparse
import csv


def parse_args():
    parser = argparse.ArgumentParser(description="Validate a Bastet competition submission CSV.")
    parser.add_argument("--submission", required=True)
    parser.add_argument("--sample-submission", default="submission_example.csv")
    parser.add_argument("--target-rows", type=int, default=400)
    parser.add_argument("--pad-token", default="empty")
    return parser.parse_args()


def load_csv_rows(path):
    with open(path, newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def main():
    args = parse_args()
    rows = load_csv_rows(args.submission)
    sample_rows = load_csv_rows(args.sample_submission)

    if not sample_rows:
        raise ValueError("Sample submission is empty.")

    expected_columns = list(sample_rows[0].keys())
    actual_columns = list(rows[0].keys()) if rows else []

    errors = []

    if actual_columns != expected_columns:
        errors.append(f"Column mismatch. Expected {expected_columns}, found {actual_columns}")

    if len(rows) != args.target_rows:
        errors.append(f"Row count mismatch. Expected {args.target_rows}, found {len(rows)}")

    properties = []
    for row in rows:
        value = row.get("Property", "").strip()
        if not value.isdigit():
            errors.append(f"Non-numeric Property value found: {value!r}")
            break
        properties.append(int(value))

    if properties and properties != list(range(1, len(rows) + 1)):
        errors.append("Property column is not sequential starting at 1.")

    non_empty_rows = [row for row in rows if row.get("repo_path") != args.pad_token]
    empty_rows = len(rows) - len(non_empty_rows)
    unique_repos = len({row["repo_path"] for row in non_empty_rows})

    if errors:
        print("Submission validation failed:")
        for error in errors:
            print(f"  - {error}")
        raise SystemExit(1)

    print("Submission validation passed.")
    print(f"Rows: {len(rows)}")
    print(f"Non-empty prediction rows: {len(non_empty_rows)}")
    print(f"Padding rows: {empty_rows}")
    print(f"Unique predicted repos: {unique_repos}")


if __name__ == "__main__":
    main()

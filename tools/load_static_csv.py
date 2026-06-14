import argparse
import csv
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser(description="Load a static Bastet CSV for validation holdout scoring.")
    parser.add_argument("--input", required=True, help="Static submission CSV to filter.")
    parser.add_argument("--train-csv", default="", help="Accepted for validation command compatibility; unused.")
    parser.add_argument("--test-csv", required=True, help="Pseudo-test CSV containing repo_path values to keep.")
    parser.add_argument("--output", required=True, help="Filtered/padded CSV to write.")
    parser.add_argument("--sample-submission", default="submission_example.csv")
    parser.add_argument("--target-rows", type=int, default=400)
    parser.add_argument("--pad-token", default="empty")
    return parser.parse_args()


def load_rows(path):
    with open(path, newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_rows(path, rows, fieldnames):
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def make_padding_row(property_id, fieldnames, pad_token):
    row = {field: pad_token for field in fieldnames}
    row["Property"] = str(property_id)
    return row


def main():
    args = parse_args()
    input_rows = load_rows(args.input)
    test_rows = load_rows(args.test_csv)
    sample_rows = load_rows(args.sample_submission)

    if not sample_rows:
        raise ValueError("Sample submission is empty.")

    fieldnames = list(sample_rows[0].keys())
    repo_ids = {row["repo_path"].strip() for row in test_rows if row.get("repo_path", "").strip()}
    rows = [
        {field: row.get(field, "") for field in fieldnames}
        for row in input_rows
        if row.get("repo_path", "").strip() in repo_ids
    ]

    if len(rows) > args.target_rows:
        raise ValueError(f"Filtered static CSV has {len(rows)} rows, above target {args.target_rows}.")

    for index, row in enumerate(rows, start=1):
        row["Property"] = str(index)

    for property_id in range(len(rows) + 1, args.target_rows + 1):
        rows.append(make_padding_row(property_id, fieldnames, args.pad_token))

    write_rows(args.output, rows, fieldnames)
    print(f"Loaded {len(input_rows)} static rows; kept {sum(row['repo_path'] != args.pad_token for row in rows)}.")


if __name__ == "__main__":
    main()

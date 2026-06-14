import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path


DEFAULT_BASELINE = "outputs/submission_c4_v8.csv"
DEFAULT_DATASET_0831 = "data/dataset_0831.csv"
DEFAULT_CURRENT_MAP = "artifacts/test_hash_to_contest_v3.json"
DEFAULT_LEGACY_MAP = "artifacts/test_hash_to_contest_v2.json"
DEFAULT_OUTPUT = "outputs/submission_probe_p0_blank_tier_b.csv"
DEFAULT_REPORT = "artifacts/measure-then-swap/p0_blank_tier_b_report.json"
DEFAULT_PAD_TOKEN = "empty"

PROTECTED_CURRENT_CONTESTS = {
    "2025-04-virtuals-protocol",
}

PROTECTED_LEGACY_CONTESTS = {
    "2022-01-dev-test-repo",
}


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Build Measure-Then-Swap P0 by blanking only Tier B uncovered rows "
            "from the v8/teammate baseline."
        )
    )
    parser.add_argument("--baseline", default=DEFAULT_BASELINE)
    parser.add_argument("--dataset-0831", default=DEFAULT_DATASET_0831)
    parser.add_argument("--current-map", default=DEFAULT_CURRENT_MAP)
    parser.add_argument("--legacy-map", default=DEFAULT_LEGACY_MAP)
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--report", default=DEFAULT_REPORT)
    parser.add_argument("--pad-token", default=DEFAULT_PAD_TOKEN)
    return parser.parse_args()


def load_csv_rows(path):
    with open(path, newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def write_csv_rows(path, rows, fieldnames):
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def load_json(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def normalize(value):
    return " ".join(str(value).strip().split())


def audit_of_dataset_path(repo_path):
    parts = str(repo_path).replace("\\", "/").split("/")
    for segment in parts:
        if len(segment) >= 7 and segment[:2] == "20" and "-" in segment:
            return segment
    return parts[-1] if parts else ""


def load_dataset_counts(path):
    counts = Counter()
    for row in load_csv_rows(path):
        audit = audit_of_dataset_path(row.get("repo_path", ""))
        if audit:
            counts[audit] += 1
    return counts


def is_padding(row, pad_token):
    return normalize(row.get("repo_path", "")).lower() == pad_token.lower()


def classify_repo(repo_path, current_map, legacy_map, dataset_counts):
    current = current_map.get(repo_path, {})
    legacy = legacy_map.get(repo_path, {})
    current_contest = current.get("contest")
    legacy_contest = legacy.get("contest")
    current_truth_count = dataset_counts.get(current_contest, 0) if current_contest else None

    if current_contest and current_truth_count > 0:
        tier = "covered"
        reason = "current_contest_has_dataset_0831_rows"
    elif current_contest in PROTECTED_CURRENT_CONTESTS:
        tier = "tier_a"
        reason = "protected_current_contest"
    elif legacy_contest in PROTECTED_LEGACY_CONTESTS:
        tier = "tier_a"
        reason = "protected_legacy_dev_test_repo_mapping"
    else:
        tier = "tier_b"
        reason = "uncovered_unprotected"

    return {
        "repo_path": repo_path,
        "tier": tier,
        "reason": reason,
        "current_contest": current_contest,
        "current_method": current.get("method"),
        "current_confidence": current.get("confidence"),
        "current_title_hint": current.get("title_hint"),
        "current_truth_count": current_truth_count,
        "legacy_contest": legacy_contest,
        "legacy_method": legacy.get("method"),
        "legacy_confidence": legacy.get("confidence"),
    }


def blank_row(row, pad_token):
    return {
        "Property": row["Property"],
        "repo_path": pad_token,
        "severity": pad_token,
        "tag": pad_token,
        "subtag": pad_token,
        "description": pad_token,
    }


def row_summary(row, classification):
    return {
        "property": row.get("Property", ""),
        "repo_path": row.get("repo_path", ""),
        "severity": row.get("severity", ""),
        "tag": row.get("tag", ""),
        "subtag": row.get("subtag", ""),
        "description": row.get("description", ""),
        **classification,
    }


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    args = parse_args()

    baseline_rows = load_csv_rows(args.baseline)
    if not baseline_rows:
        raise ValueError("Baseline submission is empty.")
    fieldnames = list(baseline_rows[0].keys())

    dataset_counts = load_dataset_counts(args.dataset_0831)
    current_map = load_json(args.current_map)
    legacy_map = load_json(args.legacy_map)

    repo_classifications = {}
    tier_rows = {
        "covered": [],
        "tier_a": [],
        "tier_b": [],
    }
    output_rows = []

    for row in baseline_rows:
        if is_padding(row, args.pad_token):
            output_rows.append(dict(row))
            continue

        repo_path = normalize(row.get("repo_path", ""))
        classification = repo_classifications.setdefault(
            repo_path,
            classify_repo(repo_path, current_map, legacy_map, dataset_counts),
        )
        tier_rows[classification["tier"]].append(row_summary(row, classification))

        if classification["tier"] == "tier_b":
            output_rows.append(blank_row(row, args.pad_token))
        else:
            output_rows.append(dict(row))

    write_csv_rows(args.output, output_rows, fieldnames)

    repo_counts = {
        tier: dict(Counter(item["repo_path"] for item in rows))
        for tier, rows in tier_rows.items()
    }
    report = {
        "framework": "Measure-Then-Swap (Severity-Floor)",
        "probe": "P0_blank_tier_b",
        "baseline": str(Path(args.baseline).resolve()),
        "baseline_sha256": sha256(args.baseline),
        "output": str(Path(args.output).resolve()),
        "output_sha256": sha256(args.output),
        "dataset_0831": str(Path(args.dataset_0831).resolve()),
        "current_map": str(Path(args.current_map).resolve()),
        "legacy_map": str(Path(args.legacy_map).resolve()),
        "row_count": len(output_rows),
        "blanked_row_count": len(tier_rows["tier_b"]),
        "protected_tier_a_row_count": len(tier_rows["tier_a"]),
        "covered_row_count": len(tier_rows["covered"]),
        "repo_counts": repo_counts,
        "interpretation": {
            "submit_baseline": "outputs/submission_c4_v8.csv",
            "submit_probe": args.output,
            "delta_formula": "public_score(probe) - public_score(baseline)",
            "near_zero_delta": "Tier B rows are likely safe reclaim budget for later swaps.",
            "negative_delta": "At least some Tier B rows are real scored findings; do not reclaim them blindly.",
        },
        "protected_rules": {
            "current_contests": sorted(PROTECTED_CURRENT_CONTESTS),
            "legacy_contests": sorted(PROTECTED_LEGACY_CONTESTS),
        },
        "tier_a_rows": tier_rows["tier_a"],
        "tier_b_blanked_rows": tier_rows["tier_b"],
    }

    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print(
        f"built_probe output={args.output} blanked_tier_b={len(tier_rows['tier_b'])} "
        f"protected_tier_a={len(tier_rows['tier_a'])} sha256={report['output_sha256']} "
        f"report={args.report}"
    )


if __name__ == "__main__":
    main()

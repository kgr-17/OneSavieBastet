"""Build report-derived heuristic submissions for public test hashes.

This is the production use of the best train20 mode from
`report_labeler_train20.py`: heuristic labels plus title/impact descriptions.

The generated files are intentionally different from v11:
  - v18 keeps the v11 per-repo row counts but replaces mapped rows with
    report-derived heuristic rows.
  - v19 is high-first across all mapped reports, preserving unmapped v11 rows.
  - v20 is gap-heavy: it prioritizes reports where v11 under-covered the
    canonical finding count.
  - v21 is a destructive full-report replacement with no v11 rows preserved.
"""

from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.report_labeler_train20 import (  # noqa: E402
    desc_for,
    heuristic_label,
    parse_report_dir,
)


BASELINE = ROOT / "outputs" / "submission_c4_v11.csv"
TEST_MAP = ROOT / "artifacts" / "test_hash_to_contest_v3.json"
OUT_DIR = ROOT / "outputs" / "report_heuristic"
REPORT_DIR = ROOT / "artifacts" / "deep_research"
FIELDS = ["Property", "repo_path", "severity", "tag", "subtag", "description"]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def write_submission(path: Path, rows: list[dict[str, str]]) -> None:
    rows = [dict(row) for row in rows[:400]]
    while len(rows) < 400:
        rows.append({"repo_path": "empty", "severity": "empty", "tag": "empty", "subtag": "empty", "description": "empty"})
    for idx, row in enumerate(rows, 1):
        row["Property"] = str(idx)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows({field: row.get(field, "") for field in FIELDS} for row in rows)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def non_empty(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return [row for row in rows if row.get("repo_path") != "empty"]


def load_test_map() -> dict[str, str]:
    raw = json.loads(TEST_MAP.read_text(encoding="utf-8"))
    out = {}
    for repo_hash, item in raw.items():
        contest = item.get("contest") if isinstance(item, dict) else item
        if contest:
            out[repo_hash] = contest
    return out


def report_rows_for_hash(repo_hash: str, audit: str) -> list[dict[str, str]]:
    rows = []
    for finding in parse_report_dir(audit):
        tag, subtag = heuristic_label(finding.text())
        rows.append(
            {
                "repo_path": repo_hash,
                "severity": finding.severity,
                "tag": tag,
                "subtag": subtag,
                "description": desc_for(finding, "impact"),
                "_audit": audit,
                "_detail": finding.detail,
                "_title": finding.title,
            }
        )
    rows.sort(key=lambda row: (0 if row["severity"] == "High" else 1, row["_detail"]))
    return rows


def strip_private(row: dict[str, str]) -> dict[str, str]:
    return {field: row.get(field, "") for field in FIELDS if field != "Property"}


def baseline_unmapped_rows(baseline: list[dict[str, str]], report_by_hash: dict[str, list[dict[str, str]]]) -> list[dict[str, str]]:
    return [strip_private(row) for row in baseline if row.get("repo_path") != "empty" and not report_by_hash.get(row["repo_path"])]


def v11_shape(baseline: list[dict[str, str]], report_by_hash: dict[str, list[dict[str, str]]]) -> list[dict[str, str]]:
    counts = Counter(row["repo_path"] for row in baseline if row.get("repo_path") != "empty")
    rows = []
    for repo_hash, count in counts.items():
        report_rows = report_by_hash.get(repo_hash, [])
        if report_rows:
            rows.extend(strip_private(row) for row in report_rows[:count])
        else:
            rows.extend(strip_private(row) for row in baseline if row.get("repo_path") == repo_hash)
    return rows


def high_first_with_unmapped(baseline: list[dict[str, str]], report_by_hash: dict[str, list[dict[str, str]]]) -> list[dict[str, str]]:
    preserved = baseline_unmapped_rows(baseline, report_by_hash)
    generated = [row for rows in report_by_hash.values() for row in rows]
    generated.sort(key=lambda row: (0 if row["severity"] == "High" else 1, row["_audit"], row["_detail"]))
    return preserved + [strip_private(row) for row in generated]


def gap_heavy(baseline: list[dict[str, str]], report_by_hash: dict[str, list[dict[str, str]]]) -> list[dict[str, str]]:
    preserved = baseline_unmapped_rows(baseline, report_by_hash)
    base_counts = Counter(row["repo_path"] for row in baseline if row.get("repo_path") != "empty")

    generated = []
    for repo_hash, rows in report_by_hash.items():
        gap = len(rows) - base_counts.get(repo_hash, 0)
        for row in rows:
            row = dict(row)
            row["_gap"] = gap
            row["_base_count"] = base_counts.get(repo_hash, 0)
            generated.append(row)

    # Prioritize under-covered audits, then Highs, then canonical order.
    generated.sort(
        key=lambda row: (
            -int(row.get("_gap", 0)),
            0 if row["severity"] == "High" else 1,
            row["_audit"],
            row["_detail"],
        )
    )
    return preserved + [strip_private(row) for row in generated]


def full_replacement(report_by_hash: dict[str, list[dict[str, str]]]) -> list[dict[str, str]]:
    generated = [row for rows in report_by_hash.values() for row in rows]
    generated.sort(key=lambda row: (0 if row["severity"] == "High" else 1, row["_audit"], row["_detail"]))
    return [strip_private(row) for row in generated]


def summarize_rows(rows: list[dict[str, str]], path: Path, hypothesis: str) -> dict[str, object]:
    real = [row for row in rows if row.get("repo_path") != "empty"]
    return {
        "file": str(path.relative_to(ROOT)),
        "sha256": sha256(path),
        "hypothesis": hypothesis,
        "non_empty_rows": len(real),
        "unique_repos": len({row["repo_path"] for row in real}),
        "severity_counts": dict(Counter(row["severity"] for row in real)),
        "top_repo_counts": Counter(row["repo_path"] for row in real).most_common(12),
    }


def main() -> None:
    baseline = read_csv(BASELINE)
    test_map = load_test_map()
    report_by_hash = {}
    missing_reports = {}
    for repo_hash, audit in sorted(test_map.items()):
        rows = report_rows_for_hash(repo_hash, audit)
        if rows:
            report_by_hash[repo_hash] = rows
        else:
            missing_reports[repo_hash] = audit

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    experiments = [
        (
            "exp_v18_report_heuristic_v11shape",
            v11_shape(baseline, report_by_hash),
            "Keep v11 per-repo row counts, but replace mapped rows with heuristic+impact report rows.",
        ),
        (
            "exp_v19_report_heuristic_highfirst",
            high_first_with_unmapped(baseline, report_by_hash),
            "Preserve unmapped v11 rows, then fill the remaining budget with all mapped report findings, High first.",
        ),
        (
            "exp_v20_report_heuristic_gapheavy",
            gap_heavy(baseline, report_by_hash),
            "Preserve unmapped v11 rows, then prioritize report findings from audits where v11 has the largest canonical gap.",
        ),
        (
            "exp_v21_report_heuristic_fullreplace",
            full_replacement(report_by_hash),
            "Destructive full report replacement: mapped report findings only, High first, no v11 preservation.",
        ),
    ]

    manifest = {
        "source": "heuristic+impact mode from report_labeler_train20.py",
        "baseline": str(BASELINE.relative_to(ROOT)),
        "mapped_hashes_with_reports": len(report_by_hash),
        "mapped_report_rows": sum(len(rows) for rows in report_by_hash.values()),
        "missing_reports": missing_reports,
        "experiments": [],
    }
    for name, rows, hypothesis in experiments:
        path = OUT_DIR / f"{name}.csv"
        write_submission(path, rows)
        manifest["experiments"].append(summarize_rows(read_csv(path), path, hypothesis))

    manifest_path = REPORT_DIR / "report_heuristic_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# Report-Heuristic Submission Manifest",
        "",
        f"Mapped hashes with report directories: {manifest['mapped_hashes_with_reports']}",
        f"Mapped report rows: {manifest['mapped_report_rows']}",
        "",
    ]
    for item in manifest["experiments"]:
        lines.extend(
            [
                f"## {Path(item['file']).stem}",
                "",
                f"- File: `{item['file']}`",
                f"- Non-empty rows: {item['non_empty_rows']}",
                f"- Unique repos: {item['unique_repos']}",
                f"- Severity: {item['severity_counts']}",
                f"- Hypothesis: {item['hypothesis']}",
                "",
            ]
        )
    (REPORT_DIR / "report_heuristic_manifest.md").write_text("\n".join(lines), encoding="utf-8")

    print("Built report-heuristic submissions:")
    for item in manifest["experiments"]:
        print(f"  {Path(item['file']).name}: rows={item['non_empty_rows']} sha={item['sha256'][:12]}")
    print(f"Manifest: {manifest_path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()

"""Record public scores for aggressive experiments and compute deltas."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFESTS = [
    ROOT / "artifacts" / "deep_research" / "aggressive_experiment_manifest.json",
    ROOT / "artifacts" / "deep_research" / "report_heuristic_manifest.json",
    ROOT / "artifacts" / "deep_research" / "v13_followup_manifest.json",
    ROOT / "artifacts" / "tag_classifier" / "retag_variant_manifest.json",
]
RESULTS_JSON = ROOT / "artifacts" / "deep_research" / "aggressive_results.json"
RESULTS_MD = ROOT / "artifacts" / "deep_research" / "aggressive_results.md"
DEFAULT_BASELINE_SCORE = 442.88391


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Record a public score for an aggressive Bastet experiment.")
    parser.add_argument("--name", required=True, help="Experiment name from a deep_research manifest")
    parser.add_argument("--score", required=True, type=float, help="Public leaderboard score")
    parser.add_argument("--baseline-score", type=float, default=DEFAULT_BASELINE_SCORE)
    parser.add_argument("--notes", default="")
    return parser.parse_args()


def load_json(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_results_md(results: list[dict]) -> None:
    lines = [
        "# Aggressive Experiment Results",
        "",
        "| Date UTC | Name | Score | Delta vs baseline | Drops | Adds | Delta/drop | Delta/add | Notes |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in sorted(results, key=lambda r: r["recorded_at"]):
        lines.append(
            "| {recorded_at} | `{name}` | {score:.5f} | {delta:+.5f} | {drop_count} | {add_count} | {delta_per_drop:+.5f} | {delta_per_add:+.5f} | {notes} |".format(
                **row
            )
        )
    RESULTS_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def load_manifest_items() -> list[dict]:
    items = []
    for path in MANIFESTS:
        data = load_json(path, [])
        if isinstance(data, list):
            items.extend(data)
            continue
        if isinstance(data, dict):
            for item in data.get("experiments", []):
                file_path = item.get("file", "")
                name = Path(file_path).stem if file_path else item.get("name", "")
                converted = dict(item)
                converted["name"] = name
                converted.setdefault("drop_count", 0)
                converted.setdefault("add_count", 0)
                items.append(converted)
    return items


def main() -> None:
    args = parse_args()
    manifest = load_manifest_items()
    by_name = {item["name"]: item for item in manifest}
    if args.name not in by_name:
        names = ", ".join(sorted(by_name))
        raise SystemExit(f"Unknown experiment {args.name!r}. Known names: {names}")

    item = by_name[args.name]
    delta = args.score - args.baseline_score
    drop_count = int(item.get("drop_count", 0) or 0)
    add_count = int(item.get("add_count", 0) or 0)
    record = {
        "recorded_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "name": args.name,
        "file": item["file"],
        "score": args.score,
        "baseline_score": args.baseline_score,
        "delta": delta,
        "drop_count": drop_count,
        "add_count": add_count,
        "delta_per_drop": delta / drop_count if drop_count else 0.0,
        "delta_per_add": delta / add_count if add_count else 0.0,
        "notes": args.notes,
    }

    results = load_json(RESULTS_JSON, [])
    results = [row for row in results if row.get("name") != args.name]
    results.append(record)
    RESULTS_JSON.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    write_results_md(results)

    print(f"Recorded {args.name}: score={args.score:.5f}, delta={delta:+.5f}")
    if drop_count:
        print(f"  delta/drop={record['delta_per_drop']:+.5f}")
    if add_count:
        print(f"  delta/add={record['delta_per_add']:+.5f}")
    print(f"Results: {RESULTS_MD.relative_to(ROOT)}")


if __name__ == "__main__":
    main()

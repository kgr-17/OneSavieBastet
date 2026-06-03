from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path


DEFAULT_TEAM_PRESET = (
    {
        "name": "first_achieve_v9",
        "score": 125.87789,
        "paths": ("outputs/first_achieve_v9.csv", "first_achieve_v9.csv"),
    },
    {
        "name": "first_achieve_v12",
        "score": 123.47993,
        "paths": ("outputs/first_achieve_v12.csv", "first_achieve_v12.csv"),
    },
    {
        "name": "submission_v3",
        "score": 122.63830,
        "paths": ("outputs/submission_v3.csv", "submission_v3.csv"),
    },
    {
        "name": "submission_v4",
        "score": 119.61015,
        "paths": ("outputs/submission_v4.csv", "submission_v4.csv"),
    },
)

REQUIRED_COLUMNS = ("repo_path", "severity", "tag", "subtag", "description")
COLUMN_ALIASES = {
    "repo_id": "repo_path",
    "repo": "repo_path",
}


@dataclass
class ModelSpec:
    name: str
    path: Path
    score: float
    weight: float = 0.0
    rows: int = 0
    unique_findings: int = 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a score-weighted ensemble submission for Bastet."
    )
    parser.add_argument(
        "--model",
        action="append",
        nargs=3,
        metavar=("NAME", "PATH", "SCORE"),
        help=(
            "Custom model definition. Repeat as needed. "
            "When omitted, the built-in team preset is used."
        ),
    )
    parser.add_argument(
        "--output",
        default="outputs/submission_weighted_ensemble.csv",
        help="Where to write the final ensemble CSV.",
    )
    parser.add_argument(
        "--summary-json",
        default="outputs/submission_weighted_ensemble_summary.json",
        help="Where to write a JSON summary of weights and selected findings.",
    )
    parser.add_argument(
        "--sample-submission",
        default="submission_example.csv",
        help="Reference CSV used to preserve column order.",
    )
    parser.add_argument("--target-rows", type=int, default=400)
    parser.add_argument(
        "--max-per-repo",
        type=int,
        default=10,
        help="Soft cap for the first ensemble pass before global backfill.",
    )
    parser.add_argument(
        "--min-per-repo",
        type=int,
        default=3,
        help="Minimum predictions per repo in the adaptive cap (solo-model repos).",
    )
    parser.add_argument(
        "--weight-mode",
        choices=("shifted-linear", "softmax", "raw"),
        default="shifted-linear",
        help="How leaderboard scores are converted into model weights.",
    )
    parser.add_argument(
        "--softmax-temperature",
        type=float,
        default=3.0,
        help="Temperature used only when --weight-mode=softmax.",
    )
    parser.add_argument(
        "--pad-token",
        default="empty",
        help="Padding token used when fewer than target rows are selected.",
    )
    parser.add_argument(
        "--strict-models",
        action="store_true",
        help="Fail instead of skipping missing model CSVs.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print a few top-ranked ensemble findings.",
    )
    return parser.parse_args()


def resolve_default_models(strict_models: bool) -> list[ModelSpec]:
    specs: list[ModelSpec] = []
    missing: list[str] = []

    for item in DEFAULT_TEAM_PRESET:
        resolved_path = None
        for raw_path in item["paths"]:
            candidate = Path(raw_path)
            if candidate.exists():
                resolved_path = candidate
                break

        if resolved_path is None:
            joined_paths = ", ".join(item["paths"])
            missing.append(f"{item['name']} ({joined_paths})")
            continue

        specs.append(
            ModelSpec(
                name=item["name"],
                path=resolved_path,
                score=float(item["score"]),
            )
        )

    if strict_models and missing:
        raise FileNotFoundError(
            "Missing preset model CSVs: " + "; ".join(missing)
        )

    if missing:
        print("Skipped missing preset model CSVs:")
        for item in missing:
            print(f"  - {item}")

    return specs


def build_model_specs(args: argparse.Namespace) -> list[ModelSpec]:
    if args.model:
        return [
            ModelSpec(name=name, path=Path(path), score=float(score))
            for name, path, score in args.model
        ]
    return resolve_default_models(strict_models=args.strict_models)


def load_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def read_expected_columns(sample_submission_path: Path) -> list[str]:
    rows = load_csv_rows(sample_submission_path)
    if not rows:
        raise ValueError(f"Sample submission is empty: {sample_submission_path}")
    return list(rows[0].keys())


def normalize_submission_rows(
    rows: list[dict[str, str]],
    model_name: str,
    pad_token: str,
) -> list[dict[str, str]]:
    if not rows:
        return []

    incoming_columns = rows[0].keys()
    normalized_columns = {
        COLUMN_ALIASES.get(column.strip(), column.strip()): column
        for column in incoming_columns
    }
    missing_columns = [
        column for column in REQUIRED_COLUMNS if column not in normalized_columns
    ]
    if missing_columns:
        raise ValueError(
            f"{model_name} is missing required columns: {', '.join(missing_columns)}"
        )

    normalized_rows: list[dict[str, str]] = []
    for row in rows:
        normalized_row = {
            normalized_name: str(row.get(source_name, "") or "").strip()
            for normalized_name, source_name in normalized_columns.items()
        }
        if normalized_row["repo_path"].lower() == pad_token.lower():
            continue
        normalized_rows.append(normalized_row)

    return normalized_rows


def load_model_predictions(spec: ModelSpec, pad_token: str) -> list[dict[str, str]]:
    if not spec.path.exists():
        raise FileNotFoundError(f"Model CSV not found: {spec.path}")

    raw_rows = load_csv_rows(spec.path)
    rows = normalize_submission_rows(raw_rows, spec.name, pad_token=pad_token)
    spec.rows = len(rows)

    deduped_rows: list[dict[str, str]] = []
    seen_keys: set[tuple[str, str, str]] = set()
    for row in rows:
        key = (row["repo_path"], row["tag"], row["subtag"])
        if key in seen_keys:
            continue
        seen_keys.add(key)
        deduped_rows.append(row)

    spec.unique_findings = len(deduped_rows)
    return deduped_rows


def compute_model_weights(
    specs: list[ModelSpec],
    mode: str,
    softmax_temperature: float,
) -> None:
    if not specs:
        return

    scores = [spec.score for spec in specs]

    if len(specs) == 1:
        raw_weights = [1.0]
    elif mode == "raw":
        raw_weights = scores
    elif mode == "shifted-linear":
        min_score = min(scores)
        raw_weights = [(score - min_score) + 1.0 for score in scores]
    else:
        if softmax_temperature <= 0:
            raise ValueError("--softmax-temperature must be positive.")
        max_score = max(scores)
        raw_weights = [
            math.exp((score - max_score) / softmax_temperature) for score in scores
        ]

    total_weight = sum(raw_weights)
    if total_weight <= 0:
        raise ValueError("Could not compute positive model weights.")

    for spec, raw_weight in zip(specs, raw_weights):
        spec.weight = raw_weight / total_weight


def pick_weighted_severity(
    severity_votes: dict[str, float],
    best_model_severity: str,
) -> str:
    if not severity_votes:
        return best_model_severity or "Medium"

    return max(
        severity_votes.items(),
        key=lambda item: (
            item[1],
            item[0] == best_model_severity,
            item[0] == "High",
            item[0],
        ),
    )[0]


def aggregate_candidates(
    model_frames: list[tuple[ModelSpec, list[dict[str, str]]]],
) -> list[dict[str, object]]:
    buckets: dict[tuple[str, str, str], dict[str, object]] = {}
    model_count = len(model_frames)

    for spec, rows in model_frames:
        for row in rows:
            key = (row["repo_path"], row["tag"], row["subtag"])
            bucket = buckets.setdefault(
                key,
                {
                    "repo_path": row["repo_path"],
                    "tag": row["tag"],
                    "subtag": row["subtag"],
                    "support_weight": 0.0,
                    "support_count": 0,
                    "best_model_name": "",
                    "best_model_score": float("-inf"),
                    "best_model_weight": 0.0,
                    "best_description": "",
                    "best_model_severity": "Medium",
                    "supporting_models": [],
                    "severity_votes": defaultdict(float),
                },
            )

            bucket["support_weight"] += spec.weight
            bucket["support_count"] += 1
            bucket["supporting_models"].append(spec.name)
            bucket["severity_votes"][row["severity"]] += spec.weight

            if (
                spec.score > bucket["best_model_score"]
                or (
                    spec.score == bucket["best_model_score"]
                    and spec.weight > bucket["best_model_weight"]
                )
            ):
                bucket["best_model_name"] = spec.name
                bucket["best_model_score"] = spec.score
                bucket["best_model_weight"] = spec.weight
                bucket["best_description"] = row["description"]
                bucket["best_model_severity"] = row["severity"]

    candidates: list[dict[str, object]] = []
    divisor = max(1, model_count - 1)

    for bucket in buckets.values():
        consensus_bonus = ((bucket["support_count"] - 1) / divisor) * 0.20
        leader_bonus = bucket["best_model_weight"] * 0.15
        rank_score = bucket["support_weight"] + consensus_bonus + leader_bonus

        severity = pick_weighted_severity(
            severity_votes=dict(bucket["severity_votes"]),
            best_model_severity=str(bucket["best_model_severity"]),
        )

        candidates.append(
            {
                "repo_path": bucket["repo_path"],
                "tag": bucket["tag"],
                "subtag": bucket["subtag"],
                "severity": severity,
                "description": bucket["best_description"],
                "rank_score": rank_score,
                "support_weight": bucket["support_weight"],
                "support_count": bucket["support_count"],
                "best_model_name": bucket["best_model_name"],
                "best_model_score": bucket["best_model_score"],
                "supporting_models": sorted(
                    bucket["supporting_models"],
                    key=lambda name: (
                        -next(
                            spec.score
                            for spec, _ in model_frames
                            if spec.name == name
                        ),
                        name,
                    ),
                ),
            }
        )

    candidates.sort(
        key=lambda item: (
            -float(item["rank_score"]),
            -float(item["best_model_score"]),
            -int(item["support_count"]),
            str(item["repo_path"]),
            str(item["tag"]),
            str(item["subtag"]),
        )
    )
    return candidates


def compute_repo_cap(
    repo_path: str,
    candidates_by_repo: dict[str, list[dict]],
    flat_max: int,
    min_cap: int,
) -> int:
    """Adaptive per-repo prediction cap based on cross-model consensus.

    Repos where many models agree on many findings get a higher cap (up to
    flat_max). Repos covered by only one model stay conservative (min_cap or
    5, whichever is larger) to avoid over-reporting penalties.
    """
    repo_candidates = candidates_by_repo.get(repo_path, [])
    if not repo_candidates:
        return min_cap

    high_consensus = sum(
        1 for c in repo_candidates if int(c["support_count"]) >= 3
    )
    if high_consensus >= 3:
        return flat_max
    elif high_consensus >= 1:
        return max(min_cap, min(flat_max, high_consensus * 2 + 4))
    else:
        return max(min_cap, 5)


def select_candidates(
    candidates: list[dict[str, object]],
    target_rows: int,
    max_per_repo: int,
    min_per_repo: int = 3,
) -> tuple[list[dict[str, object]], Counter]:
    selected: list[dict[str, object]] = []
    selected_keys: set[tuple[str, str, str]] = set()
    repo_counts: Counter = Counter()

    # Pre-group candidates by repo for the adaptive cap calculation
    candidates_by_repo: dict[str, list[dict]] = defaultdict(list)
    for candidate in candidates:
        candidates_by_repo[str(candidate["repo_path"])].append(candidate)

    for candidate in candidates:
        key = (
            str(candidate["repo_path"]),
            str(candidate["tag"]),
            str(candidate["subtag"]),
        )
        repo_path = str(candidate["repo_path"])
        repo_cap = compute_repo_cap(
            repo_path, candidates_by_repo, max_per_repo, min_per_repo
        )

        if key in selected_keys or repo_counts[repo_path] >= repo_cap:
            continue

        selected.append(candidate)
        selected_keys.add(key)
        repo_counts[repo_path] += 1

        if len(selected) >= target_rows:
            return selected, repo_counts

    for candidate in candidates:
        key = (
            str(candidate["repo_path"]),
            str(candidate["tag"]),
            str(candidate["subtag"]),
        )
        repo_path = str(candidate["repo_path"])

        if key in selected_keys:
            continue

        selected.append(candidate)
        selected_keys.add(key)
        repo_counts[repo_path] += 1

        if len(selected) >= target_rows:
            break

    return selected, repo_counts


def build_submission_frame(
    selected: list[dict[str, object]],
    expected_columns: list[str],
    target_rows: int,
    pad_token: str,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []

    for index, candidate in enumerate(selected[:target_rows], start=1):
        rows.append(
            {
                "Property": index,
                "repo_path": candidate["repo_path"],
                "severity": candidate["severity"],
                "tag": candidate["tag"],
                "subtag": candidate["subtag"],
                "description": candidate["description"],
            }
        )

    while len(rows) < target_rows:
        property_value = len(rows) + 1
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


def write_submission_csv(
    output_path: Path,
    rows: list[dict[str, object]],
    expected_columns: list[str],
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=expected_columns)
        writer.writeheader()
        writer.writerows(rows)


def write_summary(
    summary_path: Path,
    specs: list[ModelSpec],
    selected: list[dict[str, object]],
    repo_counts: Counter,
    args: argparse.Namespace,
) -> None:
    summary_path.parent.mkdir(parents=True, exist_ok=True)

    summary = {
        "weight_mode": args.weight_mode,
        "softmax_temperature": args.softmax_temperature,
        "target_rows": args.target_rows,
        "max_per_repo_first_pass": args.max_per_repo,
        "min_per_repo": args.min_per_repo,
        "selected_rows": len(selected),
        "unique_repos": len(repo_counts),
        "models": [
            {
                "name": spec.name,
                "path": str(spec.path),
                "score": spec.score,
                "weight": round(spec.weight, 8),
                "rows": spec.rows,
                "unique_findings": spec.unique_findings,
            }
            for spec in specs
        ],
        "repo_counts": dict(repo_counts.most_common()),
        "top_candidates": [
            {
                "repo_path": candidate["repo_path"],
                "tag": candidate["tag"],
                "subtag": candidate["subtag"],
                "rank_score": round(float(candidate["rank_score"]), 8),
                "support_weight": round(float(candidate["support_weight"]), 8),
                "support_count": int(candidate["support_count"]),
                "best_model_name": candidate["best_model_name"],
                "best_model_score": candidate["best_model_score"],
                "supporting_models": candidate["supporting_models"],
            }
            for candidate in selected[:25]
        ],
    }

    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")


def main() -> None:
    args = parse_args()

    specs = build_model_specs(args)
    if not specs:
        raise ValueError(
            "No model CSVs available. Add --model entries or place preset CSVs in the workspace."
        )

    compute_model_weights(
        specs=specs,
        mode=args.weight_mode,
        softmax_temperature=args.softmax_temperature,
    )

    expected_columns = read_expected_columns(Path(args.sample_submission))

    model_frames: list[tuple[ModelSpec, list[dict[str, str]]]] = []
    for spec in specs:
        frame = load_model_predictions(spec, pad_token=args.pad_token)
        model_frames.append((spec, frame))

    candidates = aggregate_candidates(model_frames)
    selected, repo_counts = select_candidates(
        candidates=candidates,
        target_rows=args.target_rows,
        max_per_repo=args.max_per_repo,
        min_per_repo=args.min_per_repo,
    )

    submission_rows = build_submission_frame(
        selected=selected,
        expected_columns=expected_columns,
        target_rows=args.target_rows,
        pad_token=args.pad_token,
    )

    output_path = Path(args.output)
    write_submission_csv(output_path, submission_rows, expected_columns)

    summary_path = Path(args.summary_json)
    write_summary(summary_path, specs, selected, repo_counts, args)

    print("Model weights:")
    for spec in sorted(specs, key=lambda item: (-item.weight, -item.score, item.name)):
        print(
            f"  - {spec.name}: score={spec.score:.5f}, weight={spec.weight:.4f}, "
            f"rows={spec.rows}, unique_findings={spec.unique_findings}, path={spec.path}"
        )

    print(f"\nAggregated candidates: {len(candidates)}")
    print(f"Selected rows before padding: {len(selected)}")
    print(f"Unique repos covered: {len(repo_counts)}")
    print(f"Saved ensemble CSV to: {output_path}")
    print(f"Saved summary JSON to: {summary_path}")

    if args.verbose:
        print("\nTop ensemble findings:")
        for candidate in selected[:10]:
            print(
                "  - "
                f"{candidate['repo_path']} | {candidate['tag']} | {candidate['subtag']} "
                f"| rank={candidate['rank_score']:.4f} "
                f"| models={','.join(candidate['supporting_models'])}"
            )


if __name__ == "__main__":
    main()

"""Rank submission CSVs on a 20% teammate-row proxy validation split.

This is for public-test submissions whose repo hashes do not overlap train.csv.
It hides 20% of rows from a reference submission, then scores candidate CSVs
against that proxy truth using the same repository-level scorer.

The output is a ranking table plus JSON/CSV artifacts.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.holdout_score import (  # noqa: E402
    filter_candidate_rows,
    load_csv_rows,
    make_description_scorer,
    non_padding_rows,
    score_against_proxy,
    split_proxy_truth,
)


DEFAULT_REFERENCE = "outputs/submission_c4_v11.csv"
DEFAULT_ARTIFACTS_DIR = "artifacts/deep_research/validation20"
DEFAULT_CANDIDATES = [
    "outputs/submission_c4_v8.csv",
    "outputs/submission_c4_v10.csv",
    "outputs/submission_c4_v11.csv",
    "outputs/submission_c4_v12_miso.csv",
    "outputs/aggressive/exp_v13_known8_tierb.csv",
    "outputs/aggressive/exp_v14_known8_lowconf.csv",
    "outputs/aggressive/exp_v15_top20_mixed.csv",
    "outputs/aggressive/exp_v16_top40_mixed.csv",
    "outputs/aggressive/exp_v17_label_patch_known_current.csv",
    "outputs/aggressive/probe_v11_blank_tierb8.csv",
    "outputs/aggressive/probe_v11_blank_lowconf10.csv",
    "outputs/aggressive/probe_v11_blank_stakehouse10.csv",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Score candidates on a 20% proxy validation split.")
    parser.add_argument("--reference", default=DEFAULT_REFERENCE)
    parser.add_argument("--candidates", nargs="*", default=DEFAULT_CANDIDATES)
    parser.add_argument("--holdout-frac", type=float, default=0.2)
    parser.add_argument("--seeds", nargs="*", type=int, default=[1337])
    parser.add_argument("--scorer", choices=["bge", "lexical"], default="bge")
    parser.add_argument("--artifacts-dir", default=DEFAULT_ARTIFACTS_DIR)
    parser.add_argument("--pad-token", default="empty")
    parser.add_argument("--description-threshold", type=float, default=0.7)
    parser.add_argument("--bge-model-name", default="BAAI/bge-large-en-v1.5")
    return parser.parse_args()


def rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path.resolve())


def mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def stdev(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    mu = mean(values)
    return (sum((value - mu) ** 2 for value in values) / (len(values) - 1)) ** 0.5


def candidate_name(path: Path) -> str:
    return path.stem


def compact(metrics: dict) -> dict:
    return {
        "score": metrics["final_score"],
        "score_per_truth_row": metrics["score_per_truth_row"],
        "matched_pair_count": metrics["matched_pair_count"],
        "prediction_row_count": metrics["prediction_row_count"],
        "truth_row_count": metrics["truth_row_count"],
    }


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    args = parse_args()
    artifacts_dir = Path(args.artifacts_dir)
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    reference_path = Path(args.reference)
    reference_rows = non_padding_rows(load_csv_rows(reference_path), args.pad_token)

    scorer = make_description_scorer(args)
    candidate_paths = [Path(path) for path in args.candidates if Path(path).exists()]
    if not candidate_paths:
        raise SystemExit("No candidate CSVs found.")

    raw_results = []
    aggregate = {}

    for seed in args.seeds:
        proxy_truth_rows, reference_remaining_rows, split_by_repo = split_proxy_truth(
            reference_rows,
            args.holdout_frac,
            seed,
        )
        baseline_metrics = score_against_proxy(reference_remaining_rows, proxy_truth_rows, scorer)

        for candidate_path in candidate_paths:
            candidate_rows = non_padding_rows(load_csv_rows(candidate_path), args.pad_token)
            candidate_filtered_rows, removed_hidden = filter_candidate_rows(candidate_rows, proxy_truth_rows)
            metrics = score_against_proxy(candidate_filtered_rows, proxy_truth_rows, scorer)
            delta = metrics["final_score"] - baseline_metrics["final_score"]
            row = {
                "seed": seed,
                "candidate": candidate_name(candidate_path),
                "path": rel(candidate_path),
                "score": metrics["final_score"],
                "baseline_score": baseline_metrics["final_score"],
                "delta": delta,
                "score_per_truth_row": metrics["score_per_truth_row"],
                "matched_pairs": metrics["matched_pair_count"],
                "prediction_rows_scored": metrics["prediction_row_count"],
                "candidate_rows": len(candidate_rows),
                "hidden_rows_removed": removed_hidden,
                "proxy_truth_rows": len(proxy_truth_rows),
                "reference_remaining_rows": len(reference_remaining_rows),
                "repo_count": len(split_by_repo),
            }
            raw_results.append(row)
            aggregate.setdefault(candidate_name(candidate_path), {"path": rel(candidate_path), "runs": []})
            aggregate[candidate_name(candidate_path)]["runs"].append(row)

    ranking = []
    for name, payload in aggregate.items():
        runs = payload["runs"]
        deltas = [float(run["delta"]) for run in runs]
        scores = [float(run["score"]) for run in runs]
        ranking.append(
            {
                "rank": 0,
                "candidate": name,
                "path": payload["path"],
                "mean_score": mean(scores),
                "mean_delta": mean(deltas),
                "delta_stdev": stdev(deltas),
                "best_delta": max(deltas),
                "worst_delta": min(deltas),
                "seeds": ",".join(str(seed) for seed in args.seeds),
                "runs": len(runs),
            }
        )
    ranking.sort(key=lambda row: (-row["mean_delta"], -row["mean_score"], row["candidate"]))
    for index, row in enumerate(ranking, 1):
        row["rank"] = index

    report = {
        "reference": rel(reference_path),
        "holdout_frac": args.holdout_frac,
        "seeds": args.seeds,
        "description_backend": {
            "requested": args.scorer,
            "used": scorer.used_mode,
            "threshold": args.description_threshold,
            "note": scorer.note,
        },
        "ranking": ranking,
        "raw_results": raw_results,
    }
    (artifacts_dir / "validation20_report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    write_csv(artifacts_dir / "validation20_ranking.csv", ranking)
    write_csv(artifacts_dir / "validation20_raw_results.csv", raw_results)

    lines = [
        "# 20% Proxy Validation Ranking",
        "",
        f"Reference: `{rel(reference_path)}`",
        f"Holdout fraction: {args.holdout_frac:.2f}",
        f"Seeds: {', '.join(str(seed) for seed in args.seeds)}",
        f"Scorer used: {scorer.used_mode}",
        "",
        "| Rank | Candidate | Mean score | Mean delta | Delta stdev | Best delta | Worst delta |",
        "|---:|---|---:|---:|---:|---:|---:|",
    ]
    for row in ranking:
        lines.append(
            "| {rank} | `{candidate}` | {mean_score:.6f} | {mean_delta:+.6f} | {delta_stdev:.6f} | {best_delta:+.6f} | {worst_delta:+.6f} |".format(
                **row
            )
        )
    (artifacts_dir / "validation20_ranking.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    best = ranking[0]
    print("20% proxy validation complete.")
    print(f"Scorer used: {scorer.used_mode}")
    print(
        f"Best: {best['candidate']} mean_score={best['mean_score']:.6f} "
        f"mean_delta={best['mean_delta']:+.6f}"
    )
    print(f"Ranking: {artifacts_dir / 'validation20_ranking.md'}")


if __name__ == "__main__":
    main()

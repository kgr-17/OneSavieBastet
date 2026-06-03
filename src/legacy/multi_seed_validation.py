from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run Bastet validation across multiple seeds and summarize stability. "
            "Use this to judge generalization, not just one fixed holdout split."
        )
    )
    parser.add_argument(
        "--seeds",
        nargs="+",
        type=int,
        default=[1337, 7, 2024],
        help="Validation seeds to evaluate.",
    )
    parser.add_argument(
        "--base-command",
        required=True,
        help=(
            "Base command passed to run_validation_standard.py after the seed/run-name flags. "
            "Example: --generator custom --description-scorer bge --generator-command \"python src/...\""
        ),
    )
    parser.add_argument(
        "--label",
        default="candidate",
        help="Short label used for run names and summary output.",
    )
    parser.add_argument(
        "--summary-json",
        default="outputs/multi_seed_validation_summary.json",
        help="Where to save the aggregated summary JSON.",
    )
    return parser.parse_args()


def run_one(seed: int, label: str, base_command: str) -> dict:
    run_name = f"{label}-seed{seed}"
    command = [
        sys.executable,
        "src/run_validation_standard.py",
        "--seed",
        str(seed),
        "--run-name",
        run_name,
    ]
    command.extend(base_command.split(" "))
    # Rebuild quoted sections by letting the shell parser handle them.
    # We invoke a subprocess with shell=False, so re-parse safely here.
    import shlex

    command = [
        sys.executable,
        "src/run_validation_standard.py",
        "--seed",
        str(seed),
        "--run-name",
        run_name,
        *shlex.split(base_command),
    ]

    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )

    if completed.returncode != 0:
        raise RuntimeError(
            f"Seed {seed} failed.\nCommand: {' '.join(command)}\n"
            f"Stdout:\n{completed.stdout}\nStderr:\n{completed.stderr}"
        )

    report_path = (
        Path("artifacts/validation-standard")
        / run_name
        / "outputs"
        / "holdout_evaluation_report.json"
    )
    report = json.loads(report_path.read_text(encoding="utf-8"))
    structured = report["metrics"]["structured"]

    return {
        "seed": seed,
        "run_name": run_name,
        "structured_score": structured["final_score"],
        "score_per_truth_row": structured["score_per_truth_row"],
        "matched_pairs": structured["matched_pair_count"],
        "predicted_rows": structured["prediction_row_count"],
        "truth_rows": structured["truth_row_count"],
        "description_mode": report["description_backend"]["used_mode"],
        "stdout": completed.stdout,
    }


def main() -> None:
    args = parse_args()

    runs = [run_one(seed, args.label, args.base_command) for seed in args.seeds]
    scores = [run["structured_score"] for run in runs]
    recalls = [run["score_per_truth_row"] for run in runs]

    summary = {
        "label": args.label,
        "seeds": args.seeds,
        "mean_structured_score": statistics.mean(scores),
        "std_structured_score": statistics.pstdev(scores) if len(scores) > 1 else 0.0,
        "min_structured_score": min(scores),
        "max_structured_score": max(scores),
        "mean_score_per_truth_row": statistics.mean(recalls),
        "runs": runs,
    }

    summary_path = Path(args.summary_json)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(f"Label: {args.label}")
    print(f"Seeds: {', '.join(str(seed) for seed in args.seeds)}")
    print(f"Mean structured score: {summary['mean_structured_score']:.4f}")
    print(f"Std structured score: {summary['std_structured_score']:.4f}")
    print(f"Min structured score: {summary['min_structured_score']:.4f}")
    print(f"Max structured score: {summary['max_structured_score']:.4f}")
    print(f"Mean score per truth row: {summary['mean_score_per_truth_row']:.4f}")
    print(f"Saved summary to: {summary_path}")


if __name__ == "__main__":
    main()

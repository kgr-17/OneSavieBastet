import argparse
import csv
import json
import random
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.run_validation_standard import (  # noqa: E402
    DescriptionScorer,
    build_finding_row,
    evaluate_repository,
    is_padding_row,
    normalize_text,
)


DEFAULT_REFERENCE = "teamate_hightst_submission.csv"
DEFAULT_ARTIFACTS_DIR = "artifacts/holdout-score"
DEFAULT_THRESHOLD = 0.7
DEFAULT_BGE_MODEL = "BAAI/bge-large-en-v1.5"


def parse_args():
    parser = argparse.ArgumentParser(
        description="Score a candidate against a teammate-row proxy holdout."
    )
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--reference", default=DEFAULT_REFERENCE)
    parser.add_argument("--holdout-frac", type=float, default=0.2)
    parser.add_argument("--seed", type=int, default=1337)
    parser.add_argument("--scorer", choices=["bge", "lexical"], default="bge")
    parser.add_argument("--run-name", default="")
    parser.add_argument("--artifacts-dir", default=DEFAULT_ARTIFACTS_DIR)
    parser.add_argument("--pad-token", default="empty")
    parser.add_argument("--description-threshold", type=float, default=DEFAULT_THRESHOLD)
    parser.add_argument("--bge-model-name", default=DEFAULT_BGE_MODEL)
    return parser.parse_args()


def load_csv_rows(path):
    with open(path, newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def non_padding_rows(rows, pad_token):
    return [row for row in rows if not is_padding_row(row, pad_token)]


def group_rows_by_repo(rows):
    by_repo = defaultdict(list)
    for row in rows:
        repo_path = normalize_text(row.get("repo_path", ""))
        if repo_path:
            by_repo[repo_path].append(row)
    return by_repo


def split_proxy_truth(reference_rows, holdout_frac, seed):
    if not 0 < holdout_frac < 1:
        raise ValueError("--holdout-frac must be between 0 and 1.")

    proxy_truth = []
    reference_remaining = []
    split_by_repo = {}
    by_repo = group_rows_by_repo(reference_rows)

    rng = random.Random(seed)
    for repo_path in sorted(by_repo):
        rows = by_repo[repo_path]
        holdout_count = max(1, min(len(rows), int(round(len(rows) * holdout_frac))))
        holdout_indices = set(rng.sample(range(len(rows)), holdout_count))
        repo_truth = []
        repo_remaining = []
        for index, row in enumerate(rows):
            if index in holdout_indices:
                proxy_truth.append(row)
                repo_truth.append(row)
            else:
                reference_remaining.append(row)
                repo_remaining.append(row)
        split_by_repo[repo_path] = {
            "reference_rows": len(rows),
            "proxy_truth_rows": len(repo_truth),
            "reference_remaining_rows": len(repo_remaining),
        }

    return proxy_truth, reference_remaining, split_by_repo


def hidden_key(row):
    return (
        normalize_text(row.get("repo_path", "")),
        normalize_text(row.get("description", "")),
    )


def filter_candidate_rows(candidate_rows, proxy_truth_rows):
    hidden_keys = {hidden_key(row) for row in proxy_truth_rows}
    filtered = []
    removed_hidden = 0
    for row in candidate_rows:
        if hidden_key(row) in hidden_keys:
            removed_hidden += 1
            continue
        filtered.append(row)
    return filtered, removed_hidden


def make_description_scorer(args):
    if args.scorer == "lexical":
        return DescriptionScorer(
            requested_mode="lexical",
            threshold=args.description_threshold,
            model_name=args.bge_model_name,
        )

    try:
        return DescriptionScorer(
            requested_mode="bge",
            threshold=args.description_threshold,
            model_name=args.bge_model_name,
        )
    except RuntimeError as exc:
        print(
            f"WARNING: BGE scorer unavailable; falling back to lexical scorer. {exc}",
            file=sys.stderr,
        )
        scorer = DescriptionScorer(
            requested_mode="lexical",
            threshold=args.description_threshold,
            model_name=args.bge_model_name,
        )
        scorer.note = f"Requested BGE, fell back to lexical: {exc}"
        return scorer


def to_finding_rows(rows):
    return [build_finding_row(row) for row in rows]


def score_against_proxy(prediction_rows, proxy_truth_rows, description_scorer):
    truth_findings = to_finding_rows(proxy_truth_rows)
    prediction_findings = to_finding_rows(prediction_rows)

    truth_by_repo = defaultdict(list)
    prediction_by_repo = defaultdict(list)
    for finding in truth_findings:
        truth_by_repo[finding.repo_path].append(finding)
    for finding in prediction_findings:
        prediction_by_repo[finding.repo_path].append(finding)

    repo_results = []
    final_score = 0.0
    matched_pairs = 0
    for repo_path in sorted(truth_by_repo):
        result = evaluate_repository(
            repo_path,
            prediction_by_repo.get(repo_path, []),
            truth_by_repo[repo_path],
            description_scorer,
        )
        repo_results.append(result)
        final_score += result["repo_score"]
        matched_pairs += result["matched_pair_count"]

    return {
        "final_score": final_score,
        "score_per_truth_row": final_score / len(truth_findings) if truth_findings else 0.0,
        "prediction_row_count": len(prediction_findings),
        "truth_row_count": len(truth_findings),
        "matched_pair_count": matched_pairs,
        "repo_results": repo_results,
    }


def compact_repo_result(result):
    return {
        "repo_path": result["repo_path"],
        "score": result["repo_score"],
        "matched_pairs": result["matched_pair_count"],
        "predicted_rows": result["prediction_row_count"],
        "truth_rows": result["truth_row_count"],
        "penalty": result["over_reporting_penalty"],
    }


def build_repo_deltas(candidate_results, baseline_results):
    by_repo = {}
    for result in baseline_results:
        by_repo.setdefault(result["repo_path"], {})["baseline"] = compact_repo_result(result)
    for result in candidate_results:
        by_repo.setdefault(result["repo_path"], {})["candidate"] = compact_repo_result(result)

    deltas = []
    for repo_path, payload in by_repo.items():
        baseline = payload.get(
            "baseline",
            {"score": 0.0, "matched_pairs": 0, "predicted_rows": 0, "truth_rows": 0, "penalty": 0},
        )
        candidate = payload.get(
            "candidate",
            {"score": 0.0, "matched_pairs": 0, "predicted_rows": 0, "truth_rows": 0, "penalty": 0},
        )
        deltas.append(
            {
                "repo_path": repo_path,
                "delta": candidate["score"] - baseline["score"],
                "candidate": candidate,
                "baseline": baseline,
            }
        )
    deltas.sort(key=lambda item: (-abs(item["delta"]), item["repo_path"]))
    return deltas


def main():
    args = parse_args()
    run_name = args.run_name.strip() or (
        f"holdout_score_{Path(args.candidate).stem}_seed{args.seed}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    )
    run_dir = Path(args.artifacts_dir) / run_name
    run_dir.mkdir(parents=True, exist_ok=True)

    reference_rows = non_padding_rows(load_csv_rows(args.reference), args.pad_token)
    candidate_rows = non_padding_rows(load_csv_rows(args.candidate), args.pad_token)

    proxy_truth_rows, reference_remaining_rows, split_by_repo = split_proxy_truth(
        reference_rows,
        args.holdout_frac,
        args.seed,
    )
    candidate_filtered_rows, removed_hidden = filter_candidate_rows(candidate_rows, proxy_truth_rows)

    description_scorer = make_description_scorer(args)
    baseline_metrics = score_against_proxy(
        reference_remaining_rows,
        proxy_truth_rows,
        description_scorer,
    )
    candidate_metrics = score_against_proxy(
        candidate_filtered_rows,
        proxy_truth_rows,
        description_scorer,
    )
    delta = candidate_metrics["final_score"] - baseline_metrics["final_score"]
    repo_deltas = build_repo_deltas(
        candidate_metrics["repo_results"],
        baseline_metrics["repo_results"],
    )

    report = {
        "run_name": run_name,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "args": {
            "candidate": str(Path(args.candidate).resolve()),
            "reference": str(Path(args.reference).resolve()),
            "holdout_frac": args.holdout_frac,
            "seed": args.seed,
            "requested_scorer": args.scorer,
            "description_threshold": args.description_threshold,
        },
        "description_backend": {
            "requested_mode": args.scorer,
            "used_mode": description_scorer.used_mode,
            "model_name": args.bge_model_name,
            "threshold": args.description_threshold,
            "note": description_scorer.note,
        },
        "split": {
            "reference_rows": len(reference_rows),
            "candidate_rows": len(candidate_rows),
            "proxy_truth_rows": len(proxy_truth_rows),
            "reference_remaining_rows": len(reference_remaining_rows),
            "candidate_filtered_rows": len(candidate_filtered_rows),
            "candidate_hidden_rows_removed": removed_hidden,
            "repo_count": len(split_by_repo),
            "by_repo": split_by_repo,
        },
        "baseline": baseline_metrics,
        "candidate": candidate_metrics,
        "delta": delta,
        "passes_gate": delta > 0.0,
        "top_repo_deltas": repo_deltas[:10],
        "repo_deltas": repo_deltas,
    }

    report_path = run_dir / "report.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print(
        f"holdout_score run={run_name} scorer={description_scorer.used_mode} "
        f"candidate_score={candidate_metrics['final_score']:.6f} "
        f"baseline_score={baseline_metrics['final_score']:.6f} "
        f"delta={delta:+.6f} report={report_path}"
    )


if __name__ == "__main__":
    main()

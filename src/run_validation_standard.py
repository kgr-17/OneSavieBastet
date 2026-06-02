import argparse
import csv
import json
import math
import random
import re
import shlex
import subprocess
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


DEFAULT_HOLDOUT_FRACTION = 0.5
DEFAULT_SEED = 1337
DEFAULT_PAD_TOKEN = "empty"
DEFAULT_DESCRIPTION_THRESHOLD = 0.7
DEFAULT_BGE_MODEL_NAME = "BAAI/bge-large-en-v1.5"
TOKEN_PATTERN = re.compile(r"[a-z0-9_]+")


@dataclass(frozen=True)
class FindingRow:
    repo_path: str
    severity_raw: str
    tag_raw: str
    subtag_raw: str
    description: str
    severities: frozenset
    tags: frozenset
    subtags: frozenset
    unique_key: tuple


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Run the shared Bastet local validation standard with repository-level holdout, "
            "competition-style structured scoring, and reference-based gating."
        )
    )
    parser.add_argument("--generator", choices=["baseline", "baseline_v2", "custom"], default="baseline")
    parser.add_argument(
        "--generator-command",
        default="",
        help=(
            "Required when --generator custom. Supports placeholders: "
            "{train_csv}, {test_csv}, {sample_submission}, {output}, {train_repo_root}, "
            "{test_repo_root}, {target_rows}."
        ),
    )
    parser.add_argument(
        "--generator-extra-args",
        default="",
        help="Optional extra arguments appended to the generator command.",
    )
    parser.add_argument("--train-csv", default="train.csv")
    parser.add_argument("--sample-submission", default="submission_example.csv")
    parser.add_argument("--artifacts-dir", default="artifacts/validation-standard")
    parser.add_argument("--run-name", default="")
    parser.add_argument("--holdout-fraction", type=float, default=DEFAULT_HOLDOUT_FRACTION)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--target-rows", type=int, default=400)
    parser.add_argument("--pad-token", default=DEFAULT_PAD_TOKEN)
    parser.add_argument(
        "--train-repo-root",
        default="",
        help="Optional directory of extracted train repos for generators that can scan code.",
    )
    parser.add_argument(
        "--validation-repo-root",
        default="",
        help="Optional directory of extracted validation repos. Defaults to --train-repo-root.",
    )
    parser.add_argument(
        "--description-scorer",
        choices=["auto", "bge", "lexical"],
        default="auto",
        help="Description similarity backend. Auto tries BGE and falls back to lexical cosine.",
    )
    parser.add_argument(
        "--bge-model-name",
        default=DEFAULT_BGE_MODEL_NAME,
        help="Sentence-transformers model name to use when --description-scorer resolves to BGE.",
    )
    parser.add_argument(
        "--description-threshold",
        type=float,
        default=DEFAULT_DESCRIPTION_THRESHOLD,
        help="Description similarity threshold. Similarities at or below this value score as zero.",
    )
    parser.add_argument(
        "--reference-report",
        default="",
        help="Optional prior JSON report for automatic improvement gating.",
    )
    parser.add_argument(
        "--structured-improvement-min",
        type=float,
        default=0.0,
        help="Minimum structured-score improvement required versus the reference report.",
    )
    return parser.parse_args()


def load_csv_rows(path):
    with open(path, newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv_rows(path, rows, fieldnames):
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def normalize_text(value):
    return " ".join(str(value).replace("\r", " ").replace("\n", " ").strip().lower().split())


def normalize_label_text(value):
    return normalize_text(value).strip(",")


def split_labels(raw_value):
    labels = []
    for part in str(raw_value).split(","):
        normalized = normalize_label_text(part)
        if normalized:
            labels.append(normalized)
    return labels


def tokenize_text(value):
    return TOKEN_PATTERN.findall(normalize_text(value))


def is_padding_row(row, pad_token):
    repo_value = normalize_text(row.get("repo_path", ""))
    return not repo_value or repo_value == normalize_text(pad_token)


def clamp_holdout_count(repo_count, fraction):
    proposed = int(round(repo_count * fraction))
    return max(1, min(repo_count - 1, proposed))


def split_train_holdout(train_rows, holdout_fraction, seed):
    repo_ids = sorted({row["repo_path"].strip() for row in train_rows if row.get("repo_path", "").strip()})
    if len(repo_ids) < 2:
        raise ValueError("Need at least two repositories in train.csv to create a holdout split.")

    holdout_count = clamp_holdout_count(len(repo_ids), holdout_fraction)
    shuffled = list(repo_ids)
    random.Random(seed).shuffle(shuffled)

    holdout_repo_ids = set(shuffled[:holdout_count])
    train_repo_ids = set(shuffled[holdout_count:])

    split_train_rows = [row for row in train_rows if row["repo_path"].strip() in train_repo_ids]
    holdout_truth_rows = [row for row in train_rows if row["repo_path"].strip() in holdout_repo_ids]
    holdout_test_rows = [{"repo_path": repo_id} for repo_id in sorted(holdout_repo_ids)]

    return {
        "all_repo_ids": repo_ids,
        "train_repo_ids": sorted(train_repo_ids),
        "holdout_repo_ids": sorted(holdout_repo_ids),
        "split_train_rows": split_train_rows,
        "holdout_truth_rows": holdout_truth_rows,
        "holdout_test_rows": holdout_test_rows,
    }


def validate_prediction_format(rows, sample_rows, target_rows):
    if not sample_rows:
        raise ValueError("Sample submission is empty.")

    expected_columns = list(sample_rows[0].keys())
    actual_columns = list(rows[0].keys()) if rows else []

    if actual_columns != expected_columns:
        raise ValueError(f"Column mismatch. Expected {expected_columns}, found {actual_columns}")

    if len(rows) != target_rows:
        raise ValueError(f"Row count mismatch. Expected {target_rows}, found {len(rows)}")

    properties = []
    for row in rows:
        property_value = str(row.get("Property", "")).strip()
        if not property_value.isdigit():
            raise ValueError(f"Non-numeric Property value found: {property_value!r}")
        properties.append(int(property_value))

    if properties != list(range(1, len(rows) + 1)):
        raise ValueError("Property column is not sequential starting at 1.")


def build_finding_row(row):
    repo_path = normalize_text(row.get("repo_path", ""))
    severity_raw = normalize_text(row.get("severity", ""))
    tag_raw = normalize_text(row.get("tag", ""))
    subtag_raw = normalize_text(row.get("subtag", ""))
    description = normalize_text(row.get("description", ""))

    return FindingRow(
        repo_path=repo_path,
        severity_raw=severity_raw,
        tag_raw=tag_raw,
        subtag_raw=subtag_raw,
        description=description,
        severities=frozenset(split_labels(row.get("severity", ""))),
        tags=frozenset(split_labels(row.get("tag", ""))),
        subtags=frozenset(split_labels(row.get("subtag", ""))),
        unique_key=(repo_path, severity_raw, tag_raw, subtag_raw, description),
    )


def normalize_rows(rows, pad_token, truth_repo_ids=None, dedupe=False):
    normalized_rows = []
    duplicate_rows_removed = 0
    ignored_rows_outside_truth = 0
    seen_keys = set()

    for row in rows:
        if is_padding_row(row, pad_token):
            continue

        finding = build_finding_row(row)
        if not finding.repo_path:
            continue

        if truth_repo_ids is not None and finding.repo_path not in truth_repo_ids:
            ignored_rows_outside_truth += 1
            continue

        if dedupe:
            if finding.unique_key in seen_keys:
                duplicate_rows_removed += 1
                continue
            seen_keys.add(finding.unique_key)

        normalized_rows.append(finding)

    rows_by_repo = defaultdict(list)
    for finding in normalized_rows:
        rows_by_repo[finding.repo_path].append(finding)

    return {
        "rows": normalized_rows,
        "rows_by_repo": rows_by_repo,
        "duplicate_rows_removed": duplicate_rows_removed,
        "ignored_rows_outside_truth": ignored_rows_outside_truth,
    }


def field_score(predicted_labels, truth_labels):
    truth_set = set(truth_labels)
    predicted_set = set(predicted_labels)
    truth_count = len(truth_set)
    if truth_count == 0:
        return {"score": 0.0, "tp": 0, "fp": len(predicted_set), "n": 0}

    true_positives = len(predicted_set & truth_set)
    false_positives = len(predicted_set - truth_set)
    score = max(0.0, (true_positives - 0.5 * false_positives) / truth_count)
    return {"score": score, "tp": true_positives, "fp": false_positives, "n": truth_count}

class DescriptionScorer:
    def __init__(self, requested_mode, threshold, model_name):
        self.requested_mode = requested_mode
        self.threshold = threshold
        self.model_name = model_name
        self.used_mode = None
        self.note = ""
        self._model = None
        self._embedding_cache = {}
        self._init_backend()

    def _init_backend(self):
        if self.requested_mode == "lexical":
            self.used_mode = "lexical"
            self.note = "Using lexical cosine fallback because lexical mode was requested explicitly."
            return

        try:
            from sentence_transformers import SentenceTransformer
        except Exception as exc:
            if self.requested_mode == "bge":
                raise RuntimeError(
                    "BGE description scoring was requested explicitly, but sentence-transformers is unavailable."
                ) from exc
            self.used_mode = "lexical"
            self.note = (
                "Using lexical cosine fallback because sentence-transformers is unavailable in the local "
                f"environment: {exc}"
            )
            return

        try:
            self._model = SentenceTransformer(self.model_name, local_files_only=True)
            self.used_mode = "bge"
            self.note = f"Using cached sentence-transformers model {self.model_name} in offline mode."
        except Exception as exc:
            if self.requested_mode == "bge":
                raise RuntimeError(
                    f"BGE description scoring was requested explicitly, but model {self.model_name} could not be loaded."
                ) from exc
            self.used_mode = "lexical"
            self.note = (
                "Using lexical cosine fallback because the BGE model could not be loaded locally: "
                f"{exc}"
            )

    def score(self, left_text, right_text):
        if not left_text or not right_text:
            return {"raw_similarity": 0.0, "score": 0.0}

        if self.used_mode == "bge":
            similarity = self._bge_similarity(left_text, right_text)
        else:
            similarity = self._lexical_similarity(left_text, right_text)

        score = similarity if similarity > self.threshold else 0.0
        return {"raw_similarity": similarity, "score": score}

    def _bge_similarity(self, left_text, right_text):
        left_embedding = self._embedding_for(left_text)
        right_embedding = self._embedding_for(right_text)
        if not left_embedding or not right_embedding:
            return 0.0
        return sum(float(left) * float(right) for left, right in zip(left_embedding, right_embedding))

    def _embedding_for(self, text):
        cached = self._embedding_cache.get(text)
        if cached is not None:
            return cached
        embedding = self._model.encode(text, normalize_embeddings=True)
        if hasattr(embedding, "tolist"):
            embedding = embedding.tolist()
        self._embedding_cache[text] = embedding
        return embedding

    def _lexical_similarity(self, left_text, right_text):
        if left_text == right_text:
            return 1.0

        left_counts = Counter(tokenize_text(left_text))
        right_counts = Counter(tokenize_text(right_text))
        if not left_counts or not right_counts:
            return 0.0

        shared_tokens = set(left_counts) & set(right_counts)
        dot = sum(left_counts[token] * right_counts[token] for token in shared_tokens)
        left_norm = math.sqrt(sum(count * count for count in left_counts.values()))
        right_norm = math.sqrt(sum(count * count for count in right_counts.values()))
        if left_norm == 0.0 or right_norm == 0.0:
            return 0.0
        return dot / (left_norm * right_norm)


def score_pair(prediction, truth, repo_penalty, description_scorer):
    tag_component = field_score(prediction.tags, truth.tags)
    subtag_component = field_score(prediction.subtags, truth.subtags)
    severity_component = field_score(prediction.severities, truth.severities)
    description_component = description_scorer.score(prediction.description, truth.description)

    total_score = (
        tag_component["score"]
        + subtag_component["score"]
        + severity_component["score"]
        + description_component["score"]
        - repo_penalty
    )

    return {
        "tag_score": tag_component["score"],
        "subtag_score": subtag_component["score"],
        "severity_score": severity_component["score"],
        "description_score": description_component["score"],
        "description_similarity": description_component["raw_similarity"],
        "penalty": repo_penalty,
        "total_score": total_score,
    }


def evaluate_repository(repo_id, prediction_rows, truth_rows, description_scorer):
    repo_penalty = max(0, len(prediction_rows) - len(truth_rows))
    unmatched_prediction_indices = set(range(len(prediction_rows)))
    unmatched_truth_indices = set(range(len(truth_rows)))
    pair_cache = {}
    matches = []

    while unmatched_prediction_indices and unmatched_truth_indices:
        best_prediction_index = None
        best_truth_index = None
        best_pair = None

        for prediction_index in unmatched_prediction_indices:
            prediction = prediction_rows[prediction_index]
            for truth_index in unmatched_truth_indices:
                cache_key = (prediction_index, truth_index)
                pair = pair_cache.get(cache_key)
                if pair is None:
                    pair = score_pair(prediction, truth_rows[truth_index], repo_penalty, description_scorer)
                    pair_cache[cache_key] = pair
                if best_pair is None or pair["total_score"] > best_pair["total_score"]:
                    best_pair = pair
                    best_prediction_index = prediction_index
                    best_truth_index = truth_index

        if best_pair is None or best_pair["total_score"] <= 0.0:
            break

        unmatched_prediction_indices.remove(best_prediction_index)
        unmatched_truth_indices.remove(best_truth_index)
        prediction = prediction_rows[best_prediction_index]
        truth = truth_rows[best_truth_index]
        matches.append(
            {
                "prediction_index": best_prediction_index,
                "truth_index": best_truth_index,
                "prediction": {
                    "repo_path": prediction.repo_path,
                    "severity": prediction.severity_raw,
                    "tag": prediction.tag_raw,
                    "subtag": prediction.subtag_raw,
                    "description": prediction.description,
                },
                "truth": {
                    "repo_path": truth.repo_path,
                    "severity": truth.severity_raw,
                    "tag": truth.tag_raw,
                    "subtag": truth.subtag_raw,
                    "description": truth.description,
                },
                **best_pair,
            }
        )

    repo_score = sum(match["total_score"] for match in matches)
    component_totals = {
        "tag_score": sum(match["tag_score"] for match in matches),
        "subtag_score": sum(match["subtag_score"] for match in matches),
        "severity_score": sum(match["severity_score"] for match in matches),
        "description_score": sum(match["description_score"] for match in matches),
        "penalty_applied_per_pair": repo_penalty,
    }

    return {
        "repo_path": repo_id,
        "prediction_row_count": len(prediction_rows),
        "truth_row_count": len(truth_rows),
        "over_reporting_penalty": repo_penalty,
        "matched_pair_count": len(matches),
        "unmatched_prediction_count": len(unmatched_prediction_indices),
        "unmatched_truth_count": len(unmatched_truth_indices),
        "repo_score": repo_score,
        "component_totals": component_totals,
        "matches": matches,
    }


def evaluate_structured_score(prediction_rows, truth_rows, description_scorer):
    truth_repo_ids = sorted({row.repo_path for row in truth_rows})
    truth_rows_by_repo = defaultdict(list)
    prediction_rows_by_repo = defaultdict(list)

    for row in truth_rows:
        truth_rows_by_repo[row.repo_path].append(row)
    for row in prediction_rows:
        prediction_rows_by_repo[row.repo_path].append(row)

    repo_results = []
    final_score = 0.0
    matched_pair_count = 0
    component_totals = {
        "tag_score": 0.0,
        "subtag_score": 0.0,
        "severity_score": 0.0,
        "description_score": 0.0,
    }

    for repo_id in truth_repo_ids:
        repo_result = evaluate_repository(
            repo_id,
            prediction_rows_by_repo.get(repo_id, []),
            truth_rows_by_repo[repo_id],
            description_scorer,
        )
        repo_results.append(repo_result)
        final_score += repo_result["repo_score"]
        matched_pair_count += repo_result["matched_pair_count"]
        component_totals["tag_score"] += repo_result["component_totals"]["tag_score"]
        component_totals["subtag_score"] += repo_result["component_totals"]["subtag_score"]
        component_totals["severity_score"] += repo_result["component_totals"]["severity_score"]
        component_totals["description_score"] += repo_result["component_totals"]["description_score"]

    truth_row_count = len(truth_rows)
    prediction_row_count = len(prediction_rows)
    score_per_truth_row = final_score / truth_row_count if truth_row_count else 0.0

    repo_results.sort(key=lambda item: (-item["repo_score"], item["repo_path"]))

    return {
        "final_score": final_score,
        "score_per_truth_row": score_per_truth_row,
        "prediction_row_count": prediction_row_count,
        "truth_row_count": truth_row_count,
        "matched_pair_count": matched_pair_count,
        "component_totals": component_totals,
        "repo_results": repo_results,
    }

def extract_proxy_signature_sets(rows):
    strict_signatures = set()
    family_signatures = set()
    strict_by_tag = defaultdict(set)
    family_by_tag = defaultdict(set)
    raw_rows_by_repo = defaultdict(int)

    for finding in rows:
        raw_rows_by_repo[finding.repo_path] += 1
        for tag in finding.tags:
            strict_key = (finding.repo_path, finding.severity_raw, tag)
            family_key = (finding.repo_path, tag)
            strict_signatures.add(strict_key)
            family_signatures.add(family_key)
            strict_by_tag[tag].add(strict_key)
            family_by_tag[tag].add(family_key)

    return {
        "strict": strict_signatures,
        "family": family_signatures,
        "strict_by_tag": strict_by_tag,
        "family_by_tag": family_by_tag,
        "raw_rows_by_repo": dict(raw_rows_by_repo),
    }


def prf(predicted_set, truth_set):
    matched = predicted_set & truth_set
    predicted_count = len(predicted_set)
    truth_count = len(truth_set)
    matched_count = len(matched)
    precision = matched_count / predicted_count if predicted_count else 0.0
    recall = matched_count / truth_count if truth_count else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision and recall else 0.0
    return {
        "predicted_count": predicted_count,
        "truth_count": truth_count,
        "matched_count": matched_count,
        "precision": precision,
        "recall": recall,
        "f1": f1,
    }


def build_proxy_category_breakdown(predicted_signatures, truth_signatures):
    tags = sorted(set(predicted_signatures) | set(truth_signatures))
    breakdown = []
    for tag in tags:
        metrics = prf(predicted_signatures.get(tag, set()), truth_signatures.get(tag, set()))
        metrics["tag"] = tag
        breakdown.append(metrics)
    breakdown.sort(key=lambda item: (-item["truth_count"], item["tag"]))
    return breakdown


def build_reference_comparison(metrics, args):
    if not args.reference_report:
        return None

    with open(args.reference_report, encoding="utf-8") as handle:
        reference_report = json.load(handle)

    reference_metrics = reference_report.get("metrics", {})
    current_structured_score = metrics["structured"]["final_score"]
    reference_structured_score = reference_metrics.get("structured", {}).get("final_score", 0.0)
    structured_delta = current_structured_score - reference_structured_score

    current_score_per_truth = metrics["structured"]["score_per_truth_row"]
    reference_score_per_truth = reference_metrics.get("structured", {}).get("score_per_truth_row", 0.0)
    score_per_truth_delta = current_score_per_truth - reference_score_per_truth

    current_proxy_strict_f1 = metrics["proxy_strict"]["f1"]
    current_proxy_family_f1 = metrics["proxy_family"]["f1"]
    reference_proxy_strict_f1 = reference_metrics.get("proxy_strict", {}).get("f1", 0.0)
    reference_proxy_family_f1 = reference_metrics.get("proxy_family", {}).get("f1", 0.0)

    passes_gate = structured_delta > args.structured_improvement_min

    return {
        "reference_report": str(Path(args.reference_report).resolve()),
        "reference_structured_score": reference_structured_score,
        "reference_score_per_truth_row": reference_score_per_truth,
        "structured_delta": structured_delta,
        "score_per_truth_delta": score_per_truth_delta,
        "reference_proxy_strict_f1": reference_proxy_strict_f1,
        "reference_proxy_family_f1": reference_proxy_family_f1,
        "proxy_strict_f1_delta": current_proxy_strict_f1 - reference_proxy_strict_f1,
        "proxy_family_f1_delta": current_proxy_family_f1 - reference_proxy_family_f1,
        "structured_improvement_min": args.structured_improvement_min,
        "passes_submission_gate": passes_gate,
    }


def parse_extra_args(extra_args):
    if not extra_args.strip():
        return []
    return shlex.split(extra_args, posix=False)


def build_generator_command(args, split_paths):
    extra_args = parse_extra_args(args.generator_extra_args)
    test_repo_root = args.validation_repo_root or args.train_repo_root

    if args.generator == "baseline":
        command = [
            sys.executable,
            "src/baseline.py",
            "--train-csv",
            str(split_paths["split_train_csv"]),
            "--test-csv",
            str(split_paths["holdout_test_csv"]),
            "--sample-submission",
            str(split_paths["sample_submission"]),
            "--output",
            str(split_paths["prediction_csv"]),
            "--target-rows",
            str(args.target_rows),
        ]
        if test_repo_root:
            command.extend(["--test-repo-root", str(Path(test_repo_root).resolve())])
        return command + extra_args

    if args.generator == "baseline_v2":
        command = [
            sys.executable,
            "src/baseline_v2.py",
            "--train-csv",
            str(split_paths["split_train_csv"]),
            "--test-csv",
            str(split_paths["holdout_test_csv"]),
            "--sample-submission",
            str(split_paths["sample_submission"]),
            "--output",
            str(split_paths["prediction_csv"]),
            "--target-rows",
            str(args.target_rows),
        ]
        if args.train_repo_root:
            command.extend(["--train-repo-root", str(Path(args.train_repo_root).resolve())])
        if test_repo_root:
            command.extend(["--test-repo-root", str(Path(test_repo_root).resolve())])
        return command + extra_args

    if not args.generator_command.strip():
        raise ValueError("--generator-command is required when --generator custom.")

    template = args.generator_command.format(
        train_csv=str(split_paths["split_train_csv"]),
        test_csv=str(split_paths["holdout_test_csv"]),
        sample_submission=str(split_paths["sample_submission"]),
        output=str(split_paths["prediction_csv"]),
        train_repo_root=str(Path(args.train_repo_root).resolve()) if args.train_repo_root else "",
        test_repo_root=str(Path(test_repo_root).resolve()) if test_repo_root else "",
        target_rows=args.target_rows,
    )
    return shlex.split(template, posix=False) + extra_args


def run_generator(command, workdir):
    completed = subprocess.run(
        command,
        cwd=workdir,
        text=True,
        capture_output=True,
        check=False,
    )
    return {
        "command": command,
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def format_proxy_metric_line(label, metric):
    return (
        f"{label}: P={metric['precision']:.4f}, R={metric['recall']:.4f}, "
        f"F1={metric['f1']:.4f} "
        f"(matched={metric['matched_count']}, predicted={metric['predicted_count']}, truth={metric['truth_count']})"
    )


def format_structured_metric_line(metric):
    return (
        f"Structured score={metric['final_score']:.4f} "
        f"(score_per_truth_row={metric['score_per_truth_row']:.4f}, matched_pairs={metric['matched_pair_count']}, "
        f"predicted_rows={metric['prediction_row_count']}, truth_rows={metric['truth_row_count']})"
    )


def write_summary_text(path, report):
    metrics = report["metrics"]
    split_info = report["split"]
    generator = report["generator"]
    prediction_cleanup = report["prediction_cleanup"]
    description_backend = report["description_backend"]

    lines = [
        "Bastet Validation Standard",
        "",
        f"Run name: {report['run_name']}",
        f"Generator: {generator['generator_name']}",
        f"Seed: {split_info['seed']}",
        f"Holdout fraction: {split_info['holdout_fraction']:.2f}",
        f"Train repos: {split_info['train_repo_count']}",
        f"Holdout repos: {split_info['holdout_repo_count']}",
        f"Description scorer requested: {description_backend['requested_mode']}",
        f"Description scorer used: {description_backend['used_mode']}",
        f"Description threshold: {description_backend['threshold']:.2f}",
        f"Description note: {description_backend['note']}",
        "",
        f"Raw non-padding prediction rows: {prediction_cleanup['raw_non_padding_prediction_rows']}",
        f"Duplicate prediction rows removed: {prediction_cleanup['duplicate_prediction_rows_removed']}",
        f"Prediction rows ignored outside holdout repos: {prediction_cleanup['ignored_prediction_rows_outside_truth']}",
        f"Scored prediction rows: {prediction_cleanup['scored_prediction_rows']}",
        f"Truth rows: {metrics['structured']['truth_row_count']}",
        format_structured_metric_line(metrics["structured"]),
        format_proxy_metric_line("Proxy strict repo+severity+tag", metrics["proxy_strict"]),
        format_proxy_metric_line("Proxy family repo+tag", metrics["proxy_family"]),
        "",
        "Top repository scores:",
    ]

    for item in report["repo_breakdown"][:8]:
        lines.append(
            f"- {item['repo_path']}: score={item['repo_score']:.4f}, matched_pairs={item['matched_pair_count']}, "
            f"penalty={item['over_reporting_penalty']}, predicted={item['prediction_row_count']}, truth={item['truth_row_count']}"
        )

    lines.extend(["", "Top proxy strict category breakdown:"])
    for item in report["proxy_category_breakdown"][:8]:
        lines.append(
            f"- {item['tag']}: strict_f1={item['f1']:.4f} "
            f"(matched={item['matched_count']}, predicted={item['predicted_count']}, truth={item['truth_count']})"
        )

    if report.get("reference_comparison"):
        comparison = report["reference_comparison"]
        lines.extend(
            [
                "",
                "Reference comparison:",
                f"- Structured score delta: {comparison['structured_delta']:+.4f}",
                f"- Score-per-truth delta: {comparison['score_per_truth_delta']:+.4f}",
                f"- Proxy strict F1 delta: {comparison['proxy_strict_f1_delta']:+.4f}",
                f"- Proxy family F1 delta: {comparison['proxy_family_f1_delta']:+.4f}",
                f"- Passes submission gate: {comparison['passes_submission_gate']}",
            ]
        )

    if generator["stdout"].strip():
        lines.extend(["", "Generator stdout:", generator["stdout"].rstrip()])
    if generator["stderr"].strip():
        lines.extend(["", "Generator stderr:", generator["stderr"].rstrip()])

    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")

def main():
    args = parse_args()
    if not 0 < args.holdout_fraction < 1:
        raise ValueError("--holdout-fraction must be between 0 and 1.")

    train_csv_path = Path(args.train_csv).resolve()
    sample_submission_path = Path(args.sample_submission).resolve()
    artifacts_root = Path(args.artifacts_dir).resolve()

    run_suffix = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_name = args.run_name.strip() or (
        f"{args.generator}_holdout{int(args.holdout_fraction * 100)}_seed{args.seed}_{run_suffix}"
    )
    run_dir = artifacts_root / run_name
    split_dir = run_dir / "split"
    output_dir = run_dir / "outputs"
    split_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    train_rows = load_csv_rows(train_csv_path)
    sample_rows = load_csv_rows(sample_submission_path)
    split = split_train_holdout(train_rows, args.holdout_fraction, args.seed)

    split_train_csv = split_dir / "train_split.csv"
    holdout_truth_csv = split_dir / "holdout_truth.csv"
    holdout_test_csv = split_dir / "holdout_test.csv"
    prediction_csv = output_dir / "holdout_predictions.csv"
    report_json = output_dir / "holdout_evaluation_report.json"
    summary_txt = output_dir / "holdout_evaluation_summary.txt"

    write_csv_rows(split_train_csv, split["split_train_rows"], fieldnames=list(train_rows[0].keys()))
    write_csv_rows(holdout_truth_csv, split["holdout_truth_rows"], fieldnames=list(train_rows[0].keys()))
    write_csv_rows(holdout_test_csv, split["holdout_test_rows"], fieldnames=["repo_path"])

    generator_result = run_generator(
        build_generator_command(
            args,
            {
                "split_train_csv": split_train_csv,
                "holdout_test_csv": holdout_test_csv,
                "sample_submission": sample_submission_path,
                "prediction_csv": prediction_csv,
            },
        ),
        workdir=str(Path.cwd()),
    )

    if generator_result["returncode"] != 0:
        raise RuntimeError(
            "Generator command failed.\n"
            f"Command: {' '.join(generator_result['command'])}\n"
            f"Stdout:\n{generator_result['stdout']}\n"
            f"Stderr:\n{generator_result['stderr']}"
        )

    prediction_rows = load_csv_rows(prediction_csv)
    validate_prediction_format(prediction_rows, sample_rows, args.target_rows)

    truth_repo_ids = set(split["holdout_repo_ids"])
    normalized_truth = normalize_rows(split["holdout_truth_rows"], args.pad_token, truth_repo_ids=None, dedupe=False)
    normalized_predictions = normalize_rows(
        prediction_rows,
        args.pad_token,
        truth_repo_ids=truth_repo_ids,
        dedupe=True,
    )

    description_scorer = DescriptionScorer(
        requested_mode=args.description_scorer,
        threshold=args.description_threshold,
        model_name=args.bge_model_name,
    )

    structured_metrics = evaluate_structured_score(
        normalized_predictions["rows"],
        normalized_truth["rows"],
        description_scorer,
    )

    proxy_prediction_sets = extract_proxy_signature_sets(normalized_predictions["rows"])
    proxy_truth_sets = extract_proxy_signature_sets(normalized_truth["rows"])
    proxy_strict_metrics = prf(proxy_prediction_sets["strict"], proxy_truth_sets["strict"])
    proxy_family_metrics = prf(proxy_prediction_sets["family"], proxy_truth_sets["family"])
    proxy_category_breakdown = build_proxy_category_breakdown(
        proxy_prediction_sets["strict_by_tag"],
        proxy_truth_sets["strict_by_tag"],
    )

    metrics = {
        "structured": structured_metrics,
        "proxy_strict": proxy_strict_metrics,
        "proxy_family": proxy_family_metrics,
    }
    reference_comparison = build_reference_comparison(metrics, args)

    report = {
        "run_name": run_name,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "paths": {
            "run_dir": str(run_dir),
            "train_split_csv": str(split_train_csv),
            "holdout_truth_csv": str(holdout_truth_csv),
            "holdout_test_csv": str(holdout_test_csv),
            "prediction_csv": str(prediction_csv),
            "report_json": str(report_json),
            "summary_txt": str(summary_txt),
        },
        "split": {
            "seed": args.seed,
            "holdout_fraction": args.holdout_fraction,
            "all_repo_count": len(split["all_repo_ids"]),
            "train_repo_count": len(split["train_repo_ids"]),
            "holdout_repo_count": len(split["holdout_repo_ids"]),
            "train_repo_ids": split["train_repo_ids"],
            "holdout_repo_ids": split["holdout_repo_ids"],
        },
        "prediction_cleanup": {
            "raw_non_padding_prediction_rows": sum(1 for row in prediction_rows if not is_padding_row(row, args.pad_token)),
            "duplicate_prediction_rows_removed": normalized_predictions["duplicate_rows_removed"],
            "ignored_prediction_rows_outside_truth": normalized_predictions["ignored_rows_outside_truth"],
            "scored_prediction_rows": len(normalized_predictions["rows"]),
        },
        "description_backend": {
            "requested_mode": args.description_scorer,
            "used_mode": description_scorer.used_mode,
            "model_name": args.bge_model_name,
            "threshold": args.description_threshold,
            "note": description_scorer.note,
        },
        "metrics": metrics,
        "proxy_category_breakdown": proxy_category_breakdown,
        "repo_breakdown": structured_metrics["repo_results"],
        "generator": {
            "generator_name": args.generator,
            "command": generator_result["command"],
            "stdout": generator_result["stdout"],
            "stderr": generator_result["stderr"],
        },
        "reference_comparison": reference_comparison,
    }

    report_json.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    write_summary_text(summary_txt, report)

    print("Validation standard run completed successfully.")
    print(f"Run directory: {run_dir}")
    print(format_structured_metric_line(structured_metrics))
    print(format_proxy_metric_line("Proxy strict repo+severity+tag", proxy_strict_metrics))
    print(format_proxy_metric_line("Proxy family repo+tag", proxy_family_metrics))
    print(f"Description scorer used: {description_scorer.used_mode}")
    if reference_comparison:
        print(
            "Submission gate: "
            f"{'PASS' if reference_comparison['passes_submission_gate'] else 'FAIL'} "
            f"(structured_delta={reference_comparison['structured_delta']:+.4f}, "
            f"score_per_truth_delta={reference_comparison['score_per_truth_delta']:+.4f})"
        )
    print(f"Summary: {summary_txt}")
    print(f"Report: {report_json}")


if __name__ == "__main__":
    main()

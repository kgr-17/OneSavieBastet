"""Validate report-derived prediction strategies on a real 20% train split.

Unlike the v11 proxy scorer, this uses actual `train.csv` truth. For each
held-out repo, it rebuilds predictions from the canonical report markdown and
labels them with variants trained from the remaining 80%.

This is the benchmark for a different framework: "report first, label second."
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.run_validation_standard import (  # noqa: E402
    DescriptionScorer,
    build_finding_row,
    evaluate_structured_score,
)

try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
except Exception as exc:  # pragma: no cover
    raise SystemExit(f"scikit-learn is required for this benchmark: {exc}")


TRAIN = ROOT / "train.csv"
DATASET_0831 = ROOT / "data" / "dataset_0831.csv"
REPORTS = ROOT / "data" / "dataset_v0" / "reports"
TRAIN_MAPS = [
    ROOT / "artifacts" / "train_hash_to_contest_v3.json",
    ROOT / "artifacts" / "train_hash_to_contest_verified.json",
    ROOT / "artifacts" / "hash_to_contest.json",
]
OUT_DIR = ROOT / "artifacts" / "deep_research" / "report_labeler_train20"


@dataclass
class ReportFinding:
    audit: str
    detail: str
    severity: str
    title: str
    body: str
    impact: str

    def text(self) -> str:
        return f"{self.title}. {self.impact or self.body}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Benchmark report-derived labelers on a 20% train split.")
    parser.add_argument("--seeds", nargs="*", type=int, default=[1337, 2024, 7, 42, 99])
    parser.add_argument("--holdout-frac", type=float, default=0.2)
    parser.add_argument("--scorer", choices=["bge", "lexical"], default="bge")
    parser.add_argument("--description-threshold", type=float, default=0.7)
    parser.add_argument("--bge-model-name", default="BAAI/bge-large-en-v1.5")
    parser.add_argument("--max-per-repo", type=int, default=80)
    return parser.parse_args()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def normalize(value: str) -> str:
    value = str(value or "").lower()
    value = re.sub(r"https?://\S+", " ", value)
    value = re.sub(r"`([^`]*)`", r"\1", value)
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(value.split())


def load_hash_map() -> dict[str, str]:
    out = {}
    for path in TRAIN_MAPS:
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        for repo_hash, item in data.items():
            contest = item.get("contest") if isinstance(item, dict) else item
            if contest:
                out.setdefault(repo_hash, contest)
    return out


def split_repos(rows: list[dict[str, str]], frac: float, seed: int) -> tuple[set[str], set[str]]:
    repos = sorted({row["repo_path"] for row in rows})
    rng = random.Random(seed)
    shuffled = list(repos)
    rng.shuffle(shuffled)
    holdout_n = max(1, min(len(repos) - 1, round(len(repos) * frac)))
    holdout = set(shuffled[:holdout_n])
    train = set(shuffled[holdout_n:])
    return train, holdout


def title_from_heading(line: str) -> str:
    title = line.strip()
    title = re.sub(r"^#+\s*", "", title)
    title = re.sub(r"^\[+\s*[HML]-?\d+\]?\s*", "", title, flags=re.I)
    title = re.sub(r"\]\(https?://[^)]+\)", "", title)
    title = title.replace("[", "").replace("]", "")
    return title.strip(" `")


def strip_markdown(text: str) -> str:
    text = re.sub(r"```[\s\S]*?```", " ", text)
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def first_body(md_text: str, limit: int = 360) -> str:
    lines = []
    for line in md_text.splitlines()[1:]:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#") or stripped.startswith("*Submitted"):
            continue
        lowered = stripped.lower()
        if lowered.startswith(("tools used", "recommended mitigation")):
            break
        clean = strip_markdown(stripped)
        if len(clean) > 30:
            lines.append(clean)
        if sum(len(item) for item in lines) >= limit:
            break
    return strip_markdown(" ".join(lines))[:limit]


def impact_body(md_text: str, limit: int = 360) -> str:
    lines = md_text.splitlines()
    capture = False
    out = []
    for line in lines:
        stripped = line.strip()
        if re.match(r"^#+\s*impact\b", stripped, re.I):
            capture = True
            continue
        if capture and stripped.startswith("#"):
            break
        if capture and stripped:
            clean = strip_markdown(stripped)
            if len(clean) > 20:
                out.append(clean)
            if sum(len(item) for item in out) >= limit:
                break
    return strip_markdown(" ".join(out))[:limit]


def parse_report_dir(audit: str) -> list[ReportFinding]:
    report_dir = REPORTS / audit
    if not report_dir.is_dir():
        return []
    findings = []
    for path in sorted(report_dir.glob("*.md")):
        stem = path.stem.lower()
        if not (stem.startswith("h_") or stem.startswith("m_")):
            continue
        severity = "High" if stem.startswith("h_") else "Medium"
        text = path.read_text(encoding="utf-8", errors="replace")
        title = title_from_heading(text.splitlines()[0] if text.splitlines() else path.stem)
        findings.append(
            ReportFinding(
                audit=audit,
                detail=f"reports/{audit}/{path.name}",
                severity=severity,
                title=title,
                body=first_body(text),
                impact=impact_body(text),
            )
        )
    return findings


def audit_of_dataset_path(repo_path: str) -> str:
    for segment in str(repo_path).replace("\\", "/").split("/"):
        if len(segment) >= 7 and segment[:2] == "20" and "-" in segment:
            return segment
    return ""


def load_dataset_done_examples(exclude_audits: set[str]) -> list[dict[str, str]]:
    examples = []
    if not DATASET_0831.exists():
        return examples
    for row in read_csv(DATASET_0831):
        audit = audit_of_dataset_path(row.get("repo_path", ""))
        if audit in exclude_audits:
            continue
        tag = row.get("tag", "").strip()
        subtag = row.get("subtag", "").strip()
        if not tag or not subtag:
            continue
        detail = row.get("detail", "").strip()
        title, body = "", ""
        if detail:
            path = ROOT / "data" / "dataset_v0" / detail
            if path.exists() and path.is_file():
                md = path.read_text(encoding="utf-8", errors="replace")
                title = title_from_heading(md.splitlines()[0] if md.splitlines() else "")
                body = first_body(md)
        text = f"{title}. {body}".strip()
        if len(normalize(text)) < 6:
            text = row.get("description", "")
        examples.append(
            {
                "severity": row.get("severity", "").strip(),
                "tag": tag,
                "subtag": subtag,
                "description": row.get("description", "").strip(),
                "text": text,
                "source": f"dataset:{audit}",
            }
        )
    return examples


def examples_from_train(rows: list[dict[str, str]], train_repos: set[str]) -> list[dict[str, str]]:
    examples = []
    for row in rows:
        if row["repo_path"] not in train_repos:
            continue
        examples.append(
            {
                "severity": row.get("severity", "").strip(),
                "tag": row.get("tag", "").strip(),
                "subtag": row.get("subtag", "").strip(),
                "description": row.get("description", "").strip(),
                "text": row.get("description", "").strip(),
                "source": "train",
            }
        )
    return examples


def heuristic_label(text: str) -> tuple[str, str]:
    hay = normalize(text)
    rules = [
        (r"\breentr|nonreentrant|cei\b", "Reentrancy", "Violating CEI / Missing nonReentrant"),
        (r"fee on transfer|fee transfer|tax token", "ERC20", "Fee On Transfer Token"),
        (r"erc4626|maxwithdraw|maxredeem|first depositor|inflation|share.*zero", "ERC4626", "Inflation Attack"),
        (r"chainlink.*deprecated|latestanswer", "Chainlink", "Deprecated Library"),
        (r"stale.*oracle|oracle.*stale|roundid|updatedat", "Chainlink", "Stale Value"),
        (r"twap|twav|time weighted", "TWAP", "Price Manipulation / Arbitrage opportunity"),
        (r"slippage|minout|maxamount|sandwich|deadline", "Slippage", "Invalid  Slippage Control / Missing slippage check"),
        (r"front run|frontrun|front running", "MEV", "Front Run"),
        (r"liquidat|bad debt|collateral", "Liquidation", "Bad Condition"),
        (r"pause|paused", "Pause", "State Update Inconsistency"),
        (r"owner|admin|onlyowner|permission|access control|role|privilege", "Access Control", "Centralization Risk"),
        (r"overflow|underflow", "Arithmetic", "Overflow / Underflow"),
        (r"precision|rounding|division before multiplication|decimal|scaling", "Arithmetic", "Precision Loss"),
        (r"out of gas|unbounded loop|gas limit", "DoS", "Out of Gas"),
        (r"dos|denial of service|revert|cannot withdraw|locked|lock funds", "DoS", "Bad Condition"),
        (r"unchecked return|return value|approve|transferfrom|transfer\(", "ERC20", "Missing Return Check"),
        (r"oracle|price feed|price manipulation", "Oracle", "Price Manipulation / Arbitrage opportunity"),
        (r"governance|vote|delegate|proposal", "Governance", "Bad Condition"),
        (r"signature|eip712|permit|nonce", "EIP712", "Nonce"),
        (r"bridge|cross chain|l1|l2", "Cross-Chain", "State Update Inconsistency"),
    ]
    for pattern, tag, subtag in rules:
        if re.search(pattern, hay):
            return tag, subtag
    return "Logic error", "Implementation Error"


class NearestLabeler:
    def __init__(self, examples: list[dict[str, str]], k: int = 1):
        self.examples = [ex for ex in examples if normalize(ex.get("text", ""))]
        self.k = k
        self.vectorizer = None
        self.matrix = None
        if self.examples:
            self.vectorizer = TfidfVectorizer(ngram_range=(1, 2), min_df=1, max_df=0.95)
            self.matrix = self.vectorizer.fit_transform(normalize(ex["text"]) for ex in self.examples)

    def predict(self, text: str) -> tuple[str, str, float, str]:
        if not self.examples or self.vectorizer is None or self.matrix is None:
            tag, subtag = heuristic_label(text)
            return tag, subtag, 0.0, "heuristic"
        vec = self.vectorizer.transform([normalize(text)])
        sims = cosine_similarity(vec, self.matrix)[0]
        order = sims.argsort()[::-1][: max(1, self.k)]
        if self.k <= 1:
            ex = self.examples[int(order[0])]
            return ex["tag"], ex["subtag"], float(sims[int(order[0])]), ex["source"]

        tag_votes = Counter()
        subtag_votes = Counter()
        best = self.examples[int(order[0])]
        for idx in order:
            ex = self.examples[int(idx)]
            weight = float(sims[int(idx)]) + 0.0001
            tag_votes[ex["tag"]] += weight
            subtag_votes[ex["subtag"]] += weight
        return tag_votes.most_common(1)[0][0], subtag_votes.most_common(1)[0][0], float(sims[int(order[0])]), best["source"]


def desc_for(finding: ReportFinding, mode: str) -> str:
    if mode == "title":
        return finding.title[:420]
    if mode == "impact":
        return f"{finding.title}. {finding.impact or finding.body}"[:420]
    if mode == "body":
        return f"{finding.title}. {finding.body}"[:420]
    raise ValueError(f"unknown desc mode {mode}")


def predict_rows_for_holdout(
    holdout_repos: set[str],
    hash_map: dict[str, str],
    labeler: NearestLabeler,
    mode: str,
    max_per_repo: int,
) -> tuple[list[dict[str, str]], dict[str, int]]:
    label_mode, desc_mode = mode.split("+", 1)
    rows = []
    missing_reports = {}
    for repo_hash in sorted(holdout_repos):
        audit = hash_map.get(repo_hash)
        findings = parse_report_dir(audit) if audit else []
        if not findings:
            missing_reports[repo_hash] = 1
            continue
        # Canonical report order: High first then Medium, preserving finding number order.
        findings = sorted(findings, key=lambda f: (0 if f.severity == "High" else 1, f.detail))
        for finding in findings[:max_per_repo]:
            text = finding.text()
            if label_mode == "heuristic":
                tag, subtag = heuristic_label(text)
            elif label_mode == "nearest1":
                tag, subtag, _, _ = labeler.predict(text)
            elif label_mode == "nearest3":
                tag, subtag, _, _ = labeler.predict(text)
            elif label_mode == "hybrid":
                n_tag, n_subtag, sim, _ = labeler.predict(text)
                h_tag, h_subtag = heuristic_label(text)
                if sim >= 0.14:
                    tag, subtag = n_tag, n_subtag
                else:
                    tag, subtag = h_tag, h_subtag
            else:
                raise ValueError(f"unknown label mode {label_mode}")
            rows.append(
                {
                    "repo_path": repo_hash,
                    "severity": finding.severity,
                    "tag": tag,
                    "subtag": subtag,
                    "description": desc_for(finding, desc_mode),
                }
            )
    return rows, missing_reports


def to_findings(rows: Iterable[dict[str, str]]):
    return [build_finding_row(row) for row in rows]


def score_predictions(pred_rows, truth_rows, scorer):
    return evaluate_structured_score(to_findings(pred_rows), to_findings(truth_rows), scorer)


def make_scorer(args: argparse.Namespace) -> DescriptionScorer:
    requested = "bge" if args.scorer == "bge" else "lexical"
    try:
        return DescriptionScorer(
            requested_mode=requested,
            threshold=args.description_threshold,
            model_name=args.bge_model_name,
        )
    except RuntimeError as exc:
        print(f"WARNING: BGE unavailable, using lexical: {exc}", file=sys.stderr)
        return DescriptionScorer(
            requested_mode="lexical",
            threshold=args.description_threshold,
            model_name=args.bge_model_name,
        )


def main() -> None:
    args = parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    train_rows = read_csv(TRAIN)
    hash_map = load_hash_map()
    scorer = make_scorer(args)

    modes = [
        "heuristic+title",
        "heuristic+impact",
        "nearest1+title",
        "nearest1+impact",
        "nearest1+body",
        "nearest3+impact",
        "hybrid+impact",
        "hybrid+body",
    ]

    raw_results = []
    aggregate = defaultdict(list)
    details = {}

    for seed in args.seeds:
        train_repos, holdout_repos = split_repos(train_rows, args.holdout_frac, seed)
        holdout_truth = [row for row in train_rows if row["repo_path"] in holdout_repos]
        holdout_audits = {hash_map.get(repo) for repo in holdout_repos if hash_map.get(repo)}
        base_examples = examples_from_train(train_rows, train_repos)
        dataset_examples = load_dataset_done_examples(holdout_audits)
        examples = base_examples + dataset_examples

        labelers = {
            "nearest1": NearestLabeler(examples, k=1),
            "nearest3": NearestLabeler(examples, k=3),
            "hybrid": NearestLabeler(examples, k=1),
            "heuristic": NearestLabeler([], k=1),
        }

        # Baseline: use train-frequency label on all report findings, to give context.
        for mode in modes:
            label_mode = mode.split("+", 1)[0]
            pred_rows, missing = predict_rows_for_holdout(
                holdout_repos,
                hash_map,
                labelers[label_mode],
                mode,
                args.max_per_repo,
            )
            metrics = score_predictions(pred_rows, holdout_truth, scorer)
            row = {
                "seed": seed,
                "mode": mode,
                "score": metrics["final_score"],
                "score_per_truth": metrics["score_per_truth_row"],
                "matched_pairs": metrics["matched_pair_count"],
                "pred_rows": metrics["prediction_row_count"],
                "truth_rows": metrics["truth_row_count"],
                "holdout_repos": len(holdout_repos),
                "missing_report_repos": len(missing),
                "scorer": scorer.used_mode,
            }
            raw_results.append(row)
            aggregate[mode].append(row)
            details[(seed, mode)] = {
                "holdout_repos": sorted(holdout_repos),
                "missing_reports": missing,
                "repo_results": metrics["repo_results"],
            }

    ranking = []
    for mode, runs in aggregate.items():
        scores = [run["score"] for run in runs]
        spt = [run["score_per_truth"] for run in runs]
        mean_score = sum(scores) / len(scores)
        mean_spt = sum(spt) / len(spt)
        variance = sum((score - mean_score) ** 2 for score in scores) / max(1, len(scores) - 1)
        ranking.append(
            {
                "rank": 0,
                "mode": mode,
                "mean_score": mean_score,
                "mean_score_per_truth": mean_spt,
                "score_stdev": math.sqrt(variance),
                "best_score": max(scores),
                "worst_score": min(scores),
                "mean_matched_pairs": sum(run["matched_pairs"] for run in runs) / len(runs),
                "mean_pred_rows": sum(run["pred_rows"] for run in runs) / len(runs),
                "runs": len(runs),
            }
        )
    ranking.sort(key=lambda row: (-row["mean_score_per_truth"], -row["mean_score"], row["mode"]))
    for index, row in enumerate(ranking, 1):
        row["rank"] = index

    report = {
        "holdout_frac": args.holdout_frac,
        "seeds": args.seeds,
        "scorer": {
            "requested": args.scorer,
            "used": scorer.used_mode,
            "threshold": args.description_threshold,
            "note": scorer.note,
        },
        "ranking": ranking,
        "raw_results": raw_results,
    }
    (OUT_DIR / "report_labeler_train20_report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    write_csv(OUT_DIR / "report_labeler_train20_ranking.csv", ranking)
    write_csv(OUT_DIR / "report_labeler_train20_raw.csv", raw_results)

    lines = [
        "# Report Labeler 20% Train Validation",
        "",
        f"Holdout fraction: {args.holdout_frac:.2f}",
        f"Seeds: {', '.join(map(str, args.seeds))}",
        f"Scorer used: {scorer.used_mode}",
        "",
        "| Rank | Mode | Mean score | Mean score/truth | Stdev | Matched pairs | Pred rows |",
        "|---:|---|---:|---:|---:|---:|---:|",
    ]
    for row in ranking:
        lines.append(
            "| {rank} | `{mode}` | {mean_score:.6f} | {mean_score_per_truth:.6f} | {score_stdev:.6f} | {mean_matched_pairs:.2f} | {mean_pred_rows:.2f} |".format(
                **row
            )
        )
    (OUT_DIR / "report_labeler_train20_ranking.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    best = ranking[0]
    print("Report-labeler train20 benchmark complete.")
    print(f"Scorer used: {scorer.used_mode}")
    print(
        f"Best mode: {best['mode']} mean_score={best['mean_score']:.6f} "
        f"mean_score_per_truth={best['mean_score_per_truth']:.6f}"
    )
    print(f"Ranking: {OUT_DIR / 'report_labeler_train20_ranking.md'}")


if __name__ == "__main__":
    main()

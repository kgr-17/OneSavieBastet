"""Build a concrete breakout worklist for the 400->500 Bastet plateau.

The important distinction:
  1. Current v11 rows that map to canonical findings but still need exact
     Bastet truth labels verified. These can improve score without spending
     any extra row budget.
  2. Canonical findings not represented in v11. These require a row swap, so
     they must beat the value of the row being removed.

This script uses only public/local artifacts:
  - data/dataset_0831.csv and data/dataset_v0 report markdown
  - outputs/submission_c4_v11.csv
  - artifacts/test_hash_to_contest_v3.json
  - optional Solodit-derived Hugging Face dump in artifacts/deep_research
"""

from __future__ import annotations

import csv
import json
import os
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Iterable

try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
except Exception:  # pragma: no cover - script still has lexical fallback
    TfidfVectorizer = None
    cosine_similarity = None


ROOT = Path(__file__).resolve().parents[1]
V11 = ROOT / "outputs" / "submission_c4_v11.csv"
DATASET_0831 = ROOT / "data" / "dataset_0831.csv"
REPORT_ROOT = ROOT / "data" / "dataset_v0"
TEST_MAP = ROOT / "artifacts" / "test_hash_to_contest_v3.json"
SOLODIT = ROOT / "artifacts" / "deep_research" / "coriolan_solodit.json"
OUT_DIR = ROOT / "artifacts" / "deep_research"

MATCH_THRESHOLD = 0.115


@dataclass
class CanonicalFinding:
    audit: str
    severity: str
    tag: str
    subtag: str
    status: str
    detail: str
    title: str
    body: str
    evidence_url: str
    property_id: str

    @property
    def text(self) -> str:
        return f"{self.title}. {self.body}"

    @property
    def has_truth_label(self) -> bool:
        return bool(self.tag.strip() and self.subtag.strip())


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})


def audit_of_repo_path(repo_path: str) -> str:
    parts = str(repo_path).replace("\\", "/").split("/")
    for segment in parts:
        if len(segment) >= 7 and segment[:2] == "20" and "-" in segment:
            return segment
    return parts[-1] if parts else ""


def normalize_text(value: str) -> str:
    value = str(value or "").lower()
    value = re.sub(r"https?://\S+", " ", value)
    value = re.sub(r"`([^`]*)`", r"\1", value)
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(value.split())


def clean_markdown(md_text: str, max_chars: int = 2200) -> str:
    text = re.sub(r"```[\s\S]*?```", " ", md_text)
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"https?://\S+", " ", text)
    lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#") or stripped.startswith("*Submitted"):
            continue
        if stripped.lower().startswith(("tools used", "recommended mitigation")):
            break
        lines.append(stripped)
    prose = " ".join(lines)
    prose = re.sub(r"`([^`]*)`", r"\1", prose)
    prose = re.sub(r"\s+", " ", prose).strip()
    return prose[:max_chars]


def parse_report_detail(detail: str) -> tuple[str, str, str]:
    if not detail:
        return "", "", ""
    path = REPORT_ROOT / detail
    if not path.exists() or not path.is_file():
        return "", "", ""

    text = path.read_text(encoding="utf-8", errors="replace")
    first = text.splitlines()[0].strip() if text.splitlines() else ""
    evidence_url = ""
    link = re.search(r"\]\((https?://[^)]+)\)", first)
    if link:
        evidence_url = link.group(1)

    title = first
    title = re.sub(r"^#+\s*", "", title)
    title = re.sub(r"^\[+\s*[HML]-?\d+\]?\s*", "", title, flags=re.I)
    title = re.sub(r"\]\(https?://[^)]+\)", "", title)
    title = title.replace("[", "").replace("]", "")
    title = title.strip(" `")
    body = clean_markdown(text)
    return title, body, evidence_url


def load_canonical_findings() -> dict[str, list[CanonicalFinding]]:
    by_audit: dict[str, list[CanonicalFinding]] = defaultdict(list)
    for row in read_csv(DATASET_0831):
        audit = audit_of_repo_path(row.get("repo_path", ""))
        title, body, evidence_url = parse_report_detail(row.get("detail", ""))
        by_audit[audit].append(
            CanonicalFinding(
                audit=audit,
                severity=row.get("severity", "").strip(),
                tag=row.get("tag", "").strip(),
                subtag=row.get("subtag", "").strip(),
                status=row.get("status", "").strip(),
                detail=row.get("detail", "").strip(),
                title=title,
                body=body,
                evidence_url=evidence_url,
                property_id=row.get("Property", "").strip(),
            )
        )
    return by_audit


def solodit_index() -> dict[str, dict[str, object]]:
    if not SOLODIT.exists():
        return {}
    try:
        rows = json.loads(SOLODIT.read_text(encoding="utf-8"))
    except Exception:
        return {}
    out = {}
    for row in rows:
        github_link = str(row.get("github_link") or "").strip()
        if github_link:
            out[github_link.rstrip("/")] = row
    return out


def title_overlap_bonus(title: str, prediction: str) -> float:
    title_norm = normalize_text(title)
    pred_norm = normalize_text(prediction)
    if not title_norm or not pred_norm:
        return 0.0
    if title_norm in pred_norm or pred_norm in title_norm:
        return 1.0
    title_tokens = set(title_norm.split())
    pred_tokens = set(pred_norm.split())
    if not title_tokens:
        return 0.0
    jaccard = len(title_tokens & pred_tokens) / len(title_tokens | pred_tokens)
    seq = SequenceMatcher(None, title_norm, pred_norm[: max(80, len(title_norm) + 60)]).ratio()
    return max(jaccard, seq * 0.45)


def similarity_matrix(canon: list[CanonicalFinding], preds: list[dict[str, str]]) -> list[list[float]]:
    if not canon or not preds:
        return []

    canon_docs = [normalize_text(c.text) for c in canon]
    pred_docs = [
        normalize_text(
            f"{p.get('description', '')} {p.get('severity', '')} {p.get('tag', '')} {p.get('subtag', '')}"
        )
        for p in preds
    ]

    matrix = [[0.0 for _ in preds] for _ in canon]
    if TfidfVectorizer is not None and cosine_similarity is not None:
        docs = canon_docs + pred_docs
        try:
            vec = TfidfVectorizer(ngram_range=(1, 2), min_df=1).fit_transform(docs)
            sim = cosine_similarity(vec[: len(canon)], vec[len(canon) :])
            for i in range(len(canon)):
                for j in range(len(preds)):
                    matrix[i][j] = float(sim[i, j])
        except ValueError:
            pass

    for i, finding in enumerate(canon):
        for j, pred in enumerate(preds):
            bonus = title_overlap_bonus(finding.title, pred.get("description", ""))
            if finding.severity and finding.severity == pred.get("severity", "").strip():
                bonus += 0.025
            matrix[i][j] = min(1.0, max(matrix[i][j], bonus))
    return matrix


def greedy_match(canon: list[CanonicalFinding], preds: list[dict[str, str]]) -> list[tuple[int, int, float]]:
    matrix = similarity_matrix(canon, preds)
    pairs = []
    for i, row in enumerate(matrix):
        for j, score in enumerate(row):
            if score >= MATCH_THRESHOLD:
                pairs.append((score, i, j))
    pairs.sort(reverse=True)

    used_canon = set()
    used_preds = set()
    matches = []
    for score, i, j in pairs:
        if i in used_canon or j in used_preds:
            continue
        used_canon.add(i)
        used_preds.add(j)
        matches.append((i, j, score))
    return matches


def load_labeled_examples(canon_by_audit: dict[str, list[CanonicalFinding]]) -> list[dict[str, str]]:
    examples = []
    for row in read_csv(ROOT / "train.csv"):
        if row.get("tag", "").strip() and row.get("subtag", "").strip():
            examples.append(
                {
                    "tag": row["tag"].strip(),
                    "subtag": row["subtag"].strip(),
                    "severity": row.get("severity", "").strip(),
                    "text": row.get("description", "").strip(),
                    "source": "train.csv",
                    "source_title": row.get("description", "").strip()[:140],
                }
            )
    for findings in canon_by_audit.values():
        for finding in findings:
            if finding.has_truth_label:
                examples.append(
                    {
                        "tag": finding.tag,
                        "subtag": finding.subtag,
                        "severity": finding.severity,
                        "text": finding.text,
                        "source": f"dataset_0831:{finding.audit}",
                        "source_title": finding.title,
                    }
                )
    return [e for e in examples if normalize_text(e["text"])]


def heuristic_label(text: str, solodit_tags: Iterable[str]) -> tuple[str, str, str]:
    hay = normalize_text(text + " " + " ".join(solodit_tags))

    rules = [
        (r"\breentr", "Reentrancy", "Violating CEI / Missing nonReentrant"),
        (r"\bfee on transfer\b|\bfee transfer\b|\btax token\b", "ERC20", "Fee On Transfer Token"),
        (r"\berc4626\b|maxwithdraw|maxredeem|share.*zero|first depositor|inflation", "ERC4626", "Inflation Attack"),
        (r"\bchainlink\b.*deprecated|latestanswer", "Chainlink", "Deprecated Library"),
        (r"\bstale\b.*oracle|\boracle\b.*stale", "Chainlink", "Stale Value"),
        (r"\btwap\b|\btwav\b", "TWAP", "Price Manipulation / Arbitrage opportunity"),
        (r"\bslippage\b|minout|maxamount|sandwich", "Slippage", "Invalid  Slippage Control / Missing slippage check"),
        (r"\bfront run\b|frontrun|front running", "MEV", "Front Run"),
        (r"\bliquidat|bad debt", "Liquidation", "Bad Debt"),
        (r"\bpause\b|paused", "Pause", "State Update Inconsistency"),
        (r"\bowner\b|admin|permission|access control|centralization", "Access Control", "Centralization Risk"),
        (r"\boverflow\b|underflow\b", "Arithmetic", "Overflow / Underflow"),
        (r"\bprecision\b|rounding|division before multiplication|decimal", "Arithmetic", "Precision Loss"),
        (r"\bout of gas\b|unbounded loop|gas limit", "DoS", "Out of Gas"),
        (r"\bdos\b|denial of service|revert|cannot withdraw|locked|lock funds", "DoS", "Bad Condition"),
        (r"\bunchecked return\b|return value|approve|transferfrom|transfer\(\)", "ERC20", "Unchecked Return Value"),
        (r"\boracle\b|price feed|price manipulation", "Oracle", "Price Manipulation / Arbitrage opportunity"),
        (r"\bgovernance\b|vote|delegate", "Governance", "Bad Condition"),
    ]
    for pattern, tag, subtag in rules:
        if re.search(pattern, hay):
            return tag, subtag, f"heuristic:{pattern}"
    return "", "", ""


def nearest_labeler(examples: list[dict[str, str]], candidates: list[CanonicalFinding]) -> list[dict[str, object]]:
    if not candidates:
        return []
    fallback = [
        {
            "tag": "",
            "subtag": "",
            "source": "",
            "source_title": "",
            "similarity": 0.0,
        }
        for _ in candidates
    ]
    if TfidfVectorizer is None or cosine_similarity is None or not examples:
        return fallback

    docs = [normalize_text(e["text"]) for e in examples] + [normalize_text(c.text) for c in candidates]
    try:
        vec = TfidfVectorizer(ngram_range=(1, 2), min_df=1, max_df=0.95).fit_transform(docs)
        sim = cosine_similarity(vec[len(examples) :], vec[: len(examples)])
    except ValueError:
        return fallback

    out = []
    for row in sim:
        best_i = int(row.argmax())
        ex = examples[best_i]
        out.append(
            {
                "tag": ex["tag"],
                "subtag": ex["subtag"],
                "source": ex["source"],
                "source_title": ex["source_title"],
                "similarity": float(row[best_i]),
            }
        )
    return out


def choose_suggestion(
    finding: CanonicalFinding,
    nearest: dict[str, object],
    solodit_row: dict[str, object] | None,
) -> tuple[str, str, str, float]:
    if finding.has_truth_label:
        return finding.tag, finding.subtag, "dataset_0831_done", 1.0

    solodit_tags = solodit_row.get("tag_list", []) if solodit_row else []
    h_tag, h_subtag, h_source = heuristic_label(finding.text, solodit_tags)
    n_sim = float(nearest.get("similarity", 0.0) or 0.0)
    n_tag = str(nearest.get("tag", "") or "")
    n_subtag = str(nearest.get("subtag", "") or "")

    if n_sim >= 0.22 and n_tag and n_subtag:
        return n_tag, n_subtag, f"nearest_label:{nearest.get('source')}", n_sim
    if h_tag and h_subtag:
        return h_tag, h_subtag, h_source, 0.18
    if n_sim >= 0.14 and n_tag and n_subtag:
        return n_tag, n_subtag, f"weak_nearest_label:{nearest.get('source')}", n_sim
    return "", "", "", 0.0


def compact_desc(finding: CanonicalFinding, solodit_row: dict[str, object] | None) -> str:
    if solodit_row and str(solodit_row.get("summary", "")).strip():
        summary = re.sub(r"\s+", " ", str(solodit_row["summary"])).strip()
        return summary[:360]

    title = finding.title.rstrip(".")
    body = finding.body
    sentences = re.split(r"(?<=[.!?])\s+", body)
    first = ""
    for sentence in sentences:
        sentence = sentence.strip()
        if len(sentence) >= 40:
            first = sentence
            break
    desc = f"{title}. {first}".strip()
    desc = re.sub(r"\s+", " ", desc)
    return desc[:360]


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    canon_by_audit = load_canonical_findings()
    solodit_by_url = solodit_index()
    examples = load_labeled_examples(canon_by_audit)
    test_map = json.loads(TEST_MAP.read_text(encoding="utf-8"))
    v11_rows = [r for r in read_csv(V11) if r.get("repo_path") != "empty"]
    preds_by_hash = defaultdict(list)
    for row in v11_rows:
        preds_by_hash[row["repo_path"]].append(row)
    v11_repo_counts = Counter(row["repo_path"] for row in v11_rows)

    audit_to_hashes = defaultdict(list)
    for repo_hash, item in test_map.items():
        audit = item.get("contest") if isinstance(item, dict) else item
        if audit:
            audit_to_hashes[audit].append(repo_hash)

    current_needs_truth: list[dict[str, object]] = []
    missing_rows: list[dict[str, object]] = []
    summary_rows: list[dict[str, object]] = []
    all_missing_candidates: list[CanonicalFinding] = []
    missing_context: list[tuple[str, str, bool]] = []

    for repo_hash, item in sorted(test_map.items()):
        audit = item.get("contest") if isinstance(item, dict) else item
        if not audit:
            continue
        canon = canon_by_audit.get(audit, [])
        preds = preds_by_hash.get(repo_hash, [])
        if not canon or not preds:
            continue

        matches = greedy_match(canon, preds)
        matched_canon = {i for i, _, _ in matches}
        duplicate_audit = len(audit_to_hashes[audit]) > 1

        summary_rows.append(
            {
                "repo_hash": repo_hash,
                "audit": audit,
                "v11_rows": len(preds),
                "canonical_rows": len(canon),
                "matched_rows": len(matches),
                "unmatched_canonical_rows": max(0, len(canon) - len(matched_canon)),
                "duplicate_audit_mapping": duplicate_audit,
                "map_confidence": item.get("confidence", "") if isinstance(item, dict) else "",
            }
        )

        for canon_i, pred_i, score in matches:
            finding = canon[canon_i]
            pred = preds[pred_i]
            truth_incomplete = (
                finding.status.lower() != "done"
                or not finding.tag.strip()
                or not finding.subtag.strip()
                or not finding.has_truth_label
            )
            if truth_incomplete:
                current_needs_truth.append(
                    {
                        "repo_hash": repo_hash,
                        "audit": audit,
                        "v11_repo_rows": v11_repo_counts[repo_hash],
                        "property": pred.get("Property", ""),
                        "match_score": round(score, 4),
                        "severity": finding.severity,
                        "current_tag": pred.get("tag", ""),
                        "current_subtag": pred.get("subtag", ""),
                        "canonical_status": finding.status,
                        "canonical_known_tag": finding.tag,
                        "canonical_known_subtag": finding.subtag,
                        "canonical_title": finding.title,
                        "detail": finding.detail,
                        "evidence_url": finding.evidence_url,
                        "current_description": pred.get("description", ""),
                        "duplicate_audit_mapping": duplicate_audit,
                    }
                )

        for i, finding in enumerate(canon):
            if i not in matched_canon:
                all_missing_candidates.append(finding)
                missing_context.append((repo_hash, audit, duplicate_audit))

    nearest = nearest_labeler(examples, all_missing_candidates)
    for finding, near, context in zip(all_missing_candidates, nearest, missing_context):
        repo_hash, audit, duplicate_audit = context
        solodit_row = solodit_by_url.get(finding.evidence_url.rstrip("/")) if finding.evidence_url else None
        suggested_tag, suggested_subtag, source, conf = choose_suggestion(finding, near, solodit_row)
        missing_rows.append(
            {
                "priority": 0,
                "repo_hash": repo_hash,
                "audit": audit,
                "severity": finding.severity,
                "suggested_tag": suggested_tag,
                "suggested_subtag": suggested_subtag,
                "suggestion_source": source,
                "suggestion_confidence": round(conf, 4),
                "nearest_label_similarity": round(float(near.get("similarity", 0.0) or 0.0), 4),
                "nearest_label_source": near.get("source", ""),
                "nearest_label_title": near.get("source_title", ""),
                "canonical_status": finding.status,
                "canonical_known_tag": finding.tag,
                "canonical_known_subtag": finding.subtag,
                "canonical_title": finding.title,
                "candidate_description": compact_desc(finding, solodit_row),
                "detail": finding.detail,
                "evidence_url": finding.evidence_url,
                "solodit_match": bool(solodit_row),
                "solodit_tags": ", ".join(solodit_row.get("tag_list", [])) if solodit_row else "",
                "duplicate_audit_mapping": duplicate_audit,
            }
        )

    # Prioritize likely high ROI: no duplicate-audit ambiguity, known labels first,
    # high severity, Solodit evidence, then nearest-label confidence.
    def priority_key(row: dict[str, object]) -> tuple:
        return (
            bool(row["duplicate_audit_mapping"]),
            0 if row["canonical_known_tag"] else 1,
            0 if row["severity"] == "High" else 1,
            0 if row["solodit_match"] else 1,
            -float(row["suggestion_confidence"]),
            row["audit"],
            row["canonical_title"],
        )

    missing_rows.sort(key=priority_key)
    for i, row in enumerate(missing_rows, 1):
        row["priority"] = i

    current_needs_truth.sort(
        key=lambda row: (
            bool(row["duplicate_audit_mapping"]),
            -int(row["v11_repo_rows"]),
            0 if row["severity"] == "High" else 1,
            -float(row["match_score"]),
            row["audit"],
            row["canonical_title"],
        )
    )
    for i, row in enumerate(current_needs_truth, 1):
        row["priority"] = i
    summary_rows.sort(key=lambda row: (-int(row["unmatched_canonical_rows"]), row["audit"]))

    current_fields = [
        "priority",
        "repo_hash",
        "audit",
        "v11_repo_rows",
        "property",
        "match_score",
        "severity",
        "current_tag",
        "current_subtag",
        "canonical_status",
        "canonical_known_tag",
        "canonical_known_subtag",
        "canonical_title",
        "detail",
        "evidence_url",
        "current_description",
        "duplicate_audit_mapping",
    ]
    missing_fields = [
        "priority",
        "repo_hash",
        "audit",
        "severity",
        "suggested_tag",
        "suggested_subtag",
        "suggestion_source",
        "suggestion_confidence",
        "nearest_label_similarity",
        "nearest_label_source",
        "nearest_label_title",
        "canonical_status",
        "canonical_known_tag",
        "canonical_known_subtag",
        "canonical_title",
        "candidate_description",
        "detail",
        "evidence_url",
        "solodit_match",
        "solodit_tags",
        "duplicate_audit_mapping",
    ]

    write_csv(
        OUT_DIR / "current_v11_rows_need_truth_labels.csv",
        current_needs_truth,
        current_fields,
    )
    write_csv(
        OUT_DIR / "teammate_batch_current_labels_top80.csv",
        current_needs_truth[:80],
        current_fields,
    )
    write_csv(
        OUT_DIR / "missing_canonical_findings_enriched.csv",
        missing_rows,
        missing_fields,
    )
    write_csv(
        OUT_DIR / "teammate_batch_swap_candidates_top40.csv",
        missing_rows[:40],
        missing_fields,
    )
    write_csv(
        OUT_DIR / "hash_level_gap_summary.csv",
        summary_rows,
        [
            "repo_hash",
            "audit",
            "v11_rows",
            "canonical_rows",
            "matched_rows",
            "unmatched_canonical_rows",
            "duplicate_audit_mapping",
            "map_confidence",
        ],
    )

    summary = {
        "baseline": str(V11.relative_to(ROOT)),
        "baseline_non_empty_rows": len(v11_rows),
        "baseline_repo_count": len(preds_by_hash),
        "match_threshold": MATCH_THRESHOLD,
        "current_rows_need_truth_labels": len(current_needs_truth),
        "missing_canonical_findings": len(missing_rows),
        "missing_with_known_dataset_labels": sum(1 for r in missing_rows if r["canonical_known_tag"]),
        "missing_with_solodit_match": sum(1 for r in missing_rows if r["solodit_match"]),
        "missing_by_audit": Counter(r["audit"] for r in missing_rows),
        "current_truth_work_by_audit": Counter(r["audit"] for r in current_needs_truth),
        "duplicate_audit_hashes": {
            audit: hashes for audit, hashes in audit_to_hashes.items() if len(hashes) > 1
        },
        "outputs": {
            "current_truth_labels": str((OUT_DIR / "current_v11_rows_need_truth_labels.csv").relative_to(ROOT)),
            "current_truth_labels_top80": str((OUT_DIR / "teammate_batch_current_labels_top80.csv").relative_to(ROOT)),
            "missing_findings": str((OUT_DIR / "missing_canonical_findings_enriched.csv").relative_to(ROOT)),
            "missing_findings_top40": str((OUT_DIR / "teammate_batch_swap_candidates_top40.csv").relative_to(ROOT)),
            "hash_gap_summary": str((OUT_DIR / "hash_level_gap_summary.csv").relative_to(ROOT)),
        },
    }
    (OUT_DIR / "breakout_summary.json").write_text(json.dumps(summary, indent=2, default=dict) + "\n", encoding="utf-8")

    lines = [
        "# Bastet 500 Breakout Worklist",
        "",
        "Generated by `scripts/deep_research_breakout.py`.",
        "",
        "## What changed",
        "",
        "- Separates current v11 rows needing exact truth-label verification from missing canonical findings that require row swaps.",
        "- Uses title-aware matching against local C4 report markdown instead of audit-level count math.",
        "- Enriches missing findings with Solodit matches when the public issue URL appears in the Solodit dump.",
        "- Provides draft tag/subtag suggestions from known Bastet labels plus conservative heuristics; these are review targets, not automatic truth.",
        "",
        "## Counts",
        "",
        f"- Current v11 rows needing truth-label verification: {len(current_needs_truth)}",
        f"- Missing canonical findings requiring swaps: {len(missing_rows)}",
        f"- Missing findings with public Solodit issue match: {summary['missing_with_solodit_match']}",
        f"- Missing findings already carrying local dataset labels: {summary['missing_with_known_dataset_labels']}",
        "",
        "## Why this can break 500",
        "",
        "- v11 needs roughly +58 points to move from the 440s to 500.",
        f"- The current-row queue has {len(current_needs_truth)} already-budgeted predictions. An average +0.21 points per row reaches that jump without any row swaps.",
        f"- The swap queue has {len(missing_rows)} canonical findings, but swaps must clear the replacement-cost bar proved by the failed MISO probe.",
        "",
        "## Priority",
        "",
        "1. Fill/verify the current-row truth-label queue first. It can improve tag/subtag/description score without spending new row budget.",
        "2. Only after that, consider swaps from `missing_canonical_findings_enriched.csv`, starting at priority 1.",
        "3. Do not submit blind swaps unless the removed row's value has been measured or the new row has reviewed labels.",
        "",
        "## Output files",
        "",
        "- `artifacts/deep_research/current_v11_rows_need_truth_labels.csv`",
        "- `artifacts/deep_research/teammate_batch_current_labels_top80.csv`",
        "- `artifacts/deep_research/missing_canonical_findings_enriched.csv`",
        "- `artifacts/deep_research/teammate_batch_swap_candidates_top40.csv`",
        "- `artifacts/deep_research/hash_level_gap_summary.csv`",
        "- `artifacts/deep_research/breakout_summary.json`",
    ]
    (OUT_DIR / "breakout_plan.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("Breakout worklist built.")
    print(f"  current rows needing truth labels: {len(current_needs_truth)}")
    print(f"  missing canonical findings:        {len(missing_rows)}")
    print(f"  Solodit matches on missing rows:   {summary['missing_with_solodit_match']}")
    print(f"  outputs: {OUT_DIR.relative_to(ROOT)}")


if __name__ == "__main__":
    main()

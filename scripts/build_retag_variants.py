"""Build follow-up retag variants after `submission_c4_v13_retag.csv` improved.

These variants keep the exact same 400 rows, repo counts, severities, and
descriptions. Only tag/subtag fields change.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
V11 = ROOT / "outputs" / "submission_c4_v11.csv"
V13 = ROOT / "outputs" / "submission_c4_v13_retag.csv"
VOTES = ROOT / "artifacts" / "tag_classifier" / "predictions_apply.json"
VOCAB = ROOT / "artifacts" / "tag_classifier" / "vocab.json"
OUT_DIR = ROOT / "outputs" / "retag_variants"
REPORT_DIR = ROOT / "artifacts" / "tag_classifier"
FIELDS = ["Property", "repo_path", "severity", "tag", "subtag", "description"]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows({field: row.get(field, "") for field in FIELDS} for row in rows)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def norm(value: str) -> str:
    return re.sub(r"\s+", " ", str(value)).strip().lower()


def load_canon():
    vocab = json.loads(VOCAB.read_text(encoding="utf-8"))
    tags = {norm(tag): tag for tag in vocab["tags"]}
    subtags = {norm(subtag): subtag for subtag in vocab["subtags"]}
    return tags, subtags


TAG_CANON, SUB_CANON = load_canon()


def canon_tag(value: str) -> str:
    return TAG_CANON.get(norm(value), str(value).strip())


def canon_subtag(value: str) -> str:
    return SUB_CANON.get(norm(value), str(value).strip())


def split_labels(value: str) -> list[str]:
    return [part.strip() for part in str(value).split(",") if part.strip()]


def join_unique(labels: list[str]) -> str:
    out = []
    seen = set()
    for label in labels:
        key = norm(label)
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(label)
    return ", ".join(out)


def top_vote(votes: list[dict[str, str]], field: str, mode: str) -> str | None:
    if not votes:
        return None
    values = [canon_tag(v[field]) if field == "tag" else canon_subtag(v[field]) for v in votes if v.get(field)]
    if not values:
        return None
    counts = Counter(values)
    top, count = counts.most_common(1)[0]
    n = len(values)

    if mode == "v13":
        return top if count >= 2 and count >= 0.6 * n else None
    if mode == "unanimous":
        return top if count == n and n >= 2 else None
    if mode == "plurality2":
        return top if count >= 2 else None
    if mode == "any":
        return top
    raise ValueError(f"unknown vote mode {mode}")


def apply_variant(base_rows: list[dict[str, str]], variant: dict) -> tuple[list[dict[str, str]], dict[str, int]]:
    votes_by_pid = json.loads(VOTES.read_text(encoding="utf-8"))
    rows = [dict(row) for row in base_rows]
    stats = Counter()

    for row in rows:
        pid = row["Property"]
        votes = votes_by_pid.get(str(pid)) or votes_by_pid.get(pid)
        if not votes:
            continue
        mode = variant["vote_mode"]
        tag_vote = top_vote(votes, "tag", mode)
        sub_vote = top_vote(votes, "subtag", mode)

        if variant.get("tag_action") == "replace" and tag_vote and norm(tag_vote) != norm(row["tag"]):
            row["tag"] = tag_vote
            stats["tag_changed"] += 1
        elif variant.get("tag_action") == "hedge" and tag_vote and norm(tag_vote) != norm(row["tag"]):
            row["tag"] = join_unique(split_labels(row["tag"]) + [tag_vote])
            stats["tag_hedged"] += 1

        if variant.get("subtag_action") == "replace" and sub_vote and norm(sub_vote) != norm(row["subtag"]):
            row["subtag"] = sub_vote
            stats["subtag_changed"] += 1
        elif variant.get("subtag_action") == "hedge" and sub_vote and norm(sub_vote) != norm(row["subtag"]):
            row["subtag"] = join_unique(split_labels(row["subtag"]) + [sub_vote])
            stats["subtag_hedged"] += 1

    return rows, dict(stats)


def main() -> None:
    v11 = read_csv(V11)
    v13 = read_csv(V13)
    variants = [
        {
            "name": "submission_c4_v14_retag_unanimous",
            "base": "v11",
            "vote_mode": "unanimous",
            "tag_action": "replace",
            "subtag_action": "replace",
            "hypothesis": "Safer than v13: only override when every vote agrees.",
        },
        {
            "name": "submission_c4_v15_retag_tagonly",
            "base": "v11",
            "vote_mode": "v13",
            "tag_action": "replace",
            "subtag_action": "keep",
            "hypothesis": "Isolate tag overrides from v13.",
        },
        {
            "name": "submission_c4_v16_retag_subtagonly",
            "base": "v11",
            "vote_mode": "v13",
            "tag_action": "keep",
            "subtag_action": "replace",
            "hypothesis": "Isolate subtag overrides from v13.",
        },
        {
            "name": "submission_c4_v17_retag_plurality2",
            "base": "v11",
            "vote_mode": "plurality2",
            "tag_action": "replace",
            "subtag_action": "replace",
            "hypothesis": "More aggressive than v13: any label with at least two votes wins.",
        },
        {
            "name": "submission_c4_v18_retag_hedge_v13",
            "base": "v11",
            "vote_mode": "v13",
            "tag_action": "hedge",
            "subtag_action": "hedge",
            "hypothesis": "Keep v11 labels and add v13 majority labels as hedges.",
        },
        {
            "name": "submission_c4_v19_retag_v13_plus_plurality_subtags",
            "base": "v13",
            "vote_mode": "plurality2",
            "tag_action": "keep",
            "subtag_action": "replace",
            "hypothesis": "Start from public-improving v13, then apply more aggressive subtag-only replacements.",
        },
    ]

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    manifest = []
    for variant in variants:
        base_rows = v13 if variant["base"] == "v13" else v11
        rows, stats = apply_variant(base_rows, variant)
        path = OUT_DIR / f"{variant['name']}.csv"
        write_csv(path, rows)
        row_counts = Counter(row["repo_path"] for row in rows)
        manifest.append(
            {
                "name": variant["name"],
                "file": str(path.relative_to(ROOT)),
                "sha256": sha256(path),
                "hypothesis": variant["hypothesis"],
                "base": variant["base"],
                "vote_mode": variant["vote_mode"],
                "tag_action": variant["tag_action"],
                "subtag_action": variant["subtag_action"],
                "stats": stats,
                "non_empty_rows": sum(1 for row in rows if row["repo_path"] != "empty"),
                "repo_counts_identical_to_v11": row_counts == Counter(row["repo_path"] for row in v11),
            }
        )

    manifest_path = REPORT_DIR / "retag_variant_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    lines = [
        "# Retag Variant Manifest",
        "",
        "All variants preserve the same 400 rows and per-repo counts as v11/v13.",
        "",
    ]
    for item in manifest:
        lines.extend(
            [
                f"## {item['name']}",
                "",
                f"- File: `{item['file']}`",
                f"- Base: `{item['base']}`",
                f"- Vote mode: `{item['vote_mode']}`",
                f"- Stats: `{item['stats']}`",
                f"- Hypothesis: {item['hypothesis']}",
                "",
            ]
        )
    (REPORT_DIR / "retag_variant_manifest.md").write_text("\n".join(lines), encoding="utf-8")

    print("Built retag variants:")
    for item in manifest:
        print(f"  {item['name']}: {item['file']} {item['stats']} sha={item['sha256'][:12]}")


if __name__ == "__main__":
    main()

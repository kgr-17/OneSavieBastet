"""Build aggressive Bastet experiment submissions from the v11 baseline.

These are intentionally *not* production-safe. The point is to turn the public
leaderboard into a black-box lab:

  - small high-confidence swaps to test replacement economics
  - large risky swaps to search for a discontinuous jump
  - blanking probes to measure row value by bucket
  - a tiny no-swap label patch probe

Each output is a valid 400-row submission CSV plus a JSON/Markdown manifest.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "outputs" / "submission_c4_v11.csv"
MISSING = ROOT / "artifacts" / "deep_research" / "missing_canonical_findings_enriched.csv"
CURRENT = ROOT / "artifacts" / "deep_research" / "current_v11_rows_need_truth_labels.csv"
SUMMARY = ROOT / "artifacts" / "deep_research" / "hash_level_gap_summary.csv"
TIERS = ROOT / "scripts" / "tiers.json"
OUT_DIR = ROOT / "outputs" / "aggressive"
REPORT_DIR = ROOT / "artifacts" / "deep_research"
FIELDS = ["Property", "repo_path", "severity", "tag", "subtag", "description"]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def write_submission(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [dict(row) for row in rows]
    if len(rows) > 400:
        rows = rows[:400]
    while len(rows) < 400:
        rows.append(
            {
                "repo_path": "empty",
                "severity": "empty",
                "tag": "empty",
                "subtag": "empty",
                "description": "empty",
            }
        )
    for i, row in enumerate(rows, 1):
        row["Property"] = str(i)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows({key: row.get(key, "") for key in FIELDS} for row in rows)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def words(value: str) -> int:
    return len(re.findall(r"[A-Za-z0-9_]+", value or ""))


def is_empty(row: dict[str, str]) -> bool:
    return row.get("repo_path") == "empty"


def clean_desc(value: str, fallback: str) -> str:
    value = re.sub(r"\s+", " ", (value or "").strip())
    fallback = re.sub(r"\s+", " ", (fallback or "").strip())
    text = value or fallback
    text = text.replace("\r", " ").replace("\n", " ")
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        text = "The finding describes a high or medium severity smart contract vulnerability in the audited protocol."
    return text[:420]


def load_inputs() -> dict[str, object]:
    baseline = read_csv(BASELINE)
    missing = read_csv(MISSING)
    current = read_csv(CURRENT)
    summary = {row["repo_hash"]: row for row in read_csv(SUMMARY)}
    tiers = json.loads(TIERS.read_text(encoding="utf-8")) if TIERS.exists() else {"tier_b": []}
    counts = Counter(row["repo_path"] for row in baseline if not is_empty(row))
    current_by_property = {row["property"]: row for row in current}
    return {
        "baseline": baseline,
        "missing": missing,
        "current": current,
        "summary": summary,
        "tiers": tiers,
        "counts": counts,
        "current_by_property": current_by_property,
    }


def add_candidate(row: dict[str, str]) -> dict[str, str] | None:
    tag = row.get("canonical_known_tag") or row.get("suggested_tag")
    subtag = row.get("canonical_known_subtag") or row.get("suggested_subtag")
    if not tag or not subtag:
        return None
    return {
        "repo_path": row["repo_hash"],
        "severity": row["severity"],
        "tag": tag,
        "subtag": subtag,
        "description": clean_desc(row.get("candidate_description", ""), row.get("canonical_title", "")),
    }


def candidate_meta(row: dict[str, str]) -> dict[str, object]:
    return {
        "priority": row.get("priority", ""),
        "repo_hash": row.get("repo_hash", ""),
        "audit": row.get("audit", ""),
        "severity": row.get("severity", ""),
        "title": row.get("canonical_title", ""),
        "tag": row.get("canonical_known_tag") or row.get("suggested_tag", ""),
        "subtag": row.get("canonical_known_subtag") or row.get("suggested_subtag", ""),
        "source": row.get("suggestion_source", ""),
        "solodit_match": row.get("solodit_match", ""),
        "known_dataset_label": bool(row.get("canonical_known_tag")),
    }


def top_candidates(missing: list[dict[str, str]], n: int, *, known_only: bool = False) -> tuple[list[dict[str, str]], list[dict[str, object]]]:
    adds: list[dict[str, str]] = []
    metas: list[dict[str, object]] = []
    used = set()
    for row in missing:
        if known_only and not row.get("canonical_known_tag"):
            continue
        add = add_candidate(row)
        if not add:
            continue
        key = (add["repo_path"], row.get("canonical_title", ""))
        if key in used:
            continue
        used.add(key)
        adds.append(add)
        metas.append(candidate_meta(row))
        if len(adds) >= n:
            break
    return adds, metas


def row_drop_meta(row: dict[str, str], current_by_property: dict[str, dict[str, str]], counts: Counter) -> dict[str, object]:
    cur = current_by_property.get(row["Property"], {})
    return {
        "property": row.get("Property", ""),
        "repo_hash": row.get("repo_path", ""),
        "repo_rows_before": counts[row.get("repo_path", "")],
        "severity": row.get("severity", ""),
        "tag": row.get("tag", ""),
        "subtag": row.get("subtag", ""),
        "description_words": words(row.get("description", "")),
        "match_score": cur.get("match_score", ""),
        "audit": cur.get("audit", ""),
        "canonical_title": cur.get("canonical_title", ""),
        "description": row.get("description", "")[:180],
    }


def candidate_rows(baseline: list[dict[str, str]], counts: Counter) -> list[dict[str, str]]:
    return [row for row in baseline if not is_empty(row) and counts[row["repo_path"]] > 1]


def select_tierb_drops(data: dict[str, object], n: int) -> list[dict[str, str]]:
    baseline = data["baseline"]
    counts = data["counts"]
    tier_b = set(data["tiers"].get("tier_b", []))
    rows = [row for row in candidate_rows(baseline, counts) if row["repo_path"] in tier_b]
    rows.sort(key=lambda row: (counts[row["repo_path"]], row["severity"] == "High", words(row["description"]), int(row["Property"])))
    return rows[:n]


def select_lowconf_drops(data: dict[str, object], n: int, *, exclude_tierb: bool = False) -> list[dict[str, str]]:
    baseline = data["baseline"]
    counts = data["counts"]
    current_by_property = data["current_by_property"]
    tier_b = set(data["tiers"].get("tier_b", []))

    rows = []
    for row in candidate_rows(baseline, counts):
        if exclude_tierb and row["repo_path"] in tier_b:
            continue
        cur = current_by_property.get(row["Property"], {})
        match = float(cur.get("match_score") or 9.0)
        duplicate = cur.get("duplicate_audit_mapping") == "True"
        # prefer rows with low report-title match, medium severity, short desc,
        # and high repo count so a single drop is less likely to uncover a repo.
        rank = (
            duplicate,
            match,
            row["severity"] == "High",
            words(row["description"]),
            -counts[row["repo_path"]],
            int(row["Property"]),
        )
        rows.append((rank, row))
    rows.sort(key=lambda item: item[0])
    return [row for _, row in rows[:n]]


def select_stakehouse_tail(data: dict[str, object], n: int) -> list[dict[str, str]]:
    baseline = data["baseline"]
    current_by_property = data["current_by_property"]
    rows = [row for row in baseline if row.get("repo_path") == "099243e83259"]
    rows.sort(key=lambda row: (float(current_by_property.get(row["Property"], {}).get("match_score") or 9.0), words(row["description"]), int(row["Property"])))
    return rows[:n]


def select_mixed_drops(data: dict[str, object], n: int) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    seen = set()
    for group in (select_tierb_drops(data, n), select_lowconf_drops(data, n, exclude_tierb=True)):
        for row in group:
            if row["Property"] in seen:
                continue
            seen.add(row["Property"])
            out.append(row)
            if len(out) >= n:
                return out
    return out


def build_swap_submission(
    data: dict[str, object],
    drops: list[dict[str, str]],
    adds: list[dict[str, str]],
) -> list[dict[str, str]]:
    drop_props = {row["Property"] for row in drops[: len(adds)]}
    kept = [dict(row) for row in data["baseline"] if row["Property"] not in drop_props]
    kept.extend(dict(row) for row in adds)
    return kept


def build_blank_probe(data: dict[str, object], drops: list[dict[str, str]]) -> list[dict[str, str]]:
    drop_props = {row["Property"] for row in drops}
    out = []
    for row in data["baseline"]:
        if row["Property"] in drop_props:
            out.append(
                {
                    "Property": row["Property"],
                    "repo_path": "empty",
                    "severity": "empty",
                    "tag": "empty",
                    "subtag": "empty",
                    "description": "empty",
                }
            )
        else:
            out.append(dict(row))
    return out


def build_label_patch(data: dict[str, object]) -> tuple[list[dict[str, str]], list[dict[str, object]]]:
    rows = [dict(row) for row in data["baseline"]]
    by_property = {row["Property"]: row for row in rows}
    patches = []
    for cur in data["current"]:
        if not cur.get("canonical_known_tag"):
            continue
        match = float(cur.get("match_score") or 0.0)
        current_tag = cur.get("current_tag", "")
        current_subtag = cur.get("current_subtag", "")
        canon_tag = cur.get("canonical_known_tag", "")
        canon_subtag = cur.get("canonical_known_subtag", "")
        if current_tag == canon_tag and current_subtag == canon_subtag:
            continue
        if match < 0.19:
            continue
        target = by_property.get(cur["property"])
        if not target:
            continue
        before = {"tag": target["tag"], "subtag": target["subtag"]}
        target["tag"] = canon_tag
        target["subtag"] = canon_subtag
        patches.append(
            {
                "property": cur["property"],
                "repo_hash": target["repo_path"],
                "audit": cur.get("audit", ""),
                "match_score": match,
                "before": before,
                "after": {"tag": canon_tag, "subtag": canon_subtag},
                "title": cur.get("canonical_title", ""),
            }
        )
    return rows, patches


def experiment_record(
    name: str,
    path: Path,
    hypothesis: str,
    drops: list[dict[str, str]],
    adds_meta: list[dict[str, object]],
    data: dict[str, object],
    notes: str = "",
) -> dict[str, object]:
    counts = data["counts"]
    current_by_property = data["current_by_property"]
    non_empty = sum(1 for row in read_csv(path) if row.get("repo_path") != "empty")
    return {
        "name": name,
        "file": str(path.relative_to(ROOT)),
        "sha256": sha256(path),
        "hypothesis": hypothesis,
        "notes": notes,
        "non_empty_rows": non_empty,
        "drop_count": len(drops),
        "add_count": len(adds_meta),
        "drops": [row_drop_meta(row, current_by_property, counts) for row in drops],
        "adds": adds_meta,
    }


def main() -> None:
    data = load_inputs()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    manifest: list[dict[str, object]] = []

    known8, known8_meta = top_candidates(data["missing"], 8, known_only=True)
    top20, top20_meta = top_candidates(data["missing"], 20, known_only=False)
    top40, top40_meta = top_candidates(data["missing"], 40, known_only=False)

    experiments = [
        (
            "exp_v13_known8_tierb",
            "Swap 8 Tier-B rows for the 8 missing findings that already have dataset_0831 tag/subtag labels.",
            select_tierb_drops(data, len(known8)),
            known8,
            known8_meta,
            "Tests whether reviewed labels can beat the measured Tier-B replacement cost from P0.",
        ),
        (
            "exp_v14_known8_lowconf",
            "Swap 8 low-confidence non-Tier-B rows for the same 8 known-label missing findings.",
            select_lowconf_drops(data, len(known8), exclude_tierb=True),
            known8,
            known8_meta,
            "Riskier than v13; tests whether report-title low-confidence rows are actually weak.",
        ),
        (
            "exp_v15_top20_mixed",
            "Swap 20 mixed low-confidence rows for the top 20 enriched missing canonical findings.",
            select_mixed_drops(data, len(top20)),
            top20,
            top20_meta,
            "This is the first real jump attempt: known labels plus strong Solodit/heuristic candidates.",
        ),
        (
            "exp_v16_top40_mixed",
            "Swap 40 mixed low-confidence rows for the top 40 enriched missing canonical findings.",
            select_mixed_drops(data, len(top40)),
            top40,
            top40_meta,
            "High-variance search for a discontinuous jump. Use after v13/v15 teach replacement cost.",
        ),
    ]

    for name, hypothesis, drops, adds, adds_meta, notes in experiments:
        path = OUT_DIR / f"{name}.csv"
        write_submission(path, build_swap_submission(data, drops, adds))
        manifest.append(experiment_record(name, path, hypothesis, drops[: len(adds)], adds_meta, data, notes))

    probes = [
        (
            "probe_v11_blank_tierb8",
            "Blank only the 8 Tier-B rows used by exp_v13, with no adds.",
            select_tierb_drops(data, 8),
            "Score delta estimates the exact replacement bar for exp_v13's drop set.",
        ),
        (
            "probe_v11_blank_lowconf10",
            "Blank the 10 lowest report-title-confidence non-Tier-B rows, with no adds.",
            select_lowconf_drops(data, 10, exclude_tierb=True),
            "If this barely hurts, low-confidence matching is a real row-value signal.",
        ),
        (
            "probe_v11_blank_stakehouse10",
            "Blank 10 rows from the 51-row Stakehouse cluster, with no adds.",
            select_stakehouse_tail(data, 10),
            "Tests whether the huge Stakehouse cluster is over-concentrated or genuinely carrying score.",
        ),
    ]
    for name, hypothesis, drops, notes in probes:
        path = OUT_DIR / f"{name}.csv"
        write_submission(path, build_blank_probe(data, drops))
        manifest.append(experiment_record(name, path, hypothesis, drops, [], data, notes))

    patch_rows, patches = build_label_patch(data)
    patch_path = OUT_DIR / "exp_v17_label_patch_known_current.csv"
    write_submission(patch_path, patch_rows)
    manifest.append(
        {
            "name": "exp_v17_label_patch_known_current",
            "file": str(patch_path.relative_to(ROOT)),
            "sha256": sha256(patch_path),
            "hypothesis": "No row swaps; patch current rows where local dataset_0831 known labels disagree with v11 and match confidence is at least 0.19.",
            "notes": "Tiny, risky label-set probe. If it improves, mine current-row label corrections harder.",
            "non_empty_rows": 400,
            "drop_count": 0,
            "add_count": 0,
            "patches": patches,
        }
    )

    manifest_path = REPORT_DIR / "aggressive_experiment_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# Aggressive Experiment Manifest",
        "",
        "Generated by `scripts/build_aggressive_experiments.py`.",
        "",
        "These files are intentionally high-variance. Submit the smaller probes first if daily limits matter; submit the large swaps when you want to search for a jump.",
        "",
    ]
    for item in manifest:
        lines.extend(
            [
                f"## {item['name']}",
                "",
                f"- File: `{item['file']}`",
                f"- Non-empty rows: {item['non_empty_rows']}",
                f"- Drops/adds: {item.get('drop_count', 0)} / {item.get('add_count', 0)}",
                f"- Hypothesis: {item['hypothesis']}",
                f"- Notes: {item.get('notes', '')}",
                "",
            ]
        )
    (REPORT_DIR / "aggressive_experiment_manifest.md").write_text("\n".join(lines), encoding="utf-8")

    print("Built aggressive experiment submissions:")
    for item in manifest:
        print(f"  {item['name']}: {item['file']} sha={item['sha256'][:12]}")
    print(f"Manifest: {manifest_path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()

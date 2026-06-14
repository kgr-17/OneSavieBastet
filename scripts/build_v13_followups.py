"""Build incremental row-swap follow-ups from an obsolete v13 hypothesis.

WARNING: This script is not the current primary path. It was created before we
confirmed that public `submission_c4_v13_retag.csv` was a pure retag ensemble,
not the `exp_v13_known8_tierb` row-swap file. Prefer
`scripts/build_retag_variants.py`.

Public feedback:
  submission_c4_v13_retag: 464.74789, +21.86398 vs 442.88391
  exp_v20_report_heuristic_gapheavy: 48.12250, discard broad retagging.

This script only remains as an optional row-swap branch:
  - keep the 8 reviewed-label adds
  - add only a few more high-priority candidate findings
  - fund them with the next Tier-B rows or measured-low-confidence rows
"""

from __future__ import annotations

import csv
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_aggressive_experiments import (  # noqa: E402
    add_candidate,
    candidate_meta,
    load_inputs,
    select_lowconf_drops,
    select_tierb_drops,
    write_submission,
)


BASELINE = ROOT / "outputs" / "submission_c4_v11.csv"
MISSING = ROOT / "artifacts" / "deep_research" / "missing_canonical_findings_enriched.csv"
OUT_DIR = ROOT / "outputs" / "v13_followups"
REPORT_DIR = ROOT / "artifacts" / "deep_research"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def top_adds(start_priority: int, n: int, *, require_tag: bool = True) -> tuple[list[dict[str, str]], list[dict[str, object]]]:
    adds = []
    metas = []
    used = set()
    for row in read_csv(MISSING):
        priority = int(row["priority"])
        if priority < start_priority:
            continue
        if require_tag and not (row.get("canonical_known_tag") or row.get("suggested_tag")):
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


def base_known8() -> tuple[list[dict[str, str]], list[dict[str, object]]]:
    return top_adds(1, 8)


def build_submission(data: dict, drops: list[dict[str, str]], adds: list[dict[str, str]]) -> list[dict[str, str]]:
    drop_props = {row["Property"] for row in drops[: len(adds)]}
    kept = [dict(row) for row in data["baseline"] if row["Property"] not in drop_props]
    kept.extend(dict(row) for row in adds)
    return kept


def drop_meta(row: dict[str, str], data: dict) -> dict[str, object]:
    cur = data["current_by_property"].get(row["Property"], {})
    return {
        "property": row.get("Property", ""),
        "repo_hash": row.get("repo_path", ""),
        "severity": row.get("severity", ""),
        "tag": row.get("tag", ""),
        "subtag": row.get("subtag", ""),
        "audit": cur.get("audit", ""),
        "match_score": cur.get("match_score", ""),
        "canonical_title": cur.get("canonical_title", ""),
        "repo_rows_before": data["counts"].get(row.get("repo_path", ""), 0),
    }


def record(name: str, path: Path, hypothesis: str, drops: list[dict[str, str]], adds_meta: list[dict[str, object]], data: dict) -> dict[str, object]:
    rows = read_csv(path)
    real = [row for row in rows if row.get("repo_path") != "empty"]
    return {
        "name": name,
        "file": str(path.relative_to(ROOT)),
        "sha256": sha256(path),
        "hypothesis": hypothesis,
        "non_empty_rows": len(real),
        "unique_repos": len({row["repo_path"] for row in real}),
        "drop_count": len(drops),
        "add_count": len(adds_meta),
        "severity_counts": dict(Counter(row["severity"] for row in real)),
        "drops": [drop_meta(row, data) for row in drops],
        "adds": adds_meta,
    }


def main() -> None:
    data = load_inputs()
    known8, known8_meta = base_known8()

    tierb_all = select_tierb_drops(data, 21)
    tierb_base8 = tierb_all[:8]
    tierb_next = tierb_all[8:]
    lowconf_all = select_lowconf_drops(data, 20, exclude_tierb=True)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    manifest = []

    specs = []
    for extra_n in (2, 4, 6, 8):
        extra_adds, extra_meta = top_adds(9, extra_n)
        specs.append(
            (
                f"exp_v22_v13_plus{extra_n}_nexttierb",
                tierb_base8 + tierb_next[:extra_n],
                known8 + extra_adds,
                known8_meta + extra_meta,
                f"v13 plus {extra_n} next-priority candidates, funded by next Tier-B rows.",
            )
        )

    for extra_n in (2, 4, 6):
        extra_adds, extra_meta = top_adds(9, extra_n)
        specs.append(
            (
                f"exp_v23_v13_plus{extra_n}_lowconf",
                tierb_base8 + lowconf_all[:extra_n],
                known8 + extra_adds,
                known8_meta + extra_meta,
                f"v13 plus {extra_n} next-priority candidates, funded by low-confidence mapped rows.",
            )
        )

    # A retag-only probe: v13 additions, plus the two known current label patches from exp_v17.
    # Implement inline to avoid depending on prior output files.
    label_patch_rows = [dict(row) for row in data["baseline"]]
    by_prop = {row["Property"]: row for row in label_patch_rows}
    patches = []
    for cur in data["current"]:
        if not cur.get("canonical_known_tag"):
            continue
        if cur.get("current_tag") == cur.get("canonical_known_tag") and cur.get("current_subtag") == cur.get("canonical_known_subtag"):
            continue
        match = float(cur.get("match_score") or 0.0)
        if match < 0.19:
            continue
        target = by_prop.get(cur["property"])
        if not target:
            continue
        patches.append(
            {
                "property": cur["property"],
                "repo_hash": target["repo_path"],
                "before": {"tag": target["tag"], "subtag": target["subtag"]},
                "after": {"tag": cur["canonical_known_tag"], "subtag": cur["canonical_known_subtag"]},
                "match_score": match,
                "title": cur.get("canonical_title", ""),
            }
        )
        target["tag"] = cur["canonical_known_tag"]
        target["subtag"] = cur["canonical_known_subtag"]
    # Apply v13 swaps on top of patched baseline.
    patched_data = dict(data)
    patched_data["baseline"] = label_patch_rows
    specs.append(
        (
            "exp_v24_v13_plus_current_labelpatch",
            tierb_base8,
            known8,
            known8_meta,
            "v13 swaps plus the two current-row label patches from known dataset labels.",
        )
    )

    for name, drops, adds, adds_meta, hypothesis in specs:
        path = OUT_DIR / f"{name}.csv"
        source_data = patched_data if name == "exp_v24_v13_plus_current_labelpatch" else data
        write_submission(path, build_submission(source_data, drops, adds))
        item = record(name, path, hypothesis, drops[: len(adds)], adds_meta, data)
        if name == "exp_v24_v13_plus_current_labelpatch":
            item["patches"] = patches
        manifest.append(item)

    manifest_path = REPORT_DIR / "v13_followup_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# v13 Follow-Up Manifest",
        "",
        "These are incremental experiments after v13 improved publicly. Submit small plus-N variants first.",
        "",
    ]
    for item in manifest:
        lines.extend(
            [
                f"## {item['name']}",
                "",
                f"- File: `{item['file']}`",
                f"- Drops/adds: {item['drop_count']} / {item['add_count']}",
                f"- Unique repos: {item['unique_repos']}",
                f"- Hypothesis: {item['hypothesis']}",
                "",
            ]
        )
    (REPORT_DIR / "v13_followup_manifest.md").write_text("\n".join(lines), encoding="utf-8")

    print("Built v13 follow-up submissions:")
    for item in manifest:
        print(f"  {item['name']}: {item['file']} sha={item['sha256'][:12]}")
    print(f"Manifest: {manifest_path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()

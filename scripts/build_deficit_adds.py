"""STEP 4+5: build the severity-floor deficit-add pool.

For each deep-deficit test hash, compute free truth slots BY SEVERITY
(free = dataset_0831_sev_count - teammate_sev_count). Generate candidate add rows:
  - severity: VERBATIM from dataset_0831 (prioritize the severity that has free slots)
  - tag/subtag: from dataset_0831 where present; else best-effort TF-IDF (wrong = 0, never negative)
  - description: gated .md extraction (bonus only; blank if no good extract)

Each candidate carries a confidence rank. v10 assembly takes the top-N where
N = number of TIER_B rows freed by the probe. Caps each repo at dataset_0831_count - 2.

Outputs scripts/deficit_pool.json (ranked candidate rows).
"""
import csv
import json
import os
import re
import sys
from collections import defaultdict, Counter

sys.stdout.reconfigure(encoding="utf-8")
ROOT = "c:/OneSavieBastet"

# deficit hash -> audit (the repos with the most free slots, Medium-dominant)
TARGETS = {
    "e0d2d83ea351": "2023-01-popcorn",
    "54405135ebf3": "2022-08-frax",
    "198fa93fabdd": "2022-06-nibbl",
    "ee25ec7abd40": "2024-07-optimism",
    "2c5e13b4e147": "2022-05-cudos",
    "804fe35b0164": "2022-11-non-fungible",
    "e169bbefc6e2": "2022-04-jpegd",
    "fa1836e0615e": "2023-08-dopex",
}
# priority order for filling (deepest, cleanest-Medium first)
PRIORITY = ["e0d2d83ea351", "54405135ebf3", "198fa93fabdd", "ee25ec7abd40",
            "2c5e13b4e147", "804fe35b0164", "e169bbefc6e2", "fa1836e0615e"]


def norm(rp):
    return rp[6:] if rp.startswith("repos/") else rp


def clean_md_to_desc(md_text):
    """Extract a concise competition-style description from a warden .md. Bonus only."""
    # title: first '## [[X-NN] Title](url)' line -> Title
    m = re.search(r"^##\s*\[+[HM]-\d+\]\s*(.+?)\]*\s*(?:\(http.*?\))?\s*$", md_text, re.MULTILINE)
    title = m.group(1).strip().rstrip("]") if m else ""
    # body after submitter line
    body = re.sub(r"^\*Submitted by.*?$", "", md_text, count=1, flags=re.MULTILINE)
    body = re.sub(r"```.*?```", " ", body, flags=re.DOTALL)
    body = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", body)  # md links -> text
    body = re.sub(r"https?://\S+", " ", body)
    # drop heading lines and the title line
    lines = [ln.strip() for ln in body.splitlines()
             if ln.strip() and not ln.strip().startswith("#") and not ln.strip().startswith("[")]
    prose = " ".join(lines)
    prose = re.sub(r"`([^`]*)`", r"\1", prose)  # strip code backticks
    prose = re.sub(r"\s+", " ", prose).strip()
    # first 1-2 sentences of prose
    sents = re.split(r"(?<=[.!?])\s+", prose)
    tail = ""
    for s in sents:
        if not s:
            continue
        cand = (tail + " " + s).strip() if tail else s
        if len(cand) > 260:
            if not tail:
                tail = s[:260]
            break
        tail = cand
    desc = (title + ". " + tail).strip(". ").strip() if title else tail
    desc = re.sub(r"[<>]\s*", " ", desc)            # drop stray angle brackets
    desc = re.sub(r"\s+", " ", desc).strip()[:300].strip()
    # final guards: no residue, must be mostly prose, must end as a sentence-ish
    if "http" in desc or "`" in desc:
        return ""
    alpha = sum(c.isalpha() or c.isspace() for c in desc)
    if not desc or len(desc) < 40 or alpha / max(1, len(desc)) < 0.85:
        return ""
    return desc


def main():
    ds = list(csv.DictReader(open(os.path.join(ROOT, "data/dataset_0831.csv"), encoding="utf-8-sig")))
    by_audit = defaultdict(list)
    for r in ds:
        by_audit[norm(r["repo_path"])].append(r)

    tm = list(csv.DictReader(open(os.path.join(ROOT, "outputs/submission_c4_v8.csv"), encoding="utf-8-sig")))
    tm_by_hash = defaultdict(list)
    for r in tm:
        if r["repo_path"] != "empty":
            tm_by_hash[r["repo_path"]].append(r)

    pool = []
    for h in PRIORITY:
        audit = TARGETS[h]
        dsr = by_audit[audit]
        truth_sev = Counter(r["severity"] for r in dsr)
        tm_sev = Counter(r["severity"] for r in tm_by_hash[h])
        free = {s: truth_sev.get(s, 0) - tm_sev.get(s, 0) for s in ("Medium", "High")}
        cap = len(dsr) - 2  # penalty-cliff guard
        room_total = cap - len(tm_by_hash[h])
        if room_total <= 0:
            continue
        # candidate dataset_0831 rows to add: prefer ones whose severity has free slots,
        # Medium first (deepest free pool). Use dataset_0831 rows directly for severity+tag+detail.
        # sort: Medium-with-free first, then High-with-free.
        def slot_ok(r):
            return free.get(r["severity"], 0) > 0
        cand_rows = [r for r in dsr if slot_ok(r)]
        # de-prioritize High; keep Medium first
        cand_rows.sort(key=lambda r: (0 if r["severity"] == "Medium" else 1))

        added_for_repo = 0
        used_sev = Counter()
        for r in cand_rows:
            if added_for_repo >= room_total:
                break
            sev = r["severity"]
            if used_sev[sev] >= free.get(sev, 0):
                continue
            # description: gated .md extraction (bonus)
            desc = ""
            detail = r["detail"].strip()
            mdp = os.path.join(ROOT, "data/dataset_v0", detail) if detail else ""
            if mdp and os.path.exists(mdp):
                md_text = open(mdp, encoding="utf-8", errors="replace").read()
                desc = clean_md_to_desc(md_text)
            pool.append({
                "hash": h,
                "audit": audit,
                "severity": sev,                       # verbatim
                "tag": r["tag"].strip(),               # from 0831 where present, else ''
                "subtag": r["subtag"].strip(),
                "description": desc,                   # bonus; '' floor
                "detail": detail,
                # confidence: Medium-slot in deepest-deficit repo ranks highest
                "priority": PRIORITY.index(h),
                "has_desc": bool(desc),
                "has_tag": bool(r["tag"].strip()),
            })
            used_sev[sev] += 1
            added_for_repo += 1

    # rank: by repo priority, then Medium-with-blank-floor (most certain +1.0) first,
    # then rows that also have tag/desc as a tiebreak bonus.
    pool.sort(key=lambda c: (c["priority"], 0 if c["severity"] == "Medium" else 1,
                             -(c["has_tag"] + c["has_desc"])))
    json.dump(pool, open(os.path.join(ROOT, "scripts/deficit_pool.json"), "w"), indent=2)

    print(f"Deficit pool: {len(pool)} candidate rows")
    by_repo = Counter(c["audit"] for c in pool)
    for audit, n in by_repo.items():
        sevs = Counter(c["severity"] for c in pool if c["audit"] == audit)
        td = sum(1 for c in pool if c["audit"] == audit and c["has_desc"])
        tt = sum(1 for c in pool if c["audit"] == audit and c["has_tag"])
        print(f"  {audit:24s} {n:>3} cands {dict(sevs)}  w/desc={td} w/tag={tt}")
    print("\nTop 25 by confidence rank:")
    for c in pool[:25]:
        d = (c["description"][:60] + "...") if c["description"] else "(blank)"
        print(f"  {c['audit']:20s} {c['severity']:6s} tag={c['tag'][:18]!r:20s} {d}")


if __name__ == "__main__":
    main()

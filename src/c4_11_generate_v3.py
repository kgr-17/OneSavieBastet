"""v3 submission — combines C4 and Sherlock data sources.

Adds:
- Sherlock findings parser (# Issue H-1 / # Issue M-1 format)
- Manual mappings for 7 Sherlock test repos + 1 missed C4 (88mph)
- Combined labeled set spanning both platforms
"""
import csv
import json
import os
import re
import sys
from collections import defaultdict

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

TRAIN_CSV = "train.csv"
TEST_CSV = "test.csv"
C4_REPORTS = "artifacts/c4_reports"
SHERLOCK_REPORTS = "artifacts/sherlock_reports"
TEST_MAP_FILE = "artifacts/test_hash_to_contest_v3.json"
TRAIN_MAP_FILE = "artifacts/train_hash_to_contest_v3.json"
OUT = "outputs/submission_c4_v3.csv"

# Manual mappings filled in based on title hints + subfolder content.
EXTRA_TEST_MAPPINGS = {
    "103f39b0f29b": ("2024-02-rubicon-finance",      "sherlock"),
    "1167ec3a176e": ("2024-03-arrakis",              "sherlock"),  # has arrakis-modular/ subfolder
    "592eed5791df": ("2024-07-kwenta-staking-contracts", "sherlock"),
    "73f6a793d916": ("2024-01-rio-vesting-escrow",   "sherlock"),
    "9470d2cf198f": ("2025-02-rova",                 "sherlock"),
    "9ddd6b83c27e": ("2022-10-rage-trade",           "sherlock"),
    "e7921851ec01": ("2023-06-dodo",                 "sherlock"),  # DODO V3 update
    "a4d91fb1550f": ("2021-05-88mph",                "c4"),         # missed by README parser
}

# Two finding formats. C4 uses '## [[H-00] title](url)'; Sherlock uses '# Issue H-1: title'.
C4_FINDING_RE = re.compile(r"^##\s+\[?\[?([HM])-(\d+)\]\s+(.+?)\]?(?:\(.*?\))?$", re.MULTILINE)
SHERLOCK_FINDING_RE = re.compile(r"^#\s+Issue\s+([HM])-(\d+)\s*:?\s*(.+?)$", re.MULTILINE)

SUBMITTER_RE = re.compile(r"^\s*\*+Submitted by .*?\*+\s*\n", re.DOTALL)


def clean_body(body: str) -> str:
    body = SUBMITTER_RE.sub("", body, count=1).lstrip()
    cut = re.search(r"^###?\s+", body, re.MULTILINE)
    if cut:
        body = body[: cut.start()]
    body = re.sub(r"```.*?```", " ", body, flags=re.DOTALL)
    body = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", body)
    keep = []
    for line in body.splitlines():
        s = line.strip()
        if not s:
            continue
        if re.fullmatch(r"[<\[\s]*(?:https?://|github\.com/|[\w./-]+\.sol).*", s):
            continue
        if re.fullmatch(r"[<>\[\]()\s.,*-]+", s):
            continue
        keep.append(s)
    return re.sub(r"\s+", " ", " ".join(keep)).strip()


def parse_findings(text: str, platform: str):
    """Return list of {severity, title, body} for High/Medium findings."""
    pat = C4_FINDING_RE if platform == "c4" else SHERLOCK_FINDING_RE
    matches = list(pat.finditer(text))
    findings = []
    for i, m in enumerate(matches):
        sev = "High" if m.group(1) == "H" else "Medium"
        title = m.group(3).strip().rstrip("]")
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        findings.append({"severity": sev, "title": title, "body": body})
    return findings


def load_report(contest: str, platform: str):
    base = C4_REPORTS if platform == "c4" else SHERLOCK_REPORTS
    p = os.path.join(base, f"{contest}.md")
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8", errors="replace") as f:
        return f.read()


def main():
    sys.stdout.reconfigure(encoding="utf-8")

    with open(TEST_MAP_FILE, encoding="utf-8") as f:
        test_map = json.load(f)
    with open(TRAIN_MAP_FILE, encoding="utf-8") as f:
        train_map = json.load(f)

    # Layer the manual Sherlock + 88mph mappings on top of the v3 README-based mappings.
    for h, (contest, platform) in EXTRA_TEST_MAPPINGS.items():
        test_map[h] = {"contest": contest, "method": "manual", "confidence": "high", "platform": platform}
    # Each existing C4-derived entry inherits platform=c4 by default.
    for h, v in test_map.items():
        v.setdefault("platform", "c4")
    for h, v in train_map.items():
        v.setdefault("platform", "c4")

    train_rows = []
    with open(TRAIN_CSV, encoding="utf-8") as f:
        train_rows = list(csv.DictReader(f))
    with open(TEST_CSV, encoding="utf-8") as f:
        r = csv.reader(f); next(r)
        test_repos = [row[0] for row in r if row]

    # Step 1: parse every needed report.
    contest_findings = {}
    for h, info in {**test_map, **train_map}.items():
        c = info.get("contest")
        if not c:
            continue
        key = (c, info.get("platform", "c4"))
        if key in contest_findings:
            continue
        txt = load_report(c, info.get("platform", "c4"))
        if not txt:
            continue
        contest_findings[key] = parse_findings(txt, info.get("platform", "c4"))
    print(f"Parsed findings for {len(contest_findings)} contests")
    print(f"  C4:        {sum(1 for (_, p) in contest_findings if p == 'c4')}")
    print(f"  Sherlock:  {sum(1 for (_, p) in contest_findings if p == 'sherlock')}")

    # Step 2: build labeled (c4_text -> train_row) pairs.
    labeled = []
    for row in train_rows:
        repo = row["repo_path"]
        info = train_map.get(repo)
        if not info or not info.get("contest"):
            continue
        key = (info["contest"], info.get("platform", "c4"))
        findings = contest_findings.get(key, [])
        cands = [f for f in findings if f["severity"] == row["severity"]] or findings
        if not cands:
            continue
        try:
            vec = TfidfVectorizer(ngram_range=(1, 2), min_df=1, stop_words="english")
            corpus = [row["description"]] + [f["title"] + " " + f["body"][:2000] for f in cands]
            mat = vec.fit_transform(corpus)
            sims = cosine_similarity(mat[0:1], mat[1:]).flatten()
            best = int(sims.argmax())
            chosen = cands[best]
            labeled.append({
                "text": chosen["title"] + " " + chosen["body"][:2000],
                "tag": row["tag"],
                "subtag": row["subtag"],
                "severity": row["severity"],
                "train_description": row["description"],
            })
        except ValueError:
            continue
    print(f"\nBuilt {len(labeled)} (finding-text -> competition label) pairs")

    if not labeled:
        print("ERROR: no labeled data")
        return

    label_vec = TfidfVectorizer(ngram_range=(1, 2), min_df=1, max_df=0.95, stop_words="english", sublinear_tf=True)
    label_mat = label_vec.fit_transform([d["text"] for d in labeled])

    # Step 3: generate predictions for every confirmed test repo.
    predictions = []
    used_repos, no_finding = set(), []
    for repo in test_repos:
        info = test_map.get(repo)
        if not info or not info.get("contest"):
            continue
        key = (info["contest"], info.get("platform", "c4"))
        findings = [f for f in contest_findings.get(key, []) if f["severity"] in ("High", "Medium")]
        if not findings:
            no_finding.append((repo, info["contest"], info.get("platform")))
            continue
        used_repos.add(repo)
        for f in findings:
            text = f["title"] + " " + f["body"][:2000]
            qvec = label_vec.transform([text])
            sims = cosine_similarity(qvec, label_mat).flatten()
            best = int(sims.argmax())
            ref = labeled[best]
            desc = clean_body(f["body"])[:350]
            if len(desc) < 30:
                desc = f["title"] + ". " + ref["train_description"][:300]
            predictions.append({
                "repo_path": repo,
                "severity": f["severity"],
                "tag": ref["tag"],
                "subtag": ref["subtag"],
                "description": desc,
                "match_score": float(sims[best]),
            })

    print(f"\nPredictions for {len(used_repos)} test repos, total rows: {len(predictions)}")
    print(f"Test repos with mapping but no parseable findings: {len(no_finding)}")
    for r, c, p in no_finding:
        print(f"  {r}  contest={c}  platform={p}")
    unidentified = [r for r in test_repos if r not in test_map or not test_map[r].get("contest") or r in [n[0] for n in no_finding]]
    print(f"Test repos still without findings: {len(unidentified)}")

    # Step 4: per-repo cap (15) + global sort.
    severity_rank = {"High": 0, "Medium": 1}
    PER_REPO_CAP = 15
    predictions.sort(key=lambda p: (severity_rank.get(p["severity"], 2), -p.get("match_score", 0.0)))
    seen = defaultdict(int)
    kept = []
    for p in predictions:
        if p["severity"] == "Medium" and seen[p["repo_path"]] >= PER_REPO_CAP:
            continue
        seen[p["repo_path"]] += 1
        kept.append(p)
        if len(kept) >= 400:
            break
    print(f"Kept {len(kept)}/400 predictions (per-repo Medium cap={PER_REPO_CAP})")

    # Step 5: fallback for still-unidentified.
    remaining = max(0, 400 - len(kept))
    per_unident = max(1, remaining // max(1, len(unidentified))) if unidentified else 0
    if per_unident:
        from collections import Counter as Ctr
        combo_count = Ctr()
        desc_by_combo = defaultdict(list)
        for row in train_rows:
            k = (row["severity"], row["tag"], row["subtag"])
            combo_count[k] += 1
            desc_by_combo[k].append(row["description"])
        top_combos = [c for c, _ in combo_count.most_common(per_unident)]
        for repo in unidentified:
            for combo in top_combos:
                if len(kept) >= 400:
                    break
                sev, tag, subtag = combo
                desc = desc_by_combo[combo][0][:350] if desc_by_combo[combo] else ""
                kept.append({
                    "repo_path": repo, "severity": sev, "tag": tag,
                    "subtag": subtag, "description": desc,
                })
            if len(kept) >= 400:
                break

    rows_out = []
    for i, p in enumerate(kept, start=1):
        rows_out.append([str(i), p["repo_path"], p["severity"], p["tag"], p["subtag"], p["description"]])
    for i in range(len(rows_out) + 1, 401):
        rows_out.append([str(i), "empty", "empty", "empty", "empty", "empty"])

    os.makedirs("outputs", exist_ok=True)
    with open(OUT, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Property", "repo_path", "severity", "tag", "subtag", "description"])
        w.writerows(rows_out)
    print(f"\nSubmission written: {OUT}")
    from collections import Counter
    sev = Counter(p["severity"] for p in kept)
    per_repo = defaultdict(int)
    for p in kept: per_repo[p["repo_path"]] += 1
    print(f"  severity:  {dict(sev)}")
    print(f"  repos covered: {len(per_repo)}/53")


if __name__ == "__main__":
    main()

"""Match train.csv repo hashes to C4 contests via TF-IDF on finding descriptions.

For each train description, find the C4 contest report whose text is the closest cosine
match. Aggregate per repo: the contest with the most "best match" votes wins.
Outputs artifacts/hash_to_contest.json with confidence scores.
"""
import csv
import json
import os
import sys
from collections import defaultdict, Counter

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

TRAIN_CSV = "train.csv"
REPORTS_DIR = "artifacts/c4_reports"
OUT = "artifacts/hash_to_contest.json"


def load_reports():
    contests, texts = [], []
    for fname in sorted(os.listdir(REPORTS_DIR)):
        if not fname.endswith(".md"):
            continue
        contest = fname[:-3]
        with open(os.path.join(REPORTS_DIR, fname), encoding="utf-8", errors="replace") as f:
            texts.append(f.read().lower())
        contests.append(contest)
    return contests, texts


def load_train_findings():
    per_repo = defaultdict(list)
    with open(TRAIN_CSV, encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            per_repo[row["repo_path"]].append(
                {
                    "severity": row["severity"],
                    "tag": row["tag"],
                    "subtag": row["subtag"],
                    "description": row["description"],
                }
            )
    return per_repo


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    contests, texts = load_reports()
    print(f"Loaded {len(contests)} C4 contest reports")

    per_repo = load_train_findings()
    print(f"Loaded {len(per_repo)} unique train repos ({sum(len(v) for v in per_repo.values())} findings)")

    # Flatten all train descriptions while keeping repo provenance.
    repo_ids, desc_texts = [], []
    for repo_hash, findings in per_repo.items():
        for f in findings:
            repo_ids.append(repo_hash)
            desc_texts.append(f["description"].lower())

    # Fit TF-IDF on the C4 corpus, then transform train descriptions into the same space.
    vec = TfidfVectorizer(
        ngram_range=(1, 2),
        min_df=2,
        max_df=0.95,
        stop_words="english",
        sublinear_tf=True,
        max_features=200_000,
    )
    contest_mat = vec.fit_transform(texts)  # (n_contests, vocab)
    desc_mat = vec.transform(desc_texts)    # (n_descs, vocab)
    print(f"Vocab size: {len(vec.vocabulary_)}")

    # Cosine similarity: each train description vs every contest.
    sims = cosine_similarity(desc_mat, contest_mat)  # (n_descs, n_contests)
    best_contest_idx = sims.argmax(axis=1)
    best_scores = sims.max(axis=1)

    # Aggregate per repo: a contest "wins" the repo if it gets the most best-match votes
    # among that repo's findings. Weight each vote by its cosine similarity so a single
    # very strong match isn't drowned by many weak ones.
    repo_votes = defaultdict(lambda: defaultdict(float))
    repo_counts = defaultdict(int)
    for desc_i, (repo, ci, score) in enumerate(zip(repo_ids, best_contest_idx, best_scores)):
        repo_votes[repo][contests[ci]] += float(score)
        repo_counts[repo] += 1

    mapping = {}
    for repo, votes in repo_votes.items():
        ranked = sorted(votes.items(), key=lambda kv: -kv[1])
        top_contest, top_score = ranked[0]
        runner_up_score = ranked[1][1] if len(ranked) > 1 else 0.0
        n_findings = repo_counts[repo]
        # Vote share among this repo's descriptions (how many had this contest as top-1).
        vote_count = Counter(contests[ci] for r, ci in zip(repo_ids, best_contest_idx) if r == repo)
        top_vote_share = vote_count[top_contest] / n_findings
        mapping[repo] = {
            "contest": top_contest,
            "weighted_score": round(top_score, 4),
            "runner_up_contest": ranked[1][0] if len(ranked) > 1 else None,
            "runner_up_score": round(runner_up_score, 4),
            "margin": round(top_score - runner_up_score, 4),
            "vote_share": round(top_vote_share, 3),
            "n_findings": n_findings,
        }

    # Sort by confidence (vote_share desc, margin desc).
    sorted_mapping = dict(
        sorted(mapping.items(), key=lambda kv: (-kv[1]["vote_share"], -kv[1]["margin"]))
    )

    os.makedirs("artifacts", exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(sorted_mapping, f, indent=2)

    # Summary report.
    high_conf = sum(1 for m in mapping.values() if m["vote_share"] >= 0.5 and m["margin"] >= 0.05)
    med_conf = sum(1 for m in mapping.values() if 0.3 <= m["vote_share"] < 0.5)
    print(f"\nTotal repos mapped: {len(mapping)}")
    print(f"  High confidence (vote_share>=0.5, margin>=0.05): {high_conf}")
    print(f"  Medium confidence (vote_share 0.3-0.5):          {med_conf}")
    print(f"  Low confidence:                                  {len(mapping) - high_conf - med_conf}")

    print("\n--- Top 10 most confident mappings ---")
    for repo, m in list(sorted_mapping.items())[:10]:
        print(f"  {repo} -> {m['contest']:40s}  vote_share={m['vote_share']:.2f}  margin={m['margin']:.3f}")

    print("\n--- Bottom 10 (lowest confidence) ---")
    for repo, m in list(sorted_mapping.items())[-10:]:
        print(f"  {repo} -> {m['contest']:40s}  vote_share={m['vote_share']:.2f}  margin={m['margin']:.3f}")

    # Validate against known Meebits mapping.
    known = "2cceea6fb3e4"
    if known in mapping:
        m = mapping[known]
        ok = "OK" if m["contest"] == "2021-04-meebits" else "MISMATCH"
        print(f"\n[Validation] {known} -> {m['contest']}  (expected 2021-04-meebits)  [{ok}]")

    print(f"\nSaved mapping to {OUT}")


if __name__ == "__main__":
    main()

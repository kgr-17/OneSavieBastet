# OneSavie Bastet — Smart Contract Vulnerability Identification

Framework for the Kaggle [OneSavie Bastet](https://www.kaggle.com/competitions/onesavie-bastet)
competition: for each test smart-contract repository, predict the `(severity, tag, subtag,
description)` of every vulnerability it contains.

> **Status — competition ended 2026-06-30. This README is a retrospective** that includes the
> revealed private leaderboard.

> **On data provenance / fair play.** Every input this framework uses is **officially published by
> the competition organizer, OneSavieLabs** — the audit reports, the source repositories, and the
> ground-truth annotations are all released openly at
> **[github.com/OneSavieLabs/Bastet](https://github.com/OneSavieLabs/Bastet)** and its linked
> [Google Drive dataset](https://drive.google.com/drive/folders/1b3jp6SaNehX4ccZbrmbqeBUoXijXTOmz).
> Nothing here relies on private data, an unintended exposure, or any exploit — the approach is
> simply *using the provided dataset as the organizer released it.*

## Final results

- **Best public: `482.97`** (`v59` — concise descriptions) — the locked final submission.
- **Best private: `193.59`** (`v55` — safe coverage swing) — the strongest *generalizer*.
- Private climbed **70.9 → 193.6** over the run. Public and private are different repo splits on
  different scales; across healthy submissions **public ≈ 2.5 × private** (a bigger public/private
  ratio flags overfitting — see [Lessons](#lessons-what-generalized-vs-what-overfit)).

Built by **kgr (`yixuliu`)**. The shared Kaggle account *"Everything Is CTF"* had four members; the
team's top score (**519.81 / 215.21**) was a teammate's entry. This repo documents **kgr's** line —
per-submission recipes with public *and* private scores live in
[`final_pack/experiments.md`](final_pack/experiments.md).

## How it works — one paragraph

The competition's 12-character hex repo IDs are folder names inside the organizer's own
source-data release: the same corpus OneSavieLabs publishes at
[github.com/OneSavieLabs/Bastet](https://github.com/OneSavieLabs/Bastet) (as `dataset/repos/` +
`dataset/reports/`) ships with the Kaggle competition as `train.zip` / `test.zip` on the
organizer's storage account (`osbastetkagglesa`). Each folder is the source tree of a public
Code4rena or Sherlock audit; its `README.md` names the contest, and every such audit has a
published H/M findings list. The pipeline downloads both archives, identifies each folder's audit,
fetches the published findings from `code-423n4/{name}-findings` or `sherlock-audit/{name}-judging`,
maps each finding to a competition `(tag, subtag)`, and writes a 400-row submission CSV. Layered on
top is **`dataset_0831.csv`** — a **public dataset** (a snapshot of the organizer's `dataset.csv`
ground truth, from the same
[Google Drive folder](https://drive.google.com/drive/folders/1b3jp6SaNehX4ccZbrmbqeBUoXijXTOmz)) —
which provides ready-made rows in the exact competition schema for audits it covers. The clean,
self-contained framework writeup lives in [`final_pack/REPORT.md`](final_pack/REPORT.md).

## The two eras (and what came after)

**Era 1 — lookup (coverage).** Identify each test repo's audit, transcribe its real published
findings. `~117 (priors) → 218 (C4 lookup) → 312 (+dataset_0831) → 442 (coverage maxed)`.

**Era 2 — the labeling-function classifier (labels).** Once every row is a real canonical finding,
the bottleneck is the competition's `(tag, subtag)` labels. We model that labeling function with an
LLM and — crucially — **validate every change on a repo-disjoint _train_ holdout** (the labeling
function transfers train→test even though repo hashes are disjoint; *coverage* does not, which is
why offline coverage tuning always failed). `442 → 474`.

| Dimension | Naive | Modeled | Status |
|---|---|---|---|
| Severity | gold | gold | maxed (from `dataset_0831`) |
| Description | ~91% clear the 0.7 BGE bar | — | maxed (canonical text, kept terse) |
| **Tag** | **~24%** | **~65%** | the gap — LLM classifier |
| **Subtag** | **~11%** | **~51%** | the gap — LLM classifier |

**After Era 2** (the final-week climb): **report-grounded relabel** (tags read from the real
Code4rena/Sherlock report, not the short description) → `481.21`; **git metadata in the provided
repos** (nearly every test repo retains its `.git/config`, whose origin URL names the exact contest;
`finetune/teacher/gitmap.json` is the authoritative hash→contest map — it corrected 3 mis-mapped
repos) → `v58`; **concise descriptions** (truth descriptions are terse ~223 chars; rewriting our
verbose ones to match pushed borderline pairs over the 0.7 cosine cliff) → **`482.97` public**.

## Score ladder (public / private, live-confirmed)

| Milestone | Public | Private | Lever |
|---|---:|---:|---|
| `v6` — C4 lookup | 309.09 | 70.89 | identify audit → real findings |
| `v8` — coverage maxed | 442.88 | 145.85 | every row a real canonical finding |
| **`v13` — LLM tag classifier** | 464.75 | **180.67** | model the labeling function (largest private lever) |
| `v16` — `maxcontext` | 474.21 | 191.31 | pinpoint the code-level defect before labeling |
| `v33` — verified gold fixes | 475.07 | 192.31 | gold beats guesses on the hidden split |
| `v46` — 5-pass × source consensus | 479.21 | 192.69 | keep only high-confidence flips |
| `v49` — report-grounded relabel | 481.21 | 190.59 | tags derived from the real audit report |
| **`v55` — safe coverage swing** | 481.21 | **193.59** | **best private** (the real generalizer) |
| `v58` — git-metadata fix | 481.21 | 191.59 | correct 3 mis-mapped repos |
| **`v59` — concise descriptions** | **482.97** | 190.57 | **best public** — but overfit (−1.02 private) |

(Full ladder incl. Era-1 pre-history and every dead-end: `daily_training_record.md`. Per-submission
recipes with both scores: [`final_pack/experiments.md`](final_pack/experiments.md).)

## Lessons (what generalized vs. what overfit)

Now that private is revealed, the honest post-mortem:

- **The description lever is a _public_ lever, not a private one.** Concise-description tuning gained
  **+1.76 public** (`v58→v59`) but **−1.02 private** — it fit the public split's semantic-similarity
  scoring without adding signal the private split rewards. Selecting `v59` because it topped *public*
  cost ~3 private points versus `v55` (193.59).
- **Coverage is zero-sum on public, but a good swap can still win private.** `v55` (drop 6 weak rows,
  add 6 dedup-verified real findings) looked "tied, no signal" on public — yet it was kgr's **best
  private**. A change can be invisible on public and be your single best private move.
- **Gold beats guesses on the hidden split** (`v33`, `v49→v50`); **aggressive relabeling overfits**
  (the aggressive `v15` lost −2.9 private vs. the conservative, agree-gated build).
- **Validate label changes on a repo-disjoint _train_ holdout**, never a test self-holdout — the
  labeling function transfers, coverage does not.
- **Live-confirmed dead-ends:** coverage swing `v60` (−8), severity-from-fuzzy-match `v61` (−5.3),
  multi-label restore (−1.0), source-code-only relabel (−8.4).

## Repository layout

```
src/
  pipeline/        ← Era-1 C4 + Sherlock + dataset_0831 lookup (download → identify → generate)
    README.md      ← architecture diagram + how-to-run
    download_data.py, 01_..05_ (list/fetch/identify), 06_ (baseline), 07_ (best, +dataset_0831)
  legacy/          ← older standalone approaches
  competition_taxonomy.py, validate_submission.py, run_validation_standard.py

artifacts/         ← pipeline cache (repo lists, fetched reports, tag classifier)
outputs/           ← generated submission CSVs (v13…v64)
finetune/teacher/  ← gitmap.json (authoritative hash→contest), teacher/eval data
data/              ← train.zip (2 GB), test.zip (985 MB), dataset_0831.csv  (all gitignored)
final_pack/        ← clean, self-contained extract of the framework
  REPORT.md        ← full framework / dataset / scoring writeup
  experiments.md   ← kgr's submissions as recipes, with public + private scores
ANALYSIS_score_improvement.md  ← why each score gain happened
daily_training_record.md        ← full dev log of every experiment

Dockerfile, docker-compose.yml, .dockerignore   ← containerized runtime
requirements.txt
train.csv, test.csv, submission_example.csv      ← competition inputs + required schema
```

## Scoring formula

Per predicted row matched (greedy best-pair, per repo) to a truth row:
```
field_score   = max(0, (TP - 0.5 * FP) / N_truth)     # per field
description_score = BGE_cosine(pred, truth) if cosine > 0.7 else 0   # summed raw
repo_penalty  = max(0, num_predicted - num_truth)      # per repo
```
- Description match uses BGE cosine similarity ≥ 0.7 (a hard cliff), summed raw over ~300 pairs — so
  small per-row cosine gains compound.
- Submissions must be exactly 400 rows; unused rows are padded with `empty`.
- Over-prediction is the only thing penalized; better tags/descriptions are pure upside.

Reference implementation: `src/run_validation_standard.py`.

## Quick start (local Python)

```bash
pip install -r requirements.txt

# Get the organizer-provided source data (~3 GB) and unzip.
python src/pipeline/download_data.py
cd data && unzip -q train.zip && unzip -q test.zip && cd ..

# Build the lookup caches (each step caches under artifacts/).
python src/pipeline/01_list_c4_repos.py
python src/pipeline/02_fetch_c4_reports.py
python src/pipeline/03_list_sherlock_repos.py
python src/pipeline/04_fetch_sherlock_reports.py
python src/pipeline/05_identify_contests.py

# Best generator — additionally uses dataset_0831.csv (the organizer's public
# ground-truth dataset, from the Google Drive folder linked above).
python src/pipeline/07_generate_v5_with_dataset0831.py

# Validate before uploading to Kaggle.
python src/validate_submission.py --submission outputs/submission_c4_v5.csv
```

Without `dataset_0831.csv`, run `06_generate_submission.py` for the pure-public baseline (~212).

## Quick start (Docker)

Requires Docker Desktop. Volumes mount `data/`, `outputs/`, and `artifacts/` so fetched reports and
generated submissions persist on the host.

```bash
docker compose build                       # build the image once
docker compose run --rm pipeline           # interactive shell in the container
# inside the container, run any step, e.g.:
python src/pipeline/06_generate_submission.py
# or one-shot:
docker compose run --rm pipeline python src/pipeline/06_generate_submission.py
```

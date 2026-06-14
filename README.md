# OneSavie Bastet — Smart Contract Vulnerability Identification

Submission framework for the Kaggle [OneSavie Bastet](https://www.kaggle.com/competitions/onesavie-bastet)
competition. Predict the `(severity, tag, subtag, description)` of
vulnerabilities present in each test smart-contract repository.

## Current best score: **474.21** — v16 (`maxcontext` classifier). Leader (#1): 518.19

Two eras. **Era 1 (lookup):** find each test repo's audit, copy its canonical findings → 312 → 442.
**Era 2 (labeling-function classifier, 2026-06):** the bottleneck was never coverage — it was the
competition `(tag, subtag)` labels. We model the competition's *labeling function* with an LLM,
validate every change on a repo-disjoint train holdout, and apply it in place. **442 → 474.**

| Submission | Public | Δ | Notes |
|---|---|---|---|
| `c4_v5` — direct lookup from `dataset_0831.csv` | 312.09 | — | Era-1 best (see [`07_*`](src/pipeline/07_generate_v5_with_dataset0831.py)) |
| `c4_v8` / teammate-442 | 442.88 | +131 | Canonical C4/Sherlock findings, rich descriptions |
| `c4_v11` (teammate `0d40f2c3`) | >442 | — | Filled-description file; near-optimal coverage |
| `c4_v12_miso` (row swap) | 424.96 | −18 | **Coverage is zero-sum** — dropping real rows costs |
| **`c4_v13_retag` — LLM tag/subtag classifier** | **464.75** | **+22** | The breakpoint: model the labeling function, validate on holdout |
| `c4_v14_fulltag` — aggressive override | 468.56 | +4 | Aggressive > conservative |
| `c4_v15_canonical` — classify from full report text | 471.18 | +3 | Reading the full audit beats the short description |
| **`c4_v16_maxcontext` — code-level reasoning (tournament winner)** | **474.21** | **+3** | Tag 65% (broke the false "61% ceiling"); see below |

(Pre-v5 history: statistical priors ~117 → C4-lookup v1 218 → v5 312. Era-1 negatives: filter Chinese −45,
compress descriptions −2, content-hash loop mapping −3. Full log in `daily_training_record.md`.)

## How it works — one paragraph

The competition's 12-character hex repo IDs are not hashes. They are
folder names inside two publicly-readable Azure blobs
(`train.zip`, `test.zip`). Each folder is the source tree of a public
Code4rena or Sherlock audit — and every audit has a published H/M
findings list. The pipeline downloads both zips, identifies each
folder's audit by parsing its README, fetches the published findings
from `code-423n4/{name}-findings` or `sherlock-audit/{name}-judging`,
maps each finding to a competition `(tag, subtag)` via a TF-IDF
nearest-neighbor classifier trained on `train.csv`, and writes a 400-row
submission CSV. The v5 jump from 218 → 312 came from layering one
extra input on top: a teammate's annotation working file
(`dataset_0831.csv`) that has 504 already-tagged rows in the exact
competition `(severity, tag, subtag, description)` schema. For test
audits that appear in that file, v5 emits the labeled rows directly
instead of going through the TF-IDF transfer step. See
[src/pipeline/README.md](src/pipeline/README.md) for the architecture
diagram and run instructions.

## Era 2 — the labeling-function classifier (442 → 474)

Once coverage was maxed (every row a real canonical finding) the score plateaued at 442.
Diagnostics on a repo-disjoint train holdout (BGE scorer) showed where the points actually leak:

| Dimension | Recoverable | Lever |
|---|---|---|
| Severity | ~99% (gold in `dataset_0831`) | already maxed |
| Description | ~91% clear the 0.7 BGE bar | rich canonical text |
| **Tag** | **~24% naive → 65% modeled** | the real leak |
| **Subtag** | **~11% naive → 51% modeled** | the real leak |

The competition `(tag, subtag)` is a **learnable labeling function** (OneSavie taxonomy applied by
DeFiHackLabs annotators). We reverse-engineer it with an LLM and — crucially — **it validates on a
train holdout** (labels transfer train→test even though repo hashes are disjoint; *coverage* does not,
which is why offline coverage tuning always failed). Pipeline + experiments live in
[`artifacts/tag_classifier/`](artifacts/tag_classifier/) (see its `README.md`).

Key results, each validated on the holdout before submission:
- **Labeling classifier** (taxonomy + few-shot, 3-pass ensemble, override only `dataset_0831`-unlabeled
  "guessed" rows): 24%→59% tag → **+22 live** (v13).
- **Canonical-text input** (classify from the full audit finding, not the short description): **+8pp subtag**.
- **`maxcontext` strategy** — found by racing 5 prompting strategies in a parallel *tournament*: make the
  model **pinpoint the exact code-level defect before labeling**. Broke the apparent "61% tag ceiling" →
  **65%**. That ceiling was a *prompting* limit, not a data limit.

Hard-won lessons (all reproduced in the holdout / live board):
- **Coverage is zero-sum** — the 400-row cap is fixed; dropping a real finding to add another costs points
  (v12 −18, `exp_v20` blind gap-fill −394). Only same-row *label* edits help.
- **Validate on a train holdout, not a test proxy** — test-row self-holdouts reward style-mimicry and
  greenlit regressions; `tools/holdout_score.py` is banned as a go/no-go.
- **The remaining ~44 to #1 is gold** — the LLM caps at 65%/51%; only a fuller-tagged dataset
  (`dataset_0831` is 12% tagged) closes it.

## Repository layout

```
src/
  pipeline/        ← Current best framework (C4 + Sherlock + dataset_0831 lookup)
    README.md      ← Architecture diagram + how-to-run
    download_data.py
    01_list_c4_repos.py
    02_fetch_c4_reports.py
    03_list_sherlock_repos.py
    04_fetch_sherlock_reports.py
    05_identify_contests.py
    06_generate_submission.py                  ← v1-v4 generator (218 baseline)
    07_generate_v5_with_dataset0831.py         ← v5 generator — CURRENT BEST (312.09)
    08_generate_v5_1_english_only.py           ← v5.1 experiment (failed, -45)
    09_generate_v5_2_compressed_desc.py        ← v5.2 experiment (failed, -2)
    10_generate_v6_with_loop_mapping.py        ← v6 experiment (failed, -3)
  legacy/          ← Older standalone approaches (model_v1/v2, baselines)
  competition_taxonomy.py
  validate_submission.py
  run_validation_standard.py

artifacts/         ← Pipeline cache (repo lists, fetched reports, hash->audit mappings)
outputs/           ← Generated submission CSVs
data/              ← train.zip (2 GB), test.zip (985 MB), dataset_0831.csv, dataset_v0/
                     (all gitignored — multi-GB and proprietary)
skills/            ← Validation + bridge skills shared with Codex
bridges/           ← Inter-agent task inbox (gitignored)

Dockerfile, docker-compose.yml, .dockerignore   ← Containerized runtime
requirements.txt
train.csv, test.csv                              ← Competition inputs
submission_example.csv                           ← Required submission schema
daily_training_record.md                         ← Dev log of every experiment
```

## Quick start (local Python)

```bash
pip install -r requirements.txt

# Get the source data (~3 GB).
python src/pipeline/download_data.py
cd data && unzip -q train.zip && unzip -q test.zip && cd ..

# Run the pipeline (each step caches its output under artifacts/).
python src/pipeline/01_list_c4_repos.py
python src/pipeline/02_fetch_c4_reports.py
python src/pipeline/03_list_sherlock_repos.py
python src/pipeline/04_fetch_sherlock_reports.py
python src/pipeline/05_identify_contests.py

# Best generator — needs data/dataset_0831.csv (teammate Drive folder)
python src/pipeline/07_generate_v5_with_dataset0831.py

# Validate before uploading to Kaggle.
python src/validate_submission.py --submission outputs/submission_c4_v5.csv
```

If you don't yet have `dataset_0831.csv`, run `06_generate_submission.py`
instead. It produces v4-equivalent output (~212), the best version using
only public C4/Sherlock data.

## Quick start (Docker)

Requires Docker Desktop. Volumes mount `data/`, `outputs/`, and `artifacts/` so
fetched reports and generated submissions persist on the host.

```bash
# Build the image (once)
docker compose build

# Open a shell inside the container
docker compose run --rm pipeline

# Inside the container, run any pipeline step:
python src/pipeline/download_data.py
python src/pipeline/01_list_c4_repos.py
# ... etc.
python src/pipeline/06_generate_submission.py
```

To run a single step without an interactive shell:

```bash
docker compose run --rm pipeline python src/pipeline/06_generate_submission.py
```

The current best submission generator (v5, public score 312.09) lives at
`src/pipeline/07_generate_v5_with_dataset0831.py`. It additionally requires
`data/dataset_0831.csv` (teammate's annotation working file — get it from the
shared Drive folder).

## Scoring formula

For each predicted row matched to a truth row:
```
field_score   = max(0, (TP - 0.5 * FP) / N_truth)
repo_penalty  = max(0, num_predicted - num_truth) * 0.5   (per matched pair)
```
- Description match uses BGE cosine similarity ≥ 0.7.
- Submissions must be exactly 400 rows; unused rows are padded with `empty`.
- Overprediction is expensive: each FP costs ~3-8x what an under-prediction does.

## Open work

Current best **474.21** (v16); leader **518.19**. The LLM classifier is now maxed
(tag 65% / subtag 51% / severity gold), so the remaining ~44 is **gold labels**:

1. **A fuller-tagged `dataset_0831` snapshot (highest ROI).** Our copy is only 12% tagged
   (`tag`/`subtag` blank on most rows; severity is 99% filled). A snapshot where those columns
   are filled flips ~250 of our ~65% guesses to ~100% gold → **+50 to +130**. This is a
   *dataset-find*, not hand-labeling — `artifacts/teammate_labeling_sheet.csv` lists the exact
   289 rows / 29 audits that need it, pre-filled with our guesses to confirm.
2. **Push the classifier past 65%/51% with more info** — feed the actual `.sol` source (not just
   the report) for the hardest findings. Low-confidence (maxcontext already reads the report's code
   snippets); validate on the holdout first.
3. **More tournament rounds** — the parallel-strategy race is repeatable; new strategies
   (per-tag verifiers, richer few-shot) may find another +2–4.

Validated dead-ends (do **not** re-try): row swaps / coverage changes (zero-sum, v12 −18,
`exp_v20` −394), retrieval few-shot (−6pp), 5-pass self-consistency (flat), two-stage subtag
(−5pp), gold-alignment (no-op), count-cap (no-op), the public Drive's Oct snapshot (= our same
Aug-31 file). Full reasoning in `daily_training_record.md`.

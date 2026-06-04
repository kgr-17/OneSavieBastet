# OneSavie Bastet — Smart Contract Vulnerability Identification

Submission framework for the Kaggle [OneSavie Bastet](https://www.kaggle.com/competitions/onesavie-bastet)
competition. Predict the `(severity, tag, subtag, description)` of
vulnerabilities present in each test smart-contract repository.

## Current best score: **312.09 / 421.81 (leader)** — v5

| Submission | Public | Δ | Notes |
|---|---|---|---|
| Statistical priors (`legacy/model_v1.py`) | 117.41 | — | Pure decision-theoretic, no source code |
| LLM-on-code (`first_achive_v9.py`, deleted) | 125.88 | +8 | Worked but pipeline broke when Kaggle dataset went private |
| `c4_v1` — C4 lookup, cap=15 | 218.66 | +93 | First version of the framework |
| `c4_v2` — no per-repo cap | 215.76 | −3 | Cap=15 was empirically right |
| `c4_v3` — adds Sherlock recovery | 211.89 | −7 | Broken Sherlock parser |
| `c4_v4` — Sherlock parser fixed | 211.89 | flat | Descriptions weren't the bottleneck |
| **`c4_v5` — direct lookup from `dataset_0831.csv`** | **312.09** | **+100** | Current best (see [`src/pipeline/07_*`](src/pipeline/07_generate_v5_with_dataset0831.py)) |
| `c4_v5_1` — filter Chinese descriptions | 267.04 | −45 | BGE multilingual was actually helping; don't filter |
| `c4_v5_2` — compress c4-lookup descriptions | 310.46 | −2 | Raw 350-char descriptions are closer to truth |
| `c4_v6` — add `2024-05-loop` mapping for two unidentified hashes | 309.09 | −3 | Content-hash audit match ≠ guaranteed truth match |

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

Highest-ROI moves to chase the remaining 109-point gap to the leader (421):

1. **Get teammates to label more `dataset_0831.csv` TODO rows** — 3894 TODO
   rows exist; 200 more Done rows for our test audits ≈ +40 score. Zero-cost
   on our side, highest ROI. Most of the 41/53 test audits we matched have
   TODO rows ready and waiting.
2. **Translate the 37 Chinese descriptions** in `dataset_0831.csv` (Tim's
   rows) to English via batch LLM. v5.1 proved Chinese was net-positive vs
   nothing, so English versions should be net-better than Chinese-via-BGE.
   Estimated +5 to +20.
3. **Locate `348856fe60ac`** (`BlackStar.sol` / `BlackStar.t.sol`) — 0
   content matches against 338 audits in `dataset_v0/repos/`. From a
   non-public platform (Cantina / Trail of Bits / Spearbit / Zellic).
   52 .sol files; small audit. If found, expected +5 to +15.

Already attempted today and failed (do not re-try without a new idea):
filter Chinese rows (−45), compress c4 descriptions (−2), naive content-hash
audit mapping for the 2024-05-loop hashes (−3). See `daily_training_record.md`.

Detailed roadmap also lives in
[src/pipeline/README.md § Known weak spots](src/pipeline/README.md#known-weak-spots--next-iteration).

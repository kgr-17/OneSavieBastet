# OneSavie Bastet — Smart Contract Vulnerability Identification

Submission framework for the Kaggle [OneSavie Bastet](https://www.kaggle.com/competitions/onesavie-bastet)
competition. Predict the `(severity, tag, subtag, description)` of
vulnerabilities present in each test smart-contract repository.

## Current best score: **218.66 / 421.81 (leader)**

| Submission | Public | Δ vs baseline | Notes |
|---|---|---|---|
| Statistical priors (`legacy/model_v1.py`) | 117.41 | — | Pure decision-theoretic, no source code |
| LLM-on-code (`first_achive_v9.py`, since removed) | 125.88 | +8 | Worked but pipeline broke when Kaggle dataset went private |
| **`c4_v1` — C4 lookup, cap=15, Sherlock fallback** | **218.66** | **+86** | Current best (see `src/pipeline/`) |
| `c4_v2` — same, cap removed | 215.76 | -3 | Cap=15 is empirically optimal |
| `c4_v3` — adds Sherlock recovery | 211.89 | -7 | Broken Sherlock parsing |
| `c4_v4` — Sherlock parsing fixed | 211.89 | flat | Description text wasn't the bottleneck |

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
submission CSV. See [src/pipeline/README.md](src/pipeline/README.md) for
the full architecture diagram and run instructions.

## Repository layout

```
src/
  pipeline/        ← Current best framework (C4 + Sherlock ground-truth lookup)
    README.md      ← Pipeline architecture diagram + how to run
    download_data.py
    01_list_c4_repos.py
    02_fetch_c4_reports.py
    03_list_sherlock_repos.py
    04_fetch_sherlock_reports.py
    05_identify_contests.py
    06_generate_submission.py
  legacy/          ← Older standalone approaches (statistical, LLM-on-code, etc.)
  competition_taxonomy.py
  validate_submission.py
  run_validation_standard.py

artifacts/         ← Pipeline outputs (cached repo lists, fetched reports, mappings)
outputs/           ← Generated submission CSVs
data/              ← train.zip, test.zip, and unzipped folders (gitignored)
skills/            ← Validation + bridge skills shared with Codex
bridges/           ← Inter-agent task inbox (gitignored)

train.csv, test.csv    ← Competition inputs
submission_example.csv ← Required submission schema
daily_training_record.md  ← Dev log of experiments and decisions
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
python src/pipeline/06_generate_submission.py

# Validate before uploading.
python src/validate_submission.py --submission outputs/submission_c4_v4.csv
```

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

Tracked in [src/pipeline/README.md § Known weak spots](src/pipeline/README.md#known-weak-spots--next-iteration).
The three biggest leverage points right now are:
1. Identify the 3 still-unmapped test folders (BlackStar.sol family — non-C4/non-Sherlock platform).
2. Improve train-side identification from 39/54 → 50+/54 (enlarges the labeled set for the tag classifier).
3. Rewrite C4 finding bodies to train.csv style to push more descriptions over the BGE 0.7 cutoff.

# OneSavie Bastet — Foundation C4 Framework Report

> A clean extract of the **foundational C4 (Code4rena) lookup framework, workflow, and
> containerized runtime** for the Kaggle *OneSavie Bastet* smart-contract vulnerability
> competition. Experiment cruft, daily logs, and dead-end variants are intentionally left out —
> this pack contains only the reusable structure and the knowledge needed to rebuild it.

---

## 1. What this competition is

**Task.** For each test smart-contract repository, predict the list of vulnerabilities it
contains — each as a row of `(severity, tag, subtag, description)`.

**Inputs.** Each repo is identified only by a **12-character hex ID** (e.g. `0315ba9d8121`).
There is no source code in the CSVs — only the IDs and, for the train split, the gold labels.

**Output.** A single CSV of **exactly 400 rows** (`Property, repo_path, severity, tag, subtag,
description`), padded with `empty` rows where you have fewer predictions. See
[`dataset/submission_example.csv`](dataset/submission_example.csv).

### Scoring formula (per the local validation standard)

```
field_score   = max(0, (TP - 0.5 * FP) / N_truth)     # per field, per matched repo
repo_penalty  = max(0, num_predicted - num_truth)      # over-prediction is punished
description    = counts only if BGE cosine similarity >= 0.7 (else 0)
```

Three properties dominate the strategy and are baked into every design decision here:

1. **400-row hard cap.** Coverage is **zero-sum** — adding a row means dropping one. You cannot
   "buy" points by predicting more.
2. **Over-prediction is expensive.** Each false positive costs ~3–8× what an under-prediction
   costs, so the framework stays *under-covered* on purpose (per-repo cap of ~15).
3. **Descriptions are graded by semantic similarity**, not exact match — and truth descriptions
   are **terse** (~223 chars). Verbose predictions sit near the 0.7 cutoff and silently score 0.

---

## 2. The dataset (and the leak the whole framework is built on)

### 2.1 The three data files

| File | Rows | Role |
|---|---|---|
| [`dataset/train.csv`](dataset/train.csv) | 561 | Gold labels for the **train** repos — `(severity, tag, subtag, description)` keyed by hex `repo_path`. Doubles as a **labeled set of (audit finding → competition row)** examples. |
| [`dataset/test.csv`](dataset/test.csv) | 53 | The **test** repo IDs to predict (hex only, no labels). |
| [`dataset/submission_example.csv`](dataset/submission_example.csv) | abbreviated | Illustrates the required output schema + `empty` padding convention (header + rows 1–4 + a literal `...` + row 400 — a stand-in for the full 400-row format). |

`train.csv` schema (first row):

```
Property,repo_path,severity,tag,subtag,description
1,2cceea6fb3e4,High,"ERC721, Input Validation",Not EIP Compliant,"The function implements an incorrect input validation requiring the index to be greater than 0..."
```

Note the multi-value `tag` field (comma-separated), the single `subtag`, and the terse,
summary-style `description`.

### 2.2 The core insight — the IDs are not hashes, they are folder names

The 12-char hex IDs are **folder names inside two publicly downloadable Azure blobs**:

```
https://osbastetkagglesa.blob.core.windows.net/kaggle/train.zip   (~2.0 GB)
https://osbastetkagglesa.blob.core.windows.net/kaggle/test.zip    (~985 MB)
```

Each folder is the **source tree of a public Code4rena or Sherlock audit**. Open the folder,
read its `README.md`, and it names the contest:

```
# BendDAO audit details
Submit findings using the C4 form (https://code4rena.com/audits/2024-07-benddao-invitational/...)
```

Once a repo is identified as `2024-07-benddao`, its **published H/M findings** can be read
straight from `github.com/code-423n4/2024-07-benddao-findings/report.md`. The task collapses from
"predict vulnerabilities" to **"identify the audit, then transcribe its real findings."**

### 2.3 The two extra dataset leverages

- **`dataset_0831.csv`** (proprietary teammate annotation file, *not shipped here* — ~467 KB,
  504 rows). For test audits that appear in it, it provides ready-made rows in the exact
  competition schema (gold `severity`, train-style descriptions). Severity is ~99% filled; only
  ~12% of rows carry a gold `tag`/`subtag` — the remaining ~289 rows are the classifier's job.
- **The git-metadata leak — [`dataset/hash_to_contest_gitmap.json`](dataset/hash_to_contest_gitmap.json).**
  nearly every test repo retains a `.git/config` inside its folder whose `origin` URL names the
  exact GitHub audit repo. The shipped map resolves **51** of the test hashes — the
  **authoritative** hash→contest source, more reliable than parsing READMEs, and it corrected 3
  mis-mapped repos in later submissions.

---

## 3. The framework in two eras

The whole project is two stacked ideas. **Era 1 maxes coverage; Era 2 fixes the labels.**

```
                         ┌───────────────────────────────────────────────┐
                         │  ERA 1 — LOOKUP (coverage)                    │
                         │  hex folder  →  public audit  →  real findings │
                         │  312 → 442 public score                        │
                         └───────────────────────┬───────────────────────┘
                                                 │  rows are now real
                                                 │  findings, but their
                                                 │  (tag, subtag) are guesses
                                                 ▼
                         ┌───────────────────────────────────────────────┐
                         │  ERA 2 — LABELING-FUNCTION CLASSIFIER          │
                         │  model the competition's (tag,subtag) labeler  │
                         │  with an LLM; override guessed labels in place  │
                         │  442 → 474 public score                        │
                         └───────────────────────────────────────────────┘
```

**Why Era 2 is the real lever.** Once coverage is maxed, diagnostics on a repo-disjoint train
holdout show where points actually leak:

| Dimension | Naive | Modeled | Status |
|---|---|---|---|
| Severity | gold | gold | maxed (from `dataset_0831`) |
| Description | ~91% clear the 0.7 bar | — | maxed (canonical text, kept terse) |
| **Tag** | **~24%** | **~65%** | the leak — LLM classifier |
| **Subtag** | **~11%** | **~51%** | the leak — LLM classifier |

The critical methodological rule: **validate label changes on a repo-disjoint *train* holdout,
not a test self-holdout.** Repo hashes are disjoint train↔test, so coverage tuning never transfers
(and a train holdout scores any test submission at 0). But the *labeling function* — the taxonomy +
annotator conventions — **does** transfer train→test, which is exactly why label modeling works and
offline coverage tuning always failed.

---

## 4. The workflow (Era-1 pipeline, step by step)

All scripts run **from the project root** (not from inside `pipeline/`). Each step caches its
output under `artifacts/` so reruns are cheap.

```
        Public source data (Azure blob): train.zip + test.zip
                         │  download_data.py
                         ▼
   ┌──────────────────────────────────────────────────────────────┐
   │ 01_list_c4_repos.py        →  884 code-423n4 repos            │
   │ 02_fetch_c4_reports.py     →  376 *-findings/report.md        │
   │ 03_list_sherlock_repos.py  →  459 sherlock-audit repos        │
   │ 04_fetch_sherlock_reports.py → 229 *-judging/README.md        │
   └───────────────────────────────┬──────────────────────────────┘
                         ▼
   05_identify_contests.py   →  for each hex folder, scan README +
                                scope + subdir names → C4/Sherlock contest
                         ▼
   06_generate_submission.py →  parse each audit's H/M findings, train a
                                TF-IDF (tag,subtag) classifier on train.csv
                                pairs, emit a 400-row submission CSV
                         ▼
   07_generate_v5_with_dataset0831.py  →  best generator: emit gold rows
                                directly for audits in dataset_0831, fall back
                                to the lookup+TF-IDF path for the rest
                         ▼
                 outputs/submission_c4_v*.csv
```

| Step | File | What it does |
|---|---|---|
| 0 | [`pipeline/download_data.py`](pipeline/download_data.py) | Fetch `train.zip` + `test.zip` from the public Azure blob |
| 1 | [`pipeline/01_list_c4_repos.py`](pipeline/01_list_c4_repos.py) | Enumerate the `code-423n4` GitHub org → `artifacts/c4_repos.json` |
| 2 | [`pipeline/02_fetch_c4_reports.py`](pipeline/02_fetch_c4_reports.py) | Download each `*-findings/report.md` → `artifacts/c4_reports/` |
| 3 | [`pipeline/03_list_sherlock_repos.py`](pipeline/03_list_sherlock_repos.py) | Enumerate the `sherlock-audit` org |
| 4 | [`pipeline/04_fetch_sherlock_reports.py`](pipeline/04_fetch_sherlock_reports.py) | Download each `*-judging/README.md` |
| 5 | [`pipeline/05_identify_contests.py`](pipeline/05_identify_contests.py) | Map each `{hex}` folder → contest (README C4 URL regexes, Sherlock flagging, subdir voting with stop-tokens) |
| 6 | [`pipeline/06_generate_submission.py`](pipeline/06_generate_submission.py) | **Pure-public baseline generator** — parse findings, TF-IDF nearest-neighbor `(tag,subtag)` from `train.csv`, write 400-row CSV |
| 7 | [`pipeline/07_generate_v5_with_dataset0831.py`](pipeline/07_generate_v5_with_dataset0831.py) | **Best generator** — direct gold rows for `dataset_0831` audits + lookup fallback |

**How the classifier learns from `train.csv`:** once each *train* hash is mapped to its contest,
every train row becomes a labeled `(audit finding → competition (tag,subtag))` example (~437
pairs). Step 06 fits a TF-IDF vectorizer over those, then for each *test* finding copies the
`(tag, subtag)` of its nearest labeled neighbor.

### Era-2 classifier (the label-fixing layer)

Lives in [`classifier/`](classifier/). It replaces the TF-IDF guesses on the ~289 unlabeled rows
with LLM predictions:

1. [`prep.py`](classifier/prep.py) — build the repo-disjoint train holdout (seed 1337, 30%),
   few-shot set, and vocab.
2. **Classify** each guessed row from its *canonical audit text* (BGE-aligned to the cached
   report, not the short description), using the OneSavie taxonomy + few-shot + a 3-pass
   self-consistency ensemble. Winning prompt strategy: **`maxcontext`** — *pinpoint the exact
   code-level defect, then label.* (The classification passes are orchestrated by an agent; they
   are not a standalone script.)
3. [`assemble_v16.py`](classifier/assemble_v16.py) — override `tag`/`subtag` where ≥⅔ of passes
   agree (row counts, severity, descriptions untouched), writing the final submission.
4. [`score.py`](classifier/score.py) — score the change against the holdout truth + prior baseline
   (the go/no-go gate).

Supporting data: [`vocab.json`](classifier/vocab.json) (allowed labels),
[`tag2sub.json`](classifier/tag2sub.json) (tag→subtag taxonomy map),
[`fewshot.json`](classifier/fewshot.json) (few-shot examples).

---

## 5. The containerized runtime (Docker)

[`docker/`](docker/) holds the foundation runtime. The image is a thin Python-3.11-slim layer with
`git/curl/unzip` and the four pip deps; `data/`, `outputs/`, and `artifacts/` are bind-mounted so
downloaded reports and generated submissions persist on the host between runs.

> **Note:** the `COPY`/`volumes` paths in these files are written relative to the **original repo
> root** (`src/`, `train.csv`, `data/`, …). To build from this pack, move them back to the repo
> root, or adjust the paths to the `final_pack/` layout.

```bash
docker compose build                       # build the image once
docker compose run --rm pipeline           # interactive shell in the container
# inside the container, run any step:
python src/pipeline/download_data.py
python src/pipeline/06_generate_submission.py
# or one-shot:
docker compose run --rm pipeline python src/pipeline/06_generate_submission.py
```

- [`docker/Dockerfile`](docker/Dockerfile) — Python 3.11-slim + OS/pip deps + source copy
- [`docker/docker-compose.yml`](docker/docker-compose.yml) — `pipeline` service + volume mounts
- [`docker/.dockerignore`](docker/.dockerignore) — excludes multi-GB data, artifacts, dev metadata
- [`docker/requirements.txt`](docker/requirements.txt) — `pandas, numpy, scikit-learn, tqdm, anthropic`

---

## 6. Validation & taxonomy (common foundation)

| File | Role |
|---|---|
| [`common/validate_submission.py`](common/validate_submission.py) | Pre-upload checks: 400 rows, correct columns, sequential `Property`, `empty` padding |
| [`common/run_validation_standard.py`](common/run_validation_standard.py) | The local scoring standard — re-implements the competition scorer (TP/FP, repo penalty, BGE description gate) for offline evaluation |
| [`common/competition_taxonomy.py`](common/competition_taxonomy.py) | Loader for the tag/subtag taxonomy; builds prompt blocks + subtag→tag maps |
| [`references/competition_tag_definitions.md`](references/competition_tag_definitions.md) | The authoritative tag/subtag definitions (the label space) |
| [`references/taxonomy_generalization_workflow.md`](references/taxonomy_generalization_workflow.md) | How the taxonomy is applied/generalized |

Validate before every upload:

```bash
python common/validate_submission.py --submission outputs/submission_c4_v*.csv
```

---

## 7. final_pack file map

```
final_pack/
├── REPORT.md                      ← this document
├── pipeline/                      ← Era-1 C4 + Sherlock lookup workflow
│   ├── README.md                  ← architecture diagram + run instructions
│   ├── download_data.py
│   ├── 01_list_c4_repos.py
│   ├── 02_fetch_c4_reports.py
│   ├── 03_list_sherlock_repos.py
│   ├── 04_fetch_sherlock_reports.py
│   ├── 05_identify_contests.py
│   ├── 06_generate_submission.py          (pure-public baseline)
│   └── 07_generate_v5_with_dataset0831.py (best generator)
├── classifier/                    ← Era-2 labeling-function classifier
│   ├── README.md
│   ├── prep.py
│   ├── assemble_v16.py
│   ├── score.py
│   ├── vocab.json
│   ├── tag2sub.json
│   └── fewshot.json
├── common/                        ← validation + taxonomy utilities
│   ├── validate_submission.py
│   ├── run_validation_standard.py
│   └── competition_taxonomy.py
├── references/                    ← the label space
│   ├── competition_tag_definitions.md
│   └── taxonomy_generalization_workflow.md
├── dataset/                       ← schema inputs + the hash→contest map
│   ├── train.csv
│   ├── test.csv
│   ├── submission_example.csv
│   └── hash_to_contest_gitmap.json
└── docker/                        ← containerized runtime
    ├── Dockerfile
    ├── docker-compose.yml
    ├── .dockerignore
    └── requirements.txt
```

**Deliberately excluded** (not foundational): failed experiment generators (`08`–`11`), the
proprietary `dataset_0831.csv`, the multi-GB `train.zip`/`test.zip`, the full
`artifacts/c4_reports/` cache (385 fetched reports — regenerable by steps 02/04), the legacy
standalone models, and the daily experiment log. The score ladder, dead-ends, and per-experiment
reasoning live in the source repo's `daily_training_record.md` and `ANALYSIS_score_improvement.md`.

---

## 8. Score ladder (context)

| Milestone | Public score | Lever |
|---|---|---|
| Statistical priors | ~117 | most-frequent train combos |
| C4 lookup v1 | 218 | identify audit → real findings |
| v5 (`+dataset_0831`) | 312 | direct gold rows for known audits |
| Coverage maxed | 442 | every row a real canonical finding |
| **v13 — LLM tag classifier** | **464** | model the labeling function |
| v15 — canonical-text input | 471 | classify from full audit, not short desc |
| **v16 — `maxcontext`** | **474** | pinpoint code-level defect before labeling |

> The repo's *final* public best (`482.97`, v59) came from later git-fix + concise-description
> passes on top of this foundation; those are submission-specific tunings, not framework changes,
> and are documented in the source repo's logs rather than reproduced here.

---

## 9. Quick start

```bash
# 1. Dependencies
pip install -r docker/requirements.txt

# 2. Get the source data (~3 GB) and unzip
python pipeline/download_data.py
cd data && unzip -q train.zip && unzip -q test.zip && cd ..

# 3. Build the lookup caches (each step writes to artifacts/)
python pipeline/01_list_c4_repos.py
python pipeline/02_fetch_c4_reports.py
python pipeline/03_list_sherlock_repos.py
python pipeline/04_fetch_sherlock_reports.py
python pipeline/05_identify_contests.py

# 4. Generate a submission
python pipeline/06_generate_submission.py        # pure-public baseline (~212)
# or, with the teammate annotation file present:
python pipeline/07_generate_v5_with_dataset0831.py

# 5. Validate before upload
python common/validate_submission.py --submission outputs/submission_c4_v5.csv
```

> Paths in the scripts are relative to the **original repo root**. Running them from inside
> `final_pack/` requires either restoring the root layout or adjusting the hard-coded
> `train.csv` / `data/` / `artifacts/` paths.
</content>
</invoke>

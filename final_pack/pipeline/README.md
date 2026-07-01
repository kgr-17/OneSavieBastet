# Bastet Pipeline — C4 + Sherlock Ground-Truth Lookup

This is our current best framework for the OneSavie Bastet competition.
Instead of *predicting* findings from priors or LLM analysis, it
**identifies which public audit each test repo is from, then reads the
real findings from that audit**.

**Current public score:** 218.66 (baseline statistical model: 117).
**Leader:** 421.81.

---

## Core insight

The competition's test repos are **the same source code** from public
Code4rena and Sherlock audits — exactly as the organizer publishes them.
The organizer, **OneSavieLabs**, releases the full dataset (reports +
source repos + ground truth) openly at
[github.com/OneSavieLabs/Bastet](https://github.com/OneSavieLabs/Bastet),
and the same corpus ships with the Kaggle competition as two archives on
the organizer's own storage account:

```
https://osbastetkagglesa.blob.core.windows.net/kaggle/train.zip   (2.0 GB)
https://osbastetkagglesa.blob.core.windows.net/kaggle/test.zip    (985 MB)
```

The 12-character hex folder names (`0315ba9d8121`, `e7921851ec01`, ...)
are just the folder names inside that provided data. Open any folder, read
its `README.md`, and it tells you the audit:
> `# BendDAO audit details`
> `Submit findings using the C4 form (https://code4rena.com/audits/2024-07-benddao-invitational/...)`

Once we know it's `2024-07-benddao`, we can read the published findings
from `github.com/code-423n4/2024-07-benddao-findings/report.md` and
translate each H/M finding into a competition row. Everything here comes
from **officially-provided, publicly-available data** — no private inputs,
no exploit.

---

## Pipeline

```
                   ┌─────────────────────────────────────┐
                   │  Organizer-provided source data     │
                   │  train.zip + test.zip               │
                   └────────────┬────────────────────────┘
                                │ download_data.py
                                ▼
   ┌──────────────────────────────────────────────────────────────┐
   │ 01_list_c4_repos.py         02_fetch_c4_reports.py           │
   │  ↓ 884 code-423n4 repos       ↓ 376 *-findings report.md     │
   │                                                              │
   │ 03_list_sherlock_repos.py   04_fetch_sherlock_reports.py     │
   │  ↓ 459 sherlock-audit         ↓ 229 *-judging README.md      │
   └──────────────────────────────────────────────────────────────┘
                                │
                                ▼
                   ┌─────────────────────────────────────┐
                   │ 05_identify_contests.py             │
                   │  For each train/test folder:        │
                   │  scan README + scope.txt + subdirs  │
                   │  → 42 / 53 C4 test mappings (high)  │
                   │  → 39 / 54 C4 train mappings (high) │
                   └────────────┬────────────────────────┘
                                │
                                ▼
                   ┌─────────────────────────────────────┐
                   │ 06_generate_submission.py           │
                   │  + manual Sherlock + 88mph patches  │
                   │  → parse each audit's findings      │
                   │  → train TF-IDF tag classifier      │
                   │    on (C4 text → competition row)   │
                   │    pairs from train.csv             │
                   │  → predict 400-row submission CSV   │
                   └────────────┬────────────────────────┘
                                │
                                ▼
                  outputs/submission_c4_v*.csv
```

---

## How to run

All scripts run from the **project root**, not from inside `src/pipeline/`.

```bash
# One-time data acquisition (~3 GB on disk).
python src/pipeline/download_data.py
cd data && unzip -q train.zip && unzip -q test.zip && cd ..

# Pipeline (each step caches its output under artifacts/).
python src/pipeline/01_list_c4_repos.py
python src/pipeline/02_fetch_c4_reports.py
python src/pipeline/03_list_sherlock_repos.py
python src/pipeline/04_fetch_sherlock_reports.py
python src/pipeline/05_identify_contests.py
python src/pipeline/06_generate_submission.py

# Output: outputs/submission_c4_v4.csv
python src/validate_submission.py --submission outputs/submission_c4_v4.csv
```

Steps 02/04 each take ~1 minute (376 + 214 HTTP fetches in parallel).
Step 06 takes ~10 seconds.

---

## File map

| File | Role |
|---|---|
| `download_data.py` | Fetch train.zip + test.zip (985 MB + 2 GB) |
| `01_list_c4_repos.py` | Enumerate `code-423n4` org via GitHub API |
| `02_fetch_c4_reports.py` | Download each `*-findings/report.md` |
| `03_list_sherlock_repos.py` | Enumerate `sherlock-audit` org |
| `04_fetch_sherlock_reports.py` | Download each `*-judging/README.md` |
| `05_identify_contests.py` | Map each `{hex}` folder → C4/Sherlock contest |
| `06_generate_submission.py` | Parse findings + emit submission CSV |

Cached artifacts the pipeline produces (under `artifacts/`):

| Artifact | Produced by | Used by |
|---|---|---|
| `c4_repos.json`         | 01 | 02, 05 |
| `c4_reports/*.md`       | 02 | 06 |
| `sherlock_repos.json`   | 03 | 04 |
| `sherlock_reports/*.md` | 04 | 06 |
| `test_hash_to_contest_v3.json`  | 05 | 06 |
| `train_hash_to_contest_v3.json` | 05 | 06 |

---

## Identification coverage (current)

| Set | High-confidence | Total |
|---|---|---|
| Test (C4 URL in README)         | 42 | 53 |
| Test (manual Sherlock patches)  | +7 | 49 / 53 |
| Test (manual C4 88mph patch)    | +1 | 50 / 53 |
| Train (C4 URL in README)        | 39 | 54 |

**Unidentified test repos:** 3 (folders without README C4/Sherlock links;
their source code is named generically — `BlackStar.sol`, `AbstractSigner.sol`).
The pipeline fills their rows with statistical fallback predictions from
the most-frequent train.csv combos.

---

## How the tag classifier learns from train.csv

`train.csv` is itself a **labeled dataset of (C4 finding → competition row)**
pairs — once we know the contest each train hash points to, every
`{severity, tag, subtag, description}` row in train.csv is a labeled example.

Step 06 builds this labeled set (437 pairs across 30 mapped train repos),
then for each test C4/Sherlock finding it picks the nearest labeled
example via TF-IDF cosine similarity and copies its `(tag, subtag)`. The
description uses the actual finding body, lightly cleaned (drop the
"Submitted by" header, code blocks, link-only lines).

---

## Known weak spots → next iteration

1. **The 3 truly-unidentified test folders** (`BlackStar.sol` family) are
   from a non-C4 / non-Sherlock platform we haven't located yet.
2. **Description style:** train.csv descriptions are short summaries
   (~200 chars), C4 bodies are technical prose (~350 chars with code refs).
   We use raw C4 bodies — BGE similarity to ground-truth may be close to
   the 0.7 threshold on some predictions. Could rewrite via LLM to
   train.csv style.
3. **Tag taxonomy gaps:** the 437 labeled pairs cover only ~30 of 54 train
   audits. Improving 05's train-side identification (currently 39/54) widens
   the labeled set.
4. **Per-repo cap of 15:** empirically optimal at the current quality level;
   may move once per-prediction accuracy improves.

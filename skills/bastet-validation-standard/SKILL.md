---
name: bastet-validation-standard
description: Shared Bastet local-validation workflow for comparing candidate generators before a Kaggle submission. Use when evaluating a new baseline, tuning prediction count/calibration, deciding whether a local improvement is strong enough to submit, or when teammates need the same 50% repo-holdout scoring standard and submission gate.
---

# Bastet Validation Standard

## Overview

Run the repo-level holdout standard before treating a Bastet change as submission-worthy.
Use `src/run_validation_standard.py` as the single entry point so everyone compares candidate runs with the same split, structured scoring flow, and submission gate.

## Standard Workflow

1. Run a repo-level `50%` holdout split from `train.csv` with seed `1337`.
2. Train the candidate generator on the remaining `50%` only.
3. Predict on the held-out repos through a pseudo-test CSV.
4. Score the candidate with a competition-style structured score:
   - repo-level greedy one-to-one matching
   - tag / subtag / severity set scoring
   - description similarity thresholding
   - over-reporting penalty per repo
5. Use structured score as the primary submission gate.
6. Use proxy strict/family F1 only as diagnostics.
7. After the gate passes, rerun the generator on the full `train.csv` plus real `test.csv` for the actual submission.

## Commands

Use the built-in baseline runners:

```powershell
python src/run_validation_standard.py --generator baseline
python src/run_validation_standard.py --generator baseline_v2
```

Compare a candidate against the current accepted reference report:

```powershell
python src/run_validation_standard.py \
  --generator baseline_v2 \
  --reference-report artifacts/validation-standard/baseline-reference/outputs/holdout_evaluation_report.json
```

Run a custom generator command with placeholders:

```powershell
python src/run_validation_standard.py \
  --generator custom \
  --generator-command "python my_model.py --train-csv {train_csv} --test-csv {test_csv} --output {output}"
```

## Description Similarity

The scorer tries to use `bge-large-en-v1.5` through sentence-transformers when that stack is available locally.
If the model stack is unavailable, the script falls back to a lexical cosine scorer and records that fallback in the report.

Use `--description-scorer bge` if you want the run to fail instead of falling back.

## Submission Gate

Treat structured score as the primary local score.
A candidate passes by default only if its structured score improves versus the reference report.

Proxy strict and family F1 remain in the report because they are useful for quick debugging, but they are no longer the main gate.

## Interpretation Rules

- Split by `repo_path`, never by raw rows. The competition is repo-level, so row-level splits leak information.
- Keep the holdout split for evaluation only. Do not use the held-out repos when tuning that candidate.
- Do not treat the 50% holdout as the final training recipe. Once a candidate passes the gate, retrain on the full `train.csv` for the real submission.
- Duplicate prediction rows are removed before local scoring, matching the competition notes.
- Predictions outside the holdout repo set are ignored, matching the competition notes.
- Use the same seed unless the team explicitly decides to rotate it. Consistency matters more than variety for comparison.

## Outputs

Each run writes artifacts under `artifacts/validation-standard/<run-name>/`:

- `split/train_split.csv`
- `split/holdout_truth.csv`
- `split/holdout_test.csv`
- `outputs/holdout_predictions.csv`
- `outputs/holdout_evaluation_report.json`
- `outputs/holdout_evaluation_summary.txt`

Read `references/metric-standard.md` when you need the exact structured scoring components, the fallback behavior for description scoring, or the team gate.

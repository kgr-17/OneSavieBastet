# OneSavie Bastet Competition Tracker

This workspace is for the Bastet smart contract vulnerability classification competition. The goal is to detect repository-level vulnerabilities and submit structured findings with the right `repo_path`, `tag`, `subtag`, `severity`, and `description`.

This README is meant to be a working tracker, not just a project intro. Use it to keep the problem, constraints, current baseline, and experiment log in one place.

## Current Status

| Item | Status |
| --- | --- |
| Competition objective understood | Yes |
| Local training labels loaded | Yes |
| Baseline pipeline exists | Yes |
| README / tracker | This file |
| Official Bastet tag definition synced against local code | Not confirmed |
| Submission strategy calibrated for over-reporting penalty | In progress |
| Best public leaderboard score | `88.59269` |

## Local Workspace Snapshot

| File | Purpose |
| --- | --- |
| `first_achive.py` | Current end-to-end baseline pipeline |
| `train.csv` | Labeled training findings |
| `test.csv` | Unlabeled repositories for prediction |
| `submission_example.csv` | Required submission schema example |
| `src/baseline.py` | New standalone baseline submission generator |
| `src/baseline_v2.py` | Stronger second baseline inspired by rule + similarity ideas |
| `src/baseline_v3.py` | Strong local candidate after severity calibration and wider repo-support priors |
| `src/baseline_v4.py` | Current best local candidate with a safer repo-count floor and light diversity pressure |
| `src/validate_submission.py` | Submission validator |
| `src/run_validation_standard.py` | Shared 50% repo-holdout validation runner and scorer |
| `skills/bastet-validation-standard/` | Repo-local skill describing the team validation gate |
| `skills/claude-code-bridge/` | Repo-local skill for Codex-Claude collaboration tasks |
| `CLAUDE.md` | Root bridge instructions for Claude Code |
| `bridges/claude-code/` | Shared task and response inbox for cross-agent work |
| `Dockerfile` | Competition container setup |

Quick local counts from the current files:
- Training findings: `497`
- Training repositories: `54`
- Test repositories: `53`
- Submission columns: `Property, repo_path, severity, tag, subtag, description`
- Training severities seen locally: `High`, `Medium`

## Docker Baseline

This repo now includes a separate Dockerized baseline that does not depend on `first_achive.py`.

Build the image:

```bash
docker build -t onesavie-bastet-baseline .
```

Run the baseline:

```bash
docker run --rm -v "${PWD}:/workspace" onesavie-bastet-baseline
```

Or with Docker Compose:

```bash
docker compose up --build baseline
```

Run the second baseline:

```bash
docker compose up --build baseline_v2
```

The generated baseline submission is written to:

```text
outputs/submission.csv
```

Validate the file locally:

```bash
python src/validate_submission.py --submission outputs/submission.csv --sample-submission submission_example.csv
```

How the new baseline works:

- Uses training-set label priors from `train.csv`
- Produces a valid `400`-row submission immediately
- Pads unused rows with `empty`
- Can optionally scan extracted repo folders later through `--test-repo-root`
- Keeps all new work separate from `first_achive.py`
- `src/baseline_v2.py` adds observed-label rules, repo-count priors, and optional similarity transfer when repo folders are available

## Competition Goal

For each repository, identify real vulnerabilities using the Bastet tag definitions and submit:

- `repo_path`: repository identifier
- `tag`: high-level vulnerability category
- `subtag`: more specific vulnerability label
- `severity`: real-world impact level
- `description`: concise explanation of the root cause and impact

Important competition property:

- A repository can have `0`, `1`, or `many` vulnerabilities.
- Evaluation is repository-level, not file-level.
- Long-context reasoning matters because the bugs can depend on interactions across files and contracts.

## Evaluation Notes That Affect Strategy

These are the parts of the metric that matter most for day-to-day modeling decisions:

1. Matching happens within each `repo_path`.
2. Predictions are matched one-to-one against ground truth using greedy matching.
3. `tag`, `subtag`, and `severity` are rewarded for correct labels and penalized for extra labels.
4. `description` is scored with semantic similarity, so it needs to be specific and aligned with the actual root cause.
5. Over-reporting hurts. Predicting too many findings in a repo can lower total score.
6. Duplicate submission rows are removed before scoring.
7. Repositories not in ground truth are ignored.

Practical implications:

- Fewer high-confidence findings are usually better than spraying many weak ones.
- Descriptions should explain the actual bug mechanism, not generic audit filler.
- Calibrating "how many findings per repo" is part of the model, not just post-processing.
- Multi-label fields need careful handling because extra labels can reduce score.

## Submission Rules

Submission format should match `submission_example.csv` exactly:

| Column | Required |
| --- | --- |
| `Property` | Yes |
| `repo_path` | Yes |
| `severity` | Yes |
| `tag` | Yes |
| `subtag` | Yes |
| `description` | Yes |

Operational rules from the brief:

- File type must be CSV.
- Column names must match exactly.
- Submission must contain exactly `400` rows.
- If fewer than `400` findings are predicted, remaining rows should be padded.
- If more than `400` findings are predicted, truncate to `400`.
- Public leaderboard uses part of the test set; final ranking uses the private set.

Things to verify before every submission:

- Exact column order matches sample.
- Row count is exactly `400`.
- No accidental duplicates.
- No invalid tags or subtags.
- Padding format matches what the competition accepts.

## Local Validation Standard

Before spending a Kaggle submission, every serious candidate should pass the shared local validation gate.

Standard rules:

- Split `train.csv` by `repo_path`, not by raw rows.
- Use a `50%` holdout fraction with seed `1337`.
- Train the candidate only on the remaining half.
- Score with a competition-style structured score using:
  - repo-level greedy one-to-one matching
  - tag / subtag / severity field scoring
  - description similarity thresholding
  - over-reporting penalty per repo
- Treat structured score as the main local submit gate.
- Keep proxy strict/family F1 only as diagnostics.
- After a candidate passes the gate, rerun it on full `train.csv` plus real `test.csv` for the actual submission.

Standard command examples:

```bash
python src/run_validation_standard.py --generator baseline
python src/run_validation_standard.py --generator baseline_v2
python src/run_validation_standard.py --generator custom --generator-command "python src/baseline_v3.py --train-csv {train_csv} --test-csv {test_csv} --sample-submission {sample_submission} --output {output} --target-rows {target_rows}"
```

Current best local validated candidate:
- `src/baseline_v4.py`
- `artifacts/validation-standard/baseline-v4-defaults/outputs/holdout_evaluation_summary.txt`
- Structured score: `173.2500`
- Delta vs previous local best `baseline-v3-defaults-final`: `+19.7500`

Artifacts are written under `artifacts/validation-standard/<run-name>/` and include the split CSVs, holdout predictions, JSON report, and summary text.

When sentence-transformers plus `bge-large-en-v1.5` are available locally, the harness uses them for description similarity. Otherwise it records a lexical fallback in the report so the team knows exactly what was used.

The repo-local skill at `skills/bastet-validation-standard/` documents the same workflow so the team can reuse one standard when comparing experiments.

## What The Current Baseline Does

`first_achive.py` currently looks like a hybrid baseline with:

- Rule-based smart contract detectors
- Similarity lookup against training repositories
- Optional LLM-assisted finding generation
- Submission post-processing to force exactly `400` rows

Current pipeline behavior worth remembering:

- It assumes Kaggle-style paths such as `/kaggle/input/...`.
- It hardcodes a tag definition in the script.
- It limits findings per repository with a heuristic.
- It pads to `400` rows after deduplication.

## Baseline Risks To Track

These are the highest-signal risks I noticed from the current workspace:

1. The local training data appears broader than the hardcoded label space in `first_achive.py`.
   The training CSV shows multi-label examples and at least one sample with labels not obviously covered by the script's manual tag list.
2. The competition penalizes over-reporting, so aggressive padding with non-empty vulnerability guesses may be harmful.
3. The scoring is repository-level and one-to-one, so duplicate or near-duplicate findings inside the same repo can waste slots.
4. The script is written for Kaggle paths, so local testing and reproducibility will be awkward unless paths are parameterized.
5. Description quality matters because weak generic text may fail the semantic similarity threshold.

## Recommended Working Plan

### Phase 1: Label Space Audit

- Extract all unique `tag` and `subtag` values from `train.csv`
- Compare them against the official Bastet definitions
- Decide whether prediction should be single-label or multi-label per finding
- Build a mapping policy for synonyms, deprecated names, and normalization

### Phase 2: Repository Understanding

- Build per-repo summaries from train repos
- Identify common bug families and common finding counts per repo
- Track which tags often co-occur
- Separate strong exploit patterns from weak style issues

### Phase 3: Prediction Calibration

- Tune how many findings to emit per repo
- Add a confidence threshold
- Prefer precision over recall when evidence is weak
- Make padding strategy competition-safe

### Phase 4: Description Quality

- Write descriptions around root cause plus impact
- Avoid generic wording like "may be vulnerable" unless truly uncertain
- Reuse train wording patterns only when the mechanism actually matches
- Keep descriptions distinct across findings in the same repo

### Phase 5: Submission Validation

- Validate row count, columns, duplicates, nulls, and label legality
- Check per-repo prediction counts
- Review padding rows separately from real findings
- Save final run notes with leaderboard score and changes

## Experiment Tracker

Update this table after each serious run.

| Date | Version | Main change | Expected effect | Validation done | Public LB | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| 2026-04-06 | `v0` | Initial README and baseline review | Better tracking | File inspection only | `TBD` | Need label-space audit first |
| 2026-04-06 | `v1` | Added Docker setup plus standalone prior baseline | Valid first submission and reproducible environment | Local CSV validation passed | `88.59269` | `outputs/submission.csv` generated |
| 2026-04-06 | `v2` | Added highst-inspired second baseline | More diverse priors with optional rule and similarity support | Local CSV validation passed | `81.18031` | `outputs/submission_v2.csv` generated |
| 2026-04-08 | `v3` | Wider repo-support prior pool plus severity calibration fix | Stronger local structured score without high-severity inflation | Structured holdout PASS (`153.5000`) | `TBD` | `outputs/submission_v3.csv` generated |
| 2026-04-08 | `v4` | Added repo-count floor plus very light selector tuning | Clears local `169` target while staying under `400` rows without truncation | Structured holdout PASS (`173.2500`) | `TBD` | `outputs/submission_v4.csv` generated; current best local candidate |
| 2026-04-08 | `validation-standard` | Added repo-level 50% holdout scorer plus team skill | Standardized local submit gate before Kaggle | Harness compile + baseline runs | `n/a` | Use `src/run_validation_standard.py` and `skills/bastet-validation-standard/` |
|  |  |  |  |  |  |  |
|  |  |  |  |  |  |  |
|  |  |  |  |  |  |  |

## Run Checklist

Use this before each submission:

- [ ] Confirm official Bastet tag definitions are up to date
- [ ] Run `src/run_validation_standard.py` on the candidate and compare against the accepted reference report
- [ ] Require structured score improvement versus the accepted reference report before submitting
- [ ] Check whether output labels are valid for the competition
- [ ] Check whether multi-label formatting is correct
- [ ] Validate exactly `400` rows
- [ ] Validate no duplicate findings
- [ ] Review high-confidence findings manually
- [ ] Review padding rows manually
- [ ] Save submission file name and leaderboard result here

## Open Questions
- What is the exact official Bastet tag definition source to treat as canonical?
- Should padded rows be fully empty, use the literal word `empty`, or follow another exact convention from the sample?
- Does the best scoring strategy allow multi-label `tag` and `subtag` fields, or is it better to split them into separate findings?
- How many findings per repository does the training distribution suggest after deduplication and normalization?

## Near-Term TODOs

- [ ] Create a script to audit unique train tags and subtags
- [ ] Move hardcoded paths into config or CLI args
- [ ] Move API credentials out of source code and into environment variables
- [x] Add a shared local validation standard and scoring harness
- [ ] Compare empty-padding vs synthetic-padding strategies
- [ ] Add a per-repo confidence score for ranking findings

## Notes

- Competition success will likely come from calibration and label-space correctness as much as raw bug detection.
- If the official tag taxonomy and the local hardcoded taxonomy disagree, the official competition taxonomy should win.
- This README should be updated after every meaningful experiment so the project stays easy to reason about under leaderboard pressure.

## Context Limit Rule (Claude + Codex)

**If your context window reaches 90%, stop work immediately.**

Before ending the session:
1. Write a summary to `daily_training_record.md` covering:
   - What was done this session
   - Which files were changed and why
   - Current local structured score (if run)
   - What comes next (specific next step, not vague)
2. Start a fresh session and read `daily_training_record.md` first to restore context.

This rule applies to both Claude and Codex. Do not try to squeeze more work into an overloaded context — output quality degrades silently.








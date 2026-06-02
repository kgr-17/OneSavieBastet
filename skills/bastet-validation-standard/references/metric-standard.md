# Bastet Metric Standard

## Core Terms

`structured score`
The main local score used by the validation standard.
It follows the competition structure much more closely than the earlier proxy scorer:

- repository-level matching
- greedy one-to-one pairing
- tag / subtag / severity field scores
- description similarity score
- over-reporting penalty

`proxy strict`
Diagnostic metric using deduplicated signatures of `repo_path + severity + tag`.
Useful for fast debugging, but not the primary gate.

`proxy family`
Diagnostic metric using deduplicated signatures of `repo_path + tag`.
Useful for family-level coverage checks, but not the primary gate.

## Structured Pair Score

For a ground-truth finding `G` and predicted finding `P`, the local structured scorer computes:

`PairScore = TagScore + SubtagScore + SeverityScore + DescriptionScore - Penalty`

Field scores follow the competition formula shown in the evaluation brief:

`FieldScore = max(0, (TP - 0.5 * FP) / N)`

Where:

- `TP` = correctly predicted labels in the field
- `FP` = predicted labels not present in the ground truth field
- `N` = number of ground-truth labels in the field

Each of `tag`, `subtag`, and `severity` is treated as a set of comma-separated labels.

## Description Score

Preferred behavior:

- sentence-transformers with model `BAAI/bge-large-en-v1.5`
- cosine similarity over normalized embeddings
- score is zero when similarity is `<= 0.7`

Fallback behavior in the current workspace:

- if sentence-transformers or the BGE model is unavailable locally, `src/run_validation_standard.py` falls back to lexical cosine similarity over normalized tokens
- the report always records whether the run used `bge` or `lexical`
- use `--description-scorer bge` if you want the run to error instead of falling back

## Matching Procedure

For each repository independently:

1. Build all pairwise scores between predicted and ground-truth findings.
2. Subtract the same over-reporting penalty from each pair score in that repository.
3. Repeatedly take the highest-scoring unmatched pair.
4. Stop when there are no unmatched pairs left or the best remaining pair score is non-positive.
5. Sum the matched pair scores.

The stop-at-non-positive rule is an implementation inference so local score does not go negative when all remaining pairings are bad.

## Over-Reporting Penalty

For each repository:

`Penalty = max(0, #Predictions - #GroundTruth)`

The same penalty is subtracted from every pair score in that repository before greedy matching.

## Standard Split

- Split at the repository level, not row level.
- Default holdout fraction: `0.50`
- Default seed: `1337`
- Default pad token: `empty`

For the current dataset this means `54` train repos become `27` train repos and `27` holdout repos.

## Submission Gate

Default gate used by `src/run_validation_standard.py` when `--reference-report` is supplied:

- structured score delta must be `> 0.0`

The report also includes proxy strict and proxy family deltas for diagnosis.

## Recommended Team Routine

1. Keep one accepted reference report for the current production baseline.
2. Run every candidate with the validation standard before generating a real submission.
3. Submit only if structured score improves and the qualitative failure pattern still looks healthy.
4. After the gate passes, rerun the candidate on full `train.csv` plus real `test.csv`.
5. Record the public leaderboard result in `daily_training_record.md` and `README.md`.

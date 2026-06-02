# Taxonomy-Generalization Workflow

This workflow is designed to use the saved competition tag definitions as a real training asset instead of a passive note file.

## Goal

Build a new model family that generalizes better to the public leaderboard by anchoring the output space to the competition taxonomy, measuring stability across seeds, and separating stable label families from rare outliers.

## Why This Helps

The current repo has two problems:

1. Some older scripts use a custom tag vocabulary that does not fully match the competition taxonomy or the real `train.csv` labels.
2. Models have been optimized too hard for one local holdout split, which improves local score but hurts public generalization.

The new workflow reduces both problems by making taxonomy alignment a first-class step.

## Source Of Truth

- Human-readable competition taxonomy: `references/competition_tag_definitions.md`
- Parser and prompt helper: `src/competition_taxonomy.py`
- Alignment and prior-builder: `src/profile_taxonomy_alignment.py`

## Workflow

### 1. Load the competition taxonomy

Use `src/competition_taxonomy.py` to parse the markdown source into:

- canonical tag names
- canonical subtags per tag
- reverse subtag-to-tag map
- prompt text blocks for LLM-style analyzers

This avoids hardcoding tag lists separately in every model file.

### 2. Profile `train.csv` against the taxonomy

Run:

```powershell
python .\src\profile_taxonomy_alignment.py
```

This exports:

- `artifacts/taxonomy-profile/competition_taxonomy_profile.json`
- `artifacts/taxonomy-profile/competition_taxonomy_summary.txt`
- `artifacts/taxonomy-profile/competition_taxonomy_prompt_block.txt`
- `artifacts/taxonomy-profile/active_core_pairs.csv`

What to look for:

- exact taxonomy matches
- case-variant tags such as `Logic Error` vs `Logic error`
- rare train-only tags such as `Multisig`, `RCE`, `Rebalance`, and `XSS Attack`
- stable single-label tag/subtag/severity pairs

### 3. Build an active taxonomy layer

Use the exported `active_core_pairs.csv` as the high-confidence label space for the new model.

Rules:

- Stable core: pairs that appear multiple times and across multiple repos
- Alias layer: case variants mapped back to canonical competition tags
- Outlier layer: rare train-only tags kept separate and disabled by default unless there is strong evidence

This is important because multi-tag rows in `train.csv` should not be expanded into fake tag/subtag Cartesian products.

### 4. Train the new model on stable families first

Recommended model structure:

1. Detection layer
   Use rules, code fingerprints, or LLM prompts to produce candidate findings.
2. Taxonomy gate
   Only allow candidates whose tag and subtag exist in the active taxonomy layer.
3. Description layer
   Prefer prototype descriptions from the stable training families instead of split-tuned local wording.
4. Outlier layer
   Add rare labels only when code evidence is unusually strong.

This should replace the older approach of embedding together noisy submissions with weak label control.

### 5. Select by stability, not peak local score

Use multi-seed evaluation with the existing validation tooling.

Recommended objective:

```text
selection_score = mean_local_score - 0.75 * std_local_score
```

That favors models that stay strong across seeds instead of overfitting one split.

### 6. Submission strategy

- First submit the most stable model, not the highest single-split local winner.
- Use the high-variance model only as an exploratory side branch.
- Keep a simple conservative anchor model available as fallback.

## Recommended Next Model

The next model should be a taxonomy-aware successor to the `baseline_v3` family, not another wide ensemble.

Suggested name:

- `src/baseline_v8_taxonomy_guarded.py`

Suggested behavior:

- use `active_core_pairs.csv` as the default label bank
- use competition descriptions in prompts
- keep only stable tag families active by default
- treat train-only outlier tags as opt-in
- validate with multi-seed selection before submission

## Practical Commands

Profile taxonomy:

```powershell
python .\src\profile_taxonomy_alignment.py
```

Compile helper modules:

```powershell
python -m py_compile .\src\competition_taxonomy.py
python -m py_compile .\src\profile_taxonomy_alignment.py
```

## Notes

- Do not force all training labels into canonical competition tags; keep a small outlier layer so we do not erase rare but real train signals.
- Do not learn tag/subtag pairs from multi-label rows using Cartesian expansion.
- Do not pick the final model by the best score on one seed.

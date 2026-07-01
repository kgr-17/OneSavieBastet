# Labeling-function classifier (Era 2: 442 → 474)

Reverse-engineers the competition's `(tag, subtag)` labeling function with an LLM and applies it
**in place** to the rows our lookup pipeline left as guesses. Severity (99% gold in `dataset_0831`)
and descriptions (rich canonical text) are already maxed; **tag/subtag are the gap** and this is
where the points are.

## Why it works (the curse-breaker)
train/test repo hashes are **disjoint**, so a train holdout scores any *test* submission at 0 —
which is why every offline *coverage* tune failed and `tools/holdout_score.py` is banned. But the
*labeling function* (taxonomy + annotator conventions) **transfers train→test**. So a repo-disjoint
train holdout (seed 1337, 30%) is a valid, predictive validator for label models — and it is the
go/no-go gate for every change here.

## Method
1. **Identify guessed rows** — rows whose audit has no `tag` in `dataset_0831` (~289 of 400; gold is
   only 12% tagged). Keep the ~125 gold-tagged rows untouched.
2. **Classify** each from its **canonical audit text** (BGE-aligned to the cached C4/Sherlock report,
   not the short description) with: the OneSavie taxonomy, a few-shot set, and a 3-pass self-consistency
   ensemble. Winning prompt strategy = **`maxcontext`**: *pinpoint the exact code-level defect, then label.*
3. **Override** tag/subtag where ≥⅔ of passes agree. Row counts, severity, descriptions unchanged
   (pure-label, zero structural risk to the score floor).

## Validated results (holdout → live)
| Change | Holdout | Live |
|---|---|---|
| generic classifier (v13) | tag 24%→59% | **+22** |
| canonical-text input (v15) | subtag 43%→51% | 471.18 |
| `maxcontext` tournament winner (v16) | **tag 61%→65%** | **474.21** |

Dead-ends (all holdout-validated as flat/negative): retrieval few-shot (−6pp), 5-pass (flat),
two-stage subtag (−5pp), disambiguation rules (zero-sum), subtag specialist (48%), ensembles (~0).

## Files
**Pipeline (run order):** `prep.py` (build holdout/few-shot/vocab) → classification workflows
(orchestrated from the agent, not standalone scripts) → `assemble_v13/15/16.py` (apply predictions
to `outputs/submission_c4_v11.csv`, write the submission).

**Scorers** (`score_*.py`): each validates one experiment vs the holdout truth + the prior baseline.
`score_tournament.py` / `score_confirm.py` rank prompting strategies; `score_subtag.py`, `score_v15.py`, etc.

**Data:** `holdout.json` (truth), `holdout_blind.json` / `holdout_canon_input.json` (inputs),
`fewshot*.json`, `vocab.json`, `tag2sub.json` (taxonomy maps), `test_canonical.json` (test rows +
aligned canonical text), `*_apply.json` / `*_holdout.json` (cached LLM predictions), `tournament.json`.

**Teammate handoff:** `../teammate_labeling_sheet.csv` — the 289 guessed rows pre-filled with our
guesses + confidence flags, for confirming gold (the path past the 65% LLM ceiling).

## Reproduce
```bash
python artifacts/tag_classifier/prep.py            # build holdout split + few-shot + vocab
# (run the maxcontext 3-pass classification over the guessed rows — see daily_training_record.md)
python artifacts/tag_classifier/assemble_v16.py    # -> outputs/submission_c4_v16_maxcontext.csv
python src/validate_submission.py --submission outputs/submission_c4_v16_maxcontext.csv
```

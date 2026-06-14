# Retag Variant Manifest

All variants preserve the same 400 rows and per-repo counts as v11/v13.

## submission_c4_v14_retag_unanimous

- File: `outputs\retag_variants\submission_c4_v14_retag_unanimous.csv`
- Base: `v11`
- Vote mode: `unanimous`
- Stats: `{'tag_changed': 107, 'subtag_changed': 113}`
- Hypothesis: Safer than v13: only override when every vote agrees.

## submission_c4_v15_retag_tagonly

- File: `outputs\retag_variants\submission_c4_v15_retag_tagonly.csv`
- Base: `v11`
- Vote mode: `v13`
- Stats: `{'tag_changed': 145}`
- Hypothesis: Isolate tag overrides from v13.

## submission_c4_v16_retag_subtagonly

- File: `outputs\retag_variants\submission_c4_v16_retag_subtagonly.csv`
- Base: `v11`
- Vote mode: `v13`
- Stats: `{'subtag_changed': 152}`
- Hypothesis: Isolate subtag overrides from v13.

## submission_c4_v17_retag_plurality2

- File: `outputs\retag_variants\submission_c4_v17_retag_plurality2.csv`
- Base: `v11`
- Vote mode: `plurality2`
- Stats: `{'tag_changed': 146, 'subtag_changed': 161}`
- Hypothesis: More aggressive than v13: any label with at least two votes wins.

## submission_c4_v18_retag_hedge_v13

- File: `outputs\retag_variants\submission_c4_v18_retag_hedge_v13.csv`
- Base: `v11`
- Vote mode: `v13`
- Stats: `{'tag_hedged': 145, 'subtag_hedged': 152}`
- Hypothesis: Keep v11 labels and add v13 majority labels as hedges.

## submission_c4_v19_retag_v13_plus_plurality_subtags

- File: `outputs\retag_variants\submission_c4_v19_retag_v13_plus_plurality_subtags.csv`
- Base: `v13`
- Vote mode: `plurality2`
- Stats: `{'subtag_changed': 9}`
- Hypothesis: Start from public-improving v13, then apply more aggressive subtag-only replacements.

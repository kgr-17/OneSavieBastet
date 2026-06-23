# CLAUDE.md

This repository includes a file-based collaboration bridge so Claude Code and Codex can coordinate work safely.

## Bridge Protocol

Use the bridge state under `bridges/claude-code/`:

- `tasks/` contains open collaboration requests
- `responses/` contains completed or blocked handoff notes

Use the helper script when possible:

```powershell
python skills/claude-code-bridge/scripts/claude_bridge.py list
python skills/claude-code-bridge/scripts/claude_bridge.py show --task-id <task-id>
python skills/claude-code-bridge/scripts/claude_bridge.py claim --task-id <task-id> --agent claude-code
python skills/claude-code-bridge/scripts/claude_bridge.py respond --task-id <task-id> --agent claude-code --summary "..."
```

## Collaboration Rules

- Respect the task's stated file scope and constraints.
- Do not overwrite unrelated user or Codex changes.
- If the task is ambiguous or blocked, respond with status `blocked` and list the question instead of guessing.
- Record touched files in the bridge response.
- Keep the repo as the shared source of truth; do not rely on hidden side context.

## Repo Context

This project is tracking the Bastet smart-contract vulnerability competition.
The local validation standard lives in `src/run_validation_standard.py` and the shared validation skill lives in `skills/bastet-validation-standard/`.

## Latest Bastet Handoff - 2026-06-22 15:44 PT

Start here after refresh:

- Current public barrier remains the 474.x family. Known recent scores:
  - screenshot best: `474.87796`
  - v25d/v16-style: `474.21304`
  - v29j all6 pair majority ge5: `473.21304`
  - v30g GPT-5.5 top49 excluding v29j-loss pids: `472.26098`
  - v30h all6 ge4 excluding v29j-loss pids: `472.23541`
- Codex tested the aggressive label-lane idea using the top49 model/team-labeled rows.
- v29j changed seven high-consensus pids and lost live: `101, 112, 162, 164, 331, 332, 374`.
- v30 excluded those seven pids and tried broader remaining top49 label edits. Two public probes still lost:
  - `outputs/submission_c4_v30g_labeltop49_gpt55_top49_exclude_v29jloss.csv` changed 23 rows, public `472.26098`.
  - `outputs/submission_c4_v30h_labeltop49_all6_pair_majority_ge4_exclude_v29jloss.csv` changed 10 rows, public `472.23541`.
- Local old-holdout label-lane validation was directionally correct:
  - baseline maxcontext: `394.0346`
  - pair majority / independent: `393.3680` (`-0.6667`)
  - GPT-5.5: `389.3680` (`-4.6667`)
  - unanimous/high-agreement hedge: `394.0346` (`+0.0000`)
- Conclusion: stop v30-style AI-label permutations. They are noisy and public-negative. Only reopen label-lane if a genuinely human-reviewed/gold label source appears.

Useful files:

- `daily_training_record.md`
- `artifacts/tag_classifier/label_lane_v30_aggressive_plan_20260622.md`
- `artifacts/tag_classifier/label_lane_v30_aggressive_manifest_20260622.json`
- `artifacts/tag_classifier/local_label_lane_validation_20260622.json`
- `scratch/build_label_lane_v30_aggressive.py`
- `bridges/claude-code/tasks/20260622-154459-continue-after-v30-label-lane-public-results.md`

Recommended next move:

Work from the prior best submission family, not from v30. The remaining plausible path is external/human gold labels for guessed tag/subtag rows; algorithmic relabeling from the same text has repeatedly tied or lost.

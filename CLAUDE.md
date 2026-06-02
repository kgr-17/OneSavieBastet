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

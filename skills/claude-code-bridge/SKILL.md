---
name: claude-code-bridge
description: Shared bridge for Codex and Claude Code to coordinate work inside the same repository through task files, response files, and a common protocol. Use when Codex needs to hand work to Claude Code, read Claude Code responses, create a collaboration inbox in the repo, or keep both agents aligned on ownership, touched files, and next steps.
---

# Claude Code Bridge

## Overview

Use this skill when work in the repo should be shared between Codex and Claude Code instead of being passed informally in chat.
The bridge uses files under `bridges/claude-code/` plus the helper script `scripts/claude_bridge.py` so both agents can access the same task state from the workspace.

## Workflow

1. Initialize the bridge once:

```powershell
python skills/claude-code-bridge/scripts/claude_bridge.py init
```

2. Create a task for Claude Code:

```powershell
python skills/claude-code-bridge/scripts/claude_bridge.py create-task \
  --title "Improve validation scorer" \
  --request "Update the scorer to support the official pair score formula." \
  --path "src/run_validation_standard.py" \
  --constraint "Do not overwrite unrelated user edits."
```

3. If needed, render the task into a Claude-friendly prompt:

```powershell
python skills/claude-code-bridge/scripts/claude_bridge.py render-prompt --task-id <task-id>
```

4. Let Claude Code work in the same repository. Claude Code should follow `CLAUDE.md` at the repo root.

5. Read the response files under `bridges/claude-code/responses/` or inspect the task JSON.

6. After integrating the result, close the task:

```powershell
python skills/claude-code-bridge/scripts/claude_bridge.py close \
  --task-id <task-id> \
  --resolution "Merged the requested change into the baseline."
```

## Protocol Rules

- Use task files for bounded requests with a clear owner and concrete file scope.
- Use response files for summaries, touched files, questions, and next steps.
- Keep the bridge as coordination metadata, not the place for large code diffs.
- Point tasks at repo paths directly so both agents can open the same files.
- Keep ownership explicit when two agents might touch nearby files.
- Read `references/protocol.md` for the exact task and response conventions.

## Important Notes

- This bridge is file-based, so it works even if Codex cannot launch Claude Code directly from the terminal.
- If Claude Code is available elsewhere in your IDE, the root `CLAUDE.md` gives it the same protocol automatically.
- The helper script does not assume any Claude CLI command name, because this workspace currently does not expose one in the terminal path.

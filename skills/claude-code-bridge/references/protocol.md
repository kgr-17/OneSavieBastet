# Claude Code Bridge Protocol

## Shared Locations

Bridge state lives under `bridges/claude-code/`:

- `tasks/`: one JSON plus one Markdown file per task
- `responses/`: one JSON plus one Markdown file per response
- `archive/`: reserved for future cleanup or archival

## Task Lifecycle

1. Codex or the user creates a task with `create-task`.
2. Claude Code can inspect the task Markdown or JSON.
3. Claude Code can claim the task with `claim`.
4. Claude Code writes a response with `respond`.
5. Codex or the user closes the task with `close` after integration.

## Task Content

Every task should include:

- title
- request
- assignee
- created_by
- priority
- relevant repo paths
- constraints

Add artifacts when there are reports, screenshots, or generated files Claude Code should inspect.

## Response Content

Every response should include:

- summary
- status
- files_touched
- questions when blocked or uncertain
- next_steps when handoff is incomplete

## Recommended Ownership Pattern

- Codex creates the bounded task and names the write scope.
- Claude Code works only inside that scope or raises a question first.
- Codex reviews the response and integrates or follows up.

## Why This Bridge Exists

This keeps both agents aligned even when they run in different tools or sessions.
The repo becomes the shared source of truth instead of relying on ephemeral chat context.

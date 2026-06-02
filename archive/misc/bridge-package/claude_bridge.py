#!/usr/bin/env python3
"""
claude_bridge.py — Portable Codex ↔ Claude Code collaboration bridge.

Drop this single file anywhere. No external dependencies (stdlib only).

QUICKSTART (in any project):
    python claude_bridge.py install          # scaffold bridge dirs + CLAUDE.md
    python claude_bridge.py create-task --title "..." --request "..."
    python claude_bridge.py list
    python claude_bridge.py respond --task-id <id> --agent claude-code --summary "..."
    python claude_bridge.py close --task-id <id> --resolution "..."

HOW IT WORKS:
    Codex creates tasks → writes to bridges/claude-code/tasks/
    Claude reads tasks → claims → works → writes response to bridges/claude-code/responses/
    Codex reads responses → integrates → closes tasks

Both agents share the same repo files. The bridge is just coordination metadata.
No network calls. No hidden state. Everything is plain JSON + Markdown.
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path


# ── Default bridge root (relative to CWD when script runs) ──
# Override with --bridge-root if needed.
DEFAULT_BRIDGE_ROOT = Path("bridges") / "claude-code"


def utc_now():
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def slugify(value):
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug[:60] or "task"


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, data):
    Path(path).write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def get_dirs(bridge_root):
    root = Path(bridge_root)
    return {
        "tasks":     root / "tasks",
        "responses": root / "responses",
        "archive":   root / "archive",
    }


def ensure_dirs(bridge_root):
    for path in get_dirs(bridge_root).values():
        path.mkdir(parents=True, exist_ok=True)


def task_json_path(bridge_root, task_id):
    return get_dirs(bridge_root)["tasks"] / f"{task_id}.json"


def task_md_path(bridge_root, task_id):
    return get_dirs(bridge_root)["tasks"] / f"{task_id}.md"


def load_task(bridge_root, task_id):
    path = task_json_path(bridge_root, task_id)
    if not path.exists():
        raise FileNotFoundError(f"Task not found: {task_id}\nLooked at: {path}")
    return read_json(path)


def save_task(bridge_root, task):
    task["updated_at"] = utc_now()
    write_json(task_json_path(bridge_root, task["task_id"]), task)
    task_md_path(bridge_root, task["task_id"]).write_text(
        render_task_markdown(task), encoding="utf-8"
    )


def render_task_markdown(task):
    lines = [
        f"# Bridge Task: {task['title']}",
        "",
        f"- **task_id**: `{task['task_id']}`",
        f"- **status**: `{task['status']}`",
        f"- **created_by**: `{task['created_by']}`",
        f"- **assignee**: `{task['assignee']}`",
        f"- **priority**: `{task['priority']}`",
        f"- **created_at**: `{task['created_at']}`",
    ]
    if task.get("updated_at"):
        lines.append(f"- **updated_at**: `{task['updated_at']}`")
    lines += ["", "## Request", "", task["request"]]
    if task.get("context"):
        lines += ["", "## Context", "", task["context"]]
    if task.get("constraints"):
        lines += ["", "## Constraints", ""]
        lines += [f"- {c}" for c in task["constraints"]]
    if task.get("paths"):
        lines += ["", "## Paths", ""]
        lines += [f"- `{p}`" for p in task["paths"]]
    if task.get("artifacts"):
        lines += ["", "## Artifacts", ""]
        lines += [f"- `{a}`" for a in task["artifacts"]]
    lines += [
        "",
        "## Claude Response Protocol",
        "",
        "1. Claim this task before starting.",
        "2. Work only within the stated file scope.",
        "3. Write a response (summary, touched files, questions) when done.",
        "4. If blocked, respond with status `blocked` and list the blockers.",
    ]
    return "\n".join(lines) + "\n"


def render_response_markdown(response):
    lines = [
        f"# Bridge Response: {response['task_id']}",
        "",
        f"- **response_id**: `{response['response_id']}`",
        f"- **agent**: `{response['agent']}`",
        f"- **status**: `{response['status']}`",
        f"- **created_at**: `{response['created_at']}`",
        "",
        "## Summary",
        "",
        response["summary"],
    ]
    if response.get("files_touched"):
        lines += ["", "## Files Touched", ""]
        lines += [f"- `{f}`" for f in response["files_touched"]]
    if response.get("artifacts"):
        lines += ["", "## Artifacts", ""]
        lines += [f"- `{a}`" for a in response["artifacts"]]
    if response.get("questions"):
        lines += ["", "## Questions", ""]
        lines += [f"- {q}" for q in response["questions"]]
    if response.get("next_steps"):
        lines += ["", "## Next Steps", ""]
        lines += [f"- {s}" for s in response["next_steps"]]
    return "\n".join(lines) + "\n"


# ── Commands ──

def cmd_install(args):
    """Bootstrap the bridge into a project directory."""
    project = Path(args.project_root).resolve()
    bridge_root = project / args.bridge_path

    ensure_dirs(bridge_root)
    print(f"Bridge directories created under: {bridge_root}")

    # Write CLAUDE.md at project root (or append if exists)
    claude_md = project / "CLAUDE.md"
    bridge_section = _claude_md_section(args.bridge_path)

    if claude_md.exists():
        existing = claude_md.read_text(encoding="utf-8")
        if "Bridge Protocol" in existing:
            print(f"CLAUDE.md already has bridge section — skipping ({claude_md})")
        else:
            claude_md.write_text(existing.rstrip() + "\n\n" + bridge_section, encoding="utf-8")
            print(f"Appended bridge section to: {claude_md}")
    else:
        claude_md.write_text(bridge_section, encoding="utf-8")
        print(f"Created: {claude_md}")

    print("\nDone. Next steps:")
    print(f"  python claude_bridge.py --bridge-root {bridge_root} create-task --title '...' --request '...'")


def _claude_md_section(bridge_path):
    return f"""# Collaboration Bridge

This repository uses a file-based bridge so Codex and Claude Code can coordinate work.

## Bridge Protocol

Task and response files live under `{bridge_path}/`:
- `tasks/` — open collaboration requests from Codex
- `responses/` — Claude Code's completed handoff notes

Use the bridge script to manage tasks:

```bash
python claude_bridge.py list
python claude_bridge.py show --task-id <task-id>
python claude_bridge.py claim --task-id <task-id> --agent claude-code
python claude_bridge.py respond --task-id <task-id> --agent claude-code --summary "..."
```

## Collaboration Rules

- Read the task's stated file scope before starting work.
- Do not overwrite unrelated files.
- If a task is ambiguous, respond with `--status blocked` and list your questions.
- Record every file you touch in `--file-touched`.
- The repo is the shared source of truth. Do not rely on hidden chat context.
"""


def cmd_create(args):
    br = args.bridge_root
    ensure_dirs(br)
    timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    task_id = f"{timestamp}-{slugify(args.title)}"
    task = {
        "task_id":    task_id,
        "title":      args.title,
        "request":    args.request,
        "context":    args.context or "",
        "constraints": args.constraint or [],
        "paths":      args.path or [],
        "artifacts":  args.artifact or [],
        "created_by": args.created_by,
        "assignee":   args.assignee,
        "priority":   args.priority,
        "status":     "open",
        "created_at": utc_now(),
        "updated_at": utc_now(),
        "responses":  [],
    }
    save_task(br, task)
    print(f"Created task: {task_id}")
    print(f"  {task_md_path(br, task_id)}")


def cmd_list(args):
    br = args.bridge_root
    ensure_dirs(br)
    tasks_dir = get_dirs(br)["tasks"]
    rows = []
    for path in sorted(tasks_dir.glob("*.json")):
        task = read_json(path)
        if args.status and task.get("status") != args.status:
            continue
        if args.assignee and task.get("assignee") != args.assignee:
            continue
        rows.append(task)
    if not rows:
        print("No matching tasks.")
        return
    for t in rows:
        print(f"[{t['status']:10}] {t['task_id']}  →  {t['title']}")


def cmd_show(args):
    task = load_task(args.bridge_root, args.task_id)
    print(json.dumps(task, indent=2))


def cmd_claim(args):
    br = args.bridge_root
    task = load_task(br, args.task_id)
    task["status"] = "claimed"
    task["assignee"] = args.agent
    save_task(br, task)
    print(f"Claimed {args.task_id} for {args.agent}")


def cmd_respond(args):
    br = args.bridge_root
    ensure_dirs(br)
    task = load_task(br, args.task_id)
    timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    response_id = f"{args.task_id}--{slugify(args.agent)}--{timestamp}"
    response = {
        "response_id":  response_id,
        "task_id":      args.task_id,
        "agent":        args.agent,
        "created_at":   utc_now(),
        "status":       args.status,
        "summary":      args.summary,
        "files_touched": args.file_touched or [],
        "artifacts":    args.artifact or [],
        "questions":    args.question or [],
        "next_steps":   args.next_step or [],
    }
    responses_dir = get_dirs(br)["responses"]
    json_path = responses_dir / f"{response_id}.json"
    md_path   = responses_dir / f"{response_id}.md"
    write_json(json_path, response)
    md_path.write_text(render_response_markdown(response), encoding="utf-8")
    task.setdefault("responses", []).append(str(json_path))
    task["status"] = args.status
    save_task(br, task)
    print(f"Wrote response: {response_id}")
    print(f"  {md_path}")


def cmd_close(args):
    br = args.bridge_root
    task = load_task(br, args.task_id)
    task["status"] = "closed"
    task["closed_by"] = args.closed_by
    task["resolution"] = args.resolution
    save_task(br, task)
    print(f"Closed: {args.task_id}")


def cmd_render_prompt(args):
    task = load_task(args.bridge_root, args.task_id)
    lines = [
        f"You are working on bridge task `{task['task_id']}` in this repository.",
        f"Title: {task['title']}",
        "",
        "## Request",
        "",
        task["request"],
    ]
    if task.get("context"):
        lines += ["", "## Context", "", task["context"]]
    if task.get("constraints"):
        lines += ["", "## Constraints", ""]
        lines += [f"- {c}" for c in task["constraints"]]
    if task.get("paths"):
        lines += ["", "## Relevant Paths", ""]
        lines += [f"- {p}" for p in task["paths"]]
    lines += [
        "",
        "When done, write a bridge response: summary, touched files, any open questions.",
    ]
    print("\n".join(lines))


# ── Parser ──

def build_parser():
    parser = argparse.ArgumentParser(
        description="Codex ↔ Claude Code collaboration bridge.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--bridge-root",
        default=str(DEFAULT_BRIDGE_ROOT),
        help=f"Bridge directory (default: {DEFAULT_BRIDGE_ROOT})",
    )
    subs = parser.add_subparsers(dest="command", required=True)

    # install
    p = subs.add_parser("install", help="Bootstrap bridge into a project.")
    p.add_argument("--project-root", default=".", help="Target project root (default: .)")
    p.add_argument("--bridge-path", default="bridges/claude-code", help="Bridge sub-path inside project.")
    p.set_defaults(func=cmd_install)

    # create-task
    p = subs.add_parser("create-task", help="Create a new task for Claude Code.")
    p.add_argument("--title",      required=True)
    p.add_argument("--request",    required=True)
    p.add_argument("--context",    default="")
    p.add_argument("--created-by", default="codex")
    p.add_argument("--assignee",   default="claude-code")
    p.add_argument("--priority",   choices=["low", "normal", "high"], default="normal")
    p.add_argument("--constraint", action="append", metavar="TEXT")
    p.add_argument("--path",       action="append", metavar="FILE")
    p.add_argument("--artifact",   action="append", metavar="FILE")
    p.set_defaults(func=cmd_create)

    # list
    p = subs.add_parser("list", help="List tasks.")
    p.add_argument("--status")
    p.add_argument("--assignee")
    p.set_defaults(func=cmd_list)

    # show
    p = subs.add_parser("show", help="Print a task as JSON.")
    p.add_argument("--task-id", required=True)
    p.set_defaults(func=cmd_show)

    # claim
    p = subs.add_parser("claim", help="Claim a task (mark it in-progress).")
    p.add_argument("--task-id", required=True)
    p.add_argument("--agent",   required=True)
    p.set_defaults(func=cmd_claim)

    # respond
    p = subs.add_parser("respond", help="Write a response to a task.")
    p.add_argument("--task-id",      required=True)
    p.add_argument("--agent",        required=True)
    p.add_argument("--summary",      required=True)
    p.add_argument("--status",       choices=["answered", "blocked", "needs-review"], default="answered")
    p.add_argument("--file-touched", action="append", metavar="FILE")
    p.add_argument("--artifact",     action="append", metavar="FILE")
    p.add_argument("--question",     action="append", metavar="TEXT")
    p.add_argument("--next-step",    action="append", metavar="TEXT")
    p.set_defaults(func=cmd_respond)

    # close
    p = subs.add_parser("close", help="Close a task after integrating the result.")
    p.add_argument("--task-id",    required=True)
    p.add_argument("--resolution", required=True)
    p.add_argument("--closed-by",  default="codex")
    p.set_defaults(func=cmd_close)

    # render-prompt
    p = subs.add_parser("render-prompt", help="Print a task as a Claude-friendly prompt.")
    p.add_argument("--task-id", required=True)
    p.set_defaults(func=cmd_render_prompt)

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    # Resolve bridge_root relative to CWD
    args.bridge_root = Path(args.bridge_root)
    args.func(args)


if __name__ == "__main__":
    main()

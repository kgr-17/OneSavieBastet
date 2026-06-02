import argparse
import json
import re
from datetime import datetime
from pathlib import Path


BRIDGE_ROOT = Path("bridges") / "claude-code"
TASKS_DIR = BRIDGE_ROOT / "tasks"
RESPONSES_DIR = BRIDGE_ROOT / "responses"
ARCHIVE_DIR = BRIDGE_ROOT / "archive"


def utc_now():
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def ensure_dirs():
    for path in (TASKS_DIR, RESPONSES_DIR, ARCHIVE_DIR):
        path.mkdir(parents=True, exist_ok=True)


def slugify(value):
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "task"


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, data):
    Path(path).write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def task_json_path(task_id):
    return TASKS_DIR / f"{task_id}.json"


def task_md_path(task_id):
    return TASKS_DIR / f"{task_id}.md"


def load_task(task_id):
    path = task_json_path(task_id)
    if not path.exists():
        raise FileNotFoundError(f"Task not found: {task_id}")
    return read_json(path)


def save_task(task):
    task["updated_at"] = utc_now()
    write_json(task_json_path(task["task_id"]), task)
    Path(task_md_path(task["task_id"])).write_text(render_task_markdown(task), encoding="utf-8")


def render_task_markdown(task):
    lines = [
        f"# Bridge Task: {task['title']}",
        "",
        f"- task_id: `{task['task_id']}`",
        f"- status: `{task['status']}`",
        f"- created_by: `{task['created_by']}`",
        f"- assignee: `{task['assignee']}`",
        f"- priority: `{task['priority']}`",
        f"- created_at: `{task['created_at']}`",
    ]
    if task.get("updated_at"):
        lines.append(f"- updated_at: `{task['updated_at']}`")
    lines.extend([
        "",
        "## Request",
        "",
        task["request"],
    ])
    if task.get("context"):
        lines.extend(["", "## Context", "", task["context"]])
    if task.get("constraints"):
        lines.extend(["", "## Constraints", ""])
        for item in task["constraints"]:
            lines.append(f"- {item}")
    if task.get("paths"):
        lines.extend(["", "## Paths", ""])
        for item in task["paths"]:
            lines.append(f"- `{item}`")
    if task.get("artifacts"):
        lines.extend(["", "## Artifacts", ""])
        for item in task["artifacts"]:
            lines.append(f"- `{item}`")
    lines.extend([
        "",
        "## Claude Response Protocol",
        "",
        "1. Claim the task if you are starting work.",
        "2. Work only inside the files needed for the request.",
        "3. Write a response using the bridge script when done.",
        "4. Include touched files, summary, and open questions.",
    ])
    return "\n".join(lines) + "\n"


def render_response_markdown(response):
    lines = [
        f"# Bridge Response: {response['task_id']}",
        "",
        f"- response_id: `{response['response_id']}`",
        f"- task_id: `{response['task_id']}`",
        f"- agent: `{response['agent']}`",
        f"- created_at: `{response['created_at']}`",
        f"- status: `{response['status']}`",
        "",
        "## Summary",
        "",
        response["summary"],
    ]
    if response.get("files_touched"):
        lines.extend(["", "## Files Touched", ""])
        for item in response["files_touched"]:
            lines.append(f"- `{item}`")
    if response.get("artifacts"):
        lines.extend(["", "## Artifacts", ""])
        for item in response["artifacts"]:
            lines.append(f"- `{item}`")
    if response.get("questions"):
        lines.extend(["", "## Questions", ""])
        for item in response["questions"]:
            lines.append(f"- {item}")
    if response.get("next_steps"):
        lines.extend(["", "## Next Steps", ""])
        for item in response["next_steps"]:
            lines.append(f"- {item}")
    return "\n".join(lines) + "\n"


def response_paths(response_id):
    return RESPONSES_DIR / f"{response_id}.json", RESPONSES_DIR / f"{response_id}.md"


def list_tasks(args):
    ensure_dirs()
    rows = []
    for path in sorted(TASKS_DIR.glob("*.json")):
        task = read_json(path)
        if args.status and task.get("status") != args.status:
            continue
        if args.assignee and task.get("assignee") != args.assignee:
            continue
        rows.append(task)
    if not rows:
        print("No matching tasks.")
        return
    for task in rows:
        print(f"{task['task_id']} | {task['status']} | {task['assignee']} | {task['title']}")


def create_task(args):
    ensure_dirs()
    timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    task_id = f"{timestamp}-{slugify(args.title)}"
    task = {
        "task_id": task_id,
        "title": args.title,
        "request": args.request,
        "context": args.context or "",
        "constraints": args.constraint or [],
        "paths": args.path or [],
        "artifacts": args.artifact or [],
        "created_by": args.created_by,
        "assignee": args.assignee,
        "priority": args.priority,
        "status": "open",
        "created_at": utc_now(),
        "updated_at": utc_now(),
        "responses": [],
    }
    save_task(task)
    print(f"Created task: {task_id}")
    print(task_md_path(task_id))


def show_task(args):
    task = load_task(args.task_id)
    print(json.dumps(task, indent=2))


def claim_task(args):
    task = load_task(args.task_id)
    task["status"] = "claimed"
    task["assignee"] = args.agent
    save_task(task)
    print(f"Claimed task {args.task_id} for {args.agent}")


def respond_task(args):
    ensure_dirs()
    task = load_task(args.task_id)
    timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    response_id = f"{args.task_id}--{slugify(args.agent)}--{timestamp}"
    response = {
        "response_id": response_id,
        "task_id": args.task_id,
        "agent": args.agent,
        "created_at": utc_now(),
        "status": args.status,
        "summary": args.summary,
        "files_touched": args.file_touched or [],
        "artifacts": args.artifact or [],
        "questions": args.question or [],
        "next_steps": args.next_step or [],
    }
    json_path, md_path = response_paths(response_id)
    write_json(json_path, response)
    md_path.write_text(render_response_markdown(response), encoding="utf-8")
    task.setdefault("responses", []).append(str(json_path))
    task["status"] = args.status
    save_task(task)
    print(f"Wrote response: {response_id}")
    print(md_path)


def close_task(args):
    task = load_task(args.task_id)
    task["status"] = "closed"
    task["closed_by"] = args.closed_by
    task["resolution"] = args.resolution
    save_task(task)
    print(f"Closed task {args.task_id}")


def render_prompt(args):
    task = load_task(args.task_id)
    prompt = [
        f"You are working on bridge task {task['task_id']} in this repository.",
        f"Title: {task['title']}",
        "",
        "Request:",
        task['request'],
    ]
    if task.get("context"):
        prompt.extend(["", "Context:", task["context"]])
    if task.get("constraints"):
        prompt.extend(["", "Constraints:"])
        prompt.extend(f"- {item}" for item in task["constraints"])
    if task.get("paths"):
        prompt.extend(["", "Relevant paths:"])
        prompt.extend(f"- {item}" for item in task["paths"])
    prompt.extend([
        "",
        "When you finish, write a bridge response with summary, touched files, and open questions.",
    ])
    print("\n".join(prompt))

def init_bridge(_args):
    ensure_dirs()
    print(f"Bridge root: {BRIDGE_ROOT.resolve()}")


def build_parser():
    parser = argparse.ArgumentParser(description="Shared Codex-Claude Code bridge for repo collaboration.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Create bridge directories.")
    init_parser.set_defaults(func=init_bridge)

    create_parser = subparsers.add_parser("create-task", help="Create a new collaboration task.")
    create_parser.add_argument("--title", required=True)
    create_parser.add_argument("--request", required=True)
    create_parser.add_argument("--context", default="")
    create_parser.add_argument("--created-by", default="codex")
    create_parser.add_argument("--assignee", default="claude-code")
    create_parser.add_argument("--priority", choices=["low", "normal", "high"], default="normal")
    create_parser.add_argument("--constraint", action="append")
    create_parser.add_argument("--path", action="append")
    create_parser.add_argument("--artifact", action="append")
    create_parser.set_defaults(func=create_task)

    list_parser = subparsers.add_parser("list", help="List bridge tasks.")
    list_parser.add_argument("--status")
    list_parser.add_argument("--assignee")
    list_parser.set_defaults(func=list_tasks)

    show_parser = subparsers.add_parser("show", help="Show a task JSON payload.")
    show_parser.add_argument("--task-id", required=True)
    show_parser.set_defaults(func=show_task)

    claim_parser = subparsers.add_parser("claim", help="Claim a task for an agent.")
    claim_parser.add_argument("--task-id", required=True)
    claim_parser.add_argument("--agent", required=True)
    claim_parser.set_defaults(func=claim_task)

    respond_parser = subparsers.add_parser("respond", help="Write a response for a task.")
    respond_parser.add_argument("--task-id", required=True)
    respond_parser.add_argument("--agent", required=True)
    respond_parser.add_argument("--summary", required=True)
    respond_parser.add_argument("--status", choices=["answered", "blocked", "needs-review"], default="answered")
    respond_parser.add_argument("--file-touched", action="append")
    respond_parser.add_argument("--artifact", action="append")
    respond_parser.add_argument("--question", action="append")
    respond_parser.add_argument("--next-step", action="append")
    respond_parser.set_defaults(func=respond_task)

    close_parser = subparsers.add_parser("close", help="Close a task after the result is integrated.")
    close_parser.add_argument("--task-id", required=True)
    close_parser.add_argument("--closed-by", default="codex")
    close_parser.add_argument("--resolution", required=True)
    close_parser.set_defaults(func=close_task)

    prompt_parser = subparsers.add_parser("render-prompt", help="Render a task as a Claude-friendly prompt.")
    prompt_parser.add_argument("--task-id", required=True)
    prompt_parser.set_defaults(func=render_prompt)

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()

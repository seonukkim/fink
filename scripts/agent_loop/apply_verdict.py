#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import argparse

from scripts.agent_loop._common import (
    BACKLOG_PATH,
    STATE_PATH,
    dump_yaml,
    load_backlog,
    load_json,
    load_state,
    main_wrapper,
    now_utc,
    task_map,
    write_json,
    write_text,
)


def refresh_ready(backlog: dict[str, object]) -> None:
    tasks = task_map(backlog)  # type: ignore[arg-type]
    for task in tasks.values():
        if task.get("status") in {"DONE", "BLOCKED"}:
            continue
        deps = [str(dep) for dep in task.get("depends_on", [])]
        if all(str(tasks.get(dep, {}).get("status")) == "DONE" for dep in deps):
            task["status"] = "READY"


def run() -> None:
    parser = argparse.ArgumentParser(description="Apply a Claude verdict to loop state.")
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--review-json", required=True)
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--gates-ok", action="store_true")
    args = parser.parse_args()

    review = load_json(Path(args.review_json))
    verdict = review.get("verdict")
    backlog = load_backlog()
    tasks = task_map(backlog)
    if args.task_id not in tasks:
        raise SystemExit(f"unknown task id: {args.task_id}")
    task = tasks[args.task_id]
    state = load_state()

    if verdict == "APPROVE" and args.gates_ok:
        task["status"] = "DONE"
        task["completed_at"] = now_utc()
        state["active_task"] = None
        state["path_locks"] = {}
        state["last_verdict"] = verdict
        state["last_run_dir"] = str(Path(args.run_dir))
        refresh_ready(backlog)
    elif verdict == "BLOCKED":
        task["status"] = "BLOCKED"
        task["blocked_reason"] = review.get("summary", "Claude returned BLOCKED")
        state["active_task"] = None
        state["path_locks"] = {}
        state["last_verdict"] = verdict
        state["last_run_dir"] = str(Path(args.run_dir))
    else:
        state["last_verdict"] = verdict
        state["last_run_dir"] = str(Path(args.run_dir))

    write_text(BACKLOG_PATH, dump_yaml(backlog))
    write_json(STATE_PATH, state)


if __name__ == "__main__":
    main_wrapper(run)

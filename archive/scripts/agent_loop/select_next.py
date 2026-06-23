#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import argparse
import json

from scripts.agent_loop._common import (
    Eligibility,
    gate_approved,
    load_backlog,
    load_human_gates,
    load_state,
    main_wrapper,
    parse_gate_ids,
    select_eligible_task,
    task_map,
)


def read_queue(path: str | None) -> set[str] | None:
    if not path:
        return None
    ids: set[str] = set()
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if text and not text.startswith("#"):
            ids.add(text)
    return ids


def explain_blocks(queue_ids: set[str] | None) -> list[tuple[str, list[str]]]:
    """List queue tasks whose only remaining blocker is a closed human gate.

    A task qualifies when it is READY and all of its dependencies are DONE, but
    at least one of its human gates is not approved. This is what the runner
    prints when a queue stops cleanly so the operator sees the exact gate to
    approve (rather than an opaque NO_ELIGIBLE_TASK).
    """
    backlog = load_backlog()
    gates = load_human_gates()
    tasks = task_map(backlog)
    ids = set(tasks) if queue_ids is None else queue_ids
    blocked: list[tuple[str, list[str]]] = []
    for task_id in sorted(ids):
        task = tasks.get(task_id)
        if task is None or str(task.get("status")) != "READY":
            continue
        deps = [str(dep) for dep in task.get("depends_on", [])]
        if any(str(tasks.get(dep, {}).get("status")) != "DONE" for dep in deps):
            continue
        closed = [g for g in parse_gate_ids(task.get("human_gate")) if not gate_approved(gates, g)]
        if closed:
            blocked.append((task_id, closed))
    return blocked


def serialize(selection: Eligibility | None) -> dict[str, object]:
    if selection is None:
        return {"selected": None, "reason": "no eligible task"}
    task = selection.task
    return {
        "selected": task["id"],
        "task": task,
        "selection_key": [task.get("priority"), task.get("scope"), task.get("id")],
    }


def run() -> None:
    parser = argparse.ArgumentParser(description="Select the next eligible FInk loop task.")
    parser.add_argument("--queue", help="Optional queue file limiting candidate task IDs.")
    parser.add_argument("--json", action="store_true", help="Emit JSON.")
    parser.add_argument(
        "--explain",
        action="store_true",
        help="Report queue tasks blocked only by a closed human gate, then exit.",
    )
    args = parser.parse_args()

    if args.explain:
        for task_id, gates in explain_blocks(read_queue(args.queue)):
            print(f"HUMAN_GATE_BLOCKED {task_id} {','.join(gates)}")
        return

    selection = select_eligible_task(
        load_backlog(),
        load_human_gates(),
        load_state(),
        queue_ids=read_queue(args.queue),
    )
    payload = serialize(selection)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    elif selection is None:
        print("NO_ELIGIBLE_TASK")
    else:
        print(selection.task["id"])


if __name__ == "__main__":
    main_wrapper(run)

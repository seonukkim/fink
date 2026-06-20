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
    load_backlog,
    load_human_gates,
    load_state,
    main_wrapper,
    select_eligible_task,
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
    args = parser.parse_args()

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

#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import argparse
import json

from scripts.agent_loop._common import (
    REPO_ROOT,
    load_backlog,
    load_human_gates,
    main_wrapper,
    read_text,
    task_map,
    write_json,
    write_text,
)

CONTEXT_FILES = [
    "docs/FINK_MASTER_SPEC.md",
    "docs/specs/09_ACCEPTANCE_CHECKLIST.md",
    "docs/specs/11_ASSUMPTIONS_OPEN_QUESTIONS.md",
    "loop/CHARTER.md",
    "loop/ACCEPTANCE.md",
    "loop/RUBRIC.md",
    "docs/privacy.md",
    "docs/limitations.md",
    "docs/ai-use-log.md",
]


def short_file(path: Path, max_chars: int = 12000) -> str:
    text = read_text(path)
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n\n[truncated by build_task_context.py]\n"


def run() -> None:
    parser = argparse.ArgumentParser(description="Build bounded task context for a loop run.")
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--run-dir", required=True)
    args = parser.parse_args()

    backlog = load_backlog()
    tasks = task_map(backlog)
    if args.task_id not in tasks:
        raise SystemExit(f"unknown task id: {args.task_id}")
    task = tasks[args.task_id]
    run_dir = Path(args.run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)

    write_json(run_dir / "task.json", task)
    gates = load_human_gates()
    sections = [
        "# Selected Task",
        json.dumps(task, ensure_ascii=False, indent=2),
        "# Human Gates",
        json.dumps(gates, ensure_ascii=False, indent=2),
    ]
    for rel_path in CONTEXT_FILES:
        path = REPO_ROOT / rel_path
        if path.exists():
            sections.extend([f"# {rel_path}", short_file(path)])
    spec_backlog = REPO_ROOT / "docs" / "specs" / "08_IMPLEMENTATION_BACKLOG.yaml"
    if spec_backlog.exists():
        sections.extend(["# docs/specs/08_IMPLEMENTATION_BACKLOG.yaml", short_file(spec_backlog)])
    write_text(run_dir / "selected_context.txt", "\n\n".join(sections) + "\n")


if __name__ == "__main__":
    main_wrapper(run)

#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import argparse
import json
import shutil
import subprocess

from scripts.agent_loop._common import (
    REPO_ROOT,
    SCHEMA_DIR,
    main_wrapper,
    read_text,
    validate_against_schema,
    write_json,
    write_text,
)

CODEX_RESULT_SCHEMA = SCHEMA_DIR / "codex_result.schema.json"


def emit_result(result_path: Path, result: dict[str, object]) -> None:
    """Validate a Codex result against its schema, then persist it."""
    error = validate_against_schema(result, CODEX_RESULT_SCHEMA)
    if error is not None:
        print(f"WARNING: codex_result.json failed schema validation: {error}", file=sys.stderr)
    write_json(result_path, result)


def render_prompt(template: str, context: str, task: str, mode: str) -> str:
    return (
        template.replace("{{MODE}}", mode)
        .replace("{{TASK_JSON}}", task)
        .replace("{{SELECTED_CONTEXT}}", context)
    )


def run() -> None:
    parser = argparse.ArgumentParser(description="Invoke Codex for a bounded loop task.")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--mode", choices=["builder", "repair"], default="builder")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    run_dir = Path(args.run_dir)
    task_json = read_text(run_dir / "task.json")
    context = read_text(run_dir / "selected_context.txt")
    template_name = "codex_builder.md" if args.mode == "builder" else "codex_repair.md"
    template = read_text(REPO_ROOT / "scripts" / "agent_loop" / "prompts" / template_name)
    prompt = render_prompt(template, context, task_json, args.mode)
    write_text(run_dir / "codex_prompt.md", prompt)

    events_path = run_dir / "codex_events.jsonl"
    result_path = run_dir / "codex_result.json"
    if args.dry_run:
        write_text(events_path, json.dumps({"event": "dry_run", "tool": "codex"}) + "\n")
        emit_result(
            result_path,
            {
                "status": "DRY_RUN",
                "summary": "Codex invocation skipped by --dry-run.",
                "changed_files": [],
                "tests_run": [],
                "blocked_reason": None,
            },
        )
        return

    codex = shutil.which("codex")
    if codex is None:
        emit_result(
            result_path,
            {
                "status": "BLOCKED",
                "summary": "codex CLI is not available.",
                "changed_files": [],
                "tests_run": [],
                "blocked_reason": "missing codex CLI",
            },
        )
        raise SystemExit(1)

    proc = subprocess.run(
        [
            codex,
            "exec",
            "--model",
            "gpt-5.5",
            "--reasoning-effort",
            "xhigh",
            "--json",
            prompt,
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    write_text(events_path, proc.stdout)
    if proc.returncode != 0:
        write_text(run_dir / "codex_stderr.log", proc.stderr)
        emit_result(
            result_path,
            {
                "status": "FAILED",
                "summary": "Codex CLI returned a non-zero exit status.",
                "changed_files": [],
                "tests_run": [],
                "blocked_reason": proc.stderr[-2000:],
            },
        )
        raise SystemExit(proc.returncode)
    write_json(
        result_path,
        {
            "status": "SUCCESS",
            "summary": "Codex run completed. See codex_events.jsonl.",
            "changed_files": [],
            "tests_run": [],
            "blocked_reason": None,
        },
    )


if __name__ == "__main__":
    main_wrapper(run)

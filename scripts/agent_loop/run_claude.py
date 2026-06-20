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

CLAUDE_REVIEW_SCHEMA = SCHEMA_DIR / "claude_review.schema.json"

REVIEW_FIELDS = [
    "verdict",
    "summary",
    "blocking_issues",
    "major_issues",
    "minor_issues",
    "fixes_applied",
    "required_codex_actions",
    "required_tests",
    "financial_reasoning_concerns",
    "legal_language_concerns",
    "authority_source_concerns",
    "privacy_copyright_concerns",
    "bilingual_concerns",
    "ui_concerns",
    "paper_claim_concerns",
    "changed_files",
    "confidence",
]


def empty_review(verdict: str, summary: str) -> dict[str, object]:
    review: dict[str, object] = {field: [] for field in REVIEW_FIELDS}
    review["verdict"] = verdict
    review["summary"] = summary
    review["confidence"] = "dry_run"
    return review


def emit_review(review_path: Path, review: object) -> None:
    """Validate a Claude review against its schema, then persist it.

    Mirrors run_codex.py: the structured result is schema-checked before it is
    written so a malformed review is flagged rather than silently consumed by the
    orchestrator. Validation is a no-op when ``jsonschema`` is unavailable."""
    error = validate_against_schema(review, CLAUDE_REVIEW_SCHEMA)
    if error is not None:
        print(f"WARNING: claude_review.json failed schema validation: {error}", file=sys.stderr)
    write_json(review_path, review)


def run() -> None:
    parser = argparse.ArgumentParser(description="Invoke Claude review/fix for a loop task.")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    run_dir = Path(args.run_dir)
    template = read_text(REPO_ROOT / "scripts" / "agent_loop" / "prompts" / "claude_review_fix.md")
    prompt = (
        template.replace("{{TASK_JSON}}", read_text(run_dir / "task.json"))
        .replace("{{SELECTED_CONTEXT}}", read_text(run_dir / "selected_context.txt"))
        .replace("{{CODEX_RESULT}}", read_text(run_dir / "codex_result.json"))
    )
    write_text(run_dir / "claude_prompt.md", prompt)

    if args.dry_run:
        emit_review(
            run_dir / "claude_review.json",
            empty_review("APPROVE", "Claude invocation skipped by --dry-run."),
        )
        return

    claude = shutil.which("claude")
    if claude is None:
        emit_review(
            run_dir / "claude_review.json",
            empty_review("BLOCKED", "claude CLI is not available."),
        )
        raise SystemExit(1)

    proc = subprocess.run(
        [
            claude,
            "-p",
            "--model",
            "claude-opus-4-8",
            "--effort",
            "max",
            "--permission-mode",
            "acceptEdits",
            "--output-format",
            "json",
            prompt,
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    write_text(run_dir / "claude_stdout.json", proc.stdout)
    write_text(run_dir / "claude_stderr.log", proc.stderr)
    if proc.returncode != 0:
        emit_review(
            run_dir / "claude_review.json",
            empty_review("BLOCKED", "Claude CLI returned a non-zero exit status."),
        )
        raise SystemExit(proc.returncode)
    try:
        parsed = json.loads(proc.stdout)
    except json.JSONDecodeError:
        parsed = empty_review("BLOCKED", "Claude did not return valid JSON.")
    emit_review(run_dir / "claude_review.json", parsed)


if __name__ == "__main__":
    main_wrapper(run)

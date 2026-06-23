#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import argparse
import json
import re
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


def _review_from_text(text: str) -> dict[str, object] | None:
    """Pull a review object out of free-form model text (fenced or bare JSON)."""
    candidates: list[str] = []
    fence = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    if fence:
        candidates.append(fence.group(1))
    candidates.append(text.strip())
    brace = re.search(r"\{.*\}", text, re.DOTALL)
    if brace:
        candidates.append(brace.group(0))
    for candidate in candidates:
        try:
            obj = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and "verdict" in obj:
            return obj
    return None


def _verdict_from_prose(text: str) -> str | None:
    """Recover the verdict when Claude only states it in prose.

    The agentic reviewer (acceptEdits, many turns) often writes the review JSON to
    the file itself and returns a prose summary like ``## Verdict: `APPROVE` ``.
    Anchor to a line that starts with "verdict" so a mid-sentence mention does not
    win.
    """
    match = re.search(
        r"(?im)^\W*verdict\W{0,8}(APPROVE|REQUEST_CHANGES|BLOCKED)\b", text
    )
    return match.group(1).upper() if match else None


def _load_disk_review(path: Path) -> dict[str, object] | None:
    """A schema-valid review Claude wrote to the file itself (agentic mode)."""
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(data, dict) or data.get("verdict") not in {
        "APPROVE",
        "REQUEST_CHANGES",
        "BLOCKED",
    }:
        return None
    if validate_against_schema(data, CLAUDE_REVIEW_SCHEMA) is not None:
        return None
    return data


def parse_review_payload(stdout: str) -> dict[str, object]:
    """Extract the review object from `claude -p --output-format json` output.

    That command wraps the model's answer in an envelope; the review JSON the
    model produced lives in the ``result`` string. Be tolerant of markdown
    fences or surrounding prose, and fall back to a BLOCKED review on any parse
    failure so the orchestrator rolls back rather than acting on a missing
    verdict.
    """
    try:
        envelope = json.loads(stdout)
    except json.JSONDecodeError:
        return empty_review("BLOCKED", "Claude did not return a valid JSON envelope.")
    # Defensive: the model output was already the bare review object.
    if isinstance(envelope, dict) and "verdict" in envelope:
        return envelope
    if isinstance(envelope, dict) and envelope.get("is_error"):
        return empty_review("BLOCKED", f"Claude CLI error: {envelope.get('subtype', 'unknown')}.")
    text = envelope.get("result", "") if isinstance(envelope, dict) else str(envelope)
    review = _review_from_text(str(text))
    if review is not None:
        return review
    prose = _verdict_from_prose(str(text))
    if prose is not None:
        return empty_review(prose, "Verdict parsed from Claude prose summary.")
    return empty_review("BLOCKED", "Claude response contained no parseable review JSON.")


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
    # Agentic Claude may write the full, schema-valid review to the file itself;
    # prefer that, otherwise recover the verdict from the stdout envelope/summary.
    parsed = _load_disk_review(run_dir / "claude_review.json")
    if parsed is None:
        parsed = parse_review_payload(proc.stdout)
    emit_review(run_dir / "claude_review.json", parsed)


if __name__ == "__main__":
    main_wrapper(run)

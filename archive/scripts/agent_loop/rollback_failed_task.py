#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import argparse
import json

from scripts.agent_loop._common import REPO_ROOT, git, main_wrapper, write_text


def safe_allowed(path: str) -> str:
    clean = path.strip()
    if not clean or clean.startswith("/") or ".." in Path(clean).parts or clean == ".":
        raise SystemExit(f"unsafe allowed path: {path!r}")
    return clean.rstrip("/")


def remove_untracked_under(path: str) -> None:
    out = git(["ls-files", "--others", "--exclude-standard", "--", path]).stdout
    for line in out.splitlines():
        rel = line.strip()
        if not rel:
            continue
        target = (REPO_ROOT / rel).resolve()
        if not str(target).startswith(str(REPO_ROOT.resolve()) + "/"):
            raise SystemExit(f"refusing to remove outside repo: {target}")
        if target.is_file() or target.is_symlink():
            target.unlink()
    # Prune empty directories under the allowed path only.
    root = REPO_ROOT / path
    if root.exists() and root.is_dir():
        for child in sorted(root.rglob("*"), reverse=True):
            if child.is_dir():
                try:
                    child.rmdir()
                except OSError:
                    pass


def rollback_task(task: dict[str, object], base_commit: str, run_dir: Path, status: str) -> None:
    allowed = [safe_allowed(str(path)) for path in task.get("allowed_paths", [])]
    if not allowed:
        raise SystemExit("task has no allowed_paths; refusing rollback")
    run_dir.mkdir(parents=True, exist_ok=True)

    diff = git(["diff", "--binary", base_commit, "--", *allowed]).stdout
    write_text(run_dir / "BASE_COMMIT.txt", base_commit + "\n")
    write_text(run_dir / "FAILED.patch", diff)
    write_text(run_dir / "FAILED.status", status + "\n")

    for path in allowed:
        # Restore per-path and tolerate failure: an allowed path the task newly
        # created has nothing tracked to restore (only untracked files, removed
        # below). A single combined `git restore` aborts the whole rollback if ANY
        # pathspec matches no tracked file at base.
        git(["restore", "--source", base_commit, "--", path], check=False, capture=True)
    for path in allowed:
        remove_untracked_under(path)


def run() -> None:
    parser = argparse.ArgumentParser(description="Rollback a failed task within its allowed paths.")
    parser.add_argument("--task-json", required=True)
    parser.add_argument("--base-commit", required=True)
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--status", default="BLOCKED")
    args = parser.parse_args()

    task = json.loads(Path(args.task_json).read_text(encoding="utf-8"))
    rollback_task(task, args.base_commit, Path(args.run_dir), args.status)


if __name__ == "__main__":
    main_wrapper(run)

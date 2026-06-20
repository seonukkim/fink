from __future__ import annotations

import csv
import hashlib
import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
RUN_ROOT = REPO_ROOT / ".fink" / "runs"
STATE_PATH = REPO_ROOT / "loop" / "STATE.json"
BACKLOG_PATH = REPO_ROOT / "loop" / "BACKLOG.yaml"
HUMAN_GATES_PATH = REPO_ROOT / "loop" / "HUMAN_GATES.yaml"
SCHEMA_DIR = REPO_ROOT / "scripts" / "agent_loop" / "schemas"

PRIORITY_ORDER = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
SCOPE_ORDER = {"S": 0, "M": 1, "L": 2}


class LoopError(RuntimeError):
    """Raised for expected loop failures with a user-readable message."""


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def require_repo_root() -> None:
    if not (REPO_ROOT / ".git").exists():
        raise LoopError(f"not a git repository: {REPO_ROOT}")


def rel(path: Path) -> str:
    return path.resolve().relative_to(REPO_ROOT).as_posix()


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def validate_against_schema(data: Any, schema_path: Path) -> str | None:
    """Validate ``data`` against a JSON Schema file.

    Returns ``None`` when the data is valid *or* when ``jsonschema`` is not
    installed (the loop must keep working in the offline fallback environment).
    Otherwise returns a one-line validation error message.
    """
    try:
        import jsonschema  # type: ignore[import-untyped]
    except Exception:  # pragma: no cover - offline fallback
        return None
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    try:
        jsonschema.validate(data, schema)
    except jsonschema.ValidationError as exc:  # type: ignore[attr-defined]
        return str(exc).splitlines()[0]
    return None


def write_json(path: Path, data: Any) -> None:
    write_text(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def load_yaml(path: Path) -> Any:
    try:
        import yaml  # type: ignore[import-untyped]
    except Exception as exc:  # pragma: no cover - environment diagnostic
        raise LoopError("PyYAML is required for loop YAML files in this environment") from exc
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def dump_yaml(data: Any) -> str:
    try:
        import yaml  # type: ignore[import-untyped]
    except Exception as exc:  # pragma: no cover - environment diagnostic
        raise LoopError("PyYAML is required for loop YAML files in this environment") from exc
    return yaml.safe_dump(data, sort_keys=False, allow_unicode=True)


def git(
    args: list[str], *, check: bool = True, capture: bool = True
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        check=check,
        text=True,
        capture_output=capture,
    )


def current_branch() -> str:
    return git(["branch", "--show-current"]).stdout.strip()


def current_commit() -> str:
    return git(["rev-parse", "HEAD"]).stdout.strip()


def is_worktree_clean() -> bool:
    return git(["status", "--short"]).stdout.strip() == ""


def local_branches() -> list[str]:
    out = git(["for-each-ref", "--format=%(refname:short)", "refs/heads"]).stdout
    return [line.strip() for line in out.splitlines() if line.strip()]


def tracked_files() -> list[str]:
    out = git(["ls-files"]).stdout
    return [line.strip() for line in out.splitlines() if line.strip()]


def changed_files_since(base_commit: str) -> list[str]:
    out = git(["diff", "--name-only", base_commit, "--"]).stdout
    files = [line.strip() for line in out.splitlines() if line.strip()]
    untracked = git(["ls-files", "--others", "--exclude-standard"]).stdout
    files.extend(line.strip() for line in untracked.splitlines() if line.strip())
    return sorted(set(files))


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def icml_template_hashes() -> dict[str, str]:
    root = REPO_ROOT / "paper" / "template" / "icml2026"
    hashes: dict[str, str] = {}
    if not root.exists():
        return hashes
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        hashes[rel(path)] = sha256_file(path)
    return hashes


def parse_gate_ids(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    text = str(value).strip()
    if not text:
        return []
    parts = text.replace(",", ";").split(";")
    return [part.strip() for part in parts if part.strip()]


def load_backlog() -> dict[str, Any]:
    data = load_yaml(BACKLOG_PATH)
    if not isinstance(data, dict) or "tasks" not in data:
        raise LoopError("loop/BACKLOG.yaml must contain a tasks list")
    return data


def load_human_gates() -> dict[str, Any]:
    data = load_yaml(HUMAN_GATES_PATH)
    if not isinstance(data, dict):
        raise LoopError("loop/HUMAN_GATES.yaml must be a mapping")
    return data


def load_state() -> dict[str, Any]:
    return load_json(STATE_PATH)


def task_map(backlog: dict[str, Any]) -> dict[str, dict[str, Any]]:
    tasks = backlog.get("tasks", [])
    if not isinstance(tasks, list):
        raise LoopError("backlog tasks must be a list")
    result: dict[str, dict[str, Any]] = {}
    for task in tasks:
        if not isinstance(task, dict) or "id" not in task:
            raise LoopError("every task must be a mapping with id")
        result[str(task["id"])] = task
    return result


def gate_approved(gates: dict[str, Any], gate_id: str) -> bool:
    gate = gates.get("gates", {}).get(gate_id)
    if not isinstance(gate, dict):
        return False
    return bool(gate.get("approved") is True or str(gate.get("status", "")).upper() == "RESOLVED")


def allowed_path_matches(path: str, allowed_paths: list[str]) -> bool:
    clean = path.strip("/")
    for allowed in allowed_paths:
        prefix = str(allowed).strip("/")
        if not prefix:
            continue
        if clean == prefix or clean.startswith(prefix.rstrip("/") + "/"):
            return True
    return False


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


@dataclass(frozen=True)
class Eligibility:
    task: dict[str, Any]
    reason: str = ""


def select_eligible_task(
    backlog: dict[str, Any],
    gates: dict[str, Any],
    state: dict[str, Any],
    queue_ids: set[str] | None = None,
) -> Eligibility | None:
    tasks = task_map(backlog)
    if state.get("active_task"):
        return None
    locks = state.get("path_locks", {})
    candidates: list[dict[str, Any]] = []
    for task in tasks.values():
        task_id = str(task["id"])
        if queue_ids is not None and task_id not in queue_ids:
            continue
        if str(task.get("status")) != "READY":
            continue
        deps = [str(dep) for dep in task.get("depends_on", [])]
        if any(str(tasks.get(dep, {}).get("status")) != "DONE" for dep in deps):
            continue
        gate_ids = parse_gate_ids(task.get("human_gate"))
        if any(not gate_approved(gates, gate_id) for gate_id in gate_ids):
            continue
        allowed_paths = [str(path) for path in task.get("allowed_paths", [])]
        conflict = False
        for locked_path, locked_by in locks.items():
            if locked_by == task_id:
                continue
            if allowed_path_matches(str(locked_path), allowed_paths) or any(
                allowed_path_matches(path, [str(locked_path)]) for path in allowed_paths
            ):
                conflict = True
                break
        if conflict:
            continue
        candidates.append(task)
    if not candidates:
        return None
    candidates.sort(
        key=lambda item: (
            PRIORITY_ORDER.get(str(item.get("priority")), 99),
            SCOPE_ORDER.get(str(item.get("scope")), 99),
            str(item.get("id")),
        )
    )
    return Eligibility(candidates[0])


def main_wrapper(fn: Any) -> None:
    try:
        require_repo_root()
        fn()
    except LoopError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc

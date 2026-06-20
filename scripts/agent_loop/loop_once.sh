#!/usr/bin/env bash
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

dry_run=0
queue_file=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)
      dry_run=1
      shift
      ;;
    --queue)
      queue_file="${2:-}"
      shift 2
      ;;
    *)
      echo "unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

# Pass --dry-run to the sub-tools only when dry-run is actually requested.
# NOTE: a plain ${dry_run:+--dry-run} would expand for the string "0" too
# (it is non-null), which would silently force real runs into dry-run.
dry_flag=()
if [[ "$dry_run" == "1" ]]; then
  dry_flag=(--dry-run)
fi

mkdir -p .fink
lock_file=".fink/agent-loop.lock"

# The task body runs under the single global writer lock. When a parent runner
# (run_all_queues.sh) already holds that exact lock, it exports FINK_LOCK_HELD=1
# so this task does not deadlock by trying to re-acquire the same lock.
run_task() {
  if [[ -e loop/STOP ]]; then
    echo "STOP_REQUESTED: loop/STOP exists"
    exit 0
  fi

  branch="$(git branch --show-current)"
  if [[ "$branch" != "main" ]]; then
    echo "ERROR: current branch is $branch; expected main" >&2
    exit 1
  fi

  if [[ -n "$(git status --short)" ]]; then
    if [[ "$dry_run" == "1" ]]; then
      echo "DRY_RUN_NOTICE: worktree is dirty; real task runs require a clean tree"
    else
      echo "ERROR: worktree must be clean at task start" >&2
      exit 1
    fi
  fi

  BASE_COMMIT="$(git rev-parse HEAD)"
  if [[ "$dry_run" != "1" ]]; then
    export FINK_TASK_START=1
    bash scripts/agent_loop/run_gates.sh >/tmp/fink-task-start-gates.log
  fi

  select_args=(--json)
  if [[ -n "$queue_file" ]]; then
    select_args+=(--queue "$queue_file")
  fi
  selection_json="$(python3 scripts/agent_loop/select_next.py "${select_args[@]}")"
  task_id="$(python3 -c 'import json,sys; print(json.load(sys.stdin).get("selected") or "")' <<<"$selection_json")"
  if [[ -z "$task_id" ]]; then
    echo "NO_ELIGIBLE_TASK"
    exit 0
  fi

  run_id="$(date -u +%Y%m%dT%H%M%SZ)-${BASE_COMMIT:0:8}"
  task_run_dir=".fink/runs/${run_id}/${task_id}"
  mkdir -p "$task_run_dir"
  printf '%s\n' "$BASE_COMMIT" > "$task_run_dir/BASE_COMMIT.txt"
  printf '%s\n' "$selection_json" > "$task_run_dir/selection.json"

  # Activate the allowed-path scope gate for real runs. The clean-tree gate
  # guarantees that, at task start, the only post-BASE_COMMIT changes are the
  # ones Codex/Claude make, so this enforces edits stay inside allowed_paths.
  # Skipped in dry-run, where the worktree may legitimately be dirty.
  if [[ "$dry_run" != "1" ]]; then
    allowed_paths_env="$(python3 -c 'import json,os,sys
sel = json.load(sys.stdin)
task = sel.get("task") or {}
print(os.pathsep.join(str(p) for p in task.get("allowed_paths", [])))' <<<"$selection_json")"
    export FINK_BASE_COMMIT="$BASE_COMMIT"
    export FINK_ALLOWED_PATHS="$allowed_paths_env"
  fi

  for round in 1 2 3 4; do
    round_label="$(printf 'round-%02d' "$round")"
    run_dir="${task_run_dir}/${round_label}"
    mkdir -p "$run_dir"
    cp "$task_run_dir/BASE_COMMIT.txt" "$run_dir/BASE_COMMIT.txt"
    cp "$task_run_dir/selection.json" "$run_dir/selection.json"

    python3 scripts/agent_loop/build_task_context.py --task-id "$task_id" --run-dir "$run_dir"
    if [[ "$round" -eq 1 ]]; then
      python3 scripts/agent_loop/run_codex.py --run-dir "$run_dir" "${dry_flag[@]}"
    else
      python3 scripts/agent_loop/run_codex.py --run-dir "$run_dir" --mode repair
    fi
    bash scripts/agent_loop/run_gates.sh > "$run_dir/gates_after_codex.log"
    python3 scripts/agent_loop/run_claude.py --run-dir "$run_dir" "${dry_flag[@]}"
    bash scripts/agent_loop/run_gates.sh > "$run_dir/gates_after_claude.log"
    git diff --binary "$BASE_COMMIT" -- > "$run_dir/diff.patch"

    python3 - <<'PY' "$run_dir"
import json
import sys
from pathlib import Path

run_dir = Path(sys.argv[1])
review = json.loads((run_dir / "claude_review.json").read_text())
summary = [
    "# Loop Round Summary",
    "",
    f"- Verdict: `{review.get('verdict')}`",
    f"- Summary: {review.get('summary')}",
]
(run_dir / "summary.md").write_text("\n".join(summary) + "\n", encoding="utf-8")
PY

    if [[ "$dry_run" == "1" ]]; then
      echo "DRY_RUN_OK task=${task_id} run_dir=${run_dir}"
      exit 0
    fi

    verdict="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("verdict"))' "$run_dir/claude_review.json")"
    if [[ "$verdict" == "APPROVE" ]]; then
      python3 scripts/agent_loop/apply_verdict.py \
        --task-id "$task_id" \
        --review-json "$run_dir/claude_review.json" \
        --run-dir "$run_dir" \
        --gates-ok
      python3 scripts/agent_loop/update_loop_docs.py --loop-md
      bash scripts/agent_loop/git_checkpoint.sh "agent-loop: complete ${task_id}"
      exit 0
    fi

    if [[ "$verdict" == "BLOCKED" ]]; then
      python3 scripts/agent_loop/rollback_failed_task.py \
        --task-json "$run_dir/task.json" \
        --base-commit "$BASE_COMMIT" \
        --run-dir "$task_run_dir" \
        --status "BLOCKED"
      exit 1
    fi

    if [[ "$verdict" != "REQUEST_CHANGES" ]]; then
      python3 scripts/agent_loop/rollback_failed_task.py \
        --task-json "$run_dir/task.json" \
        --base-commit "$BASE_COMMIT" \
        --run-dir "$task_run_dir" \
        --status "${verdict:-BLOCKED}"
      exit 1
    fi
  done

  python3 scripts/agent_loop/rollback_failed_task.py \
    --task-json "$task_run_dir/round-04/task.json" \
    --base-commit "$BASE_COMMIT" \
    --run-dir "$task_run_dir" \
    --status "EXHAUSTED_REQUEST_CHANGES"
  exit 1
}

if [[ "${FINK_LOCK_HELD:-0}" == "1" ]]; then
  # Parent runner already holds the single writer lock; do not re-acquire it.
  run_task
else
  (
    flock -n 9 || {
      echo "ERROR: another loop run holds the writer lock" >&2
      exit 1
    }
    run_task
  ) 9>"$lock_file"
fi

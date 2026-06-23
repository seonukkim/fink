#!/usr/bin/env bash
# Drain the ENTIRE FInk backlog in one invocation.
#
# Difference from run_all_queues.sh:
#   - run_all_queues.sh runs the fixed queue files in order
#     (s0 -> models -> s1 -> s2 -> s3); it covers only those phases.
#   - run_backlog.sh repeatedly runs the UNQUEUED loop_once.sh, which selects the
#     next eligible task from the WHOLE backlog (every phase S0..S8 + MR) in
#     dependency / priority / scope order, until nothing is eligible.
#
# Both run under the single global writer lock (.fink/agent-loop.lock) and export
# FINK_LOCK_HELD=1 so the per-task loop_once.sh does not deadlock re-acquiring it.
#
# Usage:
#   bash scripts/agent_loop/run_backlog.sh --dry-run
#   bash scripts/agent_loop/run_backlog.sh --max-tasks 100
#   nohup bash scripts/agent_loop/run_backlog.sh --max-tasks 100 \
#     > .fink/backlog-loop.out 2>&1 &
#
# Behavior:
#   - stops immediately if loop/STOP exists
#   - stops on a blocked task or any non-zero loop result (never skips a failure)
#   - stops cleanly when no task is eligible, then names the human gate(s) that
#     block the remaining backlog tasks
#   - --max-tasks bounds the run (default 100); re-run to continue
#   - --dry-run runs exactly one iteration (a dry loop_once never advances state,
#     so looping would re-select the same task); no Codex/Claude/downloads/commits
#   - writes timestamped logs under .fink/runs/full-loop/<UTC>-backlog/
#   - never pushes; never approves a human gate
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

dry_run=0
max_tasks=100
while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)
      dry_run=1
      shift
      ;;
    --max-tasks)
      max_tasks="${2:-}"
      shift 2
      ;;
    *)
      echo "unknown argument: $1" >&2
      echo "usage: run_backlog.sh [--dry-run] [--max-tasks N]" >&2
      exit 2
      ;;
  esac
done

if [[ ! "$max_tasks" =~ ^[0-9]+$ ]]; then
  echo "ERROR: --max-tasks must be a non-negative integer" >&2
  exit 2
fi

dry_flag=()
if [[ "$dry_run" == "1" ]]; then
  dry_flag=(--dry-run)
fi

ts="$(date -u +%Y%m%dT%H%M%SZ)"
log_dir=".fink/runs/full-loop/${ts}-backlog"
mkdir -p "$log_dir"
summary_log="${log_dir}/summary.log"

mkdir -p .fink
lock_file=".fink/agent-loop.lock"

log() {
  printf '%s %s\n' "$(date -u +%H:%M:%SZ)" "$*" | tee -a "$summary_log"
}

(
  flock -n 9 || {
    echo "ERROR: another loop command holds the writer lock" >&2
    exit 1
  }

  # Children run under the lock this process holds.
  export FINK_LOCK_HELD=1

  log "BACKLOG_LOOP_START dry_run=${dry_run} max_tasks=${max_tasks} log_dir=${log_dir}"

  completed=0
  for ((i = 1; i <= max_tasks; i++)); do
    if [[ -e loop/STOP ]]; then
      log "STOP_REQUESTED after ${completed} task(s); halting cleanly"
      exit 0
    fi

    iter_log="${log_dir}/iter-$(printf '%03d' "$i").log"
    if ! bash scripts/agent_loop/loop_once.sh "${dry_flag[@]}" >"$iter_log" 2>&1; then
      log "TASK_FAILED at iteration ${i}; halting (no further task is run)"
      tail -n 20 "$iter_log" 2>/dev/null | sed 's/^/    /' | tee -a "$summary_log" || true
      exit 1
    fi
    cat "$iter_log" >>"$summary_log"

    if grep -q "NO_ELIGIBLE_TASK" "$iter_log"; then
      log "BACKLOG_DRAINED after ${completed} task(s): no further eligible task"
      blocked="$(python3 scripts/agent_loop/select_next.py --explain || true)"
      if [[ -n "$blocked" ]]; then
        log "Remaining backlog tasks blocked by human gate(s):"
        printf '%s\n' "$blocked" | while IFS= read -r line; do
          log "    ${line}"
        done
      fi
      exit 0
    fi

    if grep -q "STOP_REQUESTED" "$iter_log"; then
      log "STOP_REQUESTED during iteration ${i}; halting cleanly"
      exit 0
    fi

    completed=$((completed + 1))
    marker="$(grep -oE 'CHECKPOINT_COMMIT=[0-9a-f]+|DRY_RUN_OK task=[A-Z0-9-]+' "$iter_log" \
      | head -1 || true)"
    log "TASK_DONE #${completed} (${marker:-iteration ${i}})"

    if [[ "$dry_run" == "1" ]]; then
      log "DRY_RUN: single iteration only (real runs advance as tasks are committed)"
      exit 0
    fi
  done

  log "MAX_TASKS_REACHED max_tasks=${max_tasks} completed=${completed}; re-run to continue"
) 9>"$lock_file"

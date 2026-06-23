#!/usr/bin/env bash
# Sequential FInk queue runner.
#
# Runs the bounded task queues in their dependency order under ONE global writer
# lock (.fink/agent-loop.lock), the same lock loop_once.sh uses, so no other loop
# command can run concurrently. Children are told the lock is already held
# (FINK_LOCK_HELD=1) so they do not deadlock re-acquiring it.
#
# Usage:
#   bash scripts/agent_loop/run_all_queues.sh --dry-run
#   bash scripts/agent_loop/run_all_queues.sh --max-tasks-per-queue 20
#   nohup bash scripts/agent_loop/run_all_queues.sh --max-tasks-per-queue 20 &
#
# Behavior:
#   - order: queue.s0 -> queue.models -> queue.s1 -> queue.s2 -> queue.s3
#   - stops immediately if loop/STOP exists (prints which queue it stopped before)
#   - stops on a blocked task or any non-zero phase result (never skips a failure)
#   - on a clean stop, names the exact human gate(s) blocking each remaining queue
#   - writes timestamped logs under .fink/runs/full-loop/<UTC>/
#   - never pushes; never approves a human gate
#   - --dry-run never calls Codex/Claude, never downloads models, never commits
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

dry_run=0
max_tasks=50
while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)
      dry_run=1
      shift
      ;;
    --max-tasks-per-queue)
      max_tasks="${2:-}"
      shift 2
      ;;
    *)
      echo "unknown argument: $1" >&2
      echo "usage: run_all_queues.sh [--dry-run] [--max-tasks-per-queue N]" >&2
      exit 2
      ;;
  esac
done

if [[ ! "$max_tasks" =~ ^[0-9]+$ ]]; then
  echo "ERROR: --max-tasks-per-queue must be a non-negative integer" >&2
  exit 2
fi

queues=(
  scripts/agent_loop/queue.s0.txt
  scripts/agent_loop/queue.models.txt
  scripts/agent_loop/queue.s1.txt
  scripts/agent_loop/queue.s2.txt
  scripts/agent_loop/queue.s3.txt
)

dry_flag=()
if [[ "$dry_run" == "1" ]]; then
  dry_flag=(--dry-run)
fi

ts="$(date -u +%Y%m%dT%H%M%SZ)"
log_dir=".fink/runs/full-loop/${ts}"
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

  log "FULL_LOOP_START dry_run=${dry_run} max_tasks_per_queue=${max_tasks} log_dir=${log_dir}"

  for queue in "${queues[@]}"; do
    if [[ -e loop/STOP ]]; then
      log "STOP_REQUESTED before ${queue}; halting cleanly"
      exit 0
    fi

    queue_name="$(basename "$queue")"
    queue_log="${log_dir}/${queue_name}.log"
    log "QUEUE_START ${queue_name} (max ${max_tasks})"

    if ! bash scripts/agent_loop/loop_run.sh "$queue" "$max_tasks" "${dry_flag[@]}" \
        >"$queue_log" 2>&1; then
      log "QUEUE_FAILED ${queue_name}; halting (no later queue is run)"
      sed 's/^/    /' "$queue_log" | tee -a "$summary_log" >/dev/null
      tail -n 15 "$queue_log" || true
      exit 1
    fi

    cat "$queue_log" >>"$summary_log"

    # Surface any task in THIS queue that is now blocked solely by a closed human
    # gate, so the operator knows the exact gate to approve. Read-only.
    blocked="$(python3 scripts/agent_loop/select_next.py --queue "$queue" --explain || true)"
    if [[ -n "$blocked" ]]; then
      log "QUEUE_DONE ${queue_name}; human gate(s) block remaining tasks:"
      printf '%s\n' "$blocked" | while IFS= read -r line; do
        log "    ${line}"
      done
    else
      log "QUEUE_DONE ${queue_name}"
    fi
  done

  log "FULL_LOOP_DONE"
) 9>"$lock_file"

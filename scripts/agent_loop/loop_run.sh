#!/usr/bin/env bash
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

if [[ $# -lt 2 ]]; then
  echo "usage: loop_run.sh <queue-file> <max-runs> [--dry-run]" >&2
  exit 2
fi

queue_file="$1"
max_runs="$2"
shift 2

dry_args=()
if [[ "${1:-}" == "--dry-run" ]]; then
  dry_args+=(--dry-run)
fi

if [[ ! "$max_runs" =~ ^[0-9]+$ ]]; then
  echo "ERROR: max-runs must be an integer" >&2
  exit 2
fi

for ((i = 1; i <= max_runs; i++)); do
  if [[ -e loop/STOP ]]; then
    echo "STOP_REQUESTED"
    exit 0
  fi
  echo "LOOP_RUN iteration=$i queue=$queue_file"
  if ! output="$(bash scripts/agent_loop/loop_once.sh --queue "$queue_file" "${dry_args[@]}")"; then
    printf '%s\n' "$output"
    exit 1
  fi
  printf '%s\n' "$output"
  if grep -q "NO_ELIGIBLE_TASK" <<<"$output"; then
    exit 0
  fi
  if [[ "${dry_args[*]-}" == *"--dry-run"* ]]; then
    exit 0
  fi
done

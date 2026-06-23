#!/usr/bin/env bash
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

log() {
  printf '\n== %s ==\n' "$*"
}

log "ruff format --check"
if command -v ruff >/dev/null 2>&1; then
  ruff format --check .
else
  echo "ruff unavailable; running offline style fallback"
  python3 scripts/agent_loop/validate_repo.py style-fallback
fi

log "ruff check"
if command -v ruff >/dev/null 2>&1; then
  ruff check .
else
  echo "ruff unavailable; running Python parse fallback"
  python3 scripts/agent_loop/validate_repo.py parse-python
fi

log "mypy"
if command -v mypy >/dev/null 2>&1; then
  mypy scripts tests
else
  echo "mypy unavailable; running Python parse fallback"
  python3 scripts/agent_loop/validate_repo.py parse-python
fi

log "pytest"
if command -v pytest >/dev/null 2>&1; then
  pytest -q
else
  echo "pytest unavailable; running unittest fallback"
  python3 scripts/agent_loop/validate_repo.py test-fallback
fi

log "FInk machine gates"
extra=()
if [[ "${FINK_TASK_START:-0}" == "1" ]]; then
  extra+=(--task-start)
fi
python3 scripts/agent_loop/validate_repo.py gates "${extra[@]}"

echo
echo "GATES_OK"

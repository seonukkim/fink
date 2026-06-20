#!/usr/bin/env bash
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"
python3 scripts/agent_loop/validate_repo.py doctor "$@"

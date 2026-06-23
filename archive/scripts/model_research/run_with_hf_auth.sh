#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: scripts/model_research/run_with_hf_auth.sh [--require-token] COMMAND [ARGS...]

Runs COMMAND with Hugging Face cache variables set. If a cached token exists it
is exported for gated operations, but public ungated model installs may run
without one. Token values are never printed.
USAGE
}

require_token=false
if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  usage
  exit 0
fi
if [[ "${1:-}" == "--require-token" ]]; then
  require_token=true
  shift
fi
if [[ "$#" -eq 0 ]]; then
  usage >&2
  exit 2
fi

export HF_HOME="${HF_HOME:-$HOME/.cache/huggingface}"
export HF_TOKEN_PATH="${HF_TOKEN_PATH:-$HF_HOME/token}"

if [[ -s "$HF_TOKEN_PATH" ]]; then
  chmod 600 "$HF_TOKEN_PATH"
  export HF_TOKEN="$(tr -d '\r\n' < "$HF_TOKEN_PATH")"
  export FINK_HF_AUTH_TOKEN_PRESENT="true"
else
  if [[ "$require_token" == "true" ]]; then
    echo "ERROR: missing Hugging Face token for token-required operation" >&2
    exit 1
  fi
  unset HF_TOKEN
  export FINK_HF_AUTH_TOKEN_PRESENT="false"
fi

export FINK_HF_AUTH_WRAPPER="run_with_hf_auth.sh"

exec "$@"

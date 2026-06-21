#!/usr/bin/env bash
set -euo pipefail

export HF_HOME="${HF_HOME:-$HOME/.cache/huggingface}"
export HF_TOKEN_PATH="${HF_TOKEN_PATH:-$HF_HOME/token}"

if [[ ! -s "$HF_TOKEN_PATH" ]]; then
  echo "ERROR: missing Hugging Face token at $HF_TOKEN_PATH" >&2
  exit 1
fi

chmod 600 "$HF_TOKEN_PATH"

export HF_TOKEN="$(tr -d '\r\n' < "$HF_TOKEN_PATH")"
export FINK_HF_AUTH_WRAPPER="run_with_hf_auth.sh"

exec "$@"

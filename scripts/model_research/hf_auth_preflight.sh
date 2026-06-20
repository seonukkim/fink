#!/usr/bin/env bash
set -euo pipefail

source "$HOME/fai/fink-env.sh"

if command -v hf >/dev/null 2>&1; then
  HF_CMD=(hf)
else
  HF_CMD=(uvx hf)
fi

echo "=== Hugging Face CLI ==="
"${HF_CMD[@]}" version || "${HF_CMD[@]}" --help >/dev/null

echo "=== Authentication ==="
"${HF_CMD[@]}" auth whoami

token_path="${HF_TOKEN_PATH:-${HF_HOME:-$HOME/.cache/huggingface}/token}"

if [[ ! -s "$token_path" ]]; then
  echo "ERROR: cached token is missing at the expected path." >&2
  echo "Run: uvx hf auth login" >&2
  exit 1
fi

chmod 600 "$token_path"

echo "Cached token exists and permissions were restricted."
echo "Token contents were not read or printed."
echo "HF_AUTH_OK"

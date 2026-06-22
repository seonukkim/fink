#!/usr/bin/env bash
#
# Download all on-device FInk models into the repo-local, gitignored .fink/models
# directory. The weights are NOT committed to git, but after `git clone` a user
# can fetch them with a single command and the app finds them automatically.
#
# Usage (from anywhere):
#   bash scripts/download_models.sh            # download embedding, reranker, chat LLM
#   bash scripts/download_models.sh --dry-run  # show what would be downloaded
#   bash scripts/download_models.sh --only llm # just the chat LLM, etc.
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Repo-local, gitignored model home (override by exporting FINK_HOME yourself).
export FINK_HOME="${FINK_HOME:-$REPO_ROOT/.fink}"
export FINK_MODEL_DOWNLOAD_ALLOWED=true

mkdir -p "$FINK_HOME/models"

echo "FInk models -> $FINK_HOME/models   (gitignored; not committed)"
echo

# Only huggingface_hub is needed to DOWNLOAD; the heavier llama-cpp-python build
# is only needed to RUN the chat LLM (see the note printed at the end).
uv run --with huggingface_hub fink-models download "$@"

echo
echo "Done. Models live in: $FINK_HOME/models"
echo
echo "To run the chatbot against these models:"
echo "  uv sync --extra web --extra chat            # one-time: installs the LLM runtime"
echo "  FINK_HOME=\"$FINK_HOME\" uv run fink-web --host 127.0.0.1 --port 8000"

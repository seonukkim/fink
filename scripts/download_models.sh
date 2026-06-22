#!/usr/bin/env bash
#
# Download all on-device FInk models with one command.
#
# Weights go to the default on-device model home (~/.local/share/fink/models),
# which is OUTSIDE the git repository (so weights are never committed) and is
# exactly where the app looks by default — so NO FINK_HOME is needed to run
# afterwards.
#
# Usage (from the repo, after `git clone`):
#   bash scripts/download_models.sh             # embedding, reranker, chat LLM
#   bash scripts/download_models.sh --dry-run   # show what would be downloaded
#   bash scripts/download_models.sh --only llm  # just the chat LLM, etc.
#
set -euo pipefail

export FINK_MODEL_DOWNLOAD_ALLOWED=true

echo "Downloading FInk models to the on-device model home (outside the repo)…"
echo

# Only huggingface_hub is needed to DOWNLOAD; the heavier llama-cpp-python build
# is only needed to RUN the chat LLM (see the note printed at the end).
uv run --with huggingface_hub fink-models download "$@"

echo
echo "Done. To run the chatbot against these models (no FINK_HOME needed):"
echo "  uv sync --extra web --extra chat   # one-time: installs the LLM runtime"
echo "  uv run fink-web --host 127.0.0.1 --port 8000"
echo
echo "For image / scanned-PDF OCR:  uv sync --extra ocr"

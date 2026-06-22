#!/usr/bin/env bash
#
# Run the FInk WEB chatbot demo with all optional on-device features enabled,
# in one command:
#   - web  : the local web server (FastAPI + uvicorn)
#   - chat : the on-device generative LLM (llama.cpp)  -> run download_models.sh first
#   - ocr  : image / scanned-PDF OCR (lightweight PP-OCR)
#
# `uv run` re-syncs the venv to the requested extras on every run, so the extras
# MUST be passed each time — otherwise OCR/LLM get uninstalled and you see
# "이미지 OCR이 이 기기에 설치되어 있지 않습니다." This script passes them for you.
#
# Usage (from the repo root):
#   bash scripts/run_web.sh                 # serves on 127.0.0.1:8000
#   bash scripts/run_web.sh --port 8001     # extra args pass through to fink-web
#
set -euo pipefail

# Install the optional deps if missing (fast no-op when already present; the
# first run builds llama-cpp-python and pulls paddle, which can take a while).
uv sync --extra web --extra chat --extra ocr

exec uv run --extra web --extra chat --extra ocr \
  fink-web --host 127.0.0.1 --port 8000 "$@"

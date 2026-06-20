#!/usr/bin/env bash
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

message="${1:-}"
if [[ -z "$message" ]]; then
  echo "usage: git_checkpoint.sh <commit-message>" >&2
  exit 2
fi

branch="$(git branch --show-current)"
if [[ "$branch" != "main" ]]; then
  echo "ERROR: refusing to commit on branch $branch; expected main" >&2
  exit 1
fi

if git ls-files | grep -E '(^\.fink/|\.pdf$|\.zip$|^contracts/|^uploads/|^data/private/|^data/raw/|^data/unsanitized/)'; then
  echo "ERROR: refusing to commit prohibited tracked files" >&2
  exit 1
fi

git add -A

if git diff --cached --quiet; then
  echo "NO_CHANGES_TO_COMMIT"
  exit 0
fi

git commit -m "$message"
echo "CHECKPOINT_COMMIT=$(git rev-parse HEAD)"

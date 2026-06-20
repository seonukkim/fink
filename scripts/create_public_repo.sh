#!/usr/bin/env bash
set -euo pipefail

if [[ "${FINK_PUBLIC_CONFIRM:-}" != "YES" ]]; then
  echo "Set FINK_PUBLIC_CONFIRM=YES to acknowledge public publication." >&2
  exit 2
fi

source "${HOME}/fai/fink-env.sh"
cd "${REPO_ROOT}"

bash scripts/public_repo_preflight.sh

if ! command -v gh >/dev/null 2>&1; then
  echo "GitHub CLI (gh) is required." >&2
  exit 1
fi

gh auth status

git add .

staged="$(mktemp)"
trap 'rm -f "${staged}"' EXIT
git diff --cached --name-only > "${staged}"

if grep -E '(^|/)\.fink/|\.pdf$|\.zip$|(^|/)contracts/|(^|/)uploads/' \
  "${staged}"; then
  echo "ERROR: prohibited file was staged." >&2
  git reset
  exit 1
fi

if [[ ! -s README.md ]]; then
  cat > README.md <<'EOF'
# FInk

FInk is a local-first Financial AI prototype for reviewing financial risk
signals in creator and webtoon contracts.

> This project provides review-priority signals and scenario analysis. It does
> not determine fraud, illegality, contract validity, or legal outcomes.

The current repository contains project specifications, reproducible
implementation infrastructure, evaluation assets, paper notes, and a static
project-page scaffold. Private source books, contracts, OCR corpora, local
indexes, and run inputs are excluded from Git.
EOF
  git add README.md
fi

if git diff --cached --quiet; then
  echo "No public files are staged; nothing to commit." >&2
  exit 1
fi

git commit -m "chore: initialize FInk public repository"

if gh repo view seonukkim/fink >/dev/null 2>&1; then
  if ! git remote get-url origin >/dev/null 2>&1; then
    git remote add origin git@github.com:seonukkim/fink.git
  fi
  git push -u origin main
else
  gh repo create seonukkim/fink \
    --public \
    --source=. \
    --remote=origin \
    --push \
    --description "Local-first Financial AI for creator-contract risk review"
fi

echo
gh repo view seonukkim/fink \
  --json nameWithOwner,visibility,url,defaultBranchRef

echo "PUBLIC_REPOSITORY_READY"

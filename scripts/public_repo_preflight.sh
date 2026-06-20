#!/usr/bin/env bash
set -euo pipefail

source "${HOME}/fai/fink-env.sh"
cd "${REPO_ROOT}"

if [[ ! -d .git ]]; then
  git init -b main
fi

git branch -M main

cat >> .gitignore <<'EOF'

# FInk local-only inputs and run artifacts
.fink/

# Never publish source scans or archives
*.pdf
*.zip

# Runtime/private material
contracts/
uploads/
models/
indexes/
data/private/
data/raw/
data/unsanitized/
EOF

# Deduplicate .gitignore while preserving first occurrence.
awk '!seen[$0]++' .gitignore > .gitignore.tmp
mv .gitignore.tmp .gitignore

if [[ -d .fink ]]; then
  probe="$(find .fink -type f | head -n 1 || true)"
  if [[ -n "${probe}" ]] && ! git check-ignore -q "${probe}"; then
    echo "ERROR: .fink input is not ignored: ${probe}" >&2
    exit 1
  fi
fi

candidate_file="$(mktemp)"
trap 'rm -f "${candidate_file}"' EXIT

git ls-files --cached --others --exclude-standard > "${candidate_file}"

if grep -E '(^|/)\.fink/|\.pdf$|\.zip$|(^|/)contracts/|(^|/)uploads/' \
  "${candidate_file}"; then
  echo "ERROR: public commit candidate contains prohibited files." >&2
  exit 1
fi

echo "=== Candidate files for the first public commit ==="
cat "${candidate_file}"

echo
echo "=== Empty public files to inspect ==="
while IFS= read -r file; do
  [[ -f "${file}" && ! -s "${file}" ]] && echo "${file}"
done < "${candidate_file}"

echo
echo "=== Git status ==="
git status --short

echo
echo "PREFLIGHT_OK"

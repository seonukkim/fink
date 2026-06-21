#!/usr/bin/env bash
set -euo pipefail

repo_root="$(git rev-parse --show-toplevel)"
cd "${repo_root}"

required_ignored_paths=(
  ".fink/preflight-probe.txt"
  "preflight-probe.pdf"
  "preflight-probe.zip"
  "uploads/preflight-probe.txt"
  "contracts/preflight-probe.txt"
  "models/preflight-probe.bin"
  "indexes/preflight-probe.idx"
  "data/private/preflight-probe.txt"
  "data/raw/preflight-probe.txt"
  "data/unsanitized/preflight-probe.txt"
)

secret_pattern='(sk-[A-Za-z0-9_-]{20,}|hf_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|gh[pousr]_[A-Za-z0-9_]{20,})'

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

is_prohibited_candidate() {
  local rel="$1"
  local lower="${rel,,}"

  case "${rel}" in
    .fink/* | uploads/* | contracts/* | models/* | indexes/* | data/private/* | data/raw/* | data/unsanitized/*)
      return 0
      ;;
  esac

  [[ "${lower}" == *.pdf || "${lower}" == *.zip ]]
}

is_sensitive_env_file() {
  local rel="$1"
  local base="${rel##*/}"

  [[ "${base}" == ".env" || "${base}" == *.env ]]
}

is_text_file() {
  local rel="$1"

  [[ -f "${rel}" ]] || return 1
  LC_ALL=C grep -Iq . "${rel}"
}

check_gitignore_enforced() {
  local missing_count=0
  local probe

  [[ -f ".gitignore" ]] || fail "gitignore_enforced failed; .gitignore is missing"

  for probe in "${required_ignored_paths[@]}"; do
    if ! git check-ignore -q -- "${probe}"; then
      missing_count=$((missing_count + 1))
    fi
  done

  if ((missing_count > 0)); then
    fail "gitignore_enforced failed; missing ignore coverage for ${missing_count} required pattern(s)"
  fi

  printf 'gitignore_enforced: checked=%d\n' "${#required_ignored_paths[@]}"
}

load_commit_candidates() {
  mapfile -d '' -t commit_candidates < <(git ls-files --cached --others --exclude-standard -z)
}

check_prohibited_candidates() {
  local bad_count=0
  local rel

  for rel in "${commit_candidates[@]}"; do
    if is_prohibited_candidate "${rel}"; then
      bad_count=$((bad_count + 1))
    fi
  done

  if ((bad_count > 0)); then
    fail "preflight_ok failed; prohibited commit-candidate file(s) found: count=${bad_count}"
  fi

  printf 'preflight_ok: candidate_files=%d prohibited=0\n' "${#commit_candidates[@]}"
}

check_secret_scan() {
  local rel
  local scanned_count=0
  local finding_count=0
  local sensitive_env_count=0

  for rel in "${commit_candidates[@]}"; do
    [[ -f "${rel}" ]] || continue

    if is_sensitive_env_file "${rel}"; then
      sensitive_env_count=$((sensitive_env_count + 1))
      continue
    fi

    if ! is_text_file "${rel}"; then
      continue
    fi

    scanned_count=$((scanned_count + 1))
    if LC_ALL=C grep -Eq "${secret_pattern}" "${rel}"; then
      finding_count=$((finding_count + 1))
    fi
  done

  if ((sensitive_env_count > 0)); then
    fail "secret_scan failed; sensitive environment file(s) in commit candidate: count=${sensitive_env_count}"
  fi

  if ((finding_count > 0)); then
    fail "secret_scan failed; possible API key(s) in commit candidate: count=${finding_count}"
  fi

  printf 'secret_scan: scanned_text_files=%d findings=0\n' "${scanned_count}"
}

check_gitignore_enforced
load_commit_candidates
check_prohibited_candidates
check_secret_scan

echo "PREFLIGHT_OK"

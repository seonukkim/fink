#!/usr/bin/env bash
set -euo pipefail

source "${HOME}/fai/fink-env.sh"
cd "${REPO_ROOT}"

required=(
  ".fink/inputs/claude/stage-0/01_SOURCE_MANIFEST.csv"
  ".fink/inputs/claude/stage-0/02_SOURCE_ROLE_AND_AUTHORITY_MAP.md"
  ".fink/inputs/claude/stage-0/03_DUPLICATE_CONFLICT_AND_PRECEDENCE_LOG.csv"

  ".fink/inputs/claude/stage-1/10_MASTER_RISK_TAXONOMY.md"
  ".fink/inputs/claude/stage-1/10_MASTER_RISK_TAXONOMY.yaml"
  ".fink/inputs/claude/stage-1/11_MASTER_CREATOR_CHECKLIST.md"
  ".fink/inputs/claude/stage-1/11_MASTER_CREATOR_CHECKLIST.jsonl"
  ".fink/inputs/claude/stage-1/12_MASTER_FINANCIAL_FEATURES.md"
  ".fink/inputs/claude/stage-1/12_MASTER_FINANCIAL_FEATURES.yaml"
  ".fink/inputs/claude/stage-1/13_MASTER_BILINGUAL_GLOSSARY.md"
  ".fink/inputs/claude/stage-1/13_MASTER_BILINGUAL_GLOSSARY.csv"
  ".fink/inputs/claude/stage-1/14_MASTER_EVIDENCE_MATRIX.csv"
  ".fink/inputs/claude/stage-1/15_MASTER_KNOWLEDGE_CARDS.jsonl"
  ".fink/inputs/claude/stage-1/16_HIERARCHICAL_RAG_CORPUS_SPEC.md"

  ".fink/inputs/claude/stage-2/20_FINANCIAL_AI_METHOD_MAP.md"
  ".fink/inputs/claude/stage-2/21_CONTRIBUTION_CANDIDATES.md"
  ".fink/inputs/claude/stage-2/22_DATASET_AND_EVALUATION_PLAN.md"
  ".fink/inputs/claude/stage-2/23_TERM_PROJECT_COMPLIANCE_MAP.md"
  ".fink/inputs/claude/stage-2/24_FUTURE_DELIVERABLE_DATA_REQUIREMENTS.md"

  ".fink/inputs/claude/stage-3/00_DATA_PACKAGE_README.md"
  ".fink/inputs/claude/stage-3/30_DATA_GAPS_CONFLICTS_AND_LIMITATIONS.md"
  ".fink/inputs/claude/stage-3/31_PREPROCESSING_QA_REPORT.md"
  ".fink/inputs/claude/stage-3/32_FINAL_FILE_INDEX.csv"
  ".fink/inputs/claude/stage-3/33_REQUIRED_HUMAN_REVIEW.csv"
)

missing=0
for file in "${required[@]}"; do
  if [[ -s "${file}" ]]; then
    printf 'OK: %s\n' "${file}"
  else
    printf 'MISSING_OR_EMPTY: %s\n' "${file}" >&2
    missing=1
  fi
done

chatgpt_count="$(
  find .fink/inputs/chatgpt -maxdepth 1 -type f \
    \( -name '*.md' -o -name '*.csv' -o -name '*.jsonl' \
       -o -name '*.yaml' -o -name '*.yml' \) \
    | wc -l
)"
printf 'ChatGPT structured-file count: %s\n' "${chatgpt_count}"

if [[ "${chatgpt_count}" -lt 10 ]]; then
  echo "MISSING_OR_TOO_FEW: .fink/inputs/chatgpt" >&2
  missing=1
fi

if find .fink/inputs -type f \
  \( -iname '*.pdf' -o -iname '*.png' -o -iname '*.jpg' \
     -o -iname '*.jpeg' -o -iname '*.zip' \) | grep -q .; then
  echo "PROHIBITED_REFERENCE_BINARY_INPUT_FOUND" >&2
  missing=1
fi

if [[ "${missing}" -ne 0 ]]; then
  echo "SPEC_INPUTS_BLOCKED" >&2
  exit 1
fi

echo "SPEC_INPUTS_OK"

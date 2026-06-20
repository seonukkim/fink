# FInk Agent Loop Status

- Generated: `2026-06-20T23:13:24+00:00`
- Current branch: `main`
- Base commit: `b3803bfa4df0e72a1b8623e271d8f202eba3dbd1`
- Latest successful commit: `b3803bfa4df0e72a1b8623e271d8f202eba3dbd1`
- Active task: `none`
- Round: `0`
- Claude verdict: `none`
- Latest run path: `.fink/runs/<RUN_ID>/<TASK_ID>`

## Gates

- Branch gate: main only.
- Clean tree gate: enforced at task start by `loop_once.sh`.
- Machine gates: `bash scripts/agent_loop/run_gates.sh`.
- Paper-sync status: scaffold ledgers present; no measured results claimed.
- Fixes: none pending in bootstrap scaffold.

## Human Gates

| Gate | Status | Approved | Notes |
|---|---|---:|---|
| HR-01 | OPEN | False | A0 current-law verification blocks current-law claims and webtoon grounded score. |
| HR-02 | OPEN | False | 2025 webtoon handbook and 2023 fair-guide extraction blocks webtoon-specific grounded scoring. |
| HR-03 | OPEN | False | Sensitive Korean-English legal alias sign-off blocks cross-lingual legal claims. |
| HR-04 | OPEN | False | Missing artist-welfare source; cross-cutting only and never score-eligible. |
| HR-05 | OPEN | False | Dated 2018-2021 figures cannot be used as current. |
| HR-06 | OPEN | False | Glossary risk_category spot-check. |
| HR-07 | RESOLVED | True | Governing offering 2026 Spring IE412 AI for Finance; deadline 2026-06-24 23:59 KST. |
| HR-08 | OPEN | False | AI-use log and human-verification attestation blocks release. |
| MODEL_METADATA_NETWORK_APPROVED | APPROVED | True | Metadata and dry-run size checks may use Hugging Face with cached token through run_with_hf_auth.sh. |
| MODEL_LICENSES_APPROVED | OPEN | False | Human review of public-open license shortlist required before download. |
| MODEL_DOWNLOAD_APPROVED | OPEN | False | Human approval required before any model weight download. |
| MODEL_PROFILE_APPROVED | OPEN | False | Human approval required for selected local model profile. |

## Tasks

- Next eligible task: `FINK-S0-01`
- Done count: `0`
- Blocked count: `0`
- Next task selection order: highest priority, shortest scope, lexical task ID.

## Operator Commands

```bash
# single task / single queue
bash scripts/agent_loop/loop_once.sh
bash scripts/agent_loop/loop_run.sh scripts/agent_loop/queue.s1.txt 8
# all queues in dependency order (s0 -> models -> s1 -> s2 -> s3)
bash scripts/agent_loop/run_all_queues.sh --dry-run
bash scripts/agent_loop/run_all_queues.sh --max-tasks-per-queue 20
# stop the loop after the current task
touch loop/STOP
```

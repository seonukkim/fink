# FInk Agent Loop Status

- Generated: `2026-06-21T15:10:52+00:00`
- Current branch: `main`
- Base commit: `b3803bfa4df0e72a1b8623e271d8f202eba3dbd1`
- Latest successful commit: `b3803bfa4df0e72a1b8623e271d8f202eba3dbd1`
- Active task: `none`
- Round: `0`
- Claude verdict: `APPROVE`
- Latest run path: `.fink/runs/20260621T145937Z-e605be23/FINK-S5-07/round-01`

## Gates

- Branch gate: main only.
- Clean tree gate: enforced at task start by `loop_once.sh`.
- Machine gates: `bash scripts/agent_loop/run_gates.sh`.
- Paper-sync status: scaffold ledgers present; no measured results claimed.
- Fixes: none pending in bootstrap scaffold.

## Human Gates

| Gate | Status | Approved | Notes |
|---|---|---:|---|
| HR-01 | RESOLVED | True | Auto-resolved under conservative mode: the system never asserts current law; evidence stays UNVERIFIED and date-stamped; scoring is A0-A2-only. No current-law claim is made, so no legal verification is needed. Enforced each task by legal_verdict_scan + authority_invariant + the INV suite. |
| HR-02 | RESOLVED | True | Auto-resolved under conservative mode: webtoon-specific signals are practice references, not authoritative grounded scores; A0-A2 grounding required to contribute to a score. No authoritative webtoon-law claim is made. |
| HR-03 | RESOLVED | True | Auto-resolved under conservative mode: Korean is canonical; English aliases are never labeled evidence; the 8 non-equivalence terms carry caveats. No cross-lingual legal claim is made. |
| HR-04 | RESOLVED | True | Auto-resolved: artist-welfare material is cross-cutting and never score-eligible, enforced by the authority/eligibility invariants. |
| HR-05 | RESOLVED | True | Auto-resolved under conservative mode: dated (2018-2021) figures are always shown with their source date and never presented as current. |
| HR-06 | RESOLVED | True | Auto-resolved: glossary risk_category is checked by the glossary/eligibility invariants rather than a manual spot-check. |
| HR-07 | RESOLVED | True | Governing offering 2026 Spring IE412 AI for Finance; deadline 2026-06-24 23:59 KST. |
| HR-08 | OPEN | False | STAYS HUMAN. Academic-integrity attestation that the author personally reviewed the AI-assisted outputs before release. Auto-attesting would misrepresent the author's review to the course. Flip to approved:true / RESOLVED only at submission, after reviewing. Everything up to release automates; this is the single final human step. |
| MODEL_METADATA_NETWORK_APPROVED | APPROVED | True | Metadata and dry-run size checks may use Hugging Face with the cached token through run_with_hf_auth.sh. |
| MODEL_LICENSES_APPROVED | RESOLVED | True | Auto-resolved under the open-source-only license floor (apache-2.0, mit, bsd-2-clause, bsd-3-clause, isc, cc0-1.0, cc-by-4.0; reject gated/unknown/custom/other/noncommercial/research-only). Enforced by model_license_floor + the loop's open_license_policy_check, which verifies real licenses from HF metadata. |
| MODEL_DOWNLOAD_APPROVED | RESOLVED | True | Auto-resolved: download only open-allowlisted models within max_download_size_gb (configs/models/candidates.yaml). Weights remain outside Git, enforced by tracking_scan + model_license_floor. |
| MODEL_PROFILE_APPROVED | RESOLVED | True | Auto-resolved: the selected local profile must use only open-allowlisted, offline-loadable models recorded with pinned revisions. |

## Tasks

- Next eligible task: `none`
- Done count: `52`
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
# drain the WHOLE backlog at once (every phase S0..S8 + MR)
bash scripts/agent_loop/run_backlog.sh --dry-run
bash scripts/agent_loop/run_backlog.sh --max-tasks 100
# stop the loop after the current task
touch loop/STOP
```

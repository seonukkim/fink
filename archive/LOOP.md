# FInk Agent Loop Status

- Generated: `2026-06-23T04:05:11+09:00`
- Current branch: `main`
- Base commit: `7a2aceac549a4e28d9422f31696f9e4f6554184f`
- Latest successful commit: `b3803bfa4df0e72a1b8623e271d8f202eba3dbd1`
- Active task: `none`
- Round: `0`
- Claude verdict: `APPROVE`
- Latest run path: `.fink/runs/20260622T043827Z-cb63fe2f/FINK-HEALTH-01/round-01`

## Gates

- Branch gate: main only.
- Clean tree gate: enforced at task start by `loop_once.sh`.
- Machine gates: `bash scripts/agent_loop/run_gates.sh`.
- Paper-sync status: scaffold ledgers present; no measured results claimed.
- Fixes: switched the default upload image/scanned-PDF OCR path from optional
  PaddleOCR-VL to lightweight standard PaddleOCR PP-OCR with Korean
  configuration, kept the VL class as an optional non-default backend, updated
  OCR install/model guidance, quieted optional PaddleOCR-VL upload OCR logs,
  cached the local PaddleOCR-VL backend across upload calls, added image/PDF pending and
  friendly OCR-failure chat bubbles, replaced the dense creator result report
  with a single-column messenger-style result sequence, polished the chat demo
  shell per owner feedback with a fixed bottom composer, pink theme, effort
  meter, and browser-print PDF brief, wired distilled knowledge checkpoints into
  chatbot conversation grounding only, applied the second premium owner-feedback
  revision with bilingual source-clause aids, stacked chips, semantic
  traffic-light effort colors, formal privacy/disclosure copy, clearer OCR
  install guidance, and Hanja stripping in local chat replies, and kept the work
  local-only with no paper-template changes. Added a transparent two-tier
  review-attention support indicator: the displayed score remains A0-A2-only,
  with separate official-evidence and practice-basis counts surfaced in the
  payload and UI. Added inline, curated, RAG-grounded practice checklists under
  creator-facing findings; the checklist payload is bilingual, non-scoring, and
  globally deduped across the result. Added English distilled checkpoint fields
  to the public knowledge YAML, renamed the integrated summary card to `요약`,
  gave it a subtle pink emphasis, and changed chat so raw checklist prompts stay
  reference-only rather than being printed. Enabled combined paste-text plus
  local file analysis by recovering upload text through the existing txt/PDF/OCR
  path, joining paste first and file text second, and added a minimal composer
  attachment preview with local object-URL image thumbnails and no auto-send.
  Ported the locked warm-greige visual redesign into the live chat app and
  public page; added self-hosted Noto Serif KR font-face routing through both
  FastAPI and the raw ASGI fallback, added `font-src 'self'` to CSP, renamed the
  user-facing score to `위험 지수` / `Risk Index`, removed the per-checklist
  source note, and kept the result framing as Contractual Financial Review
  Priority rather than a legal/verdict claim. Moved the advice/LAN warnings
  into persistent header lines, removed the collapsible Notice disclosure panel
  and amount-estimate disclosure, normalized the chat result sequence to one
  aligned card rhythm, and added multi-file thumbnail attachments plus repeated
  multipart `contract_file` analysis. Applied six local result-rendering fixes:
  single-column dimension chips, a white/pink persistent advice banner,
  underline-only audit source highlights, no opaque generic clause fallback, no
  internal follow-up support topic in the evidence checklist, and score-derived
  review-effort traffic-light levels.

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
| HR-08 | RESOLVED | True | STAYS HUMAN. Academic-integrity attestation that the author personally reviewed the AI-assisted outputs before release. Auto-attesting would misrepresent the author's review to the course. Flip to approved:true / RESOLVED only at submission, after reviewing. Everything up to release automates; this is the single final human step. |
| MODEL_METADATA_NETWORK_APPROVED | APPROVED | True | Metadata and dry-run size checks may use Hugging Face with the cached token through run_with_hf_auth.sh. |
| MODEL_LICENSES_APPROVED | RESOLVED | True | Auto-resolved under the open-source-only license floor (apache-2.0, mit, bsd-2-clause, bsd-3-clause, isc, cc0-1.0, cc-by-4.0; reject gated/unknown/custom/other/noncommercial/research-only). Enforced by model_license_floor + the loop's open_license_policy_check, which verifies real licenses from HF metadata. |
| MODEL_DOWNLOAD_APPROVED | RESOLVED | True | Auto-resolved: download only open-allowlisted models within max_download_size_gb (configs/models/candidates.yaml). Weights remain outside Git, enforced by tracking_scan + model_license_floor. |
| MODEL_PROFILE_APPROVED | RESOLVED | True | Auto-resolved: the selected local profile must use only open-allowlisted, offline-loadable models recorded with pinned revisions. |

## Tasks

- Next eligible task: `none`
- Done count: `77`
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

## Latest Verification

- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests -q` passed.
- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest
  tests/web/test_local_web_app.py tests/web/test_a11y_validation.py
  tests/web/test_report_ui.py tests/web/test_analyze_pipeline.py
  tests/test_knowledge_base.py -q` passed.
- `python3 -c "import fink.web.app"` was attempted and failed because the bare
  system interpreter does not have this `src/` layout package on `sys.path`;
  `PYTHONPATH=src python3 -c "import fink.web.app"` passed.
- The exact bare `uv run pytest tests -q` command was attempted and failed
  before tests started because the default uv cache path is read-only in this
  sandbox; `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests -q` passed.
- `bash scripts/agent_loop/run_gates.sh` ended with `GATES_OK`.

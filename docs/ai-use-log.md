# AI Use Log

## 2026-06-21 — Agent-loop bootstrap

- Tooling: Codex GPT-5.5 xhigh in this workspace.
- Scope: infrastructure bootstrap only. Created loop governance, scripts,
  schemas, prompts, documentation skeletons, and validation tests. No product
  feature implementation, model download, private corpus import, or runtime API
  dependency was added.
- Human verification: pending. HR-08 remains OPEN until the project author
  reviews and attests AI-assisted outputs for release.
- Privacy: no `.env`, Hugging Face token value, private books, contracts, model
  weights, PDFs, ZIPs, or `.fink` artifacts were committed.

## 2026-06-21 — README revision

- Tooling: Claude Opus 4.8 (max).
- Scope: documentation only. Rewrote `README.md` into an academic project README
  under the then-current title, added `docs/README_CONTENT_GUIDE.md`, and this
  log entry. No product feature, model download, or private corpus import. The
  FINK-DOC-01 entry below records the later canonical title synchronization.
- Evidence-checked: hero image and all relative links verified to exist; TODO
  boxes set from `loop/BACKLOG.yaml` (all 54 tasks READY except the committed
  agent-loop infrastructure); licensing marked pending (empty license files); no
  measured result, deployed URL, or completed product feature was claimed.
- Privacy: no token, contract text, private corpus content, or private path
  beyond the documented `~/fai/fink` and `~/fai/fink-private` roots appears.

## 2026-06-22 — Responsible-AI paper note and HR-08 record

- Tooling: Codex GPT-5.5 xhigh in this workspace.
- Scope: documentation only for FINK-S7-03. Updated this AI-use log and
  `docs/paper/08_responsible_ai.md` to record the review-priority framing,
  authority gate, uncertainty behavior, privacy boundary, synthetic-data limits,
  and no-validated-weights stance. No product feature, model download, private
  corpus import, runtime API dependency, or paper-template change was added.
- Human verification / HR-08: the human-gate snapshot supplied to this task
  records `HR-08` as `RESOLVED`, `approved=true`, `approval=human`. This entry
  records that human academic-integrity gate state; Codex did not auto-attest
  on the author's behalf.
- Privacy: no `.env`, Hugging Face token value, private books, contracts, model
  weights, PDFs, ZIPs, `.fink` artifacts, or raw user content were read or
  committed.

## 2026-06-22 — Chat UI conversational follow-up wiring

- Tooling: Codex GPT-5.5 xhigh in this workspace.
- Scope: `src/fink/web/app.py` `_APP_JS` and pinned web assertions. The chat
  composer now keeps the first text submit on `/api/analyze`, stores the analyzed
  contract text in browser state, sends later composer turns to the local
  `/api/chat` endpoint, renders pending/reply/error bot bubbles, shows returned
  citation chips, and adds up to three suggested follow-up chips from analyzed
  findings.
- Verification: `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/web -q` passed;
  `PYTHONPATH=src python3 -c "import fink.web.app"` passed; the rendered shell
  contains no `fetch(` or `https://`, and `app_js()` contains the `/api/chat`
  fetch. Plain `python3 -c "import fink.web.app"` still requires the package to
  be installed or `src` on `PYTHONPATH` in this sandbox's `src/` layout.
- Privacy: no `.env`, Hugging Face token value, private books, contracts, model
  weights, PDFs, ZIPs, `.fink` artifacts, or raw user content were read or
  committed.

## 2026-06-22 — P0 web robustness (structured errors, secondary_rights, locale)

- Tooling: Claude Code (Opus 4.8), implementing directly under the loop's
  allowed-path / test / no-push discipline (recursive loop invocation deferred).
- Scope: `src/fink/web/app.py`, `src/fink/web/analyze.py`, and a new
  `tests/web/test_analyze_robustness.py`. Known engine/setup failures
  (`SignalDetectionError`, `ScoringAggregationError`, `RetrievalCorpusError`) and
  malformed `secondary_rights` input now return a friendly, structured, bilingual
  `{error_code, error(ko), error_en, next_action}` body (400 input, 503 setup)
  instead of a leaked 500 traceback; the payload serializer tolerates a string
  locale.
- Verification: 4 new regressions + 29 web tests pass; `run_gates.sh` → GATES_OK.
- Privacy: no `.env`, token, weights, private corpora, PDFs/ZIPs, `.fink`
  artifacts, or raw user content were read or committed.

## 2026-06-22 — Installable package and web CLI

- Tooling: Codex GPT-5.5 xhigh in this workspace.
- Scope: FINK-PKG-01. Updated packaging metadata so the `src/` layout is
  installable without `PYTHONPATH`, added the `web` optional dependency extra
  and `fink-web` console entry point, preserved module invocation for
  `python -m fink.web`, and documented the new local run command. No model/OCR
  heavy dependency, runtime download, remote API dependency, or `.env` access was
  added.
- Verification: packaging/CLI regressions added under `tests/web/`; final gate
  commands for this task are recorded in the Codex result.
- Privacy: no `.env`, Hugging Face token value, private books, contracts, model
  weights, PDFs, ZIPs, `.fink` artifacts, or raw user content were read or
  committed.

## 2026-06-22 — Documentation and project-page claim synchronization

- Tooling: Codex GPT-5.5 xhigh in this workspace.
- Scope: FINK-DOC-01 documentation/page synchronization only. Updated public
  docs, project-page copy, paper notes, claim/result ledgers, citation notes,
  and site tests to the canonical title "FInk: Selective, Evidence-Gated
  Cash-Flow Triage for Creator Contracts." No product feature, deployment,
  model download, private corpus import, remote runtime API, or paper-template
  change was added.
- Claim boundary: model references are optional/when-installed only; measured
  result rows remain synthetic/sanitized fixture checks; no DFL-training,
  predicted exposure-value, real-contract performance,
  legal/fraud/validity/unfairness, or guaranteed-loss claim was added.
- Privacy: no `.env`, Hugging Face token value, private books, contracts, model
  weights, PDFs, ZIPs, `.fink` artifacts, or raw user content were read or
  committed.

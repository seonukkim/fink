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

## 2026-06-22 — Chat UI integrated-judgment summary card

- Tooling: Codex GPT-5.5 xhigh in this workspace.
- Scope: `src/fink/web/app.py` `_APP_JS` / `_css` and a pinned web smoke
  assertion. The chat analysis result now prepends a bilingual "한눈에 정리" /
  "At a glance" card with the recommended action, review-effort cue, finding
  count, top finding label, one-line rationale, and professional-confirmation
  caution. The card is decision support only and does not introduce a verdict.
- Verification: `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/web -q` passed;
  `UV_CACHE_DIR=/tmp/uv-cache uv run python3 -c "import fink.web.app"` passed;
  `app_js()` contains the new Korean label; the rendered shell remains free of
  inline request code and external URL strings.
- Privacy: no `.env`, Hugging Face token value, private books, contracts, model
  weights, PDFs, ZIPs, `.fink` artifacts, or raw user content were read or
  committed. No paper-template file was touched.

## 2026-06-22 — Chat UI messenger-style result sequence

- Tooling: Codex GPT-5.5 xhigh in this workspace.
- Scope: `src/fink/web/app.py` `_APP_JS` / `_css` and pinned web assertions.
  The browser result now renders as calm bot bubbles: opening line, compact
  "한눈에 정리" card, one compact bubble per finding, cost/timing/confidence
  chips, 의견서 action, follow-up chips, and collapsed audit details. Removed
  the app-side check-first duplicate, dimension grid, grounded-Q&A widget,
  Q&A copy/export/session-check controls, source-navigation panel, and raw
  evidence-ID display outside collapsed audit details.
- Verification: `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/web -q` passed;
  `PYTHONPATH=src python3 -c "import fink.web.app"` passed;
  `UV_CACHE_DIR=/tmp/uv-cache uv run python3 -c "import fink.web.app"` passed;
  `renderResult()` no longer calls the removed renderers; `app_js()` does not
  contain the removed grid/Q&A/check-first strings; the rendered shell contains
  no inline request code or external URL strings. Plain
  `python3 -c "import fink.web.app"` still requires the package to be installed
  or `src` on `PYTHONPATH` in this sandbox's `src/` layout.
- Privacy: no `.env`, Hugging Face token value, private books, contracts, model
  weights, PDFs, ZIPs, `.fink` artifacts, or raw user content were read or
  committed. No paper-template file was touched.

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

## 2026-06-22 — Local model download CLI

- Tooling: Codex GPT-5.5 xhigh in this workspace.
- Scope: Added `fink-models` list/download CLI support for the selected public
  embedding, reranker, and on-device GGUF chat model; documented the download
  commands; and added model CLI regressions. OCR remains guided through the
  existing `uv sync --extra ocr` path. No model weight, remote runtime API,
  telemetry, or paper-template change was added.
- Verification: `UV_CACHE_DIR=/tmp/uv-cache uv run --frozen --no-build-isolation
  fink-models list` passed; `UV_CACHE_DIR=/tmp/uv-cache
  FINK_MODEL_DOWNLOAD_ALLOWED= uv run --frozen --no-build-isolation fink-models
  download --dry-run` printed the enable instruction; `UV_CACHE_DIR=/tmp/uv-cache
  uv run --frozen --no-build-isolation python -m pytest tests/model -q` passed;
  `bash scripts/agent_loop/run_gates.sh` ended with `GATES_OK`.
- Privacy: no `.env`, Hugging Face token value, private books, contracts, model
  weights, PDFs, ZIPs, `.fink` artifacts, or raw user content were read or
  committed. Download targets remain outside the repository, and root
  `models/` paths stay ignored.

## 2026-06-22 — Quiet image/scanned-PDF OCR upload UX

- Tooling: Codex GPT-5.5 xhigh in this workspace.
- Scope: Quieted optional PaddleOCR-VL startup/inference log noise, cached the
  PaddleOCR-VL backend across upload OCR calls, and updated the chat `_APP_JS`
  upload flow to replace a visible file-analysis pending bubble with either the
  result or short OCR retry guidance. Source-navigation copy was updated to keep
  Korean canonical strings clear of the prohibited legacy label. No OCR
  correctness change, model download, remote runtime API, or deployment was
  added.
- Verification: web gate and import checks are recorded in the Codex result for
  this task. The rendered shell remains free of inline request code and external
  URL strings; fetch calls remain confined to `_APP_JS`.
- Privacy: no `.env`, Hugging Face token value, private books, contracts, model
  weights, PDFs, ZIPs, `.fink` artifacts, or raw user content were read or
  committed. No paper-template file was touched.

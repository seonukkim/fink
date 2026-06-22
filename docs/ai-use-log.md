# AI Use Log

## 2026-06-23 — Local result rendering consistency fixes

- Tooling: Codex GPT-5.5 xhigh in this workspace.
- Scope: fixed six local web app result-rendering issues in the existing
  gravitas system: dimension result chips now stack in one column at every
  width, the persistent not-legal-advice banner uses a white card treatment with
  a pink left rule, audit source highlights use the same pink underline style as
  finding excerpts, opaque generic clause labels are suppressed when no real
  heading can be recovered, the internal follow-up support topic is no longer
  shown in the evidence checklist, and the displayed review-effort traffic light
  is derived deterministically from the displayed `위험 지수` score thresholds.
  No score computation, authority A0-A2 invariant, remote runtime API, model
  weight, private input, paper, template, or `icml2026` file was changed.
- Verification: `UV_CACHE_DIR=/tmp/uv-cache uv run pytest
  tests/web/test_local_web_app.py tests/web/test_a11y_validation.py
  tests/web/test_source_highlights.py tests/web/test_report_ui.py
  tests/web/test_verification_pathway.py -q` passed; the exact bare `uv run
  pytest tests -q` command was attempted and failed before tests started because
  the default uv cache path is read-only in this sandbox; `UV_CACHE_DIR=/tmp/uv-cache
  uv run pytest tests -q` passed; the exact bare `python3 -c "import
  fink.web.app, fink.web.view_model"` command was attempted and failed because
  the system interpreter does not have the checkout's `src/` layout package on
  `sys.path`; `UV_CACHE_DIR=/tmp/uv-cache uv run python3 -c "import
  fink.web.app, fink.web.view_model"` passed; `bash scripts/agent_loop/run_gates.sh`
  ended with `GATES_OK`.
- Privacy: no `.env`, Hugging Face token value, private books, contracts, model
  weights, PDFs, ZIPs, `.fink` artifacts, or raw user content were read or
  committed.
- Claude follow-up (same area, audited visually with Playwright): removed the
  font-relative `max-width: var(--reading-measure)` from `.finding-checklist`
  and `.result-source-quote` so the checklist and excerpt blocks align to the
  same card width (serif/sans `ch` units had produced different pixel widths);
  trimmed the deterministic chat reply so a matched-question answer is just the
  finding rationale plus the tuned professional note (dropped the repeated
  "…항목과 관련이 있어 보여요" prefix and "상대방에게 …라고 확인해 보세요"
  suffix), and the overall read drops the per-finding question scaffolding;
  replaced the banned "정리했어요" wording in the post-analysis greeting with
  "추렸어요". Verified `uv run pytest tests/web tests/model -q` green,
  `run_gates.sh` `GATES_OK`, and a live :8011 render (checklist/excerpt both
  `w650`, score 9/100 → "가볍게 확인" active, "제3조(정산)" not "조항 N").
- Claude follow-up 2 (owner asked to drop the repeated disclaimer from chat
  replies): removed the "이 분석은 … 전문가 확인을 권해요" note from every
  deterministic reply path; the not-legal-advice disclaimer now lives only in the
  always-visible page banner. A matched-question reply is the finding rationale
  plus one concrete question to raise (no framing). The on-device LLM path is
  unchanged and already omits the note; confirmed `chat_model_available()` is
  true (`qwen2.5-1.5b-instruct-q4_k_m.gguf`) and a live `used_model=True` reply
  to "정산 투명성·감사권이 뭐야?" returns a contextual answer in ~9.5s, so the
  deterministic fallback only appears when the LLM is disabled. Updated the two
  fallback tests to assert the disclaimer is absent. `pytest tests/web
  tests/model -q` green, `run_gates.sh` `GATES_OK`.
- Claude follow-up 3 (owner: on-device chat answers read unnaturally — boilerplate
  openers, preambles, and a repetition loop): rewrote the KO/EN system prompts to
  demand a direct, natural answer with no honorific/greeting/"답변은 다음과
  같습니다"/"~에 대해 물어보세요" opener; relabeled the user-prompt scaffolding and
  asked the model to focus on the asked topic; added a `repeat_penalty`/`top_k`
  and shorter `max_tokens` to the llama call to stop degeneration loops; and added
  output post-processors `_strip_llm_preamble` (peel boilerplate openers),
  `_collapse_repetition` (drop looped duplicate sentences), and extra `_sanitize`
  rules (remove leaked internal "참고 N:" checkpoint labels, markdown emphasis,
  and a trailing "감사합니다" sign-off). Verified against the live local model
  (`qwen2.5-1.5b-instruct`): the looping question now returns one coherent answer
  and openers/preambles are gone. Added unit tests for all three post-processors;
  `pytest tests/model tests/web -q` green, `run_gates.sh` `GATES_OK`.
- Claude follow-up 4 (owner still saw the model dumping numbered lists / echoing
  "물어볼 말:" / "N번 항목:"): root cause was feeding the 1.5B model the entire
  structured context (all findings, their clarification questions, clause text,
  and reference checkpoints), which it regurgitates. For a question the prompt now
  narrows to the single best-matching concern only (label + rationale; no list,
  clause text, or checkpoints); the no-question read is likewise compact.
  Hardened `_sanitize` to strip the "N번 항목:" label variant and a trailing
  honorific/sign-off. Verified through the live `/api/chat` endpoint on a freshly
  restarted server: the previously failing questions now return focused 2-3
  sentence answers with no list dump or label leak. (The visible regressions the
  owner hit were a stale uvicorn process serving pre-fix code — uvicorn does not
  hot-reload — not a code defect.) `pytest tests/model tests/web -q` green,
  `run_gates.sh` `GATES_OK`.
- Claude follow-up 5 (owner: keep each answer to one sentence — two sentences
  invite drift): the model branch now hard-caps the reply to a single sentence
  (`_limit_sentences`), the dedup key ignores trailing punctuation so a
  period-less looped sentence is also collapsed, the prompts ask for one-sentence
  core-only answers, and the sampler uses `max_tokens=128`/`temperature=0.2`.
  Chat answers are intentionally terse; the rich grounded detail stays in the
  result cards. Verified via live `/api/chat`: every answer is a single clean
  sentence. Added tests for the limiter and the punctuation-insensitive dedup;
  `pytest tests/model tests/web -q` green, `run_gates.sh` `GATES_OK`.
- Claude follow-up 6 (owner: the 위험 지수 needs a real financial-AI rationale and
  a guaranteed bound, not just an under-100 clamp): documented the design rationale
  and references in `docs/specs/03_SCORING_AND_FINANCIAL_IMPACT.md` §3A — the
  per-signal `severity × likelihood × evidence-credibility` form (ISO 31000 /
  IEC 60812 FMEA / GRADE), the saturating exponential as bounded/diminishing-
  marginal utility (Pratt 1964), and the weight-normalized convex combination as
  MCDA/SAW under MAUT (Fishburn 1967; Keeney & Raiffa 1976), with a structural
  proof that the score lies in [0, 100] regardless of signal count/severity. Also
  hardened `scoring/engine.py` so the two degenerate-config cases (`k_F ≤ 0`,
  `Σ w_F ≤ 0`) cannot divide by zero or break the bound, and added
  `test_saturating_score_and_priority_stay_bounded_under_degenerate_config`. No
  weight/threshold value changed (constants remain versioned heuristics per
  INV-9); only documentation, defensive guards, and a test were added.
  `pytest tests/scoring tests/finance -q` green, `run_gates.sh` `GATES_OK`.
- Claude follow-up 7 (owner: the saved PDF carries browser header/footer chrome —
  date/time, page title, URL, page number — remove it): set the print
  stylesheet's `@page` margin to 0 (the margin box is where the browser draws
  that chrome) and moved the visual page margin onto the printable root as 16mm
  padding so the brief layout is unchanged. Verified by rendering the brief under
  print-media emulation: the document keeps its margin and is not clipped. The
  brief's own "작성일" line is document content, not browser chrome, and is kept.
  `pytest tests/web/test_report_ui.py tests/web/test_local_web_app.py
  tests/web/test_a11y_validation.py -q` green, `run_gates.sh` `GATES_OK`.
- Claude follow-up 8 (backlog: richer, more organized results): (1) the summary
  card now lists every finding by title as a pink-numbered "확인할 항목" overview
  beneath the top-priority concern; (2) findings that cite the same clause excerpt
  are merged into one card — the clause tag and source excerpt are shown once and
  the individual findings are separated by `---` dividers (`renderFindingGroup` /
  `groupRecordsByClause`; grouped `.finding-line` drops its own card chrome).
  Verified on a contract whose first two findings share 제3조: one grouped card
  (1 divider) + one standalone card for 제5조, all three findings preserved.
  Updated the three test pins for the new `renderFindingLine(record, grouped)`
  signature. `pytest tests/web -q` green, `run_gates.sh` `GATES_OK`.

## 2026-06-23 — Persistent warning, aligned results, multi-attachment upload

- Tooling: Codex GPT-5.5 xhigh in this workspace.
- Scope: revised the local web app inside the existing gravitas design system:
  the not-legal-advice warning is always visible under the privacy line, the
  collapsible Notice panel and amount-estimate disclosure are removed, LAN
  warnings stay persistent only when enabled, appended result blocks share one
  aligned card rhythm, the dimension trio is grouped into one card grid, and the
  composer now supports multiple attachments with thumbnail/file-tile previews
  and per-file removal. The upload backend accepts repeated `contract_file`
  multipart parts, recovers each file through the existing txt/PDF/OCR path,
  merges all recovered text with pasted text, and analyzes once. No remote
  runtime API, model weight, private input, paper, template, or `icml2026` file
  was changed.
- Verification: `UV_CACHE_DIR=/tmp/uv-cache uv run pytest
  tests/web/test_local_web_app.py tests/web/test_a11y_validation.py
  tests/web/test_upload_analyze_endpoint.py tests/web/test_report_ui.py -q`
  passed; the exact bare `uv run pytest tests -q` command was attempted and
  failed before tests started because the default uv cache path is read-only in
  this sandbox; `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests -q` passed; the
  exact bare `python3 -c "import fink.web.app, fink.web.upload"` command was
  attempted and failed because the system interpreter does not have the
  checkout's `src/` layout package on `sys.path`; `UV_CACHE_DIR=/tmp/uv-cache uv
  run python3 -c "import fink.web.app, fink.web.upload"` passed; `bash
  scripts/agent_loop/run_gates.sh` ended with `GATES_OK`.
- Privacy: no `.env`, Hugging Face token value, private books, contracts, model
  weights, PDFs, ZIPs, `.fink` artifacts, or raw user content were read or
  committed.

## 2026-06-23 — Locked visual redesign port

- Tooling: Codex GPT-5.5 xhigh in this workspace.
- Scope: ported the locked `/tmp/mockup5.html` visual system into the local
  chat app and public webpage: warm greige palette, charcoal brand topbar with
  divider and gradient rule, self-hosted Noto Serif KR content font, serif
  content/sans chrome split, neutral summary/finding/checklist cards, outline
  clause tags, underline-only excerpt highlights, traffic-light review-effort
  pills, and warm composer styling. The user-facing score is now
  `위험 지수` / `Risk Index`; the per-checklist source note was removed, and the
  framing remains Contractual Financial Review Priority rather than a
  legal/fraud/validity/unfairness or guaranteed-loss claim. Added
  `/fonts/<name>.woff2` routing to both FastAPI and the raw ASGI fallback and
  added `font-src 'self'` to the CSP. No behavior,
  `/api/*` flow, remote runtime API, model weight, private input, paper,
  template, or `icml2026` file was changed.
- Verification: `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests -q` passed;
  `UV_CACHE_DIR=/tmp/uv-cache uv run pytest
  tests/web/test_local_web_app.py tests/web/test_a11y_validation.py
  tests/web/test_report_ui.py tests/web/test_analyze_pipeline.py
  tests/test_knowledge_base.py -q` passed; `PYTHONPATH=src python3 -c "import
  fink.web.app"` passed; the exact bare `python3 -c "import fink.web.app"`
  command was attempted and failed because the system interpreter does not have
  the checkout's `src/` layout package on `sys.path`; the exact bare `uv run
  pytest tests -q` command was attempted and failed before tests started because
  the default uv cache path is read-only in this sandbox; `bash
  scripts/agent_loop/run_gates.sh` ended with `GATES_OK`.
- Privacy: no `.env`, Hugging Face token value, private books, contracts, model
  weights, PDFs, ZIPs, `.fink` artifacts, or raw user content were read or
  committed. Bundled OFL font files stay self-hosted and no network runtime path
  was added.

## 2026-06-23 — Combined file and text upload input

- Tooling: Codex GPT-5.5 xhigh in this workspace.
- Scope: enabled local combined paste-text plus one uploaded file analysis in
  the chat upload path. The backend now reuses the existing txt/PDF/image
  recovery and OCR flow to join pasted text before recovered file text, while
  preserving oversized, unsupported, corrupt/encrypted, and OCR-not-installed
  guards. The composer now previews an attached file without auto-sending,
  shows an object-URL thumbnail for image uploads, allows optional pasted text,
  echoes one combined user bubble, and revokes preview object URLs. No network,
  remote runtime API, model weight, private input, paper, template, or
  `icml2026` file was changed.
- Verification: `UV_CACHE_DIR=/tmp/uv-cache uv run pytest
  tests/web/test_upload_analyze_endpoint.py -q` passed; `UV_CACHE_DIR=/tmp/uv-cache
  uv run pytest tests -q` passed; `PYTHONPATH=src python3 -c "import
  fink.web.upload, fink.web.app"` passed; `UV_CACHE_DIR=/tmp/uv-cache uv run
  python3 -c "import fink.web.upload, fink.web.app"` passed; the exact bare
  `python3 -c "import fink.web.upload, fink.web.app"` command was attempted and
  failed because the system interpreter does not have the checkout's `src/`
  layout package on `sys.path`; `bash scripts/agent_loop/run_gates.sh` ended
  with `GATES_OK`.
- Privacy: no `.env`, Hugging Face token value, private books, contracts, model
  weights, PDFs, ZIPs, `.fink` artifacts, or raw user content were read or
  committed.

## 2026-06-23 — Inline RAG-grounded finding checklists

- Tooling: Codex GPT-5.5 xhigh in this workspace.
- Scope: added inline creator-facing practice checklists under each finding in
  the local conclusion. The checklist content comes from
  `data/knowledge/creator_contract_checkpoints.yaml`, is capped at the first
  three unused priority checkpoints for each finding's topic, and is globally
  deduped across the result. Added distilled English summary/checkpoint/question
  fields for all F1-F9 topics, a non-scoring bilingual checklist payload and UI
  renderer, a subtle pink-emphasized `요약` summary card, and chat prompt/fallback
  changes so raw checklist items remain reference-only in chat. No
  authority-gate, scoring, remote runtime API, model weight, private input,
  paper, template, or `icml2026` file was changed.
- Verification: `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests -q` passed;
  `UV_CACHE_DIR=/tmp/uv-cache uv run python3 -c "import fink.web.analyze,
  fink.web.view_model, fink.web.app, fink.knowledge.checkpoints,
  fink.model.explanation_llm"` passed; `PYTHONPATH=src python3 -c "import
  fink.web.analyze, fink.web.view_model, fink.web.app,
  fink.knowledge.checkpoints, fink.model.explanation_llm"` passed; `bash
  scripts/agent_loop/run_gates.sh` ended with `GATES_OK`. The exact bare
  `python3 -c "import fink..."` command was attempted and failed because the
  system interpreter does not have the checkout's `src/` layout package on
  `sys.path`.
- Privacy: no `.env`, Hugging Face token value, private books, contracts, model
  weights, PDFs, ZIPs, `.fink` artifacts, or raw user content were read or
  committed.

## 2026-06-22 — Transparent review-attention support tiers

- Tooling: Codex GPT-5.5 xhigh in this workspace.
- Scope: added separate official-evidence and practice-basis support counts for
  the review-attention display. The verified `review_priority_score` remains
  A0-A2-only; B/C practice references and distilled checkpoint coverage are
  surfaced only as a separately labeled practice-informed count. Updated
  scoring, local analysis, payload serialization, UI labels, tests, `LOOP.md`,
  and paper method notes. No authority-invariant change, remote runtime API,
  model weight, private input, or paper-template change was added.
- Verification: `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q` passed;
  `UV_CACHE_DIR=/tmp/uv-cache bash scripts/agent_loop/run_gates.sh` ended with
  `GATES_OK`; `app_js()` contains the `공식 근거` / `실무 기준` support labels.
- Privacy: no `.env`, Hugging Face token value, private books, contracts, model
  weights, PDFs, ZIPs, `.fink` artifacts, or raw user content were read or
  committed.

## 2026-06-22 — Second premium chat demo revision

- Tooling: Codex GPT-5.5 xhigh in this workspace.
- Scope: updated the local chat demo and supporting payloads for owner feedback:
  formal privacy/advice/disclosure copy, wider send target, stacked dimension and
  follow-up chips, semantic effort colors, score explanation text, real
  clause-heading references, bilingual source-clause rendering aids, distinct
  OCR-not-installed versus OCR-no-text errors, and Hanja stripping in local chat
  replies. Also updated focused tests, `LOOP.md`, and the paper discussion note.
  No remote runtime API, deployment, DNS, model weight, private input, or
  paper-template change was added.
- Verification: `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/web tests/model
  -q` passed; `PYTHONPATH=src python3 scripts/web_a11y_contrast_check.py`
  passed; `PYTHONPATH=src python3 -c "import fink.web.app"` and matching
  imports for `fink.web.upload` and `fink.model.explanation_llm` passed; the
  rendered shell contains no inline `fetch(` or `https://`, with fetch calls
  confined to `/app.js`. Bare `python3 -c "import fink..."` still fails in this
  sandbox because the `src/` layout is not installed into the bare interpreter.
- Privacy: no `.env`, Hugging Face token value, private books, contracts, model
  weights, PDFs, ZIPs, `.fink` artifacts, or raw user content were read or
  committed.

## 2026-06-22 — Chat grounding reference checkpoints

- Tooling: Codex GPT-5.5 xhigh in this workspace.
- Scope: conversation grounding only. Added distilled Korean checkpoint
  references to the chatbot `GroundedContext`, prompt grounding, deterministic
  fallback tip path, and web-context projection. No `fink.scoring`,
  `analyze.py` scoring, authority invariant, model download, remote runtime API,
  or paper-template change was added.
- Verification: `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/web tests/model
  tests/test_knowledge_base.py -q` passed; `bash scripts/agent_loop/run_gates.sh`
  ended with `GATES_OK`.
- Privacy: no `.env`, Hugging Face token value, private books, contracts, model
  weights, PDFs, ZIPs, `.fink` artifacts, or raw user content were read or
  committed.

## 2026-06-22 — Chat demo owner-feedback polish

- Tooling: Codex GPT-5.5 xhigh in this workspace.
- Scope: `src/fink/web/app.py` chat shell/CSS/JS design-token updates,
  `tests/web/` pinned assertions, `LOOP.md`, and paper implementation notes.
  The chat demo now uses a full-viewport column with only the thread scrolling,
  a fixed bottom composer, the FInk wordmark and updated creator title, the pink
  project-page palette, a three-step review-effort meter, consistent bubble max
  widths, a hidden initial result placeholder, and a browser-print review brief
  instead of Markdown download logic.
- Verification: `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/web -q` passed;
  `python3 scripts/web_a11y_contrast_check.py` passed; the rendered shell
  contains no inline `fetch(` or `https://`; `UV_CACHE_DIR=/tmp/uv-cache uv run
  python3 -c "import fink.web.app"` passed. Plain `/bin/python3 -c "import
  fink.web.app"` still fails in this sandbox because the checkout uses a `src/`
  layout and the package is not installed into the bare interpreter.
- Privacy: no `.env`, Hugging Face token value, private books, contracts, model
  weights, PDFs, ZIPs, `.fink` artifacts, or raw user content were read or
  committed. No paper-template file was touched.

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

## 2026-06-22 — Lightweight PP-OCR default upload OCR

- Tooling: Codex GPT-5.5 xhigh in this workspace.
- Scope: Switched the default uploaded image and scanned-PDF raster OCR path
  from optional PaddleOCR-VL to standard PaddleOCR PP-OCR with `lang="korean"`,
  keeping the same local-only OCR extra and preserving the optional VL class as
  a non-default backend. The PP-OCR parser handles both legacy
  `[box, (text, score)]` outputs and newer `rec_texts`/`rec_polys` dict outputs,
  and the upload path still falls back to local Tesseract when present.
- Verification: `UV_CACHE_DIR=/tmp/uv-cache uv run --no-project --with pytest
  pytest tests -q` passed; `PYTHONPATH=src python3 -c "import
  fink.ocr.paddle_vl; import fink.web.upload"` passed; `bash
  scripts/agent_loop/run_gates.sh` ended with `GATES_OK`. The exact
  `uv run pytest tests -q` command was attempted but the default uv cache path
  is read-only in this sandbox; retrying with `UV_CACHE_DIR=/tmp/uv-cache`
  reached the editable build and then failed because the sandbox could not fetch
  `setuptools>=68`.
- Privacy: no `.env`, Hugging Face token value, private books, contracts, model
  weights, PDFs, ZIPs, `.fink` artifacts, or raw user content were read or
  committed. No paper-template file was touched.

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

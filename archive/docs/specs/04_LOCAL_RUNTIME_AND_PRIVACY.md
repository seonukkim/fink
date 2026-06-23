# 04 — Local Runtime and Privacy Specification

**Parent:** `docs/FINK_MASTER_SPEC.md` · **Spec version:** 1.0.0
Inherits INV-1…INV-9, especially INV-5 (local-first) and INV-8 (privacy). Two
runtime profiles; both keep schemas (spec 02) profile-neutral.

---

## 1. Runtime profiles

### 1.1 Desktop-local full profile (MVP target)
- **App:** responsive **FastAPI** web application served from the user's own
  machine (`127.0.0.1` and the LAN interface), HTML/JS frontend.
- **Phone-camera upload:** a phone on the **same trusted LAN** opens the app in
  a mobile browser and captures pages; transport is LAN-only HTTP(S) to the
  host. No public exposure; bind to LAN interface with a clear "trusted-LAN
  only" warning and an opt-in.
- **OCR:** local engine (e.g., on-device OCR library/model), Korean + English,
  no network.
- **Corpus/index:** local hierarchical corpus + index (BM25/keyword + optional
  local embeddings), no cloud RAG.
- **Rule engine:** local deterministic risk-signal rules + authority gate.
- **LLM:** **optional** local model for explanation narrative only (never
  evidence, never sets a score); absent by default; if present it is local-only.
- **No remote runtime API:** zero outbound calls during analysis.
- **Temporary uploads:** ephemeral workspace, deleted at session end/clear.
- **Offline test:** passes a network-disabled integration test (RT-OFFLINE).

### 1.2 Mobile-local lite profile (design-compatible future)
- **Knowledge pack:** a **sanitized** mobile pack — public/synthetic-safe
  artifacts and authority-tier metadata only; **no private full corpus**, **no
  B/C full text**, **no license-gated long excerpts**.
- **OCR:** on-device mobile OCR.
- **Inference:** deterministic rules and/or a **small ONNX classifier**; same
  authority gate and scoring config schema.
- **No remote runtime API.**
- **Portability requirement:** all schemas (spec 02) and the scoring config
  (spec 03) are byte-compatible across profiles; only the corpus/model
  *artifacts* differ. The mobile pack is produced by a documented
  **sanitization step** that strips `P2_PRIVATE_LOCAL` content and keeps only
  authority-tier metadata + synthetic-safe material.

### 1.3 Profile matrix

| Capability | Desktop-full | Mobile-lite |
|------------|:------------:|:-----------:|
| FastAPI web app | ✅ | n/a (on-device app) |
| LAN phone-camera upload | ✅ | native camera |
| Local OCR | ✅ | on-device |
| Full private corpus/index | ✅ (local) | ❌ (sanitized pack) |
| Rule engine + authority gate | ✅ | ✅ |
| Local LLM (optional) | optional | typically ❌ |
| ONNX classifier | optional | ✅ (primary model arm) |
| Remote calls | ❌ | ❌ |

---

## 2. Local-only enforcement (INV-5)

- **RT-NET-1** During analysis the process makes **no outbound network
  connections**. Enforced by (a) no network client in the analysis path and
  (b) a test harness that blocks sockets and asserts success (AC-RT-OFFLINE).
- **RT-NET-2** No telemetry, analytics, crash-reporting, font/CDN, or update
  check transmits document content or fires during analysis.
- **RT-NET-3** Optional LLM/model weights are loaded from **local files**; no
  model is downloaded at runtime in the offline-test configuration.
- **RT-NET-4** LAN upload binds explicitly to the chosen interface; default is
  loopback; LAN binding requires explicit operator opt-in and shows the
  trusted-LAN warning.

---

## 3. Data minimization and upload lifecycle (INV-8)

- **RT-UP-1** Uploaded bytes (`P3_USER_EPHEMERAL`) are written only to an
  ephemeral workspace (e.g., a per-session temp dir) created with
  **owner-only / least-privilege permissions** (e.g., `0700` dir, `0600` files),
  referenced by `temp_path`, with `delete_after ≤ session end`.
- **RT-UP-2** Deletion triggers: explicit "clear," session end/timeout, and app
  shutdown. Deletion removes **raw bytes (including the source PDF), all derived
  page rasters, and OCR intermediates** for that session.
- **RT-UP-6** **PDF local processing (PR-005…PR-009).** PDFs are parsed,
  rasterized, and OCR'd **entirely locally**. Validation runs before processing:
  MIME + magic-byte (`%PDF-`) check and the configurable `max_pages`/`max_bytes`
  limits; corrupted, unsupported, oversized, or (by MVP default) encrypted PDFs
  are rejected locally with a clear error and **nothing is transmitted**. An
  optional local password-entry flow is the only path for an encrypted PDF; no
  remote decryption, cloud OCR, or cloud RAG is ever used.
- **RT-UP-3** `filename_hash` (not raw filename) and `bytes_sha256` are the only
  identifiers retained transiently; raw filenames are never persisted.
- **RT-UP-4** Export (`AnalysisReport`) excludes raw image bytes by default
  (`contains_raw_image=false`); including them is an explicit user action and
  still local-only.
- **RT-UP-5** No `P3` content is ever written under a Git-tracked path. The
  workspace lives outside the repo or under an ignored path
  (`uploads/`, `data/private/`, both git-ignored).

---

## 4. Log redaction (INV-8)

- **RT-LOG-1** **No contract text in any log** — never `OCRSpan.text`,
  `Clause.text_ko`, `value_raw`, `excerpt_ko`, or `temp_path`.
- **RT-LOG-2** Logs may contain: opaque `request_id`/`document_id`, timings,
  page/clause/signal **counts**, error codes, `scoring_config_version`. No file
  paths to user content, no IPs beyond what the web server minimally needs, and
  access logs **omit contract content and upload paths**.
- **RT-LOG-3** A redaction unit test asserts that a sample analysis produces logs
  containing none of the forbidden fields (AC-PV-2).

---

## 5. Private/public boundary (repo + artifacts)

Aligned with the existing `.gitignore` and `scripts/public_repo_preflight.sh`:

- **Git-ignored (never published):** `.fink/`, `*.pdf`, `*.zip`, `contracts/`,
  `uploads/`, `models/`, `indexes/`, `data/private/`, `data/raw/`,
  `data/unsanitized/`.
- **Private-local (`P2`):** B/C cards + glossary KO source text +
  license-gated A1/A2 excerpts; `public_export=false`.
- **Public-safe (`P0`):** specs, disclaimers, synthetic eval examples (labeled
  synthetic), schema docs, project page, paper notes.
- **Preflight gate:** `scripts/public_repo_preflight.sh` must report
  `PREFLIGHT_OK` and the candidate file list must contain no `.fink/`, `*.pdf`,
  `*.zip`, `contracts/`, or `uploads/` before any public push (S8).
- **No API keys** anywhere in repo/datasets/demo (INV-8); a secret-scan gate is
  part of S8.

---

## 6. Offline integration test (RT-OFFLINE, required by INV-5)

- **Setup:** run the full analysis pipeline (ingest → OCR → retrieve → score →
  report) with **all network access disabled** (blocked sockets / no route).
- **Pass criteria:** the pipeline completes and produces a valid
  `AnalysisReport`; **zero** outbound connection attempts are observed; latency
  and peak memory are recorded (EV-LAT, EV-MEM).
- **Failure-mode coverage:** if a network call is ever attempted, the test
  **fails** (the call must not exist on the analysis path).

---

## 7. Failure modes and degradation

| Failure | Behavior |
|---------|----------|
| OCR low confidence | proceed; lower D4; raise "needs verification"; `conf_floor` keeps risk visible (spec 03 §2) |
| Missing corpus/index artifact | refuse to score; explain "local corpus not installed"; never call remote |
| No A0–A2 grounding for a category | signals render practice-reference (score 0); category not scored; note thin grounding |
| Open-ended/opaque numbers | FIM-8 widens bands, lowers confidence; no invented value |
| Local LLM absent | explanations fall back to B/C card text (templated); scoring unaffected |
| Network present but disallowed | analysis path never calls it; offline test enforces this |
| Upload too large / unsupported type | reject with a clear local error; nothing transmitted |
| Encrypted / corrupted / oversized PDF | reject locally (MVP default for encrypted; optional local password flow); set `validation_status=rejected_*`; nothing transmitted |
| Image-only PDF page | local OCR fallback; record `OCRPage.text_source=ocr`; raster + OCR intermediate deleted with the session |

---

## 8. Runtime requirements (IDs for traceability)

- **RT-001** Desktop-full FastAPI app, LAN phone upload, fully local pipeline.
- **RT-002** Mobile-lite design-compatible: sanitized pack + on-device OCR +
  rules/ONNX; no private corpus.
- **RT-003** No remote LLM/RAG/legal-search at runtime (INV-5).
- **RT-004** Ephemeral uploads with deletion (RT-UP-*).
- **RT-005** Log redaction (RT-LOG-*).
- **RT-006** Offline integration test passes (RT-OFFLINE).
- **RT-007** Profile-neutral schemas + documented sanitization step (NFR-PORT).
- **RT-008** Measured latency + peak memory reported (EV-LAT, EV-MEM).
- **RT-009** Local-only PDF lifecycle (RT-UP-1/2/6): local raster + text-layer +
  OCR fallback; validation/rejection; ephemeral deletion of source PDF, rasters,
  and OCR intermediates; no network call (PR-005…PR-009).

Acceptance tests: spec 09 (AC-RT-*, AC-PV-*, AC-PDF-*, AC-PORT-1). Tasks: spec 08
phase S1 (ingestion/OCR, incl. PDF), S4 (web app), S5 (offline/latency/privacy
tests), S8 (release audit).

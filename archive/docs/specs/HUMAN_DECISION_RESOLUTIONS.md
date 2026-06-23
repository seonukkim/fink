# HUMAN_DECISION_RESOLUTIONS — FInk

**Owner:** project author
**Status date:** 2026-06-20
**Purpose:** binding owner decisions for specification completion.

## HD-1 — Complete missing specification deliverables

- **Status:** APPROVED
- **Decision:** Create all required files:
  - `09_ACCEPTANCE_CHECKLIST.md`
  - `10_TRACEABILITY_MATRIX.csv`
  - `11_ASSUMPTIONS_OPEN_QUESTIONS.md`
  - `SPEC_BUILD_REPORT.md`

## HD-2 — PDF upload is a mandatory MVP input

- **Status:** APPROVED_AND_REQUIRED
- **Decision:** End-user contract PDF upload is a mandatory MVP feature, together
  with camera/image upload and pasted text.
- **Supported local input paths:**
  - text-layer PDF;
  - scanned/image-only PDF;
  - mixed PDF;
  - multi-page PDF.
- **Required behavior:**
  - parse and rasterize locally;
  - use text-layer extraction when available;
  - use local OCR fallback for image-only pages;
  - allow page preview, reorder, rotate, delete, and OCR correction;
  - reject encrypted, corrupted, oversized, or unsupported PDFs clearly;
  - treat every upload as `P3_USER_EPHEMERAL`;
  - delete raw PDF bytes, page rasters, and OCR intermediates on clear, timeout,
    session end, and application shutdown;
  - never persist raw filenames or contract text in logs;
  - never send PDF bytes or extracted text to a remote LLM, cloud RAG, telemetry,
    external OCR, or web service.
- **Repository boundary:**
  - `*.pdf` remains excluded from Git because uploaded user documents and source
    reference PDFs must not be published;
  - this Git exclusion does not remove PDF upload from the product.
- **Clarification:** “Do not put PDFs in `.fink/inputs`” applies only to the
  research/reference corpus supplied to agents. It does not apply to the future
  local application's end-user upload capability.

## HD-3 — Governing offering, exact deadline, and MVP cut

- **Status:** RESOLVED
- **Governing offering:** 2026 Spring IE412 AI for Finance.
- **Binding deadline:** 2026-06-24 23:59 KST.
- **Required submission MVP:**
  1. responsive desktop/mobile web UI;
  2. camera/image/PDF/pasted-clause input;
  3. local PDF parsing and local OCR;
  4. page preview, rotation, reordering, and OCR correction;
  5. clause segmentation;
  6. local authority-aware retrieval;
  7. deterministic rule-based Contractual Financial Review Priority scoring;
  8. four independent report dimensions;
  9. FIM-1, FIM-2, FIM-3, FIM-7, and FIM-8;
  10. editable low/base/high assumptions;
  11. synthetic/sanitized evaluation;
  12. public GitHub repository;
  13. static project page;
  14. paper/report notes prepared for the ICML 2026 template.
- **Stretch:**
  - local-model-only and hybrid scoring;
  - full calibration;
  - expanded decision-focused study;
  - mobile-native ONNX profile;
  - exhaustive official-source extraction.

## HD-11 — Record-level Stage 0/1/2 inputs

- **Status:** CONDITIONAL
- **Decision:** Mark RESOLVED only when
  `scripts/verify_spec_inputs.sh` reports `SPEC_INPUTS_OK`.
- **Required behavior:** reconcile actual Stage 0–3 and ChatGPT files rather than
  preserving reconstructed counts.

## HD-12 — Automated gate resolution under conservative + open-license policy

- **Status:** APPROVED (owner, supersedes the OPEN status of HD-4..HD-8 and HD-10).
- **Decision:** The loop runs **fully automatically** except for the final
  academic-integrity attestation. The legal/authority gates (HR-01, HR-02, HR-03,
  HR-04, HR-05, HR-06) are **auto-resolved by conservative mode**, and the model
  gates (MODEL_LICENSES/DOWNLOAD/PROFILE) are **auto-resolved by an open-source-only
  license floor + size cap**.
- **Why this is safe (no legal/finance expert needed):** the product is
  conservative *by construction* — it never asserts current law, fraud, illegality,
  validity, voidness, unfairness, or guaranteed loss; evidence is `UNVERIFIED` and
  date-stamped; B/C sources contribute zero to scoring; scoring is A0–A2-only. The
  gates therefore do not require certifying "the law is verified"; they require the
  system to stay in that conservative regime, which the **machine gates enforce on
  every task** (`legal_verdict_scan`, `authority_invariant`, `model_license_floor`,
  `tracking_scan`, the INV suite, ...). Auto-resolving the human gates does not relax
  any machine gate.
- **License floor:** open-source allowlist only — `apache-2.0, mit, bsd-2-clause,
  bsd-3-clause, isc, cc0-1.0, cc-by-4.0`. Gated, unknown, custom, noncommercial, and
  research-only are rejected by default. Downloads are capped by
  `max_download_size_gb`; weights never enter Git.
- **Still human (NOT auto-resolved):** HD-9 / **HR-08** (AI-use + author attestation
  before release). The loop completes everything up to release; the author flips
  HR-08 once at submission after personally reviewing the AI-assisted outputs.
- **Unchanged:** the Non-negotiable guardrails below and HD-2/HD-3 scope.

## Decisions intentionally left OPEN

- HD-9 / HR-08: AI-use and human-verification attestation (the single final human
  step; see HD-12).

## Non-negotiable guardrails

- The score is never a fraud, illegality, validity, unfairness, or legal-outcome
  verdict.
- B/C sources contribute zero to authority-supported scoring.
- Missing inputs lower confidence or request user input; they never invent money.
- Monetary exposure types are not summed into a misleading total loss.
- Runtime analysis requires no remote API.
- Private source text, real contracts, PDFs, API keys, `.fink`, and raw run
  inputs are never published.
- The ICML 2026 template remains byte-unchanged.

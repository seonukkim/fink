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

## Decisions intentionally left OPEN

- HD-4 / HR-01: current-law verification
- HD-5 / HR-02: official webtoon grounding verification
- HD-6 / HR-03: sensitive KO–EN legal-alias review
- HD-7 / HR-05: dated-figure verification
- HD-8 / HR-06: glossary category spot-check
- HD-9 / HR-08: AI-use and human-verification attestation
- HD-10 / HR-04: missing artist-welfare source

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

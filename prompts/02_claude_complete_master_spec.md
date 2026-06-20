You are Claude Opus 4.8 with maximum effort.

Continue and complete the existing FInk Master Specification after the first
build stopped at its max-turn limit.

Do not rebuild specs 01–08 wholesale.
Do not implement code.

Read all structured inputs under `.fink/inputs/`, all current specs, the audit,
and `docs/specs/HUMAN_DECISION_RESOLUTIONS.md`.

## Binding owner corrections

Apply these decisions everywhere in the specification:

1. PDF upload is a **mandatory MVP input**, not excluded.
2. The product must accept:
   - text-layer PDF,
   - scanned/image-only PDF,
   - mixed PDF,
   - multi-page PDF.
3. PDF processing is local-only and ephemeral:
   - local text extraction,
   - local rasterization,
   - local OCR fallback,
   - page preview/reorder/rotate/delete,
   - OCR correction,
   - clear rejection for encrypted/corrupted/oversized/unsupported files,
   - raw PDF, rasters, and OCR intermediates deleted after use,
   - no contract text or raw filename in logs,
   - no remote API, cloud OCR, cloud RAG, telemetry, or remote LLM.
4. `*.pdf` being Git-ignored is a publication/privacy rule, not a product-scope
   exclusion.
5. Governing course: **2026 Spring IE412 AI for Finance**.
6. Binding deadline: **2026-06-24 23:59 KST**.
7. Replace every stale `June 24, 24:00`, `2026-06-24 24:00`, or ambiguous
   deadline reference with `2026-06-24 23:59 KST`.

## Primary completion objective

Create:

- `docs/specs/09_ACCEPTANCE_CHECKLIST.md`
- `docs/specs/10_TRACEABILITY_MATRIX.csv`
- `docs/specs/11_ASSUMPTIONS_OPEN_QUESTIONS.md`
- `docs/specs/SPEC_BUILD_REPORT.md`
- `docs/specs/SPEC_COMPLETION_REPORT.md`

Reconcile actual Stage 0–3 and ChatGPT files. Do not fabricate counts.

## Mandatory PDF requirements and acceptance coverage

Ensure specs 01, 02, 04, 06, 08, 09, and 10 explicitly trace:

- PDF as mandatory MVP input;
- MIME and magic-byte validation;
- text-layer extraction;
- image-only OCR fallback;
- mixed-page handling;
- multi-page handling;
- encrypted PDF rejection or local password flow, with MVP default rejection;
- corrupted PDF rejection;
- configurable maximum pages and bytes;
- local rasterization only;
- page preview;
- page reorder;
- page rotation;
- page deletion;
- OCR text correction;
- per-page provenance;
- temporary workspace permissions;
- deletion of source PDF, rasters, and OCR intermediates;
- no raw filename or contract text in logs;
- no network call;
- offline integration test;
- PDF-specific unit and integration tests;
- mobile-browser upload and desktop upload;
- Korean and English PDF content.

Define stable acceptance IDs for at least:

- PDF text-layer extraction
- PDF OCR fallback
- mixed PDF
- page operations
- encrypted/corrupt/oversized rejection
- deletion lifecycle
- log redaction
- offline execution

## Required missing documents

### 09 Acceptance checklist

Define every referenced AC ID exactly once, including objective tests for every
invariant, requirement, FIM module, PDF requirement, privacy rule, bilingual
behavior, evaluation metric, paper sync, and release gate.

### 10 Traceability matrix

CSV columns:

requirement_id,requirement_summary,source_spec,acceptance_ids,task_ids,
metric_ids,data_requirements,human_gate,paper_section,project_page_section,
evidence_artifact,status,notes

No MVP requirement may lack acceptance and implementation tasks.

### 11 Assumptions/open questions

Record all AQ/HD/HR items. Apply owner resolutions exactly.
Keep HD-4 through HD-10 open unless evidence exists.

### SPEC_BUILD_REPORT

Record exact inputs, actual counts, reconciliations, changed files, unresolved
conflicts, cross-reference checks, and human-decision statuses.

Final line:

- `SPEC_BUILD_STATUS: READY_FOR_AUDIT`, or
- `SPEC_BUILD_STATUS: BLOCKED_INPUTS`

## Cross-reference repair

Repair stale references in the Master Spec and specs 01–08, especially:

- PDF scope;
- deadline;
- document map;
- AC/AQ/HR/task/metric references;
- actual input counts.

Do not weaken authority, privacy, financial, bilingual, or local-runtime
guardrails.

## Validation before stopping

Confirm:

- all five completion outputs exist and are non-empty;
- every AC and AQ reference resolves;
- every MVP task is traceable;
- PDF upload is mandatory;
- PDF input remains local/ephemeral;
- deadline is exactly `2026-06-24 23:59 KST`;
- B/C never affect score;
- missing information never invents money;
- exposure types remain separate;
- no implementation code was created.

Write results to `SPEC_COMPLETION_REPORT.md` and stop.

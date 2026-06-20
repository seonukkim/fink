# 01 — Product Requirements

**Parent:** `docs/FINK_MASTER_SPEC.md` · **Spec version:** 1.0.0
Inherits all invariants INV-1…INV-9. This file defines product semantics,
numbered requirements, non-goals, and MVP-vs-stretch scope.

---

## 1. Product semantics

### 1.1 The primary score
- **Name (EN):** Contractual Financial Review Priority Score
- **Name (KO):** 계약상 금융 검토 우선도
- **Range:** integer 0–100, **ordinal/relative prioritization signal**, not a
  probability and not a calibrated risk percentage.
- **Meaning:** "how much financial-review attention this document/clause
  warrants before signing," relative to FInk's grounded signal set.
- **Forbidden readings (must be denied in copy, schema, and tooltips):** fraud
  probability, illegality probability, contract validity/voidness, legal
  conclusion, unfairness verdict, guaranteed or expected loss.

### 1.2 Four independent dimensions (INV-3)
A report **must** display all four, never collapsed:

| Dim | Field | Type | Notes |
|-----|-------|------|-------|
| D1 | `review_priority_score` | int 0–100 | with category breakdown F1–F9 |
| D2 | `monetary_exposure` | low/base/high per exposure type | nominal, PV, opportunity, liability kept separate |
| D3 | `time_exposure` | typed fields + pathway label | no fabricated court/negotiation duration |
| D4 | `confidence` | OCR + evidence + data-completeness | drives uncertainty, not the amount |

### 1.3 Bilingual semantics (INV-4)
Korean evidence is primary; English is alias/explanation
(`generated_translation=true`). A Korean query and its English alias resolve to
the same `canonical_id`. Generated English is never labeled "evidence."

---

## 2. Functional requirements

Each requirement has an ID, an MVP/Stretch tag, and a verification hook
(acceptance test in spec 09, metric in spec 05, or task in spec 08).

### 2.1 Ingestion
- **PR-001 (MVP)** Accept input as: phone-camera capture, image upload
  (JPG/PNG/HEIC/WEBP), **PDF upload**, or pasted clause text. *Verify:* AC-IN-1.
- **PR-002 (MVP)** Accept multi-page documents; pages reorderable and
  rotatable before analysis. *Verify:* AC-IN-2.
- **PR-003 (MVP)** All ingestion is **local-only**: PDFs are rasterized/parsed
  on-device; nothing is sent to any network service. *Verify:* AC-RT-OFFLINE.
- **PR-004 (MVP)** Uploaded artifacts are **ephemeral** (`P3_USER_EPHEMERAL`):
  held in a temp workspace, deleted at session end or on explicit "clear,"
  never written to a durable public path, never logged. *Verify:* AC-PV-1.
  > **Note (PDF scope — resolved by owner decision HD-2, AQ-02):** the upstream
  > README/taxonomy recorded a "no PDF upload" *design direction*. The owner has
  > **overridden** it: PDF upload is a **mandatory MVP input** (see PR-005…PR-009).
  > Resolution preserved here: PDF is parsed, rasterized, and OCR'd **locally
  > only**, treated as `P3_USER_EPHEMERAL` with the same deletion treatment as
  > images; a PDF's bytes or extracted text are **never** sent to a remote LLM,
  > cloud RAG, external OCR, telemetry, or web service. `*.pdf` stays git-ignored
  > as a **publication/privacy rule** (uploaded and reference PDFs must not be
  > published) — this does **not** remove PDF upload from the product. AQ-02 is
  > resolved in spec 11.

#### 2.1.1 PDF ingestion (mandatory MVP — HD-2)
PDF upload is a **mandatory MVP input** on equal footing with camera, image, and
paste. All PDF handling is **local-only and ephemeral** (INV-5, INV-8); see spec
04 §3.1 for the lifecycle and spec 06 §2–3 for the flow.

- **PR-005 (MVP)** Accept **text-layer**, **scanned/image-only**, **mixed**, and
  **multi-page** PDFs. *Verify:* AC-PDF-TEXT, AC-PDF-OCR, AC-PDF-MIXED,
  AC-PDF-MULTIPAGE.
- **PR-006 (MVP)** Validate every PDF by **MIME type and magic-byte** (`%PDF-`)
  sniff; **reject** corrupted, unsupported, and oversized files clearly, with
  **configurable maximum pages and bytes**; **encrypted PDFs are rejected by
  default** (MVP), with an optional **local password-entry flow** documented as
  the only alternative (no remote decryption). *Verify:* AC-PDF-MIME,
  AC-PDF-CORRUPT, AC-PDF-LIMITS, AC-PDF-ENCRYPTED.
- **PR-007 (MVP)** Process PDFs by **local rasterization** and **local text-layer
  extraction**, falling back to **local OCR** for image-only pages; record
  **per-page provenance** (text-layer vs OCR) on each page. *Verify:*
  AC-PDF-RASTER, AC-PDF-TEXT, AC-PDF-OCR, AC-PDF-PROVENANCE.
- **PR-008 (MVP)** Offer page **preview, reorder, rotate, delete**, and **OCR
  text correction** for PDF pages (shared with the image flow, PR-002/PR-011).
  *Verify:* AC-PDF-PAGEOPS, AC-PDF-OCRCORRECT.
- **PR-009 (MVP)** Source PDF bytes, page rasters, and OCR intermediates are
  written only to the **ephemeral workspace** with **restricted permissions** and
  **deleted** on clear/timeout/session-end/shutdown; the **raw filename and
  contract text are never logged**; **no network call** occurs at any PDF stage;
  the PDF path is covered by the **offline integration test** and **PDF-specific
  unit + integration tests**; it works from a **mobile browser and desktop**; it
  handles **Korean and English** PDF content. *Verify:* AC-PDF-WORKSPACE,
  AC-PDF-DELETE, AC-PDF-LOG, AC-PDF-OFFLINE, AC-PDF-TESTS, AC-PDF-MOBILE,
  AC-PDF-BILINGUAL.

### 2.2 OCR and clause reconstruction
- **PR-010 (MVP)** Local OCR produces page text with per-span bounding boxes and
  per-span confidence; Korean + English. *Verify:* AC-OCR-1, EV-OCR-CER/WER.
- **PR-011 (MVP)** OCR preview with inline correction; user edits update
  downstream extraction and are recorded as `HumanCorrection`. *Verify:* AC-OCR-2.
- **PR-012 (MVP)** Clause segmentation reconstructs clause/sub-clause units with
  references back to source spans. *Verify:* AC-SEG-1, EV-SEG.
- **PR-013 (MVP)** Numeric/temporal terms (money, %, dates, durations) are
  extracted with exact-match targets and provenance. *Verify:* AC-EXTRACT-1,
  EV-EXACT-MONEY/PCT/DATE/DUR.

### 2.3 Retrieval and authority grounding
- **PR-020 (MVP)** Bilingual keyword + canonical-ID retrieval over the local
  hierarchical corpus; Korean and English queries hit the same concept.
  *Verify:* EV-KOEN.
- **PR-021 (MVP)** Retrieval returns B/C cards for explanation **and** A0–A2
  evidence for grounding, each carrying `source_id`, `authority_tier`,
  `verification_status`. *Verify:* AC-AUTH-1.
- **PR-022 (MVP)** A risk signal is **score-eligible only if** an A0–A2 record
  grounds it; B/C-only signals render as "practice reference," score 0.
  *Verify:* AC-AUTH-2 (mirrors PASS-gate 1).
- **PR-023 (MVP)** Conflicting sources are never silently merged; both are shown
  with provenance and precedence (2025 webtoon form > 2018 form on overlap).
  *Verify:* AC-AUTH-3.

### 2.4 Explanation and questions
- **PR-030 (MVP)** Each flagged clause shows a plain-language financial
  explanation (KO primary, EN alias), sourced from B/C cards, **labeled
  non-scoring**. *Verify:* AC-UX-EXPL.
- **PR-031 (MVP)** Generate **creator-specific questions to ask before signing**,
  derived from the checklist (52 items) and cards, tied to the flagged clause.
  *Verify:* AC-UX-Q.

### 2.5 Monetary and time exposure
- **PR-040 (MVP)** Show low/base/high **monetary exposure** per exposure type
  via FIM-1…FIM-3, FIM-7 (+FIM-8 uncertainty); FIM-4/5/6 computed once the user
  supplies assumptions. *Verify:* spec 03 unit tests, AC-FIN-*.
- **PR-041 (MVP)** Keep nominal/observed leakage, present-value loss, opportunity
  cost, and liability exposure **visually and structurally separate**.
  *Verify:* AC-FIN-SEP.
- **PR-042 (MVP)** Show **time exposure** as typed fields plus a categorical
  pathway label; never fabricate court/negotiation duration. *Verify:* AC-TIME-1.
- **PR-043 (MVP)** All financial assumptions are **user-editable**; recompute is
  live and labeled "synthetic assumption." *Verify:* AC-FIN-EDIT.

### 2.6 Confidence and human review
- **PR-050 (MVP)** Show D4 confidence decomposed into OCR confidence, evidence
  confidence, and data-completeness; missing financial inputs widen exposure
  bands and lower confidence (FIM-8), never inflate amounts. *Verify:* AC-CONF-1.
- **PR-051 (MVP)** Surface **human-review guidance**: an `estimated_human_review_minutes`
  heuristic and a pathway label; clear "not legal advice" disclaimer.
  *Verify:* AC-TIME-2, AC-UX-DISC.

### 2.7 Output and export
- **PR-060 (MVP)** Produce an `AnalysisReport` rendered in the UI and exportable
  as a **local file** (HTML/Markdown/JSON) with no network calls; export
  contains no raw uploaded image bytes by default. *Verify:* AC-OUT-1.
- **PR-061 (Stretch)** Optional local-LLM narrative summary of the report,
  clearly labeled generated, never used as evidence or to set a score.

---

## 3. Non-functional requirements

- **NFR-LOCAL (MVP)** No remote LLM, cloud RAG, or external legal search at
  runtime (INV-5). *Verify:* AC-RT-OFFLINE.
- **NFR-LATENCY (MVP)** Analysis latency and peak memory are **measured and
  reported** on a reference machine (no hard SLA asserted as validated; report
  the measurement). *Verify:* EV-LAT, EV-MEM.
- **NFR-PRIVACY (MVP)** Privacy boundary INV-8 enforced; logs carry no contract
  text and no upload paths beyond opaque session IDs. *Verify:* AC-PV-2.
- **NFR-PORT (MVP)** Schemas are profile-neutral and portable to mobile-lite
  (spec 04). *Verify:* AC-PORT-1.
- **NFR-A11Y (MVP)** Responsive layout works on a phone browser and a desktop
  browser; touch targets and contrast meet a stated baseline. *Verify:* AC-UX-RESP.
- **NFR-I18N (MVP)** Full KO and EN UI; KO is default; no machine-translated
  text presented as source. *Verify:* AC-UX-I18N.
- **NFR-CONFIG (MVP)** Scoring weights, thresholds, discount-rate defaults, and
  band multipliers live in versioned config, not code; all marked heuristic
  (INV-9). *Verify:* AC-SC-CONFIG.

---

## 4. Non-goals (product-level; complements master §6)

1. No verdict on fraud/illegality/validity/unfairness/legal outcome (INV-2).
2. No legal advice; FInk is a triage and question-generation aid.
3. No automatic IP valuation from text (FIM-6 requires user scenarios).
4. No expected-loss/penalty computation without explicit user probability (FIM-7).
5. No precise court/negotiation/dispute **duration** numbers (labels only).
6. No remote inference, telemetry, analytics, or crash-reporting that transmits
   document content.
7. No persistence of uploaded contract content beyond the ephemeral workspace.
8. No publication of real contracts, private-book full text, or long official
   excerpts.
9. No claim of validated accuracy, calibration, or "optimal" weights (INV-9).

---

## 5. MVP vs stretch scope summary

| Capability | MVP | Stretch |
|------------|-----|---------|
| Camera / image / PDF / paste ingestion | ✅ | — |
| Page reorder / rotate / OCR correction | ✅ | — |
| Local OCR (KO+EN) + clause segmentation | ✅ | better models |
| Authority-gated retrieval over 20-record sample | ✅ | full extraction, 2025 handbook, A0 |
| **Rule-based** review signals + score | ✅ | local-model-only, hybrid |
| FIM-1/2/3/7 + FIM-8 from terms | ✅ | — |
| FIM-4/5/6 from user assumptions | ✅ | richer scenario libraries |
| Four-dimension report + local export | ✅ | LLM narrative (PR-061) |
| Editable assumptions, questions-before-signing | ✅ | — |
| Offline integration test | ✅ | — |
| Core eval (OCR exact, Recall@k, Macro-F1, benign-FPR, latency, unit tests) | ✅ | calibration, decision-focused utility, stability sweeps |
| Mobile-responsive web frontend | ✅ | mobile-lite ONNX on-device pack |
| Optional local LLM assist | optional | hybrid scoring + ablation |

---

## 6. Primary user flows (requirement-level; UI detail in spec 06)

1. **Capture → analyze:** open on phone over LAN → camera capture pages →
   reorder/rotate → OCR preview/correct → run → four-dimension report.
2. **Upload → analyze:** desktop → drag image/PDF or paste clause → same path.
3. **Refine assumptions:** edit FIM inputs (discount rate, hourly value,
   scenario probabilities, alternative revenue) → live recompute → compare
   low/base/high.
4. **Decide:** read prioritized clauses + official grounding + questions →
   export local report → bring questions to counterparty/lawyer.

---

## 7. Acceptance (pointers)
Objective tests for every PR-/NFR- ID above are enumerated in
`docs/specs/09_ACCEPTANCE_CHECKLIST.md`; metrics in
`docs/specs/05_EVALUATION_AND_DECISION_FOCUSED_METRICS.md`; tasks in
`docs/specs/08_IMPLEMENTATION_BACKLOG.yaml`; traceability in
`docs/specs/10_TRACEABILITY_MATRIX.csv`.

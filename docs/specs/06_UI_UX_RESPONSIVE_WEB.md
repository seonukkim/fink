# 06 — UI/UX (Responsive Web)

**Parent:** `docs/FINK_MASTER_SPEC.md` · **Spec version:** 1.0.0
Inherits INV-1…INV-9. Responsive desktop + mobile flows for the desktop-local
full profile (mobile browser over trusted LAN). KO is the default locale; EN is
a toggle and is always marked generated for non-source text.

---

## 1. Layout and responsiveness (UX-LAYOUT)

- Single responsive web app; breakpoints for phone (single column, large touch
  targets), tablet, and desktop (two-pane: document left, analysis right).
- Mobile-first capture; desktop drag-and-drop and paste.
- Baseline accessibility: legible contrast, ≥44px touch targets, keyboard
  navigation, locale toggle KO/EN (NFR-A11Y, NFR-I18N).
- A persistent **local-only / privacy** indicator (no network during analysis)
  and a persistent **"not legal advice"** banner.

---

## 2. Ingestion flows

### UX-IN-CAMERA (PR-001)
Phone opens the app over LAN → "Capture pages" → camera per page → live
thumbnail strip → continue/finish. Trusted-LAN warning shown once.

### UX-IN-IMAGE (PR-001)
Drag/drop or pick JPG/PNG/HEIC/WEBP; multi-select; thumbnails.

### UX-IN-PDF (PR-001, PR-003, PR-005…PR-009)
Upload a PDF (text-layer, scanned/image-only, mixed, or multi-page) from a
**mobile browser or desktop**; it is validated, rasterized, text-extracted, and
OCR'd (image-only pages) **locally**; pages appear in the strip with a small
per-page badge showing provenance (text-layer vs OCR). Banner: "PDF processed
locally; not uploaded anywhere." Rejected files (corrupted, unsupported,
oversized, or encrypted-by-default) show a clear local error explaining why and
how to proceed (e.g., enter a password locally for an encrypted PDF). Pages then
flow into UX-PAGE-ORG (reorder/rotate/delete) and UX-OCR-PREVIEW (OCR
correction). PDF upload is a **mandatory MVP input** per owner decision HD-2
(AQ-02 resolved in spec 11).

### UX-IN-PASTE (PR-001)
Paste clause text directly; skips OCR; goes straight to extraction.

All ingestion shows the ephemeral-storage notice and a **Clear now** button
(RT-UP-2).

---

## 3. Pre-analysis editing

### UX-PAGE-ORG (PR-002)
Reorder pages (drag), rotate (0/90/180/270), delete a page; updates
`OCRPage.page_index`/`rotation_deg`.

### UX-OCR-PREVIEW (PR-010, PR-011)
Show OCR overlay with per-span boxes colored by confidence; tap/click a span to
edit text inline. Edits create `HumanCorrection` and re-trigger extraction for
affected clauses. A "low-confidence" filter highlights spans needing review.

---

## 4. Report — four independent dimensions (INV-3)

The report header shows **four separate panels**, never one merged number:

### UX-D1-SCORE (Review Priority)
- `review_priority_score` 0–100 with an **attention band** label (low / medium /
  high) and the KO/EN name (계약상 금융 검토 우선도 / Contractual Financial
  Review Priority). Tooltip explicitly denies fraud/illegality/validity/loss
  readings (INV-2).
- Category breakdown **risk-category cards** (UX-CARDS).

### UX-D2-MONEY (Monetary Exposure)
- Low/base/high per **exposure type**, kept in separate sub-panels: nominal
  leakage, present-value loss, deferral, opportunity cost, liability exposure
  (spec 03 §8). **No grand total.** Each shows assumptions and "synthetic
  assumption" labels and FIM-8 uncertainty flags.

### UX-D3-TIME (Time Exposure)
- Typed fields (due/delay days, durations, notice, months-to-recoup,
  measured runtime, estimated human-review minutes) + the **pathway label**
  (categorical). Explicit note: no court/negotiation duration is estimated.

### UX-D4-CONF (Evidence & OCR Confidence)
- OCR confidence, evidence confidence (with UNVERIFIED notice), data
  completeness, overall confidence, and human-readable **drivers**.

---

## 5. Risk-category cards (UX-CARDS)

One card per active F-category (F1–F9):
- category name (KO/EN), category score, count of eligible vs practice-reference
  signals;
- top flagged clauses with **highlighted clause evidence** (UX-HILITE): the
  clause text with the triggering span highlighted, linked back to the page;
- **official-source comparison** (UX-EVID): the grounding `EvidenceRecord`(s)
  with `source_id`, `authority_tier`, short (<15-word) excerpt, and
  `verification_status` (UNVERIFIED badge today); conflicting sources shown
  side-by-side with precedence (2025 > 2018) — never silently merged (PR-023);
- **explanation** from B/C cards with a clear **"practice reference / non-scoring"**
  badge (PR-030);
- **questions before signing** (UX-QUESTIONS, PR-031) tied to the clause.

Cross-cutting X1–X5 items appear in a separate **"context (non-scoring)"**
section so they never look like score drivers.

---

## 6. Editable assumptions (UX-ASSUME, PR-040/043)

- An **Assumptions** panel exposes `FinancialScenarioInputs`: discount rate,
  sales low/base/high, hourly value, hours/unit, unpaid units, alternative
  monthly revenue, scenario probabilities, secondary-rights scenarios, penalty
  probability.
- Live recompute of FIM-1…FIM-7; all defaults labeled **synthetic assumption**.
- FIM-4/5/6 and FIM-7 expected-value panels are **blank with a prompt** until
  the user supplies the required inputs (never a guessed number; INV-6).
- A reset-to-defaults and a "these are your assumptions, not facts" note.

---

## 7. Questions before signing (UX-QUESTIONS)

Aggregated, deduplicated list of creator-specific questions (from the 52-item
checklist + cards), grouped by category and clause, exportable with the report.
Marked non-scoring.

---

## 8. Export and disclaimers

### UX-EXPORT (PR-060)
"Export local report" → HTML/Markdown/JSON saved locally; no network call; raw
image bytes excluded by default; includes disclaimers, four dimensions,
grounding, assumptions, and questions.

### UX-DISCLAIMER (PR-051, INV-2)
Persistent and in-export disclaimers: "Review priority, not a legal/fraud/
validity verdict; not legal advice; figures are scenario estimates from your
assumptions; official sources are UNVERIFIED pending A0 confirmation; KO is the
source language, EN is generated."

---

## 9. Empty/edge states

- No financial inputs yet → modules show "add assumptions to estimate."
- Thin/zero grounding in a category → "no official grounding available;
  shown as practice reference."
- Low OCR confidence → banner + "verify highlighted spans."
- Network attempted (should never happen) → hard error, analysis already local.

---

## 10. UX requirement IDs (traceability)

`UX-LAYOUT, UX-IN-CAMERA, UX-IN-IMAGE, UX-IN-PDF, UX-IN-PASTE, UX-PAGE-ORG,
UX-OCR-PREVIEW, UX-D1-SCORE, UX-D2-MONEY, UX-D3-TIME, UX-D4-CONF, UX-CARDS,
UX-HILITE, UX-EVID, UX-QUESTIONS, UX-ASSUME, UX-EXPORT, UX-DISCLAIMER`.
Acceptance: spec 09 (AC-UX-*, AC-IN-*, AC-PDF-PAGEOPS, AC-PDF-OCRCORRECT,
AC-PDF-MOBILE, AC-OUT-1). Tasks: spec 08 phase S4.

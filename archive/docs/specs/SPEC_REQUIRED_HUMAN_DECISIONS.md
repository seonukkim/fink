# SPEC_REQUIRED_HUMAN_DECISIONS — FInk

**Date:** 2026-06-21 (Pass 1) · **Status-synced:** 2026-06-21 (Pass 2 re-audit).
**Owner of decisions:** project author / responsible human.
**Companion to:** `docs/specs/SPEC_AUDIT_REPORT.md`.

This register lists decisions a **person** must make before the affected work
proceeds. It was first written by the Pass-1 auditor, when every item was open.

> **Pass-2 status sync (2026-06-21).** The owner has since recorded binding
> resolutions in `docs/specs/HUMAN_DECISION_RESOLUTIONS.md`, and
> `docs/specs/11_ASSUMPTIONS_OPEN_QUESTIONS.md` is the **authoritative live
> register**. This file is updated to current status for consistency:
> **HD-1, HD-2, HD-3, HD-11 are RESOLVED**; **HD-4…HD-10 remain OPEN** by design.
> Where any difference persists, spec 11 and `HUMAN_DECISION_RESOLUTIONS.md` win.
> See `docs/specs/SPEC_REAUDIT_CHANGELOG.md`.

Status legend: **OPEN** (undecided) · **RESOLVED** (decided/evidenced).
Priority mirrors upstream `33_REQUIRED_HUMAN_REVIEW.csv` (P0 highest) where
applicable.

---

## A. Spec-completion decisions (introduced by the Pass-1 audit)

### HD-1 — Authorize completion of the four missing spec files · P0 · RESOLVED
**Decision:** approve re-running/continuing the spec-build to author
`09_ACCEPTANCE_CHECKLIST.md`, `10_TRACEABILITY_MATRIX.csv`,
`11_ASSUMPTIONS_OPEN_QUESTIONS.md`, and `SPEC_BUILD_REPORT.md`, **or** explicitly
de-scope any of them with a recorded rationale.
**Resolution (HD-1, APPROVED):** all four were authored, plus
`SPEC_COMPLETION_REPORT.md`. The Pass-2 re-audit confirms all are present and that
every `AC-*`/`AQ-*`/task/metric cross-reference now resolves.

### HD-2 — PDF-upload design reversal (AQ-02) · P1 · RESOLVED
**Decision:** confirm that **local-only PDF upload is in scope**, overriding the
upstream taxonomy's "no PDF upload" design direction.
**Resolution (HD-2, APPROVED_AND_REQUIRED):** PDF upload is a **mandatory MVP
input**, processed locally and ephemerally (text-layer/scanned/mixed/multi-page;
parse + raster + OCR fallback; page preview/reorder/rotate/delete + OCR
correction; reject encrypted-by-default/corrupted/oversized/unsupported; delete
source PDF + rasters + OCR intermediates; no raw filename or contract text in
logs; no remote API/cloud OCR/cloud RAG/telemetry/remote LLM). `*.pdf` stays
git-ignored as a **publication/privacy** rule, **not** a product-scope exclusion.
AQ-02 is now a real, defined assumption in spec 11 (no longer pinned to a
nonexistent id).
**Constraint preserved:** privacy stays local-only/ephemeral; do not relax.

### HD-3 — Governing course term and submission deadline (HR-07) · P1 · RESOLVED
**Decision:** confirm the governing offering (page-1 header "2024 Spring" vs
filename "2026spring") and the binding deadline, then decide the achievable MVP
cut for the real timebox.
**Resolution (HD-3):** governing offering **2026 Spring IE412 AI for Finance**;
binding deadline **2026-06-24 23:59 KST**; MVP cut per
`HUMAN_DECISION_RESOLUTIONS.md` (this supersedes the earlier "June 24, 24:00"
phrasing). The required MVP and the deferred stretch list are recorded in spec 11
§2 and spec 07 §6.
**Standing note (non-binding):** with today = 2026-06-21 the literal deadline
leaves ~3 days, so the MVP/stretch split is the execution lever — prioritize
ingest→OCR→segment→authority-gated retrieval→rule signals→four-dimension report
with FIM-1/2/3/7/8 and the offline + formula-unit tests; defer model/hybrid arms,
DFU, calibration, mobile-lite, and the project page. (Execution risk, owner-owned;
not a spec defect.)

### HD-11 — Supply record-level Stage-0/1/2 inputs (M3) · P1 · RESOLVED
**Decision:** provide the actual `01–03`, `10–16`, `20–24` (and ChatGPT) source
files, or accept that the spec's record counts/taxonomy remain reconstructed.
**Resolution (HD-11):** the full record-level package is present under
`.fink/inputs/`. The Pass-2 re-audit independently verified the counts against the
source files (35 sources, 156 glossary terms, 64 cards, 52 checklist, 20 evidence,
29+3 features, 9F+5X taxonomy, DR-1…DR-16, 11 metrics) and reconciled AQ-01
(taxonomy) and AQ-03 (features). Runtime re-check stays `FINK-S0-01`
(`scripts/verify_spec_inputs.sh` → `SPEC_INPUTS_OK`).

---

## B. Upstream human-review items carried forward (`33_REQUIRED_HUMAN_REVIEW.csv`)

These remain **OPEN** and gate the build/paper phase. The spec routes the
score-/release-gating ones to human gates in `08`; they are restated here so no
decision is lost.

### HD-4 — A0 current-law verification (HR-01) · P0 · OPEN
Fetch/confirm the ten `law.go.kr` statutes (article / effective_date /
retrieved_at). **Blocks:** any "current law" statement; webtoon grounded score.
Until closed, every evidence record stays `UNVERIFIED`, all dated figures
`NOT_VERIFIED_CURRENT`. **Do not** assert any statute as current before this.

### HD-5 — 2025 webtoon handbook + 2023 fair-guide extraction (HR-02) · P0 · OPEN
Split the most-current webtoon official source into A1 (form) / A2 (commentary)
evidence. **Blocks:** webtoon-specific grounded scoring. Until closed, webtoon
grounding leans on the 2018 forms (precedence: 2025 > 2018 on overlap).

### HD-6 — KO-EN non-equivalence legal sign-off (HR-03) · P1 · OPEN
A legally-informed person confirms the 8 sensitive terms (assignment/license,
해제/해지, work-made-for-hire, publicity, liquidated damages, consideration,
deposit) are treated as **retrieval aliases only**, not legal equivalence.
**Blocks:** any cross-lingual legal claim.

### HD-7 — Verify dated 2018–2021 figures (HR-05) · P1 · OPEN
Re-check numbers/periods/procedural steps against A0 before any are used as
current. **Blocks:** using any dated figure as current.

### HD-8 — Glossary `risk_category` spot-check (HR-06) · P2 · OPEN
Human confirms keyword-heuristic category tags, esp. dual-category/edge terms.
**Blocks:** retrieval-routing accuracy (quality, not correctness). P2 — does not
gate release (AC-REL-HR gates P0/P1 only).

### HD-9 — AI-use log + human-verification attestation (HR-08) · P1 · OPEN
Author attests understanding/verification of AI-assisted outputs (including this
preprocessing, the spec build, and both audit passes) in `docs/ai-use-log.md`.
**Blocks:** R0 AI-disclosure compliance; release.

### HD-10 — Re-acquire empty artist-welfare casebook (HR-04) · P2 · OPEN
The `한국예술인복지재단 권리침해행위 사례집` file is 210 bytes of whitespace;
intended X4/X5 signals are absent until re-acquired. **Blocks:** artist-welfare /
rights-infringement signals (cross-cutting, never score-eligible regardless). P2 —
does not gate release.

---

## C. Standing constraints the human must keep (not decisions — guardrails)

These are **not** open to trade away while making the above decisions:

- The output stays a **Contractual Financial Review Priority** — never a fraud,
  illegality, validity/voidness, unfairness, or guaranteed-loss verdict (INV-2).
- **B/C never contribute to the score**; only A0–A2 grounding is score-eligible
  (INV-1, PASS-gate 1).
- **No invented numbers**; uncertainty widens bands / lowers confidence, never
  inflates amounts or the score (INV-6, INV-7).
- **Privacy boundary holds**: uploads (incl. PDFs) ephemeral/local-only/deleted/
  never logged; B/C `public_export=false`; official excerpts < 15 words and
  license-gated; no real contract data, private-book full text, or API keys
  anywhere (INV-8).
- **No unvalidated claim** stated as established; weights are heuristics;
  "DFL-inspired," never "trained end-to-end DFL" (INV-9).
- The ICML template at `paper/template/icml2026/` stays byte-unchanged.

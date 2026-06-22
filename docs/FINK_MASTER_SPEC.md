# FInk Master Specification

**Working paper title:** FInk: Selective, Evidence-Gated Cash-Flow Triage for Creator Contracts
**Brand:** FInk (formerly ClauseGuard-Fin — same project)
**Repository:** `fink` · **Package:** `fink_contracts`
**Spec version:** 1.0.0 · **Spec date:** 2026-06-21
**Status:** implementation-grade master specification (no application code in this run)
**Upstream data verdict:** `PREPROCESSING_PASS` (see `.fink/inputs/claude/stage-3/31_PREPROCESSING_QA_REPORT.md`)

---

## 0. How to read this document

This is the authoritative entry point for FInk. It defines the product, the
hard invariants, and the document map. Each topic is specified in depth in a
companion file under `docs/specs/`. When this file and a companion file appear
to disagree, **this file's invariants win** and the discrepancy must be logged
in `docs/specs/11_ASSUMPTIONS_OPEN_QUESTIONS.md`.

| # | File | Scope |
|---|------|-------|
| — | `docs/FINK_MASTER_SPEC.md` | This file: framing, invariants, document map |
| 01 | `docs/specs/01_PRODUCT_REQUIREMENTS.md` | Product semantics, requirements, non-goals, MVP vs stretch |
| 02 | `docs/specs/02_DATA_AND_SCHEMA_SPEC.md` | Source manifest, authority tiers, 18 typed schemas, bilingual + privacy fields |
| 03 | `docs/specs/03_SCORING_AND_FINANCIAL_IMPACT.md` | Review-priority scoring, 8 financial-impact modules, time exposure |
| 04 | `docs/specs/04_LOCAL_RUNTIME_AND_PRIVACY.md` | Desktop-local full + mobile-local lite profiles, privacy boundary |
| 05 | `docs/specs/05_EVALUATION_AND_DECISION_FOCUSED_METRICS.md` | Metrics, datasets, ablations, decision-focused utility |
| 06 | `docs/specs/06_UI_UX_RESPONSIVE_WEB.md` | Responsive desktop/mobile flows |
| 07 | `docs/specs/07_PAPER_PROJECT_PAGE_AND_DELIVERABLE_SYNC.md` | Paper notes, ledgers, project page, course compliance |
| 08 | `docs/specs/08_IMPLEMENTATION_BACKLOG.yaml` | Phased, gated, traceable task backlog (S0–S8) |
| 09 | `docs/specs/09_ACCEPTANCE_CHECKLIST.md` | Objective acceptance tests (every `AC-*` ID) |
| 10 | `docs/specs/10_TRACEABILITY_MATRIX.csv` | Requirement → spec → task → metric → paper traceability |
| 11 | `docs/specs/11_ASSUMPTIONS_OPEN_QUESTIONS.md` | Assumptions, open questions, human decisions |
| — | `docs/specs/SPEC_BUILD_REPORT.md` | What was built, inputs read, reconciliations, status |
| — | `docs/specs/SPEC_COMPLETION_REPORT.md` | Completion-pass validation results |

> **Completion note (2026-06-21 — closes SPEC_AUDIT_REPORT issues C1–C5/H1).**
> The four files the audit flagged as never written —
> `09_ACCEPTANCE_CHECKLIST.md`, `10_TRACEABILITY_MATRIX.csv`,
> `11_ASSUMPTIONS_OPEN_QUESTIONS.md`, and `SPEC_BUILD_REPORT.md` — were authored
> in the completion pass, together with `SPEC_COMPLETION_REPORT.md`. Every `AC-*`
> (acceptance) and `AQ-*` (assumption) cross-reference in specs 01–08 now resolves
> to a definition in spec 09 or spec 11. The record-level Stage-0/1/2 inputs are
> **present** in this snapshot, and the previously reconstructed counts and
> taxonomy are reconciled against them (see §3, §9, and spec 11 AQ-01/AQ-03).
> Binding owner decisions in `docs/specs/HUMAN_DECISION_RESOLUTIONS.md` apply
> throughout: **PDF upload is a mandatory, local-only/ephemeral MVP input**
> (HD-2); the **governing offering is 2026 Spring IE412 AI for Finance** and the
> **binding deadline is 2026-06-24 23:59 KST** (HD-3).

---

## 1. Problem and purpose

Korean webtoon and creator-economy authors sign contracts whose
**financially consequential** clauses — settlement basis, revenue share,
deductions, minimum guarantee (MG)/advance recoupment, payment timing, IP and
secondary-rights monetization, exclusivity/renewal, termination/penalty,
production-cost burden — are hard to read and easy to under-weight. FInk is a
**local-first, Korean/English Financial-AI system** that ingests photographed
contract pages, images, PDFs, or pasted clauses and returns a prioritized,
evidence-grounded, **uncertainty-aware financial review** so a creator can
decide *which clauses to scrutinize and ask about before signing*.

FInk reconstructs clauses (OCR), selectively highlights cash-flow-relevant words
and clauses, gates score-eligible review signals on **official Korean sources
only**, explains the financially relevant clauses bilingually, and projects
**low/base/high monetary exposure** and **time exposure** with the creator's own
editable assumptions. It never renders a legal verdict.

The runtime **must not require a remote LLM, cloud RAG, or external legal
search** (§5).

---

## 2. Global invariants (hard boundaries — non-negotiable)

These invariants are inherited from the upstream data package and the project
charter. Every companion spec, schema, formula, and task must preserve them.
They are testable; see `docs/specs/09_ACCEPTANCE_CHECKLIST.md`.

### INV-1 — Source authority chain and score eligibility
Authority chain, high → low:
`A0` current Korean law `>` `A1` official standard contracts `>`
`A2` official guidance/casebooks `>` `B` educational law book `>`
`C` creator-practical book `>` `D0` course-method drafts.
**Only A0–A2 may contribute authority-supported scoring evidence.** A risk
signal becomes *score-eligible only when an A0–A2 record grounds that specific
signal*. `B` and `C` may explain, supply terminology, generate
questions, and inform synthetic cases, but **B/C contribute exactly 0 to the
score** and carry a "practice reference" badge. `M1/M2/M3` (the IE412 method
decks: decision-focused learning, LLMs for finance, fraud/risk scoring) are
**method sources, never legal evidence**. `R0` (Term Project requirements) is
authoritative for **course compliance only**.

### INV-2 — Product is a review priority, never a verdict
The output is a **Contractual Financial Review Priority Score** (Korean:
**계약상 금융 검토 우선도**). FInk must **never** present its output as: fraud
probability, illegality probability, contract validity/voidness, a legal
conclusion, an unfairness verdict, or guaranteed loss.

### INV-3 — Four independent dimensions, never collapsed
Every report shows four dimensions that are **never reduced to one number**:
1. **Review Priority Score** (0–100, ordinal/relative)
2. **Monetary Exposure Range** (low / base / high)
3. **Time Exposure** (typed fields + a categorical pathway label)
4. **Evidence & OCR Confidence**

### INV-4 — Korean is canonical; English is alias/explanation
Korean source text is the **primary, canonical evidence**. English labels and
explanations are `generated_translation=true`, retrieval/UX aids only, and
**must never be presented as original evidence** or asserted as legal
equivalence between Korean and common-law concepts. Korean and English queries
must resolve to the **same canonical concept ID**.

### INV-5 — Local-first runtime
No remote LLM, no cloud RAG, no external legal search at runtime. Two profiles
(§5). A **network-offline integration test must pass**.

### INV-6 — No invented numbers
FInk **invents no financial values**. Monetary outputs are either (a) extracted
from the document with provenance, or (b) computed from **user-editable
assumptions** explicitly labeled *synthetic assumption*. Low/base/high is
mandatory wherever a single value would imply false certainty.

### INV-7 — Uncertainty raises uncertainty, not the number
When records, definitions, audit access, or numeric terms are missing or
opaque, FInk **widens uncertainty / lowers confidence** — it does **not**
inflate the monetary amount or the score to compensate.

### INV-8 — Privacy & copyright boundary
User-uploaded contract content is **ephemeral, local-only, deleted after use,
never logged, never in public artifacts**. Private books `B`/`C` are
`public_export=false`; no long private-book passages are reproduced anywhere.
Official `A1/A2` excerpts stay short (< 15 words) and provenance-tagged.
**No real contract data, no private-book full text, no API keys** in the repo,
datasets, or demo.

### INV-9 — No unvalidated claim stated as established
No scoring weight, threshold, or band is stated as scientifically validated.
All weights are **design heuristics** in config, to be sensitivity-analyzed.
Contribution language is **"DFL-inspired"**, never "trained end-to-end DFL."
Every current-law claim is gated on A0 verification (currently **UNVERIFIED**;
all dated 2018–2021 figures are `NOT_VERIFIED_CURRENT`).

---

## 3. Risk taxonomy (label space)

The taxonomy has **9 financial categories `F1–F9`** (score-eligible only with
A0–A2 grounding) and **5 cross-cutting categories `X1–X5`** (never
score-eligible). The canonical taxonomy lives upstream in
`10_MASTER_RISK_TAXONOMY.{md,yaml}` (Stage-1). That record-level file is **now
present** in this input snapshot, so the table below carries the **canonical
IDs** and is reconciled against it; the prior reconstruction differed mainly on
the F1/F9 labels (audit rights are canonically **F1**, not F9; F9 is the
e-contract/privacy/evidence-integrity bucket). The remaining work is the
runtime ID/label binding in task `FINK-S0-02` (see
`docs/specs/11_ASSUMPTIONS_OPEN_QUESTIONS.md`, AQ-01, now reconciled). The
per-category **module** assignment is a FInk design choice and is unchanged.

| Canonical ID | Financial category (KO / EN) | Primary module(s) |
|--------------|------------------------------|--------------------|
| F1 `F1_SETTLEMENT_AND_AUDIT` | 정산 투명성·감사권 / Settlement transparency & audit | FIM-1, FIM-8 |
| F2 `F2_REVENUE_AND_DEDUCTIONS` | 매출 기준·공제 / Revenue base & deductions (share, fees, refunds, open-ended deductions) | FIM-1 |
| F3 `F3_PAYMENT_AND_CASHFLOW` | 지급 시기·현금흐름 / Payment timing & cashflow (due/delay, fixed fee) | FIM-2 |
| F4 `F4_MG_AND_RECOUPMENT` | 미니멈 개런티·선급금 회수 / Minimum guarantee & advance recoupment | FIM-3 |
| F5 `F5_IP_MONETIZATION` | 저작권·2차적저작물 수익화 / IP & secondary-rights monetization | FIM-6 |
| F6 `F6_TERM_EXCLUSIVITY_AND_OPPORTUNITY_COST` | 기간·독점·기회비용 / Term, exclusivity & opportunity cost | FIM-5 |
| F7 `F7_TERMINATION_LIABILITY_AND_PENALTIES` | 해지·손해배상·위약금 / Termination, liability & penalties | FIM-7 |
| F8 `F8_SCOPE_CREEP_AND_PRODUCTION_COST` | 업무범위 확대·제작비 / Scope creep & production cost | FIM-4 |
| F9 `F9_E_CONTRACT_PRIVACY_AND_EVIDENCE` | 전자계약·개인정보·증거보존 / E-contract, privacy & evidentiary integrity | FIM-8 |

| Canonical ID | Cross-cutting category (never score-eligible) |
|--------------|-----------------------------------------------|
| X1 `X1_EVIDENCE_AND_CURRENCY_GOVERNANCE` | Evidence & currency governance |
| X2 `X2_DISPUTE_RESOLUTION_AND_CASH_RECOVERY` | Dispute resolution & cash recovery |
| X3 `X3_RESPONSIBLE_AI_AND_EXPLAINABILITY` | Responsible-AI & explainability |
| X4 `X4_LABOR_STATUS_AND_CREATOR_SAFETY` | Labor status & creator safety |
| X5 `X5_MORAL_AND_NON_CONTRACT_HARMS` | Moral & non-contract harms |

Grounding coverage is uneven (strongest on F5, F7; thinner on F3, F8) and the
official evidence matrix is a **20-record representative sample**, not an
exhaustive extraction. FInk must degrade gracefully where grounding is thin
(§ INV-1, FIM-8).

---

## 4. Financial-impact modules (summary)

Eight modules, fully specified in `docs/specs/03_SCORING_AND_FINANCIAL_IMPACT.md`
with formulas, units, input fields, missing-data behavior, unit tests, and
uncertainty behavior. They are named `FIM-1 … FIM-8` to avoid collision with
method sources `M1–M3`.

| Module | Name | Output | Single-value forbidden? |
|--------|------|--------|--------------------------|
| FIM-1 | Revenue-base & deduction leakage | payout-difference low/base/high | Yes — show range |
| FIM-2 | Payment-delay present-value loss | nominal unpaid **and** PV loss (separate) | PV separate from nominal |
| FIM-3 | MG & advance recoupment | balance, monthly, months-to-recoup, deferral | Yes — low/base/high sales |
| FIM-4 | Unpaid additional-work cost | cost (3 user-editable inputs) | Requires user inputs |
| FIM-5 | Exclusivity & renewal opportunity cost | scenario opportunity cost | Requires user inputs |
| FIM-6 | IP & secondary-rights scenario value | user scenario value | Requires user inputs; never auto-valued from text |
| FIM-7 | Penalty & liability exposure | capped amount, uncapped/ambiguous signal, scenario range | No expected loss without explicit probability |
| FIM-8 | Evidence-opacity uncertainty | uncertainty/confidence adjustment | Raises uncertainty, not amount |

The four exposure types — **nominal/observed leakage**, **present-value loss**,
**opportunity cost**, and **liability exposure** — are kept **strictly
separate** in schema and UI and are never summed into one "loss" figure.

---

## 5. Runtime profiles (summary)

Specified in `docs/specs/04_LOCAL_RUNTIME_AND_PRIVACY.md`.

- **Desktop-local full profile (MVP target):** responsive FastAPI web app;
  phone-camera upload via mobile browser on the **same trusted LAN**; local OCR;
  local corpus/index; local rule engine; **optional** local LLM; no remote
  runtime API; temporary uploads deleted; passes a **network-offline integration
  test**.
- **Mobile-local lite profile (design-compatible future):** sanitized mobile
  knowledge pack; on-device OCR; deterministic rules and/or small ONNX
  classifier; **no private full corpus** in the mobile package.

The first milestone uses desktop-local full inference with a mobile-responsive
frontend, but **all data contracts must remain portable** to the mobile-lite
profile (§ schemas in spec 02 are profile-neutral).

---

## 6. Non-goals (global)

FInk does **not**:
1. Determine fraud, illegality, contract validity/voidness, unfairness, or any
   legal outcome (INV-2).
2. Provide legal advice or a substitute for a lawyer.
3. Assert any statute as current law before A0 verification (HR-01).
4. Auto-value IP or secondary rights from contract text alone (FIM-6).
5. Compute expected loss/penalty without an explicit user probability (FIM-7).
6. Estimate court, negotiation-completion, or dispute-resolution **durations as
   precise numbers** (only categorical pathway labels — §3 of spec 03).
7. Require any network call, cloud service, remote LLM, or external legal search
   at runtime (INV-5).
8. Publish real contracts, private-book full text, long official excerpts, or
   API keys (INV-8).
9. Train an end-to-end differentiable decision-focused-learning model (it does
   **DFL-inspired** decision-aware re-ranking and decision-focused *evaluation*).
10. Set final/optimal scoring weights (all weights are sensitivity-analyzed
    heuristics — INV-9).

---

## 7. MVP vs stretch (global posture)

The governing course offering and deadline are **resolved** by the owner
(HD-3, superseding the HR-07 "2024 Spring" header / "2026spring" filename
ambiguity): the governing offering is **2026 Spring IE412 AI for Finance** and
the binding deadline is **2026-06-24 23:59 KST**. The spec is written so the
**MVP is demonstrable on synthetic contracts within a term-project timebox**.
PDF upload is a **mandatory MVP input** alongside camera/image/paste (HD-2),
processed locally and ephemerally.

- **MVP (must ship):** ingestion (camera/image/PDF/paste) → local OCR →
  clause segmentation → bilingual canonical-ID extraction → authority-gated
  retrieval over the **20-record** evidence sample → **rule-based** review
  signals → four-dimension report with FIM-1, FIM-2, FIM-3, FIM-7 (the modules
  computable from contract terms) plus FIM-8 uncertainty → editable assumptions
  for FIM-4/5/6 → local report export → offline test → core evaluation set
  (OCR exactness, retrieval Recall@k, risk Macro-F1, benign-FPR, latency,
  offline test, formula unit tests).
- **Stretch:** optional local LLM assist; local-model-only and hybrid scoring
  ablations; calibration; decision-focused utility study; mobile-lite ONNX
  pack; A0-verified grounding; 2025 webtoon-handbook grounding; expanded
  evidence extraction.

Per-requirement MVP/stretch tags are in spec 01; per-task scope is in spec 08.

---

## 8. Conventions

- **IDs:** requirements `PR-/DS-/SC-/RT-/EV-/UX-/PA-####`; risk signals
  `RS-<Fx>-<slug>`; financial modules `FIM-1…8`; canonical features
  `UPPER_SNAKE`; tasks `FINK-S<phase>-<NN>`; human-review `HR-##`; data
  requirements `DR-##`; assumptions/open questions `AQ-##`.
- **Units:** money in **KRW integer minor-unit-free won** unless a field says
  otherwise; rates as **decimal fractions** (0.30 = 30 %); durations in the unit
  named by the field suffix (`_days`, `_months`, `_seconds`, `_minutes`).
- **Bilingual fields:** every canonical concept carries
  `canonical_id` (English, stable), `label_ko`, `label_en`, `aliases_ko[]`,
  `aliases_en[]`.
- **Privacy class** (per field, spec 02): `P0_PUBLIC`, `P1_INTERNAL`,
  `P2_PRIVATE_LOCAL`, `P3_USER_EPHEMERAL`.
- **Provenance:** every evidence-bearing field carries `source_id`,
  `authority_tier`, and `verification_status`.

---

## 9. Upstream inputs consumed

Read for this spec (all under `.fink/inputs/`, git-ignored). The completion pass
consumed the **full** package, which is now physically present: Stage-0
(`01_SOURCE_MANIFEST.csv` 35 sources, `02_SOURCE_ROLE_AND_AUTHORITY_MAP.md`,
`03_DUPLICATE_CONFLICT_AND_PRECEDENCE_LOG.csv` 15 rows), Stage-1
(`10_MASTER_RISK_TAXONOMY.{md,yaml}` 9F+5X, `11_MASTER_CREATOR_CHECKLIST` 52
items, `12_MASTER_FINANCIAL_FEATURES.{md,yaml}` 29 canonical + 3 auxiliary,
`13_MASTER_BILINGUAL_GLOSSARY` 156 terms, `14_MASTER_EVIDENCE_MATRIX.csv` 20
A1/A2 records, `15_MASTER_KNOWLEDGE_CARDS.jsonl` 64 cards,
`16_HIERARCHICAL_RAG_CORPUS_SPEC.md`), Stage-2 (`20–24`, incl. 11 metrics and 16
`DR-*` data requirements), Stage-3 (`00`, `30`, `31` verdict `PREPROCESSING_PASS`,
`32`, `33` HR-01…HR-08), and 13 ChatGPT structured inputs. The reconstructed
counts in specs 01–02 **match** the record-level files; the taxonomy and feature
labels are reconciled in spec 11 (AQ-01/AQ-03). Tasks `FINK-S0-01…05` perform the
runtime import/binding. See `docs/specs/SPEC_BUILD_REPORT.md` for the exact
inputs, counts, and reconciliations.

---

## 10. Human approval points (global)

No public current-law claim, no webtoon-specific grounded score, and no public
release may proceed before the relevant items in
`.fink/inputs/claude/stage-3/33_REQUIRED_HUMAN_REVIEW.csv` (HR-01…HR-08) are
cleared. **HR-07** (course term/deadline) is **resolved** by owner decision
HD-3; **HR-01, HR-02, HR-03, HR-04, HR-05, HR-06, HR-08 remain OPEN**. These map
to human gates in spec 08 and are registered with status in spec 11.
The ICML template at `paper/template/icml2026/` **must remain untouched**.

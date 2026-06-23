# SPEC_AUDIT_REPORT — FInk Master Specification

**Auditor role:** independent specification auditor and scoped editor (no application code).
**Upstream data verdict consumed:** `PREPROCESSING_PASS` (`.fink/inputs/claude/stage-3/31`).

> **Current status — Pass 2 (2026-06-21): `SPEC_VERDICT: APPROVE`.** This report
> has two independent passes. **Pass 1** (§1–§6 immediately below) audited the
> master spec + specs 01–08 when the deliverable set was incomplete and the
> record-level inputs were absent; it returned REQUEST_CHANGES. **Pass 2** (the
> final section, "Pass 2 — Independent re-audit") audited the **completed** set —
> master + specs 01–11 + the build/completion/human-decision reports + all
> `.fink/inputs` record-level files — and is authoritative. The verdict on the
> **final line** of this file is the current one.

---

## Pass 1 — original audit (2026-06-21, historical)

**Spec under audit (Pass 1):** `docs/FINK_MASTER_SPEC.md` v1.0.0 + `docs/specs/01–08`.

## 1. Scope and method

Read in full: the five Stage-3 structured inputs
(`00_DATA_PACKAGE_README.md`, `30_DATA_GAPS_CONFLICTS_AND_LIMITATIONS.md`,
`31_PREPROCESSING_QA_REPORT.md`, `32_FINAL_FILE_INDEX.csv`,
`33_REQUIRED_HUMAN_REVIEW.csv`); `docs/FINK_MASTER_SPEC.md`; every present file
under `docs/specs/` (`01`–`08`); the governing prompts
(`prompts/00_claude_build_master_spec.md`, `prompts/01_claude_audit_master_spec.md`);
and the build run record (`.fink/runs/00-master-spec-build.json`). Cross-checked
existence/headers of referenced repo artifacts (`paper/template/icml2026/`,
`.gitignore`, `scripts/public_repo_preflight.sh`, `CITATION.cff`,
`docs/paper/*` notes and the three ledgers). All nine present FIM/aggregation
unit tests were re-derived arithmetically.

**Method note:** the record-level Stage-0/1/2 files were **not physically
present** in this snapshot (only `.fink/inputs/claude/stage-3/` exists), so
record counts and the taxonomy in the spec were reconstructed from the Stage-3
descriptions. This is acknowledged in the spec and is itself an open assumption
(issue M3).

---

## 2. Verdict summary

The **content that exists is strong**: authority gating, B/C-never-scores,
four-dimension separation, exposure-type separation, missing-data behavior,
no-fabricated-duration, KO-EN canonicality, local-first/offline, and the privacy
boundary are all specified rigorously and testably, and **all nine worked unit
tests are arithmetically correct**.

However, the **spec set is materially incomplete and internally inconsistent**.
The spec-build run terminated at its **max-turn limit**
(`.fink/runs/00-master-spec-build.json` → `subtype":"error_max_turns"`,
`errors:["Reached maximum number of turns (24)"]`) after emitting the master
spec and specs `01–08`. Four of the **thirteen** files the build prompt requires
were never written:

- `docs/specs/09_ACCEPTANCE_CHECKLIST.md` — objective acceptance tests (**absent**)
- `docs/specs/10_TRACEABILITY_MATRIX.csv` — requirement→task traceability (**absent**)
- `docs/specs/11_ASSUMPTIONS_OPEN_QUESTIONS.md` — assumptions / open questions (**absent**)
- `docs/specs/SPEC_BUILD_REPORT.md` — build report; never wrote `SPEC_BUILD_STATUS: READY_FOR_AUDIT` (**absent**)

Consequently the ~50 `AC-*` (acceptance) and `AQ-*` (assumption) cross-references
in specs `01–08`, plus the master document map and §9, point at files that do
not exist. Two audit dimensions explicitly required by this engagement —
**#16 testable acceptance criteria** and **#20 requirement-to-task
traceability** — have **no deliverable at all**.

This is a completion gap with a clear path forward (finish the build), not an
unresolvable blocker and not an approvable state. **Verdict: REQUEST_CHANGES.**

---

## 3. Audit-dimension coverage (21 required dimensions)

| # | Dimension | Status | Note |
|---|-----------|--------|------|
| 1 | Source-authority correctness | PASS | INV-1 chain + 02 §2.2 table correct; B/C/M/R/D0 contributions bounded. Minor labeling note L4. |
| 2 | B/C never determining scores | PASS | PASS-gate 1, `RiskSignal` hard gate (`score_eligible ⟺ ≥1 A0–A2 id`), `SC-AGG-T1`. |
| 3 | Financial-AI relevance | PASS | IE412 A1/A2/A3 reframed as review priority; EV-DFU; 8 financial modules. |
| 4 | Score semantics & calibration | PASS | Ordinal 0–100, not probability/verdict; calibration *measured-on-synthetic* only; no generalization. |
| 5 | Monetary-exposure formula correctness | PASS | FIM-1…8 + aggregation unit tests re-derived; all correct (see §6). |
| 6 | Nominal/PV/opportunity/liability separation | PASS | `exposure_type` partition, §8 table, `SC-SEP-T1`, grand-total prohibited; +`deferral` 5th type. |
| 7 | Low/base/high scenario assumptions | PASS | `low≤base≤high` validated everywhere; FIM-3 direction clarified (L1, fixed). |
| 8 | Missing-data behavior | PASS | §6 global rules + per-module; null + `is_user_input_required`; no invented numbers. |
| 9 | Time-exposure semantics | PASS | Typed fields + categorical `pathway_label`; measured runtime vs heuristic minutes separated. |
| 10 | No fabricated court/dispute/negotiation duration | PASS | Non-goal 6, §5 "Forbidden", `no_duration_number_test`. |
| 11 | OCR & evidence confidence | PASS | D4 decomposition; `conf_floor` keeps risk visible (INV-7); `unverified_factor<1`. |
| 12 | Korean-English alignment | PASS | KO canonical; EN `generated_translation`; 8 non-equivalence caveats. HR-03 sign-off = human decision. |
| 13 | Local-only runtime feasibility | PASS | INV-5, offline integration test (RT-OFFLINE), no remote LLM/RAG/legal search. |
| 14 | Desktop / mobile-lite portability | PASS | Profile-neutral schemas; documented sanitization strips P2; profile matrix. |
| 15 | Privacy, copyright, deletion, log redaction | PASS | INV-8; P3 ephemeral + deletion triggers; log-redaction test; `.gitignore` verified. Not weakened. |
| 16 | **Testable acceptance criteria** | **FAIL** | `09_ACCEPTANCE_CHECKLIST.md` absent; all `AC-*` IDs dangle (C2/H1). |
| 17 | Complete implementation backlog | CONCERN | `08` present, detailed, phased S0–S8; but `acceptance_criteria` cite missing `AC-*` and a missing `09` path (H1). |
| 18 | Course-requirement coverage | PASS | `07` maps 6 sections, 7 criteria, AI-use log, citations, deadline. HR-07 term = human decision. |
| 19 | ICML paper-note synchronization | PASS | Ledgers exist with claimed headers; template present and gated untouched; sync rules 1–6. |
| 20 | **Requirement-to-task traceability** | **FAIL** | `10_TRACEABILITY_MATRIX.csv` absent (C3). Partial traceability lives in prose/`08 depends_on` only. |
| 21 | Scope feasibility for term-project MVP | CONCERN | MVP large vs **June 24** deadline (3 days out); gated on HR-07 (2024 vs 2026 term) — human decision (M2). |

---

## 4. Findings table

| issue_id | severity | file | section | finding | fix_applied | remaining_action | verification |
|----------|----------|------|---------|---------|-------------|------------------|--------------|
| C1 | CRITICAL | `docs/specs/` (set) + `FINK_MASTER_SPEC.md` | doc map §0; §9 | Build truncated at max turns; 4 of 13 required files never written (`09`,`10`,`11`,`SPEC_BUILD_REPORT.md`). Master spec asserts they exist. | Added auditor notes to master §0 doc map and §9 marking the four files as not-yet-created with evidence pointer. | Re-run/continue the spec-build to author `09`,`10`,`11`,`SPEC_BUILD_REPORT.md`; emit `SPEC_BUILD_STATUS: READY_FOR_AUDIT`; then re-audit. | `glob docs/specs/*` shows only `01–08`; `.fink/runs/00-master-spec-build.json` → `error_max_turns`. |
| C2 | CRITICAL | `docs/specs/09_ACCEPTANCE_CHECKLIST.md` | (entire file) | No objective acceptance-test deliverable. All `AC-IN/OCR/AUTH/FIN/TIME/CONF/UX/PV/RT/OUT/PA-*` IDs referenced in `01/03/04/06/08` are undefined. | None (authoring a full acceptance suite is a build deliverable, not a scoped audit edit; would compromise auditor independence and risk inventing test semantics). | Author `09` enumerating one objective, machine- or reviewer-checkable test per `PR-/NFR-/RT-/UX-/PA-` ID, matching the `AC-*` tokens already cited. | `grep -R "AC-[A-Z]" docs/specs` returns ~48 hits with no defining file. |
| C3 | CRITICAL | `docs/specs/10_TRACEABILITY_MATRIX.csv` | (entire file) | No requirement→spec→task→metric→paper traceability matrix (dimension 20). Referenced by master §0, `01 §7`, `05 §7`. | None (build deliverable; mechanical but out of scoped-edit lane). | Author `10` as CSV linking every `PR-/NFR-/RT-/UX-/PA-` requirement to spec section, `FINK-S*` task, `EV-*` metric, `AC-*` test, and paper section. | `glob` shows file absent; `05 §7` and `01 §7` cite it. |
| C4 | HIGH | `docs/specs/11_ASSUMPTIONS_OPEN_QUESTIONS.md` | (entire file) | Assumptions/open-questions register absent. `AQ-01` (taxonomy reconciliation), `AQ-02` (PDF reversal), `AQ-03` (feature reconciliation) and the HR decisions have no home; master §0 says discrepancies "must be logged" here. | None (must not invent or pre-resolve unresolved assumptions). Human-decision subset captured in `SPEC_REQUIRED_HUMAN_DECISIONS.md`, which does **not** substitute for `11`. | Author `11` registering AQ-01/02/03, the Stage-0/1/2 absence (M3), and HR-01…08, each with status. | `grep -R "AQ-0" docs/specs` shows uses but no defining file. |
| C5 | HIGH | `docs/specs/SPEC_BUILD_REPORT.md` | (entire file) | Build report absent; `SPEC_BUILD_STATUS: READY_FOR_AUDIT` never emitted, so the spec was technically never handed off for audit. Master §0/§9 reference it. | Annotated master §0/§9 (see C1). | Author `SPEC_BUILD_REPORT.md` (inputs read, files produced, blockers) ending in the required status line. | File absent; build run errored at max turns. |
| H1 | HIGH | `01`,`03`,`04`,`06`,`08` | various | ~48 `AC-*`/`AQ-*` and 12 filename cross-references resolve to the four missing files; `FINK-S8-03.allowed_paths` includes the missing `09`. Spec is not internally consistent as delivered. | None at reference sites (a sweeping rewrite would churn the spec and pre-empt the missing files). Surfaced centrally via C1 note. | When `09/10/11` are authored, confirm every cited `AC-*`/`AQ-*` token has a definition; add a CI link-check. | `grep -Rn "AC-\|AQ-" docs/specs`. |
| M1 | MEDIUM | `01` | PR-004 note (AQ-02) | PDF-upload support **reverses** the upstream "no PDF upload" design direction. Resolution (local-only, ephemeral, `*.pdf` git-ignored) is sound and **does not weaken privacy**, but it is pinned to a nonexistent `AQ-02`/spec 11 and to an unnamed "HR-linked" item; no upstream HR-01…08 covers it. | None (privacy intact; needs human sign-off, not an auditor edit). Logged as **HD-2** in `SPEC_REQUIRED_HUMAN_DECISIONS.md`. | Owner confirms PDF-in-scope decision (build prompt mandates PDFs; README discourages them); record as a real AQ/HR item in spec 11. | `01` PR-004 note; README §1 "no PDF upload"; prompt §PURPOSE lists PDFs. |
| M2 | MEDIUM | `FINK_MASTER_SPEC.md`,`07` | §7; §6 | MVP scope (ingest+OCR+segment+retrieval+rule signals+FIM-1/2/3/7/8+web+core eval) is large vs the stated **June 24, 24:00** deadline (3 days from 2026-06-21). Feasibility is gated on HR-07 (header "2024 Spring" vs filename "2026spring"). | None (scope/term is a human decision; must not be resolved by auditor). Logged as **HD-3**. | Confirm governing term/deadline (HR-07); if timebox is short, cut to a demonstrable subset and record the cut in spec 11. | §7 + HR-07 row in `33_REQUIRED_HUMAN_REVIEW.csv`; `currentDate=2026-06-21`. |
| M3 | MEDIUM | `FINK_MASTER_SPEC.md`,`02` | §3, §9; §3 | Spec built **without** record-level Stage-0/1/2 files present; all counts (156 glossary, 64 cards, 52 checklist, 20 evidence, 29+3 features) and the F/X taxonomy are reconstructed from Stage-3 descriptions and unverified against source files. Honest and deferred to `FINK-S0-01…05`. | None (correctly flagged in spec; resolving requires the actual files). Logged as **HD-11**. | Supply the Stage-0/1/2 record files so `FINK-S0-01…05` can bind real counts/IDs; reconcile AQ-01/AQ-03. | `glob .fink/inputs/**` shows only `claude/stage-3/`; master §9 states the absence. |
| L1 | LOW | `03` | FIM-3 | `months_to_recoup`/`deferral` move **inversely** to sales, so "low/base/high" (labeling the sales input) could be misread as exposure magnitude in the UI. | **Fixed** — added a "Direction note" clarifying the labels track sales and that low-sales → longest recoupment/largest exposure; UI must label columns. | None. | Re-read `03` FIM-3 "Direction note". |
| L2 | LOW | `03` | §6 item 4 | "widens `[low,high]` symmetrically in log-space around an unchanged base" is imprecise: the multiply-by-`f`/`1/f` is symmetric around the geometric mean of `low`/`high`, with `base` held fixed (only equal to that mean when `base=√(low·high)`). | **Fixed** — reworded to "multiplying `high` by the widen factor and `low` by its reciprocal while leaving `base` unchanged." Formula and `FIM-8-T1` unchanged. | None. | Re-read `03` §6 item 4; `FIM-8-T1` still 3,791,667 / 5,250,000 / 7,140,000. |
| L3 | LOW | `03` | §8 table | `nominal_leakage` described as "observed/extracted payout difference," but the spread is driven by the **user-modeled** open-ended-deduction range (could read as observed, against INV-6). | **Fixed** — row now notes extracted gross/refunds/allowed vs user-modeled, synthetic-labeled open-ended portion. | None. | Re-read `03` §8 `nominal_leakage` row. |
| L4 | LOW | `FINK_MASTER_SPEC.md`,`02` | INV-1; §2.2 | Spec labels the IE412 method decks `M1/M2/M3` and reserves `D0` for "generated drafts" (per build prompt §SOURCE AUTHORITY), whereas upstream README §2 calls the IE412 decks "D0 course method." Both keep them non-scoring, so no scoring impact. | None (spec follows the governing prompt; correct). | Add a one-line reconciliation note in spec 11 so the `D0`-vs-`M1/2/3` mapping to upstream is explicit. | README §2/§7 vs prompt §SOURCE AUTHORITY vs `02 §2.2`. |
| L5 | LOW | `02`,`03` | 4.8 gate; §2–3 | `RiskSignal` eligibility gate keys only on "≥1 A0–A2 evidence id"; it does not explicitly require `risk_category ∈ F1..F9`. X-category signals are kept out of the score by aggregation (only F categories sum) — defense-in-depth, but the gate itself is silent. | None (no live defect; X never aggregates). | When wiring `FINK-S2-04`, assert `category ∈ F1..F9` in the eligibility predicate as belt-and-suspenders; note in spec 11. | `03 §2–3`; `EvidenceRecord.risk_category` is F-only by schema. |

Severity legend: **CRITICAL** blocks APPROVE outright; **HIGH** materially impairs implementability/consistency; **MEDIUM** needs a human decision or scope action; **LOW** clarity/precision.

---

## 5. Scoped edits applied (this audit)

All edits are documentation-only, truthful, and preserve every requirement,
assumption, and privacy boundary (nothing removed, nothing made public, no score
re-characterized, no metric invented):

1. `FINK_MASTER_SPEC.md` §0 — auditor note marking `09/10/11/SPEC_BUILD_REPORT.md`
   as never-written (truncated build), with evidence pointer (C1/C5).
2. `FINK_MASTER_SPEC.md` §9 — annotated the `SPEC_BUILD_REPORT.md` reference as
   not-yet-created (C1).
3. `03` §6 item 4 — precision fix to the FIM-8 band-widening description (L2).
4. `03` §8 — clarified `nominal_leakage` provenance vs user-modeled open-ended
   deductions, aligning with INV-6 (L3).
5. `03` FIM-3 — added a low/base/high direction note (sales vs exposure) (L1).

No edits were made to introduce missing files C2/C3/C4/C5: authoring an
acceptance suite, traceability matrix, assumptions register, and build report is
a **build deliverable**, and fabricating their contents would compromise audit
independence and risk inventing test/assumption semantics the original author
did not specify. They are returned as `remaining_action`.

---

## 6. What would move this to APPROVE

1. Author `09_ACCEPTANCE_CHECKLIST.md`, `10_TRACEABILITY_MATRIX.csv`,
   `11_ASSUMPTIONS_OPEN_QUESTIONS.md`, and `SPEC_BUILD_REPORT.md` (close
   C1–C5/H1); ensure every `AC-*`/`AQ-*` token resolves.
2. Record the human decisions in `SPEC_REQUIRED_HUMAN_DECISIONS.md` (esp. HD-2
   PDF reversal, HD-3 term/deadline, HD-11 missing record-level inputs) into
   spec 11 with explicit status.
3. Re-audit the completed set for internal consistency.

The substantive specification (master + 01–08) is, on the evidence reviewed,
**implementation-grade in content**; it is the **completeness and cross-
reference integrity of the deliverable set** that fails. Hence changes are
requested, not blocked.

---

**Pass-1 verdict (historical — superseded by the Pass-2 re-audit below): REQUEST_CHANGES.**

---

# Pass 2 — Independent re-audit (2026-06-21)

**Auditor role:** independent specification auditor and scoped editor (no
application code). **Scope under audit:** the **completed** set — `docs/FINK_MASTER_SPEC.md`
v1.0.0, `docs/specs/01–11`, `SPEC_BUILD_REPORT.md`, `SPEC_COMPLETION_REPORT.md`,
`HUMAN_DECISION_RESOLUTIONS.md`, and `SPEC_REQUIRED_HUMAN_DECISIONS.md` — checked
against **all** `.fink/inputs` record-level files (Stage 0–3 + ChatGPT), which are
now physically present.

## P2.1 Method

Independent of Pass 1. Read every spec file and every present upstream input in
full. Re-derived all nine FIM/aggregation worked unit tests arithmetically
(FIM-1-T1…FIM-8-T1 — **all correct**, incl. FIM-1-T1 leakage 1,400,000;
FIM-2-T1 PV ≈237,720; FIM-3-T1 18/9/5; FIM-5-T1 ≈5,845,000; FIM-8-T1 base
unchanged at 5,250,000 with low 3,791,667 / high 7,140,000). Verified counts by
reading the source files directly (`01_SOURCE_MANIFEST` 35; `13_…GLOSSARY` 156,
every row `generated_translation=true` + `score_eligible=false`; `15_…CARDS` 64;
`11_…CHECKLIST` 52; `14_…EVIDENCE_MATRIX` 20, all A1/A2 + `UNVERIFIED`;
`12_…FEATURES` 29+3; `10_…TAXONOMY` 9F+5X with canonical IDs; `24_…` DR-1…DR-16;
`22_…` 11 metrics). Resolved every `AC-*`, `AQ-*`, `FINK-S*`, `EV-*`, `DR-*`,
`HR-*`, `G-*`, and `PASS-gate` token to a definition. Checked the live `.gitignore`
and the deadline string across the repo.

## P2.2 Required-verification results (the 20 engagement checks)

| # | Check | Result | Evidence |
|---|-------|--------|----------|
| 1 | All required spec files exist | PASS | master + `01–11` + `SPEC_BUILD_REPORT` + `SPEC_COMPLETION_REPORT` + human-decision files present; the four Pass-1-missing files (`09/10/11/SPEC_BUILD_REPORT`) now exist (closes C1–C5/H1). |
| 2 | Every AC/AQ/task/metric reference resolves | PASS (2 fixed) | All `AC-*`→spec 09; `AQ-01/02/03`→spec 11; `FINK-S*`→spec 08; `DR-1…16`→`24`; `G-12/14/15`→upstream `30`; PASS-gates→upstream `31`. Two non-resolving metric shorthands in spec 01 (`EV-OCR`,`EV-EXACT`) fixed to registry families (R2). |
| 3 | Traceability covers every MVP requirement | PASS | `10_TRACEABILITY_MATRIX.csv` rows for every INV/PR/NFR/RT/UX/FIM/SC/PA/REL/EV item → acceptance + task + metric + paper + page; MVP-traced. |
| 4 | Stage 0–3 actual inputs reconciled | PASS (1 fixed) | All counts match source files; AQ-01 taxonomy IDs exact; AQ-03 features 29+3; one schema-vs-data fidelity defect found+fixed (R1). |
| 5 | PDF upload is a mandatory MVP input | PASS | HD-2; master §7; PR-001/PR-005…009; spec 11 AQ-02; traceability `UX-IN-PDF`. |
| 6 | Text-layer / scanned / mixed / multi-page PDFs specified | PASS | PR-005; `AC-PDF-TEXT/OCR/MIXED/MULTIPAGE`; `OCRPage.text_source`; FINK-S1-06. |
| 7 | Local parsing / OCR / page operations specified | PASS | PR-007/008; RT-UP-6; UX-IN-PDF/UX-PAGE-ORG/UX-OCR-PREVIEW; `AC-PDF-RASTER/PAGEOPS/OCRCORRECT/PROVENANCE`. |
| 8 | Encrypted / corrupt / oversized behavior specified | PASS | PR-006; `validation_status` enum; `AC-PDF-MIME/CORRUPT/LIMITS/ENCRYPTED`; spec 04 §7; encrypted rejected by default + optional local password flow. |
| 9 | Uploaded PDF bytes, rasters, OCR intermediates deleted | PASS | PR-009; RT-UP-2; `AC-PDF-DELETE`; FINK-S1-06 (`pdf_ephemeral_delete_test`). |
| 10 | Raw filename and contract text never enter logs | PASS | PR-009; `filename_hash` only; RT-LOG-1/2; `AC-PDF-LOG`, `AC-PV-2`. |
| 11 | PDF analysis works with no outbound network | PASS | PR-009; RT-UP-6/RT-009; `AC-PDF-OFFLINE/RASTER`; RT-OFFLINE integration test. |
| 12 | `*.pdf` Git exclusion ≠ removal of PDF product support | PASS | `.gitignore` `*.pdf` labeled "Never publish source scans"; master §7 / spec 01 PR-004 note / spec 11 AQ-02 / HD-2 explicitly separate the publication rule from product scope; "no PDF upload" appears only in override-context or as the (immutable) upstream taxonomy `design_direction`. |
| 13 | Binding deadline is exactly **2026-06-24 23:59 KST** everywhere | PASS (1 fixed) | All live specs (master, 07, 08, 10, 11, HUMAN_DECISION_RESOLUTIONS) use it; the only stale `June 24, 24:00` was in the historical Pass-1 register, normalized in Pass 2. Upstream inputs (`31`,`33`) keep the original wording as immutable record. |
| 14 | B/C sources never affect score | PASS | INV-1; `RiskSignal` hard gate (`score_eligible ⟺ ≥1 A0–A2 id`); data confirms all 156 glossary + 64 cards `score_eligible=false`; SC-AGG-T1; AC-AUTH-2. Belt-and-suspenders recorded as L5 (reinforced by R1). |
| 15 | Review priority is not a legal/fraud verdict | PASS | INV-2; PR-001 forbidden readings; AC-INV-2; UX-D1 tooltip denials + UX-DISCLAIMER; upstream `31` legal-language gate. |
| 16 | Uncertainty never invents money or inflates the score | PASS | INV-6/7; FIM-8 widens `[low,high]` around an **unchanged** base + lowers confidence; `conf_floor` keeps risk visible without inflating; FIM-8-T1 re-derived; AC-INV-6/7, AC-CONF-1, AC-FIN-FIM8. |
| 17 | Exposure types remain separate | PASS | 5 `exposure_type` partitions; grand total **prohibited** (spec 03 §8); FIM-2 nominal vs PV kept separate; SC-SEP-T1; AC-FIN-SEP; UX-D2 "No grand total." |
| 18 | Korean canonical, English generated alias/explanation | PASS | INV-4; data shows `generated_translation=true` on all 156 terms; 8 non-equivalence caveats; AC-INV-4 / AC-KOEN-1; EN never labeled evidence. |
| 19 | Open legal / currentness / release gates remain open | PASS | HR-01/02/03/04/05/06/08 **OPEN** (HD-4…HD-10); HR-07 RESOLVED (HD-3); spec 11 §3; every evidence record `UNVERIFIED`. |
| 20 | Feasibility for the stated deadline + MVP | PASS (concern) | HD-3 fixes the timebox and the MVP cut; spec gives a clear MVP/stretch split + deferral mechanism; much scaffolding (paper notes, ledgers, gitignore, template) pre-exists. The ~3-day execution risk is **owner-owned** (HD-3), not a specification defect. |

## P2.3 Findings

| id | severity | status | finding | action |
|----|----------|--------|---------|--------|
| R1 | MEDIUM | **fixed** | `EvidenceRecord` (spec 02 §4.7) typed `risk_category` as singular `enum{F1..F9}`, but the upstream `14_MASTER_EVIDENCE_MATRIX.csv` it mirrors uses a plural `risk_categories` **list** carrying cross-cutting **X** tags on 3 of 20 A1/A2 records (`EV-A1-ASSIGNFULL-05`→X2, `EV-A2-2024-COMICS`→F3;X2, `EV-A2-2024-STATS`→X1). The schema could not represent those records. No invariant was violated (scoring aggregates F1–F9 only), but Pass-1's "EvidenceRecord is F-only by schema" defense was not true in data. | Corrected spec 02 §4.7 to `risk_categories: list[enum{F1..F9,X1..X5}]` with a note that X tags are contextual/non-scoring (only F-grounding aggregates, INV-1); recorded in spec 11 (L5 + §5). |
| R2 | LOW | **fixed** | Spec 01 metric hooks `EV-OCR` (PR-010) and `EV-EXACT` (PR-013) did not resolve to a `05` registry row (only suffixed members exist); PR-012/013 also omitted their `AC-*` hooks present in the traceability matrix. | Spec 01 now cites `EV-OCR-CER/WER`, `EV-EXACT-MONEY/PCT/DATE/DUR`, and adds `AC-SEG-1` (PR-012) and `AC-EXTRACT-1` (PR-013). |
| R3 | LOW | observation | Master §10 says the open HR items "map to human gates in spec 08," but the two **P2** items (HR-04 missing-source, HR-06 glossary spot-check) attach to no build-task gate. This is consistent with `AC-REL-HR` gating only **P0/P1** and spec 11 tracking all items; no correctness impact. | No edit — left for the build phase; the release gate (`AC-REL-HR`) and spec 11 already scope this correctly. |
| C1–C5/H1 | (Pass 1) | **closed** | The four missing deliverables + dangling `AC-*`/`AQ-*` references. | `09/10/11/SPEC_BUILD_REPORT/SPEC_COMPLETION_REPORT` authored; all tokens now resolve. |
| M1 / M2 / M3 | (Pass 1) | **resolved** | PDF reversal / term+deadline / record-level inputs. | Owner HD-2 / HD-3 / HD-11; reconciled in spec 11 and verified here. |
| L1–L4 | (Pass 1) | **closed/recorded** | FIM-3 direction, FIM-8 band wording, `nominal_leakage` provenance (fixed in spec 03); D0-vs-M1/2/3 labeling (recorded in spec 11, confirmed against `02_SOURCE_ROLE_AND_AUTHORITY_MAP.md`). | — |

## P2.4 Scoped edits applied (Pass 2)

Documentation-only, truthful, invariant-preserving (nothing removed, nothing made
public, no score re-characterized, no metric invented):

1. `02 §4.7` — `EvidenceRecord.risk_categories` corrected to a list admitting X
   context tags, with a non-scoring note (R1).
2. `01` PR-010/012/013 — metric/acceptance hooks made to resolve precisely (R2).
3. `11` — supersession note, L5, and §5 updated to record R1 and the Pass-2 status.
4. `SPEC_REQUIRED_HUMAN_DECISIONS.md` — status synced (HD-1/2/3/11 RESOLVED;
   deadline normalized to `2026-06-24 23:59 KST`; AQ-02 no longer "nonexistent").
5. `SPEC_AUDIT_REPORT.md` — this Pass-2 section + the current-status header.
6. New `SPEC_REAUDIT_CHANGELOG.md` records all of the above.

## P2.5 Verdict rationale

The completed set is internally consistent and implementation-grade: all required
files exist; every cross-reference resolves; traceability is complete for MVP;
the record-level inputs are present and reconcile to the spec's counts and
taxonomy; all nine worked unit tests are arithmetically correct; and every hard
invariant (B/C-never-scores, review-priority-not-verdict, no-invented-numbers,
uncertainty-widens-not-inflates, exposure-type-separation, KO-canonical,
local-first/offline, privacy/copyright, no-unvalidated-claims) is specified
testably and is preserved in the actual data. The two defects found in this pass
(R1 medium, R2 low) were **objective and are fixed here**; R3 is a non-blocking
observation already handled by the release gate. The remaining open items are the
by-design human gates (HR-01…HR-08 minus the resolved HR-07) and the owner-owned
~3-day execution risk — neither is a specification defect.

Approval of the **specification** does not authorize publishing any current-law
claim or webtoon-specific grounded score: those stay blocked behind HR-01/HR-02
and the other open gates.

---

SPEC_VERDICT: APPROVE

# 11 — Assumptions and Open Questions

**Parent:** `docs/FINK_MASTER_SPEC.md` · **Spec version:** 1.0.0
This is the authoritative register of technical assumptions (`AQ-*`), owner
decisions (`HD-*`), and upstream human-review items (`HR-*`). It applies the
binding owner decisions in `docs/specs/HUMAN_DECISION_RESOLUTIONS.md` and the
follow-ups from `docs/specs/SPEC_AUDIT_REPORT.md`.

> **Supersession.** For *live status* this file supersedes
> `docs/specs/SPEC_REQUIRED_HUMAN_DECISIONS.md` (the auditor's original
> human-decision register, which predates the owner resolutions). Where the two
> differ, this file and `HUMAN_DECISION_RESOLUTIONS.md` win. The independent
> re-audit (Pass 2; see `docs/specs/SPEC_REAUDIT_CHANGELOG.md`) updated
> `SPEC_AUDIT_REPORT.md` (appended a Pass-2 section + verdict) and
> `SPEC_REQUIRED_HUMAN_DECISIONS.md` (status sync: HD-1/2/3/11 marked RESOLVED,
> deadline normalized to `2026-06-24 23:59 KST`); their pre-Pass-2 content is
> preserved as historical record.

Status legend: **RESOLVED** (decided/evidenced; no further gate), **OPEN**
(awaits a person), **APPROVED/REQUIRED** (owner mandate).

---

## 1. Technical assumptions (`AQ-*`)

### AQ-01 — Risk-taxonomy reconciliation · RESOLVED (spec-level)
**Question (from audit C4/M3):** do the master-spec §3 F1–F9 / X1–X5 labels match
the upstream canonical taxonomy?
**Evidence:** `.fink/inputs/claude/stage-1/10_MASTER_RISK_TAXONOMY.{md,yaml}` is
now present. The canonical IDs are
`F1_SETTLEMENT_AND_AUDIT`, `F2_REVENUE_AND_DEDUCTIONS`, `F3_PAYMENT_AND_CASHFLOW`,
`F4_MG_AND_RECOUPMENT`, `F5_IP_MONETIZATION`,
`F6_TERM_EXCLUSIVITY_AND_OPPORTUNITY_COST`,
`F7_TERMINATION_LIABILITY_AND_PENALTIES`, `F8_SCOPE_CREEP_AND_PRODUCTION_COST`,
`F9_E_CONTRACT_PRIVACY_AND_EVIDENCE`; and `X1_EVIDENCE_AND_CURRENCY_GOVERNANCE`,
`X2_DISPUTE_RESOLUTION_AND_CASH_RECOVERY`, `X3_RESPONSIBLE_AI_AND_EXPLAINABILITY`,
`X4_LABOR_STATUS_AND_CREATOR_SAFETY`, `X5_MORAL_AND_NON_CONTRACT_HARMS`.
**Discrepancies found and fixed:** the original reconstruction folded **audit
rights** into F9 and labeled F1 "settlement & revenue-base"; canonically **audit
access is F1** (`F1_SETTLEMENT_AND_AUDIT`) and **F9 is e-contract / privacy /
evidence integrity**. Master spec §3 is updated to the canonical IDs/labels; the
per-category FInk **module** mapping (e.g., F1→FIM-1/FIM-8) is a design choice and
is unchanged.
**Resolution:** taxonomy IDs/labels reconciled at the spec level. Counts confirmed:
**9 financial + 5 cross-cutting**. Remaining work is the runtime ID binding in
`FINK-S0-02` (no design gap). X1–X5 stay never-score-eligible; F1–F9 score-eligible
only with A0–A2 grounding.

### AQ-02 — PDF upload scope · RESOLVED (owner HD-2)
**Question (from audit M1):** the upstream README/taxonomy record a "no PDF
upload" design direction; the build prompt mandates PDF support.
**Owner resolution (HD-2, APPROVED_AND_REQUIRED):** end-user **PDF upload is a
mandatory MVP input**, alongside camera/image/paste. It must accept text-layer,
scanned/image-only, mixed, and multi-page PDFs, processed **locally and
ephemerally** (parse, rasterize, OCR fallback, page preview/reorder/rotate/delete,
OCR correction), with clear rejection of encrypted (MVP default)/corrupted/
oversized/unsupported files, deletion of source PDF + rasters + OCR intermediates,
no raw filename or contract text in logs, and **no remote API/cloud OCR/cloud
RAG/telemetry/remote LLM**.
**Repository boundary:** `*.pdf` stays git-ignored as a **publication/privacy
rule** (uploaded user PDFs and reference PDFs must not be published); this is **not**
a product-scope exclusion. The "do not put PDFs in `.fink/inputs`" rule applies
only to the research/reference corpus, not to the application's upload capability.
**Where specified:** PR-005…PR-009 (spec 01), `UploadedDocument`/`OCRPage` PDF
fields (spec 02 §4.2–4.3), RT-UP-1/2/6 + RT-009 (spec 04), UX-IN-PDF (spec 06),
FINK-S1-06 (spec 08), and `AC-PDF-*` (spec 09).

### AQ-03 — Financial-feature reconciliation · RESOLVED (spec-level)
**Question (from audit M3):** do spec-03 FIM working IDs map to the upstream
canonical features?
**Evidence:** `12_MASTER_FINANCIAL_FEATURES.yaml` is present and declares **29
canonical + 3 auxiliary** features. Most FIM inputs map directly
(`GROSS_SALES→gross_sales`, `REFUNDS→refunds`, `REVENUE_SHARE_RATE→
revenue_share_rate`, `FIXED_FEE→fixed_fee`, `ADVANCE_RECOUPMENT→advance_recoupment`,
`MINIMUM_GUARANTEE→minimum_guarantee`, `PENALTY→penalty_amount`,
`LIABILITY_CAP→liability_cap`, durations/notice/exclusivity, etc.).
**Clarification:** several spec-03 working IDs are **scenario/derived inputs, not
extracted contract features**, and correctly live in `FinancialScenarioInputs` or
are computed: `ANNUAL_DISCOUNT_RATE`, `OPEN_ENDED_DEDUCTIONS[]`,
`EXPLICITLY_ALLOWED_DEDUCTIONS` (≈ `deduction_items`, closed list),
`CUMULATIVE_RECOUPED`, `MONTHLY_NET_SALES` (≈ `net_sales`, low/base/high),
`DELAYED_AMOUNT`, `RECOUPMENT_RATE` (≈ `revenue_share_rate` in recoupment context),
`NET_SALES` (derived). The 3 auxiliary fields (`tax_withholding`,
`total_work_hours`, `setoff_scope`) are `score_input=false`.
**Resolution:** mapping reconciled at the spec level; runtime binding (every FIM
input resolves to a canonical/aux `feature_id`) is `FINK-S0-03`.

---

## 2. Owner decisions (`HD-*` — binding)

| ID | Decision | Status |
|----|----------|--------|
| HD-1 | Author the missing deliverables `09`, `10`, `11`, `SPEC_BUILD_REPORT.md` (+ `SPEC_COMPLETION_REPORT.md`). | **RESOLVED** — all created in this completion pass. |
| HD-2 | PDF upload is a mandatory, local-only/ephemeral MVP input (see AQ-02). | **APPROVED_AND_REQUIRED.** |
| HD-3 | Governing offering **2026 Spring IE412 AI for Finance**; binding deadline **2026-06-24 23:59 KST**; MVP cut per `HUMAN_DECISION_RESOLUTIONS.md`. Supersedes the HR-07 "2024 Spring"/"2026spring" ambiguity. | **RESOLVED.** |
| HD-11 | Reconcile actual Stage-0…3 + ChatGPT files rather than reconstructed counts. | **RESOLVED** — see §5; inputs present, counts reconciled. |

The required-submission MVP (HD-3) is: responsive web UI; camera/image/**PDF**/paste
input; local PDF parsing + OCR; page preview/rotate/reorder + OCR correction; clause
segmentation; local authority-aware retrieval; deterministic rule-based review-priority
scoring; four independent report dimensions; FIM-1/2/3/7/8; editable low/base/high
assumptions; synthetic/sanitized evaluation; public GitHub repo; static project page;
paper/report notes prepared for the ICML 2026 template (template byte-unchanged).

---

## 3. Open human-review items (`HR-*` / `HD-4…HD-10`) — **kept OPEN**

These remain **OPEN** by design; no evidence yet exists to close them. They gate
the build/paper/release phase and are routed to human gates in spec 08.

| ID | HR | Item | Priority | Blocks | Status |
|----|----|------|----------|--------|--------|
| HD-4 | HR-01 | A0 current-law verification (10 `law.go.kr` statutes: article/effective_date/retrieved_at). Until closed, all evidence stays `UNVERIFIED` and dated 2018–2021 figures `NOT_VERIFIED_CURRENT`. | P0 | any "current law" statement; webtoon grounded score | **OPEN** |
| HD-5 | HR-02 | 2025 webtoon standard-contract handbook + 2023 fair-guide extraction (split A1 form vs A2 commentary). | P0 | webtoon-specific grounded scoring | **OPEN** |
| HD-6 | HR-03 | KO–EN non-equivalence sign-off for the 8 sensitive terms (assignment/license, 해제/해지, work-made-for-hire, publicity, liquidated damages, consideration, deposit) — retrieval aliases only, not legal equivalence. | P1 | any cross-lingual legal claim | **OPEN** |
| HD-7 | HR-05 | Verify dated 2018–2021 figures/periods/procedures against A0 before any are used as current. | P1 | using any dated figure as current | **OPEN** |
| HD-8 | HR-06 | Spot-check keyword-heuristic glossary `risk_category` tags (esp. dual-category/edge terms). | P2 | retrieval-routing accuracy | **OPEN** |
| HD-9 | HR-08 | AI-use log + human-verification attestation in `docs/ai-use-log.md` (incl. this completion pass). | P1 | R0 AI-disclosure compliance; release | **OPEN** |
| HD-10 | HR-04 | Re-acquire the empty (210-byte) artist-welfare rights-infringement casebook; intended X4/X5 signals absent until then (cross-cutting, never score-eligible regardless). | P2 | artist-welfare/rights signals | **OPEN** |

> HR-07 (course term/deadline) is **RESOLVED** by HD-3 and is therefore not in
> this open list.

---

## 4. Audit follow-ups carried into the spec (`L-*`)

| ID | Note | Status |
|----|------|--------|
| L4 | Authority-tier label mapping: the upstream README §2 calls the IE412 method decks **"D0 course method,"** while this spec labels them `M1/M2/M3` (method sources) and reserves `D0` for **generated drafts** (per the build prompt's source-authority section). **Both keep the IE412 decks non-scoring**, so there is no scoring impact; this is a labeling convention difference only. `FINK-S0-01` records the `D0`↔`M1/M2/M3` crosswalk. | RECORDED |
| L5 | The `RiskSignal` eligibility gate keys on "≥1 A0–A2 evidence id" and is silent on `risk_category ∈ F1..F9`; X-category signals are kept out of the score by aggregation (only F categories sum). When wiring `FINK-S2-04`, also assert `category ∈ F1..F9` in the eligibility predicate (belt-and-suspenders). **Pass-2 note:** this matters in the data — `14_MASTER_EVIDENCE_MATRIX.csv` carries X1/X2 tags on 3 of 20 A1/A2 records, so the F1–F9-only aggregation (spec 03 §3) is what keeps X non-scoring; spec 02 §4.7 was corrected to `risk_categories: list[enum{F1..F9,X1..X5}]` to admit those context tags (R1). No live scoring defect. | RECORDED |
| L1–L3 | FIM-3 direction note, FIM-8 band-widening precision, and `nominal_leakage` provenance — already fixed in spec 03 by the audit. | CLOSED |

---

## 5. Record-level input reconciliation (closes audit M3 / HD-11)

The audit was performed when only `.fink/inputs/claude/stage-3/` was present, so
the spec counts and taxonomy were reconstructed from Stage-3 descriptions. In this
completion pass the **full** record-level package is present and the reconstructed
figures were checked against it (see `SPEC_BUILD_REPORT.md` for the per-file table):

| Quantity | Spec value | Source-file value | Match |
|----------|-----------|-------------------|:-----:|
| Sources | 35 | `01_SOURCE_MANIFEST.csv` = 35 | ✅ |
| Glossary terms | 156 | `13_MASTER_BILINGUAL_GLOSSARY.csv` = 156 | ✅ |
| Knowledge cards | 64 | `15_MASTER_KNOWLEDGE_CARDS.jsonl` = 64 (84 source → 64) | ✅ |
| Checklist items | 52 | `11_MASTER_CREATOR_CHECKLIST.jsonl` = 52 (38 F + 14 X) | ✅ |
| Evidence records | 20 (A1/A2) | `14_MASTER_EVIDENCE_MATRIX.csv` = 20 | ✅ |
| Financial features | 29 + 3 | `12_MASTER_FINANCIAL_FEATURES.yaml` = 29 canonical + 3 aux | ✅ |
| Taxonomy | 9F + 5X | `10_MASTER_RISK_TAXONOMY.{md,yaml}` = 9F + 5X | ✅ |
| Data requirements | DR-6/7/8/11/12/13 used | `24_…` = 16 DR (DR-1…DR-16) | ✅ (subset) |
| Metrics | 11 + supporting | `22_…` = 11 required | ✅ |

All reconstructed counts **matched**; no count was fabricated. `FINK-S0-01`
performs the same check at runtime against `32_FINAL_FILE_INDEX.csv`.

> **Pass-2 data-fidelity note (R1).** The independent re-audit read the record-level
> files directly and confirmed every count above against the source files
> (taxonomy IDs, `12_…` 29+3 features, `24_…` DR-1…DR-16, `22_…` 11 metrics). One
> schema-vs-data discrepancy was found and fixed: the evidence matrix column is
> `risk_categories` (a list) and includes cross-cutting **X** tags on 3 of 20
> A1/A2 records, whereas spec 02 §4.7 had typed it `risk_category: enum{F1..F9}`
> (singular, F-only). Spec 02 §4.7 was corrected to
> `risk_categories: list[enum{F1..F9,X1..X5}]`; scoring still aggregates F1–F9
> only (INV-1), so no invariant changed. See `SPEC_REAUDIT_CHANGELOG.md`.

---

## 6. Non-negotiable guardrails (not open to trade away)

- Output stays a **Contractual Financial Review Priority** — never a fraud,
  illegality, validity/voidness, unfairness, or guaranteed-loss verdict (INV-2).
- **B/C contribute exactly 0** to authority-supported scoring; only A0–A2
  grounding is score-eligible (INV-1).
- **No invented numbers**; missing inputs widen bands / lower confidence or
  request user input — never invent money (INV-6, INV-7).
- **Monetary exposure types stay separate**; no misleading grand total (INV-3,
  spec 03 §8).
- **Runtime requires no remote API**, cloud RAG, remote LLM, cloud OCR, or
  telemetry (INV-5).
- **Privacy boundary holds**: uploads (incl. PDFs) ephemeral/local-only/deleted/
  never logged; B/C `public_export=false`; official excerpts < 15 words; no real
  contract data, private-book full text, or API keys published (INV-8).
- **No unvalidated claim** stated as established; weights are heuristics;
  "DFL-inspired," never "trained end-to-end DFL" (INV-9).
- The ICML 2026 template at `paper/template/icml2026/` stays **byte-unchanged**.

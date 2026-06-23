# 02 — Data and Schema Specification

**Parent:** `docs/FINK_MASTER_SPEC.md` · **Spec version:** 1.0.0
Inherits INV-1…INV-9. Defines the source manifest model, authority/eligibility
fields, provenance/versioning, the private/public boundary, and **18 typed
schemas**. All schemas are **profile-neutral** (portable to mobile-lite, INV-PORT).

---

## 1. Conventions for schema tables

Each schema is a table with columns:
`field` · `type` · `null?` · `units` · `validation` · `provenance` ·
`bilingual` · `privacy`.

- **type:** JSON/Python-ish (`str`, `int`, `float`, `bool`, `enum{…}`,
  `list[T]`, `obj`, `datetime` ISO-8601, `decimal` for money).
- **null?:** `N` = required/non-null; `Y` = nullable/optional; `Y*` = nullable
  but, when null, triggers a defined missing-data behavior (spec 03 §6).
- **units:** `KRW` (integer won), `frac` (decimal fraction, 0–1), `days`,
  `months`, `seconds`, `minutes`, `px`, `—`.
- **provenance:** where the value comes from (`user`, `ocr`, `extractor`,
  `corpus:<file>`, `derived`, `config`).
- **bilingual:** `canonical` (stable EN id), `ko-primary`, `en-alias`,
  `n/a`.
- **privacy:** `P0_PUBLIC`, `P1_INTERNAL`, `P2_PRIVATE_LOCAL`,
  `P3_USER_EPHEMERAL`.

**Money rule:** `decimal` won, non-negative unless a field explicitly allows
negatives (e.g., net of recoupment). **Rate rule:** `frac` in [0,1] unless noted.
**Range rule:** every monetary estimate carries `low ≤ base ≤ high` (validated).

---

## 2. Source manifest and authority model (data layer)

### 2.1 SourceManifestEntry (mirrors upstream `01_SOURCE_MANIFEST.csv`, 35 sources)

| field | type | null? | units | validation | provenance | bilingual | privacy |
|-------|------|-------|-------|------------|------------|-----------|---------|
| `source_id` | str | N | — | unique, stable | corpus:01 | canonical | P1_INTERNAL |
| `title_ko` | str | Y | — | — | corpus:01 | ko-primary | P2_PRIVATE_LOCAL if B/C |
| `title_en` | str | Y | — | — | corpus:01 | en-alias | P2_PRIVATE_LOCAL if B/C |
| `authority_tier` | enum{A0,A1,A2,B,C,M1,M2,M3,R0,D0} | N | — | in set | corpus:01 | n/a | P1_INTERNAL |
| `score_eligible` | bool | N | — | `true` ⟺ tier∈{A0,A1,A2} | derived | n/a | P1_INTERNAL |
| `public_export` | bool | N | — | `false` for B,C and for unknown-license A1/A2 | corpus:01 | n/a | P1_INTERNAL |
| `license_status` | enum{KNOWN_OPEN,UNKNOWN,RESTRICTED} | N | — | default UNKNOWN for A1/A2 | corpus:01 | n/a | P1_INTERNAL |
| `verification_status` | enum{VERIFIED,UNVERIFIED,NOT_VERIFIED_CURRENT} | N | — | A0 path ⇒ UNVERIFIED until HR-01 | corpus:01 | n/a | P1_INTERNAL |
| `retrieved_at` | datetime | Y* | — | required to assert "current" | user | n/a | P1_INTERNAL |
| `effective_date` | datetime | Y* | — | required to assert "current law" | user | n/a | P1_INTERNAL |
| `notes` | str | Y | — | — | corpus:01 | n/a | P2_PRIVATE_LOCAL if B/C |

**Invariant checks (CI):** (a) `score_eligible` true only for A0–A2;
(b) every B/C row `public_export=false`; (c) no A0 row may be
`verification_status=VERIFIED` until HR-01 closed.

### 2.2 Authority tiers and their permitted contributions

| tier | role | score? | explain? | questions? | synthetic cases? | public export |
|------|------|:------:|:--------:|:----------:|:----------------:|:-------------:|
| A0 current law | top authority | ✅ | ✅ | ✅ | ✅ | short excerpt, license-gated |
| A1 standard contracts | official forms | ✅ | ✅ | ✅ | ✅ | short excerpt, license-gated |
| A2 guidance/casebooks | official | ✅ | ✅ | ✅ | ✅ | short excerpt, license-gated |
| B educational book | secondary | ❌ | ✅ | ✅ | ✅ | ❌ |
| C creator-practical | secondary | ❌ | ✅ | ✅ | ✅ | ❌ |
| M1/M2/M3 method | method only | ❌ | method | ❌ | ❌ | method notes only |
| R0 course reqs | compliance | ❌ | ❌ | ❌ | ❌ | course docs only |
| D0 drafts | generated | ❌ | draft | ❌ | ❌ | ❌ as evidence |

---

## 3. Corpus record schemas

### 3.1 GlossaryTerm (mirrors `13_MASTER_BILINGUAL_GLOSSARY.csv`, 156 terms)

| field | type | null? | units | validation | provenance | bilingual | privacy |
|-------|------|-------|-------|------------|------------|-----------|---------|
| `canonical_id` | str | N | — | UPPER_SNAKE, unique | corpus:13 | canonical | P1_INTERNAL |
| `label_ko` | str | N | — | non-blank | corpus:13 | ko-primary | P1_INTERNAL |
| `label_en` | str | N | — | `generated_translation=true` | corpus:13 | en-alias | P1_INTERNAL |
| `aliases_ko` | list[str] | Y | — | dedup | corpus:13 | ko-primary | P1_INTERNAL |
| `aliases_en` | list[str] | Y | — | dedup; generated | corpus:13 | en-alias | P1_INTERNAL |
| `risk_category` | enum{F1..F9,X1..X5} | N | — | in set | corpus:13 (heuristic; HR-06) | n/a | P1_INTERNAL |
| `financial_variable` | str | Y | — | ∈ 29 canonical ∪ 3 aux or null | corpus:12 | canonical | P1_INTERNAL |
| `merged_src_canonical_ids` | list[str] | Y | — | records normalization | corpus:13 | n/a | P1_INTERNAL |
| `score_eligible` | bool | N | — | **always false** | corpus:13 | n/a | P1_INTERNAL |
| `non_equivalence_caveat` | str | Y | — | required for the 8 sensitive terms | corpus:13 | n/a | P1_INTERNAL |
| `source_ids` | list[str] | N | — | non-empty | corpus:13 | n/a | P1_INTERNAL |

The 8 non-equivalence-sensitive terms (assignment/license, 해제/해지,
work-made-for-hire, publicity, liquidated damages, consideration, deposit)
**must** carry `non_equivalence_caveat` (HR-03).

### 3.2 FinancialFeature (mirrors `12_MASTER_FINANCIAL_FEATURES.{md,yaml}`, 29 canonical + 3 aux)

| field | type | null? | units | validation | provenance | bilingual | privacy |
|-------|------|-------|-------|------------|------------|-----------|---------|
| `feature_id` | str | N | — | UPPER_SNAKE, unique | corpus:12 | canonical | P1_INTERNAL |
| `is_canonical` | bool | N | — | 29 true / 3 false | corpus:12 | n/a | P1_INTERNAL |
| `dtype` | enum{money,rate,days,months,count,bool,text} | N | — | in set | corpus:12 | n/a | P1_INTERNAL |
| `unit` | enum{KRW,frac,days,months,—} | N | — | matches dtype | corpus:12 | n/a | P1_INTERNAL |
| `label_ko`/`label_en` | str | N/N | — | bilingual | corpus:12 | ko/en | P1_INTERNAL |
| `module_refs` | list[enum{FIM-1..8}] | Y | — | — | derived | n/a | P1_INTERNAL |
| `score_input` | bool | N | — | aux fields **false** | corpus:12 | n/a | P1_INTERNAL |

> The 29 canonical IDs are owned by upstream `12`; this spec **references** them
> and binds module inputs to them in task `FINK-S0-03`. Known IDs surfaced by
> the Stage-3 audit include `PAYMENT_PROCESSING_FEE`, `PAYMENT_DUE_DATE`,
> `PAYMENT_DELAY`, `SETTLEMENT_STATEMENT`, `REFUNDS`. The module input lists in
> spec 03 use working IDs (`GROSS_SALES`, `NET_SALES`,
> `EXPLICITLY_ALLOWED_DEDUCTIONS`, `FIXED_FEE`, `REVENUE_SHARE_RATE`,
> `ADVANCE_RECOUPMENT`, `MINIMUM_GUARANTEE`, `DELAYED_AMOUNT`,
> `ANNUAL_DISCOUNT_RATE`, …) that **must be reconciled** to the canonical set
> (AQ-03).

### 3.3 ChecklistItem (mirrors `11_MASTER_CREATOR_CHECKLIST.jsonl`, 52 items)
Key fields: `check_id` (unique), `risk_category` (F/X), `prompt_ko`,
`prompt_en` (en-alias), `authority_tier`∈{B,C,B/C}, `score_eligible=false`
(always), `evidence_ids` (optional pointers to where a signal *could* be
grounded), `source_ids`. Privacy `P2_PRIVATE_LOCAL` for any B/C-derived text.
Used for questions-before-signing (PR-031), never for scoring.

### 3.4 KnowledgeCard (mirrors `15_MASTER_KNOWLEDGE_CARDS.jsonl`, 64 cards)
Key fields: `card_id`, `title_ko`/`title_en`, `explanation_ko`/`explanation_en`,
`risk_category`, `authority_tier`∈{B,C,B/C}, `financial_variable` (optional),
`aliases_ko`/`aliases_en`, `evidence_ids` (optional), `source_card_ids`,
`source_ids`, **`score_eligible=false`**, **`public_export=false`**. Privacy
`P2_PRIVATE_LOCAL`. Explanation/terminology/scenario only.

---

## 4. The 18 runtime/eval schemas

### 4.1 `AnalysisRequest`
| field | type | null? | units | validation | provenance | bilingual | privacy |
|-------|------|-------|-------|------------|------------|-----------|---------|
| `request_id` | str(uuid) | N | — | unique | derived | n/a | P3_USER_EPHEMERAL |
| `created_at` | datetime | N | — | — | derived | n/a | P3_USER_EPHEMERAL |
| `ui_locale` | enum{ko,en} | N | — | default ko | user | n/a | P1_INTERNAL |
| `input_mode` | enum{camera,image,pdf,paste} | N | — | in set | user | n/a | P3_USER_EPHEMERAL |
| `runtime_profile` | enum{desktop_full,mobile_lite} | N | — | in set | config | n/a | P1_INTERNAL |
| `documents` | list[`UploadedDocument`] | N | — | ≥1 unless paste | user | n/a | P3_USER_EPHEMERAL |
| `pasted_text` | str | Y* | — | present iff mode=paste | user | ko-primary | P3_USER_EPHEMERAL |
| `scenario_inputs` | `FinancialScenarioInputs` | Y | — | defaults if null | user | n/a | P3_USER_EPHEMERAL |
| `consent_local_only` | bool | N | — | must be true to run | user | n/a | P1_INTERNAL |

### 4.2 `UploadedDocument`
| field | type | null? | units | validation | provenance | bilingual | privacy |
|-------|------|-------|-------|------------|------------|-----------|---------|
| `document_id` | str(uuid) | N | — | unique | derived | n/a | P3_USER_EPHEMERAL |
| `filename_hash` | str | N | — | hash, **not** raw name | derived | n/a | P3_USER_EPHEMERAL |
| `mime_type` | enum{image/*,application/pdf,text/plain} | N | — | in set | extractor | n/a | P3_USER_EPHEMERAL |
| `magic_byte_verified` | bool | N | — | PDF ⇒ leading bytes are `%PDF-` | extractor | n/a | P3_USER_EPHEMERAL |
| `is_encrypted` | bool | N | — | PDF only; `true` ⇒ rejected by default (PR-006) | extractor | n/a | P3_USER_EPHEMERAL |
| `validation_status` | enum{accepted,rejected_unsupported,rejected_corrupt,rejected_encrypted,rejected_oversized} | N | — | in set | extractor | n/a | P3_USER_EPHEMERAL |
| `page_count` | int | N | count | ≥1; ≤ `max_pages` (config) | extractor | n/a | P3_USER_EPHEMERAL |
| `temp_path` | str | N | — | inside ephemeral workspace only | derived | n/a | P3_USER_EPHEMERAL |
| `bytes_sha256` | str | N | — | integrity | derived | n/a | P3_USER_EPHEMERAL |
| `delete_after` | datetime | N | — | ≤ session end | config | n/a | P1_INTERNAL |
| `pages` | list[`OCRPage`] | Y | — | filled post-OCR | ocr | n/a | P3_USER_EPHEMERAL |

Raw bytes never leave `temp_path`; never logged; deleted at `delete_after` or on
clear (PR-004). Export omits raw bytes by default (PR-060).

**PDF handling (PR-005…PR-009, local-only/ephemeral).** A `application/pdf`
document must pass `magic_byte_verified` and the `max_pages`/`max_bytes` config
limits; otherwise `validation_status` is set to the matching `rejected_*` value
and the file is refused with a clear local error (nothing transmitted). For each
accepted PDF page FInk records per-page provenance via `OCRPage.text_source`
(text-layer vs local OCR fallback vs mixed). Source PDF bytes, intermediate page
**rasters**, and OCR intermediates are all `P3_USER_EPHEMERAL`, live only under
`temp_path`, and are deleted together on clear/timeout/session-end/shutdown (spec
04 §3). Raw filename is never persisted (`filename_hash` only); no PDF byte or
extracted text is ever sent to a remote service.

### 4.3 `OCRPage`
| field | type | null? | units | validation | provenance | bilingual | privacy |
|-------|------|-------|-------|------------|------------|-----------|---------|
| `page_id` | str | N | — | unique within doc | derived | n/a | P3_USER_EPHEMERAL |
| `page_index` | int | N | count | ≥0; reflects reorder | user/derived | n/a | P3_USER_EPHEMERAL |
| `rotation_deg` | enum{0,90,180,270} | N | deg | in set | user | n/a | P3_USER_EPHEMERAL |
| `width_px`/`height_px` | int | N | px | >0 | extractor | n/a | P3_USER_EPHEMERAL |
| `spans` | list[`OCRSpan`] | N | — | — | ocr | n/a | P3_USER_EPHEMERAL |
| `page_ocr_confidence` | float | N | frac | 0–1 | ocr | n/a | P3_USER_EPHEMERAL |
| `text_source` | enum{text_layer,ocr,mixed} | N | — | per-page provenance (PDF text-layer vs OCR fallback) | extractor | n/a | P3_USER_EPHEMERAL |
| `is_user_corrected` | bool | N | — | — | derived | n/a | P3_USER_EPHEMERAL |

### 4.4 `OCRSpan`
| field | type | null? | units | validation | provenance | bilingual | privacy |
|-------|------|-------|-------|------------|------------|-----------|---------|
| `span_id` | str | N | — | unique within page | derived | n/a | P3_USER_EPHEMERAL |
| `text` | str | N | — | — | ocr | ko-primary | P3_USER_EPHEMERAL |
| `bbox` | obj{x,y,w,h} | N | px | within page | ocr | n/a | P3_USER_EPHEMERAL |
| `confidence` | float | N | frac | 0–1 | ocr | n/a | P3_USER_EPHEMERAL |
| `lang` | enum{ko,en,mixed,num} | N | — | in set | ocr | n/a | P3_USER_EPHEMERAL |
| `corrected_text` | str | Y | — | set by user edit | user | ko-primary | P3_USER_EPHEMERAL |

### 4.5 `Clause`
| field | type | null? | units | validation | provenance | bilingual | privacy |
|-------|------|-------|-------|------------|------------|-----------|---------|
| `clause_id` | str | N | — | unique | derived | n/a | P3_USER_EPHEMERAL |
| `clause_index` | int | N | count | order | derived | n/a | P3_USER_EPHEMERAL |
| `heading_ko` | str | Y | — | — | extractor | ko-primary | P3_USER_EPHEMERAL |
| `text_ko` | str | N | — | reconstructed | derived(ocr+edit) | ko-primary | P3_USER_EPHEMERAL |
| `text_en_gloss` | str | Y | — | generated; **not evidence** | derived | en-alias | P3_USER_EPHEMERAL |
| `source_span_ids` | list[str] | N | — | ≥1 | derived | n/a | P3_USER_EPHEMERAL |
| `risk_categories` | list[enum{F1..F9,X1..X5}] | Y | — | from retrieval | derived | n/a | P3_USER_EPHEMERAL |
| `canonical_ids` | list[str] | Y | — | glossary hits | derived | canonical | P3_USER_EPHEMERAL |
| `seg_confidence` | float | N | frac | 0–1 | extractor | n/a | P3_USER_EPHEMERAL |

### 4.6 `ExtractedFinancialTerms`
One row per detected numeric/temporal/term value tied to a clause.
| field | type | null? | units | validation | provenance | bilingual | privacy |
|-------|------|-------|-------|------------|------------|-----------|---------|
| `term_id` | str | N | — | unique | derived | n/a | P3_USER_EPHEMERAL |
| `clause_id` | str | N | — | FK | derived | n/a | P3_USER_EPHEMERAL |
| `feature_id` | str | N | — | ∈ canonical/aux | extractor | canonical | P3_USER_EPHEMERAL |
| `value_raw` | str | N | — | as found | ocr | ko-primary | P3_USER_EPHEMERAL |
| `value_norm` | decimal/int/float | Y* | per feature unit | normalized | extractor | n/a | P3_USER_EPHEMERAL |
| `unit` | enum{KRW,frac,days,months,—} | N | — | matches feature | extractor | n/a | P3_USER_EPHEMERAL |
| `is_open_ended` | bool | N | — | flags "etc./as determined by Co." | extractor | n/a | P3_USER_EPHEMERAL |
| `extraction_confidence` | float | N | frac | 0–1 | extractor | n/a | P3_USER_EPHEMERAL |
| `source_span_ids` | list[str] | N | — | ≥1 | derived | n/a | P3_USER_EPHEMERAL |

`value_norm=null` with `is_open_ended=true` is the canonical **missing/opaque
numeric** signal that FIM-8 consumes (raises uncertainty, not amount).

### 4.7 `EvidenceRecord` (mirrors `14_MASTER_EVIDENCE_MATRIX.csv`, 20 records, A1/A2 only)
| field | type | null? | units | validation | provenance | bilingual | privacy |
|-------|------|-------|-------|------------|------------|-----------|---------|
| `evidence_id` | str | N | — | unique | corpus:14 | canonical | P1_INTERNAL |
| `source_id` | str | N | — | FK to manifest | corpus:14 | n/a | P1_INTERNAL |
| `authority_tier` | enum{A0,A1,A2} | N | — | **A1/A2 only today** | corpus:14 | n/a | P1_INTERNAL |
| `risk_categories` | list[enum{F1..F9,X1..X5}] | N | — | ≥1 (mirrors upstream CSV column); X tags are **contextual only** — never score-eligible, only F1–F9 signals aggregate (INV-1, spec 03 §3, L5) | corpus:14 | n/a | P1_INTERNAL |
| `article_ref` | str | Y | — | article/section | corpus:14 | ko-primary | P1_INTERNAL |
| `page_ref` | str | Y | — | page | corpus:14 | n/a | P1_INTERNAL |
| `excerpt_ko` | str | Y | — | **< 15 words** | corpus:14 | ko-primary | P2_PRIVATE_LOCAL (license-gated) |
| `excerpt_en_gloss` | str | Y | — | generated; not evidence | corpus:14 | en-alias | P2_PRIVATE_LOCAL |
| `verification_status` | enum{VERIFIED,UNVERIFIED,NOT_VERIFIED_CURRENT} | N | — | **all UNVERIFIED now** | corpus:14 | n/a | P1_INTERNAL |
| `score_eligible` | bool | N | — | true (A1/A2) | derived | n/a | P1_INTERNAL |
| `public_export` | bool | N | — | false until license check | corpus:14 | n/a | P1_INTERNAL |

**Validation:** `excerpt_ko` word count < 15 (CI gate); `public_export=false`
while `license_status=UNKNOWN` (HR/legal gate). `risk_categories` mirrors the
upstream `14_MASTER_EVIDENCE_MATRIX.csv` column: 3 of the 20 A1/A2 records carry
cross-cutting **X** context tags (e.g. `EV-A1-ASSIGNFULL-05`→X2,
`EV-A2-2024-COMICS`→F3;X2, `EV-A2-2024-STATS`→X1). An X-tagged official record may
ground only **contextual, non-scoring** display; scoring aggregation still sums
F1–F9 signals only (INV-1), so the X tags do not make any category score-eligible.

### 4.8 `RiskSignal`
| field | type | null? | units | validation | provenance | bilingual | privacy |
|-------|------|-------|-------|------------|------------|-----------|---------|
| `signal_id` | str | N | — | `RS-<Fx>-<slug>` | config | canonical | P1_INTERNAL |
| `clause_id` | str | N | — | FK | derived | n/a | P3_USER_EPHEMERAL |
| `risk_category` | enum{F1..F9,X1..X5} | N | — | in set | derived | n/a | P3_USER_EPHEMERAL |
| `detector` | enum{rule,model,hybrid} | N | — | in set | config | n/a | P1_INTERNAL |
| `fired` | bool | N | — | — | derived | n/a | P3_USER_EPHEMERAL |
| `grounding_evidence_ids` | list[str] | Y* | — | non-empty ⇒ score-eligible | derived | n/a | P3_USER_EPHEMERAL |
| `score_eligible` | bool | N | — | **true ⟺ ≥1 A0–A2 evidence id** | derived | n/a | P3_USER_EPHEMERAL |
| `severity_raw` | float | Y | frac | 0–1 heuristic | config | n/a | P3_USER_EPHEMERAL |
| `practice_reference` | bool | N | — | true ⟺ only B/C support | derived | n/a | P3_USER_EPHEMERAL |
| `signal_confidence` | float | N | frac | 0–1 | derived | n/a | P3_USER_EPHEMERAL |
| `is_missing_protection` | bool | N | — | "absent clause" signal | derived | n/a | P3_USER_EPHEMERAL |

**Hard gate (CI):** `score_eligible=true` **iff** `grounding_evidence_ids`
contains ≥1 A0–A2 id; a B/C-only signal has `practice_reference=true`,
`score_eligible=false`, and contributes 0 (PASS-gate 1).

### 4.9 `ClauseAssessment`
| field | type | null? | units | validation | provenance | bilingual | privacy |
|-------|------|-------|-------|------------|------------|-----------|---------|
| `clause_id` | str | N | — | FK | derived | n/a | P3_USER_EPHEMERAL |
| `signals` | list[`RiskSignal`] | N | — | — | derived | n/a | P3_USER_EPHEMERAL |
| `category_scores` | map{F1..F9→0–100} | N | — | only eligible signals contribute | derived | n/a | P3_USER_EPHEMERAL |
| `clause_priority` | int | N | 0–100 | aggregate | derived | n/a | P3_USER_EPHEMERAL |
| `explanation_card_ids` | list[str] | Y | — | B/C cards | derived | n/a | P3_USER_EPHEMERAL |
| `questions` | list[str] | Y | — | from checklist | derived | ko-primary | P3_USER_EPHEMERAL |
| `evidence_ids` | list[str] | Y | — | A0–A2 grounding shown | derived | n/a | P3_USER_EPHEMERAL |
| `monetary_links` | list[enum{FIM-1..8}] | Y | — | modules touched | derived | n/a | P3_USER_EPHEMERAL |

### 4.10 `FinancialScenarioInputs` (all user-editable; defaults labeled synthetic)
| field | type | null? | units | validation | provenance | bilingual | privacy |
|-------|------|-------|-------|------------|------------|-----------|---------|
| `annual_discount_rate` | float | N | frac | ≥0; default config | user/config | n/a | P3_USER_EPHEMERAL |
| `sales_low`/`sales_base`/`sales_high` | decimal | Y* | KRW | low≤base≤high | user | n/a | P3_USER_EPHEMERAL |
| `creator_hourly_value` | decimal | Y* | KRW/hour | ≥0 | user | n/a | P3_USER_EPHEMERAL |
| `hours_per_unit` | float | Y* | hours | ≥0 | user | n/a | P3_USER_EPHEMERAL |
| `unpaid_revision_units` | int | Y* | count | ≥0 | user | n/a | P3_USER_EPHEMERAL |
| `alternative_monthly_revenue` | decimal | Y* | KRW/month | ≥0 | user | n/a | P3_USER_EPHEMERAL |
| `scenario_probabilities` | map{str→frac} | Y* | frac | each 0–1 | user | n/a | P3_USER_EPHEMERAL |
| `secondary_rights` | list[obj{type,value,prob}] | Y* | KRW,frac | value≥0, prob 0–1 | user | canonical(type) | P3_USER_EPHEMERAL |
| `penalty_probability` | float | Y* | frac | 0–1; required for FIM-7 expected calc | user | n/a | P3_USER_EPHEMERAL |
| `inputs_are_synthetic` | bool | N | — | **always true for defaults** | derived | n/a | P1_INTERNAL |

### 4.11 `MonetaryExposureEstimate`
One per exposure type per module; **never** summed across types.
| field | type | null? | units | validation | provenance | bilingual | privacy |
|-------|------|-------|-------|------------|------------|-----------|---------|
| `module` | enum{FIM-1..8} | N | — | in set | derived | n/a | P3_USER_EPHEMERAL |
| `exposure_type` | enum{nominal_leakage,present_value_loss,opportunity_cost,liability_exposure,deferral} | N | — | in set | derived | n/a | P3_USER_EPHEMERAL |
| `low`/`base`/`high` | decimal | Y* | KRW | low≤base≤high; null if inputs absent | derived | n/a | P3_USER_EPHEMERAL |
| `is_user_input_required` | bool | N | — | true ⇒ blank until user supplies | derived | n/a | P3_USER_EPHEMERAL |
| `assumptions` | list[str] | N | — | enumerated, labeled synthetic | derived | ko/en | P3_USER_EPHEMERAL |
| `uncertainty_flags` | list[str] | Y | — | from FIM-8 | derived | n/a | P3_USER_EPHEMERAL |
| `nominal_amount` | decimal | Y* | KRW | FIM-2: kept separate from PV | derived | n/a | P3_USER_EPHEMERAL |

### 4.12 `TimeExposure`
| field | type | null? | units | validation | provenance | bilingual | privacy |
|-------|------|-------|-------|------------|------------|-----------|---------|
| `payment_due_days` | int | Y* | days | ≥0 | extractor | n/a | P3_USER_EPHEMERAL |
| `payment_delay_days` | int | Y* | days | ≥0 | extractor/user | n/a | P3_USER_EPHEMERAL |
| `contract_duration_months` | int | Y* | months | ≥0 | extractor | n/a | P3_USER_EPHEMERAL |
| `renewal_duration_months` | int | Y* | months | ≥0 | extractor | n/a | P3_USER_EPHEMERAL |
| `exclusivity_duration_months` | int | Y* | months | ≥0 | extractor | n/a | P3_USER_EPHEMERAL |
| `termination_notice_days` | int | Y* | days | ≥0 | extractor | n/a | P3_USER_EPHEMERAL |
| `estimated_months_to_recoup` | float | Y* | months | ≥0; from FIM-3 | derived | n/a | P3_USER_EPHEMERAL |
| `measured_analysis_runtime_seconds` | float | N | seconds | ≥0; **measured** | derived | n/a | P1_INTERNAL |
| `estimated_human_review_minutes` | float | N | minutes | ≥0; heuristic (spec 03 §5) | derived | n/a | P3_USER_EPHEMERAL |
| `pathway_label` | enum{clarification_likely_sufficient,negotiation_required,professional_review_required,dispute_pathway_may_be_required} | N | — | in set | derived | ko/en | P3_USER_EPHEMERAL |

**Forbidden:** any numeric estimate of court/negotiation/dispute duration. Only
`pathway_label` (categorical) is allowed (INV/non-goal 6).

### 4.13 `ConfidenceBreakdown`
| field | type | null? | units | validation | provenance | bilingual | privacy |
|-------|------|-------|-------|------------|------------|-----------|---------|
| `ocr_confidence` | float | N | frac | 0–1 | ocr | n/a | P3_USER_EPHEMERAL |
| `evidence_confidence` | float | N | frac | 0–1; lowers with UNVERIFIED/thin grounding | derived | n/a | P3_USER_EPHEMERAL |
| `data_completeness` | float | N | frac | 0–1; lowers with missing inputs | derived | n/a | P3_USER_EPHEMERAL |
| `overall_confidence` | float | N | frac | 0–1; documented combination | derived | n/a | P3_USER_EPHEMERAL |
| `drivers` | list[str] | N | — | human-readable reasons | derived | ko/en | P3_USER_EPHEMERAL |

### 4.14 `DocumentAssessment`
| field | type | null? | units | validation | provenance | bilingual | privacy |
|-------|------|-------|-------|------------|------------|-----------|---------|
| `document_id` | str | N | — | FK | derived | n/a | P3_USER_EPHEMERAL |
| `review_priority_score` | int | N | 0–100 | aggregate of eligible signals | derived | n/a | P3_USER_EPHEMERAL |
| `category_scores` | map{F1..F9→0–100} | N | — | — | derived | n/a | P3_USER_EPHEMERAL |
| `clause_assessments` | list[`ClauseAssessment`] | N | — | — | derived | n/a | P3_USER_EPHEMERAL |
| `monetary_exposures` | list[`MonetaryExposureEstimate`] | N | — | grouped by type | derived | n/a | P3_USER_EPHEMERAL |
| `time_exposure` | `TimeExposure` | N | — | — | derived | n/a | P3_USER_EPHEMERAL |
| `confidence` | `ConfidenceBreakdown` | N | — | — | derived | n/a | P3_USER_EPHEMERAL |
| `missing_protections` | list[str] | Y | — | absent-clause signals | derived | ko/en | P3_USER_EPHEMERAL |
| `scoring_config_version` | str | N | — | pins heuristic weights | config | n/a | P1_INTERNAL |

### 4.15 `AnalysisReport`
| field | type | null? | units | validation | provenance | bilingual | privacy |
|-------|------|-------|-------|------------|------------|-----------|---------|
| `report_id` | str | N | — | unique | derived | n/a | P3_USER_EPHEMERAL |
| `request_id` | str | N | — | FK | derived | n/a | P3_USER_EPHEMERAL |
| `assessment` | `DocumentAssessment` | N | — | — | derived | n/a | P3_USER_EPHEMERAL |
| `disclaimers` | list[str] | N | — | must include INV-2 + "not legal advice" | config | ko/en | P0_PUBLIC |
| `generated_text_flag` | bool | N | — | true if any LLM narrative present | derived | n/a | P1_INTERNAL |
| `exported_at` | datetime | Y | — | — | derived | n/a | P3_USER_EPHEMERAL |
| `export_format` | enum{html,md,json} | Y | — | in set | user | n/a | P1_INTERNAL |
| `contains_raw_image` | bool | N | — | **default false** | config | n/a | P3_USER_EPHEMERAL |

### 4.16 `HumanCorrection`
| field | type | null? | units | validation | provenance | bilingual | privacy |
|-------|------|-------|-------|------------|------------|-----------|---------|
| `correction_id` | str | N | — | unique | derived | n/a | P3_USER_EPHEMERAL |
| `target_type` | enum{ocr_span,term,segmentation,assumption} | N | — | in set | user | n/a | P3_USER_EPHEMERAL |
| `target_id` | str | N | — | FK | user | n/a | P3_USER_EPHEMERAL |
| `before`/`after` | str | N/N | — | — | user | ko-primary | P3_USER_EPHEMERAL |
| `created_at` | datetime | N | — | — | derived | n/a | P3_USER_EPHEMERAL |
| `counts_for_review_estimate` | bool | N | — | feeds human-review heuristic | derived | n/a | P1_INTERNAL |

### 4.17 `EvaluationExample` (frozen eval split; **synthetic only**)
| field | type | null? | units | validation | provenance | bilingual | privacy |
|-------|------|-------|-------|------------|------------|-----------|---------|
| `example_id` | str | N | — | unique | dataset | canonical | P1_INTERNAL |
| `split` | enum{dev,frozen_eval} | N | — | frozen split immutable | dataset | n/a | P1_INTERNAL |
| `dataset_ref` | enum{DR-6,DR-7,DR-8,DR-11,DR-12,DR-13,…} | N | — | maps to plan | dataset | n/a | P1_INTERNAL |
| `input_kind` | enum{clause_pair,camera_ocr,paste,query} | N | — | in set | dataset | n/a | P1_INTERNAL |
| `is_synthetic` | bool | N | — | **always true** | dataset | n/a | P1_INTERNAL |
| `is_benign` | bool | N | — | for benign-FPR | dataset | n/a | P1_INTERNAL |
| `gold` | obj | N | — | task-specific gold (labels/spans/values) | dataset | ko-primary | P1_INTERNAL |
| `public_export` | bool | N | — | synthetic-only may be true; **no real data ever** | dataset | n/a | P1_INTERNAL |

### 4.18 `ExperimentResult`
| field | type | null? | units | validation | provenance | bilingual | privacy |
|-------|------|-------|-------|------------|------------|-----------|---------|
| `experiment_id` | str | N | — | unique | derived | n/a | P1_INTERNAL |
| `config_hash` | str | N | — | pins config + code rev | derived | n/a | P1_INTERNAL |
| `arm` | enum{rule_only,model_only,hybrid} | N | — | ablation arm | config | n/a | P1_INTERNAL |
| `metric` | str | N | — | ∈ spec 05 metric set | config | n/a | P1_INTERNAL |
| `value` | float | N | metric unit | — | derived | n/a | P1_INTERNAL |
| `split` | enum{dev,frozen_eval} | N | — | — | config | n/a | P1_INTERNAL |
| `artifact_path` | str | Y | — | local results path | derived | n/a | P1_INTERNAL |
| `result_status` | enum{measured,planned,NA} | N | — | no fabricated values | derived | n/a | P1_INTERNAL |
| `reviewer` | str | Y | — | links RESULT_LEDGER | user | n/a | P1_INTERNAL |

---

## 5. Provenance, versioning, and frozen split

- **Provenance:** every evidence-bearing value carries `source_id` +
  `authority_tier` + `verification_status`; runtime artifacts carry `request_id`
  / `document_id` lineage; scores carry `scoring_config_version`.
- **Versioning:** `corpus_version`, `scoring_config_version`, `code_rev`, and
  `schema_version` are pinned in every `DocumentAssessment` and
  `ExperimentResult`. Config changes bump `scoring_config_version`.
- **Frozen evaluation split:** `EvaluationExample.split=frozen_eval` is created
  once, hashed, and **never edited**; tuning uses `dev` only. Results on the
  frozen split are reported untouched (prevents leakage).

---

## 6. Private/public separation and log redaction

| Class | Examples | In public repo/export? | In logs? |
|-------|----------|:----------------------:|:--------:|
| `P0_PUBLIC` | disclaimers, schema docs, synthetic eval (labeled) | ✅ | ✅ |
| `P1_INTERNAL` | configs, manifest flags, metrics | local only | metadata only |
| `P2_PRIVATE_LOCAL` | B/C cards, glossary KO text, license-gated A1/A2 excerpts | ❌ | ❌ |
| `P3_USER_EPHEMERAL` | uploads, OCR text, clauses, terms, report contents | ❌ | ❌ |

- **No contract text in access logs** (PR/NFR-PRIVACY). Logs may store opaque
  `request_id`/`document_id`, timings, counts, error codes — never `text`,
  `excerpt_ko`, `value_raw`, or `temp_path`.
- **No long private-book excerpts** anywhere; B/C `public_export=false`.
- **Temporary uploads** (`P3`) live only in the ephemeral workspace and are
  deleted at `delete_after`/clear; `.gitignore` already excludes `uploads/`,
  `contracts/`, `models/`, `indexes/`, `data/private|raw|unsanitized`, `*.pdf`,
  `*.zip`, and `.fink/`.
- **Copyright/public-export fields** (`license_status`, `public_export`) gate
  every excerpt; `UNKNOWN` license ⇒ `public_export=false`.

---

## 7. Bilingual behavior (cross-schema)

- Every concept-bearing record carries `canonical_id` (EN stable) + `label_ko` +
  `label_en` + `aliases_ko[]` + `aliases_en[]`.
- KO and EN queries normalize to the same `canonical_id` (PR-020, EV-KOEN).
- `*_en_gloss` / `label_en` / `excerpt_en_gloss` are `generated_translation` and
  **never** rendered as evidence; the UI labels them "generated."
- The 8 non-equivalence-sensitive terms carry caveats (HR-03) and are never
  silently equated.

Binding tasks: `FINK-S0-02` (taxonomy), `FINK-S0-03` (features/glossary),
`FINK-S0-04` (evidence), `FINK-S0-05` (cards/checklist) in spec 08.

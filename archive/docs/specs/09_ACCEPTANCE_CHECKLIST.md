# 09 — Acceptance Checklist

**Parent:** `docs/FINK_MASTER_SPEC.md` · **Spec version:** 1.0.0
Inherits INV-1…INV-9. This file defines **one objective, machine- or
reviewer-checkable acceptance test per `AC-*` ID** referenced anywhere in specs
01–08. Each `AC-*` is defined **exactly once** here. Every test runs on
**synthetic/sanitized** data only (INV-8); results are *measured-on-synthetic*
and not generalized (INV-9).

**How to read a row.** `AC ID` is the stable token cited by the specs.
`Objective pass criterion` is the binary condition that must hold. `Traces`
lists the requirement/invariant/metric IDs the test covers. `Verifier` names the
spec-08 task and/or machine gate that executes it. Status starts `not_run`.

Coverage map (families → section): invariants → §A; ingestion + PDF → §B;
OCR/segmentation/extraction → §C; retrieval/authority/bilingual → §D; scoring +
financial modules → §E; time + confidence → §F; output/export → §G;
privacy/runtime/portability → §H; UX → §I; paper/deliverable sync → §J;
evaluation metrics → §K; release gates → §L.

---

## §A Invariants (`AC-INV-*`)

| AC ID | Objective pass criterion | Traces | Verifier |
|-------|--------------------------|--------|----------|
| AC-INV-1 | On a fixture with mixed-tier grounding, a signal is `score_eligible=true` **iff** it carries ≥1 `A0/A1/A2` evidence id; B/C-only signals contribute exactly 0; `M1/M2/M3` and `R0`/`D0` never appear as scoring evidence. | INV-1 | FINK-S0-08, FINK-S2-04 / `invariant_suite`, `eligibility_gate_test` |
| AC-INV-2 | The rendered report and every score tooltip/label assert "review priority" and **deny** fraud/illegality/validity/voidness/unfairness/guaranteed-loss readings; a string scan of the report template finds the required disclaimer and no forbidden verdict phrase. | INV-2 | FINK-S4-03 / `four_dimension_present_test` |
| AC-INV-3 | A produced `AnalysisReport` contains all four dimensions (D1 score, D2 monetary range, D3 time, D4 confidence) as separate fields; no field merges them into one number. | INV-3 | FINK-S4-03 / `four_dimension_present_test` |
| AC-INV-4 | KO source text is stored as canonical; every EN label/gloss has `generated_translation=true`; a KO query and its EN alias resolve to the same `canonical_id`. | INV-4 | FINK-S2-02 / `koen_consistency_harness` |
| AC-INV-5 | The full pipeline completes with all sockets blocked and **zero** outbound connection attempts (same as AC-RT-OFFLINE). | INV-5 | FINK-S5-06 / `offline_integration_test` |
| AC-INV-6 | When a required extracted input is absent, the module output is `null` with `is_user_input_required=true`; no numeric value is substituted anywhere in the report. | INV-6 | FINK-S3-04 / `blank_without_inputs_test` |
| AC-INV-7 | Adding opacity flags raises `band_widen_factor`, widens `[low,high]` around an **unchanged** `base`, lowers `overall_confidence`, and leaves `review_priority_score` unchanged (same vector as FIM-8-T1). | INV-7 | FINK-S3-05 / `fim8_uncertainty_test` |
| AC-INV-8 | A sample run leaves no `P3` content under any git-tracked path; logs/exports contain no contract text; B/C `public_export=false`; official excerpts < 15 words. | INV-8 | FINK-S8-01, FINK-S8-02 / `preflight_ok`, `copyright_audit` |
| AC-INV-9 | Every scoring weight/threshold/band is sourced from versioned config and tagged heuristic; the paper notes use "DFL-inspired"; no A0-gated figure is stated as current while HR-01 is open. | INV-9 | FINK-S0-07, FINK-S7-02 / `weights_flagged_heuristic`, `paper_sync_checker` |

---

## §B Ingestion and PDF (`AC-IN-*`, `AC-PDF-*`)

| AC ID | Objective pass criterion | Traces | Verifier |
|-------|--------------------------|--------|----------|
| AC-IN-1 | All four input modes — camera, image (JPG/PNG/HEIC/WEBP), **PDF**, paste — reach a valid `AnalysisReport`; PDF is exercised as a **mandatory** mode, not skipped. | PR-001, PR-005 | FINK-S1-01, FINK-S4-02 / `ingest_tests`, `ui_ingest_tests` |
| AC-IN-2 | A multi-page document can be reordered, rotated (0/90/180/270), and have a page deleted before analysis; `OCRPage.page_index`/`rotation_deg` reflect the edits. | PR-002 | FINK-S1-03 / `correction_flow_test` |
| AC-PDF-TEXT | A text-layer PDF (KO and EN fixtures) yields page text via **local text-layer extraction**; `OCRPage.text_source=text_layer`; extracted money/%/date values match gold. | PR-005, PR-007 | FINK-S1-06 / `pdf_textlayer_ocr_tests` |
| AC-PDF-OCR | An image-only (scanned) PDF triggers **local OCR fallback**; `OCRPage.text_source=ocr`; spans carry confidence; no text-layer is assumed. | PR-005, PR-007 | FINK-S1-06 / `pdf_textlayer_ocr_tests` |
| AC-PDF-MIXED | A mixed PDF (some text-layer, some image pages) yields correct per-page `text_source` (`text_layer`/`ocr`), with no page dropped. | PR-005 | FINK-S1-06 / `pdf_textlayer_ocr_tests` |
| AC-PDF-MULTIPAGE | A multi-page PDF produces one `OCRPage` per page with stable `page_index`; `page_count` equals the source page count (≤ `max_pages`). | PR-005, PR-002 | FINK-S1-06 / `pdf_validation_tests` |
| AC-PDF-MIME | A file whose extension is `.pdf` but whose leading bytes are not `%PDF-`, or whose MIME is not `application/pdf`, is rejected (`validation_status=rejected_unsupported`); a valid PDF passes `magic_byte_verified=true`. | PR-006 | FINK-S1-06 / `pdf_validation_tests` |
| AC-PDF-CORRUPT | A truncated/garbled PDF is rejected with `validation_status=rejected_corrupt` and a clear local error; nothing is transmitted. | PR-006 | FINK-S1-06 / `pdf_validation_tests` |
| AC-PDF-LIMITS | A PDF exceeding the configured `max_pages` or `max_bytes` is rejected with `validation_status=rejected_oversized`; limits are read from config (not hard-coded). | PR-006 | FINK-S1-06 / `pdf_validation_tests` |
| AC-PDF-ENCRYPTED | An encrypted PDF is **rejected by default** (`validation_status=rejected_encrypted`); the only alternative is a **local** password-entry flow; no remote decryption is attempted. | PR-006 | FINK-S1-06 / `pdf_validation_tests` |
| AC-PDF-RASTER | PDF rasterization runs entirely locally; with sockets blocked, rasterization + OCR still succeed (no remote raster/OCR service). | PR-007 | FINK-S1-06 / `pdf_offline_test` |
| AC-PDF-PAGEOPS | PDF pages support **preview, reorder, rotate, delete** through the same controls as images (UX-PAGE-ORG); edits persist into analysis. | PR-008, PR-002 | FINK-S4-02 / `ui_ingest_tests`, `ui_pdf_upload_test` |
| AC-PDF-OCRCORRECT | A user inline-corrects OCR text on a PDF page; the edit creates a `HumanCorrection` and updates downstream extraction (UX-OCR-PREVIEW). | PR-008, PR-011 | FINK-S1-03 / `correction_flow_test` |
| AC-PDF-PROVENANCE | Every accepted PDF page records per-page provenance in `OCRPage.text_source` (`text_layer`/`ocr`/`mixed`); the report can show which path produced each page. | PR-007 | FINK-S1-06 / `pdf_textlayer_ocr_tests` |
| AC-PDF-WORKSPACE | The PDF temp workspace is created with least-privilege permissions (owner-only dir/files); no `P3` PDF artifact is written outside it. | PR-009, RT-UP-1 | FINK-S1-06 / `pdf_ephemeral_delete_test` |
| AC-PDF-DELETE | On clear/timeout/session-end/shutdown, the source PDF bytes, **all page rasters, and OCR intermediates** are deleted; a post-clear scan of the workspace finds none. | PR-009, RT-UP-2 | FINK-S1-06 / `pdf_ephemeral_delete_test` |
| AC-PDF-LOG | After a PDF run, logs contain no raw filename and no contract text (only `filename_hash`, opaque ids, counts, timings, error codes). | PR-009, NFR-PRIVACY | FINK-S1-06 / `pdf_log_redaction_test` |
| AC-PDF-OFFLINE | The complete PDF path (validate → raster → text/OCR → segment) completes with sockets blocked and **zero** outbound attempts. | PR-009, INV-5 | FINK-S1-06, FINK-S5-06 / `pdf_offline_test` |
| AC-PDF-TESTS | PDF-specific **unit** tests (validation, text-layer, OCR-fallback, provenance) and **integration** tests (end-to-end PDF → report, offline) exist and pass. | PR-009 | FINK-S1-06 / `pdf_validation_tests`, `pdf_textlayer_ocr_tests` |
| AC-PDF-MOBILE | A PDF can be uploaded and its pages operated on from a **mobile browser** and a **desktop** browser; both reach a report. | PR-009, NFR-A11Y | FINK-S4-02 / `ui_pdf_upload_test` |
| AC-PDF-BILINGUAL | Korean-content and English-content PDFs are both extracted/OCR'd correctly (text-layer and image-only variants). | PR-009, NFR-I18N | FINK-S1-06 / `pdf_textlayer_ocr_tests` |

---

## §C OCR, segmentation, extraction (`AC-OCR-*`, `AC-SEG-1`, `AC-EXTRACT-1`)

| AC ID | Objective pass criterion | Traces | Verifier |
|-------|--------------------------|--------|----------|
| AC-OCR-1 | Local OCR (KO+EN) produces `OCRSpan`s with per-span `bbox`, `confidence`, and `lang`; runs offline; EV-OCR-CER/WER are computable on DR-7. | PR-010, EV-OCR-CER, EV-OCR-WER | FINK-S1-02 / `ocr_offline_test`, `ocr_schema_ok` |
| AC-OCR-2 | OCR preview allows inline edits; an edit writes a `HumanCorrection`, flips `is_user_corrected=true`, and re-triggers extraction for affected clauses. | PR-011 | FINK-S1-03 / `correction_flow_test` |
| AC-SEG-1 | Clause segmentation produces `Clause` records each linking ≥1 `source_span_id`; boundary quality EV-SEG is computable on DR-7. | PR-012, EV-SEG | FINK-S1-04 / `segmentation_tests` |
| AC-EXTRACT-1 | Money/%/date/duration terms produce `ExtractedFinancialTerms` with `value_norm`, `unit`, provenance, and `is_open_ended`; open-ended/opaque numerics carry `value_norm=null`; EV-EXACT-* computable. | PR-013, EV-EXACT-MONEY, EV-EXACT-PCT, EV-EXACT-DATE, EV-EXACT-DUR | FINK-S1-05 / `extract_tests`, `exact_match_harness` |

---

## §D Retrieval, authority, bilingual (`AC-AUTH-*`, `AC-KOEN-1`)

| AC ID | Objective pass criterion | Traces | Verifier |
|-------|--------------------------|--------|----------|
| AC-AUTH-1 | Retrieval returns B/C cards (explanation) **and** A0–A2 evidence (grounding); every returned record carries `source_id`, `authority_tier`, `verification_status`. | PR-021 | FINK-S2-03 / `authority_tag_present` |
| AC-AUTH-2 | A signal grounded only by B/C is `practice_reference=true`, `score_eligible=false`, contribution 0; a signal grounded by ≥1 A0–A2 id is `score_eligible=true` (mirrors PASS-gate 1; SC-AGG-T1). | PR-022, INV-1 | FINK-S2-04 / `eligibility_gate_test` |
| AC-AUTH-3 | When two sources conflict, both are returned with provenance and the precedence rule (2025 webtoon form > 2018 form on overlap); neither is silently dropped or merged. | PR-023 | FINK-S2-03 / `conflict_preserved_test` |
| AC-KOEN-1 | KO and EN paired queries (DR-8) return the same `canonical_id`/top-k; the 8 non-equivalence-sensitive terms carry `non_equivalence_caveat`; EN is never labeled "evidence". | PR-020, INV-4, EV-KOEN | FINK-S2-02 / `koen_consistency_harness` |

---

## §E Scoring and financial-impact modules (`AC-SC-*`, `AC-FIN-*`)

| AC ID | Objective pass criterion | Traces | Verifier |
|-------|--------------------------|--------|----------|
| AC-SC-AGG | Category scores saturate within 0–100; document `review_priority_score` is bounded 0–100; only score-eligible signals contribute; tests SC-AGG-T1 (B/C → 0), SC-AGG-T2 (bounded), SC-AGG-T3 (low OCR confidence lowers D4 not the floored priority) pass. | INV-3, INV-1 | FINK-S3-02 / `aggregation_tests` |
| AC-SC-CONFIG | All `severity_weight`, `authority_factor`, `k_F`, `w_F`, confidence weights, `conf_floor`, FIM defaults, and band/pathway thresholds load from versioned `scoring_config.yaml` with `scoring_config_version`; each is flagged heuristic. | NFR-CONFIG, INV-9 | FINK-S0-07 / `config_versioned`, `weights_flagged_heuristic` |
| AC-FIN-FIM1 | FIM-1 unit test **FIM-1-T1** passes: leakage = 1,400,000 (exact) for the specified inputs; output is a low/base/high `nominal_leakage` range. | FIM-1, EV-UNIT | FINK-S3-03 / `fim_core_unit_tests` |
| AC-FIN-FIM2 | FIM-2 unit test **FIM-2-T1** passes: `delay_pv_loss ≈ 237,700` (±1 %) and `nominal_amount = 10,000,000` is reported as a **separate** field (never summed). | FIM-2, EV-UNIT | FINK-S3-03 / `fim_core_unit_tests` |
| AC-FIN-FIM3 | FIM-3 unit test **FIM-3-T1** passes: `months_to_recoup = 18/9/5` for low/base/high sales; the column meaning (sales vs exposure) is labeled so high-sales is not misread as high exposure. | FIM-3, EV-UNIT | FINK-S3-03 / `fim_core_unit_tests` |
| AC-FIN-FIM4 | FIM-4 unit test **FIM-4-T1** passes: base 1,200,000 / low 800,000 / high 1,600,000; module is **blank** until the three user inputs are supplied. | FIM-4, EV-UNIT, INV-6 | FINK-S3-04 / `fim_scenario_unit_tests`, `blank_without_inputs_test` |
| AC-FIN-FIM5 | FIM-5 unit test **FIM-5-T1** passes: `opportunity_cost ≈ 5,845,000` (±1 %); requires `alternative_monthly_revenue` and `p`; labeled scenario/synthetic. | FIM-5, EV-UNIT | FINK-S3-04 / `fim_scenario_unit_tests` |
| AC-FIN-FIM6 | FIM-6 unit test **FIM-6-T1** passes: `scenario_value = 2,600,000` (exact); IP value comes **only** from user scenarios, never auto-valued from text. | FIM-6, EV-UNIT, non-goal 3 | FINK-S3-04 / `fim_scenario_unit_tests` |
| AC-FIN-FIM7 | FIM-7 unit tests **FIM-7-T1/T2** pass: capped → `max_nominal_exposure=5,000,000`, `expected_penalty=500,000` with p=0.1; uncapped + no probability → `expected_penalty=null` and an "uncapped" signal with **no invented number**. | FIM-7, EV-UNIT, non-goal 4 | FINK-S3-03 / `fim_core_unit_tests` |
| AC-FIN-FIM8 | FIM-8 unit test **FIM-8-T1** passes: factor 1.2 → low 3,791,667 / base 5,250,000 (unchanged) / high 7,140,000; `review_priority_score` unchanged; `data_completeness` reduced. | FIM-8, EV-UNIT, INV-7 | FINK-S3-05 / `fim8_uncertainty_test` |
| AC-FIN-SEP | The five `exposure_type` partitions (nominal_leakage, present_value_loss, deferral, opportunity_cost, liability_exposure) are never summed into one total; test **SC-SEP-T1** passes. | PR-041, INV-3 | FINK-S3-03 / `exposure_separation_test` |
| AC-FIN-EDIT | Editing any `FinancialScenarioInputs` value live-recomputes FIM-1…FIM-7; all defaults are labeled "synthetic assumption"; no guessed number is shown. | PR-043 | FINK-S4-04 / `assumptions_recompute_test` |
| AC-FIN-BLANK | FIM-4/5/6 and the FIM-7 expected-value path stay **blank with a prompt** until the user supplies required inputs. | PR-040, INV-6 | FINK-S3-04 / `blank_without_inputs_test` |

---

## §F Time and confidence (`AC-TIME-*`, `AC-CONF-1`)

| AC ID | Objective pass criterion | Traces | Verifier |
|-------|--------------------------|--------|----------|
| AC-TIME-1 | `TimeExposure` exposes typed fields + a categorical `pathway_label`; a scan asserts **no** numeric court/negotiation/dispute-duration field exists (`no_duration_number_test`). | PR-042, non-goal 6 | FINK-S3-06 / `no_duration_number_test` |
| AC-TIME-2 | `estimated_human_review_minutes` is computed from the documented heuristic coefficients (config) and `measured_analysis_runtime_seconds` is the measured value; the "not legal advice" disclaimer is present. | PR-051 | FINK-S3-06 / `time_exposure_tests` |
| AC-CONF-1 | `ConfidenceBreakdown` decomposes OCR/evidence/data-completeness/overall; missing financial inputs **widen** exposure bands and **lower** confidence, never inflate amounts or the score. | PR-050, INV-7 | FINK-S3-05 / `fim8_uncertainty_test` |

---

## §G Output and export (`AC-OUT-1`)

| AC ID | Objective pass criterion | Traces | Verifier |
|-------|--------------------------|--------|----------|
| AC-OUT-1 | "Export local report" writes HTML/MD/JSON locally with **no** network call; `contains_raw_image=false` by default; disclaimers, four dimensions, grounding, assumptions, and questions are present. | PR-060 | FINK-S4-05 / `export_local_test`, `export_no_raw_image_test` |

---

## §H Privacy, runtime, portability (`AC-PV-*`, `AC-RT-*`, `AC-PORT-1`)

| AC ID | Objective pass criterion | Traces | Verifier |
|-------|--------------------------|--------|----------|
| AC-PV-1 | Uploaded artifacts live only in the ephemeral workspace and are deleted at session end and on explicit "clear"; none is ever written under a git-tracked path. | PR-004, RT-UP-1/2/5 | FINK-S1-01 / `ephemeral_delete_test` |
| AC-PV-2 | A redaction test asserts logs contain none of `OCRSpan.text`, `Clause.text_ko`, `value_raw`, `excerpt_ko`, `temp_path`, or raw filename — only opaque ids/counts/timings/error codes. | NFR-PRIVACY, RT-LOG-1/2/3 | FINK-S5-06 / `privacy_redaction_test` |
| AC-PV-3 | No `P2` private material is in any public artifact: B/C `public_export=false`; official excerpts < 15 words and license-gated; no API keys. | INV-8, RT-LOG | FINK-S8-02 / `copyright_audit` |
| AC-RT-OFFLINE | With network disabled, the full pipeline (ingest → OCR → retrieve → score → report) completes and produces a valid `AnalysisReport` with **zero** outbound connection attempts; latency + peak memory recorded (EV-OFFLINE, EV-LAT, EV-MEM). | NFR-LOCAL, INV-5, RT-006 | FINK-S5-06 / `offline_integration_test` |
| AC-RT-NET | No telemetry, analytics, crash-reporting, font/CDN, or update check fires during analysis (no such client exists on the analysis path). | RT-NET-2 | FINK-S4-01 / `no_network_runtime_test` |
| AC-RT-LLM | Any optional model/LLM weights load from **local files**; in the offline-test configuration nothing is downloaded at runtime. | RT-NET-3 | FINK-S5-06 / `offline_integration_test` |
| AC-PORT-1 | The 18 schemas are profile-neutral; a documented sanitization step strips `P2_PRIVATE_LOCAL` content to produce the mobile-lite pack while keeping authority-tier metadata. | NFR-PORT, RT-007 | FINK-S0-06 / `schema_validation_suite` |

---

## §I UX (`AC-UX-*`)

| AC ID | Objective pass criterion | Traces | Verifier |
|-------|--------------------------|--------|----------|
| AC-UX-RESP | The app renders usably on a phone browser and a desktop browser; touch targets ≥ 44px, stated contrast baseline met, keyboard navigation works. | NFR-A11Y | FINK-S4-01 / `web_smoke_test` |
| AC-UX-I18N | Full KO and EN UI with KO default; no machine-translated text is presented as source (EN marked generated). | NFR-I18N, INV-4 | FINK-S4-01 / `web_smoke_test` |
| AC-UX-DISC | Persistent and in-export disclaimers state: review-priority-not-verdict, not legal advice, figures are scenario estimates, sources UNVERIFIED pending A0, KO source/EN generated. | PR-051, INV-2 | FINK-S4-01 / `web_smoke_test` |
| AC-UX-EXPL | Each flagged clause shows a plain-language financial explanation (KO primary, EN alias) from B/C cards, labeled **non-scoring / practice reference**. | PR-030 | FINK-S4-03 / `report_ui_tests` |
| AC-UX-Q | Creator-specific questions-before-signing (from the 52-item checklist + cards) are shown, tied to the flagged clause, marked non-scoring. | PR-031 | FINK-S4-03 / `report_ui_tests` |
| AC-UX-CARDS | One card per active F-category; cross-cutting X1–X5 items render in a separate "context (non-scoring)" section so they never look like score drivers. | UX-CARDS | FINK-S4-03 / `report_ui_tests` |
| AC-UX-EVID | Each card's official-source comparison shows `source_id`, `authority_tier`, a < 15-word excerpt, and the `verification_status` (UNVERIFIED badge today); conflicting sources appear side-by-side with precedence. | UX-EVID, PR-023 | FINK-S4-03 / `report_ui_tests` |
| AC-UX-HILITE | A flagged clause highlights its triggering span and links back to the source page. | UX-HILITE | FINK-S4-03 / `report_ui_tests` |

---

## §J Paper, project page, deliverable sync (`AC-PA-*`)

| AC ID | Objective pass criterion | Traces | Verifier |
|-------|--------------------------|--------|----------|
| AC-PA-MAP | The six course report parts each map to the named `docs/paper/*` note(s). | PA-MAP | FINK-S7-01 / `paper_claim_trace` |
| AC-PA-CLAIM | Every quantitative/evaluative claim in a paper note references a `claim_id` in `CLAIM_LEDGER.csv`. | PA-CLAIM | FINK-S7-02 / `paper_sync_checker` |
| AC-PA-RESULT | Each results/experiments claim points to a `RESULT_LEDGER.csv` row with `status=measured` and a real `artifact_path`; no `value` is fabricated. | PA-RESULT, INV-9 | FINK-S7-02 / `no_fabricated_value` |
| AC-PA-FIG | Every figure in a note or on the project page has a `FIGURE_REGISTRY.csv` row with a real `source_artifact`. | PA-FIG | FINK-S7-02 / `paper_sync_checker` |
| AC-PA-SYNC | `scripts/check_paper_sync` enforces sync rules 1–6 and fails on any unsupported claim, fabricated value, orphan figure, or template change. | PA-SYNC | FINK-S7-02 / `paper_sync_checker` |
| AC-PA-TEMPLATE | A gate asserts `paper/template/icml2026/` is byte-unchanged. | PA-TEMPLATE | FINK-S7-02 / `template_untouched_gate` |
| AC-PA-AIUSE | `docs/ai-use-log.md` is current and records the HR-08 human-verification attestation. | PA-AIUSE, HR-08 | FINK-S7-03 / `aiuse_present` |
| AC-PA-SITE | The static project page is public-safe: no real contracts, no private-book text, no long official excerpts, no keys; figures come from `FIGURE_REGISTRY`. | PA-SITE | FINK-S6-01 / `site_public_safe_scan` |
| AC-PA-COMPLY | The R0 term-project checklist (six sections, seven evaluation criteria, AI-disclosure, citations, submission conditions) is satisfied or explicitly deferred-with-rationale. | PA-COMPLY | FINK-S8-03 / `acceptance_checklist_run` |

---

## §K Evaluation metrics (`AC-EV-*`)

| AC ID | Objective pass criterion | Traces | Verifier |
|-------|--------------------------|--------|----------|
| AC-EV-CORE | Every MVP metric (EV-OCR-CER/WER, EV-EXACT-MONEY/PCT/DATE/DUR, EV-SEG, EV-R@3/R@5, EV-AUTH, EV-KOEN, EV-F1, EV-BENIGN-FPR, EV-SEV, EV-SPAN, EV-STAB, EV-LAT, EV-MEM, EV-OFFLINE, EV-PRIV, EV-DFU core, EV-USAB) is computed on the frozen synthetic split and logged to `RESULT_LEDGER.csv` with `status=measured`; **no metric carries a pre-asserted value**. | spec 05 metric registry, INV-9 | FINK-S5-02…S5-06 / metric runs |
| AC-EV-UNIT | All formula unit tests pass within tolerance: FIM-1-T1…FIM-8-T1, SC-AGG-T1/T2/T3, SC-SEP-T1 (EV-UNIT, EV-FINSCEN). | EV-UNIT, EV-FINSCEN | FINK-S5-05 / `formula_unit_suite` |
| AC-EV-ABLATION | The three arms `rule_only`/`model_only`/`hybrid` are reported on identical inputs; no arm is claimed optimal beyond the measured synthetic result. | spec 05 §5 | FINK-S5-04 / `ablation_three_arms` |
| AC-EV-FROZEN | The `frozen_eval` split is created once, hashed, and never edited; tuning uses `dev` only. | spec 02 §5, spec 05 §1 | FINK-S5-01 / `frozen_split_hash_test` |
| AC-EV-SYNTH | Every `EvaluationExample` has `is_synthetic=true`; no real contract data exists in any eval artifact. | spec 05 §1, INV-8 | FINK-S5-01 / `synthetic_only_test` |
| AC-EV-CALIB | *(Stretch)* Calibration (EV-CALIB) is reported *measured-on-synthetic* only (rank agreement; ECE if a probability-like confidence is exposed) and not generalized. | EV-CALIB, INV-9 | FINK-S5-07 / `dfu_run` |

---

## §L Release gates (`AC-REL-*`)

| AC ID | Objective pass criterion | Traces | Verifier |
|-------|--------------------------|--------|----------|
| AC-REL-PREFLIGHT | `scripts/public_repo_preflight.sh` reports `PREFLIGHT_OK`; the commit candidate contains no `.fink/`, `*.pdf`, `*.zip`, `contracts/`, or `uploads/`. | spec 04 §5 | FINK-S8-01 / `preflight_ok` |
| AC-REL-SECRET | A secret scan finds no API keys anywhere in repo/datasets/demo. | INV-8 | FINK-S8-01 / `secret_scan` |
| AC-REL-GITIGNORE | `.gitignore` excludes `.fink/`, `*.pdf`, `*.zip`, `uploads/`, `contracts/`, `models/`, `indexes/`, `data/private|raw|unsanitized/`. | spec 04 §5 | FINK-S8-01 / `gitignore_enforced` |
| AC-REL-COPYRIGHT | 0 official excerpts ≥ 15 words; `public_export=false` wherever `license_status=UNKNOWN`; B/C never public. | INV-8 | FINK-S8-02 / `copyright_audit` |
| AC-REL-HR | HR P0/P1 items are resolved or explicitly deferred-with-rationale; **no current-law claim is published before HR-01**; HR-07 recorded RESOLVED (HD-3). | spec 08 human_gates | FINK-S8-03 / `acceptance_checklist_run` |
| AC-REL-INPUTS | `scripts/verify_spec_inputs.sh` reports `SPEC_INPUTS_OK` (all 23 record-level Claude files + ≥10 ChatGPT structured files present; no prohibited reference binaries); record counts match `32_FINAL_FILE_INDEX.csv` (HD-11). | HD-11 | FINK-S0-01 / `count_check`, `schema_load_ok` |

---

## FINK-S8-03 pre-submission checklist run

**Run date:** 2026-06-22 KST. **Base commit:** `f99379feeb108b47235d2672aa0d3ad0a779900e`.
**Scope:** this run records the final acceptance/human-gate disposition for
`FINK-S8-03`; non-S8 implementation rows remain delegated to their listed
verifiers and prior dependency tasks. **Result:** `acceptance_checklist_run`
passes with no unresolved P0/P1 HR deferral under the current loop gate
snapshot.

| Checklist item | Result | Rationale |
|----------------|--------|-----------|
| AC-REL-PREFLIGHT / AC-REL-SECRET / AC-REL-GITIGNORE | GREEN from dependency | `FINK-S8-01` is a declared dependency. This task changes only paper/checklist notes and adds no `.fink/`, PDF, ZIP, upload, contract, model, index, private/raw/unsanitized data, or secret-bearing artifact. |
| AC-REL-COPYRIGHT | GREEN from dependency | `FINK-S8-02` is a declared dependency. This task adds no source excerpts, private-book text, contract text, or license-gated material. |
| AC-PA-SYNC / AC-PA-TEMPLATE | GREEN from dependency plus recheck | `FINK-S7-02` is a declared dependency; this run keeps the paper notes claim-ledgered and does not touch the ICML template. |
| AC-PA-COMPLY | GREEN | Course report mapping, AI disclosure requirement, citation/claim/result ledgers, submission deadline, and HR dispositions are recorded. The governing offering is **2026 Spring IE412 AI for Finance** and the deadline is **2026-06-24 23:59 KST** (HD-3 / HR-07). |
| AC-REL-HR | GREEN | HR-01/02/03/05/06/08 status is recorded below; HR-07 is confirmed resolved. No current-law claim is published. |
| AC-INV-9 | GREEN | Paper notes retain DFL-inspired wording, heuristic-weight limits, synthetic-result limits, and no current-law claim. |

### HR disposition

| HR ID | Priority | Status for FINK-S8-03 | Disposition |
|-------|----------|-----------------------|-------------|
| HR-01 | P0 | RESOLVED (auto, `conservative_mode`) | No current-law claim is made. Evidence remains `UNVERIFIED` and date-stamped; A0-A2-only scoring remains enforced by the invariant/authority gates. |
| HR-02 | P0 | RESOLVED (auto, `conservative_mode`) | Webtoon-specific material is treated as practice/context unless independently A0-A2 grounded; no authoritative webtoon-law claim is published. |
| HR-03 | P1 | RESOLVED (auto, `conservative_mode`) | Korean remains canonical; English aliases are retrieval/UX aids with caveats and are never labeled original evidence or legal equivalence. |
| HR-05 | P1 | RESOLVED (auto, `conservative_mode`) | Dated 2018-2021 figures stay date-stamped and are never presented as current. |
| HR-06 | P2 | RESOLVED (auto) | Glossary/category routing is covered by glossary/eligibility invariants; cross-cutting X categories remain non-scoring. Recorded here because the task requires HR-06 status. |
| HR-07 | P1 | RESOLVED (human, HD-3) | Governing offering: 2026 Spring IE412 AI for Finance. Binding deadline: 2026-06-24 23:59 KST. |
| HR-08 | P1 | RESOLVED (human) | The academic-integrity attestation remains a human act. This run records the resolved loop gate and does not auto-attest on the author's behalf. |

### Deferrals

No P0/P1 HR item is deferred for this checklist run. The conservative-mode
resolutions above are not permission to publish current-law, legal-equivalence,
authoritative webtoon-law, unfairness, validity, fraud, or guaranteed-loss
claims; they are release constraints that keep FInk framed only as Contractual
Financial Review Priority.

---

## Definition completeness

Every `AC-*` token cited in specs 01, 03, 04, 06, 07, and 08 is defined exactly
once above. Wildcard citations expand as: `AC-FIN-*` → AC-FIN-FIM1…FIM8,
AC-FIN-SEP, AC-FIN-EDIT, AC-FIN-BLANK; `AC-SC-*` → AC-SC-AGG, AC-SC-CONFIG;
`AC-RT-*` → AC-RT-OFFLINE, AC-RT-NET, AC-RT-LLM; `AC-PV-*` → AC-PV-1/2/3;
`AC-UX-*` → AC-UX-RESP/I18N/DISC/EXPL/Q/CARDS/EVID/HILITE; `AC-IN-*` →
AC-IN-1/2; `AC-PA-*` → AC-PA-MAP/CLAIM/RESULT/FIG/SYNC/TEMPLATE/AIUSE/SITE/COMPLY;
`AC-PDF-*` → the 20 PDF rows in §B. Requirement-level traceability to tasks and
metrics is in `docs/specs/10_TRACEABILITY_MATRIX.csv`.

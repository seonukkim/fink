You are Claude Opus 4.8 with maximum effort.

Your sole task is to create an implementation-grade master specification for FInk.
Do not implement application code, agent-loop code, tests, UI, or deployment in this run.

# INPUTS

Read every supported structured file under:

- .fink/inputs/chatgpt/
- .fink/inputs/claude/stage-0/
- .fink/inputs/claude/stage-1/
- .fink/inputs/claude/stage-2/
- .fink/inputs/claude/stage-3/

Supported formats:

- Markdown
- CSV
- JSON
- JSONL
- YAML

Do not search the web.
Do not use PDFs.
Do not request OCR.
Do not rely on files outside this repository.

Before writing the specification, verify that Stage 3 includes:

- 00_DATA_PACKAGE_README.md
- 30_DATA_GAPS_CONFLICTS_AND_LIMITATIONS.md
- 31_PREPROCESSING_QA_REPORT.md
- 32_FINAL_FILE_INDEX.csv
- 33_REQUIRED_HUMAN_REVIEW.csv

If mandatory Stage 3 inputs are missing, write only:

docs/specs/SPEC_BLOCKERS.md

and stop.

# PROJECT

Brand: FInk

Working paper title:

FInk: Local-First Financial Risk Review for Creator Contracts

Purpose:

A Korean/English, local-first Financial AI system that accepts photographed
contract pages, images, PDFs, or pasted clauses and provides:

- OCR and clause reconstruction,
- contractual financial-risk review priorities,
- official-source evidence,
- financially relevant clause explanations,
- low/base/high monetary exposure scenarios,
- time-exposure indicators,
- creator-specific questions before signing,
- uncertainty and human-review guidance.

The runtime must not require a remote LLM, cloud RAG, or external legal search.

# SOURCE AUTHORITY

Preserve this hard boundary:

A0 current law
A1 official standard contracts
A2 official guidance and cases
B educational law
C creator-practical material
M1/M2/M3 financial-AI method material
R0 course requirements
D0 generated drafts

Only A0-A2 may contribute authority-supported scoring evidence.

B and C may:

- explain,
- provide terminology,
- generate practical questions,
- inform synthetic cases.

B and C must never directly determine the final score.

M1-M3 are method sources, not legal evidence.

R0 is authoritative for course compliance.

# PRODUCT SEMANTICS

Never define the output as:

- fraud probability,
- illegality probability,
- contract validity,
- legal conclusion,
- guaranteed loss.

The primary score must be named:

Contractual Financial Review Priority Score

Korean:

계약상 금융 검토 우선도

The report must display four independent dimensions:

1. Review Priority Score, 0-100
2. Monetary Exposure Range, low/base/high
3. Time Exposure
4. Evidence and OCR Confidence

Do not collapse all four into one number.

# REQUIRED FINANCIAL-IMPACT MODULES

Define formulas, assumptions, input fields, missing-data behavior,
unit tests, and uncertainty behavior for all modules.

## 1. Revenue-base and deduction leakage

Estimate the creator payout difference caused by alternative interpretations
of gross sales, net sales, refunds, platform fees, marketing costs,
payment-processing fees, and open-ended deductions.

At minimum define:

net_sales =
gross_sales
- refunds
- explicitly_allowed_deductions

creator_payout =
fixed_fee
+ revenue_share_rate * max(net_sales, 0)
- advance_recoupment

Show low/base/high assumptions rather than one certain value.

## 2. Payment-delay present-value loss

Define:

delay_pv_loss =
delayed_amount * (
  1 - 1 / (1 + annual_discount_rate) ** (delay_days / 365)
)

Keep nominal unpaid amount and time-value loss separate.

## 3. MG and advance recoupment

Estimate:

- recoupment balance,
- monthly recoupment,
- months to recoup,
- payout deferral under low/base/high sales.

## 4. Unpaid additional-work cost

Estimate:

unpaid_work_cost =
unpaid_revision_units
* hours_per_unit
* creator_hourly_value

All three inputs must be user-editable.

## 5. Exclusivity and renewal opportunity cost

Estimate scenario-based opportunity cost from:

- exclusivity duration,
- automatic renewal,
- alternative monthly revenue,
- probability or scenario assumptions,
- discount rate.

Never present opportunity cost as observed loss without user inputs.

## 6. IP and secondary-rights scenario value

Support:

- translation,
- overseas distribution,
- adaptation,
- game,
- merchandise,
- other secondary rights.

This must be a user-supplied scenario model.
Do not automatically value IP from contract text alone.

## 7. Penalty and liability exposure

Display:

- explicit capped amount,
- uncapped or ambiguous exposure signal,
- low/base/high scenario range only when user assumptions exist.

Do not compute expected loss without an explicit probability input.

## 8. Evidence-opacity uncertainty

When settlement records, deduction definitions, audit access, or numeric terms
are missing, increase uncertainty, not the monetary amount itself.

# REQUIRED TIME EXPOSURE

Define separate fields for:

- payment_due_days
- payment_delay_days
- contract_duration_months
- renewal_duration_months
- exclusivity_duration_months
- termination_notice_days
- estimated_months_to_recoup
- measured_analysis_runtime_seconds
- estimated_human_review_minutes

The human-review estimate may use transparent heuristics based on:

- page count,
- OCR corrections required,
- number of flagged clauses,
- number of missing financial inputs.

Do not estimate court duration, negotiation completion, or legal outcome time
as a precise number. Use a label such as:

- clarification likely sufficient
- negotiation required
- professional review required
- dispute pathway may be required

# SCORING SPECIFICATION

Specify:

- clause-level risk signals,
- document-level aggregation,
- category scores,
- missing-protection signals,
- authority-supported comparison,
- OCR/data-quality penalties,
- confidence,
- calibration plan,
- threshold-selection plan,
- ablations.

The score must be configurable and testable.
Do not state unvalidated weights as scientifically established.

Require comparison of:

- rule-only
- local-model-only
- hybrid

Require benign-clause false-positive measurement.

Require a decision-focused evaluation showing whether the system helps users
prioritize financially consequential clauses, not only classify text.

# BILINGUAL REQUIREMENTS

Korean source evidence is primary.

Every canonical concept and output schema must support:

- canonical English ID
- preferred Korean label
- preferred English label
- Korean aliases
- English aliases

Korean and English queries must resolve to the same concept.

Generated English must never be presented as original evidence.

# LOCAL-FIRST ARCHITECTURE

Specify two runtime profiles.

## Desktop-local full profile

- responsive FastAPI web application
- phone camera upload through a mobile browser on the same trusted LAN
- local OCR
- local corpus/index
- local rule engine
- optional local LLM
- no remote runtime API
- temporary upload deletion
- network-offline integration test

## Mobile-local lite profile

Design-compatible future profile using:

- sanitized mobile knowledge pack
- on-device OCR
- deterministic rules and/or small ONNX classifier
- no private full corpus in the mobile package

The first implementation milestone may use desktop-local full inference with a
mobile-responsive frontend, but the data contracts must remain portable to the
mobile-local lite profile.

# DATA AND PRIVACY

Specify:

- source manifest
- authority tier
- score eligibility
- copyright/public-export fields
- provenance
- versioning
- frozen evaluation split
- private/public separation
- temporary uploads
- log redaction
- no contract text in access logs
- no long private-book excerpts in public artifacts.

# REQUIRED SCHEMAS

Define implementation-level schemas for:

- AnalysisRequest
- UploadedDocument
- OCRPage
- OCRSpan
- Clause
- ExtractedFinancialTerms
- EvidenceRecord
- RiskSignal
- ClauseAssessment
- FinancialScenarioInputs
- MonetaryExposureEstimate
- TimeExposure
- ConfidenceBreakdown
- DocumentAssessment
- AnalysisReport
- HumanCorrection
- EvaluationExample
- ExperimentResult

For each schema, specify:

- field name
- type
- nullability
- units
- validation
- provenance
- bilingual behavior
- privacy classification.

# USER EXPERIENCE

Specify responsive desktop/mobile flows for:

- camera capture
- image upload
- PDF upload
- pasted clause
- OCR preview and correction
- page reorder and rotation
- overall score
- risk-category cards
- highlighted clause evidence
- official-source comparison
- monetary low/base/high scenarios
- time exposure
- editable assumptions
- questions before signing
- exportable local report
- privacy and legal disclaimers.

# EVALUATION

Include:

- OCR CER and WER
- exact match for money, percentages, dates, and durations
- clause segmentation quality
- retrieval Recall@3 and Recall@5
- authority-tier correctness
- Korean-English query consistency
- risk Macro-F1
- benign false-positive rate
- severity error
- evidence-span overlap
- calibration
- score stability
- formula unit tests
- financial-scenario correctness
- measured latency
- peak memory
- offline-network failure test
- decision-focused financial utility
- human usability checklist.

# PAPER AND DELIVERABLE SYNC

The course requires a report containing:

- problem definition
- motivation
- proposed method
- data and implementation
- results
- discussion

The repository must continuously maintain Markdown notes for later ICML-format
paper conversion.

Specify synchronization rules for:

- docs/paper/00_abstract.md
- docs/paper/01_problem_and_motivation.md
- docs/paper/02_related_work.md
- docs/paper/03_method.md
- docs/paper/04_data_and_implementation.md
- docs/paper/05_experiments.md
- docs/paper/06_results.md
- docs/paper/07_discussion_and_limitations.md
- docs/paper/08_responsible_ai.md
- docs/paper/09_conclusion.md
- CLAIM_LEDGER.csv
- RESULT_LEDGER.csv
- FIGURE_REGISTRY.csv
- docs/ai-use-log.md

The ICML template under paper/template/icml2026 must remain untouched.

# OUTPUTS

Create all files below.

1. docs/FINK_MASTER_SPEC.md
2. docs/specs/01_PRODUCT_REQUIREMENTS.md
3. docs/specs/02_DATA_AND_SCHEMA_SPEC.md
4. docs/specs/03_SCORING_AND_FINANCIAL_IMPACT.md
5. docs/specs/04_LOCAL_RUNTIME_AND_PRIVACY.md
6. docs/specs/05_EVALUATION_AND_DECISION_FOCUSED_METRICS.md
7. docs/specs/06_UI_UX_RESPONSIVE_WEB.md
8. docs/specs/07_PAPER_PROJECT_PAGE_AND_DELIVERABLE_SYNC.md
9. docs/specs/08_IMPLEMENTATION_BACKLOG.yaml
10. docs/specs/09_ACCEPTANCE_CHECKLIST.md
11. docs/specs/10_TRACEABILITY_MATRIX.csv
12. docs/specs/11_ASSUMPTIONS_OPEN_QUESTIONS.md
13. docs/specs/SPEC_BUILD_REPORT.md

The backlog must contain:

- stable task IDs
- phase
- priority
- dependencies
- estimated scope
- allowed paths
- acceptance criteria
- machine gates
- paper sections to update
- human gate requirement
- implementation status

Plan phases:

S0 foundation and data validation
S1 ingestion and OCR
S2 retrieval and authority grounding
S3 scoring and monetary/time exposure
S4 responsive local web application
S5 evaluation
S6 project page
S7 paper synchronization
S8 final privacy, copyright, and release audit

# QUALITY

The specification is not complete unless it contains:

- explicit non-goals
- MVP versus stretch scope
- typed schemas
- formulas and units
- missing-data behavior
- confidence behavior
- bilingual behavior
- privacy boundary
- public/private data boundary
- objective acceptance tests
- failure modes
- human approval points
- requirement-to-task traceability
- paper-claim traceability.

At the end of SPEC_BUILD_REPORT.md, write:

SPEC_BUILD_STATUS: READY_FOR_AUDIT

Stop after writing the specification.

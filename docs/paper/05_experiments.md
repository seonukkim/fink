# Experiments

## Course Mapping

This note supports the course report's results part together with
`06_results.md` (`CLM-S7-MAP-RESULTS`).

## Experimental Suites

The paper uses the measured synthetic/sanitized S5 suites below:

- OCR, financial-term extraction, and clause segmentation
  (`ocr_extract_metric_run`).
- Retrieval, authority grounding, span overlap, and KO/EN canonical consistency
  (`retrieval_metric_run`).
- Risk-signal ablation arms over identical synthetic labels
  (`risk_metric_run`, `ablation_three_arms`; `CLM-S7-EXP-ABLATION-ARMS`).
- Formula and financial-scenario unit checks (`formula_unit_suite`).
- Offline, privacy-redaction, latency, and memory runtime gates
  (`runtime_gate_suite`).
- Production-path factorial review-priority experiment (`production_path_factorial_experiment`):
  authority gate off/on crossed with severity-baseline/exposure-aware ranking,
  with every arm using the same local analysis, scoring, ranking, and FIM
  engines on the same frozen synthetic fixtures.

## FINK-EXP-01 Factorial Design

The FINK-EXP-01 suite replaces hand-authored prediction tables with a frozen
synthetic corpus under `data/eval/fink_exp_01/` and the result artifact
`scripts/eval/fink_exp_01_factorial_results.json`. The production fixture file
contains only rendered synthetic text, OCR-mode metadata where applicable, and
synthetic scenario assumptions. Hidden oracle rows are stored separately and are
used only after production outputs are produced.

The corpus is synthetic-only and contains paired benign and counterfactual
documents across FIM-1..8, Korean-canonical and bilingual renderings,
noisy-OCR-style inputs, missing-input cases, unbounded-liability cases, and
officially supported versus unsupported authority paths. No real contract,
private input, PDF, ZIP, token, or model weight is part of the suite.

Primary metrics are Oracle Exposure Capture at top-one and top-three, Benign
Scored-Warning Rate, and Unsupported Scored-Finding Rate. Oracle Exposure
Capture uses hidden oracle exposure weights, never predicted exposure values,
and is computed within exposure type before macro-averaging. The artifact also
records confidence intervals, denominators, raw per-document rows, fixture and
config hashes, measured extrema, and actual failure-analysis cases. The paper
does not claim any arm is superior beyond the measured synthetic-only rows; when
a baseline arm shares or wins a measured metric, the artifact records that fact.

## Reporting Rule

Every numeric or evaluative result reported from these suites must be copied
from `RESULT_LEDGER.csv` and cited through a claim id. Unrun or stretch metrics
remain out of the results text until a measured row exists.

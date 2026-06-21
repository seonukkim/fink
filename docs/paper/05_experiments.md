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

## Reporting Rule

Every numeric or evaluative result reported from these suites must be copied
from `RESULT_LEDGER.csv` and cited through a claim id. Unrun or stretch metrics
remain out of the results text until a measured row exists.

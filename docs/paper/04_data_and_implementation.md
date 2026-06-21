# Data and Implementation

## Course Mapping

This note covers the data and implementation part of the course report
(`CLM-S7-MAP-DATA`).

## Public Data Boundary

Paper-visible evaluation artifacts are synthetic or sanitized. The notes,
ledgers, and project page must not include real contracts, uploaded PDFs,
private-book text, private corpus passages, raw filenames, token values, model
weights, ZIPs, or unsanitized data (`CLM-S7-PRIVACY-BOUNDARY`).

## Local Implementation Boundary

The implementation is described as local-first: ingestion, PDF handling, OCR,
retrieval, scoring, and report construction are specified to avoid remote
runtime services. Runtime measurements are reported only from the local
synthetic gate artifacts (`CLM-S7-RES-EV-OFFLINE`,
`CLM-S7-RES-EV-PRIV`, `CLM-S7-RES-EV-LAT`, `CLM-S7-RES-EV-MEM`).

## Evaluation Artifacts

The measured result ledger is sourced from the S5 JSON artifacts under
`scripts/eval/`. Those artifacts provide the paper's only quantitative values
for OCR/extraction/segmentation, retrieval/grounding, risk ablations, formula
checks, and runtime/privacy gates.

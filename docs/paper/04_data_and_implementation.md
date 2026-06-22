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

For image and scanned-PDF uploads, the optional PaddleOCR-VL path remains an
on-device runtime path: startup/inference logging is quieted, the local pipeline
is reused across requests, and user-facing OCR failures are presented as short
retry guidance rather than technical logs. This is a usability/privacy boundary
note only and does not add a new OCR accuracy claim.

The chat demo UI follows the same local-first boundary. The browser shell keeps
request code confined to the local app script, presents review output as
Contractual Financial Review Priority decision support, and generates the
creator-facing review brief through the browser print dialog instead of a remote
document service or Markdown download. The three-step visual indicator denotes
review effort only (`가볍게 확인`, `꼼꼼히 확인`, `전문가 확인 권장`) and is not a
legal, safety, validity, unfairness, or guaranteed-loss verdict.

Model-profile records are implementation metadata unless a private local
installation passes the offline health/smoke gate in the current environment.
No public paper section should claim an active model from metadata, shortlist,
or dry-run records alone.

## Evaluation Artifacts

The measured result ledger is sourced from the S5 JSON artifacts under
`scripts/eval/`. Those artifacts provide the paper's only quantitative values
for OCR/extraction/segmentation, retrieval/grounding, risk ablations, formula
checks, and runtime/privacy gates.

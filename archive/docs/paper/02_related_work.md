# Related Work

## Course Mapping

This note supports the proposed-method section by positioning FInk against
official-source grounding, local OCR/retrieval, and decision-focused evaluation
context (`CLM-S7-MAP-METHOD`).

## Grounded Contract Review

FInk's review-priority framing depends on separating official grounding from
practice references. A0-A2 official records can ground score-eligible financial
signals, while B/C material is limited to explanation, terminology, questions,
and synthetic case design (`CLM-S7-AUTHORITY-GATE`).

## Local-First Document AI

The related-work discussion should emphasize the local processing boundary:
OCR, retrieval, scoring, and report generation are specified to avoid remote
LLMs, cloud retrieval, external legal search, telemetry, and cloud OCR at
runtime (`CLM-S7-PRIVACY-BOUNDARY`).

## Decision-Focused Evaluation

The paper may describe the contribution as DFL-inspired because the evaluation
uses decision-relevant review-priority metrics and ablations. It must not claim
the system was trained end-to-end with decision-focused learning
(`CLM-S7-METHOD-DFL`).

Citation details and acknowledgements should stay in `CITATION_NOTES.md`.

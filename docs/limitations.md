# FInk Limitations

FInk is a selective, evidence-gated cash-flow triage aid for creator contracts.
It reports Contractual Financial Review Priority, monetary exposure ranges, time
exposure, and evidence/OCR confidence. It is not a lawyer or legal verdict
engine, and it must not present fraud probability, illegality probability,
contract validity, unfairness, guaranteed loss, or legal conclusions.

Current limitations:

- The system runs in conservative mode (HD-12): it never asserts current law,
  fraud, illegality, contract validity, voidness, unfairness, or guaranteed loss.
  Current-law and webtoon-specific grounding are not certified, so outputs stay
  review-priority signals over A0-A2 evidence, never authoritative legal
  conclusions.
- Evidence is UNVERIFIED and date-stamped; dated 2018-2021 figures are shown with
  their date and never presented as current.
- Korean is canonical; English aliases are never labeled evidence.
- Scoring weights are heuristic and must be sensitivity-analyzed before any
  result claim.
- Evaluation results must be measured on synthetic or sanitized data and cannot
  be generalized as established performance, real-contract behavior, predicted
  exposure-value, or deployment behavior.
- Public model records are optional candidate/profile metadata unless the
  corresponding private local installation passes the offline health check in
  the current environment.
- HR-08 (the author's attestation that AI-assisted outputs were reviewed) is the
  single remaining human step before release.

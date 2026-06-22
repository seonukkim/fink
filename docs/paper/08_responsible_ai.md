# Responsible AI

FInk is framed as a local-first, selective, evidence-gated cash-flow triage
system for creator contracts. It reports Contractual Financial Review Priority,
not legal advice or a fraud, legality, validity, unfairness, or guaranteed-loss
verdict. Its output separates review priority, monetary exposure range, time
exposure, and evidence/OCR confidence so that no single number is presented as a
definitive conclusion (`CLM-S7-FRAME-REVIEW`).

Authority gating is a hard boundary. Only A0-A2 official records may ground a
score-eligible signal; B/C practice references can explain terms and motivate
questions, but contribute zero scoring evidence. Method sources and course
requirements are never treated as legal evidence. Korean source text remains
canonical, while English labels and aliases are generated aids with non-
equivalence caveats, not original evidence (`CLM-S7-AUTHORITY-GATE`).

Uncertainty is handled by widening uncertainty and lowering confidence, not by
inflating the review-priority score or inventing financial values. Missing,
opaque, or low-confidence inputs stay null or require user-editable assumptions;
low/base/high ranges are used where a single monetary value would imply false
precision. A0-gated source-currency and dated-figure statements remain
conservative and date-stamped under the human-gate disposition
(`CLM-S8-HR-DISPOSITION`).

The privacy posture is local-first. Runtime analysis must not require a remote
LLM, cloud RAG, cloud OCR, telemetry, external legal search, or runtime model
download. User contracts, uploads, OCR text, raw filenames, temporary paths,
private corpus content, tokens, model weights, PDFs, ZIPs, and unsanitized data
are excluded from public artifacts (`CLM-S7-PRIVACY-BOUNDARY`).

Evaluation and paper results are limited to synthetic or sanitized fixtures.
They support implementation sanity checks and decision-focused reporting, but
they are not generalized deployment-performance claims. Scoring weights,
thresholds, bands, and any model weights remain design heuristics unless future
work validates them; this paper therefore uses DFL-inspired wording and does not
claim end-to-end decision-focused training or validated financial-loss
prediction (`CLM-S7-RESULT-SCOPE`, `CLM-S7-METHOD-DFL`).

FINK-EXP-01 and FINK-COST-01 keep the same boundary. Oracle fixture weights and
fixture-derived review costs are evaluation labels, not predicted exposure-value,
real-loss, legal-damage, or real-performance claims. Optional local model
profiles remain metadata unless privately installed weights pass the offline
health check; the model layer may explain retrieved records only and must not
create evidence or set review-priority values.

The FINK-S7-03 gate snapshot records HR-08 as a human academic-integrity
attestation: the author, not the system, is responsible for personally reviewing
AI-assisted outputs before release. This note records that human gate state and
does not auto-attest on the author's behalf (`CLM-S8-HR-DISPOSITION`).

# Method

## Course Mapping

This note covers the proposed-method part of the course report, with
`02_related_work.md` as supporting context (`CLM-S7-MAP-METHOD`).

## Review-Priority Frame

FInk's method is organized around selective, evidence-gated cash-flow triage and
Contractual Financial Review Priority (`CLM-S7-FRAME-REVIEW`). The report first
highlights contract wording that may affect settlement, deductions, recoupment,
payment timing, IP revenue, exclusivity, termination exposure, or production
costs. It then keeps four dimensions separate: review priority, low/base/high
monetary exposure, time exposure, and evidence/OCR confidence. The method should
not collapse those dimensions into a single financial verdict.

## Authority-Gated Signals

The scoring path keeps A0-A2 official grounding separate from B/C practice
references (`CLM-S7-AUTHORITY-GATE`). Signals without A0-A2 grounding can still
support explanation and user questions, but they do not contribute scoring
evidence.

FInk reports this boundary as a transparent two-tier support indicator
(`CLM-S7-AUTHORITY-GATE`, `CLM-S7-FRAME-REVIEW`): the review-attention score
remains A0-A2-only, while a separately labeled practice-informed support count
records B/C practice references or distilled checkpoint coverage. The
practice-informed count strengthens explanation and question selection, but it
does not replace the evidence-gated score and is never a legal, fraud,
validity, unfairness, safety, or guaranteed-loss verdict.

Korean source text remains canonical. English aliases are retrieval and UX aids
with non-equivalence caveats, not independent evidence or legal-equivalence
claims.

## Financial Modules

Financial-impact modules are reported as scenario-specific exposure types:
nominal leakage, present-value loss, deferral, opportunity cost, liability
exposure, and uncertainty widening. The formula checks in the result ledger
cover the registered unit and scenario cases without claiming that heuristic
weights are scientifically validated (`CLM-S7-RES-EV-UNIT`,
`CLM-S7-RES-EV-FINSCEN`).

The production-path factorial suite uses hidden oracle fixture weights only for
evaluation. It is not a predicted exposure-value estimator, and it does not
claim real financial loss, A0 verification status, or generalized performance.

## DFL-Inspired Evaluation

The method language is DFL-inspired: metrics and ablations are chosen to reflect
financial review-priority decisions, but no paper section should claim
end-to-end decision-focused training (`CLM-S7-METHOD-DFL`).

Optional local model profiles are described as metadata or when-installed
components only. The paper should not describe a model as active unless private
local weights are outside Git and the current environment passes the offline
health/smoke gate.

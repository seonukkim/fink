# Method

## Course Mapping

This note covers the proposed-method part of the course report, with
`02_related_work.md` as supporting context (`CLM-S7-MAP-METHOD`).

## Review-Priority Frame

FInk's method is organized around Contractual Financial Review Priority
(`CLM-S7-FRAME-REVIEW`). The report keeps four dimensions separate: review
priority, low/base/high monetary exposure, time exposure, and evidence/OCR
confidence. The method should not collapse those dimensions into a single
financial verdict.

## Authority-Gated Signals

The scoring path keeps A0-A2 official grounding separate from B/C practice
references (`CLM-S7-AUTHORITY-GATE`). Signals without A0-A2 grounding can still
support explanation and user questions, but they do not contribute scoring
evidence.

## Financial Modules

Financial-impact modules are reported as scenario-specific exposure types:
nominal leakage, present-value loss, deferral, opportunity cost, liability
exposure, and uncertainty widening. The formula checks in the result ledger
cover the registered unit and scenario cases without claiming that heuristic
weights are scientifically validated (`CLM-S7-RES-EV-UNIT`,
`CLM-S7-RES-EV-FINSCEN`).

## DFL-Inspired Evaluation

The method language is DFL-inspired: metrics and ablations are chosen to reflect
financial review-priority decisions, but no paper section should claim
end-to-end decision-focused training (`CLM-S7-METHOD-DFL`).

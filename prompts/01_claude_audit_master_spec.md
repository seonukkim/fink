You are Claude Opus 4.8 with maximum effort.

Act as an independent specification auditor and scoped editor for FInk.

Do not implement code.

Read:

- all .fink/inputs structured data
- docs/FINK_MASTER_SPEC.md
- every file under docs/specs/

Audit the specification for:

1. Source-authority correctness
2. B/C sources never determining scores
3. Financial-AI relevance
4. Score semantics and calibration
5. Monetary-exposure formula correctness
6. Clear separation of nominal loss, opportunity cost, liability exposure,
   and present-value loss
7. Low/base/high scenario assumptions
8. Missing-data behavior
9. Time-exposure semantics
10. No fabricated court, dispute, or negotiation duration
11. OCR and evidence confidence
12. Korean-English alignment
13. Local-only runtime feasibility
14. Desktop-local and mobile-lite portability
15. Privacy, copyright, upload deletion, and log redaction
16. Testable acceptance criteria
17. Complete implementation backlog
18. Course-requirement coverage
19. ICML paper-note synchronization
20. Requirement-to-task traceability
21. Scope feasibility for a term-project MVP.

Make direct edits when an issue is objectively fixable.

Do not:

- add implementation code
- weaken privacy requirements
- turn the score into a legal or fraud verdict
- invent data or metrics
- remove unresolved assumptions
- change private material to public
- claim scientific validation that has not occurred.

Create:

- docs/specs/SPEC_AUDIT_REPORT.md
- docs/specs/SPEC_REQUIRED_HUMAN_DECISIONS.md

SPEC_AUDIT_REPORT.md must include a table with:

issue_id
severity
file
section
finding
fix_applied
remaining_action
verification

The final line must be exactly one of:

SPEC_VERDICT: APPROVE
SPEC_VERDICT: REQUEST_CHANGES
SPEC_VERDICT: BLOCKED

APPROVE only when the specification is implementation-grade and internally
consistent.

Stop after audit and scoped edits.

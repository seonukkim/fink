You are Claude Opus 4.8 with maximum effort.

Perform a new independent audit of the completed FInk specification.

Read all `.fink/inputs`, `docs/FINK_MASTER_SPEC.md`, every file under
`docs/specs/`, and `HUMAN_DECISION_RESOLUTIONS.md`.

Do not implement code.

Independently verify:

1. all required spec files exist;
2. every AC/AQ/task/metric reference resolves;
3. traceability covers every MVP requirement;
4. Stage 0–3 actual inputs were reconciled;
5. PDF upload is a **mandatory MVP input**;
6. text-layer, scanned, mixed, and multi-page PDFs are specified;
7. local parsing/OCR/page operations are specified;
8. encrypted/corrupt/oversized behavior is specified;
9. uploaded PDF bytes, rasters, and OCR intermediates are deleted;
10. raw filename and contract text never enter logs;
11. PDF analysis works with no outbound network access;
12. `*.pdf` Git exclusion is not mistaken for removal of PDF product support;
13. the binding deadline is exactly **2026-06-24 23:59 KST** everywhere;
14. B/C sources never affect score;
15. review priority is not a legal/fraud verdict;
16. uncertainty never invents money or inflates the score;
17. exposure types remain separate;
18. Korean is canonical and English is generated alias/explanation;
19. open legal/currentness/release gates remain open;
20. implementation is feasible for the stated deadline and MVP.

You may directly fix objective documentation defects.

Update:

- `docs/specs/SPEC_AUDIT_REPORT.md`
- `docs/specs/SPEC_REQUIRED_HUMAN_DECISIONS.md`
- any objectively broken cross-reference

Create:

- `docs/specs/SPEC_REAUDIT_CHANGELOG.md`

The final line of `SPEC_AUDIT_REPORT.md` must be exactly one of:

- `SPEC_VERDICT: APPROVE`
- `SPEC_VERDICT: REQUEST_CHANGES`
- `SPEC_VERDICT: BLOCKED`

Stop after audit and scoped documentation fixes.

# SPEC_REAUDIT_CHANGELOG — FInk

**Pass:** 2 (independent re-audit) · **Date:** 2026-06-21
**Auditor role:** independent specification auditor + scoped editor (no application code).
**Result:** `SPEC_VERDICT: APPROVE` (see `docs/specs/SPEC_AUDIT_REPORT.md`, final line).

This changelog records every change the Pass-2 re-audit made. All edits are
documentation-only, truthful, and invariant-preserving: nothing was removed, made
public, re-characterized as a different score, or invented. The substantive specs
(master + 01–11) were **not** rewritten; only the objective defects below were
corrected and the audit/decision records were brought to current status.

---

## 1. What Pass 2 verified (no change needed)

- **All required files present** — master + `docs/specs/01–11` + `SPEC_BUILD_REPORT.md`
  + `SPEC_COMPLETION_REPORT.md` + `HUMAN_DECISION_RESOLUTIONS.md`
  + `SPEC_REQUIRED_HUMAN_DECISIONS.md`. The four files Pass 1 flagged as missing
  (`09`, `10`, `11`, `SPEC_BUILD_REPORT.md`) now exist (closes Pass-1 C1–C5/H1).
- **Cross-references resolve** — every `AC-*`→spec 09; `AQ-01/02/03`→spec 11;
  `FINK-S*`→spec 08; `DR-1…16`→`24_FUTURE_DELIVERABLE_DATA_REQUIREMENTS.md`;
  `G-12/14/15`→upstream `30_DATA_GAPS…`; PASS-gates→upstream `31_PREPROCESSING_QA_REPORT.md`.
- **Counts reconcile to source files** — 35 sources; 156 glossary terms (all
  `generated_translation=true`, `score_eligible=false`); 64 cards; 52 checklist;
  20 evidence (A1/A2, all `UNVERIFIED`); 29+3 features; 9F+5X taxonomy with
  canonical IDs; DR-1…DR-16; 11 metrics.
- **Unit tests** — FIM-1-T1…FIM-8-T1 and the aggregation/separation tests
  re-derived arithmetically; all correct.
- **Invariants** — INV-1…INV-9 specified testably and preserved in the actual
  data (B/C never score; review-priority-not-verdict; no invented numbers;
  uncertainty widens bands around an unchanged base; exposure types separate; KO
  canonical / EN generated alias; local-first/offline; privacy/copyright;
  no-unvalidated-claims).
- **Deadline** — `2026-06-24 23:59 KST` consistent across all live specs.
- **Open gates** — HR-01/02/03/04/05/06/08 OPEN by design; HR-07 RESOLVED (HD-3).

---

## 2. Defects found and fixed (objective, scoped)

### R1 — `EvidenceRecord` schema vs. evidence data · MEDIUM · FIXED
**File:** `docs/specs/02_DATA_AND_SCHEMA_SPEC.md` §4.7.
**Defect:** the field was typed `risk_category | enum{F1..F9}` (singular, F-only),
but the upstream `14_MASTER_EVIDENCE_MATRIX.csv` it mirrors uses a plural
`risk_categories` **list** that carries cross-cutting **X** tags on 3 of 20 A1/A2
records (`EV-A1-ASSIGNFULL-05`→X2, `EV-A2-2024-COMICS`→F3;X2, `EV-A2-2024-STATS`→X1).
A loader honoring the old schema could not represent those records. No invariant
was breached (scoring aggregates F1–F9 only), but Pass-1's "EvidenceRecord is
F-only by schema" assumption was not true in the data.
**Fix:** changed the field to `risk_categories | list[enum{F1..F9,X1..X5}]` and
added a validation note: X-tagged official records may ground only **contextual,
non-scoring** display; scoring still aggregates F1–F9 signals only (INV-1). No
other spec referenced `EvidenceRecord.risk_category`, so the rename is safe.
**Recorded in:** `11_ASSUMPTIONS_OPEN_QUESTIONS.md` (L5 note + §5 data-fidelity note).

### R2 — Non-resolving metric shorthands in spec 01 · LOW · FIXED
**File:** `docs/specs/01_PRODUCT_REQUIREMENTS.md` §2.2.
**Defect:** PR-010 cited `EV-OCR` and PR-013 cited `EV-EXACT`, neither of which is
a row in the spec-05 metric registry (only suffixed members exist); PR-012/PR-013
also omitted the `AC-*` hooks that the traceability matrix already assigns them.
**Fix:** PR-010 → `EV-OCR-CER/WER`; PR-012 → adds `AC-SEG-1`; PR-013 → adds
`AC-EXTRACT-1` and `EV-EXACT-MONEY/PCT/DATE/DUR`. Every metric/acceptance token in
spec 01 now resolves to a definition.

---

## 3. Records brought to current status (housekeeping tied to the above)

### `docs/specs/SPEC_REQUIRED_HUMAN_DECISIONS.md` (updated)
- Added a Pass-2 status-sync header pointing to `11` / `HUMAN_DECISION_RESOLUTIONS.md`
  as authoritative.
- **HD-1, HD-2, HD-3, HD-11** marked **RESOLVED** (were OPEN at Pass 1).
- Normalized the deadline `June 24, 24:00` → **`2026-06-24 23:59 KST`** (HD-3).
- AQ-02 noted as a real, defined assumption in spec 11 (was "pinned to a
  nonexistent `AQ-02`").
- HD-4…HD-10 left **OPEN**; noted HD-8/HD-10 are P2 and do not gate release
  (`AC-REL-HR` gates P0/P1 only). Guardrails (§C) unchanged.

### `docs/specs/11_ASSUMPTIONS_OPEN_QUESTIONS.md` (updated)
- Supersession note updated: the re-audit edited `SPEC_AUDIT_REPORT.md` and
  `SPEC_REQUIRED_HUMAN_DECISIONS.md` (pre-Pass-2 content preserved as history).
- L5 extended with the Pass-2 data finding (evidence X-tags) tying to R1.
- §5 reconciliation: added a Pass-2 data-fidelity note for R1.

### `docs/specs/SPEC_AUDIT_REPORT.md` (updated)
- Added a top-of-file current-status pointer (`Pass 2: APPROVE`).
- Wrapped the original audit as "Pass 1 — original audit (historical)"; its
  closing verdict relabeled "Pass-1 verdict (historical — superseded)".
- Appended "Pass 2 — Independent re-audit" (method, the 20 engagement checks,
  findings R1–R3, scoped edits, verdict rationale).
- Final line is now `SPEC_VERDICT: APPROVE`.

---

## 4. Non-blocking observation (no edit)

- **R3** — Master §10 says the open HR items "map to human gates in spec 08," but
  the two **P2** items (HR-04 missing-source, HR-06 glossary spot-check) attach to
  no build-task gate. This is consistent with `AC-REL-HR` gating only **P0/P1** and
  with spec 11 tracking all items, so there is no correctness impact. Left for the
  build phase; no documentation change made.

---

## 5. Files changed by Pass 2

```
docs/specs/01_PRODUCT_REQUIREMENTS.md        (R2)
docs/specs/02_DATA_AND_SCHEMA_SPEC.md        (R1)
docs/specs/11_ASSUMPTIONS_OPEN_QUESTIONS.md  (R1 record + supersession/status)
docs/specs/SPEC_REQUIRED_HUMAN_DECISIONS.md  (status sync + deadline normalize)
docs/specs/SPEC_AUDIT_REPORT.md              (Pass-2 section + verdict)
docs/specs/SPEC_REAUDIT_CHANGELOG.md         (new — this file)
```

No application code was written. The substantive specification content (master +
specs 01–10 scoring/schema/metrics/backlog/traceability) is unchanged except the
two objective fixes R1 and R2.

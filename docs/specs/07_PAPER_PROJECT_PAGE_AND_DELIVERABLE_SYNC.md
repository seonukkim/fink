# 07 — Paper, Project Page, and Deliverable Synchronization

**Parent:** `docs/FINK_MASTER_SPEC.md` · **Spec version:** 1.0.0
Inherits INV-1…INV-9. Specifies how the repository continuously maintains
ICML-convertible paper notes, how claims/results/figures stay synchronized via
ledgers, the project page, and Term-Project (R0) compliance. **The ICML template
at `paper/template/icml2026/` must remain untouched** (read-only).

---

## 1. Course report ↔ paper-note mapping (R0)

The course requires six report parts. They map to the existing
`docs/paper/*` notes (already present in the repo):

| Course part | Paper note(s) |
|-------------|---------------|
| Problem definition | `docs/paper/01_problem_and_motivation.md` |
| Motivation | `docs/paper/01_problem_and_motivation.md` |
| Proposed method | `docs/paper/03_method.md` (+ `02_related_work.md`) |
| Data and implementation | `docs/paper/04_data_and_implementation.md` |
| Results | `docs/paper/06_results.md` (+ `05_experiments.md`) |
| Discussion | `docs/paper/07_discussion_and_limitations.md` |
| (supporting) | `00_abstract.md`, `08_responsible_ai.md`, `09_conclusion.md` |

`docs/paper/CITATION_NOTES.md` collects sources/acknowledgements. The
`paper/template/icml2026/` LaTeX template is the conversion target and is never
edited by FInk tooling.

---

## 2. Ledgers and the synchronization contract

Three ledgers already exist with fixed headers; FInk populates them:

- **`docs/paper/CLAIM_LEDGER.csv`** —
  `claim_id, section, claim_text, evidence_file, evidence_key, status, reviewer, notes`
- **`docs/paper/RESULT_LEDGER.csv`** —
  `result_id, experiment_id, metric, value, artifact_path, status, reviewer, notes`
- **`docs/paper/FIGURE_REGISTRY.csv`** —
  `figure_id, title, source_artifact, paper_section, site_section, status, notes`

**Sync rules (machine-checkable in S7):**
1. **No unsupported claim.** Every quantitative or evaluative claim in any
   `docs/paper/*` note must reference a `claim_id` in `CLAIM_LEDGER.csv`.
2. **Every result claim → a measured result.** A `CLAIM_LEDGER` row whose
   `section` is results/experiments must point (`evidence_file`/`evidence_key`)
   at a `RESULT_LEDGER.csv` row with `status=measured` and a real
   `artifact_path`. No `value` may be fabricated; unrun metrics are
   `status=planned` and may **not** be stated as results (INV-9).
3. **Every figure registered.** Each figure in a note or on the project page has
   a `FIGURE_REGISTRY.csv` row with a real `source_artifact`.
4. **Provenance & honesty.** Claims about official sources carry
   `verification_status`; no current-law claim until HR-01 is closed; "DFL-
   inspired" wording enforced (no "trained end-to-end DFL").
5. **Bilingual & privacy.** Notes never reproduce long private-book passages
   (B/C `public_export=false`) or long official excerpts; KO source vs EN gloss
   respected.
6. **Template untouched.** A gate asserts `paper/template/icml2026/` is
   byte-unchanged.

A `scripts/check_paper_sync` (S7 task) enforces rules 1–6 and fails CI on any
unsupported claim, fabricated value, orphan figure, or template modification.

---

## 3. Continuous maintenance workflow

- When an experiment produces a metric → append a `RESULT_LEDGER` row
  (`status=measured`, `artifact_path`) → update the relevant `docs/paper`
  note → add/update its `CLAIM_LEDGER` row → register any figure.
- When scope/assumptions change → update `07_discussion_and_limitations.md` and
  `08_responsible_ai.md`, and reflect open items from spec 11.
- Each phase (S0–S8) names the **paper sections to update** (spec 08 field
  `paper_sections`), so notes evolve continuously rather than at the end.

---

## 4. Responsible-AI and AI-use disclosure (R0; HR-08)

- `docs/paper/08_responsible_ai.md` documents: review-priority-not-verdict
  framing, authority gating, uncertainty handling, bilingual non-equivalence
  caveats, privacy/local-first posture, synthetic-data limits, and the no-
  validated-weights stance.
- **`docs/ai-use-log.md`** records AI assistance (including this preprocessing
  and spec build) and the author's human-verification attestations (R0). It is
  updated whenever AI tools materially contribute, and is a submission-gate item
  (HR-08).

---

## 5. Project page (S6)

- A **static** project-page scaffold (no runtime, no contract data) summarizing
  problem, method, four-dimension output, demo screenshots on **synthetic**
  contracts, and the metric table sourced from `RESULT_LEDGER`/`FIGURE_REGISTRY`.
- Public-safe only (`P0`): no real contracts, no private-book text, no long
  official excerpts, no keys. Figures come from `FIGURE_REGISTRY` (`site_section`).
- Disclaimers identical to the app (INV-2, not legal advice).

---

## 6. Term-Project compliance checklist (R0)

Mirrors upstream `23_TERM_PROJECT_COMPLIANCE_MAP`:
- Six report sections present and synced (§1).
- Seven evaluation criteria addressed via spec 05 metrics and the results note.
- AI-tool disclosure + human verification (`docs/ai-use-log.md`, HR-08).
- Citations/acknowledgements (`CITATION_NOTES.md`, `CITATION.cff`).
- Optional creative outputs (demo, project page) — allowed, public-safe only.
- Submission conditions: governing offering **2026 Spring IE412 AI for Finance**;
  binding deadline **2026-06-24 23:59 KST** (HR-07 resolved by owner HD-3,
  superseding the "2024 Spring" header / "2026spring" filename ambiguity).
- Pre-submission checklist run before release (S8): paper sync passes, privacy
  preflight `PREFLIGHT_OK`, template untouched, ledgers consistent, disclaimers
  present, HR P0/P1 items resolved or explicitly deferred-with-rationale.

---

## 7. Paper requirement IDs (traceability)

`PA-MAP` (§1 mapping), `PA-CLAIM` (claim ledger), `PA-RESULT` (result ledger),
`PA-FIG` (figure registry), `PA-SYNC` (sync checker), `PA-TEMPLATE` (untouched),
`PA-AIUSE` (ai-use log), `PA-SITE` (project page), `PA-COMPLY` (R0 checklist).
Acceptance: spec 09 (AC-PA-*). Tasks: spec 08 phases S6, S7.

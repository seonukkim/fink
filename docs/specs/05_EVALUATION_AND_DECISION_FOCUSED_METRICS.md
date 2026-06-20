# 05 — Evaluation and Decision-Focused Metrics

**Parent:** `docs/FINK_MASTER_SPEC.md` · **Spec version:** 1.0.0
Inherits INV-1…INV-9. Defines metrics, datasets (mapped to upstream data
requirements `DR-*`), ablations, the frozen split, and the decision-focused
utility study. **No result values are asserted here** — only definitions,
datasets, and reporting rules. All evaluation runs on **synthetic / sanitized
data**; results are labeled *measured-on-synthetic* and **not generalized**
(G-14, G-15, INV-9).

---

## 1. Datasets (synthetic-only; map to upstream `24_FUTURE_DELIVERABLE_DATA_REQUIREMENTS`)

| DR | Dataset | Used by metrics |
|----|---------|-----------------|
| DR-6 | Synthetic clause set with risk labels, severities, grounding spans, benign clauses | Recall@k, Macro-F1, benign-FPR, severity error, evidence-span overlap, authority-tier correctness |
| DR-7 | Camera/OCR stress set (synthetic pages, perturbations) + repeated-run set | OCR CER/WER, exact-match, segmentation, score stability |
| DR-8 | KO/EN paired query set | KO-EN query consistency |
| DR-11 | Decision-task set (clauses tagged "financially consequential") | decision-focused utility |
| DR-12 | Privacy probe set (logs/exports/network) | privacy-failure test |
| DR-13 | Latency/memory harness inputs | latency, peak memory |

`EvaluationExample` (schema 4.17) carries `split ∈ {dev, frozen_eval}`,
`is_synthetic=true`, `is_benign`, `gold`. The **frozen_eval** split is created
once, hashed, and never edited; tuning uses **dev** only (no leakage).

---

## 2. Metric registry

`report_mode = measured` means a number is computed and logged to
`RESULT_LEDGER.csv`; **no metric carries a pre-asserted value** (INV-9).

| metric_id | definition | dataset | arms | MVP? |
|-----------|------------|---------|------|:----:|
| EV-OCR-CER | character error rate vs gold | DR-7 | n/a | ✅ |
| EV-OCR-WER | word error rate vs gold | DR-7 | n/a | ✅ |
| EV-EXACT-MONEY | exact-match accuracy on extracted **money** values | DR-7/DR-6 | n/a | ✅ |
| EV-EXACT-PCT | exact-match on **percentages** | DR-7/DR-6 | n/a | ✅ |
| EV-EXACT-DATE | exact-match on **dates** | DR-7/DR-6 | n/a | ✅ |
| EV-EXACT-DUR | exact-match on **durations** | DR-7/DR-6 | n/a | ✅ |
| EV-SEG | clause-segmentation quality (boundary F1 / windowed) | DR-7 | n/a | ✅ |
| EV-R@3 | retrieval Recall@3 (correct grounding in top 3) | DR-6 | n/a | ✅ |
| EV-R@5 | retrieval Recall@5 | DR-6 | n/a | ✅ |
| EV-AUTH | authority-tier correctness (returned grounding has correct tier; B/C never score-eligible) | DR-6 | n/a | ✅ |
| EV-KOEN | KO–EN query consistency (KO and EN queries resolve to same `canonical_id` / same top-k) | DR-8 | n/a | ✅ |
| EV-F1 | risk **Macro-F1** over F1–F9 | DR-6 | rule/model/hybrid | ✅ |
| EV-BENIGN-FPR | benign false-positive rate (spec 03 §4) | DR-6 | rule/model/hybrid | ✅ |
| EV-SEV | severity error (MAE between predicted and gold severity) | DR-6 | rule/model/hybrid | ✅ |
| EV-SPAN | evidence-span overlap (IoU/token-overlap of cited vs gold span) | DR-6 | all | ✅ |
| EV-CALIB | calibration (rank agreement Spearman/Kendall; ECE if prob-like confidence) | DR-6 | all | Stretch |
| EV-STAB | score stability (variance of `review_priority_score` under OCR/run perturbations) | DR-7 | all | ✅ |
| EV-UNIT | formula **unit tests** pass (FIM-*-T*, SC-*-T*) | code | n/a | ✅ |
| EV-FINSCEN | financial-scenario correctness (module outputs match worked examples within tolerance) | code/DR-6 | n/a | ✅ |
| EV-LAT | measured end-to-end **latency** (median + p95) | DR-13 | all | ✅ |
| EV-MEM | measured **peak memory** | DR-13 | all | ✅ |
| EV-OFFLINE | offline-network failure test passes (RT-OFFLINE) | DR-12 | n/a | ✅ |
| EV-PRIV | privacy-failure test (no contract text/upload paths in logs/exports; no outbound calls) | DR-12 | n/a | ✅ |
| EV-DFU | **decision-focused financial utility** (§3) | DR-11 | rule/model/hybrid | core MVP variant; full study Stretch |
| EV-USAB | human usability checklist (§4) | manual | n/a | ✅ |

---

## 3. Decision-focused financial utility (EV-DFU, required)

Goal: show FInk helps users **prioritize financially consequential clauses**,
not merely classify text (IE412 A1 "decision-focused", DFL-**inspired**, G-12).

- **Gold:** DR-11 tags each clause as *financially consequential* (yes/no) and
  with a relative financial-impact rank (from the synthetic financial model).
- **Primary metric — Decision Precision@k:** of the top-k clauses FInk surfaces
  by `review_priority_score`, the fraction that are gold financially
  consequential (k ∈ {3,5}).
- **Ranking metric — financial-impact NDCG / rank correlation** between FInk's
  clause priority and the gold financial-impact rank.
- **Decision-regret (decision-aware):** with a simple synthetic "creator
  attention budget" of k clauses, compare realized covered financial impact when
  clauses are read in FInk order vs a baseline (document order / length).
  Report **regret reduction** vs baseline.
- **Re-ranking ablation:** decision-aware re-ranking ON vs OFF (DFL-inspired),
  measured on the same set. No end-to-end DFL training is claimed.

All EV-DFU numbers are *measured-on-synthetic* and reported with the baseline.

---

## 4. Human usability checklist (EV-USAB)

A short manual rubric (pass/fail per item), executed by a reviewer on the demo:
1. User can reach a four-dimension report from a phone capture in a bounded
   number of steps.
2. The score is presented as **review priority**, never a verdict (disclaimers
   visible).
3. Monetary low/base/high and exposure-type separation are legible.
4. Time exposure shows fields + pathway label, no fabricated durations.
5. Editable assumptions recompute live and are labeled synthetic.
6. Official grounding and "practice reference" badges are distinguishable.
7. KO is primary; EN is marked generated.
8. Export produces a local file; no network indicator fires.
9. Privacy/legal disclaimers are present and clear.
10. Missing inputs are shown as blanks to fill, never as guesses.

---

## 5. Ablations (required comparison)

Three arms on identical inputs and the frozen split:
- **rule_only** — deterministic rules + authority gate (MVP).
- **model_only** — small local ONNX classifier + authority gate.
- **hybrid** — rules ∪ model, documented merge.

Reported per arm: EV-F1, EV-BENIGN-FPR, EV-SEV, EV-SPAN, EV-DFU, EV-LAT,
EV-MEM (and EV-CALIB/EV-STAB where applicable). The report states which arm is
used in the shipped MVP (rule_only) and presents the comparison without claiming
statistical superiority beyond the measured synthetic result.

---

## 6. Reporting rules and ledgers

- Every measured value → a row in `docs/paper/RESULT_LEDGER.csv`
  (`result_id, experiment_id, metric, value, artifact_path, status, reviewer,
  notes`) with `status=measured` and a local `artifact_path`.
- Planned-but-unrun metrics → `status=planned` (never a fabricated value).
- Each results claim in the paper → `docs/paper/CLAIM_LEDGER.csv`
  (`claim_id, section, claim_text, evidence_file, evidence_key, status,
  reviewer, notes`) pointing at a `RESULT_LEDGER` row.
- Figures → `docs/paper/FIGURE_REGISTRY.csv`.
- Config + code revision pinned via `ExperimentResult.config_hash`.

---

## 7. Metric → coverage traceability (summary)

| Task / product area | metrics |
|---------------------|---------|
| OCR & extraction (PR-010/013) | EV-OCR-CER, EV-OCR-WER, EV-EXACT-* , EV-SEG |
| Retrieval & grounding (PR-020/023) | EV-R@3, EV-R@5, EV-AUTH, EV-KOEN, EV-SPAN |
| Scoring (spec 03) | EV-F1, EV-BENIGN-FPR, EV-SEV, EV-CALIB, EV-STAB |
| Financial modules (FIM-*) | EV-UNIT, EV-FINSCEN |
| Runtime/privacy (spec 04) | EV-LAT, EV-MEM, EV-OFFLINE, EV-PRIV |
| Decision value | EV-DFU |
| Usability | EV-USAB |

Full requirement-to-metric mapping in `docs/specs/10_TRACEABILITY_MATRIX.csv`;
the 11 upstream metric families (`22_DATASET_AND_EVALUATION_PLAN`) are all
covered, each with a planned dataset (PASS-gate 7).

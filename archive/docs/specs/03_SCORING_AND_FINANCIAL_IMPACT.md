# 03 — Scoring and Financial-Impact Specification

**Parent:** `docs/FINK_MASTER_SPEC.md` · **Spec version:** 1.0.0
Inherits INV-1…INV-9. Defines the Review-Priority scoring pipeline, the **8
financial-impact modules** (`FIM-1…FIM-8`), and **time exposure**. All weights,
thresholds, and band factors are **design heuristics in versioned config**
(`config/scoring_config.yaml`), never stated as validated (INV-9). All formulas
have unit tests with concrete expected values and tolerances.

---

## 1. Scoring pipeline overview

```
clauses → risk signals (rule | model | hybrid)
        → authority gate (A0–A2 grounding ⇒ score-eligible; B/C ⇒ practice-ref, 0)
        → clause category contributions
        → document category scores (F1–F9, bounded 0–100)
        → weighted document Review-Priority Score (0–100)
        → confidence (D4) carries OCR/data-quality penalty (separate dimension)
```

The Review-Priority Score is **ordinal/relative**, not a probability (INV-2).
The four dimensions are produced together and never merged (INV-3).

---

## 2. Clause-level risk signals

A `RiskSignal` (schema 4.8) fires from a `detector ∈ {rule, model, hybrid}`.
Two signal kinds:

- **Presence signals:** a risky term/structure is present (e.g., open-ended
  deduction `RS-F2-OPEN_DEDUCTION`, uncapped penalty `RS-F7-UNCAPPED_PENALTY`,
  IP assignment `RS-F5-IP_ASSIGNMENT`, auto-renewal `RS-F6-AUTO_RENEWAL`).
- **Missing-protection signals:** an expected protection is **absent** (e.g.,
  no settlement-statement clause `RS-F1-NO_STATEMENT`, no audit right
  `RS-F9-NO_AUDIT`, no late-payment interest `RS-F3-NO_LATE_INTEREST`). A
  missing-protection signal is **score-eligible only if an A0–A2 record
  establishes that the protection is expected**; otherwise it renders as a
  practice-reference question (score 0).

**Authority gate (INV-1, PASS-gate 1):**
```
signal.score_eligible = any(e.authority_tier in {A0,A1,A2}
                            for e in signal.grounding_evidence_ids)
if not signal.score_eligible:
    signal.practice_reference = True   # B/C support only
    contribution = 0                   # B/C never moves the score
```

**Effective contribution** of an eligible signal `s`:
```
authority_factor(s) = {A0:1.00, A1:0.90, A2:0.80}[max tier among grounding]   # heuristic, config
raw(s)       = severity_weight[category(s)] * severity_raw(s) * authority_factor(s)
conf_used(s) = clamp(signal_confidence(s), conf_floor, 1.0)                    # conf_floor=0.5 (config)
contribution(s) = raw(s) * conf_used(s)
```
`conf_floor` prevents poor OCR/extraction confidence from **hiding** a detected
risk (INV-7): low confidence cannot drive a real signal's contribution to 0; it
instead lowers **D4 confidence** and raises a "needs verification" flag. The
true (un-floored) confidence is what feeds `ConfidenceBreakdown`.

`severity_weight[category]`, `severity_raw` defaults, and `conf_floor` are in
`scoring_config.yaml` and are **heuristics to be sensitivity-analyzed** (INV-9,
spec 05 ablations).

---

## 3. Aggregation

**Category score (document level), bounded 0–100, saturating:**
```
S_F = 100 * (1 - exp( - (Σ_{s in F, eligible} contribution(s)) / k_F ))
```
`k_F` (config) sets saturation per category. Saturation keeps any single
category bounded and avoids a few signals dominating.

**Review-Priority Score (document level):**
```
review_priority_score = round( Σ_F w_F * S_F / Σ_F w_F )      # 0–100
```
`w_F` are per-category weights (config, heuristic). Financial-first weighting
(F1–F9 only; X1–X5 never contribute) is the default but is sensitivity-analyzed.

**Missing-protection contribution** uses the same machinery with its own
`severity_weight` and a grounding requirement (above).

**OCR / data-quality penalty (D4, not the priority):** the OCR/data-quality
penalty is applied to the **confidence dimension**, not subtracted from the
priority, so risk is never hidden:
```
data_completeness   = 1 - clamp(Σ missing_input_weight_k, 0, 1)
evidence_confidence = base_evidence_conf * unverified_factor * grounding_density
ocr_confidence      = mean(page_ocr_confidence)   # measured
overall_confidence  = ocr_confidence ** wo * evidence_confidence ** we * data_completeness ** wd   # weights config, Σ=1
```
`unverified_factor < 1` while evidence is `UNVERIFIED` (today: all records),
making low confidence the honest default until A0 verification (HR-01).

---

## 3A. Design rationale and references (why this formula)

The Review-Priority Score is a **bounded composite risk index**, not an ad-hoc
"under-100" clamp. Each layer follows an established risk- and decision-modeling
construct, which is what makes the number defensible from a financial-AI
standpoint. The constants remain versioned heuristics for sensitivity analysis
(INV-9); the **structure** below is the part that is principled.

### Why `severity × likelihood × evidence-credibility` per signal

`contribution(s) = severity_weight · severity_raw · authority_factor · conf_used`
is the classical **risk = consequence × likelihood** decomposition, extended with
an explicit **evidence-credibility** factor:

- **Consequence × likelihood** is the core of quantitative risk assessment
  (ISO 31000:2018; ISO/IEC 31010). `severity_raw` is the consequence magnitude;
  `conf_used` is the likelihood/strength that the risky pattern is really present.
- The product form mirrors the **FMEA Risk Priority Number** `RPN = S · O · D`
  (IEC 60812:2018), where our `authority_factor` plays the role of a
  detection/credibility weight: a flag grounded in a higher-authority source is
  more *trustworthy*, so it carries more weight (A0 = 1.00 > A1 = 0.90 >
  A2 = 0.80). B/C/D/M/R sources contribute **exactly 0** (INV-1 authority gate).
- Weighting evidence by source authority is the same idea as **evidence-grading
  systems** such as GRADE (Guyatt et al., 2008): conclusions inherit the quality
  of their evidence; non-authoritative material informs questions, not the score.
- `conf_floor = 0.5` encodes a **precautionary** stance: poor OCR/extraction
  confidence must not *hide* a detected exposure (the floor applies only to the
  contribution; the true confidence is surfaced separately in D4). Not letting
  measurement noise suppress a flagged financial risk is standard conservative
  risk practice.

### Why the saturating exponential `S_F = 100·(1 − e^(−ΣC/k_F))`

A category score must (a) be bounded and (b) reflect **diminishing marginal
risk** — the fifth weak red flag in one category adds less new decision-relevant
risk than the first. A concave, monotonic, saturating transform encodes exactly
this:

- It is the **exponential / bounded-utility** form (Pratt, 1964): a constant-rate
  approach to a ceiling. It maps the non-negative accumulation `ΣC ∈ [0, ∞)` into
  `[0, 100)` **by construction**, so no category can be dominated by sheer count
  of signals.
- `k_F` is the saturation scale: at `ΣC = k_F`, `S_F = 100·(1 − 1/e) ≈ 63.2`.
  This is the standard exponential-CDF characteristic scale and is the knob the
  sensitivity analysis (spec 05) varies.

### Why the normalized weighted sum `P = Σ w_F·S_F / Σ w_F`

Combining the nine category scores into one priority is a **multi-criteria
decision-analysis (MCDA)** aggregation:

- It is **Simple Additive Weighting / the weighted-sum model** (Fishburn, 1967)
  under **multi-attribute utility theory** (Keeney & Raiffa, 1976) — the most
  widely used, most transparent MCDA aggregator, and the standard backbone of
  composite financial scorecards.
- Dividing by `Σ w_F` makes `P` a **convex combination** of the `S_F`, so `P`
  inherits their `[0, 100]` range. Financial-first weighting (F1–F9 only; the
  non-financial X-dimensions never contribute) is the default but is itself
  sensitivity-analyzed.

### Bound guarantee — why `P` can never exceed 100

This is structural, not a clamp:

1. For each category, `ΣC ≥ 0` and `k_F > 0` ⇒ `e^(−ΣC/k_F) ∈ (0, 1]` ⇒
   `S_F = 100·(1 − e^(−ΣC/k_F)) ∈ [0, 100)`.
2. `P = (Σ w_F·S_F) / (Σ w_F)` with `w_F ≥ 0` and `Σ w_F > 0` is a convex
   combination of the `S_F`, so `min_F S_F ≤ P ≤ max_F S_F < 100`.
3. Therefore `P ∈ [0, 100)` before the final `round`+clamp, i.e. `P ∈ {0,…,100}`
   — **independent of the number or severity of signals**. The `SC-AGG-T2`
   self-test and `test_sc_agg_t2_scores_are_bounded_with_saturation` confirm this
   empirically with 500 maximum-severity A0 signals. The engine additionally
   guards the two degenerate-config cases (`k_F ≤ 0`, `Σ w_F ≤ 0`), covered by
   `test_saturating_score_and_priority_stay_bounded_under_degenerate_config`, so
   the bound holds even under a malformed config.

### What is deliberately *not* claimed (financial-AI honesty)

- `P` is **ordinal / relative review-priority**, not a probability of fraud,
  loss, or invalidity (INV-2). It ranks "look here first," nothing more.
- Only **A0–A2** authoritative grounding can move the score; the system is
  conservative by construction and cannot inflate risk from non-authoritative
  sources.
- Every weight, factor, and threshold is a **versioned design heuristic**
  (INV-9), disclosed in `config/scoring_config.yaml` and subject to the spec-05
  sensitivity analysis — never presented as an empirically validated constant.

### References

- ISO 31000:2018 — *Risk management — Guidelines.*
- ISO/IEC 31010:2019 — *Risk management — Risk assessment techniques.*
- IEC 60812:2018 — *Failure modes and effects analysis (FMEA/FMECA)* (Risk
  Priority Number = Severity × Occurrence × Detection).
- Pratt, J. W. (1964). "Risk Aversion in the Small and in the Large."
  *Econometrica* 32(1/2), 122–136. (exponential / bounded utility)
- Keeney, R. L., & Raiffa, H. (1976). *Decisions with Multiple Objectives:
  Preferences and Value Tradeoffs.* Wiley. (multi-attribute utility theory)
- Fishburn, P. C. (1967). "Additive Utilities with Incomplete Product Sets."
  *Operations Research* 15(3), 537–542. (simple additive weighting)
- Guyatt, G. H., et al. (2008). "GRADE: an emerging consensus on rating quality
  of evidence and strength of recommendations." *BMJ* 336, 924–926. (evidence
  grading → authority-tier weighting)

---

## 4. Calibration, thresholds, ablations (plan; results in spec 05)

- **Calibration plan.** The priority is ordinal, so calibration is reported two
  ways on the **frozen synthetic split** only, labeled *measured-on-synthetic*:
  (a) **rank agreement** (Spearman/Kendall) between FInk priority and a human
  "review-priority" rating of synthetic clauses; (b) if a probability-like
  confidence is exposed, a **reliability diagram + ECE** on benign-vs-risky
  synthetic examples. No calibration claim is generalized beyond synthetic data
  (G-14, INV-9).
- **Threshold-selection plan.** Attention bands (e.g., *low / medium / high
  review priority*) are chosen by maximizing **decision-focused utility**
  (spec 05) on the `dev` split, then **frozen**; benign-FPR at the chosen
  threshold is reported on the frozen split. Thresholds live in config.
- **Ablations (required).** Three arms on identical inputs:
  `rule_only`, `model_only` (small local ONNX classifier), `hybrid`. Compare
  risk Macro-F1, benign-FPR, evidence-span overlap, decision-focused utility,
  latency, peak memory. Report all three; declare no arm "optimal" without the
  measured comparison.
- **Benign false-positive measurement (required).** On `is_benign` synthetic
  clauses, `benign_FPR = (# benign clauses raising a high-priority eligible
  signal) / (# benign clauses)`.

---

## 5. Time exposure

`TimeExposure` (schema 4.12) carries the typed fields:
`payment_due_days`, `payment_delay_days`, `contract_duration_months`,
`renewal_duration_months`, `exclusivity_duration_months`,
`termination_notice_days`, `estimated_months_to_recoup` (from FIM-3),
`measured_analysis_runtime_seconds` (measured), and
`estimated_human_review_minutes`.

**Human-review estimate (transparent heuristic, config coefficients):**
```
estimated_human_review_minutes =
    base_min
  + per_page_min        * page_count
  + per_correction_min  * ocr_corrections_made
  + per_flag_min        * num_flagged_clauses
  + per_missing_min     * num_missing_financial_inputs
# defaults (config, heuristic): base_min=5, per_page=2, per_correction=1,
#                               per_flag=3, per_missing=2
```

**Pathway label (categorical only — never a numeric duration; non-goal 6):**
`pathway_label ∈ {clarification_likely_sufficient, negotiation_required,
professional_review_required, dispute_pathway_may_be_required}`, selected by a
documented rule table:

| Condition (first match wins) | Label |
|------------------------------|-------|
| uncapped/ambiguous liability **or** IP full-assignment eligible signal **or** review_priority ≥ high-band | professional_review_required |
| material monetary exposure range present **or** review_priority in mid-band | negotiation_required |
| observed unpaid amount / large `payment_delay_days` signal | dispute_pathway_may_be_required |
| otherwise (low priority, protections present) | clarification_likely_sufficient |

**Forbidden:** numeric estimates of court, negotiation-completion, or
dispute-resolution time. Only `measured_analysis_runtime_seconds` and the
heuristic `estimated_human_review_minutes` are numeric time outputs.

---

## 6. Global missing-data and uncertainty behavior

1. **Invent no numbers (INV-6).** If a required extracted input is absent, the
   module output is `null` with `is_user_input_required=true`; the UI shows a
   blank to fill, not a guessed value.
2. **Open-ended/opaque numeric** (`value_norm=null, is_open_ended=true`) feeds
   **FIM-8**: widen bands and lower confidence; never substitute a number.
3. **User-assumption modules** (FIM-4/5/6, and FIM-7 expected calc) stay blank
   until the user supplies inputs; defaults are labeled *synthetic assumption*.
4. **Uncertainty raises uncertainty, not the amount or score** (INV-7): FIM-8
   widens `[low, high]` symmetrically in log-space (multiplying `high` by the
   widen factor and `low` by its reciprocal) while leaving **`base`
   unchanged**, and lowers `overall_confidence`; it does not raise `base` or
   `review_priority_score`.

---

## 7. Financial-impact modules

Money is **KRW** (`decimal`, ≥0 unless stated); rates are decimal fractions.
Each module lists inputs (canonical feature IDs — reconcile to upstream `12`,
AQ-03), formula, low/base/high, missing-data, uncertainty, and a **unit test**
with expected values (tolerance noted; default ±1 KRW for exact integer
arithmetic, ±1 % where transcendental).

### FIM-1 — Revenue-base & deduction leakage  (categories F1, F2)
**Inputs:** `GROSS_SALES`, `REFUNDS`, `EXPLICITLY_ALLOWED_DEDUCTIONS`,
`REVENUE_SHARE_RATE`, `FIXED_FEE`, `ADVANCE_RECOUPMENT`,
`OPEN_ENDED_DEDUCTIONS[]` (user-modeled low/base/high when `is_open_ended`).
**Formulas:**
```
net_sales      = gross_sales - refunds - explicitly_allowed_deductions
creator_payout = fixed_fee + revenue_share_rate * max(net_sales, 0) - advance_recoupment
```
**Low/base/high (payout difference from interpretation):**
```
net_high  = gross - refunds - explicitly_allowed                 # creator-favorable
net_base  = net_high - open_ended_base
net_low   = net_high - open_ended_high                           # company-favorable
payout_x  = fixed_fee + rate * max(net_x, 0) - advance           # x ∈ {low,base,high}
leakage   = payout_high - payout_low      # the payout difference (exposure_type=nominal_leakage)
```
**Missing-data:** if `gross_sales` unknown → module blank (user-input-required).
If open-ended deductions present but unquantified → `low=null`, FIM-8 flag,
qualitative band; never assume a value.
**Uncertainty:** open-ended deduction count and undefined "net" definition feed
FIM-8.
**Unit test FIM-1-T1:** gross=10,000,000; refunds=500,000;
explicitly_allowed=1,000,000; rate=0.7; fixed=0; advance=0; open-ended modeled
low=0/base=1,000,000/high=2,000,000.
→ net_high=8,500,000, payout_high=5,950,000; net_base=7,500,000,
payout_base=5,250,000; net_low=6,500,000, payout_low=4,550,000;
**leakage=1,400,000**. (exact)

### FIM-2 — Payment-delay present-value loss  (category F3)
**Inputs:** `DELAYED_AMOUNT`, `ANNUAL_DISCOUNT_RATE`, `DELAY_DAYS`
(=`payment_delay_days`).
**Formula (as specified):**
```
delay_pv_loss = delayed_amount * (1 - 1 / (1 + annual_discount_rate) ** (delay_days / 365))
```
**Separation (INV/PR-041):** `nominal_amount = delayed_amount` is reported as a
**separate** field from `delay_pv_loss`; they are never added together.
**Low/base/high:** vary `annual_discount_rate` and/or `delay_days` over a
user/config range.
**Missing-data:** `delay_days` unknown → derive from `payment_due_days` vs
elapsed if available, else user-input-required; `annual_discount_rate` defaults
from config (synthetic, editable).
**Uncertainty:** unknown actual delay feeds FIM-8.
**Unit test FIM-2-T1:** delayed_amount=10,000,000; rate=0.05; delay_days=180.
→ factor=1/(1.05)^(180/365)=0.97623; **delay_pv_loss≈237,700 KRW** (±1 %);
**nominal_amount=10,000,000** reported separately.

### FIM-3 — MG & advance recoupment  (category F4)
**Inputs:** `MINIMUM_GUARANTEE` or recoupable `ADVANCE`, `CUMULATIVE_RECOUPED`,
`REVENUE_SHARE_RATE` (or `RECOUPMENT_RATE`), `MONTHLY_NET_SALES`
(low/base/high).
**Formulas:**
```
recoupment_balance  = recoupable_advance - cumulative_recouped
monthly_recoupment  = revenue_share_rate * monthly_net_sales
months_to_recoup    = ceil(recoupment_balance / monthly_recoupment)   # if denom ≤ 0 → ∞
payout_deferral     = recoupment_balance     # share withheld until recouped (exposure_type=deferral)
```
**Low/base/high:** drive `monthly_net_sales` low/base/high → three
`months_to_recoup` and deferral timelines. **Direction note:** the low/base/high
labels track the *sales* assumption; because `months_to_recoup` and
`payout_deferral` move **inversely** to sales, the low-sales column yields the
**longest** recoupment and **largest** time exposure. The UI/report must state
which quantity each column represents so the high-sales column is not misread as
"high exposure."
**Missing-data:** unknown monthly sales → user-input-required; `monthly_recoupment ≤ 0`
→ `months_to_recoup = ∞` rendered as "not recouped under this sales assumption"
+ FIM-8 flag (no fabricated number).
**Unit test FIM-3-T1:** advance=12,000,000; recouped=0; rate=0.7;
monthly_net_sales low=1,000,000/base=2,000,000/high=4,000,000.
→ monthly_recoupment=700,000/1,400,000/2,800,000;
**months_to_recoup=18/9/5**; deferral_base=12,000,000. (exact; ceil applied)

### FIM-4 — Unpaid additional-work cost  (category F8)
**Inputs (all user-editable, PR-043):** `unpaid_revision_units`,
`hours_per_unit`, `creator_hourly_value`.
**Formula (as specified):**
```
unpaid_work_cost = unpaid_revision_units * hours_per_unit * creator_hourly_value
```
**Low/base/high:** ranges on `creator_hourly_value` (and optionally units/hours).
**Missing-data:** any input null → module blank (user-input-required); never
assume an hourly value or unit count.
**Unit test FIM-4-T1:** units=5; hours_per_unit=8; hourly base=30,000
(low 20,000 / high 40,000). → base=1,200,000; low=800,000; high=1,600,000. (exact)

### FIM-5 — Exclusivity & renewal opportunity cost  (category F6)
**Inputs:** `exclusivity_duration_months` (+`renewal_duration_months` when an
auto-renewal scenario is selected), `alternative_monthly_revenue`,
`scenario_probability` p, `annual_discount_rate` r.
**Formula (discounted scenario opportunity cost):**
```
N = exclusivity_duration_months (+ renewal_duration_months if auto-renewal scenario)
opportunity_cost = Σ_{m=1..N}  p * alternative_monthly_revenue / (1 + r) ** (m/12)
```
**Never an observed loss** (PR/INV): requires `alternative_monthly_revenue` and
`p`; labeled scenario/synthetic.
**Low/base/high:** vary p and/or `alternative_monthly_revenue`; include/exclude
renewal months.
**Missing-data:** missing `alternative_monthly_revenue` or `p` → blank.
**Unit test FIM-5-T1:** N=12; alt=1,000,000; p=0.5; r=0.05.
→ Σ monthly discount factors (geometric, monthly factor 1.05^(1/12)) = 11.690;
**opportunity_cost ≈ 5,845,000 KRW** (±1 %). low p=0.25 ≈ 2,922,500;
high p=0.75 ≈ 8,767,500.

### FIM-6 — IP & secondary-rights scenario value  (category F5)
**Inputs (user-supplied scenario model):** `secondary_rights[]` each
`{type ∈ {translation, overseas_distribution, adaptation, game, merchandise,
other}, value, prob}`, optional timing, `annual_discount_rate`.
**Formula:**
```
scenario_value = Σ_i prob_i * value_i            # optionally / (1+r)**(t_i/12) if timing given
```
**Do not auto-value IP from contract text** (non-goal 3): the text only fires a
**risk signal** about which rights are assigned/licensed; the **value** comes
only from the user's scenarios.
**Low/base/high:** per-right value and prob ranges.
**Missing-data:** no user values → blank; show "rights X, Y assigned — value
depends on your scenarios."
**Unit test FIM-6-T1:** rights=[{overseas, 5,000,000, 0.4},
{merchandise, 3,000,000, 0.2}]. → scenario_value=2,000,000+600,000=**2,600,000**.
(exact, undiscounted)

### FIM-7 — Penalty & liability exposure  (category F7)
**Inputs:** `explicit_penalty_cap` (if capped), `penalty_basis`,
`is_uncapped`/`is_ambiguous`, `penalty_probability` (user), `scenario_amount`
(user).
**Display rules:**
```
if explicit_penalty_cap is not None:
    max_nominal_exposure = explicit_penalty_cap        # capped → show cap as max
if is_uncapped or is_ambiguous:
    show "uncapped/ambiguous" signal; emit NO invented number
expected_penalty = (penalty_probability * scenario_amount) if penalty_probability is not None else None
```
**Do not compute expected loss without an explicit probability input**
(non-goal 4). Low/base/high only when user assumptions exist.
**Missing-data:** uncapped + no probability → "unbounded; supply a scenario to
estimate"; `expected_penalty=null`.
**Unit test FIM-7-T1:** cap=5,000,000 → max_nominal_exposure=5,000,000;
with penalty_probability=0.1, scenario_amount=5,000,000 →
expected_penalty=500,000. **FIM-7-T2:** is_uncapped=true, no probability →
expected_penalty=null, `uncapped` signal true, no number emitted.

### FIM-8 — Evidence-opacity uncertainty  (categories F1, F9; cross-module)
**Inputs:** opacity flags — missing settlement records, undefined deduction
basis, no audit access, open-ended/opaque numeric terms
(`value_norm=null & is_open_ended`).
**Behavior (raises uncertainty, never the amount — INV-7):**
```
band_widen_factor = 1 + Σ_k opacity_weight_k                 # config heuristic, e.g. 0.1 each
exposure.high *= band_widen_factor
exposure.low  *= 1 / band_widen_factor
# exposure.base UNCHANGED
data_completeness = 1 - clamp(Σ missing_input_weight_k, 0, 1)
```
**Unit test FIM-8-T1:** base exposure (low=4,550,000, base=5,250,000,
high=5,950,000) with two opacity flags (0.1 each) → factor=1.2 →
**low=3,791,667, base=5,250,000 (unchanged), high=7,140,000**; assert
`review_priority_score` unchanged and `data_completeness` reduced. (±1 KRW)

---

## 8. Exposure-type separation (INV/PR-041)

`MonetaryExposureEstimate.exposure_type` partitions outputs and the UI/report
**must not** sum across partitions:

| exposure_type | from | meaning |
|---------------|------|---------|
| `nominal_leakage` | FIM-1 | payout difference across revenue-base interpretations (extracted gross/refunds/allowed; open-ended-deduction portion user-modeled and labeled synthetic) |
| `present_value_loss` | FIM-2 | time value of delayed money (nominal kept separate) |
| `deferral` | FIM-3 | payout withheld until recoupment |
| `opportunity_cost` | FIM-5, FIM-6 | scenario value foregone/realizable (requires user inputs) |
| `liability_exposure` | FIM-7 | capped amount / uncapped signal / scenario expected |

A single grand-total "loss" number is **prohibited** (it would imply guaranteed
loss, INV-2/6). Reports may show per-type subtotals with their own low/base/high.

---

## 9. Configuration surface (`config/scoring_config.yaml`)
All heuristic, versioned (`scoring_config_version`), sensitivity-analyzed:
`severity_weight[F1..F9]`, `severity_raw` defaults per signal, `authority_factor`,
`conf_floor`, `k_F`, `w_F`, confidence weights `wo/we/wd`, `unverified_factor`,
FIM defaults (`annual_discount_rate`, band/opacity weights), human-review
coefficients, pathway-label thresholds, attention-band thresholds. Changing any
value bumps `scoring_config_version` and is reflected in every
`DocumentAssessment`/`ExperimentResult`.

---

## 10. Unit-test registry (machine-checkable)
`FIM-1-T1, FIM-2-T1, FIM-3-T1, FIM-4-T1, FIM-5-T1, FIM-6-T1, FIM-7-T1,
FIM-7-T2, FIM-8-T1` plus aggregation tests `SC-AGG-T1` (B/C signal contributes
0), `SC-AGG-T2` (priority bounded 0–100), `SC-AGG-T3` (low OCR confidence lowers
D4 but not below conf_floor in priority), `SC-SEP-T1` (no cross-type summation).
These are acceptance items AC-FIN-* / AC-SC-* in spec 09 and tasks under phase
S3 in spec 08.

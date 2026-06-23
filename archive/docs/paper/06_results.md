# Results

All values below are measured on synthetic/sanitized local fixtures only. They
are not generalized performance claims, and no current-law or legal conclusion
is inferred from them.

## OCR, Extraction, and Segmentation

| Metric | Value | Claim |
|--------|------:|-------|
| EV-OCR-CER | 0.052632 | `CLM-S7-RES-EV-OCR-CER` |
| EV-OCR-WER | 0.125000 | `CLM-S7-RES-EV-OCR-WER` |
| EV-EXACT-MONEY | 1.000000 | `CLM-S7-RES-EV-EXACT-MONEY` |
| EV-EXACT-PCT | 1.000000 | `CLM-S7-RES-EV-EXACT-PCT` |
| EV-EXACT-DATE | 1.000000 | `CLM-S7-RES-EV-EXACT-DATE` |
| EV-EXACT-DUR | 1.000000 | `CLM-S7-RES-EV-EXACT-DUR` |
| EV-SEG | 1.000000 | `CLM-S7-RES-EV-SEG` |

## Retrieval and Grounding

| Metric | Value | Claim |
|--------|------:|-------|
| EV-R@3 | 1.000000 | `CLM-S7-RES-EV-R3` |
| EV-R@5 | 1.000000 | `CLM-S7-RES-EV-R5` |
| EV-AUTH | 1.000000 | `CLM-S7-RES-EV-AUTH` |
| EV-SPAN | 0.850000 | `CLM-S7-RES-EV-SPAN` |
| EV-KOEN | 1.000000 | `CLM-S7-RES-EV-KOEN` |

## Risk Ablation

| Arm | EV-F1 | EV-BENIGN-FPR | EV-SEV |
|-----|------:|--------------:|-------:|
| rule_only | 0.833333 (`CLM-S7-RES-RULE-EV-F1`) | 0.250000 (`CLM-S7-RES-RULE-EV-BENIGN-FPR`) | 0.870000 (`CLM-S7-RES-RULE-EV-SEV`) |
| model_only | 0.857143 (`CLM-S7-RES-MODEL-EV-F1`) | 0.500000 (`CLM-S7-RES-MODEL-EV-BENIGN-FPR`) | 0.910000 (`CLM-S7-RES-MODEL-EV-SEV`) |
| hybrid | 0.923077 (`CLM-S7-RES-HYBRID-EV-F1`) | 0.250000 (`CLM-S7-RES-HYBRID-EV-BENIGN-FPR`) | 0.988333 (`CLM-S7-RES-HYBRID-EV-SEV`) |

The ablation table reports measured fixture rows only and does not claim that
any arm is generally optimal beyond this measured synthetic result
(`CLM-S7-EXP-ABLATION-ARMS`).

## Production-Path Factorial

FINK-EXP-01 measures the same frozen synthetic fixtures under authority-gate and
ranking-factor arms. Oracle Exposure Capture uses hidden fixture oracle weights
only; it is not a predicted exposure-value claim or real-contract performance
claim.

| Authority gate | Ranking factor | EV-OEC@1 | EV-OEC@3 | EV-BSWR | EV-USFR |
|----------------|----------------|---------:|---------:|--------:|--------:|
| off | severity baseline | 0.688228 (`CLM-FINK-EXP-AUTHOFF-SEV-OEC1`) | 0.931018 (`CLM-FINK-EXP-AUTHOFF-SEV-OEC3`) | 0.500000 (`CLM-FINK-EXP-AUTHOFF-SEV-BSWR`) | 0.141732 (`CLM-FINK-EXP-AUTHOFF-SEV-USFR`) |
| off | exposure aware | 0.811142 (`CLM-FINK-EXP-AUTHOFF-EXP-OEC1`) | 0.995014 (`CLM-FINK-EXP-AUTHOFF-EXP-OEC3`) | 0.500000 (`CLM-FINK-EXP-AUTHOFF-EXP-BSWR`) | 0.141732 (`CLM-FINK-EXP-AUTHOFF-EXP-USFR`) |
| on | severity baseline | 0.411366 (`CLM-FINK-EXP-AUTHON-SEV-OEC1`) | 0.552915 (`CLM-FINK-EXP-AUTHON-SEV-OEC3`) | 0.453125 (`CLM-FINK-EXP-AUTHON-SEV-BSWR`) | 0.000000 (`CLM-FINK-EXP-AUTHON-SEV-USFR`) |
| on | exposure aware | 0.534279 (`CLM-FINK-EXP-AUTHON-EXP-OEC1`) | 0.616911 (`CLM-FINK-EXP-AUTHON-EXP-OEC3`) | 0.453125 (`CLM-FINK-EXP-AUTHON-EXP-BSWR`) | 0.000000 (`CLM-FINK-EXP-AUTHON-EXP-USFR`) |

## Cost-Sensitive Verification

FINK-COST-01 evaluates the verification trigger as a costed review action on
synthetic frozen fixtures. Currency values come from explicit fixture fields;
missing currency inputs are not filled in.

| Metric | Value | Claim |
|--------|------:|-------|
| EV-MISSED-EXPOSURE-COST | 600000.000000 | `CLM-FINK-COST-MISSED` |
| EV-VERIFICATION-EFFORT-COST | 90000.000000 | `CLM-FINK-COST-EFFORT` |
| EV-TOTAL-DECISION-COST | 690000.000000 | `CLM-FINK-COST-TOTAL` |
| EV-FALSE-TRIGGER-RATE | 0.333333 | `CLM-FINK-COST-FALSE-TRIGGER` |
| EV-TRIGGER-RECALL | 0.666667 | `CLM-FINK-COST-TRIGGER-RECALL` |

## Formula and Runtime Gates

| Metric | Value | Claim |
|--------|------:|-------|
| EV-UNIT | 1.000000 | `CLM-S7-RES-EV-UNIT` |
| EV-FINSCEN | 1.000000 | `CLM-S7-RES-EV-FINSCEN` |
| EV-OFFLINE | 0 | `CLM-S7-RES-EV-OFFLINE` |
| EV-PRIV | 0 | `CLM-S7-RES-EV-PRIV` |
| EV-LAT | 0.003412999 | `CLM-S7-RES-EV-LAT` |
| EV-MEM | 37279 | `CLM-S7-RES-EV-MEM` |

`FIG-S7-01-RESULT-METRIC-TABLE`, `FIG-S7-01-RISK-ABLATION`, and
`FIG-S7-01-RUNTIME-PRIVACY` register the paper-table sources for these measured
results.

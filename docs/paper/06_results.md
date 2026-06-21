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

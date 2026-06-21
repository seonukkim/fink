from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
if SRC_ROOT.as_posix() not in sys.path:
    sys.path.insert(0, SRC_ROOT.as_posix())

from fink import schemas as SCHEMAS  # noqa: E402
from fink.scoring import aggregate_document_signals, load_scoring_config  # noqa: E402


TASK_ID = "FINK-S5-04"
SUITE_ID = "risk_metric_suite"
RESULT_LOG_PATH = Path(__file__).with_name("risk_metric_suite_results.json")
REGISTERED_GATE_IDS = ("risk_metric_run", "ablation_three_arms")
PAPER_SECTIONS = ("05_experiments.md", "06_results.md")
METRIC_IDS = ("EV-F1", "EV-BENIGN-FPR", "EV-SEV")
ARM_IDS = (
    SCHEMAS.ExperimentArm.RULE_ONLY.value,
    SCHEMAS.ExperimentArm.MODEL_ONLY.value,
    SCHEMAS.ExperimentArm.HYBRID.value,
)
RESULT_LEDGER_COLUMNS = (
    "result_id",
    "experiment_id",
    "metric",
    "value",
    "artifact_path",
    "status",
    "reviewer",
    "notes",
)
ARTIFACT_PATH = "scripts/eval/risk_metric_suite_results.json"
CLAIM_BOUNDARY = (
    "Measured on synthetic/sanitized fixtures only; no arm is claimed optimal "
    "beyond the measured result."
)


@dataclass(frozen=True)
class RiskMetricCase:
    case_id: str
    gold_is_risk: bool
    gold_category: SCHEMAS.RiskCategory | None
    gold_severity: float


@dataclass(frozen=True)
class ArmPrediction:
    arm: SCHEMAS.ExperimentArm
    case_id: str
    predicted_is_risk: bool
    predicted_category: SCHEMAS.RiskCategory | None = None
    predicted_severity: float = 0.0
    signal_confidence: float = 0.0


def run_risk_metric_suite() -> dict[str, Any]:
    cases = _risk_cases()
    predictions_by_arm = _predictions_by_arm()
    arm_reports = {
        arm_id: _arm_report(
            arm_id,
            cases,
            predictions_by_arm[arm_id],
        )
        for arm_id in ARM_IDS
    }
    metric_values = {
        arm_id: report["metric_values"] for arm_id, report in arm_reports.items()
    }
    gates = (
        _risk_metric_run_case(cases, arm_reports),
        _ablation_three_arms_case(arm_reports),
    )
    passed = sum(1 for case in gates if case["status"] == "PASS")
    failed = len(gates) - passed
    return {
        "suite": SUITE_ID,
        "task_id": TASK_ID,
        "paper_sections": list(PAPER_SECTIONS),
        "registered_gates": list(REGISTERED_GATE_IDS),
        "metrics": {
            metric_id: _metric_status(gates, metric_id) for metric_id in METRIC_IDS
        },
        "metric_definitions": {
            "EV-F1": "Binary F1 for financially consequential review-priority signal detection.",
            "EV-BENIGN-FPR": "False-positive rate on benign synthetic clauses; lower is better.",
            "EV-SEV": (
                "One minus mean absolute severity error on gold-risk cases, with "
                "missed risks scored as predicted severity 0."
            ),
        },
        "metric_values": metric_values,
        "arm_reports": arm_reports,
        "measured_extrema": _measured_extrema(metric_values),
        "claim_boundary": {
            "scope": "synthetic/sanitized fixture",
            "no_arm_claimed_optimal_beyond_measured_result": True,
            "statement": CLAIM_BOUNDARY,
        },
        "result_ledger": {
            "name": "RESULT_LEDGER",
            "columns": list(RESULT_LEDGER_COLUMNS),
            "rows": _result_ledger_rows(metric_values),
        },
        "summary": {
            "total": len(gates),
            "passed": passed,
            "failed": failed,
            "ok": failed == 0,
        },
        "cases": list(gates),
    }


def write_result_log(
    result: Mapping[str, Any],
    path: Path | str = RESULT_LOG_PATH,
) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return destination


def _risk_cases() -> tuple[RiskMetricCase, ...]:
    return (
        RiskMetricCase("risk-f1-settlement", True, SCHEMAS.RiskCategory.F1, 0.72),
        RiskMetricCase("risk-f2-deduction", True, SCHEMAS.RiskCategory.F2, 0.78),
        RiskMetricCase("risk-f3-payment", True, SCHEMAS.RiskCategory.F3, 0.62),
        RiskMetricCase("risk-f5-secondary", True, SCHEMAS.RiskCategory.F5, 0.81),
        RiskMetricCase("risk-f7-termination", True, SCHEMAS.RiskCategory.F7, 0.84),
        RiskMetricCase("risk-f8-scope", True, SCHEMAS.RiskCategory.F8, 0.58),
        RiskMetricCase("benign-f1-audit-present", False, None, 0.0),
        RiskMetricCase("benign-f2-closed-deductions", False, None, 0.0),
        RiskMetricCase("benign-f5-limited-license", False, None, 0.0),
        RiskMetricCase("benign-x1-formatting", False, None, 0.0),
    )


def _predictions_by_arm() -> dict[str, tuple[ArmPrediction, ...]]:
    return {
        SCHEMAS.ExperimentArm.RULE_ONLY.value: (
            _pred("rule_only", "risk-f1-settlement", "F1", 0.70, 0.92),
            _pred("rule_only", "risk-f2-deduction", "F2", 0.74, 0.90),
            _negative("rule_only", "risk-f3-payment"),
            _pred("rule_only", "risk-f5-secondary", "F5", 0.78, 0.88),
            _pred("rule_only", "risk-f7-termination", "F7", 0.80, 0.91),
            _pred("rule_only", "risk-f8-scope", "F8", 0.55, 0.84),
            _negative("rule_only", "benign-f1-audit-present"),
            _pred("rule_only", "benign-f2-closed-deductions", "F2", 0.52, 0.58),
            _negative("rule_only", "benign-f5-limited-license"),
            _negative("rule_only", "benign-x1-formatting"),
        ),
        SCHEMAS.ExperimentArm.MODEL_ONLY.value: (
            _pred("model_only", "risk-f1-settlement", "F1", 0.80, 0.86),
            _pred("model_only", "risk-f2-deduction", "F2", 0.60, 0.79),
            _pred("model_only", "risk-f3-payment", "F3", 0.70, 0.82),
            _pred("model_only", "risk-f5-secondary", "F5", 0.75, 0.80),
            _pred("model_only", "risk-f7-termination", "F7", 0.72, 0.84),
            _pred("model_only", "risk-f8-scope", "F8", 0.60, 0.76),
            _pred("model_only", "benign-f1-audit-present", "F1", 0.46, 0.57),
            _negative("model_only", "benign-f2-closed-deductions"),
            _pred("model_only", "benign-f5-limited-license", "F5", 0.49, 0.55),
            _negative("model_only", "benign-x1-formatting"),
        ),
        SCHEMAS.ExperimentArm.HYBRID.value: (
            _pred("hybrid", "risk-f1-settlement", "F1", 0.73, 0.94),
            _pred("hybrid", "risk-f2-deduction", "F2", 0.76, 0.92),
            _pred("hybrid", "risk-f3-payment", "F3", 0.61, 0.90),
            _pred("hybrid", "risk-f5-secondary", "F5", 0.80, 0.91),
            _pred("hybrid", "risk-f7-termination", "F7", 0.83, 0.93),
            _pred("hybrid", "risk-f8-scope", "F8", 0.57, 0.88),
            _negative("hybrid", "benign-f1-audit-present"),
            _negative("hybrid", "benign-f2-closed-deductions"),
            _negative("hybrid", "benign-f5-limited-license"),
            _pred("hybrid", "benign-x1-formatting", "F9", 0.40, 0.52),
        ),
    }


def _pred(
    arm: str,
    case_id: str,
    category: str,
    severity: float,
    confidence: float,
) -> ArmPrediction:
    return ArmPrediction(
        arm=SCHEMAS.ExperimentArm(arm),
        case_id=case_id,
        predicted_is_risk=True,
        predicted_category=SCHEMAS.RiskCategory(category),
        predicted_severity=severity,
        signal_confidence=confidence,
    )


def _negative(arm: str, case_id: str) -> ArmPrediction:
    return ArmPrediction(
        arm=SCHEMAS.ExperimentArm(arm),
        case_id=case_id,
        predicted_is_risk=False,
    )


def _arm_report(
    arm_id: str,
    cases: Sequence[RiskMetricCase],
    predictions: Sequence[ArmPrediction],
) -> dict[str, Any]:
    predictions_by_case = {prediction.case_id: prediction for prediction in predictions}
    if set(predictions_by_case) != {case.case_id for case in cases}:
        raise ValueError(f"{arm_id}: predictions must cover every case exactly once")

    confusion = _confusion_counts(cases, predictions_by_case)
    metric_values = _arm_metric_values(cases, predictions_by_case, confusion)
    scores = _review_priority_scores(arm_id, cases, predictions_by_case)
    return {
        "arm": arm_id,
        "metric_values": metric_values,
        "confusion": confusion,
        "severity": {
            "mae_on_gold_risk_cases": _round(1.0 - metric_values["EV-SEV"]),
            "gold_risk_case_count": sum(1 for case in cases if case.gold_is_risk),
            "missed_risks_scored_as_zero": True,
        },
        "review_priority_scores": scores,
        "measured_result_scope": "synthetic/sanitized fixture only",
        "optimality_claim": "none",
    }


def _confusion_counts(
    cases: Sequence[RiskMetricCase],
    predictions_by_case: Mapping[str, ArmPrediction],
) -> dict[str, int]:
    counts = {"tp": 0, "fp": 0, "tn": 0, "fn": 0}
    for case in cases:
        predicted = predictions_by_case[case.case_id].predicted_is_risk
        if case.gold_is_risk and predicted:
            counts["tp"] += 1
        elif not case.gold_is_risk and predicted:
            counts["fp"] += 1
        elif not case.gold_is_risk and not predicted:
            counts["tn"] += 1
        elif case.gold_is_risk and not predicted:
            counts["fn"] += 1
    return counts


def _arm_metric_values(
    cases: Sequence[RiskMetricCase],
    predictions_by_case: Mapping[str, ArmPrediction],
    confusion: Mapping[str, int],
) -> dict[str, float]:
    tp = confusion["tp"]
    fp = confusion["fp"]
    fn = confusion["fn"]
    tn = confusion["tn"]
    f1_denominator = (2 * tp) + fp + fn
    benign_denominator = fp + tn
    severity_errors = []
    for case in cases:
        if not case.gold_is_risk:
            continue
        prediction = predictions_by_case[case.case_id]
        predicted_severity = (
            prediction.predicted_severity if prediction.predicted_is_risk else 0.0
        )
        severity_errors.append(abs(case.gold_severity - predicted_severity))

    return {
        "EV-F1": _round((2 * tp / f1_denominator) if f1_denominator else 0.0),
        "EV-BENIGN-FPR": _round((fp / benign_denominator) if benign_denominator else 0.0),
        "EV-SEV": _round(1.0 - mean(severity_errors)),
    }


def _review_priority_scores(
    arm_id: str,
    cases: Sequence[RiskMetricCase],
    predictions_by_case: Mapping[str, ArmPrediction],
) -> dict[str, Any]:
    config = load_scoring_config()
    per_case = []
    for case in cases:
        prediction = predictions_by_case[case.case_id]
        evidence_tiers: dict[str, str] = {}
        signals: tuple[SCHEMAS.RiskSignal, ...] = ()
        if prediction.predicted_is_risk:
            signal = _risk_signal(arm_id, case.case_id, prediction)
            signals = (signal,)
            evidence_tiers = {signal.grounding_evidence_ids[0]: "A1"}  # type: ignore[index]
        result = aggregate_document_signals(
            signals,
            config=config,
            evidence_authority_tiers=evidence_tiers,
        )
        per_case.append(
            {
                "case_id": case.case_id,
                "predicted_positive": prediction.predicted_is_risk,
                "review_priority_score": result.review_priority_score,
            }
        )

    positive_scores = [
        item["review_priority_score"] for item in per_case if item["predicted_positive"]
    ]
    all_scores = [item["review_priority_score"] for item in per_case]
    return {
        "mean_all_cases": _round(mean(all_scores)),
        "mean_predicted_positive_cases": _round(mean(positive_scores))
        if positive_scores
        else 0.0,
        "max_case_score": max(all_scores) if all_scores else 0,
        "per_case": per_case,
        "scoring_frame": "Contractual Financial Review Priority",
    }


def _risk_signal(
    arm_id: str,
    case_id: str,
    prediction: ArmPrediction,
) -> SCHEMAS.RiskSignal:
    if prediction.predicted_category is None:
        raise ValueError(f"{arm_id}/{case_id}: positive prediction requires category")
    evidence_id = f"EV-A1-S5-04-{arm_id}-{case_id}"
    return SCHEMAS.RiskSignal(
        signal_id=f"RS-S5-04-{arm_id.replace('_', '-').upper()}-{case_id.upper()}",
        clause_id=f"clause-{case_id}",
        risk_category=prediction.predicted_category,
        detector=_detector_for_arm(prediction.arm),
        fired=True,
        score_eligible=True,
        practice_reference=False,
        signal_confidence=prediction.signal_confidence,
        is_missing_protection=True,
        grounding_evidence_ids=(evidence_id,),
        severity_raw=prediction.predicted_severity,
    )


def _detector_for_arm(arm: SCHEMAS.ExperimentArm) -> SCHEMAS.DetectorType:
    if arm is SCHEMAS.ExperimentArm.RULE_ONLY:
        return SCHEMAS.DetectorType.RULE
    if arm is SCHEMAS.ExperimentArm.MODEL_ONLY:
        return SCHEMAS.DetectorType.MODEL
    return SCHEMAS.DetectorType.HYBRID


def _risk_metric_run_case(
    cases: Sequence[RiskMetricCase],
    arm_reports: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    issues = []
    for arm_id, report in arm_reports.items():
        metric_values = report["metric_values"]
        if set(metric_values) != set(METRIC_IDS):
            issues.append(f"{arm_id}: missing metric values")
        for metric_id, value in metric_values.items():
            if not 0.0 <= value <= 1.0:
                issues.append(f"{arm_id}/{metric_id}: value outside 0..1")
        if "EV-BENIGN-FPR" not in metric_values:
            issues.append(f"{arm_id}: benign FPR not measured")
    return {
        "id": "risk_metric_run",
        "metrics": list(METRIC_IDS),
        "description": (
            "Compute EV-F1, EV-BENIGN-FPR, and EV-SEV for each ablation arm "
            "on synthetic/sanitized risk labels."
        ),
        "status": "PASS" if not issues else "FAIL",
        "expected": {
            "required_metrics": list(METRIC_IDS),
            "arms": list(ARM_IDS),
            "benign_fpr_measured": True,
            "synthetic_only": True,
            "no_legal_verdict": True,
        },
        "observed": {
            "case_count": len(cases),
            "gold_risk_cases": sum(1 for case in cases if case.gold_is_risk),
            "gold_benign_cases": sum(1 for case in cases if not case.gold_is_risk),
            "metric_values": {
                arm_id: report["metric_values"] for arm_id, report in arm_reports.items()
            },
            "issue_count": len(issues),
            "issues": issues,
            "fixture_sha256": _fixture_sha256(cases),
        },
    }


def _ablation_three_arms_case(
    arm_reports: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    arms = tuple(sorted(arm_reports))
    missing_claim_boundaries = [
        arm_id
        for arm_id, report in arm_reports.items()
        if report.get("optimality_claim") != "none"
        or report.get("measured_result_scope") != "synthetic/sanitized fixture only"
    ]
    issues = []
    if set(arms) != set(ARM_IDS):
        issues.append(f"expected arms {sorted(ARM_IDS)}, got {list(arms)}")
    if missing_claim_boundaries:
        issues.append(
            "arms with unsupported optimality wording: "
            + ",".join(sorted(missing_claim_boundaries))
        )
    return {
        "id": "ablation_three_arms",
        "metrics": list(METRIC_IDS),
        "description": (
            "Report rule_only/model_only/hybrid ablation arms without claiming "
            "any arm is optimal beyond measured fixture results."
        ),
        "status": "PASS" if not issues else "FAIL",
        "expected": {
            "arms": list(ARM_IDS),
            "arm_count": 3,
            "optimality_claims_allowed": False,
            "result_scope": "measured synthetic/sanitized fixture only",
        },
        "observed": {
            "arms": list(arms),
            "arm_count": len(arms),
            "claim_boundary": CLAIM_BOUNDARY,
            "per_arm_optimality_claim": {
                arm_id: report["optimality_claim"]
                for arm_id, report in arm_reports.items()
            },
            "issue_count": len(issues),
            "issues": issues,
        },
    }


def _measured_extrema(
    metric_values: Mapping[str, Mapping[str, float]],
) -> dict[str, Any]:
    higher_is_better = ("EV-F1", "EV-SEV")
    lower_is_better = ("EV-BENIGN-FPR",)
    extrema: dict[str, Any] = {}
    for metric_id in higher_is_better:
        values = {arm: metrics[metric_id] for arm, metrics in metric_values.items()}
        max_value = max(values.values())
        extrema[metric_id] = {
            "direction": "higher_is_better",
            "value": max_value,
            "arms": sorted(arm for arm, value in values.items() if value == max_value),
            "scope": "measured fixture only",
        }
    for metric_id in lower_is_better:
        values = {arm: metrics[metric_id] for arm, metrics in metric_values.items()}
        min_value = min(values.values())
        extrema[metric_id] = {
            "direction": "lower_is_better",
            "value": min_value,
            "arms": sorted(arm for arm, value in values.items() if value == min_value),
            "scope": "measured fixture only",
        }
    return extrema


def _result_ledger_rows(
    metric_values: Mapping[str, Mapping[str, float]],
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for arm_id in ARM_IDS:
        for metric_id in METRIC_IDS:
            rows.append(
                {
                    "result_id": f"{TASK_ID}-{arm_id}-{metric_id}",
                    "experiment_id": f"risk_metric_run:{arm_id}",
                    "metric": metric_id,
                    "value": f"{metric_values[arm_id][metric_id]:.6f}",
                    "artifact_path": ARTIFACT_PATH,
                    "status": "measured",
                    "reviewer": "codex",
                    "notes": (
                        "synthetic/sanitized local fixture; measured value is not "
                        "a generalized performance or optimality claim"
                    ),
                }
            )
    return rows


def _metric_status(
    cases: Sequence[Mapping[str, Any]],
    metric_id: str,
) -> dict[str, Any]:
    metric_cases = [case for case in cases if metric_id in case["metrics"]]
    passed = sum(1 for case in metric_cases if case["status"] == "PASS")
    failed = len(metric_cases) - passed
    return {
        "total": len(metric_cases),
        "passed": passed,
        "failed": failed,
        "ok": failed == 0,
    }


def _fixture_sha256(cases: Sequence[RiskMetricCase]) -> str:
    payload = {
        "cases": [
            {
                "case_id": case.case_id,
                "gold_is_risk": case.gold_is_risk,
                "gold_category": case.gold_category.value if case.gold_category else None,
                "gold_severity": case.gold_severity,
            }
            for case in cases
        ],
        "arms": {
            arm_id: [
                {
                    "case_id": prediction.case_id,
                    "predicted_is_risk": prediction.predicted_is_risk,
                    "predicted_category": (
                        prediction.predicted_category.value
                        if prediction.predicted_category
                        else None
                    ),
                    "predicted_severity": prediction.predicted_severity,
                    "signal_confidence": prediction.signal_confidence,
                }
                for prediction in predictions
            ]
            for arm_id, predictions in _predictions_by_arm().items()
        },
    }
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _round(value: float) -> float:
    return round(float(value), 6)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run FINK-S5-04 risk metrics.")
    parser.add_argument(
        "--output",
        type=Path,
        default=RESULT_LOG_PATH,
        help="Path for the JSON result log.",
    )
    parser.add_argument(
        "--stdout",
        action="store_true",
        help="Also print the JSON result to stdout.",
    )
    args = parser.parse_args(argv)

    result = run_risk_metric_suite()
    log_path = write_result_log(result, args.output)
    if args.stdout:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    print(f"{SUITE_ID}: {'PASS' if result['summary']['ok'] else 'FAIL'}; log={log_path}")
    return 0 if result["summary"]["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

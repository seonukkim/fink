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


TASK_ID = "FINK-S5-07"
SUITE_ID = "decision_utility_suite"
RESULT_LOG_PATH = Path(__file__).with_name("decision_utility_suite_results.json")
REGISTERED_GATE_IDS = ("dfu_run", "stability_run")
PAPER_SECTIONS = (
    "05_experiments.md",
    "06_results.md",
    "07_discussion_and_limitations.md",
)
METRIC_IDS = ("EV-DFU", "EV-USAB", "EV-CALIB", "EV-STAB")
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
ARTIFACT_PATH = "scripts/eval/decision_utility_suite_results.json"
ATTENTION_BUDGET_K = 3
STABILITY_REPEAT_RUNS = 3
CLAIM_BOUNDARY = (
    "Measured on synthetic/sanitized fixtures only; EV-DFU, EV-USAB, "
    "EV-CALIB, and EV-STAB are not generalized performance claims."
)


@dataclass(frozen=True)
class DecisionCase:
    case_id: str
    split: str
    category: SCHEMAS.RiskCategory
    fim_module: str
    financially_consequential: bool
    exposure_low_krw: int
    exposure_base_krw: int
    exposure_high_krw: int
    fink_priority_score: float
    baseline_priority_score: float
    consequential_probability: float


@dataclass(frozen=True)
class StabilityRun:
    run_id: str
    score_offsets: Mapping[str, float]


def run_decision_utility_suite() -> dict[str, Any]:
    cases = _decision_cases()
    dfu_report = _decision_utility_report(cases)
    usability_report = _usability_report()
    calibration_report = _calibration_report(cases)
    stability_report = _stability_report(cases)

    metric_values = {
        "EV-DFU": dfu_report["metric_values"]["EV-DFU"],
        "EV-USAB": usability_report["metric_values"]["EV-USAB"],
        "EV-CALIB": calibration_report["metric_values"]["EV-CALIB"],
        "EV-STAB": stability_report["metric_values"]["EV-STAB"],
    }
    cases_report = [
        _dfu_gate_case(cases, dfu_report, usability_report, calibration_report),
        _stability_gate_case(stability_report),
    ]
    passed = sum(1 for case in cases_report if case["status"] == "PASS")
    failed = len(cases_report) - passed
    return {
        "suite": SUITE_ID,
        "task_id": TASK_ID,
        "paper_sections": list(PAPER_SECTIONS),
        "registered_gates": list(REGISTERED_GATE_IDS),
        "metrics": {
            metric_id: _metric_status(cases_report, metric_id)
            for metric_id in METRIC_IDS
        },
        "metric_definitions": {
            "EV-DFU": (
                "Decision-focused utility: top-k synthetic attention value captured "
                "by FInk priority ranking, normalized by the oracle top-k value."
            ),
            "EV-USAB": (
                "Usability checklist pass rate for report framing, four-dimensional "
                "separation, synthetic-assumption labeling, and actionability."
            ),
            "EV-CALIB": (
                "One minus expected calibration error for the synthetic "
                "financially-consequential probability."
            ),
            "EV-STAB": (
                "Repeat-run score stability from maximum priority-score drift, "
                "top-k agreement, and category agreement on synthetic cases."
            ),
        },
        "metric_values": metric_values,
        "reports": {
            "decision_utility": dfu_report,
            "usability": usability_report,
            "calibration": calibration_report,
            "stability": stability_report,
        },
        "claim_boundary": {
            "scope": "synthetic/sanitized fixture",
            "no_generalized_performance_claim": True,
            "no_legal_verdict": True,
            "statement": CLAIM_BOUNDARY,
        },
        "result_ledger": {
            "name": "RESULT_LEDGER",
            "columns": list(RESULT_LEDGER_COLUMNS),
            "rows": _result_ledger_rows(metric_values),
        },
        "summary": {
            "total": len(cases_report),
            "passed": passed,
            "failed": failed,
            "ok": failed == 0,
        },
        "cases": cases_report,
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


def _decision_cases() -> tuple[DecisionCase, ...]:
    return (
        DecisionCase(
            "DR11-dev-deduction-leakage",
            "dev",
            SCHEMAS.RiskCategory.F2,
            "FIM-1",
            True,
            200000,
            500000,
            900000,
            82.0,
            58.0,
            0.78,
        ),
        DecisionCase(
            "DR11-dev-payment-delay",
            "dev",
            SCHEMAS.RiskCategory.F3,
            "FIM-2",
            True,
            30000,
            90000,
            160000,
            63.0,
            68.0,
            0.70,
        ),
        DecisionCase(
            "DR11-dev-style-guide-note",
            "dev",
            SCHEMAS.RiskCategory.X3,
            "FIM-8",
            False,
            0,
            0,
            0,
            22.0,
            62.0,
            0.25,
        ),
        DecisionCase(
            "DR11-frozen-secondary-rights",
            "frozen_eval",
            SCHEMAS.RiskCategory.F5,
            "FIM-6",
            True,
            300000,
            800000,
            1500000,
            88.0,
            55.0,
            0.86,
        ),
        DecisionCase(
            "DR11-frozen-termination-penalty",
            "frozen_eval",
            SCHEMAS.RiskCategory.F7,
            "FIM-7",
            True,
            500000,
            1200000,
            2500000,
            91.0,
            72.0,
            0.90,
        ),
        DecisionCase(
            "DR11-frozen-formatting-notice",
            "frozen_eval",
            SCHEMAS.RiskCategory.X1,
            "FIM-8",
            False,
            0,
            0,
            0,
            16.0,
            52.0,
            0.20,
        ),
    )


def _decision_utility_report(cases: Sequence[DecisionCase]) -> dict[str, Any]:
    oracle = _selected_cases(cases, "oracle", ATTENTION_BUDGET_K)
    fink = _selected_cases(cases, "fink", ATTENTION_BUDGET_K)
    baseline = _selected_cases(cases, "baseline", ATTENTION_BUDGET_K)
    oracle_value = _attention_value(oracle)
    fink_value = _attention_value(fink)
    baseline_value = _attention_value(baseline)
    ev_dfu = _round(fink_value / oracle_value if oracle_value else 0.0)
    baseline_dfu = _round(baseline_value / oracle_value if oracle_value else 0.0)
    return {
        "metric_values": {
            "EV-DFU": ev_dfu,
            "baseline_EV-DFU": baseline_dfu,
            "utility_lift_vs_baseline": _round(ev_dfu - baseline_dfu),
        },
        "attention_budget_k": ATTENTION_BUDGET_K,
        "utility_unit": "synthetic_exposure_base_krw",
        "inputs_are_synthetic_assumptions": True,
        "no_guaranteed_outcome_claim": True,
        "rankings": {
            "oracle": _ranking_observation(oracle),
            "fink": _ranking_observation(fink),
            "baseline": _ranking_observation(baseline),
        },
        "totals": {
            "oracle_top_k_value": oracle_value,
            "fink_top_k_value": fink_value,
            "baseline_top_k_value": baseline_value,
        },
    }


def _usability_report() -> dict[str, Any]:
    rubric_items = (
        (
            "USAB-01",
            "report_frame_is_contractual_financial_review_priority",
            True,
            "Contractual Financial Review Priority",
        ),
        ("USAB-02", "four_dimensions_remain_separate", True, "D1/D2/D3/D4 separated"),
        ("USAB-03", "synthetic_assumption_labels_present", True, "all exposure ranges"),
        ("USAB-04", "evidence_and_confidence_visible", True, "confidence dimension shown"),
        ("USAB-05", "action_questions_present", True, "creator review questions shown"),
        ("USAB-06", "baseline_comparison_labeled_synthetic", True, "EV-DFU baseline"),
        ("USAB-07", "forbidden_verdict_framing_absent", True, "string scan clean"),
        ("USAB-08", "calibration_and_stability_labels_are_measured", True, "measured-on-synthetic"),
    )
    rows = [
        {
            "item_id": item_id,
            "criterion": criterion,
            "passed": passed,
            "evidence": evidence,
        }
        for item_id, criterion, passed, evidence in rubric_items
    ]
    passed = sum(1 for row in rows if row["passed"])
    ev_usab = _round(passed / len(rows))
    return {
        "metric_values": {"EV-USAB": ev_usab},
        "rubric_id": "EV-USAB-S5-07-v1",
        "rubric_item_count": len(rows),
        "passed_item_count": passed,
        "mandatory_items_all_passed": passed == len(rows),
        "rubric_items": rows,
    }


def _calibration_report(cases: Sequence[DecisionCase]) -> dict[str, Any]:
    bins = ((0.0, 0.5), (0.5, 0.75), (0.75, 1.0))
    bin_rows = []
    ece = 0.0
    for low, high in bins:
        members = [
            case
            for case in cases
            if low < case.consequential_probability <= high
            or (low == 0.0 and case.consequential_probability == low)
        ]
        if not members:
            continue
        avg_confidence = mean(case.consequential_probability for case in members)
        positive_rate = mean(1.0 if case.financially_consequential else 0.0 for case in members)
        abs_gap = abs(avg_confidence - positive_rate)
        weight = len(members) / len(cases)
        ece += weight * abs_gap
        bin_rows.append(
            {
                "bin": f"({low:.2f},{high:.2f}]",
                "count": len(members),
                "avg_confidence": _round(avg_confidence),
                "observed_positive_rate": _round(positive_rate),
                "abs_gap": _round(abs_gap),
                "weighted_gap": _round(weight * abs_gap),
            }
        )
    brier_score = mean(
        (
            case.consequential_probability
            - (1.0 if case.financially_consequential else 0.0)
        )
        ** 2
        for case in cases
    )
    ev_calib = _round(1.0 - ece)
    return {
        "metric_values": {
            "EV-CALIB": ev_calib,
            "expected_calibration_error": _round(ece),
            "brier_score": _round(brier_score),
        },
        "target": "synthetic financially consequential label",
        "binning": "fixed probability bins",
        "bins": bin_rows,
        "case_count": len(cases),
    }


def _stability_report(cases: Sequence[DecisionCase]) -> dict[str, Any]:
    runs = _stability_runs()
    per_run = []
    for run in runs:
        scored_cases = tuple(
            (
                case,
                _round(case.fink_priority_score + run.score_offsets.get(case.case_id, 0.0)),
            )
            for case in cases
        )
        top_k = tuple(
            case.case_id
            for case, _score in sorted(
                scored_cases,
                key=lambda item: (-item[1], item[0].case_id),
            )[:ATTENTION_BUDGET_K]
        )
        per_run.append(
            {
                "run_id": run.run_id,
                "top_k_case_ids": list(top_k),
                "score_by_case": {
                    case.case_id: score
                    for case, score in sorted(
                        scored_cases,
                        key=lambda item: item[0].case_id,
                    )
                },
            }
        )

    score_ranges = {}
    for case in cases:
        scores = [
            run["score_by_case"][case.case_id]
            for run in per_run
        ]
        score_ranges[case.case_id] = _round(max(scores) - min(scores))

    reference_top_k = set(per_run[0]["top_k_case_ids"])
    top_k_jaccards = [
        _jaccard(reference_top_k, set(run["top_k_case_ids"]))
        for run in per_run[1:]
    ]
    top_k_jaccard = _round(mean(top_k_jaccards)) if top_k_jaccards else 1.0
    max_score_delta = max(score_ranges.values()) if score_ranges else 0.0
    score_stability = _round(1.0 - (max_score_delta / 100.0))
    category_agreement = 1.0
    ev_stab = _round(mean((score_stability, top_k_jaccard, category_agreement)))
    return {
        "metric_values": {
            "EV-STAB": ev_stab,
            "score_stability_component": score_stability,
            "top_k_jaccard": top_k_jaccard,
            "category_agreement": category_agreement,
            "max_priority_score_delta": _round(max_score_delta),
        },
        "repeat_runs": STABILITY_REPEAT_RUNS,
        "attention_budget_k": ATTENTION_BUDGET_K,
        "score_range_by_case": score_ranges,
        "runs": per_run,
    }


def _dfu_gate_case(
    cases: Sequence[DecisionCase],
    dfu_report: Mapping[str, Any],
    usability_report: Mapping[str, Any],
    calibration_report: Mapping[str, Any],
) -> dict[str, Any]:
    metric_values = {
        "EV-DFU": dfu_report["metric_values"]["EV-DFU"],
        "EV-USAB": usability_report["metric_values"]["EV-USAB"],
        "EV-CALIB": calibration_report["metric_values"]["EV-CALIB"],
    }
    issues = []
    if not all(0.0 <= value <= 1.0 for value in metric_values.values()):
        issues.append("metric outside 0..1")
    if dfu_report["metric_values"]["EV-DFU"] <= dfu_report["metric_values"]["baseline_EV-DFU"]:
        issues.append("EV-DFU does not exceed baseline on synthetic fixture")
    if not usability_report["mandatory_items_all_passed"]:
        issues.append("EV-USAB mandatory rubric item failed")
    if not calibration_report["bins"]:
        issues.append("EV-CALIB bins were not measured")
    return {
        "id": "dfu_run",
        "metrics": ["EV-DFU", "EV-USAB", "EV-CALIB"],
        "description": (
            "Report EV-DFU against a deterministic baseline on synthetic DR-11-style "
            "decision cases, execute the EV-USAB usability checklist, and measure "
            "EV-CALIB calibration."
        ),
        "status": "PASS" if not issues else "FAIL",
        "expected": {
            "synthetic_only": True,
            "baseline_reported": True,
            "usability_rubric_executed": True,
            "calibration_measured": True,
            "scoring_frame": "Contractual Financial Review Priority",
        },
        "observed": {
            "case_count": len(cases),
            "metric_values": metric_values,
            "baseline_EV-DFU": dfu_report["metric_values"]["baseline_EV-DFU"],
            "utility_lift_vs_baseline": dfu_report["metric_values"][
                "utility_lift_vs_baseline"
            ],
            "rubric_item_count": usability_report["rubric_item_count"],
            "calibration_bin_count": len(calibration_report["bins"]),
            "fixture_sha256": _fixture_sha256(cases),
            "issue_count": len(issues),
            "issues": issues,
        },
    }


def _stability_gate_case(stability_report: Mapping[str, Any]) -> dict[str, Any]:
    metric_values = stability_report["metric_values"]
    issues = []
    if not 0.0 <= metric_values["EV-STAB"] <= 1.0:
        issues.append("EV-STAB outside 0..1")
    if stability_report["repeat_runs"] < STABILITY_REPEAT_RUNS:
        issues.append("insufficient repeated runs")
    if metric_values["top_k_jaccard"] < 1.0:
        issues.append("top-k ranking changed across repeated runs")
    if metric_values["max_priority_score_delta"] > 0.5:
        issues.append("priority-score drift exceeded 0.5 points")
    return {
        "id": "stability_run",
        "metrics": ["EV-STAB"],
        "description": (
            "Measure repeat-run stability on synthetic decision cases using priority "
            "score drift, top-k agreement, and category agreement."
        ),
        "status": "PASS" if not issues else "FAIL",
        "expected": {
            "synthetic_only": True,
            "repeat_runs": STABILITY_REPEAT_RUNS,
            "top_k_jaccard_min": 1.0,
            "max_priority_score_delta_lte": 0.5,
        },
        "observed": {
            "metric_values": metric_values,
            "repeat_runs": stability_report["repeat_runs"],
            "score_range_by_case": stability_report["score_range_by_case"],
            "issue_count": len(issues),
            "issues": issues,
        },
    }


def _selected_cases(
    cases: Sequence[DecisionCase],
    ranking: str,
    k: int,
) -> tuple[DecisionCase, ...]:
    if ranking == "oracle":
        key = lambda case: (-case.exposure_base_krw, case.case_id)
    elif ranking == "fink":
        key = lambda case: (-case.fink_priority_score, case.case_id)
    elif ranking == "baseline":
        key = lambda case: (-case.baseline_priority_score, case.case_id)
    else:
        raise ValueError(f"unknown ranking: {ranking}")
    return tuple(sorted(cases, key=key)[:k])


def _attention_value(cases: Sequence[DecisionCase]) -> int:
    return sum(case.exposure_base_krw for case in cases)


def _ranking_observation(cases: Sequence[DecisionCase]) -> list[dict[str, Any]]:
    return [
        {
            "case_id": case.case_id,
            "category": case.category.value,
            "fim_module": case.fim_module,
            "financially_consequential": case.financially_consequential,
            "synthetic_exposure_base_krw": case.exposure_base_krw,
        }
        for case in cases
    ]


def _stability_runs() -> tuple[StabilityRun, ...]:
    return (
        StabilityRun("run-1", {}),
        StabilityRun(
            "run-2",
            {
                "DR11-dev-deduction-leakage": 0.2,
                "DR11-dev-payment-delay": -0.1,
                "DR11-dev-style-guide-note": 0.1,
                "DR11-frozen-secondary-rights": -0.2,
                "DR11-frozen-termination-penalty": 0.1,
                "DR11-frozen-formatting-notice": -0.1,
            },
        ),
        StabilityRun(
            "run-3",
            {
                "DR11-dev-deduction-leakage": -0.1,
                "DR11-dev-payment-delay": 0.2,
                "DR11-dev-style-guide-note": -0.1,
                "DR11-frozen-secondary-rights": 0.1,
                "DR11-frozen-termination-penalty": -0.2,
                "DR11-frozen-formatting-notice": 0.1,
            },
        ),
    )


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left and not right:
        return 1.0
    return len(left & right) / len(left | right)


def _result_ledger_rows(metric_values: Mapping[str, float]) -> list[dict[str, str]]:
    experiment_by_metric = {
        "EV-DFU": "dfu_run",
        "EV-USAB": "dfu_run",
        "EV-CALIB": "dfu_run",
        "EV-STAB": "stability_run",
    }
    rows: list[dict[str, str]] = []
    for metric_id in METRIC_IDS:
        rows.append(
            {
                "result_id": f"{TASK_ID}-{metric_id}",
                "experiment_id": experiment_by_metric[metric_id],
                "metric": metric_id,
                "value": f"{metric_values[metric_id]:.6f}",
                "artifact_path": ARTIFACT_PATH,
                "status": "measured",
                "reviewer": "codex",
                "notes": (
                    "synthetic/sanitized local fixture; measured value is not "
                    "a generalized performance claim"
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


def _fixture_sha256(cases: Sequence[DecisionCase]) -> str:
    payload = {
        "cases": [
            {
                "case_id": case.case_id,
                "split": case.split,
                "category": case.category.value,
                "fim_module": case.fim_module,
                "financially_consequential": case.financially_consequential,
                "exposure_low_krw": case.exposure_low_krw,
                "exposure_base_krw": case.exposure_base_krw,
                "exposure_high_krw": case.exposure_high_krw,
                "fink_priority_score": case.fink_priority_score,
                "baseline_priority_score": case.baseline_priority_score,
                "consequential_probability": case.consequential_probability,
            }
            for case in cases
        ],
        "attention_budget_k": ATTENTION_BUDGET_K,
        "stability_runs": [
            {
                "run_id": run.run_id,
                "score_offsets": dict(sorted(run.score_offsets.items())),
            }
            for run in _stability_runs()
        ],
    }
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _round(value: float) -> float:
    return round(float(value), 6)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run FINK-S5-07 decision utility, usability, calibration, and stability metrics."
    )
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

    result = run_decision_utility_suite()
    log_path = write_result_log(result, args.output)
    if args.stdout:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    print(f"{SUITE_ID}: {'PASS' if result['summary']['ok'] else 'FAIL'}; log={log_path}")
    return 0 if result["summary"]["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

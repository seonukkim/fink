from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
if SRC_ROOT.as_posix() not in sys.path:
    sys.path.insert(0, SRC_ROOT.as_posix())

from fink import finance as FINANCE  # noqa: E402
from fink import schemas as SCHEMAS  # noqa: E402
from fink.scoring import (  # noqa: E402
    aggregate_document_signals,
    load_scoring_config,
)


TASK_ID = "FINK-S5-05"
SUITE_ID = "formula_unit_suite"
RESULT_LOG_PATH = Path(__file__).with_name("formula_unit_suite_results.json")

REGISTERED_CASE_IDS = (
    "FIM-1-T1",
    "FIM-2-T1",
    "FIM-3-T1",
    "FIM-4-T1",
    "FIM-5-T1",
    "FIM-6-T1",
    "FIM-7-T1",
    "FIM-7-T2",
    "FIM-8-T1",
    "SC-AGG-T1",
    "SC-AGG-T2",
    "SC-AGG-T3",
    "SC-SEP-T1",
)


@dataclass(frozen=True)
class FormulaCase:
    case_id: str
    metric_ids: tuple[str, ...]
    description: str
    run: Callable[[], dict[str, Any]]


def run_formula_unit_suite() -> dict[str, Any]:
    cases = [_run_case(case) for case in _registered_cases()]
    passed = sum(1 for case in cases if case["status"] == "PASS")
    failed = len(cases) - passed
    return {
        "suite": SUITE_ID,
        "task_id": TASK_ID,
        "metrics": {
            "EV-UNIT": _metric_status(cases, "EV-UNIT"),
            "EV-FINSCEN": _metric_status(cases, "EV-FINSCEN"),
        },
        "registered_cases": list(REGISTERED_CASE_IDS),
        "summary": {
            "total": len(cases),
            "passed": passed,
            "failed": failed,
            "ok": failed == 0,
        },
        "cases": cases,
    }


def write_result_log(result: Mapping[str, Any], path: Path | str = RESULT_LOG_PATH) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return destination


def _registered_cases() -> tuple[FormulaCase, ...]:
    return (
        FormulaCase(
            "FIM-1-T1",
            ("EV-UNIT", "EV-FINSCEN"),
            "Revenue-base and deduction leakage matches the worked KRW vector.",
            _fim_1_t1,
        ),
        FormulaCase(
            "FIM-2-T1",
            ("EV-UNIT", "EV-FINSCEN"),
            "Payment-delay present-value loss remains separate from nominal unpaid amount.",
            _fim_2_t1,
        ),
        FormulaCase(
            "FIM-3-T1",
            ("EV-UNIT", "EV-FINSCEN"),
            "MG/advance recoupment reports 18/9/5 months by low/base/high sales.",
            _fim_3_t1,
        ),
        FormulaCase(
            "FIM-4-T1",
            ("EV-UNIT", "EV-FINSCEN"),
            "Additional-work scenario cost matches low/base/high user assumptions.",
            _fim_4_t1,
        ),
        FormulaCase(
            "FIM-5-T1",
            ("EV-UNIT", "EV-FINSCEN"),
            "Exclusivity opportunity-cost scenario matches the discounted worked example.",
            _fim_5_t1,
        ),
        FormulaCase(
            "FIM-6-T1",
            ("EV-UNIT", "EV-FINSCEN"),
            "Secondary-rights value comes only from user supplied scenarios.",
            _fim_6_t1,
        ),
        FormulaCase(
            "FIM-7-T1",
            ("EV-UNIT", "EV-FINSCEN"),
            "Capped liability reports max nominal exposure and expected penalty.",
            _fim_7_t1,
        ),
        FormulaCase(
            "FIM-7-T2",
            ("EV-UNIT", "EV-FINSCEN"),
            "Uncapped liability without probability emits no invented monetary number.",
            _fim_7_t2,
        ),
        FormulaCase(
            "FIM-8-T1",
            ("EV-UNIT", "EV-FINSCEN"),
            "Evidence opacity widens low/high while preserving base and score.",
            _fim_8_t1,
        ),
        FormulaCase(
            "SC-AGG-T1",
            ("EV-UNIT",),
            "B/C practice references contribute zero to review-priority scoring.",
            _sc_agg_t1,
        ),
        FormulaCase(
            "SC-AGG-T2",
            ("EV-UNIT",),
            "Category and document scores saturate inside the 0-100 range.",
            _sc_agg_t2,
        ),
        FormulaCase(
            "SC-AGG-T3",
            ("EV-UNIT",),
            "Low confidence lowers D4 without lowering priority below the confidence floor.",
            _sc_agg_t3,
        ),
        FormulaCase(
            "SC-SEP-T1",
            ("EV-UNIT", "EV-FINSCEN"),
            "Exposure types stay partitioned with no cross-type grand total.",
            _sc_sep_t1,
        ),
    )


def _run_case(case: FormulaCase) -> dict[str, Any]:
    result = case.run()
    return {
        "id": case.case_id,
        "metrics": list(case.metric_ids),
        "description": case.description,
        "status": "PASS" if result.pop("ok") else "FAIL",
        **result,
    }


def _metric_status(cases: Sequence[Mapping[str, Any]], metric_id: str) -> dict[str, Any]:
    metric_cases = [case for case in cases if metric_id in case["metrics"]]
    passed = sum(1 for case in metric_cases if case["status"] == "PASS")
    failed = len(metric_cases) - passed
    return {
        "total": len(metric_cases),
        "passed": passed,
        "failed": failed,
        "ok": failed == 0,
    }


def _fim_1_t1() -> dict[str, Any]:
    result = FINANCE.fim1_revenue_base_deduction_leakage(
        gross_sales=Decimal("10000000"),
        refunds=Decimal("500000"),
        explicitly_allowed_deductions=Decimal("1000000"),
        revenue_share_rate=Decimal("0.7"),
        fixed_fee=Decimal("0"),
        advance_recoupment=Decimal("0"),
        open_ended_deductions=FINANCE.DecimalRange(
            low=Decimal("0"),
            base=Decimal("1000000"),
            high=Decimal("2000000"),
        ),
    )
    observed = {
        "nominal_leakage": _exposure_range(result.nominal_leakage),
        "maximum_nominal_leakage": _decimal(result.maximum_nominal_leakage),
        "exposure_type": result.nominal_leakage.exposure_type.value,
    }
    expected = {
        "nominal_leakage": {"low": "0.0", "base": "700000.0", "high": "1400000.0"},
        "maximum_nominal_leakage": "1400000.0",
        "exposure_type": "nominal_leakage",
    }
    return {
        "ok": observed == expected,
        "tolerance": "exact",
        "expected": expected,
        "observed": observed,
    }


def _fim_2_t1() -> dict[str, Any]:
    result = FINANCE.fim2_payment_delay_present_value_loss(
        delayed_amount=Decimal("10000000"),
        annual_discount_rate=Decimal("0.05"),
        delay_days=Decimal("180"),
    )
    pv_krw = _krw(result.delay_pv_loss)
    ok = (
        result.nominal_amount == Decimal("10000000")
        and _within_percent(result.delay_pv_loss, Decimal("237700"), Decimal("0.01"))
        and result.present_value_loss.nominal_amount == Decimal("10000000")
        and result.present_value_loss.exposure_type is SCHEMAS.ExposureType.PRESENT_VALUE_LOSS
        and result.present_value_loss.base != result.nominal_amount
    )
    return {
        "ok": ok,
        "tolerance": "+/-1% on delay_pv_loss",
        "expected": {
            "nominal_amount": "10000000",
            "delay_pv_loss_krw": "237700",
            "exposure_type": "present_value_loss",
        },
        "observed": {
            "nominal_amount": _decimal(result.nominal_amount),
            "delay_pv_loss": _decimal(result.delay_pv_loss),
            "delay_pv_loss_krw": str(pv_krw),
            "exposure_type": result.present_value_loss.exposure_type.value,
        },
    }


def _fim_3_t1() -> dict[str, Any]:
    result = FINANCE.fim3_mg_advance_recoupment(
        advance=Decimal("12000000"),
        cumulative_recouped=Decimal("0"),
        revenue_share_rate=Decimal("0.7"),
        monthly_net_sales=FINANCE.DecimalRange(
            low=Decimal("1000000"),
            base=Decimal("2000000"),
            high=Decimal("4000000"),
        ),
    )
    observed = {
        "months_to_recoup": list(result.months_to_recoup),
        "deferral_base": _decimal(result.deferral.base),
        "sales_label_note_has_monthly_sales": "monthly sales" in result.sales_label_note,
    }
    expected = {
        "months_to_recoup": [18, 9, 5],
        "deferral_base": "12000000",
        "sales_label_note_has_monthly_sales": True,
    }
    return {
        "ok": observed == expected,
        "tolerance": "exact",
        "expected": expected,
        "observed": observed,
    }


def _fim_4_t1() -> dict[str, Any]:
    result = FINANCE.fim4_unpaid_additional_work_cost(
        unpaid_revision_units=Decimal("5"),
        hours_per_unit=Decimal("8"),
        creator_hourly_value=FINANCE.DecimalRange(
            low=Decimal("20000"),
            base=Decimal("30000"),
            high=Decimal("40000"),
        ),
    )
    observed = {
        "unpaid_work_cost": _exposure_range(result.unpaid_work_cost),
        "module": result.unpaid_work_cost.module.value,
        "exposure_type": result.unpaid_work_cost.exposure_type.value,
        "synthetic_assumption_labeled": _has_assumption(
            result.unpaid_work_cost,
            "synthetic assumption",
        ),
    }
    expected = {
        "unpaid_work_cost": {"low": "800000", "base": "1200000", "high": "1600000"},
        "module": "FIM-4",
        "exposure_type": "opportunity_cost",
        "synthetic_assumption_labeled": True,
    }
    return {
        "ok": observed == expected,
        "tolerance": "exact",
        "expected": expected,
        "observed": observed,
    }


def _fim_5_t1() -> dict[str, Any]:
    result = FINANCE.fim5_exclusivity_renewal_opportunity_cost(
        exclusivity_duration_months=Decimal("12"),
        alternative_monthly_revenue=Decimal("1000000"),
        scenario_probability=FINANCE.DecimalRange(
            low=Decimal("0.25"),
            base=Decimal("0.5"),
            high=Decimal("0.75"),
        ),
        annual_discount_rate=Decimal("0.05"),
    )
    low = result.opportunity_cost.low or Decimal("0")
    base = result.opportunity_cost.base or Decimal("0")
    high = result.opportunity_cost.high or Decimal("0")
    ok = (
        _within_percent(low, Decimal("2922500"), Decimal("0.01"))
        and _within_percent(base, Decimal("5845000"), Decimal("0.01"))
        and _within_percent(high, Decimal("8767500"), Decimal("0.01"))
        and result.opportunity_cost.module is SCHEMAS.FimModule.FIM_5
        and _has_assumption(result.opportunity_cost, "synthetic assumption")
    )
    return {
        "ok": ok,
        "tolerance": "+/-1% on discounted opportunity-cost range",
        "expected": {
            "opportunity_cost_krw": {"low": "2922500", "base": "5845000", "high": "8767500"},
            "module": "FIM-5",
            "synthetic_assumption_labeled": True,
        },
        "observed": {
            "opportunity_cost": _exposure_range(result.opportunity_cost),
            "opportunity_cost_krw": {
                "low": str(_krw(low)),
                "base": str(_krw(base)),
                "high": str(_krw(high)),
            },
            "module": result.opportunity_cost.module.value,
            "synthetic_assumption_labeled": _has_assumption(
                result.opportunity_cost,
                "synthetic assumption",
            ),
        },
    }


def _fim_6_t1() -> dict[str, Any]:
    result = FINANCE.fim6_ip_secondary_rights_scenario_value(
        secondary_rights=(
            {"type": "overseas", "value": Decimal("5000000"), "prob": Decimal("0.4")},
            {"type": "merchandise", "value": Decimal("3000000"), "prob": Decimal("0.2")},
        )
    )
    observed = {
        "scenario_value": _exposure_range(result.scenario_value),
        "module": result.scenario_value.module.value,
        "auto_valued_from_contract_text": result.auto_valued_from_contract_text,
        "right_types": list(result.right_types),
    }
    expected = {
        "scenario_value": {"low": "2600000.0", "base": "2600000.0", "high": "2600000.0"},
        "module": "FIM-6",
        "auto_valued_from_contract_text": False,
        "right_types": ["overseas", "merchandise"],
    }
    return {
        "ok": observed == expected,
        "tolerance": "exact",
        "expected": expected,
        "observed": observed,
    }


def _fim_7_t1() -> dict[str, Any]:
    result = FINANCE.fim7_penalty_liability_exposure(
        explicit_penalty_cap=Decimal("5000000"),
        penalty_probability=Decimal("0.1"),
        scenario_amount=Decimal("5000000"),
    )
    observed = {
        "max_nominal_exposure": _decimal(result.max_nominal_exposure),
        "expected_penalty": _decimal(result.expected_penalty),
        "liability_exposure_base": _decimal(result.liability_exposure.base),
        "liability_nominal_amount": _decimal(result.liability_exposure.nominal_amount),
    }
    expected = {
        "max_nominal_exposure": "5000000",
        "expected_penalty": "500000.0",
        "liability_exposure_base": "500000.0",
        "liability_nominal_amount": "5000000",
    }
    return {
        "ok": observed == expected,
        "tolerance": "exact",
        "expected": expected,
        "observed": observed,
    }


def _fim_7_t2() -> dict[str, Any]:
    result = FINANCE.fim7_penalty_liability_exposure(is_uncapped=True)
    observed = {
        "max_nominal_exposure": _decimal(result.max_nominal_exposure),
        "expected_penalty": _decimal(result.expected_penalty),
        "uncapped_signal": result.uncapped_signal,
        "user_input_required": result.liability_exposure.is_user_input_required,
        "liability_exposure": _exposure_range(result.liability_exposure),
        "has_uncapped_flag": "uncapped" in result.liability_exposure.uncertainty_flags,
    }
    expected = {
        "max_nominal_exposure": None,
        "expected_penalty": None,
        "uncapped_signal": True,
        "user_input_required": True,
        "liability_exposure": {"low": None, "base": None, "high": None},
        "has_uncapped_flag": True,
    }
    return {
        "ok": observed == expected,
        "tolerance": "exact null/no-number behavior",
        "expected": expected,
        "observed": observed,
    }


def _fim_8_t1() -> dict[str, Any]:
    config = load_scoring_config()
    base_exposure = SCHEMAS.MonetaryExposureEstimate(
        module=SCHEMAS.FimModule.FIM_1,
        exposure_type=SCHEMAS.ExposureType.NOMINAL_LEAKAGE,
        is_user_input_required=False,
        assumptions=(),
        low=Decimal("4550000"),
        base=Decimal("5250000"),
        high=Decimal("5950000"),
    )
    result = FINANCE.fim8_evidence_opacity_uncertainty(
        base_exposure,
        opacity_flags=("missing_settlement_records", "no_audit_access"),
        opacity_weights=config.fim8_opacity_weights,
    )
    adjusted = result.adjusted_exposure
    report = FINANCE.fim8_uncertainty_test()
    observed = {
        "band_widen_factor": _decimal(result.band_widen_factor),
        "adjusted_krw": {
            "low": str(_krw(adjusted.low or Decimal("0"))),
            "base": str(_krw(adjusted.base or Decimal("0"))),
            "high": str(_krw(adjusted.high or Decimal("0"))),
        },
        "base_unchanged": report.fim_8_t1_base_unchanged,
        "score_unchanged": report.fim_8_t1_score_unchanged,
        "data_completeness_down": report.fim_8_t1_data_completeness_down,
    }
    expected = {
        "band_widen_factor": "1.2",
        "adjusted_krw": {"low": "3791667", "base": "5250000", "high": "7140000"},
        "base_unchanged": True,
        "score_unchanged": True,
        "data_completeness_down": True,
    }
    return {
        "ok": observed == expected,
        "tolerance": "exact KRW rounding for widened range",
        "expected": expected,
        "observed": observed,
    }


def _sc_agg_t1() -> dict[str, Any]:
    config = load_scoring_config()
    bc_only = _signal(
        "RS-SC-AGG-T1-BC-ONLY",
        SCHEMAS.RiskCategory.F2,
        score_eligible=False,
        practice_reference=True,
        evidence_ids=(),
        severity=1.0,
    )
    grounded = _signal(
        "RS-SC-AGG-T1-A1",
        SCHEMAS.RiskCategory.F2,
        evidence_ids=("EV-A1-F2",),
        confidence=1.0,
        severity=1.0,
    )
    bc_result = aggregate_document_signals((bc_only,), config=config)
    grounded_result = aggregate_document_signals(
        (grounded,),
        config=config,
        evidence_authority_tiers={"EV-A1-F2": "A1"},
    )
    mixed_result = aggregate_document_signals(
        (bc_only, grounded),
        config=config,
        evidence_authority_tiers={"EV-A1-F2": "A1"},
    )
    observed = {
        "bc_review_priority_score": bc_result.review_priority_score,
        "bc_category_score": bc_result.category_scores[SCHEMAS.RiskCategory.F2],
        "mixed_equals_grounded": (
            mixed_result.review_priority_score == grounded_result.review_priority_score
            and mixed_result.category_scores[SCHEMAS.RiskCategory.F2]
            == grounded_result.category_scores[SCHEMAS.RiskCategory.F2]
        ),
        "bc_contribution": mixed_result.contributions[0].contribution,
        "bc_practice_reference": mixed_result.contributions[0].practice_reference,
    }
    expected = {
        "bc_review_priority_score": 0,
        "bc_category_score": 0.0,
        "mixed_equals_grounded": True,
        "bc_contribution": 0.0,
        "bc_practice_reference": True,
    }
    return {
        "ok": observed == expected,
        "tolerance": "exact",
        "expected": expected,
        "observed": observed,
    }


def _sc_agg_t2() -> dict[str, Any]:
    config = load_scoring_config()
    signals = tuple(
        _signal(
            f"RS-SC-AGG-T2-{idx}",
            SCHEMAS.RiskCategory.F7,
            evidence_ids=(f"EV-A0-{idx}",),
            confidence=1.0,
            severity=1.0,
        )
        for idx in range(500)
    )
    tiers = {f"EV-A0-{idx}": "A0" for idx in range(500)}
    result = aggregate_document_signals(
        signals,
        config=config,
        evidence_authority_tiers=tiers,
    )
    category_scores = result.category_scores
    all_category_scores_bounded = all(0.0 <= score <= 100.0 for score in category_scores.values())
    observed = {
        "f7_category_score": category_scores[SCHEMAS.RiskCategory.F7],
        "review_priority_score": result.review_priority_score,
        "all_category_scores_bounded": all_category_scores_bounded,
    }
    return {
        "ok": (
            observed["f7_category_score"] > 99.0
            and 0 <= result.review_priority_score <= 100
            and all_category_scores_bounded
        ),
        "tolerance": "bounded 0-100 with F7 saturation > 99",
        "expected": {
            "f7_category_score": ">99 and <=100",
            "review_priority_score": "0..100",
            "all_category_scores_bounded": True,
        },
        "observed": observed,
    }


def _sc_agg_t3() -> dict[str, Any]:
    config = load_scoring_config()
    low_confidence_signal = _signal(
        "RS-SC-AGG-T3-LOW",
        SCHEMAS.RiskCategory.F3,
        evidence_ids=("EV-A1-LOW",),
        confidence=0.05,
        severity=1.0,
    )
    floor_confidence_signal = _signal(
        "RS-SC-AGG-T3-FLOOR",
        SCHEMAS.RiskCategory.F3,
        evidence_ids=("EV-A1-FLOOR",),
        confidence=config.conf_floor,
        severity=1.0,
    )
    low_result = aggregate_document_signals(
        (low_confidence_signal,),
        config=config,
        evidence_authority_tiers={"EV-A1-LOW": "A1"},
    )
    floor_result = aggregate_document_signals(
        (floor_confidence_signal,),
        config=config,
        evidence_authority_tiers={"EV-A1-FLOOR": "A1"},
    )
    observed = {
        "priority_same_as_floor": low_result.review_priority_score
        == floor_result.review_priority_score,
        "category_score_same_as_floor": low_result.category_scores[SCHEMAS.RiskCategory.F3]
        == floor_result.category_scores[SCHEMAS.RiskCategory.F3],
        "overall_confidence_lower": low_result.confidence.overall_confidence
        < floor_result.confidence.overall_confidence,
        "driver_present": "low_signal_confidence_floored_for_priority_only"
        in low_result.confidence.drivers,
    }
    expected = {
        "priority_same_as_floor": True,
        "category_score_same_as_floor": True,
        "overall_confidence_lower": True,
        "driver_present": True,
    }
    return {
        "ok": observed == expected,
        "tolerance": "exact invariant",
        "expected": expected,
        "observed": observed,
    }


def _sc_sep_t1() -> dict[str, Any]:
    report = FINANCE.exposure_separation_test()
    fim1 = FINANCE.fim1_revenue_base_deduction_leakage(
        Decimal("10000000"),
        Decimal("500000"),
        Decimal("1000000"),
        Decimal("0.7"),
        open_ended_deductions=FINANCE.DecimalRange(
            low=Decimal("0"),
            base=Decimal("1000000"),
            high=Decimal("2000000"),
        ),
    )
    fim2 = FINANCE.fim2_payment_delay_present_value_loss(
        Decimal("10000000"),
        Decimal("0.05"),
        Decimal("180"),
    )
    subtotals = FINANCE.exposure_type_subtotals(
        (fim1.nominal_leakage, fim2.present_value_loss)
    )
    observed = {
        "exposure_types": list(report.exposure_types),
        "no_cross_type_summation": report.sc_sep_t1_no_cross_type_summation,
        "grand_total_present": "grand_total" in subtotals,
    }
    expected_types = [
        "deferral",
        "liability_exposure",
        "nominal_leakage",
        "opportunity_cost",
        "present_value_loss",
    ]
    return {
        "ok": (
            report.ok
            and observed["exposure_types"] == expected_types
            and not observed["grand_total_present"]
        ),
        "tolerance": "exact exposure-type set",
        "expected": {
            "exposure_types": expected_types,
            "no_cross_type_summation": True,
            "grand_total_present": False,
        },
        "observed": observed,
    }


def _signal(
    signal_id: str,
    category: Any,
    *,
    clause_id: str = "clause-1",
    score_eligible: bool = True,
    practice_reference: bool = False,
    evidence_ids: tuple[str, ...] = ("EV-A1-1",),
    confidence: float = 0.9,
    severity: float = 0.8,
) -> Any:
    return SCHEMAS.RiskSignal(
        signal_id=signal_id,
        clause_id=clause_id,
        risk_category=category,
        detector=SCHEMAS.DetectorType.RULE,
        fired=True,
        score_eligible=score_eligible,
        practice_reference=practice_reference,
        signal_confidence=confidence,
        is_missing_protection=False,
        grounding_evidence_ids=evidence_ids if score_eligible else None,
        severity_raw=severity,
    )


def _within_percent(observed: Decimal, expected: Decimal, pct: Decimal) -> bool:
    return abs(observed - expected) <= abs(expected) * pct


def _krw(value: Decimal) -> int:
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _decimal(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _exposure_range(exposure: Any) -> dict[str, str | None]:
    return {
        "low": _decimal(exposure.low),
        "base": _decimal(exposure.base),
        "high": _decimal(exposure.high),
    }


def _has_assumption(exposure: Any, needle: str) -> bool:
    return any(needle in item for item in exposure.assumptions)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run FINK-S5-05 formula unit suite.")
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

    result = run_formula_unit_suite()
    log_path = write_result_log(result, args.output)
    if args.stdout:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    print(f"{SUITE_ID}: {'PASS' if result['summary']['ok'] else 'FAIL'}; log={log_path}")
    return 0 if result["summary"]["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

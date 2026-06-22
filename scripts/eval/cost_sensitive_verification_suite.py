from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
if SRC_ROOT.as_posix() not in sys.path:
    sys.path.insert(0, SRC_ROOT.as_posix())


TASK_ID = "FINK-COST-01"
SUITE_ID = "cost_sensitive_verification_evaluation"
DATA_DIR = REPO_ROOT / "data" / "eval" / "fink_cost_01"
DEV_FIXTURE_PATH = DATA_DIR / "dev_cost_fixtures.jsonl"
FROZEN_FIXTURE_PATH = DATA_DIR / "frozen_cost_fixtures.jsonl"
RESULT_LOG_PATH = Path(__file__).with_name("cost_sensitive_verification_results.json")
ARTIFACT_PATH = "scripts/eval/cost_sensitive_verification_results.json"
PAPER_SECTIONS = ("05_experiments.md",)
REGISTERED_GATE_IDS = (
    "dev_threshold_selection",
    "frozen_fixed_threshold",
    "fixture_cost_derivation",
    "normalized_missing_input_analysis",
    "verdict_free_metric_labels",
)
METRIC_IDS = (
    "EV-MISSED-EXPOSURE-COST",
    "EV-VERIFICATION-EFFORT-COST",
    "EV-TOTAL-DECISION-COST",
    "EV-FALSE-TRIGGER-RATE",
    "EV-TRIGGER-RECALL",
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
FIXTURE_BOUNDARY = (
    "Synthetic-only cost fixtures for FINK-COST-01; no real contract, private "
    "corpus passage, PDF, ZIP, model weight, token, or user upload is included."
)


@dataclass(frozen=True)
class CurrencyInputs:
    exposure_amount: Decimal
    exposure_currency: str
    verification_minutes: Decimal
    hourly_amount: Decimal
    hourly_currency: str

    @property
    def verification_effort_cost(self) -> Decimal:
        return (self.verification_minutes / Decimal("60")) * self.hourly_amount


@dataclass(frozen=True)
class CurrencyDecision:
    fixture_id: str
    split: str
    review_priority_score: Decimal
    threshold: Decimal
    trigger: bool
    oracle_has_exposure: bool
    outcome: str
    missed_exposure_cost: Decimal
    verification_effort_cost: Decimal
    total_decision_cost: Decimal
    currency: str


@dataclass(frozen=True)
class NormalizedDecision:
    fixture_id: str
    split: str
    review_priority_score: Decimal
    threshold: Decimal
    trigger: bool
    oracle_has_exposure: bool
    outcome: str
    normalized_decision_loss: Decimal
    sensitivity_by_scenario: Mapping[str, Decimal]


def run_cost_sensitive_verification_suite(
    *,
    dev_path: Path | str = DEV_FIXTURE_PATH,
    frozen_path: Path | str = FROZEN_FIXTURE_PATH,
) -> dict[str, Any]:
    dev_fixtures = _read_jsonl(Path(dev_path))
    frozen_fixtures = _read_jsonl(Path(frozen_path))
    _validate_fixture_collection(dev_fixtures, "dev")
    _validate_fixture_collection(frozen_fixtures, "frozen_eval")

    dev_complete = tuple(row for row in dev_fixtures if _has_complete_currency_inputs(row))
    frozen_complete = tuple(row for row in frozen_fixtures if _has_complete_currency_inputs(row))
    dev_missing = tuple(row for row in dev_fixtures if not _has_complete_currency_inputs(row))
    frozen_missing = tuple(row for row in frozen_fixtures if not _has_complete_currency_inputs(row))

    selection = _select_threshold_on_dev(dev_complete)
    threshold = selection["selected_threshold_decimal"]
    dev_currency_report = _currency_report(dev_complete, threshold, "dev")
    frozen_currency_report = _currency_report(frozen_complete, threshold, "frozen_eval")
    dev_normalized_report = _normalized_report(dev_missing, threshold, "dev")
    frozen_normalized_report = _normalized_report(frozen_missing, threshold, "frozen_eval")

    metric_values = {
        metric_id: frozen_currency_report["metric_values"][metric_id]
        for metric_id in METRIC_IDS
    }
    cases = _gate_cases(
        dev_complete=dev_complete,
        frozen_complete=frozen_complete,
        dev_missing=dev_missing,
        frozen_missing=frozen_missing,
        selection=selection,
        dev_currency_report=dev_currency_report,
        frozen_currency_report=frozen_currency_report,
        dev_normalized_report=dev_normalized_report,
        frozen_normalized_report=frozen_normalized_report,
        metric_values=metric_values,
    )
    passed = sum(1 for case in cases if case["status"] == "PASS")
    failed = len(cases) - passed
    result = {
        "suite": SUITE_ID,
        "task_id": TASK_ID,
        "paper_sections": list(PAPER_SECTIONS),
        "registered_gates": list(REGISTERED_GATE_IDS),
        "metrics": {metric_id: _metric_status(cases, metric_id) for metric_id in METRIC_IDS},
        "metric_definitions": _metric_definitions(),
        "metric_values": metric_values,
        "threshold_selection": {
            "selected_on_split": "dev",
            "objective": "minimize_total_decision_cost_on_complete_currency_dev_fixtures",
            "selected_threshold": _decimal_text(threshold),
            "candidate_count": len(selection["candidate_rows"]),
            "candidate_rows": selection["candidate_rows"],
            "frozen_eval_used_for_threshold_selection": False,
            "frozen_eval_uses_fixed_dev_threshold": True,
        },
        "reports": {
            "dev_complete_currency": dev_currency_report,
            "frozen_complete_currency": frozen_currency_report,
            "dev_missing_inputs_normalized": dev_normalized_report,
            "frozen_missing_inputs_normalized": frozen_normalized_report,
        },
        "fixtures": {
            "dev_fixture_path": _display_path(Path(dev_path)),
            "frozen_fixture_path": _display_path(Path(frozen_path)),
            "dev_fixture_sha256": _sha256_file(Path(dev_path)),
            "frozen_fixture_sha256": _sha256_file(Path(frozen_path)),
            "dev_count": len(dev_fixtures),
            "frozen_count": len(frozen_fixtures),
            "complete_currency_case_count": len(dev_complete) + len(frozen_complete),
            "missing_currency_case_count": len(dev_missing) + len(frozen_missing),
            "fixture_boundary": FIXTURE_BOUNDARY,
        },
        "claim_boundary": {
            "scoring_frame": "Contractual Financial Review Priority",
            "verdict_free": True,
            "no_generalized_performance_claim": True,
            "currency_values_only_from_fixtures": True,
            "normalized_loss_used_when_currency_inputs_absent": True,
        },
        "result_ledger": {
            "name": "RESULT_LEDGER",
            "columns": list(RESULT_LEDGER_COLUMNS),
            "rows": _result_ledger_rows(metric_values),
        },
        "summary": {
            "total": len(cases),
            "passed": passed,
            "failed": failed,
            "ok": failed == 0,
        },
        "cases": cases,
    }
    return result


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


def _select_threshold_on_dev(fixtures: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    if not fixtures:
        raise ValueError("at least one complete dev fixture is required")
    scores = sorted({_score(row) for row in fixtures})
    candidates = tuple(scores + [max(scores) + Decimal("0.000001")])
    rows = []
    best: dict[str, Any] | None = None
    for threshold in candidates:
        report = _currency_report(fixtures, threshold, "dev")
        row = {
            "threshold": _decimal_text(threshold),
            "missed_exposure_cost": report["metric_values"]["EV-MISSED-EXPOSURE-COST"],
            "verification_effort_cost": report["metric_values"]["EV-VERIFICATION-EFFORT-COST"],
            "total_decision_cost": report["metric_values"]["EV-TOTAL-DECISION-COST"],
            "false_trigger_rate": report["metric_values"]["EV-FALSE-TRIGGER-RATE"],
            "trigger_recall": report["metric_values"]["EV-TRIGGER-RECALL"],
        }
        rows.append(row)
        sort_key = (
            _decimal(row["total_decision_cost"]),
            _decimal(row["false_trigger_rate"]),
            -_decimal(row["trigger_recall"]),
            -threshold,
        )
        if best is None or sort_key < best["sort_key"]:
            best = {
                "selected_threshold_decimal": threshold,
                "selected_row": row,
                "sort_key": sort_key,
            }
    if best is None:
        raise ValueError("threshold selection failed")
    return {
        "selected_threshold_decimal": best["selected_threshold_decimal"],
        "selected_row": best["selected_row"],
        "candidate_rows": rows,
    }


def _currency_report(
    fixtures: Sequence[Mapping[str, Any]],
    threshold: Decimal,
    split: str,
) -> dict[str, Any]:
    decisions = tuple(_currency_decision(row, threshold) for row in fixtures)
    if any(decision.split != split for decision in decisions):
        raise ValueError(f"fixture split mismatch for {split}")
    currencies = sorted({decision.currency for decision in decisions})
    if len(currencies) > 1:
        raise ValueError(f"cannot aggregate mixed currencies for {split}: {currencies}")
    missed = sum((item.missed_exposure_cost for item in decisions), Decimal("0"))
    effort = sum((item.verification_effort_cost for item in decisions), Decimal("0"))
    total = sum((item.total_decision_cost for item in decisions), Decimal("0"))
    oracle_exposure_count = sum(1 for item in decisions if item.oracle_has_exposure)
    no_exposure_count = sum(1 for item in decisions if not item.oracle_has_exposure)
    triggered_oracle_count = sum(
        1 for item in decisions if item.oracle_has_exposure and item.trigger
    )
    false_trigger_count = sum(
        1 for item in decisions if (not item.oracle_has_exposure) and item.trigger
    )
    false_trigger_rate = (
        Decimal(false_trigger_count) / Decimal(no_exposure_count)
        if no_exposure_count
        else Decimal("0")
    )
    trigger_recall = (
        Decimal(triggered_oracle_count) / Decimal(oracle_exposure_count)
        if oracle_exposure_count
        else Decimal("0")
    )
    metric_values = {
        "EV-MISSED-EXPOSURE-COST": _decimal_text(missed),
        "EV-VERIFICATION-EFFORT-COST": _decimal_text(effort),
        "EV-TOTAL-DECISION-COST": _decimal_text(total),
        "EV-FALSE-TRIGGER-RATE": _decimal_text(false_trigger_rate),
        "EV-TRIGGER-RECALL": _decimal_text(trigger_recall),
    }
    return {
        "split": split,
        "threshold": _decimal_text(threshold),
        "case_count": len(decisions),
        "currency": currencies[0] if currencies else None,
        "currency_source": "fixture_explicit_currency_fields" if currencies else None,
        "metric_values": metric_values,
        "denominators": {
            "oracle_exposure_case_count": oracle_exposure_count,
            "no_exposure_case_count": no_exposure_count,
            "triggered_oracle_case_count": triggered_oracle_count,
            "false_trigger_case_count": false_trigger_count,
        },
        "case_rows": [_currency_decision_payload(item) for item in decisions],
    }


def _currency_decision(row: Mapping[str, Any], threshold: Decimal) -> CurrencyDecision:
    inputs = _currency_inputs(row)
    score = _score(row)
    trigger = score >= threshold
    oracle_has_exposure = bool(row["oracle"]["has_transfer_prepayment_exposure"])
    if trigger:
        effort = inputs.verification_effort_cost
        missed = Decimal("0")
        total = effort
        outcome = (
            "triggered_oracle_exposure"
            if oracle_has_exposure
            else "triggered_without_oracle_exposure"
        )
    elif oracle_has_exposure:
        effort = Decimal("0")
        missed = inputs.exposure_amount
        total = missed
        outcome = "missed_oracle_exposure"
    else:
        effort = Decimal("0")
        missed = Decimal("0")
        total = Decimal("0")
        outcome = "no_trigger_without_oracle_exposure"
    return CurrencyDecision(
        fixture_id=str(row["fixture_id"]),
        split=str(row["split"]),
        review_priority_score=score,
        threshold=threshold,
        trigger=trigger,
        oracle_has_exposure=oracle_has_exposure,
        outcome=outcome,
        missed_exposure_cost=missed,
        verification_effort_cost=effort,
        total_decision_cost=total,
        currency=inputs.exposure_currency,
    )


def _normalized_report(
    fixtures: Sequence[Mapping[str, Any]],
    threshold: Decimal,
    split: str,
) -> dict[str, Any]:
    decisions = tuple(_normalized_decision(row, threshold) for row in fixtures)
    if any(decision.split != split for decision in decisions):
        raise ValueError(f"fixture split mismatch for {split}")
    scenario_totals: dict[str, Decimal] = defaultdict(Decimal)
    for decision in decisions:
        for scenario, value in decision.sensitivity_by_scenario.items():
            scenario_totals[scenario] += value
    total = sum((item.normalized_decision_loss for item in decisions), Decimal("0"))
    return {
        "split": split,
        "threshold": _decimal_text(threshold),
        "case_count": len(decisions),
        "currency": None,
        "currency_invented": False,
        "normalized_decision_loss": _decimal_text(total),
        "normalized_loss_source": "fixture_explicit_normalized_loss_inputs",
        "sensitivity_analysis": [
            {"scenario": scenario, "normalized_decision_loss": _decimal_text(value)}
            for scenario, value in sorted(scenario_totals.items())
        ],
        "case_rows": [_normalized_decision_payload(item) for item in decisions],
    }


def _normalized_decision(row: Mapping[str, Any], threshold: Decimal) -> NormalizedDecision:
    score = _score(row)
    trigger = score >= threshold
    oracle_has_exposure = bool(row["oracle"]["has_transfer_prepayment_exposure"])
    normalized = row.get("normalized_loss_inputs")
    if not isinstance(normalized, Mapping):
        raise ValueError(f"{row['fixture_id']}: missing normalized_loss_inputs")
    if trigger:
        base_loss = _decimal(normalized["verification_effort_loss"])
        outcome = (
            "triggered_oracle_exposure"
            if oracle_has_exposure
            else "triggered_without_oracle_exposure"
        )
        sensitivity_key = "verification_effort_loss"
    elif oracle_has_exposure:
        base_loss = _decimal(normalized["missed_exposure_loss"])
        outcome = "missed_oracle_exposure"
        sensitivity_key = "missed_exposure_loss"
    else:
        base_loss = Decimal("0")
        outcome = "no_trigger_without_oracle_exposure"
        sensitivity_key = ""
    sensitivity = {}
    for item in normalized["sensitivity"]:
        scenario = str(item["scenario"])
        sensitivity[scenario] = (
            _decimal(item[sensitivity_key]) if sensitivity_key else Decimal("0")
        )
    return NormalizedDecision(
        fixture_id=str(row["fixture_id"]),
        split=str(row["split"]),
        review_priority_score=score,
        threshold=threshold,
        trigger=trigger,
        oracle_has_exposure=oracle_has_exposure,
        outcome=outcome,
        normalized_decision_loss=base_loss,
        sensitivity_by_scenario=sensitivity,
    )


def _currency_inputs(row: Mapping[str, Any]) -> CurrencyInputs:
    exposure = row["oracle"]["transfer_prepayment_exposure"]
    verification = row["verification"]
    hourly = verification["creator_hourly_value"]
    exposure_currency = str(exposure["currency"])
    hourly_currency = str(hourly["currency"])
    if exposure_currency != hourly_currency:
        raise ValueError(f"{row['fixture_id']}: exposure and effort currencies differ")
    return CurrencyInputs(
        exposure_amount=_decimal(exposure["amount"]),
        exposure_currency=exposure_currency,
        verification_minutes=_decimal(verification["verification_minutes"]),
        hourly_amount=_decimal(hourly["amount"]),
        hourly_currency=hourly_currency,
    )


def _has_complete_currency_inputs(row: Mapping[str, Any]) -> bool:
    oracle = row.get("oracle")
    verification = row.get("verification")
    if not isinstance(oracle, Mapping) or not isinstance(verification, Mapping):
        return False
    exposure = oracle.get("transfer_prepayment_exposure")
    hourly = verification.get("creator_hourly_value")
    if not isinstance(exposure, Mapping) or not isinstance(hourly, Mapping):
        return False
    required = (
        exposure.get("amount"),
        exposure.get("currency"),
        verification.get("verification_minutes"),
        hourly.get("amount"),
        hourly.get("currency"),
    )
    return all(item not in {None, ""} for item in required)


def _validate_fixture_collection(fixtures: Sequence[Mapping[str, Any]], split: str) -> None:
    if not fixtures:
        raise ValueError(f"{split}: fixture file is empty")
    ids = set()
    for row in fixtures:
        fixture_id = str(row.get("fixture_id", ""))
        if not fixture_id:
            raise ValueError(f"{split}: fixture_id is required")
        if fixture_id in ids:
            raise ValueError(f"{split}: duplicate fixture_id {fixture_id}")
        ids.add(fixture_id)
        if row.get("split") != split:
            raise ValueError(f"{fixture_id}: expected split {split}")
        if row.get("is_synthetic") is not True or row.get("public_export") is not True:
            raise ValueError(f"{fixture_id}: fixtures must be synthetic and public-exportable")
        _score(row)
        if _has_complete_currency_inputs(row):
            _currency_inputs(row)
        elif not isinstance(row.get("normalized_loss_inputs"), Mapping):
            raise ValueError(f"{fixture_id}: missing explicit normalized loss inputs")


def _gate_cases(
    *,
    dev_complete: Sequence[Mapping[str, Any]],
    frozen_complete: Sequence[Mapping[str, Any]],
    dev_missing: Sequence[Mapping[str, Any]],
    frozen_missing: Sequence[Mapping[str, Any]],
    selection: Mapping[str, Any],
    dev_currency_report: Mapping[str, Any],
    frozen_currency_report: Mapping[str, Any],
    dev_normalized_report: Mapping[str, Any],
    frozen_normalized_report: Mapping[str, Any],
    metric_values: Mapping[str, str],
) -> list[dict[str, Any]]:
    return [
        _dev_threshold_case(selection, dev_currency_report),
        _frozen_fixed_threshold_case(selection, frozen_currency_report),
        _cost_derivation_case(dev_complete, frozen_complete, dev_currency_report, frozen_currency_report),
        _normalized_case(dev_missing, frozen_missing, dev_normalized_report, frozen_normalized_report),
        _verdict_free_case(metric_values),
    ]


def _dev_threshold_case(
    selection: Mapping[str, Any],
    dev_currency_report: Mapping[str, Any],
) -> dict[str, Any]:
    totals = [_decimal(row["total_decision_cost"]) for row in selection["candidate_rows"]]
    selected_total = _decimal(selection["selected_row"]["total_decision_cost"])
    issues = []
    if selected_total != min(totals):
        issues.append("selected threshold does not minimize dev total decision cost")
    if dev_currency_report["split"] != "dev":
        issues.append("threshold report did not use dev split")
    return {
        "id": "dev_threshold_selection",
        "metrics": list(METRIC_IDS),
        "status": "PASS" if not issues else "FAIL",
        "expected": {
            "selected_on_split": "dev",
            "uses_complete_currency_dev_fixtures": True,
            "objective": "minimum total decision cost",
        },
        "observed": {
            "selected_threshold": _decimal_text(selection["selected_threshold_decimal"]),
            "selected_total_decision_cost": selection["selected_row"]["total_decision_cost"],
            "complete_dev_case_count": dev_currency_report["case_count"],
            "candidate_count": len(selection["candidate_rows"]),
            "issue_count": len(issues),
            "issues": issues,
        },
    }


def _frozen_fixed_threshold_case(
    selection: Mapping[str, Any],
    frozen_currency_report: Mapping[str, Any],
) -> dict[str, Any]:
    issues = []
    selected = _decimal_text(selection["selected_threshold_decimal"])
    if frozen_currency_report["threshold"] != selected:
        issues.append("frozen report did not use the dev-selected threshold")
    return {
        "id": "frozen_fixed_threshold",
        "metrics": list(METRIC_IDS),
        "status": "PASS" if not issues else "FAIL",
        "expected": {
            "frozen_eval_used_for_threshold_selection": False,
            "frozen_eval_uses_fixed_dev_threshold": True,
        },
        "observed": {
            "fixed_threshold": frozen_currency_report["threshold"],
            "complete_frozen_case_count": frozen_currency_report["case_count"],
            "metric_values": dict(frozen_currency_report["metric_values"]),
            "issue_count": len(issues),
            "issues": issues,
        },
    }


def _cost_derivation_case(
    dev_complete: Sequence[Mapping[str, Any]],
    frozen_complete: Sequence[Mapping[str, Any]],
    dev_report: Mapping[str, Any],
    frozen_report: Mapping[str, Any],
) -> dict[str, Any]:
    rows_by_id = {
        row["fixture_id"]: row
        for row in tuple(dev_complete) + tuple(frozen_complete)
    }
    decisions = dev_report["case_rows"] + frozen_report["case_rows"]
    issues = []
    for decision in decisions:
        fixture = rows_by_id[decision["fixture_id"]]
        inputs = _currency_inputs(fixture)
        expected_effort = inputs.verification_effort_cost if decision["trigger"] else Decimal("0")
        if _decimal(decision["verification_effort_cost"]) != expected_effort:
            issues.append(f"{decision['fixture_id']}: verification effort cost mismatch")
        if decision["outcome"] == "missed_oracle_exposure":
            expected_missed = inputs.exposure_amount
        else:
            expected_missed = Decimal("0")
        if _decimal(decision["missed_exposure_cost"]) != expected_missed:
            issues.append(f"{decision['fixture_id']}: missed exposure cost mismatch")
    return {
        "id": "fixture_cost_derivation",
        "metrics": [
            "EV-MISSED-EXPOSURE-COST",
            "EV-VERIFICATION-EFFORT-COST",
            "EV-TOTAL-DECISION-COST",
        ],
        "status": "PASS" if not issues else "FAIL",
        "expected": {
            "missed_exposure_cost_from_fixture_exposure": True,
            "verification_effort_cost_from_minutes_times_hourly_value": True,
            "true_negative_cost_zero": True,
        },
        "observed": {
            "checked_case_count": len(decisions),
            "issue_count": len(issues),
            "issues": issues,
        },
    }


def _normalized_case(
    dev_missing: Sequence[Mapping[str, Any]],
    frozen_missing: Sequence[Mapping[str, Any]],
    dev_report: Mapping[str, Any],
    frozen_report: Mapping[str, Any],
) -> dict[str, Any]:
    issues = []
    if not dev_missing or not frozen_missing:
        issues.append("missing-input fixtures are required on dev and frozen splits")
    for report in (dev_report, frozen_report):
        if report["currency"] is not None or report["currency_invented"]:
            issues.append(f"{report['split']}: normalized report invented currency")
        if not report["sensitivity_analysis"]:
            issues.append(f"{report['split']}: sensitivity analysis missing")
    return {
        "id": "normalized_missing_input_analysis",
        "metrics": [],
        "status": "PASS" if not issues else "FAIL",
        "expected": {
            "currency_inputs_absent_use_normalized_loss": True,
            "sensitivity_analysis_from_fixture_values": True,
            "currency_invented": False,
        },
        "observed": {
            "dev_missing_case_count": len(dev_missing),
            "frozen_missing_case_count": len(frozen_missing),
            "dev_normalized_decision_loss": dev_report["normalized_decision_loss"],
            "frozen_normalized_decision_loss": frozen_report["normalized_decision_loss"],
            "frozen_sensitivity_analysis": list(frozen_report["sensitivity_analysis"]),
            "issue_count": len(issues),
            "issues": issues,
        },
    }


def _verdict_free_case(metric_values: Mapping[str, str]) -> dict[str, Any]:
    forbidden = ("fra" + "ud", "acc" + "uracy", "illegal", "validity", "unfair")
    payload = json.dumps(
        {
            "suite": SUITE_ID,
            "task_id": TASK_ID,
            "metric_ids": list(METRIC_IDS),
            "metric_values": dict(metric_values),
            "definitions": _metric_definitions(),
        },
        ensure_ascii=False,
        sort_keys=True,
    ).lower()
    issues = [term for term in forbidden if term in payload]
    return {
        "id": "verdict_free_metric_labels",
        "metrics": list(METRIC_IDS),
        "status": "PASS" if not issues else "FAIL",
        "expected": {
            "metric_labels_are_verification_and_cost_focused": True,
            "scoring_frame": "Contractual Financial Review Priority",
        },
        "observed": {
            "metric_ids": list(METRIC_IDS),
            "forbidden_label_hits": issues,
            "issue_count": len(issues),
            "issues": issues,
        },
    }


def _metric_definitions() -> dict[str, Any]:
    return {
        "EV-MISSED-EXPOSURE-COST": {
            "name": "Missed Exposure Cost",
            "definition": (
                "For untriggered rows with oracle transfer/prepayment exposure, "
                "use the fixture exposure amount left unchecked."
            ),
            "direction": "lower_is_better",
            "unit_source": "fixture currency field",
        },
        "EV-VERIFICATION-EFFORT-COST": {
            "name": "Verification Effort Cost",
            "definition": (
                "For triggered rows, multiply fixture verification minutes by "
                "fixture creator hourly value divided by 60."
            ),
            "direction": "lower_is_better",
            "unit_source": "fixture currency field",
        },
        "EV-TOTAL-DECISION-COST": {
            "name": "Total Decision Cost",
            "definition": (
                "Missed exposure cost plus verification effort cost, with "
                "true-negative rows contributing zero."
            ),
            "direction": "lower_is_better",
            "unit_source": "fixture currency field",
        },
        "EV-FALSE-TRIGGER-RATE": {
            "name": "False-Trigger Rate",
            "definition": (
                "Triggered rows without oracle transfer/prepayment exposure divided "
                "by rows without oracle transfer/prepayment exposure."
            ),
            "direction": "lower_is_better",
        },
        "EV-TRIGGER-RECALL": {
            "name": "Trigger Recall",
            "definition": (
                "Triggered rows with oracle transfer/prepayment exposure divided by "
                "rows with oracle transfer/prepayment exposure."
            ),
            "direction": "higher_is_better",
        },
    }


def _result_ledger_rows(metric_values: Mapping[str, str]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for metric_id in METRIC_IDS:
        rows.append(
            {
                "result_id": f"{TASK_ID}-{metric_id}",
                "experiment_id": SUITE_ID,
                "metric": metric_id,
                "value": metric_values[metric_id],
                "artifact_path": ARTIFACT_PATH,
                "status": "measured",
                "reviewer": "codex",
                "notes": (
                    "synthetic-only FINK-COST-01 frozen evaluation; fixed dev "
                    "threshold, fixture-derived costs, no generalized performance claim"
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


def _currency_decision_payload(decision: CurrencyDecision) -> dict[str, Any]:
    return {
        "fixture_id": decision.fixture_id,
        "split": decision.split,
        "review_priority_score": _decimal_text(decision.review_priority_score),
        "threshold": _decimal_text(decision.threshold),
        "trigger": decision.trigger,
        "oracle_has_transfer_prepayment_exposure": decision.oracle_has_exposure,
        "outcome": decision.outcome,
        "missed_exposure_cost": _decimal_text(decision.missed_exposure_cost),
        "verification_effort_cost": _decimal_text(decision.verification_effort_cost),
        "total_decision_cost": _decimal_text(decision.total_decision_cost),
        "currency": decision.currency,
        "cost_source": "explicit_fixture_values",
    }


def _normalized_decision_payload(decision: NormalizedDecision) -> dict[str, Any]:
    return {
        "fixture_id": decision.fixture_id,
        "split": decision.split,
        "review_priority_score": _decimal_text(decision.review_priority_score),
        "threshold": _decimal_text(decision.threshold),
        "trigger": decision.trigger,
        "oracle_has_transfer_prepayment_exposure": decision.oracle_has_exposure,
        "outcome": decision.outcome,
        "normalized_decision_loss": _decimal_text(decision.normalized_decision_loss),
        "sensitivity_by_scenario": {
            key: _decimal_text(value)
            for key, value in sorted(decision.sensitivity_by_scenario.items())
        },
        "currency": None,
        "loss_source": "explicit_fixture_normalized_loss_values",
    }


def _read_jsonl(path: Path) -> tuple[dict[str, Any], ...]:
    rows = []
    with path.open(encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                rows.append(json.loads(stripped))
            except json.JSONDecodeError as exc:
                raise ValueError(f"{_display_path(path)}:{line_no}: invalid JSON") from exc
    return tuple(rows)


def _score(row: Mapping[str, Any]) -> Decimal:
    return _decimal(row["review_priority_score"])


def _decimal(raw: object) -> Decimal:
    if raw is None:
        raise ValueError("required numeric fixture value is absent")
    try:
        return Decimal(str(raw))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"invalid decimal value: {raw!r}") from exc


def _decimal_text(value: Decimal | str) -> str:
    decimal_value = _decimal(value)
    return f"{decimal_value:.6f}"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _display_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run FINK-COST-01 cost-sensitive verification evaluation."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=RESULT_LOG_PATH,
        help="Path for the JSON result artifact.",
    )
    parser.add_argument("--stdout", action="store_true", help="Also print JSON to stdout.")
    args = parser.parse_args(argv)

    result = run_cost_sensitive_verification_suite()
    log_path = write_result_log(result, args.output)
    if args.stdout:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    print(f"{SUITE_ID}: {'PASS' if result['summary']['ok'] else 'FAIL'}; log={log_path}")
    return 0 if result["summary"]["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

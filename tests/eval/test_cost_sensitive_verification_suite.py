from __future__ import annotations

import json
import unittest
from decimal import Decimal

from scripts.eval import cost_sensitive_verification_suite as COST


class CostSensitiveVerificationSuiteTests(unittest.TestCase):
    def test_suite_selects_threshold_on_dev_and_reports_frozen_metrics(self) -> None:
        result = COST.run_cost_sensitive_verification_suite()

        self.assertTrue(result["summary"]["ok"], result["cases"])
        self.assertEqual(tuple(result["registered_gates"]), COST.REGISTERED_GATE_IDS)
        self.assertEqual(set(result["metric_values"]), set(COST.METRIC_IDS))
        self.assertEqual(result["threshold_selection"]["selected_on_split"], "dev")
        self.assertFalse(result["threshold_selection"]["frozen_eval_used_for_threshold_selection"])
        self.assertTrue(result["threshold_selection"]["frozen_eval_uses_fixed_dev_threshold"])
        self.assertEqual(result["threshold_selection"]["selected_threshold"], "58.000000")
        self.assertEqual(
            result["metric_values"],
            {
                "EV-MISSED-EXPOSURE-COST": "600000.000000",
                "EV-VERIFICATION-EFFORT-COST": "90000.000000",
                "EV-TOTAL-DECISION-COST": "690000.000000",
                "EV-FALSE-TRIGGER-RATE": "0.333333",
                "EV-TRIGGER-RECALL": "0.666667",
            },
        )

    def test_costs_are_derived_from_fixture_values_without_script_currency_defaults(self) -> None:
        result = COST.run_cost_sensitive_verification_suite()
        frozen_fixtures = {
            row["fixture_id"]: row for row in COST._read_jsonl(COST.FROZEN_FIXTURE_PATH)
        }
        frozen_rows = {
            row["fixture_id"]: row
            for row in result["reports"]["frozen_complete_currency"]["case_rows"]
        }
        false_trigger_fixture = frozen_fixtures["FINK-COST-FROZEN-006"]
        false_trigger_row = frozen_rows["FINK-COST-FROZEN-006"]
        minutes = Decimal(false_trigger_fixture["verification"]["verification_minutes"])
        hourly = Decimal(
            false_trigger_fixture["verification"]["creator_hourly_value"]["amount"]
        )

        self.assertTrue(false_trigger_row["trigger"])
        self.assertFalse(false_trigger_row["oracle_has_transfer_prepayment_exposure"])
        self.assertEqual(
            Decimal(false_trigger_row["verification_effort_cost"]),
            (minutes / Decimal("60")) * hourly,
        )
        self.assertEqual(false_trigger_row["missed_exposure_cost"], "0.000000")

        true_negative = frozen_rows["FINK-COST-FROZEN-004"]
        self.assertFalse(true_negative["trigger"])
        self.assertFalse(true_negative["oracle_has_transfer_prepayment_exposure"])
        self.assertEqual(true_negative["total_decision_cost"], "0.000000")

        source = COST.RESULT_LOG_PATH.with_name("cost_sensitive_verification_suite.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("KRW", source)

    def test_missing_currency_inputs_report_normalized_loss_and_sensitivity(self) -> None:
        result = COST.run_cost_sensitive_verification_suite()
        frozen = result["reports"]["frozen_missing_inputs_normalized"]

        self.assertIsNone(frozen["currency"])
        self.assertFalse(frozen["currency_invented"])
        self.assertEqual(frozen["normalized_decision_loss"], "1.400000")
        self.assertEqual(
            frozen["sensitivity_analysis"],
            [
                {"scenario": "base", "normalized_decision_loss": "1.400000"},
                {"scenario": "high", "normalized_decision_loss": "2.050000"},
                {"scenario": "low", "normalized_decision_loss": "0.850000"},
            ],
        )
        for row in frozen["case_rows"]:
            self.assertIsNone(row["currency"])
            self.assertEqual(row["loss_source"], "explicit_fixture_normalized_loss_values")

    def test_result_ledger_rows_are_supported_by_committed_artifact(self) -> None:
        expected = COST.run_cost_sensitive_verification_suite()
        loaded = json.loads(COST.RESULT_LOG_PATH.read_text(encoding="utf-8"))

        self.assertEqual(loaded, expected)
        self.assertEqual(
            tuple(loaded["result_ledger"]["columns"]),
            COST.RESULT_LEDGER_COLUMNS,
        )
        self.assertEqual(len(loaded["result_ledger"]["rows"]), len(COST.METRIC_IDS))
        for row in loaded["result_ledger"]["rows"]:
            self.assertEqual(row["artifact_path"], COST.ARTIFACT_PATH)
            self.assertEqual(row["status"], "measured")
            self.assertEqual(row["value"], loaded["metric_values"][row["metric"]])

    def test_metric_labels_stay_verification_cost_focused(self) -> None:
        result = COST.run_cost_sensitive_verification_suite()
        payload = json.dumps(result, ensure_ascii=False).lower()

        self.assertNotIn("acc" + "uracy", payload)
        self.assertNotIn("fra" + "ud", payload)
        self.assertEqual(
            result["claim_boundary"]["scoring_frame"],
            "Contractual Financial Review Priority",
        )


if __name__ == "__main__":
    unittest.main()

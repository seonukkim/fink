from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.eval import decision_utility_suite


class DecisionUtilitySuiteTests(unittest.TestCase):
    def test_decision_utility_suite_reports_required_gates_and_metrics(self) -> None:
        result = decision_utility_suite.run_decision_utility_suite()

        self.assertTrue(result["summary"]["ok"], result)
        self.assertEqual(
            tuple(result["registered_gates"]),
            decision_utility_suite.REGISTERED_GATE_IDS,
        )
        self.assertEqual(set(result["registered_gates"]), {"dfu_run", "stability_run"})
        self.assertEqual(set(result["metrics"]), set(decision_utility_suite.METRIC_IDS))
        self.assertEqual(set(result["metric_values"]), set(decision_utility_suite.METRIC_IDS))
        for value in result["metric_values"].values():
            self.assertGreaterEqual(value, 0.0)
            self.assertLessEqual(value, 1.0)

    def test_expected_metric_values_are_pinned(self) -> None:
        result = decision_utility_suite.run_decision_utility_suite()

        self.assertEqual(
            result["metric_values"],
            {
                "EV-DFU": 1.0,
                "EV-USAB": 1.0,
                "EV-CALIB": 0.798333,
                "EV-STAB": 0.999,
            },
        )
        self.assertEqual(
            result["reports"]["decision_utility"]["metric_values"]["baseline_EV-DFU"],
            0.516,
        )
        self.assertEqual(
            result["reports"]["decision_utility"]["metric_values"][
                "utility_lift_vs_baseline"
            ],
            0.484,
        )

    def test_dfu_run_reports_baseline_usability_and_calibration_on_synthetic(self) -> None:
        result = decision_utility_suite.run_decision_utility_suite()
        by_id = {case["id"]: case for case in result["cases"]}
        dfu_case = by_id["dfu_run"]

        self.assertEqual(dfu_case["status"], "PASS")
        self.assertEqual(dfu_case["metrics"], ["EV-DFU", "EV-USAB", "EV-CALIB"])
        self.assertTrue(dfu_case["expected"]["synthetic_only"])
        self.assertTrue(dfu_case["expected"]["baseline_reported"])
        self.assertTrue(dfu_case["expected"]["usability_rubric_executed"])
        self.assertTrue(dfu_case["expected"]["calibration_measured"])
        self.assertGreater(
            dfu_case["observed"]["metric_values"]["EV-DFU"],
            dfu_case["observed"]["baseline_EV-DFU"],
        )
        self.assertEqual(dfu_case["observed"]["rubric_item_count"], 8)
        self.assertEqual(dfu_case["observed"]["calibration_bin_count"], 3)
        self.assertRegex(dfu_case["observed"]["fixture_sha256"], r"^[a-f0-9]{64}$")

    def test_usability_rubric_is_executed_without_collapsing_report_dimensions(self) -> None:
        result = decision_utility_suite.run_decision_utility_suite()
        usability = result["reports"]["usability"]

        self.assertEqual(usability["metric_values"]["EV-USAB"], 1.0)
        self.assertTrue(usability["mandatory_items_all_passed"])
        self.assertEqual(usability["rubric_item_count"], len(usability["rubric_items"]))
        criteria = {row["criterion"] for row in usability["rubric_items"]}
        self.assertIn("four_dimensions_remain_separate", criteria)
        self.assertIn("forbidden_verdict_framing_absent", criteria)
        self.assertIn("calibration_and_stability_labels_are_measured", criteria)

    def test_calibration_report_uses_fixed_bins_and_brier_score(self) -> None:
        result = decision_utility_suite.run_decision_utility_suite()
        calibration = result["reports"]["calibration"]

        self.assertEqual(calibration["case_count"], 6)
        self.assertEqual(calibration["metric_values"]["EV-CALIB"], 0.798333)
        self.assertEqual(
            calibration["metric_values"]["expected_calibration_error"],
            0.201667,
        )
        self.assertEqual(calibration["metric_values"]["brier_score"], 0.045083)
        self.assertEqual([row["count"] for row in calibration["bins"]], [2, 1, 3])

    def test_stability_run_measures_repeat_run_drift_and_top_k_agreement(self) -> None:
        result = decision_utility_suite.run_decision_utility_suite()
        by_id = {case["id"]: case for case in result["cases"]}
        stability_case = by_id["stability_run"]
        stability = result["reports"]["stability"]

        self.assertEqual(stability_case["status"], "PASS")
        self.assertEqual(stability_case["metrics"], ["EV-STAB"])
        self.assertEqual(stability["repeat_runs"], 3)
        self.assertEqual(stability["metric_values"]["top_k_jaccard"], 1.0)
        self.assertEqual(stability["metric_values"]["category_agreement"], 1.0)
        self.assertEqual(stability["metric_values"]["max_priority_score_delta"], 0.3)
        self.assertEqual(stability["metric_values"]["EV-STAB"], 0.999)
        top_k_sets = {tuple(run["top_k_case_ids"]) for run in stability["runs"]}
        self.assertEqual(len(top_k_sets), 1)

    def test_result_ledger_rows_are_measured_and_schema_aligned(self) -> None:
        result = decision_utility_suite.run_decision_utility_suite()
        ledger = result["result_ledger"]

        self.assertEqual(ledger["name"], "RESULT_LEDGER")
        self.assertEqual(
            tuple(ledger["columns"]),
            decision_utility_suite.RESULT_LEDGER_COLUMNS,
        )
        self.assertEqual(len(ledger["rows"]), len(decision_utility_suite.METRIC_IDS))
        self.assertEqual(
            {row["metric"] for row in ledger["rows"]},
            set(decision_utility_suite.METRIC_IDS),
        )
        for row in ledger["rows"]:
            with self.subTest(metric=row["metric"]):
                self.assertEqual(set(row), set(decision_utility_suite.RESULT_LEDGER_COLUMNS))
                self.assertIn(row["experiment_id"], {"dfu_run", "stability_run"})
                self.assertEqual(
                    row["artifact_path"],
                    "scripts/eval/decision_utility_suite_results.json",
                )
                self.assertEqual(row["status"], "measured")
                self.assertEqual(
                    row["value"],
                    f"{result['metric_values'][row['metric']]:.6f}",
                )

    def test_result_log_can_be_written_without_fixture_text_or_contract_data(self) -> None:
        result = decision_utility_suite.run_decision_utility_suite()

        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "decision_utility_suite_results.json"
            written = decision_utility_suite.write_result_log(result, output)
            text = written.read_text(encoding="utf-8")
            loaded = json.loads(text)

        self.assertEqual(loaded, result)
        self.assertNotIn("contract text", text.lower())
        self.assertTrue(result["claim_boundary"]["no_legal_verdict"])

    def test_committed_decision_utility_log_is_current(self) -> None:
        expected = decision_utility_suite.run_decision_utility_suite()
        loaded = json.loads(
            decision_utility_suite.RESULT_LOG_PATH.read_text(encoding="utf-8")
        )

        self.assertEqual(loaded, expected)


if __name__ == "__main__":
    unittest.main()

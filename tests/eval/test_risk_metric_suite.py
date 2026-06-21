from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.eval import risk_metric_suite


class RiskMetricSuiteTests(unittest.TestCase):
    def test_risk_metric_run_reports_all_metrics_for_all_three_arms(self) -> None:
        result = risk_metric_suite.run_risk_metric_suite()

        self.assertTrue(result["summary"]["ok"], result)
        self.assertEqual(
            tuple(result["registered_gates"]),
            risk_metric_suite.REGISTERED_GATE_IDS,
        )
        self.assertEqual(
            set(result["registered_gates"]),
            {"risk_metric_run", "ablation_three_arms"},
        )
        self.assertEqual(set(result["metrics"]), set(risk_metric_suite.METRIC_IDS))
        self.assertEqual(set(result["metric_values"]), set(risk_metric_suite.ARM_IDS))
        for arm_id, metric_values in result["metric_values"].items():
            with self.subTest(arm=arm_id):
                self.assertEqual(set(metric_values), set(risk_metric_suite.METRIC_IDS))
                for value in metric_values.values():
                    self.assertGreaterEqual(value, 0.0)
                    self.assertLessEqual(value, 1.0)

    def test_expected_metric_values_are_pinned_for_each_ablation_arm(self) -> None:
        result = risk_metric_suite.run_risk_metric_suite()

        self.assertEqual(
            result["metric_values"]["rule_only"],
            {
                "EV-F1": 0.833333,
                "EV-BENIGN-FPR": 0.25,
                "EV-SEV": 0.87,
            },
        )
        self.assertEqual(
            result["metric_values"]["model_only"],
            {
                "EV-F1": 0.857143,
                "EV-BENIGN-FPR": 0.5,
                "EV-SEV": 0.91,
            },
        )
        self.assertEqual(
            result["metric_values"]["hybrid"],
            {
                "EV-F1": 0.923077,
                "EV-BENIGN-FPR": 0.25,
                "EV-SEV": 0.988333,
            },
        )

    def test_benign_fpr_is_measured_and_confusion_counts_match_fixture(self) -> None:
        result = risk_metric_suite.run_risk_metric_suite()
        reports = result["arm_reports"]

        self.assertEqual(reports["rule_only"]["confusion"], {"tp": 5, "fp": 1, "tn": 3, "fn": 1})
        self.assertEqual(reports["model_only"]["confusion"], {"tp": 6, "fp": 2, "tn": 2, "fn": 0})
        self.assertEqual(reports["hybrid"]["confusion"], {"tp": 6, "fp": 1, "tn": 3, "fn": 0})
        for arm_id in risk_metric_suite.ARM_IDS:
            with self.subTest(arm=arm_id):
                self.assertIn("EV-BENIGN-FPR", reports[arm_id]["metric_values"])
                self.assertEqual(
                    reports[arm_id]["metric_values"]["EV-BENIGN-FPR"],
                    result["metric_values"][arm_id]["EV-BENIGN-FPR"],
                )

    def test_ablation_three_arms_keeps_measured_scope_without_optimality_claims(self) -> None:
        result = risk_metric_suite.run_risk_metric_suite()
        ablation_case = {
            case["id"]: case for case in result["cases"]
        }["ablation_three_arms"]

        self.assertEqual(ablation_case["status"], "PASS")
        self.assertEqual(ablation_case["observed"]["arm_count"], 3)
        self.assertEqual(set(ablation_case["observed"]["arms"]), set(risk_metric_suite.ARM_IDS))
        self.assertTrue(
            result["claim_boundary"]["no_arm_claimed_optimal_beyond_measured_result"]
        )
        for report in result["arm_reports"].values():
            self.assertEqual(report["optimality_claim"], "none")
            self.assertEqual(
                report["measured_result_scope"],
                "synthetic/sanitized fixture only",
            )
        self.assertEqual(
            result["measured_extrema"]["EV-BENIGN-FPR"]["arms"],
            ["hybrid", "rule_only"],
        )
        self.assertEqual(
            result["measured_extrema"]["EV-BENIGN-FPR"]["scope"],
            "measured fixture only",
        )

    def test_review_priority_scores_are_reported_without_collapsing_metrics(self) -> None:
        result = risk_metric_suite.run_risk_metric_suite()

        for arm_id, report in result["arm_reports"].items():
            with self.subTest(arm=arm_id):
                scores = report["review_priority_scores"]
                self.assertEqual(
                    scores["scoring_frame"],
                    "Contractual Financial Review Priority",
                )
                self.assertEqual(len(scores["per_case"]), 10)
                self.assertIn("mean_all_cases", scores)
                self.assertIn("mean_predicted_positive_cases", scores)
                self.assertIn("max_case_score", scores)
                self.assertNotIn("overall_risk_score", scores)

    def test_result_ledger_rows_are_measured_and_schema_aligned(self) -> None:
        result = risk_metric_suite.run_risk_metric_suite()
        ledger = result["result_ledger"]

        self.assertEqual(ledger["name"], "RESULT_LEDGER")
        self.assertEqual(
            tuple(ledger["columns"]),
            risk_metric_suite.RESULT_LEDGER_COLUMNS,
        )
        self.assertEqual(
            len(ledger["rows"]),
            len(risk_metric_suite.ARM_IDS) * len(risk_metric_suite.METRIC_IDS),
        )
        for row in ledger["rows"]:
            with self.subTest(result_id=row["result_id"]):
                self.assertEqual(set(row), set(risk_metric_suite.RESULT_LEDGER_COLUMNS))
                arm_id = row["experiment_id"].split(":", maxsplit=1)[1]
                self.assertIn(arm_id, risk_metric_suite.ARM_IDS)
                self.assertEqual(
                    row["artifact_path"],
                    "scripts/eval/risk_metric_suite_results.json",
                )
                self.assertEqual(row["status"], "measured")
                self.assertEqual(
                    row["value"],
                    f"{result['metric_values'][arm_id][row['metric']]:.6f}",
                )

    def test_result_log_can_be_written_without_fixture_text_or_contract_data(self) -> None:
        result = risk_metric_suite.run_risk_metric_suite()

        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "risk_metric_suite_results.json"
            written = risk_metric_suite.write_result_log(result, output)
            text = written.read_text(encoding="utf-8")
            loaded = json.loads(text)

        self.assertEqual(loaded, result)
        self.assertNotIn("contract text", text.lower())
        self.assertRegex(result["cases"][0]["observed"]["fixture_sha256"], r"^[a-f0-9]{64}$")

    def test_committed_risk_metric_log_is_current(self) -> None:
        expected = risk_metric_suite.run_risk_metric_suite()
        loaded = json.loads(
            risk_metric_suite.RESULT_LOG_PATH.read_text(encoding="utf-8")
        )

        self.assertEqual(loaded, expected)


if __name__ == "__main__":
    unittest.main()

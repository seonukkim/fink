from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.eval import retrieval_metric_suite


class RetrievalMetricSuiteTests(unittest.TestCase):
    def test_retrieval_metric_run_computes_all_required_metrics(self) -> None:
        result = retrieval_metric_suite.run_retrieval_metric_suite()

        self.assertTrue(result["summary"]["ok"], result)
        self.assertEqual(
            tuple(result["registered_gates"]),
            retrieval_metric_suite.REGISTERED_GATE_IDS,
        )
        self.assertEqual(set(result["registered_gates"]), {"retrieval_metric_run"})
        self.assertEqual(set(result["metrics"]), set(retrieval_metric_suite.METRIC_IDS))
        self.assertEqual(
            set(result["metric_values"]),
            set(retrieval_metric_suite.METRIC_IDS),
        )
        self.assertEqual(result["metric_values"]["EV-R@3"], 1.0)
        self.assertEqual(result["metric_values"]["EV-R@5"], 1.0)
        self.assertEqual(result["metric_values"]["EV-AUTH"], 1.0)
        self.assertEqual(result["metric_values"]["EV-KOEN"], 1.0)
        self.assertEqual(result["metric_values"]["EV-SPAN"], 0.85)
        for metric_id in retrieval_metric_suite.METRIC_IDS:
            self.assertEqual(
                result["metrics"][metric_id],
                {"total": 1, "passed": 1, "failed": 0, "ok": True},
            )

    def test_authority_observation_verifies_tiers_and_zero_contribution(self) -> None:
        result = retrieval_metric_suite.run_retrieval_metric_suite()
        authority = result["cases"][0]["observed"]["authority"]

        self.assertEqual(authority["total_checks"], authority["passed_checks"])
        self.assertEqual(authority["errors"], {})
        self.assertTrue(authority["checks"]["grounding_records_a0_a2"])
        self.assertTrue(authority["checks"]["practice_records_bc_non_scoring"])
        self.assertTrue(authority["checks"]["bc_only_zero_contribution"])
        self.assertTrue(authority["checks"]["x_category_non_scoring"])
        self.assertFalse(authority["eligibility"]["bc_only"]["score_eligible"])
        self.assertTrue(authority["eligibility"]["bc_only"]["practice_reference"])
        self.assertEqual(authority["eligibility"]["bc_only"]["score_contribution"], 0.0)
        self.assertTrue(authority["eligibility"]["a1_grounded"]["score_eligible"])
        self.assertFalse(authority["eligibility"]["x_context"]["score_eligible"])

    def test_koen_observation_preserves_caveats_and_alias_boundary(self) -> None:
        result = retrieval_metric_suite.run_retrieval_metric_suite()
        koen = result["cases"][0]["observed"]["koen"]

        self.assertEqual(koen["total_pairs"], 8)
        self.assertEqual(koen["consistent_pairs"], 8)
        self.assertEqual(koen["top_k_consistent_pairs"], 8)
        self.assertEqual(koen["caveat_required_pairs"], 8)
        self.assertEqual(koen["caveat_present_pairs"], 8)
        self.assertTrue(koen["english_never_labeled_evidence"])
        for row in koen["per_query"]:
            with self.subTest(query=row["query_id"]):
                self.assertTrue(row["same_top1"])
                self.assertTrue(row["same_top_k"])
                self.assertTrue(row["consistent"])
                self.assertTrue(row["non_equivalence_caveat_present"])
                self.assertFalse(row["english_labeled_evidence"])
                self.assertEqual(row["ko_canonical_ids"], row["en_canonical_ids"])

    def test_span_metric_uses_token_iou_without_logging_span_text(self) -> None:
        result = retrieval_metric_suite.run_retrieval_metric_suite()
        span = result["cases"][0]["observed"]["span"]

        self.assertEqual(span["aggregation"], "mean token-set IoU")
        self.assertEqual(span["case_count"], 3)
        self.assertEqual(
            [case["token_iou"] for case in span["cases"]],
            [1.0, 0.8, 0.75],
        )
        for case in span["cases"]:
            self.assertRegex(case["gold_span_sha256"], r"^[a-f0-9]{64}$")
            self.assertRegex(case["cited_span_sha256"], r"^[a-f0-9]{64}$")
            self.assertNotIn("gold_span", case)
            self.assertNotIn("cited_span", case)

    def test_result_ledger_rows_are_measured_and_schema_aligned(self) -> None:
        result = retrieval_metric_suite.run_retrieval_metric_suite()
        ledger = result["result_ledger"]

        self.assertEqual(ledger["name"], "RESULT_LEDGER")
        self.assertEqual(
            tuple(ledger["columns"]),
            retrieval_metric_suite.RESULT_LEDGER_COLUMNS,
        )
        self.assertEqual(len(ledger["rows"]), len(retrieval_metric_suite.METRIC_IDS))
        self.assertEqual(
            {row["metric"] for row in ledger["rows"]},
            set(retrieval_metric_suite.METRIC_IDS),
        )
        for row in ledger["rows"]:
            with self.subTest(metric=row["metric"]):
                self.assertEqual(set(row), set(retrieval_metric_suite.RESULT_LEDGER_COLUMNS))
                self.assertEqual(row["experiment_id"], "retrieval_metric_run")
                self.assertEqual(
                    row["artifact_path"],
                    "scripts/eval/retrieval_metric_suite_results.json",
                )
                self.assertEqual(row["status"], "measured")
                self.assertEqual(
                    row["value"],
                    f"{result['metric_values'][row['metric']]:.6f}",
                )

    def test_result_log_can_be_written_without_fixture_text(self) -> None:
        result = retrieval_metric_suite.run_retrieval_metric_suite()

        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "retrieval_metric_suite_results.json"
            written = retrieval_metric_suite.write_result_log(result, output)
            text = written.read_text(encoding="utf-8")
            loaded = json.loads(text)

        self.assertEqual(loaded, result)
        for _case_id, gold_span, cited_span in retrieval_metric_suite.SPAN_FIXTURES:
            self.assertNotIn(gold_span, text)
            self.assertNotIn(cited_span, text)
        for chunk in retrieval_metric_suite._retrieval_chunks():
            self.assertNotIn(chunk.text, text)

    def test_committed_retrieval_metric_log_is_current(self) -> None:
        expected = retrieval_metric_suite.run_retrieval_metric_suite()
        loaded = json.loads(
            retrieval_metric_suite.RESULT_LOG_PATH.read_text(encoding="utf-8")
        )

        self.assertEqual(loaded, expected)


if __name__ == "__main__":
    unittest.main()

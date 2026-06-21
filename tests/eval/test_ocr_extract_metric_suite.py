from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.eval import ocr_extract_metric_suite


class OcrExtractMetricSuiteTests(unittest.TestCase):
    def test_ocr_extract_metric_run_computes_all_required_metrics(self) -> None:
        result = ocr_extract_metric_suite.run_ocr_extract_metric_suite()

        self.assertTrue(result["summary"]["ok"], result)
        self.assertEqual(
            tuple(result["registered_gates"]),
            ocr_extract_metric_suite.REGISTERED_GATE_IDS,
        )
        self.assertEqual(
            set(result["registered_gates"]),
            {"ocr_extract_metric_run"},
        )
        self.assertEqual(set(result["metrics"]), set(ocr_extract_metric_suite.METRIC_IDS))
        self.assertEqual(set(result["metric_values"]), set(ocr_extract_metric_suite.METRIC_IDS))
        self.assertEqual(result["metric_values"]["EV-OCR-CER"], 0.052632)
        self.assertEqual(result["metric_values"]["EV-OCR-WER"], 0.125)
        for metric_id in (
            "EV-EXACT-MONEY",
            "EV-EXACT-PCT",
            "EV-EXACT-DATE",
            "EV-EXACT-DUR",
            "EV-SEG",
        ):
            self.assertEqual(result["metric_values"][metric_id], 1.0)
            self.assertEqual(
                result["metrics"][metric_id],
                {"total": 1, "passed": 1, "failed": 0, "ok": True},
            )

    def test_result_ledger_rows_are_measured_and_schema_aligned(self) -> None:
        result = ocr_extract_metric_suite.run_ocr_extract_metric_suite()
        ledger = result["result_ledger"]

        self.assertEqual(ledger["name"], "RESULT_LEDGER")
        self.assertEqual(
            tuple(ledger["columns"]),
            ocr_extract_metric_suite.RESULT_LEDGER_COLUMNS,
        )
        self.assertEqual(len(ledger["rows"]), len(ocr_extract_metric_suite.METRIC_IDS))
        self.assertEqual(
            {row["metric"] for row in ledger["rows"]},
            set(ocr_extract_metric_suite.METRIC_IDS),
        )
        for row in ledger["rows"]:
            with self.subTest(metric=row["metric"]):
                self.assertEqual(set(row), set(ocr_extract_metric_suite.RESULT_LEDGER_COLUMNS))
                self.assertEqual(row["experiment_id"], "ocr_extract_metric_run")
                self.assertEqual(
                    row["artifact_path"],
                    "scripts/eval/ocr_extract_metric_suite_results.json",
                )
                self.assertEqual(row["status"], "measured")
                self.assertEqual(
                    row["value"],
                    f"{result['metric_values'][row['metric']]:.6f}",
                )

    def test_result_log_can_be_written_without_fixture_text(self) -> None:
        result = ocr_extract_metric_suite.run_ocr_extract_metric_suite()

        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "ocr_extract_metric_suite_results.json"
            written = ocr_extract_metric_suite.write_result_log(result, output)
            text = written.read_text(encoding="utf-8")
            loaded = json.loads(text)

        self.assertEqual(loaded, result)
        for marker in (
            ocr_extract_metric_suite.REFERENCE_TEXT,
            ocr_extract_metric_suite.OCR_EXACT_TEXT,
            ocr_extract_metric_suite.OCR_NOISY_REFERENCE_TEXT,
            ocr_extract_metric_suite.OCR_NOISY_HYPOTHESIS_TEXT,
        ):
            self.assertNotIn(marker, text)

    def test_committed_ocr_extract_metric_log_is_current(self) -> None:
        expected = ocr_extract_metric_suite.run_ocr_extract_metric_suite()
        loaded = json.loads(
            ocr_extract_metric_suite.RESULT_LOG_PATH.read_text(encoding="utf-8")
        )

        self.assertEqual(loaded, expected)


if __name__ == "__main__":
    unittest.main()

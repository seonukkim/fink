from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.eval import formula_unit_suite


class FormulaUnitSuiteTests(unittest.TestCase):
    def test_formula_unit_suite_registers_all_fim_and_sc_cases(self) -> None:
        result = formula_unit_suite.run_formula_unit_suite()

        self.assertTrue(result["summary"]["ok"], result)
        self.assertEqual(result["summary"]["total"], 13)
        self.assertEqual(
            tuple(result["registered_cases"]),
            formula_unit_suite.REGISTERED_CASE_IDS,
        )
        self.assertEqual(
            set(result["registered_cases"]),
            {
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
            },
        )
        self.assertEqual(
            result["metrics"]["EV-UNIT"],
            {"total": 13, "passed": 13, "failed": 0, "ok": True},
        )
        self.assertEqual(
            result["metrics"]["EV-FINSCEN"],
            {"total": 10, "passed": 10, "failed": 0, "ok": True},
        )

    def test_formula_unit_suite_cases_include_tolerance_expected_and_observed(self) -> None:
        result = formula_unit_suite.run_formula_unit_suite()

        for case in result["cases"]:
            self.assertEqual(case["status"], "PASS", case)
            self.assertIn("tolerance", case)
            self.assertIn("expected", case)
            self.assertIn("observed", case)
            self.assertTrue(case["metrics"])

    def test_formula_unit_suite_can_write_json_log(self) -> None:
        result = formula_unit_suite.run_formula_unit_suite()

        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "formula_unit_suite_results.json"
            written = formula_unit_suite.write_result_log(result, output)
            loaded = json.loads(written.read_text(encoding="utf-8"))

        self.assertEqual(loaded, result)

    def test_committed_formula_unit_suite_log_is_current(self) -> None:
        expected = formula_unit_suite.run_formula_unit_suite()
        loaded = json.loads(
            formula_unit_suite.RESULT_LOG_PATH.read_text(encoding="utf-8")
        )

        self.assertEqual(loaded, expected)


if __name__ == "__main__":
    unittest.main()

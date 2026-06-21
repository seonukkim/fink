from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.eval import runtime_gate_suite


class RuntimeGateSuiteTests(unittest.TestCase):
    def test_runtime_gate_suite_passes_all_selected_gates(self) -> None:
        result = runtime_gate_suite.run_runtime_gate_suite()

        self.assertTrue(result["summary"]["ok"], result)
        self.assertEqual(
            tuple(result["registered_gates"]),
            runtime_gate_suite.REGISTERED_GATE_IDS,
        )
        self.assertEqual(
            set(result["registered_gates"]),
            {
                "offline_integration_test",
                "privacy_redaction_test",
                "latency_memory_run",
            },
        )
        self.assertEqual(set(result["metrics"]), set(runtime_gate_suite.METRIC_IDS))
        self.assertEqual(
            result["metrics"]["EV-OFFLINE"],
            {"total": 1, "passed": 1, "failed": 0, "ok": True},
        )
        self.assertEqual(
            result["metrics"]["EV-PRIV"],
            {"total": 1, "passed": 1, "failed": 0, "ok": True},
        )
        self.assertEqual(
            result["metrics"]["EV-LAT"],
            {"total": 1, "passed": 1, "failed": 0, "ok": True},
        )
        self.assertEqual(
            result["metrics"]["EV-MEM"],
            {"total": 1, "passed": 1, "failed": 0, "ok": True},
        )

        by_id = {case["id"]: case for case in result["cases"]}
        offline = by_id["offline_integration_test"]["observed"]
        self.assertEqual(offline["network_attempts"], 0)
        self.assertIsNone(offline["runtime_error"])
        self.assertEqual(offline["workspace_removed_runs"], 2)

        privacy = by_id["privacy_redaction_test"]["observed"]
        self.assertEqual(privacy["leak_count"], 0)
        self.assertGreaterEqual(privacy["surface_count"], 6)

        latency_memory = by_id["latency_memory_run"]["observed"]
        self.assertEqual(latency_memory["measured_runs"], 2)
        self.assertGreaterEqual(latency_memory["max_latency_seconds"], 0.0)
        self.assertGreater(latency_memory["max_peak_memory_bytes"], 0)
        self.assertEqual(
            {run["input_mode"] for run in latency_memory["per_run"]},
            {"pdf", "paste"},
        )

    def test_runtime_gate_suite_artifact_can_be_written_without_private_markers(self) -> None:
        result = runtime_gate_suite.run_runtime_gate_suite()

        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "runtime_gate_suite_results.json"
            written = runtime_gate_suite.write_result_log(result, output)
            text = written.read_text(encoding="utf-8")
            loaded = json.loads(text)

        self.assertEqual(loaded, result)
        self._assert_no_private_marker_text(text)

    def test_committed_runtime_gate_log_is_public_safe_and_structured(self) -> None:
        text = runtime_gate_suite.RESULT_LOG_PATH.read_text(encoding="utf-8")
        loaded = json.loads(text)

        self.assertEqual(loaded["suite"], runtime_gate_suite.SUITE_ID)
        self.assertEqual(loaded["task_id"], runtime_gate_suite.TASK_ID)
        self.assertTrue(loaded["summary"]["ok"], loaded)
        self.assertEqual(
            tuple(loaded["registered_gates"]),
            runtime_gate_suite.REGISTERED_GATE_IDS,
        )
        self._assert_no_private_marker_text(text)

    def _assert_no_private_marker_text(self, text: str) -> None:
        for marker in runtime_gate_suite.PRIVATE_MARKERS_FOR_TESTS:
            self.assertNotIn(marker, text)
        self.assertNotIn("/tmp/", text)
        self.assertNotIn("\\AppData\\", text)


if __name__ == "__main__":
    unittest.main()

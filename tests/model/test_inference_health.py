from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from fink.model import runtime


class InferenceHealthTests(unittest.TestCase):
    def test_absent_component_is_not_installed_and_uses_fallback_path(self) -> None:
        manifest = runtime.load_runtime_manifest()
        component = manifest.components["qwen3_embedding_0_6b"]
        with tempfile.TemporaryDirectory(prefix="fink-health-test-") as tmp:
            home = Path(tmp)
            state = runtime.component_state(component, home)
            execution_path = runtime.execution_path_for_states(
                profile_id="core",
                states=(state,),
            )

        self.assertFalse(state.installed)
        self.assertFalse(state.files_present)
        self.assertEqual(state.status, runtime.MODEL_STATUS_NOT_INSTALLED)
        self.assertEqual(
            execution_path["model_status"]["summary_status"],
            runtime.MODEL_STATUS_DETERMINISTIC_FALLBACK_ACTIVE,
        )
        self.assertTrue(execution_path["deterministic_fallback_active"])
        self.assertEqual(
            execution_path["model_status"]["adapters"]["embedding"],
            runtime.MODEL_STATUS_NOT_INSTALLED,
        )

    def test_broken_component_fails_health_and_does_not_count_installed(self) -> None:
        manifest = runtime.load_runtime_manifest()
        component = manifest.components["qwen3_embedding_0_6b"]
        with tempfile.TemporaryDirectory(prefix="fink-health-test-") as tmp:
            home = Path(tmp)
            target = component.local_path(home)
            target.mkdir(parents=True)
            (target / runtime.LOCAL_CONFIG_FILE).write_text(
                json.dumps({"model_type": "fixture"}),
                encoding="utf-8",
            )
            (target / runtime.LOCAL_MARKER_FILE).write_text(
                json.dumps(
                    {
                        "id": "wrong-component",
                        "repo_id": component.repo_id,
                        "exact_revision": component.exact_revision,
                        "license": component.license,
                    }
                ),
                encoding="utf-8",
            )

            state = runtime.component_state(component, home)

        self.assertTrue(state.files_present)
        self.assertFalse(state.installed)
        self.assertEqual(state.status, runtime.MODEL_STATUS_FAILED_HEALTH_CHECK)
        self.assertIn("mismatch", state.health.error if state.health else "")

    def test_full_mock_install_runs_all_synthetic_inference_health_checks(self) -> None:
        with tempfile.TemporaryDirectory(prefix="fink-health-test-") as tmp:
            plan = runtime.run_install(
                profile_id="full",
                fink_home=Path(tmp),
                mock_download=True,
            )

        self.assertEqual(plan["missing_count"], 0)
        self.assertEqual(plan["failed_health_check_count"], 0)
        self.assertTrue(all(item["installed"] for item in plan["components"]))

        checks_by_adapter: dict[str, dict[str, object]] = {}
        for component in plan["components"]:
            for check in component["health_check"]["checks"]:
                checks_by_adapter[check["adapter"]] = check

        for adapter in (
            "ocr",
            "embedding",
            "reranker",
            "optional_extractor",
            "optional_explanation_qa",
        ):
            self.assertIn(adapter, checks_by_adapter)
            self.assertTrue(checks_by_adapter[adapter]["passed"])

        ocr_fields = checks_by_adapter["ocr"]["observed"]["normalized_fields"]
        self.assertIn(
            {
                "feature_id": "REVENUE_SHARE_RATE",
                "unit": "frac",
                "value_norm": "0.4",
                "source_span_ids": ["page-0:span-0"],
            },
            ocr_fields,
        )
        self.assertEqual(checks_by_adapter["reranker"]["observed"]["top_document_index"], 0)
        explanation = checks_by_adapter["optional_explanation_qa"]["observed"]
        self.assertEqual(explanation["language"], "ko")
        self.assertEqual(explanation["score_delta"], 0)
        self.assertIn(runtime.SYNTHETIC_HEALTH_CITATION, explanation["citation_ids"])

    def test_health_failure_blocks_marker_creation(self) -> None:
        manifest = runtime.load_runtime_manifest()
        component = manifest.components["qwen3_embedding_0_6b"]
        with tempfile.TemporaryDirectory(prefix="fink-health-test-") as tmp:
            home = Path(tmp)
            target = component.local_path(home)
            target.mkdir(parents=True)
            with self.assertRaises(runtime.LocalModelRuntimeError):
                runtime.write_install_marker(
                    component,
                    target,
                    health=runtime.ComponentHealthResult(
                        component_id=component.id,
                        status=runtime.MODEL_STATUS_FAILED_HEALTH_CHECK,
                        passed=False,
                        checks=(),
                        error="synthetic failure",
                    ),
                    weights_downloaded=True,
                    mock_runtime_fixture=False,
                )


if __name__ == "__main__":
    unittest.main()

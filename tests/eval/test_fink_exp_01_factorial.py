from __future__ import annotations

import json
import unittest

from scripts.eval import fink_exp_01_factorial as EXP


class FinkExp01FactorialTests(unittest.TestCase):
    def test_frozen_corpus_has_paired_synthetic_inputs_and_hidden_oracle(self) -> None:
        corpus = EXP.build_frozen_corpus()
        fixtures = tuple(corpus["production_fixtures"])
        oracle = tuple(corpus["oracle_hidden"])

        self.assertEqual(len(fixtures), 128)
        self.assertEqual(len(oracle), 128)
        self.assertEqual(len({row["pair_id"] for row in fixtures}), 64)
        self.assertEqual(
            {row["fixture_profile"]["variant"] for row in fixtures},
            set(EXP.VARIANTS),
        )
        self.assertEqual({row["input_mode"] for row in fixtures}, {"ocr", "paste"})

        forbidden_fixture_keys = {
            "oracle_findings",
            "oracle_rank",
            "risk_category",
            "expected_ranking",
            "oracle_exposure_weight",
            "is_benign",
        }
        for fixture in fixtures:
            self.assertFalse(forbidden_fixture_keys & set(fixture), fixture["doc_id"])
            self.assertTrue(fixture["fixture_profile"]["synthetic_only"])
            self.assertTrue(fixture["fixture_profile"]["no_real_contract"])
            self.assertIn("실제 계약이 아닌", fixture["rendered_text"])

        oracle_findings = [
            finding
            for row in oracle
            for finding in row["oracle_findings"]
        ]
        self.assertEqual(
            {finding["fim_module"] for finding in oracle_findings},
            {f"FIM-{index}" for index in range(1, 9)},
        )
        self.assertIn(
            "unsupported_practice_reference_only",
            {finding["authority_support_expected"] for finding in oracle_findings},
        )
        self.assertTrue(corpus["manifest"]["synthetic_only_boundary"]["no_real_contract"])

    def test_factorial_run_uses_production_path_and_oracle_weighted_metrics(self) -> None:
        result = EXP.run_factorial_experiment(bootstrap_samples=20)

        self.assertTrue(result["summary"]["ok"], result["cases"])
        self.assertEqual(set(result["arm_reports"]), {arm["arm_id"] for arm in EXP.ARM_CONFIGS})
        self.assertFalse(result["production_path"]["production_receives_oracle_fields"])
        self.assertIn("fink.scoring.rank_review_findings", result["production_path"]["shared_engines"])
        self.assertIn("fink.finance.fim8_evidence_opacity_uncertainty", result["production_path"]["shared_engines"])

        by_arm = result["arm_reports"]
        fixture_orders = {
            arm_id: [row["doc_id"] for row in report["raw_values"]]
            for arm_id, report in by_arm.items()
        }
        self.assertEqual(len({tuple(order) for order in fixture_orders.values()}), 1)

        for arm_id, report in by_arm.items():
            self.assertEqual(len(report["raw_values"]), 128, arm_id)
            for metric in EXP.PRIMARY_METRIC_IDS:
                value = report["metric_values"][metric]
                self.assertGreaterEqual(value, 0.0)
                self.assertLessEqual(value, 1.0)
                self.assertIn("ci95", report["confidence_intervals"][metric])
            for metric in ("EV-OEC@1", "EV-OEC@3"):
                denominator = report["metric_denominators"][metric]
                self.assertEqual(
                    denominator["weight_source"],
                    "hidden oracle exposure, not predicted exposure",
                )
                self.assertGreaterEqual(denominator["macro_type_count"], 5)

        self.assertGreater(
            result["metric_values"]["authority_off__exposure_aware"]["EV-USFR"],
            result["metric_values"]["authority_on__exposure_aware"]["EV-USFR"],
        )
        self.assertGreaterEqual(
            result["metric_values"]["authority_off__exposure_aware"]["EV-OEC@1"],
            result["metric_values"]["authority_off__severity_baseline"]["EV-OEC@1"],
        )
        self.assertGreater(result["failure_analysis"]["case_count"], 0)

    def test_committed_artifact_is_complete_and_ledger_values_are_measured(self) -> None:
        loaded = json.loads(EXP.RESULT_LOG_PATH.read_text(encoding="utf-8"))

        self.assertEqual(loaded["suite"], EXP.SUITE_ID)
        self.assertEqual(loaded["task_id"], EXP.TASK_ID)
        self.assertTrue(loaded["summary"]["ok"], loaded["cases"])
        self.assertRegex(loaded["commit"], r"^[0-9a-f]{40}$|^UNKNOWN$")
        self.assertIn("production_fixture_sha256", loaded["hashes"])
        self.assertIn("config/scoring_config.yaml", loaded["hashes"]["config_hashes"])
        self.assertEqual(loaded["corpus"]["doc_count"], 128)
        self.assertEqual(loaded["corpus"]["pair_count"], 64)
        self.assertGreater(loaded["failure_analysis"]["case_count"], 0)

        for row in loaded["result_ledger"]["rows"]:
            arm_id = row["experiment_id"].rsplit(":", maxsplit=1)[1]
            metric = row["metric"]
            measured = loaded["metric_values"][arm_id][metric]
            self.assertEqual(row["value"], f"{measured:.6f}")
            self.assertEqual(row["artifact_path"], EXP.ARTIFACT_PATH)
            self.assertEqual(row["status"], "measured")


if __name__ == "__main__":
    unittest.main()

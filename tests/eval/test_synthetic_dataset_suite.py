from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.eval import synthetic_dataset_suite


class SyntheticDatasetSuiteTests(unittest.TestCase):
    def test_builder_outputs_schema_valid_synthetic_examples_for_each_dr_and_split(self) -> None:
        examples = synthetic_dataset_suite.build_examples()

        self.assertEqual(len(examples), 62)
        self.assertEqual(
            {example.dataset_ref for example in examples},
            set(synthetic_dataset_suite.REQUIRED_DATASET_REFS),
        )
        for dataset_ref in synthetic_dataset_suite.REQUIRED_DATASET_REFS:
            splits = {
                example.split.value
                for example in examples
                if example.dataset_ref == dataset_ref
            }
            self.assertEqual(splits, {"dev", "frozen_eval"}, dataset_ref)

        for example in examples:
            self.assertTrue(example.is_synthetic, example.example_id)
            self.assertTrue(example.public_export, example.example_id)
            self.assertTrue(example.gold["synthetic_declared"], example.example_id)
            self.assertTrue(example.gold["no_real_contract_data"], example.example_id)
            self.assertTrue(example.gold["not_a_legal_verdict"], example.example_id)

    def test_synthetic_only_test_passes_on_committed_fixtures(self) -> None:
        result = synthetic_dataset_suite.run_synthetic_dataset_suite()
        by_id = {case["id"]: case for case in result["cases"]}

        self.assertEqual(
            tuple(result["registered_gates"]),
            synthetic_dataset_suite.REGISTERED_GATE_IDS,
        )
        self.assertEqual(by_id["synthetic_only_test"]["status"], "PASS")
        observed = by_id["synthetic_only_test"]["observed"]
        self.assertEqual(observed["issue_count"], 0, observed["issues"])
        self.assertEqual(observed["total_examples"], 62)
        self.assertEqual(
            set(observed["dataset_counts"]),
            set(synthetic_dataset_suite.REQUIRED_DATASET_REFS),
        )

    def test_frozen_split_hash_test_passes_and_keeps_splits_isolated(self) -> None:
        result = synthetic_dataset_suite.run_synthetic_dataset_suite()
        by_id = {case["id"]: case for case in result["cases"]}

        self.assertEqual(by_id["frozen_split_hash_test"]["status"], "PASS")
        observed = by_id["frozen_split_hash_test"]["observed"]
        self.assertEqual(observed["issue_count"], 0, observed["issues"])
        self.assertEqual(
            set(observed["frozen_file_hashes"]),
            set(synthetic_dataset_suite.REQUIRED_DATASET_REFS),
        )
        self.assertRegex(observed["combined_sha256"], r"^[a-f0-9]{64}$")

    def test_committed_data_files_are_deterministic_builder_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            generated_root = Path(tmpdir) / "eval"
            synthetic_dataset_suite.write_dataset(generated_root)
            expected_paths = [
                Path("frozen_eval_manifest.json"),
                *(
                    Path(split) / f"{dataset_ref}.jsonl"
                    for split in ("dev", "frozen_eval")
                    for dataset_ref in synthetic_dataset_suite.REQUIRED_DATASET_REFS
                ),
            ]
            for relative_path in expected_paths:
                with self.subTest(path=relative_path.as_posix()):
                    generated = (generated_root / relative_path).read_text(encoding="utf-8")
                    committed = (
                        synthetic_dataset_suite.DATA_ROOT / relative_path
                    ).read_text(encoding="utf-8")
                    self.assertEqual(committed, generated)

    def test_generated_scratch_dataset_passes_the_same_machine_gates(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            generated_root = Path(tmpdir) / "eval"
            synthetic_dataset_suite.write_dataset(generated_root)
            result = synthetic_dataset_suite.run_synthetic_dataset_suite(generated_root)

        self.assertTrue(result["summary"]["ok"], result)
        self.assertEqual(
            {case["id"] for case in result["cases"]},
            set(synthetic_dataset_suite.REGISTERED_GATE_IDS),
        )

    def test_committed_suite_log_is_current(self) -> None:
        expected = synthetic_dataset_suite.run_synthetic_dataset_suite()
        loaded = json.loads(
            synthetic_dataset_suite.RESULT_LOG_PATH.read_text(encoding="utf-8")
        )

        self.assertEqual(loaded, expected)


if __name__ == "__main__":
    unittest.main()

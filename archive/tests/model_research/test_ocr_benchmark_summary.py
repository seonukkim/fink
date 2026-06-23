from __future__ import annotations

import re
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
MODEL_CARD_PATH = REPO_ROOT / "docs" / "model-card.md"

EXPECTED_REVISIONS = {
    "PaddlePaddle/PaddleOCR-VL": "baee27eebcbf26cdeab160116679d765f13a3f27",
    "Qwen/Qwen3-VL-4B-Instruct": "ebb281ec70b05090aa6165b016eac8ec08e71b17",
}

REQUIRED_FIELD_FAMILIES = {
    "Money",
    "Percentages",
    "Dates",
    "Durations",
    "Article numbers",
}


def ocr_benchmark_section() -> str:
    text = MODEL_CARD_PATH.read_text(encoding="utf-8")
    match = re.search(
        r"^## OCR Extraction Benchmark Summary\n(?P<section>.*?)(?=^## |\Z)",
        text,
        flags=re.MULTILINE | re.DOTALL,
    )
    if not match:
        raise AssertionError("docs/model-card.md is missing the MR-07 OCR summary")
    return match.group("section")


def metric_rows(section: str) -> dict[str, tuple[int, int, float]]:
    rows: dict[str, tuple[int, int, float]] = {}
    row_pattern = re.compile(
        r"^\|\s*(?P<family>Money|Percentages|Dates|Durations|Article numbers)"
        r"\s*\|\s*(?P<gold>\d+)\s*\|\s*(?P<matches>\d+)\s*\|"
        r"\s*(?P<rate>\d+(?:\.\d+)?)%\s*\|$"
    )
    for line in section.splitlines():
        match = row_pattern.match(line)
        if match:
            rows[match.group("family")] = (
                int(match.group("gold")),
                int(match.group("matches")),
                float(match.group("rate")),
            )
    return rows


class OCRBenchmarkSummaryTests(unittest.TestCase):
    def test_summary_uses_synthetic_sanitized_inputs_only(self) -> None:
        section = ocr_benchmark_section()
        normalized = re.sub(r"\s+", " ", section)
        required_phrases = [
            "synthetic/sanitized only",
            "no real contract text",
            "private corpus",
            "model weights",
            "Hugging Face token",
            "measured on synthetic/sanitized fixtures",
            "must not be generalized",
        ]
        for phrase in required_phrases:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, normalized)

    def test_summary_records_exact_ocr_candidate_revisions(self) -> None:
        section = ocr_benchmark_section()
        for repo_id, revision in EXPECTED_REVISIONS.items():
            with self.subTest(repo_id=repo_id):
                self.assertIn(repo_id, section)
                self.assertIn(revision, section)
                self.assertRegex(revision, r"^[0-9a-f]{40}$")

    def test_summary_covers_required_extraction_field_families(self) -> None:
        rows = metric_rows(ocr_benchmark_section())
        self.assertEqual(set(rows), REQUIRED_FIELD_FAMILIES)
        for family, (gold, matches, rate) in rows.items():
            with self.subTest(family=family):
                self.assertGreater(gold, 0)
                self.assertGreaterEqual(matches, 0)
                self.assertLessEqual(matches, gold)
                self.assertGreaterEqual(rate, 0.0)
                self.assertLessEqual(rate, 100.0)

    def test_summary_includes_paper_experiments_note(self) -> None:
        section = ocr_benchmark_section()
        self.assertIn("Paper note for `05_experiments.md`", section)
        self.assertIn("FINK-MR-07", section)
        self.assertIn("41 gold items", section)
        self.assertIn("real-contract OCR accuracy claim", section)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from scripts.check_paper_sync import PaperSyncReport, check_paper_sync, template_hashes


REPO_ROOT = Path(__file__).resolve().parents[2]


class PaperSyncCheckerTests(unittest.TestCase):
    def test_real_repo_passes(self) -> None:
        report = check_paper_sync(REPO_ROOT)
        self.assertTrue(report.ok, report.format_violations())

    def test_clean_fixture_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self.write_clean_fixture(Path(tmp))
            report = check_paper_sync(root)
        self.assertTrue(report.ok, report.format_violations())

    def test_unsupported_result_claim_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self.write_clean_fixture(Path(tmp))
            note = root / "docs" / "paper" / "06_results.md"
            note.write_text(
                note.read_text(encoding="utf-8")
                + "\nEV-NEW measured 0.750000 on a synthetic fixture.\n",
                encoding="utf-8",
            )

            report = check_paper_sync(root)

        self.assertIn("UNSUPPORTED_PAPER_CLAIM", self.codes(report))

    def test_fabricated_note_value_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self.write_clean_fixture(Path(tmp))
            note = root / "docs" / "paper" / "06_results.md"
            note.write_text(
                note.read_text(encoding="utf-8").replace("0.500000", "0.900000"),
                encoding="utf-8",
            )

            report = check_paper_sync(root)

        self.assertIn("FABRICATED_NOTE_VALUE", self.codes(report))

    def test_fabricated_result_ledger_value_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self.write_clean_fixture(Path(tmp))
            result_ledger = root / "docs" / "paper" / "RESULT_LEDGER.csv"
            text = result_ledger.read_text(encoding="utf-8").replace(",0.500000,", ",0.900000,")
            result_ledger.write_text(text, encoding="utf-8")

            report = check_paper_sync(root)

        self.assertIn("FABRICATED_RESULT_VALUE", self.codes(report))

    def test_orphan_figure_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self.write_clean_fixture(Path(tmp))
            note = root / "docs" / "paper" / "06_results.md"
            note.write_text(
                note.read_text(encoding="utf-8") + "\n![Unregistered](missing.png)\n",
                encoding="utf-8",
            )

            report = check_paper_sync(root)

        self.assertIn("ORPHAN_FIGURE", self.codes(report))

    def test_template_modification_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self.write_clean_fixture(Path(tmp))
            template = root / "paper" / "template" / "icml2026" / "icml2026.sty"
            template.write_text("changed\n", encoding="utf-8")

            report = check_paper_sync(root)

        self.assertIn("TEMPLATE_MODIFIED", self.codes(report))

    @staticmethod
    def codes(report: PaperSyncReport) -> set[str]:
        return {violation.code for violation in report.violations}

    def write_clean_fixture(self, root: Path) -> Path:
        (root / "docs" / "paper").mkdir(parents=True)
        (root / "scripts" / "eval").mkdir(parents=True)
        (root / "site" / "assets" / "images").mkdir(parents=True)
        (root / "paper" / "template" / "icml2026").mkdir(parents=True)
        (root / "loop").mkdir()

        result_artifact = {
            "result_ledger": {
                "rows": [
                    {
                        "result_id": "FINK-S5-99-EV-TEST",
                        "experiment_id": "fixture_run",
                        "metric": "EV-TEST",
                        "value": "0.500000",
                    }
                ]
            },
            "metric_values": {"EV-TEST": 0.5},
        }
        (root / "scripts" / "eval" / "fixture_results.json").write_text(
            json.dumps(result_artifact),
            encoding="utf-8",
        )
        (root / "site" / "assets" / "images" / "figure.png").write_bytes(b"image")

        self.write_csv(
            root / "docs" / "paper" / "RESULT_LEDGER.csv",
            [
                "result_id",
                "experiment_id",
                "metric",
                "value",
                "artifact_path",
                "status",
                "reviewer",
                "notes",
            ],
            [
                [
                    "FINK-S5-99-EV-TEST",
                    "fixture_run",
                    "EV-TEST",
                    "0.500000",
                    "scripts/eval/fixture_results.json",
                    "measured",
                    "test",
                    "synthetic fixture",
                ]
            ],
        )
        self.write_csv(
            root / "docs" / "paper" / "CLAIM_LEDGER.csv",
            [
                "claim_id",
                "section",
                "claim_text",
                "evidence_file",
                "evidence_key",
                "status",
                "reviewer",
                "notes",
            ],
            [
                [
                    "CLM-S7-RES-EV-TEST",
                    "06_results.md",
                    "EV-TEST measured 0.500000 on the synthetic fixture.",
                    "RESULT_LEDGER.csv",
                    "FINK-S5-99-EV-TEST",
                    "measured",
                    "test",
                    "fixture",
                ]
            ],
        )
        self.write_csv(
            root / "docs" / "paper" / "FIGURE_REGISTRY.csv",
            [
                "figure_id",
                "title",
                "source_artifact",
                "paper_section",
                "site_section",
                "status",
                "notes",
            ],
            [
                [
                    "FIG-S7-99-TEST",
                    "Fixture figure",
                    "site/assets/images/figure.png",
                    "06_results.md",
                    "hero",
                    "registered",
                    "public-safe fixture",
                ]
            ],
        )

        (root / "docs" / "paper" / "06_results.md").write_text(
            "# Results\n\n"
            "| Metric | Value | Claim |\n"
            "|--------|------:|-------|\n"
            "| EV-TEST | 0.500000 | `CLM-S7-RES-EV-TEST` |\n"
            "`FIG-S7-99-TEST` registers the fixture figure.\n",
            encoding="utf-8",
        )
        (root / "site" / "index.html").write_text(
            '<img src="assets/images/figure.png" data-figure-id="FIG-S7-99-TEST">\n',
            encoding="utf-8",
        )
        (root / "paper" / "template" / "icml2026" / "icml2026.sty").write_text(
            "template\n",
            encoding="utf-8",
        )
        (root / "loop" / "STATE.json").write_text(
            json.dumps({"icml_template_hashes": template_hashes(root)}),
            encoding="utf-8",
        )
        return root

    @staticmethod
    def write_csv(path: Path, header: list[str], rows: list[list[str]]) -> None:
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(header)
            writer.writerows(rows)


if __name__ == "__main__":
    unittest.main()

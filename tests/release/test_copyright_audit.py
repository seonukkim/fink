from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from scripts import copyright_audit as ca


class CopyrightAuditTests(unittest.TestCase):
    def test_current_local_corpus_passes_when_present(self) -> None:
        corpus = Path("data/corpus")
        if not (corpus / ca.SOURCE_MANIFEST).is_file():
            self.skipTest("local git-ignored corpus is not imported")
        report = ca.run_audit(Path("."), corpus_dir=corpus, public_files=[])
        self.assertTrue(report.ok, [item.as_dict() for item in report.violations])
        self.assertIn("UNKNOWN", report.license_status_counts)
        self.assertIn("EV-A2-2021-SETTLEMENT", report.evidence_license_status)

    def test_license_status_is_surfaced(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            corpus = root / "corpus"
            self._write_source_manifest(
                corpus,
                [
                    {
                        "source_id": "A1-OK",
                        "authority_tier": "A1",
                        "public_export": "false",
                        "license_status": "UNKNOWN",
                    }
                ],
            )
            self._write_evidence(
                corpus,
                [
                    {
                        "evidence_id": "EV-1",
                        "source_id": "A1-OK",
                        "short_source_excerpt": "one two three",
                    }
                ],
            )
            report = ca.run_audit(root, corpus_dir=corpus, public_files=[])
        self.assertEqual(report.license_status_by_source_id["A1-OK"], "UNKNOWN")
        self.assertEqual(report.evidence_license_status["EV-1"], "UNKNOWN")
        self.assertTrue(report.ok)

    def test_unknown_license_public_export_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            corpus = root / "corpus"
            self._write_source_manifest(
                corpus,
                [
                    {
                        "source_id": "A1-BAD",
                        "authority_tier": "A1",
                        "public_export": "true",
                        "license_status": "UNKNOWN",
                    }
                ],
            )
            report = ca.run_audit(root, corpus_dir=corpus, public_files=[])
        self.assertIn("UNKNOWN_LICENSE_PUBLIC_EXPORT", self._codes(report))

    def test_bc_public_export_fails_for_manifest_and_cards(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            corpus = root / "corpus"
            self._write_source_manifest(
                corpus,
                [
                    {
                        "source_id": "B-KLL-RAG",
                        "authority_tier": "B",
                        "public_export": "true",
                        "license_status": "UNKNOWN",
                    }
                ],
            )
            self._write_jsonl(
                corpus / ca.KNOWLEDGE_CARDS,
                [
                    {
                        "card_id": "MC-1",
                        "authority_tier": "B/C",
                        "source_ids": ["B-KLL-RAG"],
                        "public_export": True,
                    }
                ],
            )
            report = ca.run_audit(root, corpus_dir=corpus, public_files=[])
        self.assertIn("PRIVATE_REFERENCE_PUBLIC_EXPORT", self._codes(report))

    def test_official_excerpt_must_be_under_fifteen_words(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            corpus = root / "corpus"
            self._write_source_manifest(
                corpus,
                [
                    {
                        "source_id": "A1-OK",
                        "authority_tier": "A1",
                        "public_export": "false",
                        "license_status": "UNKNOWN",
                    }
                ],
            )
            self._write_evidence(
                corpus,
                [
                    {
                        "evidence_id": "EV-LONG",
                        "source_id": "A1-OK",
                        "short_source_excerpt": " ".join(f"word{i}" for i in range(15)),
                    }
                ],
            )
            report = ca.run_audit(root, corpus_dir=corpus, public_files=[])
        self.assertIn("OFFICIAL_EXCERPT_TOO_LONG", self._codes(report))

    def test_long_private_book_passage_in_public_file_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            public = root / "export.md"
            long_private_line = "B-KLL " + (chr(0xAC00) * 121)
            public.write_text(long_private_line + "\n", encoding="utf-8")
            report = ca.run_audit(root, corpus_dir=root / "missing", public_files=[public])
        self.assertIn("LONG_PRIVATE_BOOK_PASSAGE", self._codes(report))

    @staticmethod
    def _codes(report: ca.CopyrightAuditReport) -> set[str]:
        return {violation.code for violation in report.violations}

    @staticmethod
    def _write_source_manifest(corpus: Path, rows: list[dict[str, str]]) -> None:
        path = corpus / ca.SOURCE_MANIFEST
        path.parent.mkdir(parents=True, exist_ok=True)
        fieldnames = ["source_id", "authority_tier", "public_export", "license_status"]
        with path.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    @staticmethod
    def _write_evidence(corpus: Path, rows: list[dict[str, str]]) -> None:
        path = corpus / ca.EVIDENCE_MATRIX
        path.parent.mkdir(parents=True, exist_ok=True)
        fieldnames = ["evidence_id", "source_id", "short_source_excerpt"]
        with path.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    @staticmethod
    def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        text = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
        path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    unittest.main()

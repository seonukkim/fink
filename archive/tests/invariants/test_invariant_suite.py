from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from scripts import invariant_suite as inv
from scripts.agent_loop import validate_repo as vr


class InvariantSuiteTests(unittest.TestCase):
    def test_current_local_corpus_passes_when_present(self) -> None:
        corpus = Path("data/corpus")
        if not (corpus / inv.SOURCE_MANIFEST).is_file():
            self.skipTest("local git-ignored corpus is not imported")
        report = inv.run_invariant_suite(Path("."), corpus_dir=corpus, public_files=[])
        self.assertTrue(report.ok, [item.as_dict() for item in report.violations])
        self.assertEqual(report.corpus_counts["evidence_records"], 20)
        self.assertEqual(report.corpus_counts["knowledge_cards"], 64)

    def test_clean_fixture_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            corpus = self._write_clean_corpus(root)
            report = inv.run_invariant_suite(root, corpus_dir=corpus, public_files=[])
        self.assertTrue(report.ok, [item.as_dict() for item in report.violations])

    def test_a_tier_evidence_must_be_score_eligible(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            corpus = self._write_clean_corpus(root)
            self._write_evidence(
                corpus,
                [
                    {
                        "evidence_id": "EV-A1-BAD",
                        "source_id": "A1-OK",
                        "source_class": "A1",
                        "authority_tier": "A1",
                        "short_source_excerpt": "one two three",
                        "score_eligible": "false",
                    }
                ],
            )
            report = inv.run_invariant_suite(root, corpus_dir=corpus, public_files=[])
        self.assertIn("EVIDENCE_ELIGIBILITY_MISMATCH", self._codes(report))

    def test_b_tier_evidence_cannot_score(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            corpus = self._write_clean_corpus(root)
            self._write_evidence(
                corpus,
                [
                    {
                        "evidence_id": "EV-B-BAD",
                        "source_id": "B-KLL-RAG",
                        "source_class": "B",
                        "authority_tier": "B",
                        "short_source_excerpt": "one two three",
                        "score_eligible": "true",
                    }
                ],
            )
            report = inv.run_invariant_suite(root, corpus_dir=corpus, public_files=[])
        codes = self._codes(report)
        self.assertIn("EVIDENCE_ELIGIBILITY_MISMATCH", codes)
        self.assertIn("EVIDENCE_NON_AUTHORITY_SOURCE_SCORE_ELIGIBLE", codes)

    def test_private_sources_and_cards_cannot_score_or_export_publicly(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            corpus = self._write_clean_corpus(root)
            self._write_source_manifest(
                corpus,
                [
                    self._source("A1-OK", "A1", "true", "false"),
                    self._source("B-KLL-RAG", "B", "true", "true"),
                ],
            )
            self._write_jsonl(
                corpus / inv.KNOWLEDGE_CARDS,
                [
                    {
                        "card_id": "MC-BAD",
                        "source_ids": ["B-KLL-RAG"],
                        "authority_tier": "B",
                        "score_eligible": True,
                        "public_export": True,
                    }
                ],
            )
            report = inv.run_invariant_suite(root, corpus_dir=corpus, public_files=[])
        codes = self._codes(report)
        self.assertIn("BC_SOURCE_SCORE_ELIGIBLE", codes)
        self.assertIn("KNOWLEDGE_CARD_SCORE_ELIGIBLE", codes)
        self.assertIn("PRIVATE_REFERENCE_PUBLIC_EXPORT", codes)

    def test_official_excerpt_limit_is_enforced(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            corpus = self._write_clean_corpus(root)
            self._write_evidence(
                corpus,
                [
                    {
                        "evidence_id": "EV-LONG",
                        "source_id": "A1-OK",
                        "source_class": "A1",
                        "authority_tier": "A1",
                        "short_source_excerpt": " ".join(f"word{i}" for i in range(15)),
                        "score_eligible": "true",
                    }
                ],
            )
            report = inv.run_invariant_suite(root, corpus_dir=corpus, public_files=[])
        self.assertIn("OFFICIAL_EXCERPT_TOO_LONG", self._codes(report))

    def test_public_private_material_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            corpus = self._write_clean_corpus(root)
            public = root / "export.md"
            public.write_text("B-KLL " + (chr(0xAC00) * 120) + "\n", encoding="utf-8")
            report = inv.run_invariant_suite(root, corpus_dir=corpus, public_files=[public])
        self.assertIn("LONG_PRIVATE_BOOK_PASSAGE", self._codes(report))

    def test_contract_text_marker_in_logs_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            corpus = self._write_clean_corpus(root)
            logs = root / "logs"
            logs.mkdir()
            (logs / "run.log").write_text(
                "raw_contract_text=creator payment clause\n",
                encoding="utf-8",
            )
            report = inv.run_invariant_suite(
                root,
                corpus_dir=corpus,
                public_files=[],
                log_dirs=[logs],
            )
        self.assertIn("CONTRACT_TEXT_IN_LOG", self._codes(report))

    def test_validate_repo_gate_calls_invariant_suite(self) -> None:
        out = vr.invariant_suite()
        self.assertIn("invariant_suite", out)

    @staticmethod
    def _codes(report: inv.InvariantReport) -> set[str]:
        return {violation.code for violation in report.violations}

    def _write_clean_corpus(self, root: Path) -> Path:
        corpus = root / "corpus"
        self._write_source_manifest(
            corpus,
            [
                self._source("A1-OK", "A1", "true", "false"),
                self._source("B-KLL-RAG", "B", "false", "false"),
            ],
        )
        self._write_evidence(
            corpus,
            [
                {
                    "evidence_id": "EV-A1-OK",
                    "source_id": "A1-OK",
                    "source_class": "A1",
                    "authority_tier": "A1",
                    "short_source_excerpt": "one two three",
                    "score_eligible": "true",
                }
            ],
        )
        self._write_jsonl(
            corpus / inv.KNOWLEDGE_CARDS,
            [
                {
                    "card_id": "MC-OK",
                    "source_ids": ["B-KLL-RAG"],
                    "authority_tier": "B/C",
                    "score_eligible": False,
                    "public_export": False,
                }
            ],
        )
        self._write_jsonl(
            corpus / inv.CHECKLIST_ITEMS,
            [
                {
                    "check_id": "CHK-OK",
                    "educational_source_ids": ["B-KLL-RAG"],
                    "practical_source_ids": [],
                    "score_eligible": False,
                }
            ],
        )
        self._write_glossary(corpus, score_eligible="false")
        return corpus

    @staticmethod
    def _source(
        source_id: str,
        tier: str,
        score_eligible: str,
        public_export: str,
    ) -> dict[str, str]:
        return {
            "source_id": source_id,
            "source_class": tier,
            "authority_tier": tier,
            "score_eligible": score_eligible,
            "public_export": public_export,
            "license_status": "UNKNOWN",
        }

    @staticmethod
    def _write_source_manifest(corpus: Path, rows: list[dict[str, str]]) -> None:
        path = corpus / inv.SOURCE_MANIFEST
        path.parent.mkdir(parents=True, exist_ok=True)
        fieldnames = [
            "source_id",
            "source_class",
            "authority_tier",
            "score_eligible",
            "public_export",
            "license_status",
        ]
        with path.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    @staticmethod
    def _write_evidence(corpus: Path, rows: list[dict[str, str]]) -> None:
        path = corpus / inv.EVIDENCE_MATRIX
        path.parent.mkdir(parents=True, exist_ok=True)
        fieldnames = [
            "evidence_id",
            "source_id",
            "source_class",
            "authority_tier",
            "short_source_excerpt",
            "score_eligible",
        ]
        with path.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    @staticmethod
    def _write_glossary(corpus: Path, *, score_eligible: str) -> None:
        path = corpus / inv.GLOSSARY
        path.parent.mkdir(parents=True, exist_ok=True)
        fieldnames = ["canonical_id", "source_ids", "score_eligible"]
        with path.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerow(
                {
                    "canonical_id": "TERM-OK",
                    "source_ids": "B-KLL-RAG",
                    "score_eligible": score_eligible,
                }
            )

    @staticmethod
    def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        text = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
        path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    unittest.main()

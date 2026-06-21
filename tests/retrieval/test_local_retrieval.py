from __future__ import annotations

import csv
import importlib
import json
import socket
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch


def _load_module(name: str) -> Any:
    src_root = Path(__file__).resolve().parents[2] / "src"
    src_text = src_root.as_posix()
    if src_text not in sys.path:
        sys.path.insert(0, src_text)
    return importlib.import_module(name)


RETRIEVAL = _load_module("fink.retrieval")


def _chunk(
    chunk_id: str,
    text: str,
    *,
    chunk_type: str = "evidence",
    authority_tier: str = "A1",
    risk_categories: tuple[str, ...] = ("F1",),
    score_eligible: bool = True,
    practice_reference: bool = False,
) -> Any:
    source_id = f"{authority_tier}-TEST"
    return RETRIEVAL.RetrievalChunk(
        chunk_id=chunk_id,
        chunk_type=chunk_type,
        text=text,
        title=chunk_id,
        source_id=source_id,
        source_ids=(source_id,),
        source_class=authority_tier,
        authority_tier=authority_tier,
        verification_status="UNVERIFIED",
        risk_categories=risk_categories,
        hierarchy=(f"tier:{authority_tier}", f"source:{source_id}", f"chunk:{chunk_id}"),
        score_eligible=score_eligible,
        practice_reference=practice_reference,
        public_export=False,
        generated_translation=practice_reference,
    )


class LocalRetrievalTests(unittest.TestCase):
    def test_retrieval_offline_test_builds_bm25_and_queries_without_socket(self) -> None:
        index = RETRIEVAL.LocalBM25Index(
            (
                _chunk(
                    "EV-F1-SETTLEMENT",
                    "monthly settlement statement audit 정산서 감사 정산 투명성",
                ),
                _chunk(
                    "MC-F1-QUESTION",
                    "ask for settlement records audit rights 정산자료 요청",
                    chunk_type="knowledge_card",
                    authority_tier="B/C",
                    score_eligible=False,
                    practice_reference=True,
                ),
                _chunk(
                    "EV-F7-PENALTY",
                    "termination penalty liability 손해배상 위약금",
                    risk_categories=("F7",),
                ),
            )
        )

        with patch.object(socket, "socket", side_effect=AssertionError("network blocked")):
            results = index.query("settlement audit 정산서", k=3)

        self.assertGreaterEqual(len(results), 2)
        self.assertEqual(results[0].chunk.chunk_id, "EV-F1-SETTLEMENT")
        self.assertEqual(results[0].chunk.source_id, "A1-TEST")
        self.assertEqual(results[0].chunk.authority_tier, "A1")
        self.assertEqual(results[0].chunk.verification_status, "UNVERIFIED")
        self.assertFalse(results[0].chunk.practice_reference)
        self.assertTrue(any(result.chunk.practice_reference for result in results))
        self.assertTrue(all(result.matched_terms for result in results))

    def test_hierarchical_corpus_loads_stage_records_and_preserves_authority(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            corpus_dir = Path(tmp)
            _write_minimal_stage_one_corpus(corpus_dir)

            corpus = RETRIEVAL.load_hierarchical_corpus(corpus_dir)

        by_id = {chunk.chunk_id: chunk for chunk in corpus.documents}
        self.assertEqual(corpus.counts_by_type["evidence"], 1)
        self.assertEqual(corpus.counts_by_type["knowledge_card"], 1)
        self.assertEqual(corpus.counts_by_type["checklist_item"], 1)
        self.assertEqual(corpus.counts_by_type["glossary_term"], 1)

        evidence = by_id["EV-F3-PAYMENT"]
        self.assertEqual(evidence.hierarchy[0], "tier:A1")
        self.assertEqual(evidence.authority_tier, "A1")
        self.assertTrue(evidence.score_eligible)
        self.assertFalse(evidence.practice_reference)
        self.assertEqual(evidence.verification_status, "UNVERIFIED")

        card = by_id["MC-F3-CASHFLOW"]
        self.assertEqual(card.authority_tier, "B/C")
        self.assertFalse(card.score_eligible)
        self.assertTrue(card.practice_reference)
        self.assertFalse(card.public_export)

        glossary = by_id["GL-CANON_PAYMENT_DELAY"]
        self.assertEqual(glossary.canonical_id, "CANON_PAYMENT_DELAY")
        self.assertTrue(glossary.generated_translation)
        self.assertIn("risk:F3", glossary.hierarchy)

    def test_recall_harness_computes_ev_r_at_3_and_r_at_5(self) -> None:
        index = RETRIEVAL.LocalBM25Index(
            (
                _chunk(
                    "EV-F3-PAYMENT",
                    "payment due delay cashflow 지급 지연",
                    risk_categories=("F3",),
                ),
                _chunk(
                    "EV-F7-TERMINATION",
                    "termination penalty damages 위약금 해지",
                    risk_categories=("F7",),
                ),
                _chunk(
                    "EV-F5-IP",
                    "secondary rights copyright monetization",
                    risk_categories=("F5",),
                ),
            )
        )
        cases = (
            RETRIEVAL.RetrievalCase(
                query_id="q-payment",
                query="late payment cashflow 지급 지연",
                relevant_chunk_ids=("EV-F3-PAYMENT",),
                risk_categories=("F3",),
            ),
            RETRIEVAL.RetrievalCase(
                query_id="q-penalty",
                query="termination penalty damages",
                relevant_chunk_ids=("EV-F7-TERMINATION",),
                risk_categories=("F7",),
            ),
        )

        metrics = RETRIEVAL.recall_harness(index, cases)

        self.assertEqual(metrics.total_cases, 2)
        self.assertEqual(metrics.ev_r_at_3, 1.0)
        self.assertEqual(metrics.ev_r_at_5, 1.0)
        self.assertEqual(metrics.as_dict()["EV-R@3"], 1.0)
        self.assertEqual(metrics.as_dict()["EV-R@5"], 1.0)

    def test_index_persistence_round_trips_without_external_dependencies(self) -> None:
        index = RETRIEVAL.LocalBM25Index(
            (
                _chunk("EV-F2-REVENUE", "revenue share deductions gross sales"),
                _chunk("EV-F4-MG", "minimum guarantee advance recoupment", risk_categories=("F4",)),
            )
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "index.json"
            index.save(path)
            loaded = RETRIEVAL.LocalBM25Index.load(path)

        results = loaded.query("advance recoupment", k=1)

        self.assertEqual(results[0].chunk.chunk_id, "EV-F4-MG")
        self.assertEqual(loaded.documents[0].chunk_id, "EV-F2-REVENUE")

    def test_koen_consistency_harness_computes_ev_koen_and_caveats(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            corpus_dir = Path(tmp)
            rows = _non_equivalence_glossary_rows()
            _write_minimal_stage_one_corpus(corpus_dir, glossary_rows=rows)
            corpus = RETRIEVAL.load_hierarchical_corpus(corpus_dir)

        glossary_chunks = tuple(
            chunk for chunk in corpus.documents if chunk.chunk_type == "glossary_term"
        )
        self.assertEqual(len(glossary_chunks), 8)
        self.assertTrue(all(chunk.non_equivalence_caveat for chunk in glossary_chunks))
        self.assertTrue(all(chunk.generated_translation for chunk in glossary_chunks))
        self.assertFalse(any(chunk.score_eligible for chunk in glossary_chunks))

        index = RETRIEVAL.LocalBM25Index(corpus.documents)
        pairs = tuple(
            RETRIEVAL.BilingualQueryPair(
                query_id=f"koen-{row['canonical_id'].lower()}",
                query_ko=row["preferred_ko"],
                query_en=row["preferred_en"],
                expected_canonical_id=row["canonical_id"],
                requires_non_equivalence_caveat=True,
            )
            for row in rows
        )

        metrics = RETRIEVAL.koen_consistency_harness(index, pairs, k=1)

        self.assertEqual(metrics.ev_koen, 1.0)
        self.assertEqual(metrics.top_k_consistency, 1.0)
        self.assertEqual(metrics.caveat_coverage, 1.0)
        self.assertTrue(metrics.english_never_labeled_evidence)
        self.assertEqual(metrics.as_dict()["EV-KOEN"], 1.0)
        for row in metrics.per_query:
            self.assertTrue(row["same_top1"])
            self.assertTrue(row["same_top_k"])
            self.assertTrue(row["non_equivalence_caveat_present"])
            self.assertFalse(row["english_labeled_evidence"])

    def test_glossary_loader_rejects_english_aliases_not_marked_generated(self) -> None:
        rows = list(_non_equivalence_glossary_rows())
        rows[0] = {**rows[0], "generated_translation": "false"}
        with tempfile.TemporaryDirectory() as tmp:
            corpus_dir = Path(tmp)
            _write_minimal_stage_one_corpus(corpus_dir, glossary_rows=tuple(rows))

            with self.assertRaisesRegex(
                RETRIEVAL.RetrievalCorpusError,
                "English labels must be generated aliases",
            ):
                RETRIEVAL.load_hierarchical_corpus(corpus_dir)


def _write_minimal_stage_one_corpus(
    corpus_dir: Path,
    *,
    glossary_rows: tuple[dict[str, str], ...] | None = None,
) -> None:
    stage = corpus_dir / "stage-1"
    stage.mkdir(parents=True)
    _write_csv(
        stage / "14_MASTER_EVIDENCE_MATRIX.csv",
        (
            {
                "evidence_id": "EV-F3-PAYMENT",
                "source_id": "A1-PAYMENT",
                "source_class": "A1",
                "authority_tier": "A1",
                "article_or_section": "Section 3",
                "page_or_slide": "p.1",
                "short_source_excerpt": "payment due date",
                "canonical_url": "https://example.invalid/local",
                "verification_status": "UNVERIFIED",
                "supports_protection": "true",
                "supports_review_signal": "true",
                "risk_categories": "F3",
                "financial_variables": "PAYMENT_DUE_DAYS",
                "score_eligible": "true",
                "notes": "synthetic fixture",
            },
        ),
    )
    _write_jsonl(
        stage / "15_MASTER_KNOWLEDGE_CARDS.jsonl",
        (
            {
                "card_id": "MC-F3-CASHFLOW",
                "source_card_ids": ["SRC-1"],
                "source_ids": ["B-BOOK", "C-GUIDE"],
                "authority_tier": "B/C",
                "score_eligible": False,
                "risk_categories": ["F3"],
                "title_ko": "지급 지연",
                "title_en": "Payment delay",
                "explanation_ko": "지급 시기 확인",
                "explanation_en": "Check payment timing",
                "aliases_ko": ["정산 지연"],
                "aliases_en": ["cashflow delay"],
                "financial_variables": ["PAYMENT_DUE_DAYS"],
                "page_or_slide_references": ["SYN-P01"],
                "evidence_ids": ["EV-F3-PAYMENT"],
                "evidence_strength": "practice",
                "conflicts": [],
                "generated_translation": True,
                "public_export": False,
                "notes": "synthetic fixture",
            },
        ),
    )
    _write_jsonl(
        stage / "11_MASTER_CREATOR_CHECKLIST.jsonl",
        (
            {
                "check_id": "CHK-F3-PAYMENT",
                "risk_category": "F3",
                "question_ko": "지급기한이 명확한가?",
                "question_en": "Is the due date clear?",
                "positive_protections": ["clear due date"],
                "review_signals": ["missing due date"],
                "financial_variables": ["PAYMENT_DUE_DAYS"],
                "possible_financial_effects": ["cashflow delay"],
                "official_evidence_ids": ["EV-F3-PAYMENT"],
                "educational_source_ids": ["B-BOOK"],
                "practical_source_ids": ["C-GUIDE"],
                "score_eligible": False,
                "human_review_required": True,
                "notes": "synthetic fixture",
            },
        ),
    )
    _write_csv(
        stage / "13_MASTER_BILINGUAL_GLOSSARY.csv",
        glossary_rows
        or (
            {
                "canonical_id": "CANON_PAYMENT_DELAY",
                "preferred_ko": "지급 지연",
                "preferred_en": "payment delay",
                "risk_category": "F3",
                "aliases_ko": "정산 지연",
                "aliases_en": "cashflow delay",
                "source_ids": "B-BOOK;C-GUIDE",
                "merged_src_canonical_ids": "",
                "generated_translation": "true",
                "score_eligible": "false",
                "non_equivalence_caveat": "",
                "notes": "synthetic fixture",
            },
        ),
    )


def _non_equivalence_glossary_rows() -> tuple[dict[str, str], ...]:
    caveat = (
        "Generated English alias for retrieval only; Korean source term remains canonical "
        "and no legal equivalence is asserted."
    )
    return (
        _glossary_row(
            "CANON_ASSIGNMENT_LICENSE_BOUNDARY",
            "저작권 양도와 이용허락",
            "assignment license boundary",
            "양도;이용허락",
            "assignment;license",
            caveat,
        ),
        _glossary_row(
            "CANON_RESCISSION",
            "해제",
            "rescission",
            "계약 해제",
            "rescission;contract cancellation",
            caveat,
        ),
        _glossary_row(
            "CANON_TERMINATION",
            "해지",
            "termination",
            "계약 해지",
            "termination",
            caveat,
        ),
        _glossary_row(
            "CANON_WORK_MADE_FOR_HIRE",
            "업무상저작물",
            "work made for hire",
            "업무상 저작물",
            "work-made-for-hire",
            caveat,
        ),
        _glossary_row(
            "CANON_PUBLICITY",
            "초상 등 영리 이용",
            "publicity",
            "퍼블리시티",
            "publicity;image likeness",
            caveat,
        ),
        _glossary_row(
            "CANON_LIQUIDATED_DAMAGES",
            "손해배상액 예정",
            "liquidated damages",
            "위약벌;예정 손해배상",
            "liquidated damages",
            caveat,
        ),
        _glossary_row(
            "CANON_CONSIDERATION",
            "대가",
            "consideration",
            "계약 대가",
            "consideration;payment basis",
            caveat,
        ),
        _glossary_row(
            "CANON_DEPOSIT",
            "계약금",
            "deposit",
            "보증금;선급 계약금",
            "deposit",
            caveat,
        ),
    )


def _glossary_row(
    canonical_id: str,
    preferred_ko: str,
    preferred_en: str,
    aliases_ko: str,
    aliases_en: str,
    caveat: str,
) -> dict[str, str]:
    return {
        "canonical_id": canonical_id,
        "preferred_ko": preferred_ko,
        "preferred_en": preferred_en,
        "risk_category": "F5",
        "aliases_ko": aliases_ko,
        "aliases_en": aliases_en,
        "source_ids": "B-BOOK;C-GUIDE",
        "merged_src_canonical_ids": "",
        "generated_translation": "true",
        "score_eligible": "false",
        "non_equivalence_caveat": caveat,
        "notes": "synthetic non-equivalence fixture",
    }


def _write_csv(path: Path, rows: tuple[dict[str, str], ...]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=tuple(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _write_jsonl(path: Path, rows: tuple[dict[str, Any], ...]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


if __name__ == "__main__":
    unittest.main()

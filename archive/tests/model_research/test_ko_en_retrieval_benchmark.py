from __future__ import annotations

import importlib
import re
import sys
import unittest
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
MODEL_CARD_PATH = REPO_ROOT / "docs" / "model-card.md"

MACHINE_GATE = "ko_en_retrieval_benchmark"
FIXTURE_ID = "ko_en_retrieval_synthetic_v1"
MODEL_PROFILE_ID = "core_local_offline_v1"
BENCHMARK_K = 1

EXPECTED_REVISIONS = {
    "Qwen/Qwen3-Embedding-0.6B": "97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3",
    "Qwen/Qwen3-Reranker-0.6B": "e61197ed45024b0ed8a2d74b80b4d909f1255473",
}

CAVEAT = (
    "Generated English alias for retrieval only; Korean source term remains canonical "
    "and no legal equivalence is asserted."
)

PAIR_ROWS: tuple[dict[str, str], ...] = (
    {
        "slug": "assignment-license",
        "canonical_id": "CANON_ASSIGNMENT_LICENSE_BOUNDARY",
        "ko_query": "저작권 양도 이용허락",
        "en_query": "assignment license boundary",
        "aliases": "양도 이용허락 assignment license transfer permission",
    },
    {
        "slug": "rescission",
        "canonical_id": "CANON_RESCISSION",
        "ko_query": "계약 해제",
        "en_query": "rescission",
        "aliases": "해제 rescission contract cancellation",
    },
    {
        "slug": "termination",
        "canonical_id": "CANON_TERMINATION",
        "ko_query": "계약 해지",
        "en_query": "termination",
        "aliases": "해지 termination ongoing contract end",
    },
    {
        "slug": "work-made-for-hire",
        "canonical_id": "CANON_WORK_MADE_FOR_HIRE",
        "ko_query": "업무상저작물",
        "en_query": "work made for hire",
        "aliases": "업무상 저작물 work-made-for-hire employee work",
    },
    {
        "slug": "publicity",
        "canonical_id": "CANON_PUBLICITY",
        "ko_query": "초상 영리 이용",
        "en_query": "publicity image likeness",
        "aliases": "초상 등 영리 이용 퍼블리시티 publicity likeness",
    },
    {
        "slug": "liquidated-damages",
        "canonical_id": "CANON_LIQUIDATED_DAMAGES",
        "ko_query": "손해배상액 예정",
        "en_query": "liquidated damages",
        "aliases": "손해배상액 예정 위약벌 liquidated damages preset damages",
    },
    {
        "slug": "consideration",
        "canonical_id": "CANON_CONSIDERATION",
        "ko_query": "계약 대가",
        "en_query": "consideration payment basis",
        "aliases": "대가 consideration payment basis compensation",
    },
    {
        "slug": "deposit",
        "canonical_id": "CANON_DEPOSIT",
        "ko_query": "계약금",
        "en_query": "deposit",
        "aliases": "계약금 보증금 선급 계약금 deposit advance deposit",
    },
)


def _load_module(name: str) -> Any:
    src_root = REPO_ROOT / "src"
    src_text = src_root.as_posix()
    if src_text not in sys.path:
        sys.path.insert(0, src_text)
    return importlib.import_module(name)


RETRIEVAL = _load_module("fink.retrieval")


def ko_en_retrieval_benchmark() -> dict[str, Any]:
    """Run the public-safe MR-08 KO/EN canonical-ID consistency benchmark."""

    index = RETRIEVAL.LocalBM25Index(_retrieval_chunks())
    metrics = RETRIEVAL.koen_consistency_harness(index, _query_pairs(), k=BENCHMARK_K)
    passed = (
        metrics.ev_koen == 1.0
        and metrics.top_k_consistency == 1.0
        and metrics.caveat_coverage == 1.0
        and metrics.english_never_labeled_evidence
    )
    return {
        "status": "ko_en_retrieval_benchmark_passed" if passed else "failed",
        "machine_gate": MACHINE_GATE,
        "fixture_id": FIXTURE_ID,
        "model_profile_id": MODEL_PROFILE_ID,
        "k": BENCHMARK_K,
        "total_pairs": metrics.total_pairs,
        "canonical_id_matches": metrics.consistent_pairs,
        "top_k_consistent_pairs": metrics.top_k_consistent_pairs,
        "EV-KOEN": metrics.ev_koen,
        "top_k_consistency": metrics.top_k_consistency,
        "caveat_coverage": metrics.caveat_coverage,
        "english_never_labeled_evidence": metrics.english_never_labeled_evidence,
        "english_labeled_evidence_violations": (
            metrics.english_labeled_evidence_violations
        ),
        "synthetic_sanitized": True,
        "per_query": list(metrics.per_query),
    }


def _retrieval_chunks() -> tuple[Any, ...]:
    chunks = [
        _glossary_chunk(row)
        for row in PAIR_ROWS
    ]
    chunks.extend(
        (
            _evidence_decoy(
                "EV-SYN-F7-TERMINATION-DECOY",
                "termination penalty liability 해지 위약금 손해배상",
                "F7",
            ),
            _evidence_decoy(
                "EV-SYN-F5-IP-DECOY",
                "assignment license secondary rights 저작권 이용허락",
                "F5",
            ),
        )
    )
    return tuple(chunks)


def _glossary_chunk(row: dict[str, str]) -> Any:
    return RETRIEVAL.RetrievalChunk(
        chunk_id=f"GL-{row['canonical_id']}",
        chunk_type="glossary_term",
        title=row["canonical_id"],
        text=(
            f"{row['canonical_id']} {row['ko_query']} {row['en_query']} "
            f"{row['aliases']}"
        ),
        source_id="SYNTH-DR8",
        source_ids=("SYNTH-DR8",),
        source_class="B/C",
        authority_tier="B/C",
        verification_status="UNVERIFIED",
        risk_categories=("F5",),
        canonical_id=row["canonical_id"],
        non_equivalence_caveat=CAVEAT,
        hierarchy=(
            "tier:B/C",
            "source:SYNTH-DR8",
            "risk:F5",
            f"chunk:GL-{row['canonical_id']}",
        ),
        score_eligible=False,
        practice_reference=True,
        public_export=False,
        generated_translation=True,
        metadata={"fixture_id": FIXTURE_ID, "slug": row["slug"]},
    )


def _evidence_decoy(chunk_id: str, text: str, risk_category: str) -> Any:
    return RETRIEVAL.RetrievalChunk(
        chunk_id=chunk_id,
        chunk_type="evidence",
        title=chunk_id,
        text=text,
        source_id="A1-SYNTH",
        source_ids=("A1-SYNTH",),
        source_class="A1",
        authority_tier="A1",
        verification_status="UNVERIFIED",
        risk_categories=(risk_category,),
        hierarchy=("tier:A1", "source:A1-SYNTH", f"risk:{risk_category}", chunk_id),
        score_eligible=True,
        practice_reference=False,
        public_export=False,
        generated_translation=False,
        metadata={"fixture_id": FIXTURE_ID, "decoy": True},
    )


def _query_pairs() -> tuple[Any, ...]:
    return tuple(
        RETRIEVAL.BilingualQueryPair(
            query_id=f"koen-{row['slug']}",
            query_ko=row["ko_query"],
            query_en=row["en_query"],
            expected_canonical_id=row["canonical_id"],
            requires_non_equivalence_caveat=True,
        )
        for row in PAIR_ROWS
    )


def benchmark_section() -> str:
    text = MODEL_CARD_PATH.read_text(encoding="utf-8")
    match = re.search(
        r"^## KO/EN Retrieval Consistency Benchmark\n(?P<section>.*?)(?=^## |\Z)",
        text,
        flags=re.MULTILINE | re.DOTALL,
    )
    if not match:
        raise AssertionError("docs/model-card.md is missing the MR-08 retrieval summary")
    return match.group("section")


class KOENRetrievalBenchmarkTests(unittest.TestCase):
    def test_ko_and_en_pairs_resolve_to_the_same_canonical_ids(self) -> None:
        result = ko_en_retrieval_benchmark()

        self.assertEqual(result["status"], "ko_en_retrieval_benchmark_passed")
        self.assertEqual(result["machine_gate"], MACHINE_GATE)
        self.assertEqual(result["fixture_id"], FIXTURE_ID)
        self.assertEqual(result["total_pairs"], 8)
        self.assertEqual(result["canonical_id_matches"], 8)
        self.assertEqual(result["top_k_consistent_pairs"], 8)
        self.assertEqual(result["EV-KOEN"], 1.0)
        self.assertEqual(result["top_k_consistency"], 1.0)

        for row in result["per_query"]:
            with self.subTest(query_id=row["query_id"]):
                self.assertEqual(row["ko_canonical_ids"], row["en_canonical_ids"])
                self.assertEqual(row["ko_canonical_ids"], [row["expected_canonical_id"]])
                self.assertTrue(row["same_top1"])
                self.assertTrue(row["same_top_k"])
                self.assertTrue(row["consistent"])

    def test_english_aliases_are_not_evidence_or_score_eligible(self) -> None:
        chunks = _retrieval_chunks()
        glossary_chunks = [chunk for chunk in chunks if chunk.chunk_type == "glossary_term"]

        self.assertEqual(len(glossary_chunks), 8)
        for chunk in glossary_chunks:
            with self.subTest(canonical_id=chunk.canonical_id):
                self.assertTrue(chunk.generated_translation)
                self.assertFalse(chunk.score_eligible)
                self.assertTrue(chunk.practice_reference)
                self.assertEqual(chunk.authority_tier, "B/C")
                self.assertEqual(chunk.verification_status, "UNVERIFIED")
                self.assertEqual(chunk.non_equivalence_caveat, CAVEAT)

        result = ko_en_retrieval_benchmark()
        self.assertTrue(result["english_never_labeled_evidence"])
        self.assertEqual(result["english_labeled_evidence_violations"], 0)
        self.assertEqual(result["caveat_coverage"], 1.0)

    def test_fixture_is_synthetic_sanitized_and_public_safe(self) -> None:
        result = ko_en_retrieval_benchmark()
        self.assertTrue(result["synthetic_sanitized"])

        forbidden_fragments = (
            ".fink",
            "private_root",
            "hf_token",
            "real contract",
            "pdf",
            "zip",
        )
        fixture_text = "\n".join(
            chunk.text for chunk in _retrieval_chunks() if chunk.metadata.get("fixture_id")
        )
        for fragment in forbidden_fragments:
            with self.subTest(fragment=fragment):
                self.assertNotIn(fragment, fixture_text.lower())

    def test_model_card_records_public_benchmark_summary(self) -> None:
        section = benchmark_section()
        normalized = re.sub(r"\s+", " ", section)

        required_phrases = [
            MACHINE_GATE,
            FIXTURE_ID,
            MODEL_PROFILE_ID,
            "synthetic/sanitized only",
            "English labels are generated retrieval aliases only",
            "never evidence",
            "must not be generalized",
            "8/8",
            "1.000",
            "Paper note for `05_experiments.md`",
            "FINK-MR-08",
        ]
        for phrase in required_phrases:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, normalized)

        for repo_id, revision in EXPECTED_REVISIONS.items():
            with self.subTest(repo_id=repo_id):
                self.assertIn(repo_id, section)
                self.assertIn(revision, section)
                self.assertRegex(revision, r"^[0-9a-f]{40}$")


if __name__ == "__main__":
    unittest.main()

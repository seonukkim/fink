from __future__ import annotations

import importlib
import sys
import unittest
from pathlib import Path
from typing import Any


def _load_module(name: str) -> Any:
    src_root = Path(__file__).resolve().parents[2] / "src"
    src_text = src_root.as_posix()
    if src_text not in sys.path:
        sys.path.insert(0, src_text)
    return importlib.import_module(name)


GROUNDING = _load_module("fink.grounding")
RETRIEVAL = _load_module("fink.retrieval")


def _chunk(
    chunk_id: str,
    text: str,
    *,
    chunk_type: str = "evidence",
    authority_tier: str = "A1",
    risk_categories: tuple[str, ...] = ("F2",),
    score_eligible: bool = True,
    practice_reference: bool = False,
    source_id: str | None = None,
    metadata: dict[str, object] | None = None,
) -> Any:
    resolved_source = source_id or f"{authority_tier}-TEST"
    return RETRIEVAL.RetrievalChunk(
        chunk_id=chunk_id,
        chunk_type=chunk_type,
        text=text,
        title=chunk_id,
        source_id=resolved_source,
        source_ids=(resolved_source,),
        source_class=authority_tier,
        authority_tier=authority_tier,
        verification_status="UNVERIFIED",
        risk_categories=risk_categories,
        hierarchy=(f"tier:{authority_tier}", f"source:{resolved_source}", f"chunk:{chunk_id}"),
        score_eligible=score_eligible,
        practice_reference=practice_reference,
        public_export=False,
        generated_translation=practice_reference,
        metadata=metadata or {},
    )


def _record(
    record_id: str,
    *,
    record_type: str = "evidence",
    authority_tier: str = "A1",
    risk_categories: tuple[str, ...] = ("F2",),
    score_eligible: bool = True,
    practice_reference: bool = False,
) -> Any:
    return GROUNDING.AuthorityRetrievedRecord(
        rank=1,
        retrieval_score=1.0,
        record_id=record_id,
        record_type=record_type,
        title=record_id,
        text="synthetic grounding fixture",
        source_id=f"{authority_tier}-TEST",
        source_ids=(f"{authority_tier}-TEST",),
        authority_tier=authority_tier,
        verification_status="UNVERIFIED",
        risk_categories=risk_categories,
        score_eligible=score_eligible,
        practice_reference=practice_reference,
        matched_terms=("synthetic",),
    )


class AuthorityGroundingTests(unittest.TestCase):
    def test_authority_tag_present_returns_bc_explanation_and_a_grounding(self) -> None:
        index = RETRIEVAL.LocalBM25Index(
            (
                _chunk(
                    "KC-F2-DEDUCTIONS",
                    "deductions revenue base 공제 매출 기준 explanation",
                    chunk_type="knowledge_card",
                    authority_tier="B/C",
                    score_eligible=False,
                    practice_reference=True,
                    source_id="B-BOOK",
                ),
                _chunk(
                    "EV-A1-DEDUCTIONS",
                    "deductions revenue base 공제 매출 기준 official grounding",
                    authority_tier="A1",
                    score_eligible=True,
                    source_id="A1-2025-FORM",
                ),
                _chunk(
                    "EV-A2-DEDUCTIONS",
                    "deductions revenue base 공제 매출 기준 guidance",
                    authority_tier="A2",
                    score_eligible=True,
                    source_id="A2-GUIDE",
                ),
            )
        )

        bundle = GROUNDING.authority_gated_retrieval(
            index,
            "deductions revenue base 공제",
            explanation_k=1,
            grounding_k=2,
            risk_categories=("F2",),
        )

        self.assertTrue(GROUNDING.authority_tag_present(bundle))
        self.assertEqual(
            [record.record_id for record in bundle.explanation_records],
            ["KC-F2-DEDUCTIONS"],
        )
        self.assertEqual(
            {record.record_id for record in bundle.grounding_records},
            {"EV-A1-DEDUCTIONS", "EV-A2-DEDUCTIONS"},
        )
        for record in bundle.returned_records:
            payload = record.as_dict()
            self.assertTrue(payload["source_id"])
            self.assertTrue(payload["authority_tier"])
            self.assertEqual(payload["verification_status"], "UNVERIFIED")
        self.assertTrue(all(record.is_explanation for record in bundle.explanation_records))
        self.assertTrue(all(record.is_grounding for record in bundle.grounding_records))

    def test_conflict_preserved_test_keeps_2025_and_2018_with_precedence(self) -> None:
        conflict_metadata_2025 = {
            "conflict_group": "webtoon-form:deduction-basis",
            "source_year": 2025,
        }
        conflict_metadata_2018 = {
            "conflict_group": "webtoon-form:deduction-basis",
            "source_year": 2018,
        }
        index = RETRIEVAL.LocalBM25Index(
            (
                _chunk(
                    "KC-F2-DEDUCTIONS",
                    "deductions revenue base 공제 explanation",
                    chunk_type="knowledge_card",
                    authority_tier="B/C",
                    score_eligible=False,
                    practice_reference=True,
                    source_id="C-PRACTICE",
                ),
                _chunk(
                    "EV-A1-2025-WEBTOON",
                    "deductions revenue base 공제 webtoon standard form overlap",
                    source_id="A1-2025-WEBTOON-FORM",
                    metadata=conflict_metadata_2025,
                ),
                _chunk(
                    "EV-A1-2018-WEBTOON",
                    "deductions revenue base 공제 webtoon standard form overlap",
                    source_id="A1-2018-WEBTOON-FORM",
                    metadata=conflict_metadata_2018,
                ),
            )
        )

        bundle = GROUNDING.authority_gated_retrieval(
            index,
            "deductions revenue base 공제 webtoon",
            explanation_k=1,
            grounding_k=1,
        )

        self.assertTrue(GROUNDING.conflict_preserved_test(bundle))
        self.assertEqual(len(bundle.conflict_sets), 1)
        conflict = bundle.conflict_sets[0]
        self.assertEqual(
            set(conflict.precedence_order),
            {"EV-A1-2025-WEBTOON", "EV-A1-2018-WEBTOON"},
        )
        self.assertEqual(conflict.precedence_order[0], "EV-A1-2025-WEBTOON")
        self.assertEqual(conflict.preferred_record_id, "EV-A1-2025-WEBTOON")
        self.assertIn("2025 > 2018", conflict.as_dict()["precedence_rule"])
        by_id = {record.record_id: record for record in bundle.grounding_records}
        self.assertEqual(by_id["EV-A1-2025-WEBTOON"].precedence_rank, 1)
        self.assertEqual(by_id["EV-A1-2018-WEBTOON"].precedence_rank, 2)

    def test_authority_tag_present_rejects_bc_only_grounding(self) -> None:
        bundle = GROUNDING.AuthorityRetrievalBundle(
            query="deductions",
            explanation_records=(
                GROUNDING.AuthorityRetrievedRecord(
                    rank=1,
                    retrieval_score=1.0,
                    record_id="KC-ONLY",
                    record_type="knowledge_card",
                    title="card",
                    text="deductions",
                    source_id="B-BOOK",
                    source_ids=("B-BOOK",),
                    authority_tier="B",
                    verification_status="UNVERIFIED",
                    risk_categories=("F2",),
                    score_eligible=False,
                    practice_reference=True,
                    matched_terms=("deductions",),
                ),
            ),
            grounding_records=(),
        )

        with self.assertRaisesRegex(
            GROUNDING.AuthorityGroundingError,
            "A0-A2 grounding record",
        ):
            GROUNDING.authority_tag_present(bundle)

    def test_eligibility_gate_test_marks_bc_only_as_zero_practice_reference(self) -> None:
        eligibility = GROUNDING.evaluate_signal_eligibility(
            "SIG-F2-BC-ONLY",
            (
                _record(
                    "KC-B-DEDUCTIONS",
                    record_type="knowledge_card",
                    authority_tier="B",
                    score_eligible=False,
                    practice_reference=True,
                ),
                _record(
                    "KC-C-DEDUCTIONS",
                    record_type="knowledge_card",
                    authority_tier="C",
                    score_eligible=False,
                    practice_reference=True,
                ),
            ),
            risk_categories=("F2",),
            raw_contribution=35.0,
        )

        self.assertFalse(eligibility.score_eligible)
        self.assertTrue(eligibility.practice_reference)
        self.assertEqual(eligibility.scoring_evidence_ids, ())
        self.assertEqual(
            eligibility.practice_reference_ids,
            ("KC-B-DEDUCTIONS", "KC-C-DEDUCTIONS"),
        )
        self.assertEqual(eligibility.raw_contribution, 35.0)
        self.assertEqual(eligibility.score_contribution, 0.0)
        payload = eligibility.as_dict()
        self.assertFalse(payload["score_eligible"])
        self.assertTrue(payload["practice_reference"])
        self.assertEqual(payload["score_contribution"], 0.0)

    def test_eligibility_gate_test_marks_a0_a2_evidence_as_score_eligible(self) -> None:
        for tier in ("A0", "A1", "A2"):
            with self.subTest(tier=tier):
                eligibility = GROUNDING.evaluate_signal_eligibility(
                    f"SIG-F2-{tier}",
                    (
                        _record(
                            f"EV-{tier}-DEDUCTIONS",
                            authority_tier=tier,
                        ),
                    ),
                    risk_categories=("F2_REVENUE_AND_DEDUCTIONS",),
                    raw_contribution=22.5,
                )

                self.assertTrue(eligibility.score_eligible)
                self.assertFalse(eligibility.practice_reference)
                self.assertEqual(
                    eligibility.scoring_evidence_ids,
                    (f"EV-{tier}-DEDUCTIONS",),
                )
                self.assertEqual(eligibility.score_contribution, 22.5)

    def test_eligibility_accepts_bare_category_text(self) -> None:
        eligibility = GROUNDING.evaluate_signal_eligibility(
            "SIG-F2-BARE-CATEGORY",
            (_record("EV-A1-DEDUCTIONS"),),
            risk_categories="F2",
            raw_contribution=7.0,
        )

        self.assertEqual(eligibility.risk_categories, ("F2",))
        self.assertTrue(eligibility.score_eligible)
        with self.assertRaisesRegex(
            GROUNDING.AuthorityGroundingError,
            "B/C-only zero case",
        ):
            GROUNDING.eligibility_gate_test(eligibility)

    def test_eligibility_gate_test_keeps_method_and_course_sources_non_scoring(
        self,
    ) -> None:
        eligibility = GROUNDING.evaluate_signal_eligibility(
            "SIG-F2-METHOD-ONLY",
            (
                _record(
                    "M1-DFL-DECK",
                    authority_tier="M1",
                    score_eligible=False,
                ),
                _record(
                    "R0-TERM-PROJECT",
                    authority_tier="R0",
                    score_eligible=False,
                ),
                _record(
                    "D0-DRAFT",
                    authority_tier="D0",
                    score_eligible=False,
                ),
            ),
            risk_categories=("F2",),
            raw_contribution=99.0,
        )

        self.assertFalse(eligibility.score_eligible)
        self.assertFalse(eligibility.practice_reference)
        self.assertEqual(eligibility.scoring_evidence_ids, ())
        self.assertEqual(
            eligibility.ignored_reference_ids,
            ("M1-DFL-DECK", "R0-TERM-PROJECT", "D0-DRAFT"),
        )
        self.assertEqual(eligibility.score_contribution, 0.0)

    def test_eligibility_gate_test_keeps_x_categories_non_scoring(self) -> None:
        eligibility = GROUNDING.evaluate_signal_eligibility(
            "SIG-X1-A1-CONTEXT",
            (
                _record(
                    "EV-A1-X1-CONTEXT",
                    authority_tier="A1",
                    risk_categories=("X1",),
                ),
            ),
            risk_categories=("X1_EVIDENCE_AND_CURRENCY_GOVERNANCE",),
            raw_contribution=40.0,
        )

        self.assertFalse(eligibility.score_eligible)
        self.assertFalse(eligibility.practice_reference)
        self.assertEqual(eligibility.scoring_evidence_ids, ("EV-A1-X1-CONTEXT",))
        self.assertEqual(eligibility.score_contribution, 0.0)

    def test_eligibility_gate_test_accepts_mixed_fixture_for_ac_auth_2(self) -> None:
        bc_only = GROUNDING.evaluate_signal_eligibility(
            "SIG-F2-BC-ONLY",
            (
                _record(
                    "KC-B-DEDUCTIONS",
                    record_type="knowledge_card",
                    authority_tier="B/C",
                    score_eligible=False,
                    practice_reference=True,
                ),
            ),
            risk_categories=("F2",),
            raw_contribution=10.0,
        )
        a_grounded = GROUNDING.evaluate_signal_eligibility(
            "SIG-F2-A1-GROUNDED",
            (_record("EV-A1-DEDUCTIONS"),),
            risk_categories=("F2",),
            raw_contribution=10.0,
        )

        self.assertTrue(GROUNDING.eligibility_gate_test((bc_only, a_grounded)))

    def test_eligibility_gate_test_rejects_missing_bc_only_case(self) -> None:
        a_grounded = GROUNDING.evaluate_signal_eligibility(
            "SIG-F2-A1-GROUNDED",
            (_record("EV-A1-DEDUCTIONS"),),
            risk_categories=("F2",),
            raw_contribution=10.0,
        )

        with self.assertRaisesRegex(
            GROUNDING.AuthorityGroundingError,
            "B/C-only zero case",
        ):
            GROUNDING.eligibility_gate_test((a_grounded,))


if __name__ == "__main__":
    unittest.main()

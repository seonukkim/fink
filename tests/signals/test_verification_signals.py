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


RETRIEVAL = _load_module("fink.retrieval")
SCHEMAS = _load_module("fink.schemas")
SIGNALS = _load_module("fink.signals")


def _clause(clause_id: str, text: str) -> Any:
    return SCHEMAS.Clause(
        clause_id=clause_id,
        clause_index=0,
        text_ko=text,
        source_span_ids=(f"span-{clause_id}",),
        seg_confidence=0.95,
    )


def _chunk(
    chunk_id: str,
    text: str,
    *,
    canonical_id: str = "",
    risk_categories: tuple[str, ...] = ("X1_EVIDENCE_AND_CURRENCY_GOVERNANCE",),
) -> Any:
    return RETRIEVAL.RetrievalChunk(
        chunk_id=chunk_id,
        chunk_type="glossary_term",
        text=text,
        title=text,
        source_id="B-KLL-GLOSSARY",
        source_ids=("B-KLL-GLOSSARY",),
        source_class="B",
        authority_tier="B",
        verification_status="UNVERIFIED",
        risk_categories=risk_categories,
        canonical_id=canonical_id,
        hierarchy=("tier:B", "source:B-KLL-GLOSSARY", f"chunk:{chunk_id}"),
        score_eligible=False,
        practice_reference=True,
        public_export=False,
        generated_translation=True,
    )


def _support_index() -> Any:
    return RETRIEVAL.LocalBM25Index(
        (
            _chunk(
                "GL-CONTRACT_PARTY",
                "CONTRACT_PARTY 계약 당사자 계약주체 party to contract",
                canonical_id="CONTRACT_PARTY",
            ),
            _chunk(
                "GL-COUNTERPARTY_RISK",
                "COUNTERPARTY_RISK 상대방 위험 정확한 법인 주소 보증",
                canonical_id="COUNTERPARTY_RISK",
                risk_categories=("X2_DISPUTE_RESOLUTION_AND_CASH_RECOVERY",),
            ),
            _chunk(
                "GL-PERSONAL_DATA",
                "PERSONAL_DATA 개인정보 계약서 이름 서명 계좌 주소 account payment",
                canonical_id="PERSONAL_DATA",
                risk_categories=("F9_E_CONTRACT_PRIVACY_AND_EVIDENCE",),
            ),
        )
    )


class VerificationSignalTests(unittest.TestCase):
    def test_counterparty_and_payment_route_patterns_fire_with_local_corpus_support(self) -> None:
        clauses = (
            _clause(
                "counterparty",
                "상대방의 사업자등록번호는 추후 제공하고 브랜드명으로 계약을 진행한다.",
            ),
            _clause(
                "payment",
                "입금 계좌는 별도 개인 명의 계좌로 안내하며 정산서에는 추후 표시한다.",
            ),
        )

        detected = SIGNALS.detect_verification_signals(
            clauses,
            support_index=_support_index(),
        )
        by_id = {signal.signal_id: signal for signal in detected}

        self.assertEqual(set(by_id), {"VFY-COUNTERPARTY-IDENTITY", "VFY-PAYMENT-ROUTE"})
        for signal in detected:
            self.assertEqual(signal.score_contribution, 0)
            self.assertTrue(signal.separate_from_review_priority_score)
            self.assertEqual(signal.support_state, "local_corpus_supported")
            self.assertTrue(signal.support_record_ids)
            self.assertTrue(set(signal.support_authority_tiers) <= {"B", "C", "B/C"})
            self.assertIn("확인", signal.label_ko)
            self.assertNotIn("판정", signal.instruction_ko)

    def test_no_local_corpus_support_means_no_verification_signal(self) -> None:
        unrelated_index = RETRIEVAL.LocalBM25Index(
            (
                _chunk(
                    "GL-UNRELATED",
                    "REVISION 수정 revision",
                    canonical_id="REVISION",
                    risk_categories=("F8_SCOPE_CREEP_AND_PRODUCTION_COST",),
                ),
            )
        )
        clause = _clause(
            "unsupported",
            "입금 계좌는 별도 개인 명의 계좌로 안내하며 정산서에는 추후 표시한다.",
        )

        self.assertEqual(
            SIGNALS.detect_verification_signals((clause,), support_index=unrelated_index),
            (),
        )

    def test_verification_payload_is_verdict_free_and_non_scoring(self) -> None:
        clause = _clause(
            "payment",
            "입금 계좌는 별도 개인 명의 계좌로 안내하며 정산서에는 추후 표시한다.",
        )
        detected = SIGNALS.detect_verification_signals(
            (clause,),
            support_index=_support_index(),
        )
        payload = SIGNALS.verification_payload(detected)
        encoded = __import__("json").dumps(payload, ensure_ascii=False)
        sensitive_root = chr(0xC0AC) + chr(0xAE30)
        forbidden = (
            sensitive_root + chr(0xC785) + chr(0xB2C8) + chr(0xB2E4),
            sensitive_root + " " + chr(0xD655) + chr(0xB960),
            sensitive_root + " " + chr(0xACC4) + chr(0xC57D),
            sensitive_root + " " + chr(0xD328) + chr(0xD134) + chr(0xC740),
        )

        self.assertEqual(payload["score_contribution"], 0)
        self.assertTrue(payload["separate_from_review_priority_score"])
        self.assertIn("상대방·지급 경로 확인 신호", encoded)
        for phrase in forbidden:
            self.assertNotIn(phrase, encoded)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import importlib
import json
import sys
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


ANALYZE = _load_module("fink.web.analyze")
RETRIEVAL = _load_module("fink.retrieval")
SCHEMAS = _load_module("fink.schemas")
WEB = _load_module("fink.web")

VERIFY_TEXT = (
    "제1조 상대방의 사업자등록번호는 추후 제공하고 브랜드명으로 계약을 진행한다.\n"
    "제2조 입금 계좌는 별도 개인 명의 계좌로 안내하며 정산서에는 추후 표시한다."
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


class VerificationPathwayTests(unittest.TestCase):
    def test_verification_payload_is_separate_from_findings_score_and_money(self) -> None:
        with patch.object(RETRIEVAL, "load_or_build_retrieval_index", return_value=_support_index()):
            result = ANALYZE.run_local_analysis(
                pasted_text=VERIFY_TEXT,
                ui_locale=SCHEMAS.UILocale.KO,
            )

        self.assertEqual(result.review_priority_score, 0)
        self.assertEqual(len(result.verification_signals), 2)
        self.assertTrue(all(signal.score_contribution == 0 for signal in result.verification_signals))

        payload = ANALYZE.analysis_result_to_payload(result, SCHEMAS.UILocale.KO)
        verification = payload["verification"]
        self.assertEqual(verification["section_title"]["ko"], "상대방·지급 경로 확인 신호")
        self.assertEqual(verification["score_contribution"], 0)
        self.assertTrue(verification["separate_from_review_priority_score"])
        self.assertEqual(verification["signal_count"], 2)
        self.assertNotIn("verification", payload["dimensions"])
        self.assertFalse(
            any(
                str(finding["finding_id"]).startswith("VFY-")
                for finding in payload["findings"]
            )
        )
        self.assertEqual(payload["dimensions"]["review_priority"]["score"], 0)
        self.assertEqual(
            payload["dimensions"]["monetary"]["quantification_status"]["state"],
            "not_quantified",
        )
        self.assertEqual(
            payload["audit_detail"]["verification"]["score_contribution"],
            0,
        )

        encoded = json.dumps(payload, ensure_ascii=False)
        self.assertIn("회사명", encoded)
        self.assertIn("사업자등록번호", encoded)
        self.assertIn("공식 연락처", encoded)
        self.assertIn("지급 계좌", encoded)
        self.assertNotIn("loss estimate", encoded.lower())

    def test_verification_section_renders_after_scenario_before_ranked_findings(self) -> None:
        with patch.object(RETRIEVAL, "load_or_build_retrieval_index", return_value=_support_index()):
            result = ANALYZE.run_local_analysis(
                pasted_text=VERIFY_TEXT,
                ui_locale=SCHEMAS.UILocale.KO,
            )
        view_model = WEB.build_creator_review_view_model(result, SCHEMAS.UILocale.KO)
        markup = WEB.render_report_html(view_model)

        self.assertIn('data-verification-section="true"', markup)
        self.assertIn('data-score-contribution="0"', markup)
        self.assertLess(
            markup.index('data-primary-scenario-inputs="true"'),
            markup.index('data-verification-section="true"'),
        )
        self.assertLess(
            markup.index('data-verification-section="true"'),
            markup.index('data-ranked-findings="true"'),
        )
        self.assertIn("상대방·지급 경로 확인 신호", markup)
        self.assertNotIn(" / 100", markup.split('data-audit-detail="true"', 1)[0])


if __name__ == "__main__":
    unittest.main()

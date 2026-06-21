from __future__ import annotations

import importlib
import sys
import unittest
from decimal import Decimal
from pathlib import Path
from typing import Any


def _load_module(name: str) -> Any:
    src_root = Path(__file__).resolve().parents[2] / "src"
    src_text = src_root.as_posix()
    if src_text not in sys.path:
        sys.path.insert(0, src_text)
    return importlib.import_module(name)


SCHEMAS = _load_module("fink.schemas")
WEB = _load_module("fink.web")


def _category_scores(**overrides: float) -> dict[Any, float]:
    scores = {category: 0.0 for category in SCHEMAS.FINANCIAL_RISK_CATEGORIES}
    for key, value in overrides.items():
        scores[getattr(SCHEMAS.RiskCategory, key)] = value
    return scores


def _synthetic_report() -> Any:
    eligible_signal = SCHEMAS.RiskSignal(
        signal_id="RS-F2-OFFICIAL",
        clause_id="clause-f2",
        risk_category=SCHEMAS.RiskCategory.F2,
        detector=SCHEMAS.DetectorType.RULE,
        fired=True,
        score_eligible=True,
        practice_reference=False,
        signal_confidence=0.88,
        is_missing_protection=False,
        grounding_evidence_ids=("EV-A1-F2",),
        severity_raw=0.70,
    )
    practice_signal = SCHEMAS.RiskSignal(
        signal_id="RS-F2-PRACTICE",
        clause_id="clause-f2",
        risk_category=SCHEMAS.RiskCategory.F2,
        detector=SCHEMAS.DetectorType.RULE,
        fired=True,
        score_eligible=False,
        practice_reference=True,
        signal_confidence=0.74,
        is_missing_protection=True,
    )
    clause = SCHEMAS.ClauseAssessment(
        clause_id="clause-f2",
        signals=(eligible_signal, practice_signal),
        category_scores=_category_scores(F2=42.0),
        clause_priority=42,
        explanation_card_ids=("BC-F2-1",),
        questions=("Which costs can be deducted before revenue share is calculated?",),
        evidence_ids=("EV-A1-F2", "EV-A2-F2"),
        monetary_links=(SCHEMAS.FimModule.FIM_1,),
    )
    exposure = SCHEMAS.MonetaryExposureEstimate(
        module=SCHEMAS.FimModule.FIM_1,
        exposure_type=SCHEMAS.ExposureType.NOMINAL_LEAKAGE,
        is_user_input_required=False,
        assumptions=("synthetic assumption: creator-entered low/base/high sales",),
        low=Decimal("100000"),
        base=Decimal("300000"),
        high=Decimal("600000"),
        uncertainty_flags=("open deduction wording widens the range",),
        nominal_amount=Decimal("900000"),
    )
    assessment = SCHEMAS.DocumentAssessment(
        document_id="00000000-0000-4000-8000-000000000001",
        review_priority_score=37,
        category_scores=_category_scores(F2=42.0),
        clause_assessments=(clause,),
        monetary_exposures=(exposure,),
        time_exposure=SCHEMAS.TimeExposure(
            measured_analysis_runtime_seconds=0.4,
            estimated_human_review_minutes=12.5,
            pathway_label=SCHEMAS.PathwayLabel.NEGOTIATION_REQUIRED,
            payment_due_days=45,
            payment_delay_days=15,
            contract_duration_months=24,
            termination_notice_days=30,
        ),
        confidence=SCHEMAS.ConfidenceBreakdown(
            ocr_confidence=0.91,
            evidence_confidence=0.62,
            data_completeness=0.70,
            overall_confidence=0.73,
            drivers=("UNVERIFIED official evidence", "synthetic assumption present"),
        ),
        scoring_config_version="synthetic-web-test-v1",
    )
    return SCHEMAS.AnalysisReport(
        report_id="report-web-synthetic",
        request_id="00000000-0000-4000-8000-000000000002",
        assessment=assessment,
        disclaimers=(
            "FInk reports Contractual Financial Review Priority only and is not legal advice.",
            "It is not a fraud, illegality, validity, unfairness, or guaranteed-loss verdict.",
        ),
        generated_text_flag=False,
        contains_raw_image=False,
        export_format=SCHEMAS.ExportFormat.HTML,
    )


def _official_records() -> tuple[Any, ...]:
    return (
        SCHEMAS.EvidenceRecord(
            evidence_id="EV-A1-F2",
            source_id="A1-2025-STANDARD-FORM",
            authority_tier=SCHEMAS.AuthorityTier.A1,
            risk_categories=(SCHEMAS.RiskCategory.F2,),
            verification_status=SCHEMAS.VerificationStatus.UNVERIFIED,
            score_eligible=True,
            public_export=True,
            article_ref="settlement clause",
            excerpt_ko="공제 항목 명확히 표시",
        ),
        SCHEMAS.EvidenceRecord(
            evidence_id="EV-A2-F2",
            source_id="A2-2023-FAIR-GUIDE",
            authority_tier=SCHEMAS.AuthorityTier.A2,
            risk_categories=(SCHEMAS.RiskCategory.F2,),
            verification_status=SCHEMAS.VerificationStatus.UNVERIFIED,
            score_eligible=True,
            public_export=True,
            page_ref="p.12",
            excerpt_ko="정산 근거 자료 제공",
        ),
    )


class ReportUITests(unittest.TestCase):
    def test_four_dimension_present_test_keeps_report_dimensions_separate(self) -> None:
        report = _synthetic_report()
        markup = WEB.render_report_html(report, evidence_records=_official_records())

        self.assertEqual(
            WEB.report_dimension_ids(),
            (
                "review-priority-score",
                "monetary-exposure-range",
                "time-exposure",
                "evidence-ocr-confidence",
            ),
        )
        self.assertEqual(markup.count('data-report-dimension="'), 4)
        for dimension_id in WEB.report_dimension_ids():
            self.assertIn(f'data-report-dimension="{dimension_id}"', markup)

        self.assertIsInstance(report.assessment.review_priority_score, int)
        self.assertIsInstance(report.assessment.monetary_exposures, tuple)
        self.assertIsInstance(report.assessment.time_exposure, SCHEMAS.TimeExposure)
        self.assertIsInstance(report.assessment.confidence, SCHEMAS.ConfidenceBreakdown)
        self.assertIn('data-grand-total="absent"', markup)
        self.assertNotIn("overall risk score", markup.lower())
        self.assertNotIn("fraud probability", markup.lower())
        self.assertNotIn("guaranteed loss", markup.lower())

    def test_report_ui_tests_cards_evidence_questions_and_x_context(self) -> None:
        report = _synthetic_report()
        practice_reference = WEB.PracticeReference(
            reference_id="BC-F2-1",
            risk_category=SCHEMAS.RiskCategory.F2,
            clause_id="clause-f2",
            explanation_ko="공제 범위가 열려 있으면 실제 정산액 확인이 어려울 수 있습니다.",
            explanation_en_alias="Open-ended deductions can make payout review harder.",
            questions=("Can every deduction category be listed before signing?",),
        )
        highlight = WEB.HighlightedEvidence(
            clause_id="clause-f2",
            page_index=0,
            source_span_id="span-f2-1",
            text_before="매출액에서 ",
            trigger_text="공제 비용",
            text_after="을 제한 뒤 정산한다.",
        )
        cross_cutting = (
            SCHEMAS.RiskSignal(
                signal_id="RS-X1-CONTEXT",
                clause_id="clause-x1",
                risk_category=SCHEMAS.RiskCategory.X1,
                detector=SCHEMAS.DetectorType.RULE,
                fired=True,
                score_eligible=False,
                practice_reference=True,
                signal_confidence=0.60,
                is_missing_protection=False,
            ),
        )

        markup = WEB.render_report_html(
            report,
            evidence_records=_official_records(),
            practice_references=(practice_reference,),
            highlighted_evidence=(highlight,),
            cross_cutting_signals=cross_cutting,
        )

        self.assertEqual(WEB.active_financial_category_codes(report), ("F2",))
        self.assertIn('data-risk-category-card="F2"', markup)
        self.assertNotIn('data-risk-category-card="X1"', markup)
        self.assertIn('data-eligible-signal-count="1"', markup)
        self.assertIn('data-practice-reference-count="1"', markup)

        self.assertIn('data-highlighted-evidence="true"', markup)
        self.assertIn('data-source-span-id="span-f2-1"', markup)
        self.assertIn('<mark data-triggering-span="true">공제 비용</mark>', markup)
        self.assertIn('href="#page-1"', markup)

        self.assertIn('data-official-source-comparison="true"', markup)
        self.assertIn('data-conflicting-sources="side-by-side"', markup)
        self.assertIn('data-source-id="A1-2025-STANDARD-FORM"', markup)
        self.assertIn('data-source-id="A2-2023-FAIR-GUIDE"', markup)
        self.assertIn('data-authority-tier="A1"', markup)
        self.assertIn('data-authority-tier="A2"', markup)
        self.assertIn('data-verification-status="UNVERIFIED"', markup)
        self.assertIn("공제 항목 명확히 표시", markup)
        self.assertIn("정산 근거 자료 제공", markup)

        self.assertIn('data-practice-reference-badge="true"', markup)
        self.assertIn("practice reference / non-scoring", markup)
        self.assertIn('data-score-driver="false"', markup)
        self.assertIn("Open-ended deductions can make payout review harder.", markup)

        self.assertIn('data-questions-before-signing="true"', markup)
        self.assertIn('data-question-non-scoring="true"', markup)
        self.assertIn('data-clause-id="clause-f2"', markup)
        self.assertIn("Which costs can be deducted before revenue share is calculated?", markup)
        self.assertIn("Can every deduction category be listed before signing?", markup)

        self.assertIn('data-non-scoring-section="X1-X5"', markup)
        for category in ("X1", "X2", "X3", "X4", "X5"):
            self.assertIn(f'data-risk-category="{category}"', markup)
        self.assertIn('data-risk-category="X1" data-score-driver="false"', markup)
        self.assertIn('data-active="true"', markup)


if __name__ == "__main__":
    unittest.main()

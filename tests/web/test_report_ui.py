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
    def test_copy_keys_are_bilingual_and_required(self) -> None:
        copy = WEB.creator_review_copy_payload()
        self.assertGreaterEqual(
            set(copy),
            set(WEB.creator_review_required_copy_keys()),
        )
        for key in WEB.creator_review_required_copy_keys():
            self.assertTrue(copy[key]["ko"].strip(), key)
            self.assertTrue(copy[key]["en"].strip(), key)
            self.assertTrue(copy[key]["en_generated"], key)

    def test_four_dimension_present_test_keeps_report_dimensions_separate(self) -> None:
        report = _synthetic_report()
        view_model = WEB.build_creator_review_view_model_from_report(
            report,
            evidence_records=_official_records(),
            highlighted_evidence=(
                WEB.HighlightedEvidence(
                    clause_id="clause-f2",
                    page_index=0,
                    source_span_id="span-f2-1",
                    text_before="매출액에서 ",
                    trigger_text="공제 비용",
                    text_after="을 제한 뒤 정산한다.",
                ),
            ),
        )
        markup = WEB.render_report_html(view_model)

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

        self.assertLess(markup.index('data-check-first="true"'), markup.index('data-dimension-count="4"'))
        self.assertLess(markup.index('data-exact-excerpt="true"'), markup.index(" / 100"))
        self.assertGreater(markup.index(" / 100"), markup.index('data-audit-detail="true"'))
        self.assertIn("규칙 기반 검토 집중도 지수", markup)
        self.assertIn("위험 확률, 손실액, 안전 판정이 아닙니다.", markup)
        self.assertIn("물어볼 말 복사", markup)
        self.assertIn("원문에서 보기", markup)
        self.assertIn("통화 확인 필요", markup)
        self.assertIn('data-collapsed-badge-count="3"', markup)
        self.assertIn('<details id=', markup)
        first_finding = markup.split('data-finding-rank="1"', 1)[1].split("</details>", 1)[0]
        self.assertIn("open", first_finding)
        section_order = [
            'data-finding-section="section.why_check"',
            'data-finding-section="section.wording"',
            'data-finding-section="section.impact"',
            'data-finding-section="section.question"',
            'data-finding-section="section.evidence"',
            'data-finding-section="section.detail"',
        ]
        positions = [first_finding.index(section) for section in section_order]
        self.assertEqual(positions, sorted(positions))

        self.assertEqual(view_model.view_model, "CreatorReviewViewModel")
        self.assertIn("reading_status", view_model.statuses)
        self.assertIn("evidence_status", view_model.statuses)
        self.assertIn("scenario_status", view_model.statuses)
        self.assertIn("quantification_status", view_model.statuses)
        self.assertIn('data-grand-total="absent"', markup)
        self.assertIn('data-primary-scenario-inputs="true"', markup)
        self.assertIn('data-max-primary-fields="6"', markup)
        self.assertIn('data-value-origin="missing"', markup)
        self.assertIn('data-selection-origin="model_suggestion"', markup)
        self.assertIn("모델 제안 — 확인 필요", markup)
        self.assertIn("시나리오 다시 계산", markup)
        self.assertIn("계약 24개월", markup)
        self.assertNotIn("검토 시간", markup)
        self.assertNotIn("measured_runtime_seconds", markup)
        self.assertNotIn("Overall confidence", markup)
        self.assertNotIn("Decision Brief", markup)
        self.assertNotIn("브리프", markup)
        self.assertNotIn("local-first", markup)
        self.assertNotIn("우선도", markup)
        self.assertNotIn("overall risk score", markup.lower())
        self.assertNotIn("fraud probability", markup.lower())
        self.assertNotIn("guaranteed loss", markup.lower())

    def test_html_markdown_and_json_exports_share_view_model_semantics(self) -> None:
        report = _synthetic_report()
        highlight = WEB.HighlightedEvidence(
            clause_id="clause-f2",
            page_index=0,
            source_span_id="span-f2-1",
            text_before="매출액에서 ",
            trigger_text="공제 비용",
            text_after="을 제한 뒤 정산한다.",
        )
        view_model = WEB.build_creator_review_view_model_from_report(
            report,
            evidence_records=_official_records(),
            highlighted_evidence=(highlight,),
        )
        html_markup = WEB.render_report_html(view_model)
        json_payload = WEB.export_creator_review_json(view_model)
        markdown = WEB.export_creator_review_markdown(view_model)
        decoded = __import__("json").loads(json_payload)

        self.assertEqual(decoded["view_model"], "CreatorReviewViewModel")
        self.assertEqual(
            decoded["findings"][0]["finding_id"],
            view_model.findings[0]["finding_id"],
        )
        self.assertIn(view_model.findings[0]["finding_id"], html_markup)
        self.assertIn(view_model.findings[0]["finding_id"], markdown)
        self.assertIn("공제 비용", html_markup)
        self.assertIn("공제 비용", markdown)

        primary_html = html_markup.split('data-audit-detail="true"', 1)[0]
        for forbidden in ("FIM-1", "F2", "overall_confidence", "runtime_s", " / 100"):
            self.assertNotIn(forbidden, primary_html)
            self.assertNotIn(forbidden, markdown)
        self.assertIn("FIM-1", html_markup)
        self.assertIn("overall_confidence", html_markup)
        self.assertIn("FIM-1", decoded["audit_detail"]["monetary_exposures"][0]["fim_module"])

    def test_project_page_synthetic_example_uses_same_view_model(self) -> None:
        view_model = WEB.build_project_page_synthetic_view_model()
        payload = view_model.to_payload()
        self.assertEqual(payload["view_model"], "CreatorReviewViewModel")
        self.assertEqual(payload["findings"][0]["rank"], 1)
        self.assertIn("audit_detail", payload)
        markup = WEB.render_report_html(view_model)
        self.assertIn("입력 필요", markup)
        self.assertIn("상한 미확정", markup)
        self.assertIn("통화 확인 필요", markup)
        self.assertNotIn("FIM-1", WEB.export_creator_review_markdown(view_model))


if __name__ == "__main__":
    unittest.main()

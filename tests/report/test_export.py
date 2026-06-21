from __future__ import annotations

import importlib
import json
import socket
import sys
import tempfile
import unittest
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from unittest.mock import patch


def _load_module(name: str) -> Any:
    src_root = Path(__file__).resolve().parents[2] / "src"
    src_text = src_root.as_posix()
    if src_text not in sys.path:
        sys.path.insert(0, src_text)
    return importlib.import_module(name)


SCHEMAS = _load_module("fink.schemas")
REPORT = _load_module("fink.report")
WEB = _load_module("fink.web")


def _category_scores(**overrides: float) -> dict[Any, float]:
    scores = {category: 0.0 for category in SCHEMAS.FINANCIAL_RISK_CATEGORIES}
    for key, value in overrides.items():
        scores[getattr(SCHEMAS.RiskCategory, key)] = value
    return scores


def _synthetic_report(*, contains_raw_image: bool = False) -> Any:
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
        scoring_config_version="synthetic-export-test-v1",
    )
    return SCHEMAS.AnalysisReport(
        report_id="report-export-synthetic",
        request_id="00000000-0000-4000-8000-000000000002",
        assessment=assessment,
        disclaimers=(
            "FInk reports Contractual Financial Review Priority only and is not legal advice.",
        ),
        generated_text_flag=False,
        contains_raw_image=contains_raw_image,
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
    )


def _practice_reference() -> Any:
    return WEB.PracticeReference(
        reference_id="BC-F2-1",
        risk_category=SCHEMAS.RiskCategory.F2,
        clause_id="clause-f2",
        explanation_ko="공제 범위가 열려 있으면 실제 정산액 확인이 어려울 수 있습니다.",
        explanation_en_alias="Open-ended deductions can make payout review harder.",
        questions=("Can every deduction category be listed before signing?",),
    )


def _highlight() -> Any:
    return WEB.HighlightedEvidence(
        clause_id="clause-f2",
        page_index=0,
        source_span_id="span-f2-1",
        text_before="매출액에서 ",
        trigger_text="공제 비용",
        text_after="을 제한 뒤 정산한다.",
    )


class ReportExportTests(unittest.TestCase):
    def test_export_local_test_writes_html_md_json_without_network(self) -> None:
        def fail_network(*args: object, **kwargs: object) -> None:
            raise AssertionError("report export must not use network clients")

        exported_at = datetime(2026, 6, 21, 12, 0, tzinfo=UTC)
        with tempfile.TemporaryDirectory() as tmpdir:
            with (
                patch.object(socket.socket, "connect", fail_network),
                patch.object(socket, "create_connection", fail_network),
            ):
                exports = REPORT.export_report_bundle(
                    _synthetic_report(),
                    tmpdir,
                    evidence_records=_official_records(),
                    practice_references=(_practice_reference(),),
                    highlighted_evidence=(_highlight(),),
                    exported_at=exported_at,
                )

            self.assertEqual({item.format.value for item in exports}, {"html", "md", "json"})
            self.assertTrue(all(item.local_only for item in exports))
            self.assertTrue(all(item.outbound_network_clients == 0 for item in exports))
            self.assertTrue(all(not item.contains_raw_image for item in exports))
            for item in exports:
                self.assertTrue(item.path.exists())
                self.assertGreater(item.bytes_written, 0)

            bodies = {item.format.value: item.path.read_text(encoding="utf-8") for item in exports}
            for body in bodies.values():
                self.assertIn("Contractual Financial Review Priority", body)
                self.assertIn("not legal advice", body)
                self.assertIn("guaranteed-loss verdict", body)
                self.assertIn("review-priority-score", body)
                self.assertIn("monetary-exposure-range", body)
                self.assertIn("time-exposure", body)
                self.assertIn("evidence-ocr-confidence", body)
                self.assertIn("A1-2025-STANDARD-FORM", body)
                self.assertIn("UNVERIFIED", body)
                self.assertIn("synthetic assumption: creator-entered low/base/high sales", body)
                self.assertIn(
                    "Which costs can be deducted before revenue share is calculated?",
                    body,
                )
                self.assertIn("Can every deduction category be listed before signing?", body)

            payload = json.loads(bodies["json"])
            self.assertEqual(payload["export_metadata"]["format"], "json")
            self.assertTrue(payload["export_metadata"]["local_only"])
            self.assertEqual(payload["export_metadata"]["outbound_network_clients"], 0)
            self.assertFalse(payload["export_metadata"]["contains_raw_image"])
            self.assertEqual(payload["export_metadata"]["raw_image_policy"], "excluded_by_default")
            self.assertFalse(payload["report"]["contains_raw_image"])

    def test_export_no_raw_image_test_excludes_raw_image_bytes_by_default(self) -> None:
        report = _synthetic_report(contains_raw_image=True)
        body = REPORT.render_report_export(
            report,
            SCHEMAS.ExportFormat.JSON,
            evidence_records=_official_records(),
            exported_at=datetime(2026, 6, 21, 12, 0, tzinfo=UTC),
        )
        payload = json.loads(body)

        self.assertFalse(payload["export_metadata"]["contains_raw_image"])
        self.assertFalse(payload["report"]["contains_raw_image"])
        self.assertNotIn('"contains_raw_image": true', body)
        self.assertNotIn("raw_image_bytes", body)
        self.assertNotIn("page_raster_bytes", body)
        self.assertNotIn("source_pdf_bytes", body)

        with self.assertRaises(REPORT.ReportExportError):
            REPORT.render_report_export(report, SCHEMAS.ExportFormat.JSON, include_raw_images=True)


if __name__ == "__main__":
    unittest.main()

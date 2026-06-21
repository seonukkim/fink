from __future__ import annotations

import importlib
import json
import sys
import unittest
from dataclasses import fields
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import uuid4


def _schemas() -> Any:
    src_root = Path(__file__).resolve().parents[2] / "src"
    src_text = src_root.as_posix()
    if src_text not in sys.path:
        sys.path.insert(0, src_text)
    return importlib.import_module("fink.schemas")


SCHEMAS: Any = _schemas()


def _category_scores(value: float = 0.0) -> dict[Any, float]:
    return {category: value for category in SCHEMAS.FINANCIAL_RISK_CATEGORIES}


def _span() -> Any:
    return SCHEMAS.OCRSpan(
        span_id="span-1",
        text="raw contract clause",
        bbox={"x": 1, "y": 2, "w": 100, "h": 20},
        confidence=0.97,
        lang=SCHEMAS.Lang.KO,
    )


def _page() -> Any:
    return SCHEMAS.OCRPage(
        page_id="page-1",
        page_index=0,
        rotation_deg=0,
        width_px=800,
        height_px=1200,
        spans=(_span(),),
        page_ocr_confidence=0.95,
        text_source=SCHEMAS.TextSource.OCR,
        is_user_corrected=False,
    )


def _document(document_id: str) -> Any:
    return SCHEMAS.UploadedDocument(
        document_id=document_id,
        filename_hash="filenamehash",
        mime_type=SCHEMAS.MimeType.TEXT,
        magic_byte_verified=False,
        is_encrypted=False,
        validation_status=SCHEMAS.ValidationStatus.ACCEPTED,
        page_count=1,
        temp_path="/tmp/fink-ephemeral/private-upload",
        bytes_sha256="a" * 64,
        delete_after=datetime.now() + timedelta(minutes=30),
        pages=(_page(),),
    )


def _risk_signal() -> Any:
    return SCHEMAS.RiskSignal(
        signal_id="RS-F2-open-deductions",
        clause_id="clause-1",
        risk_category=SCHEMAS.RiskCategory.F2,
        detector=SCHEMAS.DetectorType.RULE,
        fired=True,
        score_eligible=True,
        practice_reference=False,
        signal_confidence=0.88,
        is_missing_protection=False,
        grounding_evidence_ids=("EV-A1-1",),
        severity_raw=0.6,
    )


def _clause_assessment() -> Any:
    return SCHEMAS.ClauseAssessment(
        clause_id="clause-1",
        signals=(_risk_signal(),),
        category_scores=_category_scores(5.0),
        clause_priority=5,
        explanation_card_ids=("CARD-1",),
        questions=("question",),
        evidence_ids=("EV-A1-1",),
        monetary_links=(SCHEMAS.FimModule.FIM_1,),
    )


def _time_exposure() -> Any:
    return SCHEMAS.TimeExposure(
        measured_analysis_runtime_seconds=1.2,
        estimated_human_review_minutes=12.0,
        pathway_label=SCHEMAS.PathwayLabel.NEGOTIATION_REQUIRED,
        payment_due_days=30,
        payment_delay_days=15,
        contract_duration_months=12,
        renewal_duration_months=12,
        exclusivity_duration_months=6,
        termination_notice_days=30,
        estimated_months_to_recoup=4.5,
    )


def _confidence() -> Any:
    return SCHEMAS.ConfidenceBreakdown(
        ocr_confidence=0.95,
        evidence_confidence=0.7,
        data_completeness=0.8,
        overall_confidence=0.78,
        drivers=("synthetic driver",),
    )


def _monetary_exposure() -> Any:
    return SCHEMAS.MonetaryExposureEstimate(
        module=SCHEMAS.FimModule.FIM_1,
        exposure_type=SCHEMAS.ExposureType.NOMINAL_LEAKAGE,
        is_user_input_required=False,
        assumptions=("synthetic assumption",),
        low=Decimal("100"),
        base=Decimal("200"),
        high=Decimal("300"),
        uncertainty_flags=("thin_grounding",),
        nominal_amount=Decimal("500"),
    )


def _assessment(document_id: str) -> Any:
    return SCHEMAS.DocumentAssessment(
        document_id=document_id,
        review_priority_score=40,
        category_scores=_category_scores(4.0),
        clause_assessments=(_clause_assessment(),),
        monetary_exposures=(_monetary_exposure(),),
        time_exposure=_time_exposure(),
        confidence=_confidence(),
        scoring_config_version="test-config-v1",
        missing_protections=("missing audit right",),
    )


def _report(request_id: str, document_id: str) -> Any:
    return SCHEMAS.AnalysisReport(
        report_id="report-1",
        request_id=request_id,
        assessment=_assessment(document_id),
        disclaimers=(
            "FInk reports review priority only and is not legal advice.",
        ),
        generated_text_flag=False,
        contains_raw_image=False,
        exported_at=datetime.now(),
        export_format=SCHEMAS.ExportFormat.JSON,
    )


def _all_schema_instances() -> list[Any]:
    request_id = str(uuid4())
    document_id = str(uuid4())
    scenario_inputs = SCHEMAS.FinancialScenarioInputs(
        annual_discount_rate=0.05,
        inputs_are_synthetic=True,
        sales_low=Decimal("100"),
        sales_base=Decimal("200"),
        sales_high=Decimal("300"),
        creator_hourly_value=Decimal("50000"),
        hours_per_unit=2.5,
        unpaid_revision_units=3,
        alternative_monthly_revenue=Decimal("1000000"),
        scenario_probabilities={"base": 0.5},
        secondary_rights=({"type": "MERCH", "value": Decimal("1000"), "prob": 0.2},),
        penalty_probability=0.1,
    )
    return [
        SCHEMAS.AnalysisRequest(
            request_id=request_id,
            created_at=datetime.now(),
            ui_locale=SCHEMAS.UILocale.KO,
            input_mode=SCHEMAS.InputMode.IMAGE,
            runtime_profile=SCHEMAS.RuntimeProfile.DESKTOP_FULL,
            documents=(_document(document_id),),
            consent_local_only=True,
            scenario_inputs=scenario_inputs,
        ),
        _document(document_id),
        _page(),
        _span(),
        SCHEMAS.Clause(
            clause_id="clause-1",
            clause_index=0,
            text_ko="raw contract clause",
            source_span_ids=("span-1",),
            seg_confidence=0.9,
            heading_ko="heading",
            text_en_gloss="generated gloss",
            risk_categories=(SCHEMAS.RiskCategory.F2,),
            canonical_ids=("REVENUE_SHARE",),
        ),
        SCHEMAS.ExtractedFinancialTerms(
            term_id="term-1",
            clause_id="clause-1",
            feature_id="GROSS_SALES",
            value_raw="1000 KRW",
            unit=SCHEMAS.Unit.KRW,
            is_open_ended=False,
            extraction_confidence=0.91,
            source_span_ids=("span-1",),
            value_norm=Decimal("1000"),
        ),
        SCHEMAS.EvidenceRecord(
            evidence_id="EV-A1-1",
            source_id="A1-2025",
            authority_tier=SCHEMAS.AuthorityTier.A1,
            risk_categories=(SCHEMAS.RiskCategory.F2,),
            verification_status=SCHEMAS.VerificationStatus.UNVERIFIED,
            score_eligible=True,
            public_export=False,
            article_ref="article",
            page_ref="p1",
            excerpt_ko="short official excerpt",
            excerpt_en_gloss="generated gloss",
        ),
        _risk_signal(),
        _clause_assessment(),
        scenario_inputs,
        _monetary_exposure(),
        _time_exposure(),
        _confidence(),
        _assessment(document_id),
        _report(request_id, document_id),
        SCHEMAS.HumanCorrection(
            correction_id="corr-1",
            target_type=SCHEMAS.TargetType.OCR_SPAN,
            target_id="span-1",
            before="before",
            after="after",
            created_at=datetime.now(),
            counts_for_review_estimate=True,
        ),
        SCHEMAS.EvaluationExample(
            example_id="example-1",
            split=SCHEMAS.Split.DEV,
            dataset_ref="DR-7",
            input_kind=SCHEMAS.InputKind.CAMERA_OCR,
            is_synthetic=True,
            is_benign=False,
            gold={"label": "F2"},
            public_export=True,
        ),
        SCHEMAS.ExperimentResult(
            experiment_id="exp-1",
            config_hash="b" * 64,
            arm=SCHEMAS.ExperimentArm.RULE_ONLY,
            metric="EV-R@3",
            value=0.5,
            split=SCHEMAS.Split.DEV,
            result_status=SCHEMAS.ResultStatus.MEASURED,
            artifact_path="results/synthetic.json",
            reviewer="synthetic-reviewer",
        ),
    ]


class RuntimeSchemaTests(unittest.TestCase):
    def test_all_18_schema_classes_instantiate_and_serialize(self) -> None:
        instances = _all_schema_instances()
        self.assertEqual(len(SCHEMAS.SCHEMA_CLASSES), 18)
        self.assertEqual([type(item) for item in instances], list(SCHEMAS.SCHEMA_CLASSES))
        for instance in instances:
            self.assertIsInstance(instance.to_dict(), dict)
            self.assertIsInstance(instance.to_log_dict(), dict)

    def test_every_schema_field_has_full_metadata(self) -> None:
        for schema_cls in SCHEMAS.SCHEMA_CLASSES:
            with self.subTest(schema=schema_cls.__name__):
                for item in fields(schema_cls):
                    self.assertEqual(
                        set(item.metadata),
                        {
                            "nullable",
                            "unit",
                            "provenance",
                            "bilingual",
                            "privacy",
                            "generated_translation",
                        },
                    )
                    self.assertIsInstance(item.metadata["privacy"], SCHEMAS.PrivacyClass)
                    self.assertIsInstance(item.metadata["unit"], SCHEMAS.Unit)
                    self.assertIsInstance(item.metadata["provenance"], SCHEMAS.Provenance)
                    self.assertIsInstance(item.metadata["bilingual"], SCHEMAS.BilingualTag)

    def test_low_base_high_and_money_nonnegative_are_enforced(self) -> None:
        with self.assertRaises(SCHEMAS.SchemaValidationError):
            SCHEMAS.FinancialScenarioInputs(
                annual_discount_rate=0.05,
                inputs_are_synthetic=True,
                sales_low=Decimal("300"),
                sales_base=Decimal("200"),
                sales_high=Decimal("400"),
            )
        with self.assertRaises(SCHEMAS.SchemaValidationError):
            SCHEMAS.MonetaryExposureEstimate(
                module=SCHEMAS.FimModule.FIM_1,
                exposure_type=SCHEMAS.ExposureType.NOMINAL_LEAKAGE,
                is_user_input_required=False,
                assumptions=("synthetic",),
                low=Decimal("1"),
                base=Decimal("3"),
                high=Decimal("2"),
            )
        with self.assertRaises(SCHEMAS.SchemaValidationError):
            SCHEMAS.ExtractedFinancialTerms(
                term_id="term-1",
                clause_id="clause-1",
                feature_id="GROSS_SALES",
                value_raw="-100 KRW",
                unit=SCHEMAS.Unit.KRW,
                is_open_ended=False,
                extraction_confidence=0.9,
                source_span_ids=("span-1",),
                value_norm=Decimal("-100"),
            )
        with self.assertRaises(SCHEMAS.SchemaValidationError):
            SCHEMAS.FinancialScenarioInputs(
                annual_discount_rate=0.05,
                inputs_are_synthetic=True,
                creator_hourly_value=Decimal("-1"),
            )

    def test_risk_signal_eligibility_matches_grounding_ids(self) -> None:
        with self.assertRaises(SCHEMAS.SchemaValidationError):
            SCHEMAS.RiskSignal(
                signal_id="RS-F2-open-deductions",
                clause_id="clause-1",
                risk_category=SCHEMAS.RiskCategory.F2,
                detector=SCHEMAS.DetectorType.RULE,
                fired=True,
                score_eligible=True,
                practice_reference=False,
                signal_confidence=0.88,
                is_missing_protection=False,
                grounding_evidence_ids=(),
            )
        practice_reference = SCHEMAS.RiskSignal(
            signal_id="RS-F2-practice",
            clause_id="clause-1",
            risk_category=SCHEMAS.RiskCategory.F2,
            detector=SCHEMAS.DetectorType.RULE,
            fired=True,
            score_eligible=False,
            practice_reference=True,
            signal_confidence=0.5,
            is_missing_protection=False,
        )
        self.assertFalse(practice_reference.score_eligible)

    def test_log_serializer_excludes_p2_and_p3_fields(self) -> None:
        request_id = str(uuid4())
        document_id = str(uuid4())
        report = _report(request_id, document_id)
        log_dict = report.to_log_dict()
        self.assertEqual(
            log_dict,
            {
                "disclaimers": [
                    "FInk reports review priority only and is not legal advice.",
                ],
                "generated_text_flag": False,
                "export_format": "json",
            },
        )
        serialized = json.dumps(log_dict, ensure_ascii=True)
        self.assertNotIn(request_id, serialized)
        self.assertNotIn(document_id, serialized)
        self.assertNotIn("raw contract clause", serialized)
        self.assertNotIn("/tmp/fink-ephemeral/private-upload", serialized)

    def test_paste_request_requires_text_and_no_documents(self) -> None:
        SCHEMAS.AnalysisRequest(
            request_id=str(uuid4()),
            created_at=datetime.now(),
            ui_locale=SCHEMAS.UILocale.KO,
            input_mode=SCHEMAS.InputMode.PASTE,
            runtime_profile=SCHEMAS.RuntimeProfile.MOBILE_LITE,
            documents=(),
            consent_local_only=True,
            pasted_text="pasted contract text",
        )
        with self.assertRaises(SCHEMAS.SchemaValidationError):
            SCHEMAS.AnalysisRequest(
                request_id=str(uuid4()),
                created_at=datetime.now(),
                ui_locale=SCHEMAS.UILocale.KO,
                input_mode=SCHEMAS.InputMode.PASTE,
                runtime_profile=SCHEMAS.RuntimeProfile.MOBILE_LITE,
                documents=(_document(str(uuid4())),),
                consent_local_only=True,
                pasted_text="pasted contract text",
            )


if __name__ == "__main__":
    unittest.main()

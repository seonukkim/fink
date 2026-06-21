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


SCHEMAS = _load_module("fink.schemas")
TIME = _load_module("fink.time")


class TimeExposureTests(unittest.TestCase):
    def test_time_exposure_tests_gate_passes(self) -> None:
        report = TIME.time_exposure_tests()

        self.assertTrue(report.ok, report.as_dict())
        self.assertTrue(report.ac_time_1_typed_fields_categorical_pathway)
        self.assertTrue(report.ac_time_1_no_duration_number_fields)
        self.assertTrue(report.ac_time_2_human_review_minutes_from_config)
        self.assertTrue(report.ac_time_2_runtime_measured)
        self.assertTrue(report.ac_time_2_not_legal_advice_disclaimer)

    def test_human_review_minutes_use_config_coefficients(self) -> None:
        config = TIME.load_time_exposure_config()

        minutes = TIME.estimate_human_review_minutes(
            page_count=3,
            ocr_corrections_made=2,
            num_flagged_clauses=4,
            num_missing_financial_inputs=5,
            config=config,
        )

        coefficients = config.human_review_time_coefficients
        expected = (
            coefficients.base_min
            + coefficients.per_page_min * 3
            + coefficients.per_correction_min * 2
            + coefficients.per_flag_min * 4
            + coefficients.per_missing_min * 5
        )
        self.assertEqual(minutes, expected)

    def test_build_time_exposure_keeps_runtime_measured_and_pathway_categorical(self) -> None:
        config = TIME.load_time_exposure_config()
        result = TIME.build_time_exposure(
            page_count=2,
            ocr_corrections_made=1,
            num_flagged_clauses=2,
            num_missing_financial_inputs=1,
            measured_analysis_runtime_seconds=2.75,
            review_priority_score=config.pathway_thresholds.mid_review_priority_min,
            payment_due_days=30,
            payment_delay_days=15,
            contract_duration_months=12,
            renewal_duration_months=12,
            exclusivity_duration_months=6,
            termination_notice_days=30,
            estimated_months_to_recoup=4.5,
            config=config,
        )

        exposure = result.time_exposure
        self.assertIsInstance(exposure, SCHEMAS.TimeExposure)
        self.assertEqual(exposure.measured_analysis_runtime_seconds, 2.75)
        self.assertEqual(exposure.pathway_label, SCHEMAS.PathwayLabel.NEGOTIATION_REQUIRED)
        self.assertIsInstance(exposure.pathway_label, SCHEMAS.PathwayLabel)
        self.assertEqual(exposure.payment_due_days, 30)
        self.assertEqual(exposure.contract_duration_months, 12)
        self.assertTrue(any("not legal advice" in item.lower() for item in result.disclaimers))

    def test_pathway_label_first_match_rules(self) -> None:
        config = TIME.load_time_exposure_config()
        delay_threshold = config.pathway_thresholds.large_payment_delay_days_min

        dispute = TIME.select_pathway_label(
            TIME.TimeExposureInputs(
                page_count=1,
                ocr_corrections_made=0,
                num_flagged_clauses=0,
                num_missing_financial_inputs=0,
                measured_analysis_runtime_seconds=0.5,
                review_priority_score=0,
                payment_delay_days=delay_threshold,
            ),
            config=config,
        )
        professional = TIME.select_pathway_label(
            TIME.TimeExposureInputs(
                page_count=1,
                ocr_corrections_made=0,
                num_flagged_clauses=1,
                num_missing_financial_inputs=0,
                measured_analysis_runtime_seconds=0.5,
                review_priority_score=0,
                uncapped_or_ambiguous_liability_signal_present=True,
            ),
            config=config,
        )
        negotiation_first = TIME.select_pathway_label(
            TIME.TimeExposureInputs(
                page_count=1,
                ocr_corrections_made=0,
                num_flagged_clauses=1,
                num_missing_financial_inputs=0,
                measured_analysis_runtime_seconds=0.5,
                review_priority_score=config.pathway_thresholds.mid_review_priority_min,
                payment_delay_days=delay_threshold,
            ),
            config=config,
        )

        self.assertEqual(dispute, SCHEMAS.PathwayLabel.DISPUTE_PATHWAY_MAY_BE_REQUIRED)
        self.assertEqual(professional, SCHEMAS.PathwayLabel.PROFESSIONAL_REVIEW_REQUIRED)
        self.assertEqual(negotiation_first, SCHEMAS.PathwayLabel.NEGOTIATION_REQUIRED)

    def test_no_duration_number_test_scans_time_fields(self) -> None:
        report = TIME.no_duration_number_test()

        self.assertTrue(report.ok, report.as_dict())
        self.assertIn("TimeExposure.payment_due_days", report.inspected_fields)
        self.assertIn("TimeExposure.pathway_label", report.inspected_fields)
        self.assertEqual(report.forbidden_numeric_duration_fields, ())

    def test_runtime_timer_measures_elapsed_seconds(self) -> None:
        ticks = iter((10.0, 12.25))

        with TIME.AnalysisRuntimeTimer(clock=lambda: next(ticks)) as timer:
            pass

        self.assertEqual(timer.elapsed_seconds, 2.25)
        self.assertEqual(TIME.measure_runtime_seconds(5.0, 8.5), 3.5)

    def test_invalid_counts_are_rejected(self) -> None:
        with self.assertRaises(TIME.TimeExposureError):
            TIME.estimate_human_review_minutes(
                page_count=-1,
                ocr_corrections_made=0,
                num_flagged_clauses=0,
                num_missing_financial_inputs=0,
            )
        with self.assertRaises(TIME.TimeExposureError):
            TIME.build_time_exposure(
                page_count=1,
                measured_analysis_runtime_seconds=1.0,
                review_priority_score=101,
            )


if __name__ == "__main__":
    unittest.main()

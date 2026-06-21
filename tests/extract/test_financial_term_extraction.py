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


EXTRACT = _load_module("fink.extract")
SCHEMAS = _load_module("fink.schemas")


def _clause(clause_id: str, text: str) -> Any:
    return SCHEMAS.Clause(
        clause_id=clause_id,
        clause_index=0,
        text_ko=text,
        source_span_ids=(f"span-{clause_id}",),
        seg_confidence=0.90,
    )


def _span(
    span_id: str,
    text: str,
    *,
    corrected_text: str | None = None,
    confidence: float = 0.87,
) -> Any:
    return SCHEMAS.OCRSpan(
        span_id=span_id,
        text=text,
        corrected_text=corrected_text,
        bbox={"x": 10, "y": 10, "w": 500, "h": 24},
        confidence=confidence,
        lang=SCHEMAS.Lang.MIXED,
    )


def _page(spans: tuple[Any, ...]) -> Any:
    return SCHEMAS.OCRPage(
        page_id="page-1",
        page_index=0,
        rotation_deg=0,
        width_px=800,
        height_px=1200,
        spans=spans,
        page_ocr_confidence=0.88,
        text_source=SCHEMAS.TextSource.OCR,
        is_user_corrected=any(span.corrected_text is not None for span in spans),
    )


def _by_feature(terms: tuple[Any, ...], feature_id: str) -> list[Any]:
    return [term for term in terms if term.feature_id == feature_id]


class FinancialTermExtractionTests(unittest.TestCase):
    def test_extract_tests_money_pct_date_and_duration_are_normalized(self) -> None:
        clause = _clause(
            "clause-1",
            "총매출 1,200,000원, 수익배분율 30%, 지급일 2026년 7월 15일, 지급기일 45일",
        )

        terms = EXTRACT.extract_terms_from_clauses((clause,))

        gross_sales = _by_feature(terms, "GROSS_SALES")[0]
        revenue_share = _by_feature(terms, "REVENUE_SHARE_RATE")[0]
        payment_date = _by_feature(terms, "PAYMENT_DUE_DATE")[0]
        due_days = _by_feature(terms, "PAYMENT_DUE_DAYS")[0]

        self.assertEqual(gross_sales.unit, SCHEMAS.Unit.KRW)
        self.assertEqual(gross_sales.value_norm, Decimal("1200000"))
        self.assertEqual(revenue_share.unit, SCHEMAS.Unit.FRAC)
        self.assertEqual(revenue_share.value_norm, 0.3)
        self.assertEqual(payment_date.unit, SCHEMAS.Unit.NONE)
        self.assertEqual(payment_date.value_norm, 20260715)
        self.assertEqual(due_days.unit, SCHEMAS.Unit.DAYS)
        self.assertEqual(due_days.value_norm, 45.0)
        self.assertTrue(all(term.source_span_ids == ("span-clause-1",) for term in terms))

    def test_extract_tests_context_maps_money_and_durations_to_financial_features(self) -> None:
        clause = _clause(
            "clause-2",
            "위약금은 2,000,000원, 해지 통지기간은 30일, 독점기간은 1년으로 한다.",
        )

        terms = EXTRACT.extract_terms_from_clauses((clause,))

        self.assertEqual(_by_feature(terms, "PENALTY_AMOUNT")[0].value_norm, Decimal("2000000"))
        self.assertEqual(_by_feature(terms, "TERMINATION_NOTICE_DAYS")[0].value_norm, 30.0)
        self.assertEqual(_by_feature(terms, "EXCLUSIVITY_DURATION_MONTHS")[0].value_norm, 12.0)

    def test_extract_tests_open_ended_and_opaque_numerics_have_null_value_norm(self) -> None:
        terms = EXTRACT.extract_terms_from_text(
            "공제율 약 15% 및 기타 회사가 정하는 비용을 공제할 수 있다. Revenue share 10~20%.",
            clause_id="clause-open",
            source_span_ids=("span-open",),
        )

        deduction_rate = _by_feature(terms, "DEDUCTION_RATE")[0]
        range_rate = [term for term in terms if term.value_raw == "10~20%"][0]
        opaque = _by_feature(terms, "OPEN_ENDED_NUMERIC_TERMS")[0]

        self.assertIsNone(deduction_rate.value_norm)
        self.assertTrue(deduction_rate.is_open_ended)
        self.assertIsNone(range_rate.value_norm)
        self.assertTrue(range_rate.is_open_ended)
        self.assertIsNone(opaque.value_norm)
        self.assertTrue(opaque.is_open_ended)
        self.assertEqual(opaque.unit, SCHEMAS.Unit.NONE)

    def test_extract_tests_out_of_domain_percent_is_opaque_not_invalid_schema(self) -> None:
        terms = EXTRACT.extract_terms_from_text(
            "Revenue share 150%",
            clause_id="clause-over",
            source_span_ids=("span-over",),
        )

        term = _by_feature(terms, "REVENUE_SHARE_RATE")[0]

        self.assertIsNone(term.value_norm)
        self.assertTrue(term.is_open_ended)
        self.assertEqual(term.value_raw, "150%")

    def test_extract_tests_pages_use_corrected_text_and_span_provenance(self) -> None:
        page = _page(
            (
                _span(
                    "span-1",
                    "Revenue share 10% Payment due 30 days",
                    corrected_text="Revenue share 15% Payment due 45 days",
                ),
            )
        )

        terms = EXTRACT.extract_terms_from_pages((page,))

        revenue_share = _by_feature(terms, "REVENUE_SHARE_RATE")[0]
        due_days = _by_feature(terms, "PAYMENT_DUE_DAYS")[0]
        self.assertEqual(revenue_share.value_norm, 0.15)
        self.assertEqual(due_days.value_norm, 45.0)
        self.assertEqual(revenue_share.source_span_ids, ("span-1",))
        self.assertEqual(revenue_share.extraction_confidence, 0.87)

    def test_exact_match_harness_computes_ev_exact_families(self) -> None:
        predicted = EXTRACT.extract_terms_from_text(
            "Gross sales 1.5 million KRW, Revenue share 25%, "
            "Payment due March 5, 2026 and 30 days.",
            clause_id="clause-metrics",
            source_span_ids=("span-metrics",),
        )
        gold = (
            EXTRACT.ExpectedFinancialTerm("GROSS_SALES", Decimal("1500000"), SCHEMAS.Unit.KRW),
            EXTRACT.ExpectedFinancialTerm("REVENUE_SHARE_RATE", Decimal("0.25"), SCHEMAS.Unit.FRAC),
            EXTRACT.ExpectedFinancialTerm("PAYMENT_DUE_DATE", 20260305, SCHEMAS.Unit.NONE),
            EXTRACT.ExpectedFinancialTerm("PAYMENT_DUE_DAYS", 30.0, SCHEMAS.Unit.DAYS),
        )

        report = EXTRACT.exact_match_harness(gold, predicted)

        self.assertEqual(report.ev_exact_money, 1.0)
        self.assertEqual(report.ev_exact_pct, 1.0)
        self.assertEqual(report.ev_exact_date, 1.0)
        self.assertEqual(report.ev_exact_dur, 1.0)
        self.assertEqual(report.metrics["EV-EXACT-MONEY"].matched_count, 1)
        self.assertEqual(
            set(report.as_dict()),
            {"EV-EXACT-MONEY", "EV-EXACT-PCT", "EV-EXACT-DATE", "EV-EXACT-DUR"},
        )

    def test_exact_match_harness_penalizes_false_positive_terms(self) -> None:
        gold = (
            EXTRACT.ExpectedFinancialTerm("REVENUE_SHARE_RATE", Decimal("0.25"), SCHEMAS.Unit.FRAC),
        )
        predicted = (
            EXTRACT.ExpectedFinancialTerm("REVENUE_SHARE_RATE", Decimal("0.25"), SCHEMAS.Unit.FRAC),
            EXTRACT.ExpectedFinancialTerm("DEDUCTION_RATE", Decimal("0.10"), SCHEMAS.Unit.FRAC),
        )

        report = EXTRACT.evaluate_exact_matches(gold, predicted)

        self.assertEqual(report.metrics["EV-EXACT-PCT"].matched_count, 1)
        self.assertEqual(report.metrics["EV-EXACT-PCT"].predicted_count, 2)
        self.assertEqual(report.ev_exact_pct, 0.5)


if __name__ == "__main__":
    unittest.main()

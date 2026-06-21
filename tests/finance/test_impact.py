from __future__ import annotations

import importlib
import sys
import unittest
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any


def _load_module(name: str) -> Any:
    src_root = Path(__file__).resolve().parents[2] / "src"
    src_text = src_root.as_posix()
    if src_text not in sys.path:
        sys.path.insert(0, src_text)
    return importlib.import_module(name)


FINANCE = _load_module("fink.finance")
SCHEMAS = _load_module("fink.schemas")


def _krw(value: Decimal) -> int:
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


class FinanceImpactTests(unittest.TestCase):
    def test_fim_1_t1_revenue_base_deduction_leakage(self) -> None:
        result = FINANCE.fim1_revenue_base_deduction_leakage(
            gross_sales=Decimal("10000000"),
            refunds=Decimal("500000"),
            explicitly_allowed_deductions=Decimal("1000000"),
            revenue_share_rate=Decimal("0.7"),
            fixed_fee=Decimal("0"),
            advance_recoupment=Decimal("0"),
            open_ended_deductions=FINANCE.DecimalRange(
                low=Decimal("0"),
                base=Decimal("1000000"),
                high=Decimal("2000000"),
            ),
        )

        self.assertEqual(result.net_sales.high, Decimal("8500000"))
        self.assertEqual(result.creator_payout.high, Decimal("5950000.0"))
        self.assertEqual(result.creator_payout.base, Decimal("5250000.0"))
        self.assertEqual(result.creator_payout.low, Decimal("4550000.0"))
        self.assertEqual(result.leakage, Decimal("1400000.0"))
        self.assertEqual(result.nominal_leakage.low, Decimal("0.0"))
        self.assertEqual(result.nominal_leakage.base, Decimal("700000.0"))
        self.assertEqual(result.nominal_leakage.high, Decimal("1400000.0"))
        self.assertEqual(
            result.nominal_leakage.exposure_type,
            SCHEMAS.ExposureType.NOMINAL_LEAKAGE,
        )

    def test_fim_2_t1_payment_delay_pv_loss_keeps_nominal_separate(self) -> None:
        result = FINANCE.fim2_payment_delay_present_value_loss(
            delayed_amount=Decimal("10000000"),
            annual_discount_rate=Decimal("0.05"),
            delay_days=Decimal("180"),
        )

        self.assertEqual(result.nominal_amount, Decimal("10000000"))
        self.assertLess(abs(_krw(result.delay_pv_loss) - 237700), 3000)
        self.assertEqual(result.present_value_loss.nominal_amount, Decimal("10000000"))
        self.assertEqual(
            result.present_value_loss.exposure_type,
            SCHEMAS.ExposureType.PRESENT_VALUE_LOSS,
        )
        self.assertNotEqual(result.present_value_loss.base, result.nominal_amount)

    def test_fim_3_t1_mg_advance_recoupment_labels_sales_direction(self) -> None:
        result = FINANCE.fim3_mg_advance_recoupment(
            advance=Decimal("12000000"),
            cumulative_recouped=Decimal("0"),
            revenue_share_rate=Decimal("0.7"),
            monthly_net_sales=FINANCE.DecimalRange(
                low=Decimal("1000000"),
                base=Decimal("2000000"),
                high=Decimal("4000000"),
            ),
        )

        self.assertEqual(result.monthly_recoupment.low, Decimal("700000.0"))
        self.assertEqual(result.monthly_recoupment.base, Decimal("1400000.0"))
        self.assertEqual(result.monthly_recoupment.high, Decimal("2800000.0"))
        self.assertEqual(result.months_to_recoup, (18, 9, 5))
        self.assertEqual(result.deferral.base, Decimal("12000000"))
        self.assertEqual(result.deferral.exposure_type, SCHEMAS.ExposureType.DEFERRAL)
        self.assertIn("monthly sales", result.sales_label_note)

    def test_fim_7_t1_capped_liability_with_user_probability(self) -> None:
        result = FINANCE.fim7_penalty_liability_exposure(
            explicit_penalty_cap=Decimal("5000000"),
            penalty_probability=Decimal("0.1"),
            scenario_amount=Decimal("5000000"),
        )

        self.assertEqual(result.max_nominal_exposure, Decimal("5000000"))
        self.assertEqual(result.expected_penalty, Decimal("500000.0"))
        self.assertEqual(result.liability_exposure.base, Decimal("500000.0"))
        self.assertEqual(result.liability_exposure.nominal_amount, Decimal("5000000"))
        self.assertEqual(
            result.liability_exposure.exposure_type,
            SCHEMAS.ExposureType.LIABILITY_EXPOSURE,
        )

    def test_fim_7_t2_uncapped_without_probability_emits_no_number(self) -> None:
        result = FINANCE.fim7_penalty_liability_exposure(is_uncapped=True)

        self.assertIsNone(result.max_nominal_exposure)
        self.assertIsNone(result.expected_penalty)
        self.assertTrue(result.uncapped_signal)
        self.assertTrue(result.liability_exposure.is_user_input_required)
        self.assertIsNone(result.liability_exposure.low)
        self.assertIsNone(result.liability_exposure.base)
        self.assertIsNone(result.liability_exposure.high)
        self.assertIn("uncapped", result.liability_exposure.uncertainty_flags)

    def test_fim_core_unit_tests_gate_report_passes(self) -> None:
        report = FINANCE.fim_core_unit_tests()

        self.assertTrue(report.ok, report.as_dict())
        self.assertTrue(report.fim_1_t1)
        self.assertTrue(report.fim_2_t1)
        self.assertTrue(report.fim_3_t1)
        self.assertTrue(report.fim_7_t1)
        self.assertTrue(report.fim_7_t2)

    def test_sc_sep_t1_no_cross_exposure_type_summation(self) -> None:
        report = FINANCE.exposure_separation_test()

        self.assertTrue(report.ok, report.as_dict())
        self.assertEqual(
            set(report.exposure_types),
            {
                "deferral",
                "liability_exposure",
                "nominal_leakage",
                "present_value_loss",
            },
        )

        fim1 = FINANCE.fim1_revenue_base_deduction_leakage(
            Decimal("10000000"),
            Decimal("500000"),
            Decimal("1000000"),
            Decimal("0.7"),
            open_ended_deductions=FINANCE.DecimalRange(
                low=Decimal("0"),
                base=Decimal("1000000"),
                high=Decimal("2000000"),
            ),
        )
        fim2 = FINANCE.fim2_payment_delay_present_value_loss(
            Decimal("10000000"),
            Decimal("0.05"),
            Decimal("180"),
        )
        partitions = FINANCE.partition_exposures_by_type(
            (fim1.nominal_leakage, fim2.present_value_loss)
        )
        subtotals = FINANCE.exposure_type_subtotals(
            (fim1.nominal_leakage, fim2.present_value_loss)
        )

        self.assertEqual(
            set(partitions),
            {
                SCHEMAS.ExposureType.NOMINAL_LEAKAGE,
                SCHEMAS.ExposureType.PRESENT_VALUE_LOSS,
            },
        )
        self.assertEqual(set(subtotals), set(partitions))
        self.assertNotIn("grand_total", subtotals)


if __name__ == "__main__":
    unittest.main()

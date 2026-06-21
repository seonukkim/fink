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
SCORING = _load_module("fink.scoring")
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

    def test_fim_4_t1_unpaid_additional_work_cost(self) -> None:
        result = FINANCE.fim4_unpaid_additional_work_cost(
            unpaid_revision_units=Decimal("5"),
            hours_per_unit=Decimal("8"),
            creator_hourly_value=FINANCE.DecimalRange(
                low=Decimal("20000"),
                base=Decimal("30000"),
                high=Decimal("40000"),
            ),
        )

        self.assertFalse(result.is_blank)
        self.assertEqual(result.unpaid_work_cost.low, Decimal("800000"))
        self.assertEqual(result.unpaid_work_cost.base, Decimal("1200000"))
        self.assertEqual(result.unpaid_work_cost.high, Decimal("1600000"))
        self.assertEqual(result.unpaid_work_cost.module, SCHEMAS.FimModule.FIM_4)
        self.assertEqual(
            result.unpaid_work_cost.exposure_type,
            SCHEMAS.ExposureType.OPPORTUNITY_COST,
        )
        self.assertTrue(
            any("synthetic assumption" in item for item in result.unpaid_work_cost.assumptions)
        )

    def test_fim_5_t1_exclusivity_opportunity_cost(self) -> None:
        result = FINANCE.fim5_exclusivity_renewal_opportunity_cost(
            exclusivity_duration_months=Decimal("12"),
            alternative_monthly_revenue=Decimal("1000000"),
            scenario_probability=FINANCE.DecimalRange(
                low=Decimal("0.25"),
                base=Decimal("0.5"),
                high=Decimal("0.75"),
            ),
            annual_discount_rate=Decimal("0.05"),
        )

        self.assertFalse(result.is_blank)
        self.assertEqual(result.scenario_months, (12, 12, 12))
        self.assertLess(abs(_krw(result.opportunity_cost.low) - 2922500), 30000)
        self.assertLess(abs(_krw(result.opportunity_cost.base) - 5845000), 60000)
        self.assertLess(abs(_krw(result.opportunity_cost.high) - 8767500), 90000)
        self.assertEqual(result.opportunity_cost.module, SCHEMAS.FimModule.FIM_5)
        self.assertEqual(
            result.opportunity_cost.exposure_type,
            SCHEMAS.ExposureType.OPPORTUNITY_COST,
        )
        self.assertTrue(
            any("synthetic assumption" in item for item in result.opportunity_cost.assumptions)
        )

    def test_fim_6_t1_ip_secondary_rights_scenario_value(self) -> None:
        result = FINANCE.fim6_ip_secondary_rights_scenario_value(
            secondary_rights=(
                {"type": "overseas", "value": Decimal("5000000"), "prob": Decimal("0.4")},
                {"type": "merchandise", "value": Decimal("3000000"), "prob": Decimal("0.2")},
            )
        )

        self.assertFalse(result.is_blank)
        self.assertEqual(result.scenario_value.low, Decimal("2600000.0"))
        self.assertEqual(result.scenario_value.base, Decimal("2600000.0"))
        self.assertEqual(result.scenario_value.high, Decimal("2600000.0"))
        self.assertEqual(result.scenario_value.module, SCHEMAS.FimModule.FIM_6)
        self.assertEqual(
            result.scenario_value.exposure_type,
            SCHEMAS.ExposureType.OPPORTUNITY_COST,
        )
        self.assertFalse(result.auto_valued_from_contract_text)
        self.assertIn("overseas", result.right_types)
        self.assertTrue(
            any("no automatic IP valuation" in item for item in result.scenario_value.assumptions)
        )

    def test_fim_6_missing_valuation_inputs_stays_input_required(self) -> None:
        result = FINANCE.fim6_ip_secondary_rights_scenario_value(
            secondary_rights=({"type": "overseas"},)
        )

        self.assertTrue(result.is_blank)
        self.assertEqual(
            result.missing_inputs,
            ("secondary_rights[1].value", "secondary_rights[1].prob"),
        )
        self.assertIsNone(result.scenario_value.low)
        self.assertIsNone(result.scenario_value.base)
        self.assertIsNone(result.scenario_value.high)
        self.assertIn(
            "missing_user_input:secondary_rights[1].value",
            result.scenario_value.uncertainty_flags,
        )

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

    def test_fim_8_t1_evidence_opacity_widens_band_around_unchanged_base(self) -> None:
        config = SCORING.load_scoring_config()
        base_exposure = SCHEMAS.MonetaryExposureEstimate(
            module=SCHEMAS.FimModule.FIM_1,
            exposure_type=SCHEMAS.ExposureType.NOMINAL_LEAKAGE,
            is_user_input_required=False,
            assumptions=(),
            low=Decimal("4550000"),
            base=Decimal("5250000"),
            high=Decimal("5950000"),
        )

        result = FINANCE.fim8_evidence_opacity_uncertainty(
            base_exposure,
            opacity_flags=("missing_settlement_records", "no_audit_access"),
            opacity_weights=config.fim8_opacity_weights,
        )
        adjusted = result.adjusted_exposure

        self.assertEqual(result.band_widen_factor, Decimal("1.2"))
        self.assertEqual(adjusted.base, Decimal("5250000"))
        if (
            adjusted.low is None
            or adjusted.high is None
            or base_exposure.low is None
            or base_exposure.high is None
        ):
            self.fail("FIM-8 adjusted exposure should keep numeric low/high values")
        self.assertEqual(_krw(adjusted.low), 3791667)
        self.assertEqual(_krw(adjusted.high), 7140000)
        self.assertLess(adjusted.low, base_exposure.low)
        self.assertGreater(adjusted.high, base_exposure.high)
        self.assertEqual(adjusted.module, base_exposure.module)
        self.assertEqual(adjusted.exposure_type, base_exposure.exposure_type)
        self.assertIn("opacity:missing_settlement_records", adjusted.uncertainty_flags)
        self.assertIn("opacity:no_audit_access", adjusted.uncertainty_flags)

    def test_fim8_uncertainty_gate_report_passes(self) -> None:
        report = FINANCE.fim8_uncertainty_test()

        self.assertTrue(report.ok, report.as_dict())
        self.assertTrue(report.fim_8_t1_base_unchanged)
        self.assertTrue(report.fim_8_t1_high_up)
        self.assertTrue(report.fim_8_t1_low_down)
        self.assertTrue(report.fim_8_t1_score_unchanged)
        self.assertTrue(report.fim_8_t1_data_completeness_down)

    def test_fim8_opacity_flags_lower_confidence_not_score(self) -> None:
        config = SCORING.load_scoring_config()
        signal = SCHEMAS.RiskSignal(
            signal_id="RS-FIM8-CONF",
            clause_id="clause-fim8",
            risk_category=SCHEMAS.RiskCategory.F1,
            detector=SCHEMAS.DetectorType.RULE,
            fired=True,
            score_eligible=True,
            practice_reference=False,
            signal_confidence=1.0,
            is_missing_protection=False,
            grounding_evidence_ids=("EV-A1-FIM8-CONF",),
            severity_raw=0.7,
        )

        baseline = SCORING.aggregate_document_signals(
            (signal,),
            config=config,
            evidence_authority_tiers={"EV-A1-FIM8-CONF": "A1"},
        )
        opaque = SCORING.aggregate_document_signals(
            (signal,),
            config=config,
            evidence_authority_tiers={"EV-A1-FIM8-CONF": "A1"},
            opacity_flags=("missing_settlement_records", "no_audit_access"),
        )

        self.assertEqual(opaque.review_priority_score, baseline.review_priority_score)
        self.assertEqual(opaque.category_scores, baseline.category_scores)
        self.assertLess(
            opaque.confidence.data_completeness,
            baseline.confidence.data_completeness,
        )
        self.assertLess(
            opaque.confidence.overall_confidence,
            baseline.confidence.overall_confidence,
        )
        self.assertIn(
            "opacity_flags=missing_settlement_records,no_audit_access",
            opaque.confidence.drivers,
        )

    def test_fim_core_unit_tests_gate_report_passes(self) -> None:
        report = FINANCE.fim_core_unit_tests()

        self.assertTrue(report.ok, report.as_dict())
        self.assertTrue(report.fim_1_t1)
        self.assertTrue(report.fim_2_t1)
        self.assertTrue(report.fim_3_t1)
        self.assertTrue(report.fim_7_t1)
        self.assertTrue(report.fim_7_t2)

    def test_fim_scenario_unit_tests_gate_report_passes(self) -> None:
        report = FINANCE.fim_scenario_unit_tests()

        self.assertTrue(report.ok, report.as_dict())
        self.assertTrue(report.fim_4_t1)
        self.assertTrue(report.fim_5_t1)
        self.assertTrue(report.fim_6_t1)

    def test_blank_without_inputs_test_gate_report_passes(self) -> None:
        report = FINANCE.blank_without_inputs_test()

        self.assertTrue(report.ok, report.as_dict())
        self.assertTrue(report.fim_4_blank)
        self.assertTrue(report.fim_5_blank)
        self.assertTrue(report.fim_6_blank)
        self.assertTrue(report.fim_7_expected_path_blank)

    def test_fim_4_5_6_blank_without_required_user_inputs(self) -> None:
        fim4 = FINANCE.fim4_unpaid_additional_work_cost()
        fim5 = FINANCE.fim5_exclusivity_renewal_opportunity_cost(
            exclusivity_duration_months=Decimal("12")
        )
        fim6 = FINANCE.fim6_ip_secondary_rights_scenario_value()

        for exposure in (
            fim4.unpaid_work_cost,
            fim5.opportunity_cost,
            fim6.scenario_value,
        ):
            self.assertTrue(exposure.is_user_input_required)
            self.assertIsNone(exposure.low)
            self.assertIsNone(exposure.base)
            self.assertIsNone(exposure.high)
            self.assertTrue(exposure.uncertainty_flags)

    def test_sc_sep_t1_no_cross_exposure_type_summation(self) -> None:
        report = FINANCE.exposure_separation_test()

        self.assertTrue(report.ok, report.as_dict())
        self.assertEqual(
            set(report.exposure_types),
            {
                "deferral",
                "liability_exposure",
                "nominal_leakage",
                "opportunity_cost",
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

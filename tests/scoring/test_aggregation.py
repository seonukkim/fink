from __future__ import annotations

import importlib
import json
import math
import sys
import unittest
from dataclasses import replace
from pathlib import Path
from typing import Any


def _load_module(name: str) -> Any:
    src_root = Path(__file__).resolve().parents[2] / "src"
    src_text = src_root.as_posix()
    if src_text not in sys.path:
        sys.path.insert(0, src_text)
    return importlib.import_module(name)


SCHEMAS = _load_module("fink.schemas")
SCORING = _load_module("fink.scoring")
FINANCE = _load_module("fink.finance")


def _signal(
    signal_id: str,
    category: Any,
    *,
    clause_id: str = "clause-1",
    score_eligible: bool = True,
    practice_reference: bool = False,
    evidence_ids: tuple[str, ...] = ("EV-A1-1",),
    confidence: float = 0.9,
    severity: float = 0.8,
) -> Any:
    return SCHEMAS.RiskSignal(
        signal_id=signal_id,
        clause_id=clause_id,
        risk_category=category,
        detector=SCHEMAS.DetectorType.RULE,
        fired=True,
        score_eligible=score_eligible,
        practice_reference=practice_reference,
        signal_confidence=confidence,
        is_missing_protection=False,
        grounding_evidence_ids=evidence_ids if score_eligible else None,
        severity_raw=severity,
    )


class AggregationTests(unittest.TestCase):
    def test_aggregation_tests_gate_passes(self) -> None:
        report = SCORING.aggregation_tests()

        self.assertTrue(report.ok, report.as_dict())
        self.assertTrue(report.sc_agg_t1_bc_contributes_zero)
        self.assertTrue(report.sc_agg_t2_bounded_0_100)
        self.assertTrue(report.sc_agg_t3_low_confidence_lowers_d4_not_priority)

    def test_sc_agg_t1_bc_practice_reference_contributes_zero(self) -> None:
        config = SCORING.load_scoring_config()
        bc_only = _signal(
            "RS-SC-AGG-T1-BC-ONLY",
            SCHEMAS.RiskCategory.F2,
            score_eligible=False,
            practice_reference=True,
            evidence_ids=(),
            severity=1.0,
        )
        grounded = _signal(
            "RS-SC-AGG-T1-A1",
            SCHEMAS.RiskCategory.F2,
            evidence_ids=("EV-A1-F2",),
            confidence=1.0,
            severity=1.0,
        )

        bc_result = SCORING.aggregate_document_signals((bc_only,), config=config)
        grounded_result = SCORING.aggregate_document_signals(
            (grounded,),
            config=config,
            evidence_authority_tiers={"EV-A1-F2": "A1"},
        )
        mixed_result = SCORING.aggregate_document_signals(
            (bc_only, grounded),
            config=config,
            evidence_authority_tiers={"EV-A1-F2": "A1"},
        )

        self.assertEqual(bc_result.review_priority_score, 0)
        self.assertEqual(bc_result.category_scores[SCHEMAS.RiskCategory.F2], 0.0)
        self.assertEqual(bc_result.verified_support_count, 0)
        self.assertEqual(bc_result.practice_support_count, 1)
        self.assertEqual(grounded_result.verified_support_count, 1)
        self.assertEqual(grounded_result.practice_support_count, 0)
        self.assertEqual(mixed_result.verified_support_count, 1)
        self.assertEqual(mixed_result.practice_support_count, 1)
        self.assertEqual(mixed_result.review_priority_score, grounded_result.review_priority_score)
        self.assertEqual(
            mixed_result.category_scores[SCHEMAS.RiskCategory.F2],
            grounded_result.category_scores[SCHEMAS.RiskCategory.F2],
        )
        self.assertEqual(mixed_result.contributions[0].contribution, 0.0)
        self.assertTrue(mixed_result.contributions[0].practice_reference)
        self.assertEqual(mixed_result.as_dict()["verified_support_count"], 1)
        self.assertEqual(mixed_result.as_dict()["practice_support_count"], 1)

        checkpoint_result = SCORING.aggregate_document_signals(
            (grounded,),
            config=config,
            evidence_authority_tiers={"EV-A1-F2": "A1"},
            practice_checkpoint_categories=("F2",),
        )
        self.assertEqual(
            checkpoint_result.review_priority_score,
            grounded_result.review_priority_score,
        )
        self.assertEqual(checkpoint_result.verified_support_count, 1)
        self.assertEqual(checkpoint_result.practice_support_count, 1)

    def test_score_eligible_signal_requires_real_authority_tier_mapping(self) -> None:
        config = SCORING.load_scoring_config()
        signal = _signal(
            "RS-SC-AGG-NO-FAKE-TIER",
            SCHEMAS.RiskCategory.F5,
            evidence_ids=("EV-A1-REAL-ID-BUT-NO-TIER",),
            confidence=1.0,
            severity=1.0,
        )

        without_tier = SCORING.aggregate_document_signals((signal,), config=config)
        wrong_tier = SCORING.aggregate_document_signals(
            (signal,),
            config=config,
            evidence_authority_tiers={"EV-A1-REAL-ID-BUT-NO-TIER": "B"},
        )
        with_tier = SCORING.aggregate_document_signals(
            (signal,),
            config=config,
            evidence_authority_tiers={"EV-A1-REAL-ID-BUT-NO-TIER": "A1"},
        )

        self.assertEqual(without_tier.review_priority_score, 0)
        self.assertEqual(without_tier.contributions[0].contribution, 0.0)
        self.assertEqual(wrong_tier.review_priority_score, 0)
        self.assertEqual(wrong_tier.contributions[0].contribution, 0.0)
        self.assertGreater(with_tier.review_priority_score, 0)
        self.assertGreater(with_tier.contributions[0].contribution, 0.0)

    def test_sc_agg_t2_scores_are_bounded_with_saturation(self) -> None:
        config = SCORING.load_scoring_config()
        signals = tuple(
            _signal(
                f"RS-SC-AGG-T2-{idx}",
                SCHEMAS.RiskCategory.F7,
                evidence_ids=(f"EV-A0-{idx}",),
                confidence=1.0,
                severity=1.0,
            )
            for idx in range(500)
        )
        tiers = {f"EV-A0-{idx}": "A0" for idx in range(500)}

        result = SCORING.aggregate_document_signals(
            signals,
            config=config,
            evidence_authority_tiers=tiers,
        )

        self.assertGreater(result.category_scores[SCHEMAS.RiskCategory.F7], 99.0)
        self.assertLessEqual(result.category_scores[SCHEMAS.RiskCategory.F7], 100.0)
        self.assertGreaterEqual(result.review_priority_score, 0)
        self.assertLessEqual(result.review_priority_score, 100)
        for category in SCHEMAS.FINANCIAL_RISK_CATEGORIES:
            self.assertIn(category, result.category_scores)
            self.assertGreaterEqual(result.category_scores[category], 0.0)
            self.assertLessEqual(result.category_scores[category], 100.0)

    def test_sc_agg_t3_low_confidence_lowers_d4_not_floored_priority(self) -> None:
        config = SCORING.load_scoring_config()
        low_confidence_signal = _signal(
            "RS-SC-AGG-T3-LOW",
            SCHEMAS.RiskCategory.F3,
            evidence_ids=("EV-A1-LOW",),
            confidence=0.05,
            severity=1.0,
        )
        floor_confidence_signal = _signal(
            "RS-SC-AGG-T3-FLOOR",
            SCHEMAS.RiskCategory.F3,
            evidence_ids=("EV-A1-FLOOR",),
            confidence=config.conf_floor,
            severity=1.0,
        )

        low_result = SCORING.aggregate_document_signals(
            (low_confidence_signal,),
            config=config,
            evidence_authority_tiers={"EV-A1-LOW": "A1"},
        )
        floor_result = SCORING.aggregate_document_signals(
            (floor_confidence_signal,),
            config=config,
            evidence_authority_tiers={"EV-A1-FLOOR": "A1"},
        )

        self.assertEqual(low_result.review_priority_score, floor_result.review_priority_score)
        self.assertEqual(
            low_result.category_scores[SCHEMAS.RiskCategory.F3],
            floor_result.category_scores[SCHEMAS.RiskCategory.F3],
        )
        self.assertLess(
            low_result.confidence.overall_confidence,
            floor_result.confidence.overall_confidence,
        )
        self.assertIn(
            "low_signal_confidence_floored_for_priority_only",
            low_result.confidence.drivers,
        )

    def test_config_values_drive_saturation_and_document_weighting(self) -> None:
        config = SCORING.load_scoring_config()
        signal = _signal(
            "RS-SC-AGG-CONFIG",
            SCHEMAS.RiskCategory.F2,
            evidence_ids=("EV-A1-CONFIG",),
            confidence=1.0,
            severity=0.6,
        )
        baseline = SCORING.aggregate_document_signals(
            (signal,),
            config=config,
            evidence_authority_tiers={"EV-A1-CONFIG": "A1"},
        )
        faster_saturation = replace(
            config,
            k_by_category={
                **config.k_by_category,
                SCHEMAS.RiskCategory.F2: config.k_by_category[SCHEMAS.RiskCategory.F2] / 10,
            },
        )
        reweighted = replace(
            faster_saturation,
            w_by_category={
                **faster_saturation.w_by_category,
                SCHEMAS.RiskCategory.F2: 10.0,
            },
        )

        saturated = SCORING.aggregate_document_signals(
            (signal,),
            config=faster_saturation,
            evidence_authority_tiers={"EV-A1-CONFIG": "A1"},
        )
        weighted = SCORING.aggregate_document_signals(
            (signal,),
            config=reweighted,
            evidence_authority_tiers={"EV-A1-CONFIG": "A1"},
        )

        self.assertGreater(
            saturated.category_scores[SCHEMAS.RiskCategory.F2],
            baseline.category_scores[SCHEMAS.RiskCategory.F2],
        )
        self.assertGreater(weighted.review_priority_score, saturated.review_priority_score)
        self.assertEqual(baseline.scoring_config_version, config.scoring_config_version)

    def test_cross_cutting_category_never_contributes(self) -> None:
        config = SCORING.load_scoring_config()
        x_signal = _signal(
            "RS-SC-AGG-X1",
            SCHEMAS.RiskCategory.X1,
            evidence_ids=("EV-A1-X1",),
            confidence=1.0,
            severity=1.0,
        )

        result = SCORING.aggregate_document_signals(
            (x_signal,),
            config=config,
            evidence_authority_tiers={"EV-A1-X1": "A1"},
        )

        self.assertEqual(result.review_priority_score, 0)
        self.assertTrue(all(score == 0.0 for score in result.category_scores.values()))
        self.assertEqual(result.contributions[0].contribution, 0.0)

    def test_saturation_formula_matches_spec_for_one_signal(self) -> None:
        config = SCORING.load_scoring_config()
        signal = _signal(
            "RS-SC-AGG-FORMULA",
            SCHEMAS.RiskCategory.F5,
            evidence_ids=("EV-A2-F5",),
            confidence=0.8,
            severity=0.75,
        )

        result = SCORING.aggregate_document_signals(
            (signal,),
            config=config,
            evidence_authority_tiers={"EV-A2-F5": "A2"},
        )

        expected_contribution = (
            config.severity_weight[SCHEMAS.RiskCategory.F5]
            * 0.75
            * config.authority_factor["A2"]
            * 0.8
        )
        expected_score = 100.0 * (
            1.0
            - math.exp(
                -(expected_contribution / config.k_by_category[SCHEMAS.RiskCategory.F5])
            )
        )
        self.assertAlmostEqual(
            result.contributions[0].contribution,
            expected_contribution,
        )
        self.assertAlmostEqual(
            result.category_scores[SCHEMAS.RiskCategory.F5],
            expected_score,
        )

    def test_exposure_aware_ranking_uses_actual_fim_outputs_not_confidence_product(self) -> None:
        config = SCORING.load_scoring_config()
        low_conf_large_exposure = _signal(
            "RS-RANK-F5-LARGE",
            SCHEMAS.RiskCategory.F5,
            evidence_ids=("EV-A1-F5",),
            confidence=0.10,
            severity=0.20,
        )
        high_conf_small_exposure = _signal(
            "RS-RANK-F6-SMALL",
            SCHEMAS.RiskCategory.F6,
            evidence_ids=("EV-A1-F6",),
            confidence=1.0,
            severity=1.0,
        )
        scoring = SCORING.aggregate_document_signals(
            (high_conf_small_exposure, low_conf_large_exposure),
            config=config,
            evidence_authority_tiers={"EV-A1-F5": "A1", "EV-A1-F6": "A1"},
        )
        fim5 = FINANCE.fim5_exclusivity_renewal_opportunity_cost(
            exclusivity_duration_months=(1, 1, 1),
            alternative_monthly_revenue=("10000", "10000", "10000"),
            scenario_probability=("1", "1", "1"),
            annual_discount_rate=("0", "0", "0"),
        )
        fim6 = FINANCE.fim6_ip_secondary_rights_scenario_value(
            (
                {
                    "type": "translation",
                    "value": ("1000000", "1000000", "1000000"),
                    "prob": ("1", "1", "1"),
                },
            )
        )

        ranked = SCORING.rank_review_findings(
            (high_conf_small_exposure, low_conf_large_exposure),
            exposures=(fim5.opportunity_cost, fim6.scenario_value),
            contributions=scoring.contributions,
        )

        self.assertEqual(ranked[0].signal_id, "RS-RANK-F5-LARGE")
        self.assertEqual(ranked[0].ranking_policy, "exposure_aware")
        self.assertEqual(ranked[0].authority_gate, "enforce")
        self.assertEqual(ranked[0].priority_basis, "quantified_exposure")
        self.assertEqual(ranked[0].quantification_status, "quantified")
        self.assertEqual(ranked[0].exposure_type, SCHEMAS.ExposureType.OPPORTUNITY_COST)
        self.assertEqual(ranked[0].fim_module, SCHEMAS.FimModule.FIM_6)
        self.assertIn(
            "confidence_not_used_as_exposure_multiplier",
            ranked[0].policy_notes,
        )

    def test_exposure_aware_ranking_never_sums_incompatible_exposure_types(self) -> None:
        config = SCORING.load_scoring_config()
        nominal_signal = _signal(
            "RS-RANK-F2-NOMINAL",
            SCHEMAS.RiskCategory.F2,
            evidence_ids=("EV-A1-F2",),
        )
        timing_signal = _signal(
            "RS-RANK-F3-PV",
            SCHEMAS.RiskCategory.F3,
            evidence_ids=("EV-A1-F3",),
        )
        scoring = SCORING.aggregate_document_signals(
            (nominal_signal, timing_signal),
            config=config,
            evidence_authority_tiers={"EV-A1-F2": "A1", "EV-A1-F3": "A1"},
        )
        fim1 = FINANCE.fim1_revenue_base_deduction_leakage(
            gross_sales="1000000",
            refunds="0",
            explicitly_allowed_deductions="0",
            revenue_share_rate="0.5",
            open_ended_deductions=("10000", "10000", "10000"),
        )
        fim2 = FINANCE.fim2_payment_delay_present_value_loss(
            delayed_amount="1000000",
            annual_discount_rate=("0.05", "0.05", "0.05"),
            delay_days=(30, 30, 30),
        )

        ranked = SCORING.rank_review_findings(
            (nominal_signal, timing_signal),
            exposures=(fim1.nominal_leakage, fim2.present_value_loss),
            contributions=scoring.contributions,
        )
        payloads = [item.as_dict() for item in ranked]

        self.assertEqual(
            {item["exposure_type"] for item in payloads},
            {"nominal_leakage", "present_value_loss"},
        )
        self.assertNotIn("grand_total", json.dumps(payloads))
        self.assertTrue(
            all("no_cross_exposure_type_total" in item["policy_notes"] for item in payloads)
        )

    def test_uncapped_unbounded_finding_gets_override_without_fabricated_high(self) -> None:
        config = SCORING.load_scoring_config()
        signal = _signal(
            "RS-RANK-F7-UNCAPPED",
            SCHEMAS.RiskCategory.F7,
            evidence_ids=("EV-A1-F7",),
        )
        scoring = SCORING.aggregate_document_signals(
            (signal,),
            config=config,
            evidence_authority_tiers={"EV-A1-F7": "A1"},
        )
        fim7 = FINANCE.fim7_penalty_liability_exposure(is_uncapped=True)

        ranked = SCORING.rank_review_findings(
            (signal,),
            exposures=(fim7.liability_exposure,),
            contributions=scoring.contributions,
        )
        first = ranked[0]

        self.assertEqual(first.priority_basis, "uncapped_or_unbounded")
        self.assertEqual(first.quantification_status, "unbounded")
        self.assertEqual(first.deterministic_class, "unbounded_override")
        self.assertIsNone(first.exposure_high)
        self.assertIsNone(first.comparable_sort_value)
        self.assertIn("no_cross_exposure_type_total", first.policy_notes)

    def test_severity_baseline_and_authority_bypass_are_explicit_evaluation_options(self) -> None:
        candidate = _signal(
            "RS-RANK-F2-CANDIDATE",
            SCHEMAS.RiskCategory.F2,
            score_eligible=False,
            evidence_ids=(),
            confidence=1.0,
            severity=1.0,
        )
        grounded = _signal(
            "RS-RANK-F2-GROUNDED",
            SCHEMAS.RiskCategory.F2,
            evidence_ids=("EV-A1-F2",),
            confidence=0.5,
            severity=0.5,
        )

        baseline = SCORING.rank_review_findings(
            (grounded, candidate),
            ranking_policy=SCORING.RANKING_POLICY_SEVERITY_BASELINE,
            authority_gate=SCORING.AUTHORITY_GATE_BYPASS_FOR_ABLATION,
        )

        self.assertEqual(baseline[0].signal_id, "RS-RANK-F2-CANDIDATE")
        self.assertEqual(baseline[0].ranking_policy, "severity_baseline")
        self.assertEqual(baseline[0].authority_gate, "bypass_for_ablation")
        self.assertIn("evaluation_only_authority_gate_bypass", baseline[0].policy_notes)


if __name__ == "__main__":
    unittest.main()

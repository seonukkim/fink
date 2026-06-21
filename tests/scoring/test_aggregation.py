from __future__ import annotations

import importlib
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
        self.assertEqual(mixed_result.review_priority_score, grounded_result.review_priority_score)
        self.assertEqual(
            mixed_result.category_scores[SCHEMAS.RiskCategory.F2],
            grounded_result.category_scores[SCHEMAS.RiskCategory.F2],
        )
        self.assertEqual(mixed_result.contributions[0].contribution, 0.0)
        self.assertTrue(mixed_result.contributions[0].practice_reference)

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


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

try:
    import yaml  # type: ignore[import-untyped]
except Exception as exc:  # pragma: no cover - dependency is declared in pyproject
    raise RuntimeError("PyYAML is required for FInk scoring config") from exc

from fink.schemas import (
    ClauseAssessment,
    ConfidenceBreakdown,
    ExposureType,
    FINANCIAL_RISK_CATEGORIES,
    FimModule,
    MonetaryExposureEstimate,
    RiskCategory,
    RiskSignal,
)


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SCORING_CONFIG_PATH = REPO_ROOT / "config" / "scoring_config.yaml"

SCORING_AUTHORITY_TIERS = ("A0", "A1", "A2")
AUTHORITY_TIER_RANK = {"A0": 0, "A1": 1, "A2": 2}
ZERO_SCORE_TIERS = ("B", "C", "B/C", "D0", "M1", "M2", "M3", "R0")
RANKING_POLICY_EXPOSURE_AWARE = "exposure_aware"
RANKING_POLICY_SEVERITY_BASELINE = "severity_baseline"
RANKING_POLICIES = (RANKING_POLICY_EXPOSURE_AWARE, RANKING_POLICY_SEVERITY_BASELINE)
AUTHORITY_GATE_ENFORCE = "enforce"
AUTHORITY_GATE_BYPASS_FOR_ABLATION = "bypass_for_ablation"
AUTHORITY_GATES = (AUTHORITY_GATE_ENFORCE, AUTHORITY_GATE_BYPASS_FOR_ABLATION)

PRIORITY_BASIS_QUANTIFIED_EXPOSURE = "quantified_exposure"
PRIORITY_BASIS_PRESENT_VALUE_TIMING = "present_value_timing"
PRIORITY_BASIS_UNCAPPED_OR_UNBOUNDED = "uncapped_or_unbounded"
PRIORITY_BASIS_COUNTERPARTY_VERIFICATION = "counterparty_verification"
PRIORITY_BASIS_GROUNDED_QUALITATIVE_SIGNAL = "grounded_qualitative_signal"
PRIORITY_BASIS_UNVERIFIED_CANDIDATE = "unverified_candidate"

QUANTIFICATION_STATUS_QUANTIFIED = "quantified"
QUANTIFICATION_STATUS_PARTIALLY_BOUNDED = "partially_bounded"
QUANTIFICATION_STATUS_UNBOUNDED = "unbounded"
QUANTIFICATION_STATUS_INPUT_REQUIRED = "input_required"
QUANTIFICATION_STATUS_NOT_APPLICABLE = "not_applicable"

CATEGORY_CONFIG_IDS: Mapping[RiskCategory, str] = {
    RiskCategory.F1: "F1_SETTLEMENT_AND_AUDIT",
    RiskCategory.F2: "F2_REVENUE_AND_DEDUCTIONS",
    RiskCategory.F3: "F3_PAYMENT_AND_CASHFLOW",
    RiskCategory.F4: "F4_MG_AND_RECOUPMENT",
    RiskCategory.F5: "F5_IP_MONETIZATION",
    RiskCategory.F6: "F6_TERM_EXCLUSIVITY_AND_OPPORTUNITY_COST",
    RiskCategory.F7: "F7_TERMINATION_LIABILITY_AND_PENALTIES",
    RiskCategory.F8: "F8_SCOPE_CREEP_AND_PRODUCTION_COST",
    RiskCategory.F9: "F9_E_CONTRACT_PRIVACY_AND_EVIDENCE",
}
CONFIG_ID_TO_CATEGORY = {value: key for key, value in CATEGORY_CONFIG_IDS.items()}
SORTED_FINANCIAL_CATEGORIES = tuple(
    sorted(FINANCIAL_RISK_CATEGORIES, key=lambda category: category.value)
)
RISK_CATEGORY_FIM_MODULE: Mapping[RiskCategory, FimModule | None] = {
    RiskCategory.F1: FimModule.FIM_1,
    RiskCategory.F2: FimModule.FIM_1,
    RiskCategory.F3: FimModule.FIM_2,
    RiskCategory.F4: FimModule.FIM_3,
    RiskCategory.F5: FimModule.FIM_6,
    RiskCategory.F6: FimModule.FIM_5,
    RiskCategory.F7: FimModule.FIM_7,
    RiskCategory.F8: FimModule.FIM_4,
    RiskCategory.F9: FimModule.FIM_8,
}
RISK_CATEGORY_EXPOSURE_TYPE: Mapping[RiskCategory, ExposureType | None] = {
    RiskCategory.F1: ExposureType.NOMINAL_LEAKAGE,
    RiskCategory.F2: ExposureType.NOMINAL_LEAKAGE,
    RiskCategory.F3: ExposureType.PRESENT_VALUE_LOSS,
    RiskCategory.F4: ExposureType.DEFERRAL,
    RiskCategory.F5: ExposureType.OPPORTUNITY_COST,
    RiskCategory.F6: ExposureType.OPPORTUNITY_COST,
    RiskCategory.F7: ExposureType.LIABILITY_EXPOSURE,
    RiskCategory.F8: ExposureType.OPPORTUNITY_COST,
    RiskCategory.F9: None,
}
_EXPOSURE_TYPE_ORDER: Mapping[ExposureType, int] = {
    ExposureType.LIABILITY_EXPOSURE: 0,
    ExposureType.NOMINAL_LEAKAGE: 1,
    ExposureType.PRESENT_VALUE_LOSS: 2,
    ExposureType.OPPORTUNITY_COST: 3,
    ExposureType.DEFERRAL: 4,
}


class ScoringAggregationError(ValueError):
    """Raised when score aggregation input or config violates the scoring contract."""


@dataclass(frozen=True)
class ConfidenceWeights:
    """Config-driven weights for the separate D4 confidence dimension."""

    ocr_confidence: float
    evidence_confidence: float
    data_completeness: float


@dataclass(frozen=True)
class ScoringConfig:
    """Versioned, heuristic scoring config loaded from scoring_config.yaml."""

    config_path: Path
    scoring_config_version: str
    authority_factor: Mapping[str, float]
    zero_score_tiers: Mapping[str, float]
    severity_weight: Mapping[RiskCategory, float]
    conf_floor: float
    k_by_category: Mapping[RiskCategory, float]
    w_by_category: Mapping[RiskCategory, float]
    confidence_weights: ConfidenceWeights
    unverified_factor: float
    base_evidence_confidence: float
    fim8_opacity_weights: Mapping[str, float]
    missing_input_weights: Mapping[str, float]


@dataclass(frozen=True)
class SignalContribution:
    """One signal's effective contribution after authority and confidence gates."""

    signal_id: str
    clause_id: str
    risk_category: RiskCategory
    fired: bool
    score_eligible: bool
    practice_reference: bool
    authority_tier: str | None
    severity_raw: float
    severity_weight: float
    authority_factor: float
    confidence_used: float
    contribution: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "signal_id": self.signal_id,
            "clause_id": self.clause_id,
            "risk_category": self.risk_category.value,
            "fired": self.fired,
            "score_eligible": self.score_eligible,
            "practice_reference": self.practice_reference,
            "authority_tier": self.authority_tier,
            "severity_raw": self.severity_raw,
            "severity_weight": self.severity_weight,
            "authority_factor": self.authority_factor,
            "confidence_used": self.confidence_used,
            "contribution": self.contribution,
        }


@dataclass(frozen=True)
class FindingPriority:
    """Shared review-ordering metadata for production and evaluation arms."""

    signal_id: str
    clause_id: str
    risk_category: RiskCategory
    ranking_policy: str
    authority_gate: str
    priority_basis: str
    quantification_status: str
    fim_module: FimModule | None
    exposure_type: ExposureType | None
    source_assumptions: tuple[str, ...]
    missing_inputs: tuple[str, ...]
    exposure_low: Decimal | None
    exposure_base: Decimal | None
    exposure_high: Decimal | None
    nominal_amount: Decimal | None
    comparable_sort_value: Decimal | None
    deterministic_class: str
    scored: bool
    policy_notes: tuple[str, ...]
    sort_key: tuple[Any, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "signal_id": self.signal_id,
            "clause_id": self.clause_id,
            "risk_category": self.risk_category.value,
            "ranking_policy": self.ranking_policy,
            "authority_gate": self.authority_gate,
            "priority_basis": self.priority_basis,
            "quantification_status": self.quantification_status,
            "fim_module": self.fim_module.value if self.fim_module is not None else None,
            "exposure_type": (
                self.exposure_type.value if self.exposure_type is not None else None
            ),
            "source_assumptions": list(self.source_assumptions),
            "missing_inputs": list(self.missing_inputs),
            "exposure": {
                "low": _decimal_to_text(self.exposure_low),
                "base": _decimal_to_text(self.exposure_base),
                "high": _decimal_to_text(self.exposure_high),
                "nominal_amount": _decimal_to_text(self.nominal_amount),
            },
            "comparable_sort_value": _decimal_to_text(self.comparable_sort_value),
            "deterministic_class": self.deterministic_class,
            "scored": self.scored,
            "policy_notes": list(self.policy_notes),
        }


@dataclass(frozen=True)
class DocumentScoringResult:
    """Clause and document aggregation result for the score dimension plus D4 confidence."""

    review_priority_score: int
    category_scores: Mapping[RiskCategory, float]
    clause_assessments: tuple[ClauseAssessment, ...]
    confidence: ConfidenceBreakdown
    scoring_config_version: str
    contributions: tuple[SignalContribution, ...]
    verified_support_count: int = 0
    practice_support_count: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "review_priority_score": self.review_priority_score,
            "verified_support_count": self.verified_support_count,
            "practice_support_count": self.practice_support_count,
            "category_scores": {
                category.value: score for category, score in self.category_scores.items()
            },
            "clause_assessments": [
                assessment.to_dict() for assessment in self.clause_assessments
            ],
            "confidence": self.confidence.to_dict(),
            "scoring_config_version": self.scoring_config_version,
            "contributions": [
                contribution.as_dict() for contribution in self.contributions
            ],
        }


@dataclass(frozen=True)
class AggregationTestReport:
    """Machine-gate report for FINK-S3-02 aggregation tests."""

    scoring_config_version: str
    sc_agg_t1_bc_contributes_zero: bool
    sc_agg_t2_bounded_0_100: bool
    sc_agg_t3_low_confidence_lowers_d4_not_priority: bool

    @property
    def ok(self) -> bool:
        return (
            self.sc_agg_t1_bc_contributes_zero
            and self.sc_agg_t2_bounded_0_100
            and self.sc_agg_t3_low_confidence_lowers_d4_not_priority
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "scoring_config_version": self.scoring_config_version,
            "sc_agg_t1_bc_contributes_zero": self.sc_agg_t1_bc_contributes_zero,
            "sc_agg_t2_bounded_0_100": self.sc_agg_t2_bounded_0_100,
            "sc_agg_t3_low_confidence_lowers_d4_not_priority": (
                self.sc_agg_t3_low_confidence_lowers_d4_not_priority
            ),
            "ok": self.ok,
        }


@dataclass(frozen=True)
class Fim8UncertaintyTestReport:
    """Machine-gate report for FIM-8 uncertainty widening and confidence behavior."""

    scoring_config_version: str
    band_widen_factor: Decimal
    fim_8_t1_base_unchanged: bool
    fim_8_t1_high_up: bool
    fim_8_t1_low_down: bool
    fim_8_t1_score_unchanged: bool
    fim_8_t1_data_completeness_down: bool

    @property
    def ok(self) -> bool:
        return (
            self.fim_8_t1_base_unchanged
            and self.fim_8_t1_high_up
            and self.fim_8_t1_low_down
            and self.fim_8_t1_score_unchanged
            and self.fim_8_t1_data_completeness_down
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "scoring_config_version": self.scoring_config_version,
            "band_widen_factor": str(self.band_widen_factor),
            "fim_8_t1_base_unchanged": self.fim_8_t1_base_unchanged,
            "fim_8_t1_high_up": self.fim_8_t1_high_up,
            "fim_8_t1_low_down": self.fim_8_t1_low_down,
            "fim_8_t1_score_unchanged": self.fim_8_t1_score_unchanged,
            "fim_8_t1_data_completeness_down": self.fim_8_t1_data_completeness_down,
            "ok": self.ok,
        }


def load_scoring_config(
    config_path: Path | str = DEFAULT_SCORING_CONFIG_PATH,
) -> ScoringConfig:
    """Load the versioned heuristic scoring config used by aggregation."""

    resolved_path = Path(config_path)
    payload = _read_yaml_mapping(resolved_path)
    version = _require_text(
        payload.get("scoring_config_version"),
        "scoring_config_version",
    )
    authority_factor = _tier_value_map(
        payload.get("authority_factor"),
        "authority_factor",
        required_tiers=SCORING_AUTHORITY_TIERS,
        minimum=0.0,
        maximum=1.0,
    )
    zero_score_tiers = _tier_value_map(
        payload.get("zero_score_tiers"),
        "zero_score_tiers",
        required_tiers=("B", "C", "D0", "M1", "M2", "M3", "R0"),
        minimum=0.0,
        maximum=0.0,
    )
    severity_weight = _category_value_map(
        payload.get("severity_weight"),
        "severity_weight",
        minimum=0.0,
    )
    k_by_category = _category_value_map(payload.get("k_F"), "k_F", minimum=0.0)
    for category, value in k_by_category.items():
        if value <= 0.0:
            raise ScoringAggregationError(f"k_F.{CATEGORY_CONFIG_IDS[category]} must be > 0")
    w_by_category = _category_value_map(payload.get("w_F"), "w_F", minimum=0.0)
    if sum(w_by_category.values()) <= 0.0:
        raise ScoringAggregationError("w_F weights must sum to > 0")

    confidence_weights = _confidence_weights(payload.get("confidence_weights"))
    config = ScoringConfig(
        config_path=resolved_path,
        scoring_config_version=version,
        authority_factor=authority_factor,
        zero_score_tiers=zero_score_tiers,
        severity_weight=severity_weight,
        conf_floor=_heuristic_number(
            payload.get("conf_floor"),
            "conf_floor",
            minimum=0.0,
            maximum=1.0,
        ),
        k_by_category=k_by_category,
        w_by_category=w_by_category,
        confidence_weights=confidence_weights,
        unverified_factor=_heuristic_number(
            payload.get("unverified_factor"),
            "unverified_factor",
            minimum=0.0,
            maximum=1.0,
        ),
        base_evidence_confidence=_heuristic_number(
            payload.get("base_evidence_confidence"),
            "base_evidence_confidence",
            minimum=0.0,
            maximum=1.0,
        ),
        fim8_opacity_weights=_fim8_opacity_weights(payload),
        missing_input_weights=_missing_input_weights(payload),
    )
    return config


def aggregate_document_signals(
    signals: Sequence[RiskSignal],
    *,
    config: ScoringConfig | None = None,
    config_path: Path | str = DEFAULT_SCORING_CONFIG_PATH,
    evidence_authority_tiers: Mapping[str, str] | None = None,
    missing_input_flags: Sequence[str] = (),
    opacity_flags: Sequence[str] = (),
    ocr_confidence: float | None = None,
    practice_checkpoint_categories: Sequence[RiskCategory | str] = (),
) -> DocumentScoringResult:
    """Aggregate clause signals into F1-F9 scores and a 0-100 review priority.

    Low OCR or signal confidence is floored only for score contribution. The
    original confidence still feeds the separate D4 confidence dimension.
    """

    scoring_config = config or load_scoring_config(config_path)
    signal_tuple = tuple(signals)
    contributions = tuple(
        score_signal_contribution(
            signal,
            scoring_config,
            evidence_authority_tiers=evidence_authority_tiers,
        )
        for signal in signal_tuple
    )
    category_scores = _category_scores_from_contributions(contributions, scoring_config)
    review_priority_score = _weighted_priority(category_scores, scoring_config)
    practice_categories = _normalize_practice_checkpoint_categories(
        practice_checkpoint_categories
    )
    return DocumentScoringResult(
        review_priority_score=review_priority_score,
        category_scores=category_scores,
        clause_assessments=_clause_assessments(signal_tuple, contributions, scoring_config),
        confidence=_confidence_breakdown(
            signal_tuple,
            scoring_config,
            missing_input_flags=missing_input_flags,
            opacity_flags=opacity_flags,
            ocr_confidence=ocr_confidence,
        ),
        scoring_config_version=scoring_config.scoring_config_version,
        contributions=contributions,
        verified_support_count=_verified_support_count(contributions),
        practice_support_count=_practice_support_count(contributions, practice_categories),
    )


def score_signal_contribution(
    signal: RiskSignal,
    config: ScoringConfig,
    *,
    evidence_authority_tiers: Mapping[str, str] | None = None,
) -> SignalContribution:
    """Return one signal contribution after INV-1 authority gating."""

    category = signal.risk_category
    if not signal.fired or category not in FINANCIAL_RISK_CATEGORIES:
        return _zero_contribution(signal, config, authority_tier=None)
    if not signal.score_eligible:
        return _zero_contribution(signal, config, authority_tier=None)

    authority_tier = _best_authority_tier(
        signal.grounding_evidence_ids or (),
        evidence_authority_tiers,
    )
    if authority_tier is None:
        return _zero_contribution(signal, config, authority_tier=None)

    severity_raw = float(signal.severity_raw or 0.0)
    severity_weight = config.severity_weight[category]
    authority_factor = config.authority_factor[authority_tier]
    confidence_used = _clamp(signal.signal_confidence, config.conf_floor, 1.0)
    contribution = severity_weight * severity_raw * authority_factor * confidence_used
    return SignalContribution(
        signal_id=signal.signal_id,
        clause_id=signal.clause_id,
        risk_category=category,
        fired=signal.fired,
        score_eligible=signal.score_eligible,
        practice_reference=signal.practice_reference,
        authority_tier=authority_tier,
        severity_raw=severity_raw,
        severity_weight=severity_weight,
        authority_factor=authority_factor,
        confidence_used=confidence_used,
        contribution=max(0.0, contribution),
    )


def rank_review_findings(
    signals: Sequence[RiskSignal],
    *,
    exposures: Sequence[MonetaryExposureEstimate] = (),
    contributions: Sequence[SignalContribution] = (),
    ranking_policy: str = RANKING_POLICY_EXPOSURE_AWARE,
    authority_gate: str = AUTHORITY_GATE_ENFORCE,
) -> tuple[FindingPriority, ...]:
    """Rank findings with a transparent production/evaluation policy.

    Production uses ``exposure_aware`` plus ``enforce``. The
    ``severity_baseline`` and ``bypass_for_ablation`` options exist so
    evaluation can run explicit ablations through this same code path.
    Exposure-aware ordering only compares scenario values within the same
    exposure type; it never creates a cross-type total.
    """

    _validate_policy(ranking_policy, RANKING_POLICIES, "ranking_policy")
    _validate_policy(authority_gate, AUTHORITY_GATES, "authority_gate")
    signal_tuple = tuple(signals)
    exposure_tuple = tuple(exposures)
    contributions_by_signal = {
        (contribution.signal_id, contribution.clause_id): contribution
        for contribution in contributions
    }
    priorities = tuple(
        _finding_priority_for_signal(
            signal,
            exposure_tuple,
            contributions_by_signal.get((signal.signal_id, signal.clause_id)),
            ranking_policy=ranking_policy,
            authority_gate=authority_gate,
        )
        for signal in signal_tuple
    )
    return tuple(sorted(priorities, key=lambda priority: priority.sort_key))


def aggregation_tests(
    config_path: Path | str = DEFAULT_SCORING_CONFIG_PATH,
) -> AggregationTestReport:
    """Run the SC-AGG-T1/T2/T3 machine gate on synthetic scoring fixtures."""

    config = load_scoring_config(config_path)

    bc_signal = _synthetic_signal(
        "RS-SC-AGG-T1-BC",
        RiskCategory.F2,
        score_eligible=False,
        practice_reference=True,
        confidence=1.0,
    )
    a1_signal = _synthetic_signal(
        "RS-SC-AGG-T1-A1",
        RiskCategory.F2,
        evidence_ids=("EV-A1-SC-AGG-T1",),
        confidence=1.0,
    )
    a1_only = aggregate_document_signals(
        (a1_signal,),
        config=config,
        evidence_authority_tiers={"EV-A1-SC-AGG-T1": "A1"},
    )
    mixed = aggregate_document_signals(
        (bc_signal, a1_signal),
        config=config,
        evidence_authority_tiers={"EV-A1-SC-AGG-T1": "A1"},
    )
    bc_only = aggregate_document_signals((bc_signal,), config=config)
    t1 = (
        bc_only.review_priority_score == 0
        and bc_only.category_scores[RiskCategory.F2] == 0.0
        and mixed.review_priority_score == a1_only.review_priority_score
        and mixed.category_scores[RiskCategory.F2] == a1_only.category_scores[RiskCategory.F2]
    )

    bounded_signals = tuple(
        _synthetic_signal(
            f"RS-SC-AGG-T2-{idx}",
            RiskCategory.F7,
            evidence_ids=(f"EV-A0-SC-AGG-T2-{idx}",),
            confidence=1.0,
            severity=1.0,
        )
        for idx in range(200)
    )
    bounded_tiers = {
        f"EV-A0-SC-AGG-T2-{idx}": "A0" for idx in range(len(bounded_signals))
    }
    bounded = aggregate_document_signals(
        bounded_signals,
        config=config,
        evidence_authority_tiers=bounded_tiers,
    )
    t2 = (
        0 <= bounded.review_priority_score <= 100
        and all(0.0 <= score <= 100.0 for score in bounded.category_scores.values())
    )

    low_conf = _synthetic_signal(
        "RS-SC-AGG-T3-LOW",
        RiskCategory.F3,
        evidence_ids=("EV-A1-SC-AGG-T3-LOW",),
        confidence=config.conf_floor / 5.0,
    )
    floored_conf = _synthetic_signal(
        "RS-SC-AGG-T3-FLOOR",
        RiskCategory.F3,
        evidence_ids=("EV-A1-SC-AGG-T3-FLOOR",),
        confidence=config.conf_floor,
    )
    low_result = aggregate_document_signals(
        (low_conf,),
        config=config,
        evidence_authority_tiers={"EV-A1-SC-AGG-T3-LOW": "A1"},
    )
    floor_result = aggregate_document_signals(
        (floored_conf,),
        config=config,
        evidence_authority_tiers={"EV-A1-SC-AGG-T3-FLOOR": "A1"},
    )
    t3 = (
        low_result.review_priority_score == floor_result.review_priority_score
        and low_result.category_scores[RiskCategory.F3]
        == floor_result.category_scores[RiskCategory.F3]
        and low_result.confidence.overall_confidence
        < floor_result.confidence.overall_confidence
    )

    report = AggregationTestReport(
        scoring_config_version=config.scoring_config_version,
        sc_agg_t1_bc_contributes_zero=t1,
        sc_agg_t2_bounded_0_100=t2,
        sc_agg_t3_low_confidence_lowers_d4_not_priority=t3,
    )
    if not report.ok:
        raise ScoringAggregationError(f"aggregation_tests failed: {report.as_dict()}")
    return report


def fim8_uncertainty_test(
    config_path: Path | str = DEFAULT_SCORING_CONFIG_PATH,
) -> Fim8UncertaintyTestReport:
    """Run FIM-8-T1: opacity widens bands and lowers D4 without changing score."""

    from fink.finance import fim8_evidence_opacity_uncertainty

    config = load_scoring_config(config_path)
    opacity_flags = ("missing_settlement_records", "no_audit_access")
    baseline_exposure = MonetaryExposureEstimate(
        module=FimModule.FIM_1,
        exposure_type=ExposureType.NOMINAL_LEAKAGE,
        is_user_input_required=False,
        assumptions=(),
        low=Decimal("4550000"),
        base=Decimal("5250000"),
        high=Decimal("5950000"),
    )
    fim8 = fim8_evidence_opacity_uncertainty(
        baseline_exposure,
        opacity_flags=opacity_flags,
        opacity_weights=config.fim8_opacity_weights,
    )
    adjusted = fim8.adjusted_exposure

    signal = _synthetic_signal(
        "RS-FIM8-T1",
        RiskCategory.F1,
        evidence_ids=("EV-A1-FIM8-T1",),
        confidence=1.0,
        severity=0.7,
    )
    baseline_score = aggregate_document_signals(
        (signal,),
        config=config,
        evidence_authority_tiers={"EV-A1-FIM8-T1": "A1"},
    )
    opaque_score = aggregate_document_signals(
        (signal,),
        config=config,
        evidence_authority_tiers={"EV-A1-FIM8-T1": "A1"},
        opacity_flags=opacity_flags,
    )

    report = Fim8UncertaintyTestReport(
        scoring_config_version=config.scoring_config_version,
        band_widen_factor=fim8.band_widen_factor,
        fim_8_t1_base_unchanged=adjusted.base == baseline_exposure.base,
        fim_8_t1_high_up=adjusted.high is not None
        and baseline_exposure.high is not None
        and _within_abs(adjusted.high, Decimal("7140000"), Decimal("1"))
        and adjusted.high > baseline_exposure.high,
        fim_8_t1_low_down=adjusted.low is not None
        and baseline_exposure.low is not None
        and _within_abs(adjusted.low, Decimal("3791667"), Decimal("1"))
        and adjusted.low < baseline_exposure.low,
        fim_8_t1_score_unchanged=(
            opaque_score.review_priority_score == baseline_score.review_priority_score
            and opaque_score.category_scores == baseline_score.category_scores
        ),
        fim_8_t1_data_completeness_down=(
            opaque_score.confidence.data_completeness
            < baseline_score.confidence.data_completeness
            and opaque_score.confidence.overall_confidence
            < baseline_score.confidence.overall_confidence
        ),
    )
    if not report.ok:
        raise ScoringAggregationError(f"fim8_uncertainty_test failed: {report.as_dict()}")
    return report


def _finding_priority_for_signal(
    signal: RiskSignal,
    exposures: Sequence[MonetaryExposureEstimate],
    contribution: SignalContribution | None,
    *,
    ranking_policy: str,
    authority_gate: str,
) -> FindingPriority:
    category = signal.risk_category
    fim_module = RISK_CATEGORY_FIM_MODULE.get(category)
    expected_type = RISK_CATEGORY_EXPOSURE_TYPE.get(category)
    exposure = _matching_exposure(exposures, fim_module, expected_type)
    scored = _signal_scored_for_ranking(signal, contribution, authority_gate)
    quantification_status = _quantification_status(exposure, expected_type)
    priority_basis = _priority_basis_for(
        signal,
        exposure,
        scored=scored,
        quantification_status=quantification_status,
    )
    source_assumptions = tuple(exposure.assumptions) if exposure is not None else ()
    missing_inputs = _priority_missing_inputs(exposure, expected_type)
    comparable_sort_value = _comparable_sort_value(exposure, quantification_status)
    deterministic_class = _deterministic_priority_class(
        priority_basis,
        quantification_status,
    )
    policy_notes = _policy_notes(ranking_policy, authority_gate, exposure)
    if ranking_policy == RANKING_POLICY_SEVERITY_BASELINE:
        sort_key = _severity_baseline_sort_key(signal)
        deterministic_class = "severity_baseline"
    else:
        sort_key = _exposure_aware_sort_key(
            signal,
            priority_basis=priority_basis,
            quantification_status=quantification_status,
            exposure_type=expected_type,
            comparable_sort_value=comparable_sort_value,
            nominal_amount=exposure.nominal_amount if exposure is not None else None,
        )
    return FindingPriority(
        signal_id=signal.signal_id,
        clause_id=signal.clause_id,
        risk_category=category,
        ranking_policy=ranking_policy,
        authority_gate=authority_gate,
        priority_basis=priority_basis,
        quantification_status=quantification_status,
        fim_module=fim_module,
        exposure_type=expected_type,
        source_assumptions=source_assumptions,
        missing_inputs=missing_inputs,
        exposure_low=exposure.low if exposure is not None else None,
        exposure_base=exposure.base if exposure is not None else None,
        exposure_high=exposure.high if exposure is not None else None,
        nominal_amount=exposure.nominal_amount if exposure is not None else None,
        comparable_sort_value=comparable_sort_value,
        deterministic_class=deterministic_class,
        scored=scored,
        policy_notes=policy_notes,
        sort_key=sort_key,
    )


def _signal_scored_for_ranking(
    signal: RiskSignal,
    contribution: SignalContribution | None,
    authority_gate: str,
) -> bool:
    if authority_gate == AUTHORITY_GATE_BYPASS_FOR_ABLATION:
        return bool(signal.fired and signal.risk_category in FINANCIAL_RISK_CATEGORIES)
    return bool(contribution is not None and contribution.contribution > 0)


def _matching_exposure(
    exposures: Sequence[MonetaryExposureEstimate],
    fim_module: FimModule | None,
    expected_type: ExposureType | None,
) -> MonetaryExposureEstimate | None:
    if fim_module is None or expected_type is None:
        return None
    exact = tuple(
        exposure
        for exposure in exposures
        if exposure.module is fim_module and exposure.exposure_type is expected_type
    )
    if exact:
        return max(exact, key=_exposure_selection_key)
    same_module = tuple(exposure for exposure in exposures if exposure.module is fim_module)
    if same_module:
        return max(same_module, key=_exposure_selection_key)
    return None


def _exposure_selection_key(exposure: MonetaryExposureEstimate) -> tuple[Decimal, Decimal, str]:
    high = exposure.high or exposure.base or exposure.nominal_amount or Decimal("0")
    base = exposure.base or exposure.nominal_amount or Decimal("0")
    return high, base, exposure.exposure_type.value


def _quantification_status(
    exposure: MonetaryExposureEstimate | None,
    expected_type: ExposureType | None,
) -> str:
    if expected_type is None:
        return QUANTIFICATION_STATUS_NOT_APPLICABLE
    if exposure is None:
        return QUANTIFICATION_STATUS_INPUT_REQUIRED
    if _has_unbounded_flag(exposure):
        return QUANTIFICATION_STATUS_UNBOUNDED
    has_range = (
        exposure.low is not None
        and exposure.base is not None
        and exposure.high is not None
    )
    if has_range and not exposure.is_user_input_required:
        return QUANTIFICATION_STATUS_QUANTIFIED
    if exposure.nominal_amount is not None:
        return QUANTIFICATION_STATUS_PARTIALLY_BOUNDED
    if exposure.is_user_input_required:
        return QUANTIFICATION_STATUS_INPUT_REQUIRED
    return QUANTIFICATION_STATUS_NOT_APPLICABLE


def _has_unbounded_flag(exposure: MonetaryExposureEstimate) -> bool:
    return any(
        flag in {"uncapped", "unbounded"} or flag.endswith(":uncapped")
        for flag in (exposure.uncertainty_flags or ())
    )


def _priority_basis_for(
    signal: RiskSignal,
    exposure: MonetaryExposureEstimate | None,
    *,
    scored: bool,
    quantification_status: str,
) -> str:
    if not scored:
        return PRIORITY_BASIS_UNVERIFIED_CANDIDATE
    if quantification_status == QUANTIFICATION_STATUS_UNBOUNDED:
        return PRIORITY_BASIS_UNCAPPED_OR_UNBOUNDED
    if exposure is not None and exposure.exposure_type is ExposureType.PRESENT_VALUE_LOSS:
        return PRIORITY_BASIS_PRESENT_VALUE_TIMING
    if quantification_status in {
        QUANTIFICATION_STATUS_QUANTIFIED,
        QUANTIFICATION_STATUS_PARTIALLY_BOUNDED,
    }:
        return PRIORITY_BASIS_QUANTIFIED_EXPOSURE
    if signal.risk_category in {RiskCategory.F1, RiskCategory.F9}:
        return PRIORITY_BASIS_COUNTERPARTY_VERIFICATION
    return PRIORITY_BASIS_GROUNDED_QUALITATIVE_SIGNAL


def _priority_missing_inputs(
    exposure: MonetaryExposureEstimate | None,
    expected_type: ExposureType | None,
) -> tuple[str, ...]:
    if expected_type is None:
        return ()
    if exposure is None:
        return ("scenario_inputs_not_provided",)
    missing: list[str] = []
    for flag in exposure.uncertainty_flags or ():
        if flag.startswith("missing_user_input:"):
            missing.append(flag.split(":", maxsplit=1)[1])
    return tuple(missing)


def _comparable_sort_value(
    exposure: MonetaryExposureEstimate | None,
    quantification_status: str,
) -> Decimal | None:
    if exposure is None or quantification_status == QUANTIFICATION_STATUS_UNBOUNDED:
        return None
    if quantification_status == QUANTIFICATION_STATUS_QUANTIFIED:
        return exposure.high or exposure.base or exposure.low
    if quantification_status == QUANTIFICATION_STATUS_PARTIALLY_BOUNDED:
        return exposure.nominal_amount
    return None


def _deterministic_priority_class(priority_basis: str, quantification_status: str) -> str:
    if priority_basis == PRIORITY_BASIS_UNCAPPED_OR_UNBOUNDED:
        return "unbounded_override"
    if priority_basis == PRIORITY_BASIS_PRESENT_VALUE_TIMING:
        return "present_value_timing"
    if quantification_status in {
        QUANTIFICATION_STATUS_QUANTIFIED,
        QUANTIFICATION_STATUS_PARTIALLY_BOUNDED,
    }:
        return "comparable_exposure_type"
    if priority_basis == PRIORITY_BASIS_COUNTERPARTY_VERIFICATION:
        return "counterparty_verification"
    if priority_basis == PRIORITY_BASIS_UNVERIFIED_CANDIDATE:
        return "unverified_candidate"
    return "grounded_qualitative_signal"


def _policy_notes(
    ranking_policy: str,
    authority_gate: str,
    exposure: MonetaryExposureEstimate | None,
) -> tuple[str, ...]:
    notes = [
        "ranking_policy:" + ranking_policy,
        "authority_gate:" + authority_gate,
        "confidence_not_used_as_exposure_multiplier",
        "no_cross_exposure_type_total",
    ]
    if authority_gate == AUTHORITY_GATE_BYPASS_FOR_ABLATION:
        notes.append("evaluation_only_authority_gate_bypass")
    if exposure is None:
        notes.append("no_fim_output_value_substituted")
    return tuple(notes)


def _severity_baseline_sort_key(signal: RiskSignal) -> tuple[Any, ...]:
    score = float(signal.severity_raw or 0.0) * float(signal.signal_confidence)
    return (-score, signal.signal_id, signal.clause_id)


def _exposure_aware_sort_key(
    signal: RiskSignal,
    *,
    priority_basis: str,
    quantification_status: str,
    exposure_type: ExposureType | None,
    comparable_sort_value: Decimal | None,
    nominal_amount: Decimal | None,
) -> tuple[Any, ...]:
    class_order = {
        PRIORITY_BASIS_UNCAPPED_OR_UNBOUNDED: 0,
        PRIORITY_BASIS_QUANTIFIED_EXPOSURE: 10,
        PRIORITY_BASIS_PRESENT_VALUE_TIMING: 10,
        PRIORITY_BASIS_COUNTERPARTY_VERIFICATION: 20,
        PRIORITY_BASIS_GROUNDED_QUALITATIVE_SIGNAL: 30,
        PRIORITY_BASIS_UNVERIFIED_CANDIDATE: 40,
    }[priority_basis]
    status_order = {
        QUANTIFICATION_STATUS_QUANTIFIED: 0,
        QUANTIFICATION_STATUS_PARTIALLY_BOUNDED: 1,
        QUANTIFICATION_STATUS_UNBOUNDED: 0,
        QUANTIFICATION_STATUS_INPUT_REQUIRED: 2,
        QUANTIFICATION_STATUS_NOT_APPLICABLE: 3,
    }[quantification_status]
    type_order = (
        _EXPOSURE_TYPE_ORDER[exposure_type]
        if exposure_type is not None
        else len(_EXPOSURE_TYPE_ORDER)
    )
    amount = comparable_sort_value or nominal_amount or Decimal("0")
    return (
        class_order,
        status_order,
        type_order,
        -amount,
        -float(signal.severity_raw or 0.0),
        signal.signal_id,
        signal.clause_id,
    )


def _category_scores_from_contributions(
    contributions: Sequence[SignalContribution],
    config: ScoringConfig,
) -> dict[RiskCategory, float]:
    totals = {category: 0.0 for category in SORTED_FINANCIAL_CATEGORIES}
    for contribution in contributions:
        if contribution.risk_category in FINANCIAL_RISK_CATEGORIES:
            totals[contribution.risk_category] += contribution.contribution
    return {
        category: _saturating_category_score(total, config.k_by_category[category])
        for category, total in totals.items()
    }


def _saturating_category_score(total_contribution: float, k_value: float) -> float:
    """Bounded, saturating category score: ``100 * (1 - exp(-ΣC / k))``.

    The exponential maps the non-negative accumulation ``ΣC ∈ [0, ∞)`` into
    ``[0, 100)`` by construction (diminishing marginal risk), so a category can
    never exceed 100 no matter how many signals fire. ``k`` is the saturation
    scale (at ``ΣC = k`` the score is ``100·(1 − 1/e) ≈ 63.2``). A non-positive
    ``k`` is degenerate config; we treat any positive accumulation as fully
    saturated so the bound still holds.
    """

    total = max(0.0, total_contribution)
    if k_value <= 0.0:
        return 100.0 if total > 0.0 else 0.0
    score = 100.0 * (1.0 - math.exp(-(total / k_value)))
    return _clamp(score, 0.0, 100.0)


def _weighted_priority(
    category_scores: Mapping[RiskCategory, float],
    config: ScoringConfig,
) -> int:
    """Document Review-Priority Score: a weight-normalized convex combination of
    the per-category scores, ``round(Σ w_F·S_F / Σ w_F)``.

    Because every ``S_F ∈ [0, 100]`` and the weights are non-negative with a
    positive total, the normalized sum is a convex combination and therefore
    inherits the ``[0, 100]`` range — the priority is bounded by construction,
    not merely clamped. Negative weights are floored at 0 and a non-positive
    weight total falls back to an equal-weight mean so a malformed config can
    never divide by zero or break the bound.
    """

    weights = [max(0.0, config.w_by_category[category]) for category in SORTED_FINANCIAL_CATEGORIES]
    scores = [category_scores[category] for category in SORTED_FINANCIAL_CATEGORIES]
    weight_total = sum(weights)
    if weight_total <= 0.0:
        weighted_sum = sum(scores)
        weight_total = float(len(scores)) or 1.0
    else:
        weighted_sum = sum(weight * score for weight, score in zip(weights, scores))
    return int(_clamp(round(weighted_sum / weight_total), 0, 100))


def _verified_support_count(contributions: Sequence[SignalContribution]) -> int:
    return sum(
        1
        for contribution in contributions
        if (
            contribution.fired
            and contribution.score_eligible
            and contribution.risk_category in FINANCIAL_RISK_CATEGORIES
        )
    )


def _practice_support_count(
    contributions: Sequence[SignalContribution],
    practice_checkpoint_categories: set[RiskCategory],
) -> int:
    return sum(
        1
        for contribution in contributions
        if (
            contribution.fired
            and contribution.risk_category in FINANCIAL_RISK_CATEGORIES
            and (
                contribution.practice_reference
                or contribution.risk_category in practice_checkpoint_categories
            )
        )
    )


def _normalize_practice_checkpoint_categories(
    categories: Sequence[RiskCategory | str],
) -> set[RiskCategory]:
    normalized: set[RiskCategory] = set()
    for category in categories:
        if isinstance(category, RiskCategory):
            normalized.add(category)
            continue
        try:
            normalized.add(RiskCategory(str(category).strip().upper()))
        except ValueError:
            continue
    return normalized


def _within_abs(observed: Decimal | None, expected: Decimal, tolerance: Decimal) -> bool:
    return observed is not None and abs(observed - expected) <= tolerance


def _clause_assessments(
    signals: Sequence[RiskSignal],
    contributions: Sequence[SignalContribution],
    config: ScoringConfig,
) -> tuple[ClauseAssessment, ...]:
    signals_by_clause: dict[str, list[RiskSignal]] = defaultdict(list)
    contributions_by_clause: dict[str, list[SignalContribution]] = defaultdict(list)
    for signal in signals:
        signals_by_clause[signal.clause_id].append(signal)
    for contribution in contributions:
        contributions_by_clause[contribution.clause_id].append(contribution)

    assessments: list[ClauseAssessment] = []
    for clause_id in sorted(signals_by_clause):
        clause_category_scores = _category_scores_from_contributions(
            contributions_by_clause.get(clause_id, ()),
            config,
        )
        evidence_ids = _unique_evidence_ids(signals_by_clause[clause_id])
        assessments.append(
            ClauseAssessment(
                clause_id=clause_id,
                signals=tuple(signals_by_clause[clause_id]),
                category_scores=clause_category_scores,
                clause_priority=_weighted_priority(clause_category_scores, config),
                evidence_ids=evidence_ids or None,
            )
        )
    return tuple(assessments)


def _confidence_breakdown(
    signals: Sequence[RiskSignal],
    config: ScoringConfig,
    *,
    missing_input_flags: Sequence[str],
    opacity_flags: Sequence[str],
    ocr_confidence: float | None,
) -> ConfidenceBreakdown:
    fired_financial_signals = tuple(
        signal
        for signal in signals
        if signal.fired and signal.risk_category in FINANCIAL_RISK_CATEGORIES
    )
    if ocr_confidence is None:
        raw_ocr_confidence = _mean(
            signal.signal_confidence for signal in fired_financial_signals
        )
    else:
        raw_ocr_confidence = _clamp(float(ocr_confidence), 0.0, 1.0)

    eligible_count = sum(1 for signal in fired_financial_signals if signal.score_eligible)
    grounding_density = (
        eligible_count / len(fired_financial_signals) if fired_financial_signals else 1.0
    )
    evidence_confidence = _clamp(
        config.base_evidence_confidence * config.unverified_factor * grounding_density,
        0.0,
        1.0,
    )
    confidence_flags = (*missing_input_flags, *opacity_flags)
    data_completeness = 1.0 - _clamp(_missing_input_penalty(confidence_flags, config), 0.0, 1.0)
    weights = config.confidence_weights
    overall = (
        raw_ocr_confidence ** weights.ocr_confidence
        * evidence_confidence ** weights.evidence_confidence
        * data_completeness ** weights.data_completeness
    )
    drivers = [
        f"ocr_confidence={raw_ocr_confidence:.3f}",
        f"evidence_confidence={evidence_confidence:.3f}",
        f"data_completeness={data_completeness:.3f}",
    ]
    if any(signal.signal_confidence < config.conf_floor for signal in fired_financial_signals):
        drivers.append("low_signal_confidence_floored_for_priority_only")
    if missing_input_flags:
        drivers.append("missing_input_flags=" + ",".join(sorted(missing_input_flags)))
    if opacity_flags:
        drivers.append("opacity_flags=" + ",".join(sorted(opacity_flags)))
    return ConfidenceBreakdown(
        ocr_confidence=raw_ocr_confidence,
        evidence_confidence=evidence_confidence,
        data_completeness=data_completeness,
        overall_confidence=_clamp(overall, 0.0, 1.0),
        drivers=tuple(drivers),
    )


def _missing_input_penalty(flags: Sequence[str], config: ScoringConfig) -> float:
    total = 0.0
    for flag in flags:
        if flag in config.missing_input_weights:
            total += config.missing_input_weights[flag]
        elif flag in config.fim8_opacity_weights:
            total += config.fim8_opacity_weights[flag]
        else:
            raise ScoringAggregationError(f"unknown missing input flag: {flag}")
    return total


def _zero_contribution(
    signal: RiskSignal,
    config: ScoringConfig,
    *,
    authority_tier: str | None,
) -> SignalContribution:
    category = signal.risk_category
    return SignalContribution(
        signal_id=signal.signal_id,
        clause_id=signal.clause_id,
        risk_category=category,
        fired=signal.fired,
        score_eligible=signal.score_eligible,
        practice_reference=signal.practice_reference,
        authority_tier=authority_tier,
        severity_raw=float(signal.severity_raw or 0.0),
        severity_weight=config.severity_weight.get(category, 0.0),
        authority_factor=0.0,
        confidence_used=_clamp(signal.signal_confidence, config.conf_floor, 1.0),
        contribution=0.0,
    )


def _best_authority_tier(
    evidence_ids: Sequence[str],
    evidence_authority_tiers: Mapping[str, str] | None,
) -> str | None:
    if not evidence_ids:
        return None
    if evidence_authority_tiers is None:
        return None

    scoring_tiers: list[str] = []
    for evidence_id in evidence_ids:
        tier = evidence_authority_tiers.get(evidence_id)
        if tier is None:
            continue
        if tier in SCORING_AUTHORITY_TIERS:
            scoring_tiers.append(tier)

    if scoring_tiers:
        return min(scoring_tiers, key=lambda tier: AUTHORITY_TIER_RANK[tier])
    return None


def _unique_evidence_ids(signals: Sequence[RiskSignal]) -> tuple[str, ...]:
    seen: set[str] = set()
    ordered: list[str] = []
    for signal in signals:
        for evidence_id in signal.grounding_evidence_ids or ():
            if evidence_id not in seen:
                seen.add(evidence_id)
                ordered.append(evidence_id)
    return tuple(ordered)


def _synthetic_signal(
    signal_id: str,
    category: RiskCategory,
    *,
    score_eligible: bool = True,
    practice_reference: bool = False,
    evidence_ids: tuple[str, ...] = (),
    confidence: float = 1.0,
    severity: float = 1.0,
) -> RiskSignal:
    return RiskSignal(
        signal_id=signal_id,
        clause_id=f"clause-{category.value.lower()}",
        risk_category=category,
        detector="rule",
        fired=True,
        score_eligible=score_eligible,
        practice_reference=practice_reference,
        signal_confidence=confidence,
        is_missing_protection=False,
        grounding_evidence_ids=evidence_ids or None,
        severity_raw=severity,
    )


def _read_yaml_mapping(path: Path) -> Mapping[str, Any]:
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ScoringAggregationError(f"scoring config not found: {path}") from exc
    return _require_mapping(payload, path.as_posix())


def _category_value_map(
    payload: Any,
    field_name: str,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
) -> dict[RiskCategory, float]:
    item = _require_mapping(payload, field_name)
    values: dict[RiskCategory, float] = {}
    for config_id, category in CONFIG_ID_TO_CATEGORY.items():
        values[category] = _heuristic_number(
            item.get(config_id),
            f"{field_name}.{config_id}",
            minimum=minimum,
            maximum=maximum,
        )
    extra = set(item) - set(CONFIG_ID_TO_CATEGORY)
    if extra:
        raise ScoringAggregationError(f"{field_name}: unknown categories {sorted(extra)}")
    return values


def _tier_value_map(
    payload: Any,
    field_name: str,
    *,
    required_tiers: Sequence[str],
    minimum: float | None = None,
    maximum: float | None = None,
) -> dict[str, float]:
    item = _require_mapping(payload, field_name)
    values: dict[str, float] = {}
    for tier in required_tiers:
        values[tier] = _heuristic_number(
            item.get(tier),
            f"{field_name}.{tier}",
            minimum=minimum,
            maximum=maximum,
        )
    return values


def _confidence_weights(payload: Any) -> ConfidenceWeights:
    item = _require_mapping(payload, "confidence_weights")
    expected_sum = _plain_number(
        item.get("sum_required"),
        "confidence_weights.sum_required",
        minimum=0.0,
    )
    weights = ConfidenceWeights(
        ocr_confidence=_heuristic_number(
            item.get("ocr_confidence_wo"),
            "confidence_weights.ocr_confidence_wo",
            minimum=0.0,
            maximum=1.0,
        ),
        evidence_confidence=_heuristic_number(
            item.get("evidence_confidence_we"),
            "confidence_weights.evidence_confidence_we",
            minimum=0.0,
            maximum=1.0,
        ),
        data_completeness=_heuristic_number(
            item.get("data_completeness_wd"),
            "confidence_weights.data_completeness_wd",
            minimum=0.0,
            maximum=1.0,
        ),
    )
    observed_sum = (
        weights.ocr_confidence + weights.evidence_confidence + weights.data_completeness
    )
    if abs(observed_sum - expected_sum) > 1e-9:
        raise ScoringAggregationError("confidence_weights must sum to sum_required")
    return weights


def _missing_input_weights(payload: Mapping[str, Any]) -> dict[str, float]:
    fim_defaults = _require_mapping(payload.get("fim_defaults"), "fim_defaults")
    fim_8 = _require_mapping(fim_defaults.get("FIM_8"), "fim_defaults.FIM_8")
    missing_weights = _require_mapping(
        fim_8.get("missing_input_weights"),
        "fim_defaults.FIM_8.missing_input_weights",
    )
    return {
        str(flag): _heuristic_number(
            item,
            f"fim_defaults.FIM_8.missing_input_weights.{flag}",
            minimum=0.0,
            maximum=1.0,
        )
        for flag, item in missing_weights.items()
    }


def _fim8_opacity_weights(payload: Mapping[str, Any]) -> dict[str, float]:
    fim_defaults = _require_mapping(payload.get("fim_defaults"), "fim_defaults")
    fim_8 = _require_mapping(fim_defaults.get("FIM_8"), "fim_defaults.FIM_8")
    opacity_weights = _require_mapping(
        fim_8.get("opacity_weights"),
        "fim_defaults.FIM_8.opacity_weights",
    )
    return {
        str(flag): _heuristic_number(
            item,
            f"fim_defaults.FIM_8.opacity_weights.{flag}",
            minimum=0.0,
            maximum=1.0,
        )
        for flag, item in opacity_weights.items()
    }


def _heuristic_number(
    payload: Any,
    field_name: str,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    item = _require_mapping(payload, field_name)
    if item.get("heuristic") is not True:
        raise ScoringAggregationError(f"{field_name}: heuristic must be true")
    number = item.get("value")
    if not isinstance(number, int | float) or isinstance(number, bool):
        raise ScoringAggregationError(f"{field_name}.value must be numeric")
    value = float(number)
    if not math.isfinite(value):
        raise ScoringAggregationError(f"{field_name}.value must be finite")
    if minimum is not None and value < minimum:
        raise ScoringAggregationError(f"{field_name}.value must be >= {minimum}")
    if maximum is not None and value > maximum:
        raise ScoringAggregationError(f"{field_name}.value must be <= {maximum}")
    return value


def _plain_number(
    payload: Any,
    field_name: str,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    if not isinstance(payload, int | float) or isinstance(payload, bool):
        raise ScoringAggregationError(f"{field_name} must be numeric")
    value = float(payload)
    if not math.isfinite(value):
        raise ScoringAggregationError(f"{field_name} must be finite")
    if minimum is not None and value < minimum:
        raise ScoringAggregationError(f"{field_name} must be >= {minimum}")
    if maximum is not None and value > maximum:
        raise ScoringAggregationError(f"{field_name} must be <= {maximum}")
    return value


def _require_mapping(value: Any, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ScoringAggregationError(f"{field_name} must be a mapping")
    return value


def _require_text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ScoringAggregationError(f"{field_name} must be nonblank text")
    return value.strip()


def _validate_policy(value: str, allowed: Sequence[str], field_name: str) -> None:
    if value not in allowed:
        raise ScoringAggregationError(
            f"{field_name} must be one of {', '.join(allowed)}"
        )


def _decimal_to_text(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return format(value, "f")


def _mean(values: Sequence[float] | Any) -> float:
    numbers = tuple(float(value) for value in values)
    if not numbers:
        return 1.0
    return _clamp(sum(numbers) / len(numbers), 0.0, 1.0)


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return min(max(value, minimum), maximum)

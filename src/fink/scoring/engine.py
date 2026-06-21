from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import yaml  # type: ignore[import-untyped]
except Exception as exc:  # pragma: no cover - dependency is declared in pyproject
    raise RuntimeError("PyYAML is required for FInk scoring config") from exc

from fink.schemas import (
    ClauseAssessment,
    ConfidenceBreakdown,
    FINANCIAL_RISK_CATEGORIES,
    RiskCategory,
    RiskSignal,
)


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SCORING_CONFIG_PATH = REPO_ROOT / "config" / "scoring_config.yaml"

SCORING_AUTHORITY_TIERS = ("A0", "A1", "A2")
AUTHORITY_TIER_RANK = {"A0": 0, "A1": 1, "A2": 2}
DEFAULT_MISSING_AUTHORITY_TIER = "A2"
ZERO_SCORE_TIERS = ("B", "C", "B/C", "D0", "M1", "M2", "M3", "R0")

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
class DocumentScoringResult:
    """Clause and document aggregation result for the score dimension plus D4 confidence."""

    review_priority_score: int
    category_scores: Mapping[RiskCategory, float]
    clause_assessments: tuple[ClauseAssessment, ...]
    confidence: ConfidenceBreakdown
    scoring_config_version: str
    contributions: tuple[SignalContribution, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "review_priority_score": self.review_priority_score,
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
    ocr_confidence: float | None = None,
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
    return DocumentScoringResult(
        review_priority_score=review_priority_score,
        category_scores=category_scores,
        clause_assessments=_clause_assessments(signal_tuple, contributions, scoring_config),
        confidence=_confidence_breakdown(
            signal_tuple,
            scoring_config,
            missing_input_flags=missing_input_flags,
            ocr_confidence=ocr_confidence,
        ),
        scoring_config_version=scoring_config.scoring_config_version,
        contributions=contributions,
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
    score = 100.0 * (1.0 - math.exp(-(max(0.0, total_contribution) / k_value)))
    return _clamp(score, 0.0, 100.0)


def _weighted_priority(
    category_scores: Mapping[RiskCategory, float],
    config: ScoringConfig,
) -> int:
    weighted_sum = sum(
        config.w_by_category[category] * category_scores[category]
        for category in SORTED_FINANCIAL_CATEGORIES
    )
    weight_total = sum(config.w_by_category[category] for category in SORTED_FINANCIAL_CATEGORIES)
    return int(_clamp(round(weighted_sum / weight_total), 0, 100))


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
    data_completeness = 1.0 - _clamp(
        _missing_input_penalty(missing_input_flags, config),
        0.0,
        1.0,
    )
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
        if flag not in config.missing_input_weights:
            raise ScoringAggregationError(f"unknown missing input flag: {flag}")
        total += config.missing_input_weights[flag]
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
        return DEFAULT_MISSING_AUTHORITY_TIER

    scoring_tiers: list[str] = []
    saw_missing = False
    for evidence_id in evidence_ids:
        tier = evidence_authority_tiers.get(evidence_id)
        if tier is None:
            saw_missing = True
            continue
        if tier in SCORING_AUTHORITY_TIERS:
            scoring_tiers.append(tier)

    if scoring_tiers:
        return min(scoring_tiers, key=lambda tier: AUTHORITY_TIER_RANK[tier])
    return DEFAULT_MISSING_AUTHORITY_TIER if saw_missing else None


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


def _mean(values: Sequence[float] | Any) -> float:
    numbers = tuple(float(value) for value in values)
    if not numbers:
        return 1.0
    return _clamp(sum(numbers) / len(numbers), 0.0, 1.0)


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return min(max(value, minimum), maximum)

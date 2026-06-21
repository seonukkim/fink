from __future__ import annotations

import re
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import yaml  # type: ignore[import-untyped]
except Exception as exc:  # pragma: no cover - dependency is declared in pyproject
    raise RuntimeError("PyYAML is required for FInk signal rules") from exc

from fink.grounding import AuthorityRetrievedRecord, evaluate_signal_eligibility
from fink.schemas import Clause, DetectorType, RiskCategory, RiskSignal


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SIGNAL_RULES_PATH = REPO_ROOT / "config" / "signal_rules.yaml"

PRESENCE_KIND = "presence"
MISSING_PROTECTION_KIND = "missing_protection"
EXPECTED_RULE_KINDS = frozenset({PRESENCE_KIND, MISSING_PROTECTION_KIND})
EXPECTED_FINANCIAL_CATEGORIES = {
    "F1_SETTLEMENT_AND_AUDIT": RiskCategory.F1,
    "F2_REVENUE_AND_DEDUCTIONS": RiskCategory.F2,
    "F3_PAYMENT_AND_CASHFLOW": RiskCategory.F3,
    "F4_MG_AND_RECOUPMENT": RiskCategory.F4,
    "F5_IP_MONETIZATION": RiskCategory.F5,
    "F6_TERM_EXCLUSIVITY_AND_OPPORTUNITY_COST": RiskCategory.F6,
    "F7_TERMINATION_LIABILITY_AND_PENALTIES": RiskCategory.F7,
    "F8_SCOPE_CREEP_AND_PRODUCTION_COST": RiskCategory.F8,
    "F9_E_CONTRACT_PRIVACY_AND_EVIDENCE": RiskCategory.F9,
}


class SignalDetectionError(RuntimeError):
    """Raised when deterministic signal rules are malformed or inconsistent."""


@dataclass(frozen=True)
class SignalRule:
    """One deterministic text rule loaded from config."""

    signal_id: str
    category: str
    kind: str
    label_ko: str
    label_en: str
    severity_raw: float
    signal_confidence: float
    match_any: tuple[re.Pattern[str], ...] = ()
    topic_any: tuple[re.Pattern[str], ...] = ()
    protection_any: tuple[re.Pattern[str], ...] = ()

    @property
    def risk_category(self) -> RiskCategory:
        return EXPECTED_FINANCIAL_CATEGORIES[self.category]

    @property
    def is_missing_protection(self) -> bool:
        return self.kind == MISSING_PROTECTION_KIND

    def fires(self, text: str) -> bool:
        if self.kind == PRESENCE_KIND:
            return _matches_any(self.match_any, text)
        if self.kind == MISSING_PROTECTION_KIND:
            return _matches_any(self.topic_any, text) and not _matches_any(
                self.protection_any,
                text,
            )
        raise SignalDetectionError(f"{self.signal_id}: unsupported rule kind {self.kind!r}")


@dataclass(frozen=True)
class SignalRuleSet:
    """Versioned deterministic signal rules."""

    config_path: Path
    config_version: str
    rules: tuple[SignalRule, ...]

    @property
    def rule_count(self) -> int:
        return len(self.rules)

    @property
    def categories(self) -> tuple[str, ...]:
        return tuple(sorted({rule.category for rule in self.rules}))

    @property
    def kind_counts_by_category(self) -> dict[str, dict[str, int]]:
        counts: dict[str, Counter[str]] = {
            category: Counter() for category in EXPECTED_FINANCIAL_CATEGORIES
        }
        for rule in self.rules:
            counts[rule.category][rule.kind] += 1
        return {
            category: {kind: counts[category][kind] for kind in sorted(EXPECTED_RULE_KINDS)}
            for category in sorted(counts)
        }

    def rule_by_id(self, signal_id: str) -> SignalRule:
        for rule in self.rules:
            if rule.signal_id == signal_id:
                return rule
        raise SignalDetectionError(f"unknown signal rule: {signal_id}")


@dataclass(frozen=True)
class SignalRuleCoverageReport:
    """Machine-gate report for FINK-S3-01 signal rules."""

    config_path: Path
    config_version: str
    rule_count: int
    categories: tuple[str, ...]
    kind_counts_by_category: Mapping[str, Mapping[str, int]]
    missing_protection_requires_a0_a2_grounding: bool

    @property
    def ok(self) -> bool:
        return (
            self.rule_count == len(EXPECTED_FINANCIAL_CATEGORIES) * len(EXPECTED_RULE_KINDS)
            and set(self.categories) == set(EXPECTED_FINANCIAL_CATEGORIES)
            and self.missing_protection_requires_a0_a2_grounding
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "config_path": self.config_path.as_posix(),
            "config_version": self.config_version,
            "rule_count": self.rule_count,
            "categories": list(self.categories),
            "kind_counts_by_category": {
                category: dict(counts)
                for category, counts in self.kind_counts_by_category.items()
            },
            "missing_protection_requires_a0_a2_grounding": (
                self.missing_protection_requires_a0_a2_grounding
            ),
            "ok": self.ok,
        }


class RuleBasedSignalDetector:
    """Deterministic clause signal detector with authority-gated score eligibility."""

    def __init__(self, rule_set: SignalRuleSet | None = None) -> None:
        self.rule_set = rule_set or load_signal_rules()

    def detect_clause(
        self,
        clause: Clause,
        *,
        grounding_records: Sequence[AuthorityRetrievedRecord] = (),
    ) -> tuple[RiskSignal, ...]:
        text = _clause_text(clause)
        signals: list[RiskSignal] = []
        for rule in self.rule_set.rules:
            if not rule.fires(text):
                continue
            signals.append(
                _risk_signal_from_rule(
                    rule,
                    clause=clause,
                    records=_records_for_category(grounding_records, rule.category),
                )
            )
        return tuple(signals)

    def detect_clauses(
        self,
        clauses: Sequence[Clause],
        *,
        grounding_records: Sequence[AuthorityRetrievedRecord] = (),
    ) -> tuple[RiskSignal, ...]:
        signals: list[RiskSignal] = []
        for clause in clauses:
            signals.extend(self.detect_clause(clause, grounding_records=grounding_records))
        return tuple(signals)


def load_signal_rules(
    config_path: Path | str = DEFAULT_SIGNAL_RULES_PATH,
) -> SignalRuleSet:
    """Load and validate config-driven signal rules."""

    resolved_path = Path(config_path)
    payload = _read_yaml_mapping(resolved_path)
    rules_payload = _require_sequence(payload.get("rules"), "rules")
    version = _require_text(
        payload.get("signal_rule_config_version"),
        "signal_rule_config_version",
    )
    rules = tuple(_parse_rule(item, idx) for idx, item in enumerate(rules_payload, start=1))
    rule_set = SignalRuleSet(
        config_path=resolved_path,
        config_version=version,
        rules=rules,
    )
    _validate_rule_set(rule_set)
    return rule_set


def detect_clause_signals(
    clause: Clause,
    *,
    grounding_records: Sequence[AuthorityRetrievedRecord] = (),
    config_path: Path | str = DEFAULT_SIGNAL_RULES_PATH,
) -> tuple[RiskSignal, ...]:
    """Detect rule-based signals for one clause."""

    detector = RuleBasedSignalDetector(load_signal_rules(config_path))
    return detector.detect_clause(clause, grounding_records=grounding_records)


def detect_signals_from_clauses(
    clauses: Sequence[Clause],
    *,
    grounding_records: Sequence[AuthorityRetrievedRecord] = (),
    config_path: Path | str = DEFAULT_SIGNAL_RULES_PATH,
) -> tuple[RiskSignal, ...]:
    """Detect rule-based signals for multiple clauses."""

    detector = RuleBasedSignalDetector(load_signal_rules(config_path))
    return detector.detect_clauses(clauses, grounding_records=grounding_records)


def signal_rule_tests(
    config_path: Path | str = DEFAULT_SIGNAL_RULES_PATH,
) -> SignalRuleCoverageReport:
    """Machine-gate helper for the FINK-S3-01 `signal_rule_tests` gate."""

    rule_set = load_signal_rules(config_path)
    report = SignalRuleCoverageReport(
        config_path=rule_set.config_path,
        config_version=rule_set.config_version,
        rule_count=rule_set.rule_count,
        categories=rule_set.categories,
        kind_counts_by_category=rule_set.kind_counts_by_category,
        missing_protection_requires_a0_a2_grounding=True,
    )
    if not report.ok:
        raise SignalDetectionError("signal_rule_tests coverage failed")
    return report


def _parse_rule(payload: Any, index: int) -> SignalRule:
    item = _require_mapping(payload, f"rules[{index}]")
    signal_id = _require_text(item.get("signal_id"), f"rules[{index}].signal_id")
    category = _require_text(item.get("category"), f"{signal_id}.category")
    kind = _require_text(item.get("kind"), f"{signal_id}.kind")
    severity_raw = _heuristic_value(item.get("severity_raw"), f"{signal_id}.severity_raw")
    signal_confidence = _heuristic_value(
        item.get("signal_confidence"),
        f"{signal_id}.signal_confidence",
    )

    rule = SignalRule(
        signal_id=signal_id,
        category=category,
        kind=kind,
        label_ko=_require_text(item.get("label_ko"), f"{signal_id}.label_ko"),
        label_en=_require_text(item.get("label_en"), f"{signal_id}.label_en"),
        severity_raw=severity_raw,
        signal_confidence=signal_confidence,
        match_any=_compile_patterns(item.get("match_any", ()), signal_id, "match_any"),
        topic_any=_compile_patterns(item.get("topic_any", ()), signal_id, "topic_any"),
        protection_any=_compile_patterns(
            item.get("protection_any", ()),
            signal_id,
            "protection_any",
        ),
    )
    _validate_rule(rule)
    return rule


def _validate_rule_set(rule_set: SignalRuleSet) -> None:
    seen_ids: set[str] = set()
    for rule in rule_set.rules:
        if rule.signal_id in seen_ids:
            raise SignalDetectionError(f"duplicate signal rule id: {rule.signal_id}")
        seen_ids.add(rule.signal_id)

    expected_categories = set(EXPECTED_FINANCIAL_CATEGORIES)
    observed_categories = set(rule_set.categories)
    if observed_categories != expected_categories:
        raise SignalDetectionError(
            "signal rule categories mismatch: "
            f"missing={sorted(expected_categories - observed_categories)} "
            f"extra={sorted(observed_categories - expected_categories)}"
        )
    for category, counts in rule_set.kind_counts_by_category.items():
        for kind in EXPECTED_RULE_KINDS:
            if counts[kind] != 1:
                raise SignalDetectionError(
                    f"{category}: expected exactly one {kind} rule, got {counts[kind]}"
                )


def _validate_rule(rule: SignalRule) -> None:
    if not rule.signal_id.startswith("RS-"):
        raise SignalDetectionError(f"{rule.signal_id}: signal_id must start with RS-")
    if rule.category not in EXPECTED_FINANCIAL_CATEGORIES:
        raise SignalDetectionError(f"{rule.signal_id}: unknown F1-F9 category {rule.category}")
    if rule.kind not in EXPECTED_RULE_KINDS:
        raise SignalDetectionError(f"{rule.signal_id}: invalid kind {rule.kind}")
    _require_fraction(rule.severity_raw, f"{rule.signal_id}.severity_raw")
    _require_fraction(rule.signal_confidence, f"{rule.signal_id}.signal_confidence")
    if rule.kind == PRESENCE_KIND and not rule.match_any:
        raise SignalDetectionError(f"{rule.signal_id}: presence rule needs match_any")
    if rule.kind == MISSING_PROTECTION_KIND:
        if not rule.topic_any:
            raise SignalDetectionError(f"{rule.signal_id}: missing rule needs topic_any")
        if not rule.protection_any:
            raise SignalDetectionError(f"{rule.signal_id}: missing rule needs protection_any")


def _risk_signal_from_rule(
    rule: SignalRule,
    *,
    clause: Clause,
    records: Sequence[AuthorityRetrievedRecord],
) -> RiskSignal:
    eligibility = evaluate_signal_eligibility(
        rule.signal_id,
        records,
        risk_categories=(rule.category,),
        raw_contribution=rule.severity_raw,
    )
    grounding_ids = (
        eligibility.scoring_evidence_ids if eligibility.score_eligible else None
    )
    return RiskSignal(
        signal_id=rule.signal_id,
        clause_id=clause.clause_id,
        risk_category=rule.risk_category,
        detector=DetectorType.RULE,
        fired=True,
        score_eligible=eligibility.score_eligible,
        practice_reference=eligibility.practice_reference,
        signal_confidence=rule.signal_confidence,
        is_missing_protection=rule.is_missing_protection,
        grounding_evidence_ids=grounding_ids,
        severity_raw=rule.severity_raw,
    )


def _records_for_category(
    records: Sequence[AuthorityRetrievedRecord],
    category: str,
) -> tuple[AuthorityRetrievedRecord, ...]:
    return tuple(
        record
        for record in records
        if any(
            _same_category(record_category, category)
            for record_category in record.risk_categories
        )
    )


def _same_category(record_category: str, rule_category: str) -> bool:
    cleaned = str(record_category).strip()
    if cleaned == rule_category:
        return True
    short = rule_category.split("_", maxsplit=1)[0]
    return cleaned == short or cleaned.startswith(f"{short}_")


def _clause_text(clause: Clause) -> str:
    parts = [clause.heading_ko or "", clause.text_ko, clause.text_en_gloss or ""]
    return "\n".join(part for part in parts if part.strip())


def _matches_any(patterns: Sequence[re.Pattern[str]], text: str) -> bool:
    return any(pattern.search(text) is not None for pattern in patterns)


def _compile_patterns(values: Any, signal_id: str, field_name: str) -> tuple[re.Pattern[str], ...]:
    patterns: list[re.Pattern[str]] = []
    for idx, value in enumerate(_optional_sequence(values), start=1):
        pattern_text = _require_text(value, f"{signal_id}.{field_name}[{idx}]")
        try:
            patterns.append(re.compile(pattern_text, re.IGNORECASE))
        except re.error as exc:
            raise SignalDetectionError(
                f"{signal_id}.{field_name}[{idx}]: invalid regex {pattern_text!r}: {exc}"
            ) from exc
    return tuple(patterns)


def _heuristic_value(value: Any, field_name: str) -> float:
    payload = _require_mapping(value, field_name)
    if payload.get("heuristic") is not True:
        raise SignalDetectionError(f"{field_name}: heuristic must be true")
    number = payload.get("value")
    if not isinstance(number, int | float):
        raise SignalDetectionError(f"{field_name}.value must be numeric")
    resolved = float(number)
    _require_fraction(resolved, field_name)
    return resolved


def _read_yaml_mapping(path: Path) -> Mapping[str, Any]:
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SignalDetectionError(f"signal rule config not found: {path}") from exc
    return _require_mapping(payload, path.as_posix())


def _require_mapping(value: Any, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise SignalDetectionError(f"{field_name} must be a mapping")
    return value


def _require_sequence(value: Any, field_name: str) -> Sequence[Any]:
    if isinstance(value, str) or not isinstance(value, Sequence):
        raise SignalDetectionError(f"{field_name} must be a sequence")
    return value


def _optional_sequence(value: Any) -> Sequence[Any]:
    if value in (None, ""):
        return ()
    return _require_sequence(value, "pattern list")


def _require_text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SignalDetectionError(f"{field_name} must be nonblank text")
    return value.strip()


def _require_fraction(value: float, field_name: str) -> None:
    if value < 0.0 or value > 1.0:
        raise SignalDetectionError(f"{field_name} must be between 0 and 1")

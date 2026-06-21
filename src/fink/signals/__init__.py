"""Deterministic rule-based risk signals for FInk clauses."""

from fink.signals.engine import (
    DEFAULT_SIGNAL_RULES_PATH,
    SignalDetectionError,
    SignalRule,
    SignalRuleCoverageReport,
    SignalRuleSet,
    RuleBasedSignalDetector,
    detect_clause_signals,
    detect_signals_from_clauses,
    load_signal_rules,
    signal_rule_tests,
)

__all__ = [
    "DEFAULT_SIGNAL_RULES_PATH",
    "SignalDetectionError",
    "SignalRule",
    "SignalRuleCoverageReport",
    "SignalRuleSet",
    "RuleBasedSignalDetector",
    "detect_clause_signals",
    "detect_signals_from_clauses",
    "load_signal_rules",
    "signal_rule_tests",
]

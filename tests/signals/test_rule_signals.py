from __future__ import annotations

import importlib
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


GROUNDING = _load_module("fink.grounding")
SCHEMAS = _load_module("fink.schemas")
SIGNALS = _load_module("fink.signals")


PRESENCE_FIXTURES = {
    "RS-F1-PRESENCE-AUDIT-BLOCK": (
        "F1_SETTLEMENT_AND_AUDIT",
        "정산 내역은 제공하지 않으며 감사권은 인정하지 않는다.",
    ),
    "RS-F2-PRESENCE-OPEN-ENDED-DEDUCTIONS": (
        "F2_REVENUE_AND_DEDUCTIONS",
        "플랫폼은 기타 비용 및 회사가 정하는 공제를 차감할 수 있다.",
    ),
    "RS-F3-PRESENCE-PAYMENT-TIMING-OPAQUE": (
        "F3_PAYMENT_AND_CASHFLOW",
        "지급시기는 회사가 추후 정하는 일정에 따른다.",
    ),
    "RS-F4-PRESENCE-RECOUPMENT-OPAQUE": (
        "F4_MG_AND_RECOUPMENT",
        "선급금은 모든 매출에서 전액 회수될 때까지 우선 회수한다.",
    ),
    "RS-F5-PRESENCE-BROAD-IP-TRANSFER": (
        "F5_IP_MONETIZATION",
        "저작권 및 2차적저작물 권리는 회사에 포괄 양도된다.",
    ),
    "RS-F6-PRESENCE-LONG-EXCLUSIVITY-AUTO-RENEWAL": (
        "F6_TERM_EXCLUSIVITY_AND_OPPORTUNITY_COST",
        "독점 계약은 3년 동안 유지되며 자동 갱신된다.",
    ),
    "RS-F7-PRESENCE-UNCAPPED-LIABILITY": (
        "F7_TERMINATION_LIABILITY_AND_PENALTIES",
        "작가는 모든 손해배상을 전액 부담한다.",
    ),
    "RS-F8-PRESENCE-UNPAID-SCOPE-CREEP": (
        "F8_SCOPE_CREEP_AND_PRODUCTION_COST",
        "회사는 무제한 수정을 추가 비용 없이 요구할 수 있다.",
    ),
    "RS-F9-PRESENCE-EVIDENCE-PRIVACY-GAP": (
        "F9_E_CONTRACT_PRIVACY_AND_EVIDENCE",
        "전자계약 원본과 증거는 보관하지 않고 삭제할 수 있다.",
    ),
}


MISSING_FIXTURES = {
    "RS-F1-MISSING-SETTLEMENT-RECORDS": (
        "F1_SETTLEMENT_AND_AUDIT",
        "정산은 회사 내부 기준에 따른다.",
    ),
    "RS-F2-MISSING-REVENUE-BASE": (
        "F2_REVENUE_AND_DEDUCTIONS",
        "수익 배분 후 필요한 비용을 공제한다.",
    ),
    "RS-F3-MISSING-PAYMENT-DEADLINE": (
        "F3_PAYMENT_AND_CASHFLOW",
        "정산금은 지급 대상이 되면 지급한다.",
    ),
    "RS-F4-MISSING-RECOUPMENT-LIMITS": (
        "F4_MG_AND_RECOUPMENT",
        "선급금은 매출에서 회수한다.",
    ),
    "RS-F5-MISSING-SECONDARY-RIGHTS-SHARE": (
        "F5_IP_MONETIZATION",
        "2차적저작물 사업은 회사가 진행할 수 있다.",
    ),
    "RS-F6-MISSING-EXIT-RIGHT": (
        "F6_TERM_EXCLUSIVITY_AND_OPPORTUNITY_COST",
        "작가는 독점 계약 기간 동안 다른 플랫폼에 제공하지 않는다.",
    ),
    "RS-F7-MISSING-LIABILITY-CAP": (
        "F7_TERMINATION_LIABILITY_AND_PENALTIES",
        "해지 또는 손해배상 사유가 발생하면 회사가 정산에서 공제한다.",
    ),
    "RS-F8-MISSING-REVISION-LIMITS": (
        "F8_SCOPE_CREEP_AND_PRODUCTION_COST",
        "작가는 검수 의견에 따라 수정 및 추가 작업을 수행한다.",
    ),
    "RS-F9-MISSING-EVIDENCE-RETENTION": (
        "F9_E_CONTRACT_PRIVACY_AND_EVIDENCE",
        "전자계약 및 개인정보 처리는 플랫폼 정책에 따른다.",
    ),
}


def _clause(clause_id: str, text: str) -> Any:
    return SCHEMAS.Clause(
        clause_id=clause_id,
        clause_index=0,
        text_ko=text,
        source_span_ids=(f"span-{clause_id}",),
        seg_confidence=0.94,
    )


def _record(
    record_id: str,
    category: str,
    *,
    authority_tier: str = "A1",
    record_type: str = "evidence",
    practice_reference: bool = False,
) -> Any:
    return GROUNDING.AuthorityRetrievedRecord(
        rank=1,
        retrieval_score=1.0,
        record_id=record_id,
        record_type=record_type,
        title=record_id,
        text="synthetic signal grounding fixture",
        source_id=f"{authority_tier}-SIGNAL-TEST",
        source_ids=(f"{authority_tier}-SIGNAL-TEST",),
        authority_tier=authority_tier,
        verification_status="UNVERIFIED",
        risk_categories=(category,),
        score_eligible=authority_tier in {"A0", "A1", "A2"} and record_type == "evidence",
        practice_reference=practice_reference,
        matched_terms=("synthetic",),
    )


def _signal_by_id(signals: tuple[Any, ...]) -> dict[str, Any]:
    return {signal.signal_id: signal for signal in signals}


class RuleSignalTests(unittest.TestCase):
    def test_signal_rule_tests_validates_f1_f9_presence_and_missing_coverage(self) -> None:
        report = SIGNALS.signal_rule_tests()

        self.assertTrue(report.ok, report.as_dict())
        self.assertEqual(report.rule_count, 18)
        self.assertEqual(len(report.categories), 9)
        for counts in report.kind_counts_by_category.values():
            self.assertEqual(counts["presence"], 1)
            self.assertEqual(counts["missing_protection"], 1)

    def test_signals_fire_on_labeled_synthetic_presence_clauses(self) -> None:
        clauses = [
            _clause(f"presence-{idx}", text)
            for idx, (_category, text) in enumerate(PRESENCE_FIXTURES.values(), start=1)
        ]
        records = tuple(
            _record(f"EV-{category}", category)
            for category, _text in PRESENCE_FIXTURES.values()
        )

        signals = SIGNALS.detect_signals_from_clauses(clauses, grounding_records=records)
        by_id = _signal_by_id(signals)

        for signal_id, (category, _text) in PRESENCE_FIXTURES.items():
            with self.subTest(signal_id=signal_id):
                signal = by_id[signal_id]
                rule = SIGNALS.load_signal_rules().rule_by_id(signal_id)
                self.assertTrue(signal.fired)
                self.assertTrue(signal.score_eligible)
                self.assertFalse(signal.is_missing_protection)
                self.assertEqual(signal.risk_category.value, category.split("_", maxsplit=1)[0])
                self.assertEqual(signal.severity_raw, rule.severity_raw)
                self.assertEqual(signal.grounding_evidence_ids, (f"EV-{category}",))

    def test_missing_protection_signals_fire_on_labeled_synthetic_clauses(self) -> None:
        clauses = [
            _clause(f"missing-{idx}", text)
            for idx, (_category, text) in enumerate(MISSING_FIXTURES.values(), start=1)
        ]
        records = tuple(
            _record(f"EV-{category}", category, authority_tier="A2")
            for category, _text in MISSING_FIXTURES.values()
        )

        signals = SIGNALS.detect_signals_from_clauses(clauses, grounding_records=records)
        by_id = _signal_by_id(signals)

        for signal_id, (category, _text) in MISSING_FIXTURES.items():
            with self.subTest(signal_id=signal_id):
                signal = by_id[signal_id]
                self.assertTrue(signal.fired)
                self.assertTrue(signal.is_missing_protection)
                self.assertTrue(signal.score_eligible)
                self.assertEqual(signal.grounding_evidence_ids, (f"EV-{category}",))

    def test_missing_protection_requires_a0_a2_grounding_to_score(self) -> None:
        clause = _clause("missing-grounding", "정산은 회사 내부 기준에 따른다.")

        ungrounded = SIGNALS.detect_clause_signals(clause)
        ungrounded_signal = _signal_by_id(ungrounded)["RS-F1-MISSING-SETTLEMENT-RECORDS"]
        self.assertTrue(ungrounded_signal.fired)
        self.assertFalse(ungrounded_signal.score_eligible)
        self.assertFalse(ungrounded_signal.practice_reference)
        self.assertIsNone(ungrounded_signal.grounding_evidence_ids)

        bc_record = _record(
            "KC-F1-PRACTICE",
            "F1_SETTLEMENT_AND_AUDIT",
            authority_tier="B",
            record_type="knowledge_card",
            practice_reference=True,
        )
        bc_only = SIGNALS.detect_clause_signals(clause, grounding_records=(bc_record,))
        bc_signal = _signal_by_id(bc_only)["RS-F1-MISSING-SETTLEMENT-RECORDS"]
        self.assertFalse(bc_signal.score_eligible)
        self.assertTrue(bc_signal.practice_reference)
        self.assertIsNone(bc_signal.grounding_evidence_ids)

        a1_record = _record("EV-F1-GROUNDED", "F1_SETTLEMENT_AND_AUDIT")
        grounded = SIGNALS.detect_clause_signals(clause, grounding_records=(a1_record,))
        grounded_signal = _signal_by_id(grounded)["RS-F1-MISSING-SETTLEMENT-RECORDS"]
        self.assertTrue(grounded_signal.score_eligible)
        self.assertFalse(grounded_signal.practice_reference)
        self.assertEqual(grounded_signal.grounding_evidence_ids, ("EV-F1-GROUNDED",))

    def test_unrelated_category_grounding_does_not_make_signal_score_eligible(self) -> None:
        clause = _clause("payment-missing", "정산금은 지급 대상이 되면 지급한다.")
        unrelated_record = _record("EV-F2-ONLY", "F2_REVENUE_AND_DEDUCTIONS")

        signals = SIGNALS.detect_clause_signals(clause, grounding_records=(unrelated_record,))
        signal = _signal_by_id(signals)["RS-F3-MISSING-PAYMENT-DEADLINE"]

        self.assertTrue(signal.fired)
        self.assertFalse(signal.score_eligible)
        self.assertIsNone(signal.grounding_evidence_ids)

    def test_signal_severity_comes_from_loaded_rule_set(self) -> None:
        rule_set = SIGNALS.load_signal_rules()
        rules = tuple(
            replace(rule, severity_raw=0.31)
            if rule.signal_id == "RS-F2-PRESENCE-OPEN-ENDED-DEDUCTIONS"
            else rule
            for rule in rule_set.rules
        )
        detector = SIGNALS.RuleBasedSignalDetector(replace(rule_set, rules=rules))
        clause = _clause(
            "config-severity",
            "플랫폼은 기타 비용 및 회사가 정하는 공제를 차감할 수 있다.",
        )
        record = _record("EV-F2-GROUNDED", "F2_REVENUE_AND_DEDUCTIONS")

        signals = detector.detect_clause(clause, grounding_records=(record,))
        signal = _signal_by_id(signals)["RS-F2-PRESENCE-OPEN-ENDED-DEDUCTIONS"]

        self.assertEqual(signal.severity_raw, 0.31)
        self.assertTrue(signal.score_eligible)


if __name__ == "__main__":
    unittest.main()

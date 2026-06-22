from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from fink.schemas import Clause


VERIFICATION_SECTION_TITLE_KO = "상대방·지급 경로 확인 신호"
VERIFICATION_SECTION_TITLE_EN = "Counterparty and payment-route verification signals"
VERIFICATION_SUPPORT_STATE = "local_corpus_supported"
VERIFICATION_SCORE_CONTRIBUTION = 0
VERIFICATION_MODEL_PATH = "local_corpus_supported_verification_rules"

PRACTICE_SUPPORT_TIERS = frozenset({"B", "C", "B/C"})
SUPPORT_CHUNK_TYPES = ("glossary_term", "knowledge_card", "checklist_item")


@dataclass(frozen=True)
class VerificationRule:
    signal_id: str
    signal_type: str
    label_ko: str
    label_en: str
    instruction_ko: str
    instruction_en: str
    support_query: str
    support_markers: tuple[str, ...]
    patterns: tuple[re.Pattern[str], ...]

    def fires(self, text: str) -> bool:
        return any(pattern.search(text) is not None for pattern in self.patterns)


@dataclass(frozen=True)
class VerificationSupportRecord:
    record_id: str
    record_type: str
    title: str
    authority_tier: str
    source_id: str
    risk_categories: tuple[str, ...]
    matched_terms: tuple[str, ...]

    @classmethod
    def from_result(cls, result: Any) -> "VerificationSupportRecord":
        chunk = result.chunk
        return cls(
            record_id=str(chunk.chunk_id),
            record_type=str(chunk.chunk_type),
            title=str(chunk.title),
            authority_tier=str(chunk.authority_tier),
            source_id=str(chunk.source_id),
            risk_categories=tuple(str(item) for item in chunk.risk_categories),
            matched_terms=tuple(str(item) for item in result.matched_terms),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "record_type": self.record_type,
            "title": self.title,
            "authority_tier": self.authority_tier,
            "source_id": self.source_id,
            "risk_categories": list(self.risk_categories),
            "matched_terms": list(self.matched_terms),
        }


@dataclass(frozen=True)
class VerificationSignal:
    signal_id: str
    signal_type: str
    clause_id: str
    exact_excerpt: str
    label_ko: str
    label_en: str
    instruction_ko: str
    instruction_en: str
    support_records: tuple[VerificationSupportRecord, ...]
    support_state: str = VERIFICATION_SUPPORT_STATE
    score_contribution: int = VERIFICATION_SCORE_CONTRIBUTION
    separate_from_review_priority_score: bool = True

    @property
    def support_record_ids(self) -> tuple[str, ...]:
        return tuple(record.record_id for record in self.support_records)

    @property
    def support_authority_tiers(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(record.authority_tier for record in self.support_records))

    @property
    def support_record_types(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(record.record_type for record in self.support_records))

    def as_dict(self) -> dict[str, Any]:
        return {
            "signal_id": self.signal_id,
            "signal_type": self.signal_type,
            "clause_id": self.clause_id,
            "exact_excerpt": self.exact_excerpt,
            "label_ko": self.label_ko,
            "label_en": self.label_en,
            "instruction_ko": self.instruction_ko,
            "instruction_en": self.instruction_en,
            "support_state": self.support_state,
            "support_record_ids": list(self.support_record_ids),
            "support_authority_tiers": list(self.support_authority_tiers),
            "support_record_types": list(self.support_record_types),
            "score_contribution": self.score_contribution,
            "separate_from_review_priority_score": (
                self.separate_from_review_priority_score
            ),
            "support_records": [record.as_dict() for record in self.support_records],
        }


VERIFICATION_RULES: tuple[VerificationRule, ...] = (
    VerificationRule(
        signal_id="VFY-COUNTERPARTY-IDENTITY",
        signal_type="counterparty",
        label_ko="상대방 정보 확인 필요",
        label_en="Counterparty information check needed",
        instruction_ko=(
            "서명 전에 회사명, 사업자등록번호, 대표자명, 공식 연락처를 "
            "계약서 밖의 독립된 경로로 확인하세요."
        ),
        instruction_en=(
            "Before signing, independently verify the company name, business "
            "registration, representative, and official contact outside the contract."
        ),
        support_query="계약 당사자 계약주체 상대방 위험 법인 주소 보증",
        support_markers=(
            "CONTRACT_PARTY",
            "COUNTERPARTY_RISK",
            "계약 당사자",
            "계약주체",
            "상대방 위험",
            "정확한 법인",
        ),
        patterns=(
            re.compile(
                r"(?:사업자\s*등록\s*번호|법인\s*명|상호|대표자|공식\s*(?:연락처|이메일))"
                r"[^.\n]{0,28}(?:없|미기재|다르|불일치|추후|별도)",
                re.IGNORECASE,
            ),
            re.compile(
                r"(?:브랜드명|필명|개인\s*명의|메신저|카카오톡)"
                r"[^.\n]{0,24}(?:계약|서명|연락|진행)",
                re.IGNORECASE,
            ),
            re.compile(
                r"(?:company\s+name|business\s+registration|official\s+contact)"
                r"[^.\n]{0,36}(?:missing|not\s+provided|different|later)",
                re.IGNORECASE,
            ),
        ),
    ),
    VerificationRule(
        signal_id="VFY-PAYMENT-ROUTE",
        signal_type="payment_route",
        label_ko="지급 경로 확인 필요",
        label_en="Payment-route check needed",
        instruction_ko=(
            "이체 또는 송금 전에 지급 계좌 명의가 계약 상대방과 일치하는지, "
            "공식 청구서·정산서에 적힌 계좌인지 독립적으로 확인하세요."
        ),
        instruction_en=(
            "Before transferring money, independently verify that the payment "
            "account holder matches the counterparty and appears on an official "
            "invoice or settlement statement."
        ),
        support_query="계좌 입금 지급 계약서 개인정보 정산서",
        support_markers=(
            "PERSONAL_DATA",
            "계좌",
            "입금",
            "지급",
            "정산서",
            "account",
            "payment",
        ),
        patterns=(
            re.compile(
                r"(?:개인|제3자|타인|별도|외부)\s*(?:명의\s*)?(?:계좌|입금|송금)",
                re.IGNORECASE,
            ),
            re.compile(
                r"(?:계좌\s*명의|입금\s*계좌|송금\s*계좌)"
                r"[^.\n]{0,28}(?:다르|불일치|개인|제3자|별도|추후)",
                re.IGNORECASE,
            ),
            re.compile(
                r"(?:personal|third[- ]party|different)\s+(?:bank\s+)?account",
                re.IGNORECASE,
            ),
        ),
    ),
)


def detect_verification_signals(
    clauses: Sequence[Clause],
    *,
    support_index: Any | None = None,
) -> tuple[VerificationSignal, ...]:
    """Detect pre-signing verification prompts supported by the local corpus.

    These signals are never scoring evidence. They only surface a separate
    counterparty/payment-route check when the clause pattern is present and the
    local B/C/X-category corpus contains a matching practice-support concept.
    """

    if not clauses:
        return ()

    candidates: list[tuple[Clause, VerificationRule]] = []
    for clause in clauses:
        text = _clause_text(clause)
        if not text.strip():
            continue
        candidates.extend(
            (clause, rule) for rule in VERIFICATION_RULES if rule.fires(text)
        )
    if not candidates:
        return ()

    index = support_index or _load_support_index()
    candidate_rules: list[VerificationRule] = []
    seen_rule_ids: set[str] = set()
    for _clause, rule in candidates:
        if rule.signal_id in seen_rule_ids:
            continue
        seen_rule_ids.add(rule.signal_id)
        candidate_rules.append(rule)
    support_by_rule = {
        rule.signal_id: _support_records_for_rule(index, rule) for rule in candidate_rules
    }
    signals: list[VerificationSignal] = []
    seen: set[tuple[str, str]] = set()
    for clause, rule in candidates:
        support_records = support_by_rule[rule.signal_id]
        if not support_records:
            continue
        key = (rule.signal_id, clause.clause_id)
        if key in seen:
            continue
        seen.add(key)
        signals.append(
            VerificationSignal(
                signal_id=rule.signal_id,
                signal_type=rule.signal_type,
                clause_id=clause.clause_id,
                exact_excerpt=_exact_excerpt(clause),
                label_ko=rule.label_ko,
                label_en=rule.label_en,
                instruction_ko=rule.instruction_ko,
                instruction_en=rule.instruction_en,
                support_records=support_records,
            )
        )
    return tuple(signals)


def verification_payload(
    signals: Sequence[VerificationSignal],
) -> dict[str, Any]:
    """Return a JSON-safe, non-scoring verification section."""

    return {
        "section_title": {
            "ko": VERIFICATION_SECTION_TITLE_KO,
            "en": VERIFICATION_SECTION_TITLE_EN,
            "en_generated": True,
        },
        "section_hint": {
            "ko": (
                "이 영역은 계약상 금융 검토 점수와 별도로, 서명·이체 전 "
                "상대방과 지급 경로를 독립적으로 확인하라는 신호만 표시합니다."
            ),
            "en": (
                "This area is separate from the review-priority score and only "
                "prompts independent counterparty and payment-route checks before "
                "signing or transferring money."
            ),
            "en_generated": True,
        },
        "signal_count": len(tuple(signals)),
        "separate_from_review_priority_score": True,
        "score_contribution": VERIFICATION_SCORE_CONTRIBUTION,
        "model_path": VERIFICATION_MODEL_PATH,
        "signals": [_signal_payload(signal) for signal in signals],
    }


def empty_verification_payload() -> dict[str, Any]:
    return verification_payload(())


def _signal_payload(signal: VerificationSignal) -> dict[str, Any]:
    return {
        "signal_id": signal.signal_id,
        "signal_type": signal.signal_type,
        "label": {"ko": signal.label_ko, "en": signal.label_en},
        "source": {
            "clause_id": signal.clause_id,
            "exact_excerpt": signal.exact_excerpt,
        },
        "instruction": {
            "ko": signal.instruction_ko,
            "en": signal.instruction_en,
        },
        "support": {
            "state": signal.support_state,
            "record_ids": list(signal.support_record_ids),
            "authority_tiers": list(signal.support_authority_tiers),
            "record_types": list(signal.support_record_types),
        },
        "score_contribution": signal.score_contribution,
        "separate_from_review_priority_score": (
            signal.separate_from_review_priority_score
        ),
        "not_financial_loss_estimate": True,
    }


def _load_support_index() -> Any:
    from fink.retrieval import load_or_build_retrieval_index

    return load_or_build_retrieval_index()


def _support_records_for_rule(
    index: Any,
    rule: VerificationRule,
) -> tuple[VerificationSupportRecord, ...]:
    results = index.query(
        rule.support_query,
        k=12,
        chunk_types=SUPPORT_CHUNK_TYPES,
        authority_tiers=tuple(PRACTICE_SUPPORT_TIERS),
    )
    selected: list[VerificationSupportRecord] = []
    seen: set[str] = set()
    for result in results:
        chunk = result.chunk
        if chunk.chunk_id in seen:
            continue
        if not _contains_support_marker(chunk, rule.support_markers):
            continue
        seen.add(chunk.chunk_id)
        selected.append(VerificationSupportRecord.from_result(result))
        if len(selected) >= 3:
            break
    return tuple(selected)


def _contains_support_marker(chunk: Any, markers: tuple[str, ...]) -> bool:
    haystack = " ".join(
        str(part)
        for part in (
            chunk.chunk_id,
            chunk.canonical_id,
            chunk.title,
            chunk.text,
            " ".join(chunk.risk_categories),
        )
    ).casefold()
    return any(marker.casefold() in haystack for marker in markers)


def _clause_text(clause: Clause) -> str:
    return "\n".join(
        part
        for part in (clause.heading_ko or "", clause.text_ko, clause.text_en_gloss or "")
        if part
    )


def _exact_excerpt(clause: Clause) -> str:
    return " ".join(_clause_text(clause).split())

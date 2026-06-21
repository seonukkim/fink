from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from fink.retrieval.engine import (
    AUTHORITY_SORT_ORDER,
    PRACTICE_AUTHORITY_TIERS,
    SCORING_AUTHORITY_TIERS,
    LocalBM25Index,
    RetrievalChunk,
    RetrievalResult,
)


DEFAULT_EXPLANATION_CHUNK_TYPES = ("knowledge_card",)
DEFAULT_GROUNDING_CHUNK_TYPES = ("evidence",)
SOURCE_YEAR_KEYS = (
    "source_year",
    "form_year",
    "effective_year",
    "publication_year",
    "published_year",
    "retrieved_year",
    "year",
)
CONFLICT_GROUP_KEYS = ("conflict_group", "overlap_key", "conflict_key")
YEAR_RE = re.compile(r"(20\d{2}|19\d{2})")
PRECEDENCE_RULE = "On overlapping webtoon forms, newer source year has precedence; 2025 > 2018."
FINANCIAL_RISK_CATEGORY_PREFIXES = tuple(f"F{index}" for index in range(1, 10))


class AuthorityGroundingError(ValueError):
    """Raised when authority-gated grounding violates FInk's retrieval contract."""


@dataclass(frozen=True)
class AuthorityRetrievedRecord:
    """One returned retrieval record with authority tags promoted to top level."""

    rank: int
    retrieval_score: float
    record_id: str
    record_type: str
    title: str
    text: str
    source_id: str
    source_ids: tuple[str, ...]
    authority_tier: str
    verification_status: str
    risk_categories: tuple[str, ...]
    score_eligible: bool
    practice_reference: bool
    matched_terms: tuple[str, ...]
    conflict_group: str = ""
    precedence_year: int | None = None
    precedence_rank: int | None = None
    precedence_rule: str = ""
    metadata: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        if not self.record_id.strip():
            raise AuthorityGroundingError("record_id must be nonblank")
        if not self.source_id.strip():
            raise AuthorityGroundingError(f"{self.record_id}: source_id is required")
        if not self.authority_tier.strip():
            raise AuthorityGroundingError(f"{self.record_id}: authority_tier is required")
        if not self.verification_status.strip():
            raise AuthorityGroundingError(
                f"{self.record_id}: verification_status is required"
            )

    @property
    def is_grounding(self) -> bool:
        return (
            self.record_type == "evidence"
            and self.authority_tier in SCORING_AUTHORITY_TIERS
        )

    @property
    def is_explanation(self) -> bool:
        return self.authority_tier in PRACTICE_AUTHORITY_TIERS

    def as_dict(self) -> dict[str, Any]:
        return {
            "rank": self.rank,
            "retrieval_score": self.retrieval_score,
            "record_id": self.record_id,
            "record_type": self.record_type,
            "title": self.title,
            "text": self.text,
            "source_id": self.source_id,
            "source_ids": list(self.source_ids),
            "authority_tier": self.authority_tier,
            "verification_status": self.verification_status,
            "risk_categories": list(self.risk_categories),
            "score_eligible": self.score_eligible,
            "practice_reference": self.practice_reference,
            "matched_terms": list(self.matched_terms),
            "conflict_group": self.conflict_group,
            "precedence_year": self.precedence_year,
            "precedence_rank": self.precedence_rank,
            "precedence_rule": self.precedence_rule,
            "metadata": dict(self.metadata or {}),
        }


@dataclass(frozen=True)
class SignalEligibility:
    """Authority-gated score eligibility for one risk signal."""

    signal_id: str
    risk_categories: tuple[str, ...]
    scoring_evidence_ids: tuple[str, ...]
    practice_reference_ids: tuple[str, ...]
    ignored_reference_ids: tuple[str, ...]
    score_eligible: bool
    practice_reference: bool
    raw_contribution: float
    score_contribution: float

    def __post_init__(self) -> None:
        if not self.signal_id.strip():
            raise AuthorityGroundingError("signal_id must be nonblank")
        if self.score_eligible and not self.scoring_evidence_ids:
            raise AuthorityGroundingError(
                f"{self.signal_id}: score_eligible requires A0-A2 evidence"
            )
        if self.practice_reference and self.score_eligible:
            raise AuthorityGroundingError(
                f"{self.signal_id}: practice_reference signals must not score"
            )
        if not self.score_eligible and self.score_contribution != 0:
            raise AuthorityGroundingError(
                f"{self.signal_id}: non-eligible signals must contribute 0"
            )

    def as_dict(self) -> dict[str, Any]:
        return {
            "signal_id": self.signal_id,
            "risk_categories": list(self.risk_categories),
            "scoring_evidence_ids": list(self.scoring_evidence_ids),
            "practice_reference_ids": list(self.practice_reference_ids),
            "ignored_reference_ids": list(self.ignored_reference_ids),
            "score_eligible": self.score_eligible,
            "practice_reference": self.practice_reference,
            "raw_contribution": self.raw_contribution,
            "score_contribution": self.score_contribution,
        }


@dataclass(frozen=True)
class ConflictSet:
    """Conflicting source records retained together with explicit precedence."""

    conflict_group: str
    records: tuple[AuthorityRetrievedRecord, ...]
    precedence_rule: str = PRECEDENCE_RULE

    def __post_init__(self) -> None:
        if not self.conflict_group.strip():
            raise AuthorityGroundingError("conflict_group must be nonblank")
        if len(self.records) < 2:
            raise AuthorityGroundingError(
                f"{self.conflict_group}: conflict sets require at least two records"
            )

    @property
    def precedence_order(self) -> tuple[str, ...]:
        return tuple(record.record_id for record in _sort_by_precedence(self.records))

    @property
    def preferred_record_id(self) -> str:
        return self.precedence_order[0]

    def as_dict(self) -> dict[str, Any]:
        return {
            "conflict_group": self.conflict_group,
            "precedence_rule": self.precedence_rule,
            "precedence_order": list(self.precedence_order),
            "preferred_record_id": self.preferred_record_id,
            "records": [record.as_dict() for record in _sort_by_precedence(self.records)],
        }


@dataclass(frozen=True)
class AuthorityRetrievalBundle:
    """Explanation and grounding records returned by the authority-gated retriever."""

    query: str
    explanation_records: tuple[AuthorityRetrievedRecord, ...]
    grounding_records: tuple[AuthorityRetrievedRecord, ...]
    conflict_sets: tuple[ConflictSet, ...] = ()

    @property
    def returned_records(self) -> tuple[AuthorityRetrievedRecord, ...]:
        return (*self.explanation_records, *self.grounding_records)

    def as_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "explanation_records": [
                record.as_dict() for record in self.explanation_records
            ],
            "grounding_records": [record.as_dict() for record in self.grounding_records],
            "conflict_sets": [conflict.as_dict() for conflict in self.conflict_sets],
        }


def authority_gated_retrieval(
    index: LocalBM25Index,
    query_text: str,
    *,
    explanation_k: int = 3,
    grounding_k: int = 3,
    risk_categories: Sequence[str] = (),
    explanation_chunk_types: Sequence[str] = DEFAULT_EXPLANATION_CHUNK_TYPES,
    grounding_chunk_types: Sequence[str] = DEFAULT_GROUNDING_CHUNK_TYPES,
) -> AuthorityRetrievalBundle:
    """Return B/C explanation cards and A0-A2 grounding evidence separately.

    The returned records intentionally keep explanation and grounding apart:
    B/C records may explain and generate questions, while only A0-A2 evidence
    may ground score-eligible signals in later stages.
    """

    if explanation_k <= 0:
        raise ValueError("explanation_k must be > 0")
    if grounding_k <= 0:
        raise ValueError("grounding_k must be > 0")

    explanation_results = index.query(
        query_text,
        k=len(index.documents),
        risk_categories=risk_categories,
        chunk_types=explanation_chunk_types,
        authority_tiers=tuple(PRACTICE_AUTHORITY_TIERS),
    )
    grounding_results = index.query(
        query_text,
        k=len(index.documents),
        risk_categories=risk_categories,
        chunk_types=grounding_chunk_types,
        authority_tiers=tuple(SCORING_AUTHORITY_TIERS),
    )

    explanation = _records_from_results(
        _select_with_conflict_siblings(explanation_results, explanation_k)
    )
    grounding = _records_from_results(
        _select_with_conflict_siblings(grounding_results, grounding_k)
    )
    conflict_sets = _build_conflict_sets((*explanation, *grounding))
    grounding = _apply_precedence_ranks(grounding, conflict_sets)
    explanation = _apply_precedence_ranks(explanation, conflict_sets)
    conflict_sets = _build_conflict_sets((*explanation, *grounding))

    return AuthorityRetrievalBundle(
        query=query_text,
        explanation_records=explanation,
        grounding_records=grounding,
        conflict_sets=conflict_sets,
    )


def evaluate_signal_eligibility(
    signal_id: str,
    records: Sequence[AuthorityRetrievedRecord],
    *,
    risk_categories: Sequence[str] | str = (),
    raw_contribution: float = 0.0,
) -> SignalEligibility:
    """Apply INV-1/AC-AUTH-2 score eligibility to one signal.

    A signal can contribute to review-priority scoring only when an A0-A2
    evidence record grounds it and the signal belongs to a financial F category.
    B/C-only references remain practice references and contribute exactly 0.
    """

    categories = _risk_categories_for_signal(risk_categories, records)
    scoring_evidence_ids: list[str] = []
    practice_reference_ids: list[str] = []
    ignored_reference_ids: list[str] = []

    for record in records:
        if _is_scoring_evidence(record):
            scoring_evidence_ids.append(record.record_id)
        elif record.authority_tier in PRACTICE_AUTHORITY_TIERS:
            practice_reference_ids.append(record.record_id)
        else:
            ignored_reference_ids.append(record.record_id)

    has_financial_category = any(
        _is_financial_risk_category(category) for category in categories
    )
    score_eligible = bool(scoring_evidence_ids and has_financial_category)
    practice_reference = bool(practice_reference_ids and not score_eligible)
    score_contribution = float(raw_contribution) if score_eligible else 0.0

    return SignalEligibility(
        signal_id=signal_id,
        risk_categories=categories,
        scoring_evidence_ids=tuple(scoring_evidence_ids),
        practice_reference_ids=tuple(practice_reference_ids),
        ignored_reference_ids=tuple(ignored_reference_ids),
        score_eligible=score_eligible,
        practice_reference=practice_reference,
        raw_contribution=float(raw_contribution),
        score_contribution=score_contribution,
    )


def eligibility_gate_test(
    eligibilities: SignalEligibility | Sequence[SignalEligibility],
) -> bool:
    """Machine-gate helper for AC-AUTH-2 and SC-AGG-T1."""

    signals = (
        (eligibilities,)
        if isinstance(eligibilities, SignalEligibility)
        else tuple(eligibilities)
    )
    if not signals:
        raise AuthorityGroundingError("AC-AUTH-2 requires at least one signal")

    saw_bc_only_practice_reference = False
    saw_authority_grounded_signal = False
    for signal in signals:
        has_financial_category = any(
            _is_financial_risk_category(category)
            for category in signal.risk_categories
        )
        expected_score_eligible = bool(
            signal.scoring_evidence_ids and has_financial_category
        )
        if signal.score_eligible != expected_score_eligible:
            raise AuthorityGroundingError(
                f"{signal.signal_id}: score_eligible must be true iff "
                "A0-A2 evidence grounds an F-category signal"
            )
        if not signal.score_eligible and signal.score_contribution != 0:
            raise AuthorityGroundingError(
                f"{signal.signal_id}: non-eligible signals must contribute 0"
            )
        if (
            signal.practice_reference_ids
            and not signal.scoring_evidence_ids
            and not signal.score_eligible
        ):
            saw_bc_only_practice_reference = True
            if not signal.practice_reference:
                raise AuthorityGroundingError(
                    f"{signal.signal_id}: B/C-only signals must be practice references"
                )
        if signal.score_eligible:
            saw_authority_grounded_signal = True

    if not saw_bc_only_practice_reference:
        raise AuthorityGroundingError("AC-AUTH-2 requires a B/C-only zero case")
    if not saw_authority_grounded_signal:
        raise AuthorityGroundingError("AC-AUTH-2 requires an A0-A2 grounded case")
    return True


def authority_tag_present(bundle: AuthorityRetrievalBundle) -> bool:
    """Machine-gate helper for AC-AUTH-1."""

    if not bundle.explanation_records:
        raise AuthorityGroundingError("AC-AUTH-1 requires at least one B/C explanation card")
    if not bundle.grounding_records:
        raise AuthorityGroundingError("AC-AUTH-1 requires at least one A0-A2 grounding record")

    for record in bundle.returned_records:
        if not (record.source_id and record.authority_tier and record.verification_status):
            raise AuthorityGroundingError(
                f"{record.record_id}: missing source_id/authority_tier/verification_status"
            )
    for record in bundle.explanation_records:
        if not record.is_explanation or record.score_eligible:
            raise AuthorityGroundingError(
                f"{record.record_id}: explanation record must be B/C and non-scoring"
            )
    for record in bundle.grounding_records:
        if not record.is_grounding or not record.score_eligible:
            raise AuthorityGroundingError(
                f"{record.record_id}: grounding record must be A0-A2 evidence"
            )
    return True


def conflict_preserved_test(bundle: AuthorityRetrievalBundle) -> bool:
    """Machine-gate helper for AC-AUTH-3."""

    if not bundle.conflict_sets:
        raise AuthorityGroundingError("AC-AUTH-3 requires at least one preserved conflict set")

    returned_ids = {record.record_id for record in bundle.returned_records}
    saw_2025_over_2018 = False
    for conflict in bundle.conflict_sets:
        conflict_ids = {record.record_id for record in conflict.records}
        if not conflict_ids <= returned_ids:
            missing = ", ".join(sorted(conflict_ids - returned_ids))
            raise AuthorityGroundingError(
                f"{conflict.conflict_group}: conflict record(s) missing from returned records: "
                + missing
            )
        ordered = _sort_by_precedence(conflict.records)
        years = [record.precedence_year for record in ordered]
        if 2025 in years and 2018 in years:
            saw_2025_over_2018 = years.index(2025) < years.index(2018)
        if ordered[0].precedence_rank != 1:
            raise AuthorityGroundingError(
                f"{conflict.conflict_group}: preferred record must have precedence_rank=1"
            )

    if not saw_2025_over_2018:
        raise AuthorityGroundingError("AC-AUTH-3 requires explicit 2025 > 2018 precedence")
    return True


def _records_from_results(
    results: Sequence[RetrievalResult],
) -> tuple[AuthorityRetrievedRecord, ...]:
    return tuple(_record_from_result(result) for result in results)


def _record_from_result(result: RetrievalResult) -> AuthorityRetrievedRecord:
    chunk = result.chunk
    return AuthorityRetrievedRecord(
        rank=result.rank,
        retrieval_score=result.score,
        record_id=chunk.chunk_id,
        record_type=chunk.chunk_type,
        title=chunk.title,
        text=chunk.text,
        source_id=chunk.source_id,
        source_ids=chunk.source_ids,
        authority_tier=chunk.authority_tier,
        verification_status=chunk.verification_status,
        risk_categories=chunk.risk_categories,
        score_eligible=chunk.score_eligible,
        practice_reference=chunk.practice_reference,
        matched_terms=result.matched_terms,
        conflict_group=_conflict_group(chunk),
        precedence_year=_source_year(chunk),
        precedence_rule=PRECEDENCE_RULE if _conflict_group(chunk) else "",
        metadata=dict(chunk.metadata),
    )


def _risk_categories_for_signal(
    risk_categories: Sequence[str] | str,
    records: Sequence[AuthorityRetrievedRecord],
) -> tuple[str, ...]:
    categories = _tuple_text(risk_categories)
    if categories:
        return categories

    seen: set[str] = set()
    inferred: list[str] = []
    for record in records:
        for category in record.risk_categories:
            cleaned = str(category).strip()
            if cleaned and cleaned not in seen:
                seen.add(cleaned)
                inferred.append(cleaned)
    return tuple(inferred)


def _is_scoring_evidence(record: AuthorityRetrievedRecord) -> bool:
    return (
        record.record_type == "evidence"
        and record.authority_tier in SCORING_AUTHORITY_TIERS
    )


def _is_financial_risk_category(category: str) -> bool:
    cleaned = str(category).strip()
    return any(
        cleaned == prefix or cleaned.startswith(f"{prefix}_")
        for prefix in FINANCIAL_RISK_CATEGORY_PREFIXES
    )


def _tuple_text(values: Sequence[str] | str) -> tuple[str, ...]:
    if isinstance(values, str):
        cleaned = values.strip()
        return (cleaned,) if cleaned else ()
    return tuple(str(value).strip() for value in values if str(value).strip())


def _select_with_conflict_siblings(
    results: Sequence[RetrievalResult],
    limit: int,
) -> tuple[RetrievalResult, ...]:
    selected = list(results[:limit])
    selected_groups = {
        _conflict_group(result.chunk)
        for result in selected
        if _conflict_group(result.chunk)
    }
    seen = {result.chunk.chunk_id for result in selected}
    for result in results[limit:]:
        group = _conflict_group(result.chunk)
        if not group or group not in selected_groups or result.chunk.chunk_id in seen:
            continue
        selected.append(result)
        seen.add(result.chunk.chunk_id)
    return tuple(selected)


def _build_conflict_sets(
    records: Sequence[AuthorityRetrievedRecord],
) -> tuple[ConflictSet, ...]:
    groups: dict[str, list[AuthorityRetrievedRecord]] = defaultdict(list)
    for record in records:
        if record.conflict_group:
            groups[record.conflict_group].append(record)
    return tuple(
        ConflictSet(conflict_group=group, records=tuple(_sort_by_precedence(group_records)))
        for group, group_records in sorted(groups.items())
        if len(group_records) >= 2
    )


def _apply_precedence_ranks(
    records: Sequence[AuthorityRetrievedRecord],
    conflict_sets: Sequence[ConflictSet],
) -> tuple[AuthorityRetrievedRecord, ...]:
    rank_by_id: dict[str, int] = {}
    for conflict in conflict_sets:
        for rank, record in enumerate(conflict.precedence_order, start=1):
            rank_by_id[record] = rank
    return tuple(
        AuthorityRetrievedRecord(
            rank=record.rank,
            retrieval_score=record.retrieval_score,
            record_id=record.record_id,
            record_type=record.record_type,
            title=record.title,
            text=record.text,
            source_id=record.source_id,
            source_ids=record.source_ids,
            authority_tier=record.authority_tier,
            verification_status=record.verification_status,
            risk_categories=record.risk_categories,
            score_eligible=record.score_eligible,
            practice_reference=record.practice_reference,
            matched_terms=record.matched_terms,
            conflict_group=record.conflict_group,
            precedence_year=record.precedence_year,
            precedence_rank=rank_by_id.get(record.record_id),
            precedence_rule=record.precedence_rule,
            metadata=record.metadata,
        )
        for record in records
    )


def _sort_by_precedence(
    records: Sequence[AuthorityRetrievedRecord],
) -> tuple[AuthorityRetrievedRecord, ...]:
    return tuple(
        sorted(
            records,
            key=lambda record: (
                record.precedence_year is None,
                -(record.precedence_year or 0),
                AUTHORITY_SORT_ORDER.get(record.authority_tier, 99),
                record.record_id,
            ),
        )
    )


def _conflict_group(chunk: RetrievalChunk) -> str:
    for key in CONFLICT_GROUP_KEYS:
        value = str(chunk.metadata.get(key) or "").strip()
        if value:
            return value
    return ""


def _source_year(chunk: RetrievalChunk) -> int | None:
    for key in SOURCE_YEAR_KEYS:
        value = chunk.metadata.get(key)
        year = _year_from_value(value)
        if year is not None:
            return year
    return (
        _year_from_value(chunk.source_id)
        or _year_from_value(chunk.title)
        or _year_from_value(chunk.text)
    )


def _year_from_value(value: Any) -> int | None:
    if isinstance(value, int):
        return value
    match = YEAR_RE.search(str(value or ""))
    return int(match.group(1)) if match else None

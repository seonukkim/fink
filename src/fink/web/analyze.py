"""Server-free local analysis pipeline for the FInk creator demo.

This module composes the existing offline FInk engines into a single
deterministic call so the web layer can turn pasted contract text (or an
already-ingested document) into a natural-language Decision Brief plus the four
separate report dimensions.

Decision-Focused framing: the pipeline does not only surface a ranked list of
rule signals, it also reports a recommended action drawn from the engine's
categorical pathway label, the pivotal lever behind each finding, a cash-flow
consequence, and negotiation questions. Nothing here calls a network, a model
weight, or a large language model; every generated sentence is honest
deterministic templating, and the Korean text is canonical while the English
text is a generated aid.

Authority-grounding note: pasted text is still routed through the versioned
local corpus. Deterministic BM25 may attach real A0-A2 evidence ids to matching
rule signals. A finding with no eligible official evidence remains a candidate
and contributes 0; generated English labels and similarity scores never create
score eligibility.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from fink.schemas import (
    Lang,
    OCRPage,
    OCRSpan,
    PathwayLabel,
    RiskCategory,
    TextSource,
    UILocale,
)
from fink.scoring.engine import (
    CATEGORY_CONFIG_IDS,
    DocumentScoringResult,
    aggregate_document_signals,
)
from fink.segment.engine import segment_pages
from fink.signals.engine import RuleBasedSignalDetector, SignalRuleSet, load_signal_rules
from fink.time.exposure import AnalysisRuntimeTimer, TimeExposureResult, build_time_exposure

if TYPE_CHECKING:
    from collections.abc import Sequence
    from decimal import Decimal

    from fink.grounding import AuthorityRetrievedRecord
    from fink.ingest.session import IngestedDocument
    from fink.schemas import Clause, MonetaryExposureEstimate, RiskSignal

# Display limits. The snippet cap keeps echoed clause text short in the brief;
# it is a display nicety only and never affects scoring.
SNIPPET_MAX_CHARS = 80
SUMMARY_TOP_FINDINGS = 3

GROUNDING_UNVERIFIED = "UNVERIFIED"
GROUNDING_GROUNDED = "LOCAL_OFFICIAL_EVIDENCE"
GROUNDING_CANDIDATE = "CANDIDATE_UNVERIFIED"
GROUNDING_NOTE_KO = (
    "로컬 공식 출처 근거가 연결된 신호만 점수에 반영되며, 근거 검증 상태는 미확인입니다."
)
GROUNDING_NOTE_EN = (
    "Only signals linked to local official-source evidence affect the score; "
    "evidence verification remains UNVERIFIED."
)
CANDIDATE_MISSING_EVIDENCE_KO = (
    "미확인 후보: 이 신호에 맞는 A0-A2 공식 근거가 필요합니다."
)
CANDIDATE_MISSING_EVIDENCE_EN = (
    "Unverified candidate: this signal needs matching A0-A2 official evidence."
)

# Plain-language label for the synthetic-input requirement on the monetary
# dimension when the creator supplies no assumptions.
MONETARY_BLANK_KO = "금액 영향은 가정값을 입력하면 저/기준/고 범위로 계산됩니다."
MONETARY_BLANK_EN = (
    "Monetary impact stays blank until you add assumptions, then it shows low/base/high ranges."
)


@dataclass(frozen=True)
class RankedFinding:
    """One rule-signal finding for the transparent review-priority ranking.

    The ranking is ordered by ``rank_score = severity_raw * signal_confidence``
    and remains visible even when no official evidence makes the signal
    score-eligible.
    """

    rank: int
    signal_id: str
    risk_category: str
    label_ko: str
    label_en: str
    clause_id: str
    clause_heading: str | None
    snippet: str
    exact_excerpt: str
    severity_raw: float
    signal_confidence: float
    rank_score: float
    is_missing_protection: bool
    scored: bool = False
    grounding: str = GROUNDING_UNVERIFIED
    grounding_evidence_ids: tuple[str, ...] = ()
    authority_tiers: tuple[str, ...] = ()
    source_ids: tuple[str, ...] = ()
    citations: tuple[dict[str, str], ...] = ()
    missing_evidence_ko: str = CANDIDATE_MISSING_EVIDENCE_KO
    missing_evidence_en: str = CANDIDATE_MISSING_EVIDENCE_EN


@dataclass(frozen=True)
class CategoryGuidance:
    """Decision-Focused guidance for one risk category, bilingual."""

    risk_category: str
    why_it_matters_ko: str
    why_it_matters_en: str
    questions_ko: tuple[str, ...]
    questions_en: tuple[str, ...]


@dataclass(frozen=True)
class RecommendedAction:
    """The decision the brief reports: action plus cash-flow consequence.

    ``action_*`` is derived from the engine's categorical pathway label, not a
    legal verdict. ``cash_flow_*`` is a qualitative consequence statement; it
    never invents a monetary figure.
    """

    pathway_label: str
    action_ko: str
    action_en: str
    cash_flow_ko: str
    cash_flow_en: str


@dataclass(frozen=True)
class LocalAnalysisResult:
    """Full offline analysis outcome for one paste/ingest request."""

    ui_locale: UILocale
    clause_count: int
    signal_count: int
    review_priority_score: int
    grounding: str
    grounding_note_ko: str
    grounding_note_en: str
    ranked_findings: tuple[RankedFinding, ...]
    category_guidance: tuple[CategoryGuidance, ...]
    recommended_action: RecommendedAction
    nl_summary_ko: str
    nl_summary_en: str
    category_scores: dict[str, float]
    evidence_authority_tiers: dict[str, str]
    retrieved_record_count: int
    exposures: tuple["MonetaryExposureEstimate", ...]
    monetary_present: bool
    monetary_note_ko: str
    monetary_note_en: str
    scenario_input_values: dict[str, str]
    scoring: DocumentScoringResult
    time_result: TimeExposureResult
    measured_runtime_seconds: float
    source_pages: tuple[OCRPage, ...]
    clauses: tuple[Any, ...]


def run_local_analysis(
    *,
    pasted_text: str | None = None,
    ingested: "IngestedDocument | None" = None,
    scenario_inputs: Any | None = None,
    ui_locale: UILocale = UILocale.KO,
) -> LocalAnalysisResult:
    """Compose the offline FInk pipeline into one deterministic result.

    Exactly one of ``pasted_text`` or ``ingested`` provides the source pages.
    ``scenario_inputs`` is an optional ``EditableAssumptions`` (or
    ``FinancialScenarioInputs``-derived) object that unlocks the monetary
    dimension; with no assumptions the monetary dimension stays blank and no
    figure is invented.
    """

    pages = _resolve_pages(pasted_text=pasted_text, ingested=ingested)
    ocr_confidence = _mean_page_confidence(pages, is_paste=ingested is None)

    with AnalysisRuntimeTimer() as timer:
        clauses = segment_pages(pages)
        rule_set = load_signal_rules()
        detector = RuleBasedSignalDetector(rule_set)
        first_pass_signals = detector.detect_clauses(clauses)
        grounding_by_clause = _retrieve_grounding_by_clause(clauses, first_pass_signals)
        grounding_records = _flatten_grounding_records(grounding_by_clause.values())
        signals = _detect_clause_signals_with_grounding(
            detector,
            clauses,
            grounding_by_clause,
        )
        evidence_authority_tiers = _evidence_authority_tiers(grounding_records)
        scoring = aggregate_document_signals(
            signals,
            ocr_confidence=ocr_confidence,
            evidence_authority_tiers=evidence_authority_tiers,
        )
        editable_inputs = _resolve_editable_assumptions(scenario_inputs)
        exposures = _resolve_exposures(editable_inputs)
    measured_runtime_seconds = timer.elapsed_seconds

    ranked_findings = _rank_findings(
        signals,
        clauses,
        rule_set,
        grounding_records=grounding_records,
        scoring=scoring,
    )
    monetary_present = any(not exposure.is_user_input_required for exposure in exposures)

    time_result = build_time_exposure(
        page_count=len(pages),
        num_flagged_clauses=len({signal.clause_id for signal in signals}),
        num_missing_financial_inputs=0 if monetary_present else 1,
        measured_analysis_runtime_seconds=measured_runtime_seconds,
        review_priority_score=scoring.review_priority_score,
        material_monetary_exposure_range_present=monetary_present,
        uncapped_or_ambiguous_liability_signal_present=_has_category(signals, RiskCategory.F7),
        broad_ip_or_secondary_rights_transfer_signal_present=_has_category(
            signals, RiskCategory.F5
        ),
    )

    pathway_label = time_result.time_exposure.pathway_label
    category_guidance = _category_guidance_for(ranked_findings)
    recommended_action = _recommended_action_for(pathway_label)
    nl_summary_ko = _build_nl_summary(
        ranked_findings, recommended_action, monetary_present, UILocale.KO
    )
    nl_summary_en = _build_nl_summary(
        ranked_findings, recommended_action, monetary_present, UILocale.EN
    )

    return LocalAnalysisResult(
        ui_locale=ui_locale,
        clause_count=len(clauses),
        signal_count=len(signals),
        review_priority_score=scoring.review_priority_score,
        grounding=GROUNDING_GROUNDED if evidence_authority_tiers else GROUNDING_CANDIDATE,
        grounding_note_ko=GROUNDING_NOTE_KO,
        grounding_note_en=GROUNDING_NOTE_EN,
        ranked_findings=ranked_findings,
        category_guidance=category_guidance,
        recommended_action=recommended_action,
        nl_summary_ko=nl_summary_ko,
        nl_summary_en=nl_summary_en,
        category_scores={
            category.value: score for category, score in scoring.category_scores.items()
        },
        evidence_authority_tiers=dict(evidence_authority_tiers),
        retrieved_record_count=len(grounding_records),
        exposures=exposures,
        monetary_present=monetary_present,
        monetary_note_ko=MONETARY_BLANK_KO,
        monetary_note_en=MONETARY_BLANK_EN,
        scenario_input_values=_scenario_input_values(editable_inputs),
        scoring=scoring,
        time_result=time_result,
        measured_runtime_seconds=measured_runtime_seconds,
        source_pages=pages,
        clauses=clauses,
    )


def _resolve_pages(
    *, pasted_text: str | None, ingested: "IngestedDocument | None"
) -> tuple[OCRPage, ...]:
    if ingested is not None:
        document = ingested.document
        if document is None or not document.pages:
            raise _ingest_validation_error("ingested item has no analyzable pages")
        return tuple(document.pages)
    if pasted_text is None:
        raise _ingest_validation_error("provide pasted_text or an ingested document")
    return _pages_from_text(pasted_text)


def _pages_from_text(text: str) -> tuple[OCRPage, ...]:
    """Build a single deterministic text page from pasted contract text.

    Each nonblank line becomes one full-confidence span for segmentation, but
    the page is marked as ``text_layer`` so the reader does not imply OCR or
    real page-box provenance for pasted text.
    """

    if not isinstance(text, str) or not text.strip():
        raise _ingest_validation_error("pasted text must be nonblank")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        raise _ingest_validation_error("pasted text must contain at least one line")

    width_px = 1000
    line_height = 20
    spans = tuple(
        OCRSpan(
            span_id=f"page-0:span-{index}",
            text=line,
            bbox={"x": 0, "y": index * line_height, "w": min(width_px, 100), "h": 18},
            confidence=1.0,
            lang=_detect_lang(line),
        )
        for index, line in enumerate(lines)
    )
    page = OCRPage(
        page_id="page-0",
        page_index=0,
        rotation_deg=0,
        width_px=width_px,
        height_px=max(len(lines) * line_height, 1),
        spans=spans,
        page_ocr_confidence=1.0,
        text_source=TextSource.TEXT_LAYER,
        is_user_corrected=False,
    )
    return (page,)


def _detect_lang(text: str) -> Lang:
    has_hangul = any("가" <= char <= "힣" for char in text)
    has_alpha = any("a" <= char.lower() <= "z" for char in text)
    has_digit = any(char.isdigit() for char in text)
    if has_hangul and has_alpha:
        return Lang.MIXED
    if has_hangul:
        return Lang.KO
    if has_alpha:
        return Lang.EN
    if has_digit:
        return Lang.NUM
    return Lang.MIXED


def _mean_page_confidence(pages: tuple[OCRPage, ...], *, is_paste: bool) -> float:
    if is_paste:
        return 1.0
    if not pages:
        return 0.0
    return sum(page.page_ocr_confidence for page in pages) / len(pages)


def _retrieve_grounding_by_clause(
    clauses: "tuple[Clause, ...]",
    first_pass_signals: "tuple[RiskSignal, ...]",
) -> dict[str, tuple["AuthorityRetrievedRecord", ...]]:
    from fink.grounding import authority_gated_retrieval
    from fink.retrieval import load_or_build_retrieval_index

    signals_by_clause: dict[str, list[RiskSignal]] = {}
    for signal in first_pass_signals:
        signals_by_clause.setdefault(signal.clause_id, []).append(signal)

    if not signals_by_clause:
        return {}

    index = load_or_build_retrieval_index()
    records_by_clause: dict[str, tuple[AuthorityRetrievedRecord, ...]] = {}
    for clause in clauses:
        clause_signals = tuple(signals_by_clause.get(clause.clause_id, ()))
        if not clause_signals:
            continue
        categories = _retrieval_categories_for(clause_signals)
        query = _retrieval_query_for_clause(clause, categories)
        bundle = authority_gated_retrieval(
            index,
            query,
            explanation_k=3,
            grounding_k=3,
            risk_categories=categories,
        )
        records_by_clause[clause.clause_id] = _signal_grounding_records(
            bundle.returned_records
        )
    return records_by_clause


def _detect_clause_signals_with_grounding(
    detector: RuleBasedSignalDetector,
    clauses: "tuple[Clause, ...]",
    grounding_by_clause: dict[str, tuple["AuthorityRetrievedRecord", ...]],
) -> tuple["RiskSignal", ...]:
    signals: list[RiskSignal] = []
    for clause in clauses:
        signals.extend(
            detector.detect_clause(
                clause,
                grounding_records=grounding_by_clause.get(clause.clause_id, ()),
            )
        )
    return tuple(signals)


def _retrieval_categories_for(signals: "tuple[RiskSignal, ...]") -> tuple[str, ...]:
    categories: list[str] = []
    for signal in signals:
        for category in (
            CATEGORY_CONFIG_IDS.get(signal.risk_category, ""),
            signal.risk_category.value,
        ):
            if category and category not in categories:
                categories.append(category)
    return tuple(categories)


def _retrieval_query_for_clause(
    clause: "Clause",
    categories: tuple[str, ...],
) -> str:
    return " ".join(
        part
        for part in (
            clause.heading_ko or "",
            clause.text_ko,
            clause.text_en_gloss or "",
            " ".join(categories),
        )
        if str(part).strip()
    )


def _signal_grounding_records(
    records: tuple["AuthorityRetrievedRecord", ...],
) -> tuple["AuthorityRetrievedRecord", ...]:
    selected: list[AuthorityRetrievedRecord] = []
    seen: set[str] = set()
    for record in records:
        is_official_evidence = (
            record.record_type == "evidence"
            and record.authority_tier in {"A0", "A1", "A2"}
            and record.score_eligible
        )
        is_practice_reference = record.authority_tier in {"B", "C", "B/C"}
        if not (is_official_evidence or is_practice_reference):
            continue
        if record.record_id in seen:
            continue
        seen.add(record.record_id)
        selected.append(record)
    return tuple(selected)


def _flatten_grounding_records(
    record_groups: "Sequence[tuple[AuthorityRetrievedRecord, ...]]",
) -> tuple["AuthorityRetrievedRecord", ...]:
    ordered: list[AuthorityRetrievedRecord] = []
    seen: set[str] = set()
    for records in record_groups:
        for record in records:
            if record.record_id in seen:
                continue
            seen.add(record.record_id)
            ordered.append(record)
    return tuple(ordered)


def _evidence_authority_tiers(
    records: "tuple[AuthorityRetrievedRecord, ...]",
) -> dict[str, str]:
    return {
        record.record_id: record.authority_tier
        for record in records
        if (
            record.record_type == "evidence"
            and record.authority_tier in {"A0", "A1", "A2"}
            and record.score_eligible
        )
    }


def _rank_findings(
    signals: "tuple[RiskSignal, ...] | list[RiskSignal]",
    clauses: "tuple[Clause, ...]",
    rule_set: SignalRuleSet,
    *,
    grounding_records: tuple["AuthorityRetrievedRecord", ...],
    scoring: DocumentScoringResult,
) -> tuple[RankedFinding, ...]:
    clauses_by_id = {clause.clause_id: clause for clause in clauses}
    records_by_id = {record.record_id: record for record in grounding_records}
    contributions_by_signal = {
        (contribution.signal_id, contribution.clause_id): contribution
        for contribution in scoring.contributions
    }
    scored = sorted(
        signals,
        key=lambda signal: (
            -(float(signal.severity_raw or 0.0) * float(signal.signal_confidence)),
            signal.signal_id,
        ),
    )
    findings: list[RankedFinding] = []
    for rank, signal in enumerate(scored, start=1):
        rule = rule_set.rule_by_id(signal.signal_id)
        clause = clauses_by_id.get(signal.clause_id)
        severity_raw = float(signal.severity_raw or 0.0)
        confidence = float(signal.signal_confidence)
        contribution = contributions_by_signal.get((signal.signal_id, signal.clause_id))
        evidence_ids = tuple(signal.grounding_evidence_ids or ())
        evidence_records = tuple(
            record for evidence_id in evidence_ids if (record := records_by_id.get(evidence_id))
        )
        is_scored = bool(contribution is not None and contribution.contribution > 0)
        findings.append(
            RankedFinding(
                rank=rank,
                signal_id=signal.signal_id,
                risk_category=signal.risk_category.value,
                label_ko=rule.label_ko,
                label_en=rule.label_en,
                clause_id=signal.clause_id,
                clause_heading=clause.heading_ko if clause is not None else None,
                snippet=_clause_snippet(clause),
                exact_excerpt=_clause_exact_excerpt(clause),
                severity_raw=severity_raw,
                signal_confidence=confidence,
                rank_score=severity_raw * confidence,
                is_missing_protection=signal.is_missing_protection,
                scored=is_scored,
                grounding=GROUNDING_GROUNDED if is_scored else GROUNDING_CANDIDATE,
                grounding_evidence_ids=evidence_ids if is_scored else (),
                authority_tiers=_record_authority_tiers(evidence_records) if is_scored else (),
                source_ids=_record_source_ids(evidence_records) if is_scored else (),
                citations=_citations_from_records(evidence_records) if is_scored else (),
            )
        )
    return tuple(findings)


def _record_authority_tiers(records: tuple["AuthorityRetrievedRecord", ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(record.authority_tier for record in records))


def _record_source_ids(records: tuple["AuthorityRetrievedRecord", ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(record.source_id for record in records if record.source_id))


def _citations_from_records(
    records: tuple["AuthorityRetrievedRecord", ...],
) -> tuple[dict[str, str], ...]:
    return tuple(
        {
            "citation_id": f"citation-{record.record_id}",
            "evidence_id": record.record_id,
            "source_id": record.source_id,
            "authority_tier": record.authority_tier,
            "verification_status": record.verification_status,
            "source_clause_id": record.title,
            "exact_excerpt": "",
        }
        for record in records
    )


def _clause_snippet(clause: "Clause | None") -> str:
    if clause is None:
        return ""
    text = " ".join(clause.text_ko.split())
    if len(text) <= SNIPPET_MAX_CHARS:
        return text
    return text[: SNIPPET_MAX_CHARS - 1].rstrip() + "…"


def _clause_exact_excerpt(clause: "Clause | None") -> str:
    if clause is None:
        return ""
    return " ".join(clause.text_ko.split())


def _has_category(
    signals: "tuple[RiskSignal, ...] | list[RiskSignal]", category: RiskCategory
) -> bool:
    return any(signal.risk_category is category for signal in signals)


def _resolve_editable_assumptions(scenario_inputs: Any | None) -> Any | None:
    if scenario_inputs is None:
        return None
    from fink.web.assumptions import EditableAssumptions

    if isinstance(scenario_inputs, EditableAssumptions):
        return scenario_inputs
    return EditableAssumptions.from_financial_scenario_inputs(scenario_inputs)


def _resolve_exposures(scenario_inputs: Any | None) -> tuple["MonetaryExposureEstimate", ...]:
    """Recompute monetary exposures only when assumptions are supplied.

    With no assumptions the exposures are empty, so the monetary dimension stays
    blank rather than inventing any number.
    """

    if scenario_inputs is None:
        return ()
    from fink.web.assumptions import recompute_assumptions

    return recompute_assumptions(scenario_inputs).exposures


def _scenario_input_values(scenario_inputs: Any | None) -> dict[str, str]:
    if scenario_inputs is None:
        return {}
    from dataclasses import fields as dataclass_fields

    values: dict[str, str] = {}
    for field in dataclass_fields(scenario_inputs):
        value = getattr(scenario_inputs, field.name)
        if value is None or value is False:
            continue
        if isinstance(value, tuple):
            values[field.name] = "provided"
        else:
            values[field.name] = str(value)
    return values


def _ingest_validation_error(message: str) -> Exception:
    from fink.ingest.session import IngestValidationError

    return IngestValidationError(message)


# ---------------------------------------------------------------------------
# Deterministic natural-language Decision Brief (no LLM, no network).
# Korean strings are canonical; English strings are a generated aid. Every
# Korean run is kept well under 180 Hangul-to-Hangul characters and ends in a
# period so the long-private-quotation gate never matches.
# ---------------------------------------------------------------------------

_CATEGORY_GUIDANCE: dict[str, CategoryGuidance] = {
    "F1": CategoryGuidance(
        risk_category="F1",
        why_it_matters_ko="정산 명세와 감사 권한이 약하면 공제 내역을 검증하기 어렵습니다.",
        why_it_matters_en=(
            "Weak settlement detail and audit rights make it hard to verify deductions."
        ),
        questions_ko=(
            "정산 명세서를 항목별로 받을 수 있나요?",
            "감사 또는 자료 열람 권한을 넣을 수 있나요?",
        ),
        questions_en=(
            "Can you receive an itemized settlement statement?",
            "Can an audit or records-access right be added?",
        ),
    ),
    "F2": CategoryGuidance(
        risk_category="F2",
        why_it_matters_ko="매출 기준과 공제 항목이 모호하면 실수령액이 줄어들 수 있습니다.",
        why_it_matters_en=(
            "An unclear revenue base and open deductions can shrink your net payout."
        ),
        questions_ko=(
            "공제 항목을 구체적으로 한정할 수 있나요?",
            "매출 기준을 총액 또는 순액으로 명확히 할 수 있나요?",
        ),
        questions_en=(
            "Can the deduction items be specifically limited?",
            "Can the revenue base be fixed as gross or net?",
        ),
    ),
    "F3": CategoryGuidance(
        risk_category="F3",
        why_it_matters_ko="지급 시점이 늦으면 현금 흐름과 자금 운용이 불리해집니다.",
        why_it_matters_en="Late payment timing hurts your cash flow and working capital.",
        questions_ko=(
            "지급 기일을 더 앞당길 수 있나요?",
            "지연 시 이자나 지연배상 조항을 넣을 수 있나요?",
        ),
        questions_en=(
            "Can the payment due date be moved earlier?",
            "Can a late-payment interest clause be added?",
        ),
    ),
    "F4": CategoryGuidance(
        risk_category="F4",
        why_it_matters_ko="선급금 회수 조건이 불리하면 정산이 장기간 미뤄질 수 있습니다.",
        why_it_matters_en="Tough advance-recoupment terms can defer your payout for a long time.",
        questions_ko=(
            "선급금 회수 기준을 명확히 할 수 있나요?",
            "회수 기간 상한을 정할 수 있나요?",
        ),
        questions_en=(
            "Can the recoupment basis be made explicit?",
            "Can a cap on the recoupment period be set?",
        ),
    ),
    "F5": CategoryGuidance(
        risk_category="F5",
        why_it_matters_ko="이차적 권리 양도 범위가 넓으면 추가 수익 기회를 잃을 수 있습니다.",
        why_it_matters_en=(
            "A broad secondary-rights transfer can cost you future revenue opportunities."
        ),
        questions_ko=(
            "양도 권리 범위를 좁힐 수 있나요?",
            "이차 활용에 대한 추가 보상을 받을 수 있나요?",
        ),
        questions_en=(
            "Can the scope of transferred rights be narrowed?",
            "Can extra compensation for secondary use be added?",
        ),
    ),
    "F6": CategoryGuidance(
        risk_category="F6",
        why_it_matters_ko="독점과 자동 갱신 조건은 다른 기회의 가치를 묶어 둘 수 있습니다.",
        why_it_matters_en="Exclusivity and auto-renewal can lock up the value of other opportunities.",
        questions_ko=(
            "독점 기간을 줄일 수 있나요?",
            "자동 갱신 대신 합의 갱신으로 바꿀 수 있나요?",
        ),
        questions_en=(
            "Can the exclusivity period be shortened?",
            "Can auto-renewal become mutual-consent renewal?",
        ),
    ),
    "F7": CategoryGuidance(
        risk_category="F7",
        why_it_matters_ko="위약금 상한이나 시정 기간이 없으면 책임이 과도해질 수 있습니다.",
        why_it_matters_en="Without a penalty cap or cure period, liability can become excessive.",
        questions_ko=(
            "위약금 상한을 정할 수 있나요?",
            "위반 시 시정 기간을 넣을 수 있나요?",
        ),
        questions_en=(
            "Can a cap on the penalty be set?",
            "Can a cure period before penalties apply be added?",
        ),
    ),
    "F8": CategoryGuidance(
        risk_category="F8",
        why_it_matters_ko="추가 작업 범위가 열려 있으면 무상 작업 부담이 커질 수 있습니다.",
        why_it_matters_en="Open-ended extra scope can pile on unpaid additional work.",
        questions_ko=(
            "수정 횟수나 추가 작업 범위를 한정할 수 있나요?",
            "추가 작업에 대한 별도 비용을 정할 수 있나요?",
        ),
        questions_en=(
            "Can revision counts or extra scope be capped?",
            "Can separate pay for additional work be set?",
        ),
    ),
    "F9": CategoryGuidance(
        risk_category="F9",
        why_it_matters_ko="전자계약과 개인정보 처리 조건이 약하면 증빙과 보호가 부족할 수 있습니다.",
        why_it_matters_en=(
            "Weak e-contract and privacy terms can leave evidence and protection lacking."
        ),
        questions_ko=(
            "계약 사본과 체결 증빙을 받을 수 있나요?",
            "개인정보 처리 범위를 명확히 할 수 있나요?",
        ),
        questions_en=(
            "Can you keep a signed copy and proof of execution?",
            "Can the scope of personal-data handling be clarified?",
        ),
    ),
}

# Recommended action drawn from the engine's categorical pathway label. These
# are decision prompts (sign / clarify / renegotiate / seek review), never a
# legal verdict and never an invented figure.
_PATHWAY_ACTIONS: dict[PathwayLabel, RecommendedAction] = {
    PathwayLabel.CLARIFICATION_LIKELY_SUFFICIENT: RecommendedAction(
        pathway_label=PathwayLabel.CLARIFICATION_LIKELY_SUFFICIENT.value,
        action_ko="권장 행동: 몇 가지 항목을 확인한 뒤 서명을 검토하세요.",
        action_en="Recommended action: clarify a few items, then consider signing.",
        cash_flow_ko="현금 흐름 영향은 작아 보이지만 확인 후 진행하는 것이 안전합니다.",
        cash_flow_en="Cash-flow impact looks small, but confirm the items before proceeding.",
    ),
    PathwayLabel.NEGOTIATION_REQUIRED: RecommendedAction(
        pathway_label=PathwayLabel.NEGOTIATION_REQUIRED.value,
        action_ko="권장 행동: 서명 전에 핵심 조건을 재협상하세요.",
        action_en="Recommended action: renegotiate the key terms before signing.",
        cash_flow_ko="조건에 따라 실수령액과 현금 흐름이 달라질 수 있습니다.",
        cash_flow_en="Depending on the terms, your net payout and cash flow may change.",
    ),
    PathwayLabel.PROFESSIONAL_REVIEW_REQUIRED: RecommendedAction(
        pathway_label=PathwayLabel.PROFESSIONAL_REVIEW_REQUIRED.value,
        action_ko="권장 행동: 서명 전에 전문가 검토를 받는 것을 권합니다.",
        action_en="Recommended action: seek a professional review before signing.",
        cash_flow_ko="책임 범위가 커서 현금 흐름에 큰 영향을 줄 수 있습니다.",
        cash_flow_en="Liability is broad and could have a large cash-flow impact.",
    ),
    PathwayLabel.DISPUTE_PATHWAY_MAY_BE_REQUIRED: RecommendedAction(
        pathway_label=PathwayLabel.DISPUTE_PATHWAY_MAY_BE_REQUIRED.value,
        action_ko="권장 행동: 미지급 또는 지연 항목을 먼저 정리하고 대응하세요.",
        action_en="Recommended action: address the unpaid or delayed items first.",
        cash_flow_ko="이미 지연된 금액이 있어 현금 흐름이 직접 영향을 받을 수 있습니다.",
        cash_flow_en="An already-delayed amount may directly affect your cash flow.",
    ),
}

_NO_FINDINGS_KO = "두드러진 금융 신호가 발견되지 않았습니다. 그래도 핵심 조건은 직접 확인하세요."
_NO_FINDINGS_EN = (
    "No prominent financial signals were found. Still, review the key terms yourself."
)
_BRIEF_LEAD_KO = "이 브리프는 결정에 도움을 주는 자동 요약이며 법률 자문이 아닙니다."
_BRIEF_LEAD_EN = "This brief is an automated decision aid and is not legal advice."


def _category_guidance_for(
    findings: tuple[RankedFinding, ...],
) -> tuple[CategoryGuidance, ...]:
    seen: list[str] = []
    guidance: list[CategoryGuidance] = []
    for finding in findings:
        if finding.risk_category in seen:
            continue
        seen.append(finding.risk_category)
        entry = _CATEGORY_GUIDANCE.get(finding.risk_category)
        if entry is not None:
            guidance.append(entry)
    return tuple(guidance)


def _recommended_action_for(pathway_label: PathwayLabel) -> RecommendedAction:
    return _PATHWAY_ACTIONS[pathway_label]


def _build_nl_summary(
    findings: tuple[RankedFinding, ...],
    recommended_action: RecommendedAction,
    monetary_present: bool,
    locale: UILocale,
) -> str:
    """Build a short, deterministic Decision Brief paragraph.

    Each sentence ends with a period so the long-private-quotation gate, which
    only matches >=180 Hangul-to-Hangul characters with no period or newline,
    never fires on the generated Korean text.
    """

    is_ko = locale is UILocale.KO
    lead = _BRIEF_LEAD_KO if is_ko else _BRIEF_LEAD_EN
    action_line = recommended_action.action_ko if is_ko else recommended_action.action_en
    cash_line = recommended_action.cash_flow_ko if is_ko else recommended_action.cash_flow_en

    if not findings:
        no_findings = _NO_FINDINGS_KO if is_ko else _NO_FINDINGS_EN
        return " ".join((lead, no_findings, action_line))

    sentences = [lead, action_line, cash_line]
    top = findings[:SUMMARY_TOP_FINDINGS]
    if is_ko:
        sentences.append(f"우선 살펴볼 신호 {len(top)}건을 정리했습니다.")
    else:
        sentences.append(f"Here are the top {len(top)} signals to look at first.")

    for finding in top:
        label = finding.label_ko if is_ko else finding.label_en
        guidance = _CATEGORY_GUIDANCE.get(finding.risk_category)
        if guidance is None:
            continue
        why = guidance.why_it_matters_ko if is_ko else guidance.why_it_matters_en
        if is_ko:
            sentences.append(f"{finding.rank}순위 {finding.risk_category} {label}: {why}")
        else:
            sentences.append(f"#{finding.rank} {finding.risk_category} {label}: {why}")

    if not monetary_present:
        sentences.append(MONETARY_BLANK_KO if is_ko else MONETARY_BLANK_EN)
    if is_ko:
        sentences.append("점수 0은 위험이 없다는 뜻이 아니라 오프라인 근거 미확인을 뜻합니다.")
    else:
        sentences.append(
            "A score of 0 means grounding is UNVERIFIED offline, not that there is no risk."
        )
    return " ".join(sentences)


# ---------------------------------------------------------------------------
# JSON-safe payload for the /api/analyze endpoint.
# ---------------------------------------------------------------------------


def analysis_result_to_payload(result: LocalAnalysisResult, locale: UILocale) -> dict[str, Any]:
    """Return the canonical creator-review view model payload."""

    if isinstance(locale, str):
        try:
            locale = UILocale(locale.strip().lower())
        except ValueError:
            locale = UILocale.KO

    from fink.web.view_model import creator_review_payload_from_result

    return creator_review_payload_from_result(result, locale)

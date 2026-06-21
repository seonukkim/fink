from __future__ import annotations

import html
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from fink.schemas import (
    FINANCIAL_RISK_CATEGORIES,
    AnalysisReport,
    ClauseAssessment,
    EvidenceRecord,
    ExportFormat,
    MonetaryExposureEstimate,
    RiskCategory,
    RiskSignal,
    TimeExposure,
)

FOUR_DIMENSION_IDS = (
    "review-priority-score",
    "monetary-exposure-range",
    "time-exposure",
    "evidence-ocr-confidence",
)
EXPORT_FORMATS = (ExportFormat.HTML.value, ExportFormat.MD.value, ExportFormat.JSON.value)

FINANCIAL_CATEGORY_ORDER = (
    RiskCategory.F1,
    RiskCategory.F2,
    RiskCategory.F3,
    RiskCategory.F4,
    RiskCategory.F5,
    RiskCategory.F6,
    RiskCategory.F7,
    RiskCategory.F8,
    RiskCategory.F9,
)
CROSS_CUTTING_CATEGORY_ORDER = (
    RiskCategory.X1,
    RiskCategory.X2,
    RiskCategory.X3,
    RiskCategory.X4,
    RiskCategory.X5,
)

CATEGORY_LABELS = {
    RiskCategory.F1: "정산 투명성·감사권 / Settlement transparency & audit",
    RiskCategory.F2: "매출 기준·공제 / Revenue base & deductions",
    RiskCategory.F3: "지급 시기·현금흐름 / Payment timing & cashflow",
    RiskCategory.F4: "미니멈 개런티·선급금 회수 / MG & advance recoupment",
    RiskCategory.F5: "저작권·2차적저작물 수익화 / IP & secondary-rights monetization",
    RiskCategory.F6: "기간·독점·기회비용 / Term, exclusivity & opportunity cost",
    RiskCategory.F7: "해지·손해배상·위약금 / Termination, liability & penalties",
    RiskCategory.F8: "업무범위 확대·제작비 / Scope creep & production cost",
    RiskCategory.F9: "전자계약·개인정보·증거보존 / E-contract, privacy & evidence",
    RiskCategory.X1: "Evidence & currency governance",
    RiskCategory.X2: "Dispute resolution & cash recovery",
    RiskCategory.X3: "Responsible-AI & explainability",
    RiskCategory.X4: "Labor status & creator safety",
    RiskCategory.X5: "Moral & non-contract harms",
}


@dataclass(frozen=True)
class HighlightedEvidence:
    clause_id: str
    page_index: int
    source_span_id: str
    text_before: str
    trigger_text: str
    text_after: str


@dataclass(frozen=True)
class PracticeReference:
    reference_id: str
    risk_category: RiskCategory | str
    clause_id: str
    explanation_ko: str
    explanation_en_alias: str
    questions: tuple[str, ...] = ()
    source_label: str = "B/C practice card"


def report_dimension_ids() -> tuple[str, str, str, str]:
    return FOUR_DIMENSION_IDS


def report_export_formats() -> tuple[str, str, str]:
    return EXPORT_FORMATS


def category_label(category: RiskCategory | str) -> str:
    return CATEGORY_LABELS[_coerce_category(category)]


def active_financial_category_codes(report: AnalysisReport) -> tuple[str, ...]:
    return tuple(category.value for category in _active_financial_categories(report))


def render_empty_report_shell_html() -> str:
    """Render the static shell before a local analysis report exists."""

    dimension_cards = "\n".join(
        f"""<article data-report-dimension="{dimension_id}">
          <h3>{_empty_dimension_title(dimension_id)}</h3>
          <p class="hint">{_empty_dimension_hint(dimension_id)}</p>
        </article>"""
        for dimension_id in FOUR_DIMENSION_IDS
    )
    return f"""<section class="report-ui report-ui-empty" data-four-dimension-report="true">
      <div class="dimension-grid" data-dimension-count="4">
        {dimension_cards}
      </div>
      <section class="category-cards" aria-labelledby="category-cards-heading"
        data-risk-category-cards="{_category_codes(FINANCIAL_CATEGORY_ORDER)}">
        <h3 id="category-cards-heading">Risk-category cards</h3>
        <p class="hint">Run local analysis to populate one card per active F-category.</p>
        <span class="badge" data-practice-reference-badge="true">
          practice reference / non-scoring
        </span>
      </section>
      {_render_context_section(())}
      {render_export_controls_html()}
    </section>"""


def render_report_html(
    report: AnalysisReport,
    *,
    evidence_records: tuple[EvidenceRecord, ...] = (),
    practice_references: tuple[PracticeReference, ...] = (),
    highlighted_evidence: tuple[HighlightedEvidence, ...] = (),
    cross_cutting_signals: tuple[RiskSignal, ...] = (),
) -> str:
    """Render a local report while keeping the four dimensions separate."""

    return f"""<section class="report-ui" data-four-dimension-report="true"
      data-report-id="{_escape(report.report_id)}">
      {_render_dimensions(report)}
      {_render_category_cards(
          report,
          evidence_records=evidence_records,
          practice_references=practice_references,
          highlighted_evidence=highlighted_evidence,
      )}
      {_render_context_section(cross_cutting_signals)}
      {render_export_controls_html(contains_raw_image=report.contains_raw_image)}
    </section>"""


def render_export_controls_html(*, contains_raw_image: bool = False) -> str:
    buttons = "\n".join(
        f"""<button type="button" class="secondary"
          data-export-format="{_escape(fmt)}"
          data-export-local-only="true"
          data-contains-raw-image="false">{_escape(fmt.upper())}</button>"""
        for fmt in EXPORT_FORMATS
    )
    return f"""<section class="report-export-controls"
      aria-labelledby="report-export-heading"
      data-export-formats="{_escape(' '.join(EXPORT_FORMATS))}"
      data-export-local-only="true"
      data-outbound-network-clients="0"
      data-contains-raw-image="{str(False).lower()}"
      data-source-report-contains-raw-image="{str(contains_raw_image).lower()}">
      <h3 id="report-export-heading">Local export</h3>
      <div class="action-row" role="group" aria-label="Local report export formats">
        {buttons}
      </div>
      <p class="hint">HTML, Markdown, and JSON exports exclude raw image bytes by default.</p>
    </section>"""


def _render_dimensions(report: AnalysisReport) -> str:
    assessment = report.assessment
    confidence = assessment.confidence
    return f"""<div class="dimension-grid" data-dimension-count="4">
      <article data-report-dimension="review-priority-score">
        <h3>Review Priority Score</h3>
        <output aria-label="Contractual Financial Review Priority Score">
          {_escape(str(assessment.review_priority_score))} / 100
        </output>
        <p>계약상 금융 검토 우선도 / Contractual Financial Review Priority.</p>
      </article>
      <article data-report-dimension="monetary-exposure-range" data-grand-total="absent">
        <h3>Monetary Exposure Range</h3>
        {_render_monetary_exposures(assessment.monetary_exposures)}
      </article>
      <article data-report-dimension="time-exposure">
        <h3>Time Exposure</h3>
        {_render_time_exposure(assessment.time_exposure)}
      </article>
      <article data-report-dimension="evidence-ocr-confidence">
        <h3>Evidence &amp; OCR Confidence</h3>
        <dl class="metric-list">
          <dt>OCR confidence</dt><dd>{confidence.ocr_confidence:.2f}</dd>
          <dt>Evidence confidence</dt><dd>{confidence.evidence_confidence:.2f}</dd>
          <dt>Data completeness</dt><dd>{confidence.data_completeness:.2f}</dd>
          <dt>Overall confidence</dt><dd>{confidence.overall_confidence:.2f}</dd>
        </dl>
        {_render_list("confidence-drivers", confidence.drivers)}
      </article>
    </div>"""


def _render_monetary_exposures(exposures: tuple[MonetaryExposureEstimate, ...]) -> str:
    if not exposures:
        return (
            '<p class="hint" data-empty-money-range="true">'
            "Add user assumptions to estimate low / base / high ranges.</p>"
        )
    items = []
    for exposure in exposures:
        range_text = (
            "requires user input"
            if exposure.is_user_input_required
            else (
                f"low {_money(exposure.low)} / base {_money(exposure.base)} / "
                f"high {_money(exposure.high)}"
            )
        )
        assumptions = " ".join(
            f'<span class="badge synthetic-assumption">synthetic assumption</span> '
            f"{_escape(assumption)}"
            for assumption in exposure.assumptions
        )
        nominal = (
            f'<p class="hint">Nominal amount kept separate: {_money(exposure.nominal_amount)}</p>'
            if exposure.nominal_amount is not None
            else ""
        )
        flags = _render_list("uncertainty-flags", exposure.uncertainty_flags or ())
        items.append(
            f"""<li data-exposure-type="{_escape(exposure.exposure_type.value)}"
              data-fim-module="{_escape(exposure.module.value)}">
              <strong>{_escape(exposure.module.value)} {_escape(exposure.exposure_type.value)}</strong>
              <p>{range_text}</p>
              <p>{assumptions}</p>
              {nominal}
              {flags}
            </li>"""
        )
    return '<ul class="exposure-list">' + "\n".join(items) + "</ul>"


def _render_time_exposure(time_exposure: TimeExposure) -> str:
    fields = (
        ("measured_runtime_seconds", time_exposure.measured_analysis_runtime_seconds, "seconds"),
        ("estimated_human_review_minutes", time_exposure.estimated_human_review_minutes, "minutes"),
        ("payment_due_days", time_exposure.payment_due_days, "days"),
        ("payment_delay_days", time_exposure.payment_delay_days, "days"),
        ("contract_duration_months", time_exposure.contract_duration_months, "months"),
        ("renewal_duration_months", time_exposure.renewal_duration_months, "months"),
        ("exclusivity_duration_months", time_exposure.exclusivity_duration_months, "months"),
        ("termination_notice_days", time_exposure.termination_notice_days, "days"),
        ("estimated_months_to_recoup", time_exposure.estimated_months_to_recoup, "months"),
    )
    rows = "\n".join(
        f'<dt data-time-field="{_escape(name)}">{_escape(name.replace("_", " "))}</dt>'
        f"<dd>{_escape(_format_optional_number(value, unit))}</dd>"
        for name, value, unit in fields
    )
    return f"""<dl class="metric-list">
      <dt data-time-field="pathway_label">pathway label</dt>
      <dd>{_escape(time_exposure.pathway_label.value)}</dd>
      {rows}
    </dl>
    <p class="hint">No court or negotiation duration is estimated.</p>"""


def _render_category_cards(
    report: AnalysisReport,
    *,
    evidence_records: tuple[EvidenceRecord, ...],
    practice_references: tuple[PracticeReference, ...],
    highlighted_evidence: tuple[HighlightedEvidence, ...],
) -> str:
    active_categories = _active_financial_categories(report)
    if not active_categories:
        body = '<p class="hint">No active F-category signals in this local report.</p>'
    else:
        body = "\n".join(
            _render_category_card(
                report,
                category,
                evidence_records=evidence_records,
                practice_references=practice_references,
                highlighted_evidence=highlighted_evidence,
            )
            for category in active_categories
        )
    return f"""<section class="category-cards" aria-labelledby="category-cards-heading"
      data-risk-category-cards="{_category_codes(FINANCIAL_CATEGORY_ORDER)}">
      <h3 id="category-cards-heading">Risk-category cards</h3>
      {body}
    </section>"""


def _render_category_card(
    report: AnalysisReport,
    category: RiskCategory,
    *,
    evidence_records: tuple[EvidenceRecord, ...],
    practice_references: tuple[PracticeReference, ...],
    highlighted_evidence: tuple[HighlightedEvidence, ...],
) -> str:
    signals = _signals_for_category(report, category)
    eligible_count = sum(1 for signal in signals if signal.score_eligible)
    practice_count = sum(1 for signal in signals if signal.practice_reference)
    score = report.assessment.category_scores.get(category, 0.0)
    clauses = tuple(
        clause
        for clause in report.assessment.clause_assessments
        if any(_coerce_category(signal.risk_category) is category for signal in clause.signals)
    )
    official_records = _official_records_for_category(report, category, evidence_records)
    references = tuple(
        reference
        for reference in practice_references
        if _coerce_category(reference.risk_category) is category
    )
    return f"""<article class="risk-category-card" data-risk-category-card="{category.value}"
      data-score-driver="true" data-eligible-signal-count="{eligible_count}"
      data-practice-reference-count="{practice_count}">
      <header>
        <p class="eyebrow">{category.value}</p>
        <h4>{_escape(CATEGORY_LABELS[category])}</h4>
        <output aria-label="{category.value} category score">{score:.1f} / 100</output>
      </header>
      {_render_flagged_clauses(clauses, highlighted_evidence)}
      {_render_official_comparison(official_records)}
      {_render_practice_references(references)}
      {_render_questions(clauses, references)}
    </article>"""


def _render_flagged_clauses(
    clauses: tuple[ClauseAssessment, ...],
    highlighted_evidence: tuple[HighlightedEvidence, ...],
) -> str:
    if not clauses:
        return '<p class="hint">No flagged clause details available.</p>'
    highlights_by_clause = {item.clause_id: item for item in highlighted_evidence}
    items = []
    for clause in clauses:
        highlight = highlights_by_clause.get(clause.clause_id)
        if highlight is None:
            evidence_html = (
                f'<p data-highlighted-evidence="missing">Clause {_escape(clause.clause_id)}</p>'
            )
        else:
            page_anchor = f"page-{highlight.page_index + 1}"
            evidence_html = f"""<p data-highlighted-evidence="true"
              data-clause-id="{_escape(clause.clause_id)}"
              data-source-span-id="{_escape(highlight.source_span_id)}">
              {_escape(highlight.text_before)}
              <mark data-triggering-span="true">{_escape(highlight.trigger_text)}</mark>
              {_escape(highlight.text_after)}
              <a href="#{_escape(page_anchor)}" data-source-page-link="true">
                Page {highlight.page_index + 1}
              </a>
            </p>"""
        items.append(
            f"""<li data-flagged-clause="{_escape(clause.clause_id)}">
              <strong>Clause priority {_escape(str(clause.clause_priority))}</strong>
              {evidence_html}
            </li>"""
        )
    return '<ul class="flagged-clauses">' + "\n".join(items) + "</ul>"


def _render_official_comparison(records: tuple[EvidenceRecord, ...]) -> str:
    if not records:
        return (
            '<section class="official-comparison" data-official-source-comparison="empty">'
            "<h5>Official-source comparison</h5>"
            '<p class="hint">No official grounding available for this category.</p>'
            "</section>"
        )
    cards = []
    for record in records:
        excerpt = record.excerpt_ko or record.article_ref or "excerpt unavailable"
        cards.append(
            f"""<div class="source-card" data-source-id="{_escape(record.source_id)}"
              data-evidence-id="{_escape(record.evidence_id)}"
              data-authority-tier="{_escape(record.authority_tier.value)}"
              data-verification-status="{_escape(record.verification_status.value)}">
              <span class="badge unverified-badge">{_escape(record.verification_status.value)}</span>
              <p lang="ko">{_escape(excerpt)}</p>
              <small>{_escape(record.source_id)} · {_escape(record.authority_tier.value)}</small>
            </div>"""
        )
    return f"""<section class="official-comparison"
      data-official-source-comparison="true" data-conflicting-sources="side-by-side">
      <h5>Official-source comparison</h5>
      <div class="source-grid">{''.join(cards)}</div>
    </section>"""


def _render_practice_references(references: tuple[PracticeReference, ...]) -> str:
    if not references:
        return (
            '<section class="practice-references" data-practice-reference-section="empty">'
            '<span class="badge" data-practice-reference-badge="true">'
            "practice reference / non-scoring</span>"
            '<p class="hint">No B/C practice reference attached.</p>'
            "</section>"
        )
    items = []
    for reference in references:
        items.append(
            f"""<li data-practice-reference-id="{_escape(reference.reference_id)}"
              data-clause-id="{_escape(reference.clause_id)}" data-score-driver="false">
              <span class="badge" data-practice-reference-badge="true">
                practice reference / non-scoring
              </span>
              <p lang="ko">{_escape(reference.explanation_ko)}</p>
              <p>{_escape(reference.explanation_en_alias)}
                <span class="generated-label">EN generated</span>
              </p>
              <small>{_escape(reference.source_label)}</small>
            </li>"""
        )
    return (
        '<section class="practice-references" data-practice-reference-section="true">'
        "<h5>Plain-language explanation</h5>"
        '<ul class="reference-list">'
        + "\n".join(items)
        + "</ul></section>"
    )


def _render_questions(
    clauses: tuple[ClauseAssessment, ...],
    references: tuple[PracticeReference, ...],
) -> str:
    question_rows: list[tuple[str, str]] = []
    for clause in clauses:
        for question in clause.questions or ():
            question_rows.append((clause.clause_id, question))
    for reference in references:
        for question in reference.questions:
            question_rows.append((reference.clause_id, question))
    if not question_rows:
        return (
            '<section class="questions-before-signing" data-questions-before-signing="empty">'
            "<h5>Questions before signing</h5>"
            '<p class="hint">No checklist question attached.</p>'
            "</section>"
        )
    rows = "\n".join(
        f"""<li data-clause-id="{_escape(clause_id)}" data-question-non-scoring="true">
          <span class="badge">non-scoring question</span>
          {_escape(question)}
        </li>"""
        for clause_id, question in _dedupe_pairs(question_rows)
    )
    return f"""<section class="questions-before-signing"
      data-questions-before-signing="true">
      <h5>Questions before signing</h5>
      <ul>{rows}</ul>
    </section>"""


def _render_context_section(cross_cutting_signals: tuple[RiskSignal, ...]) -> str:
    signals_by_category: dict[RiskCategory, list[RiskSignal]] = {
        category: [] for category in CROSS_CUTTING_CATEGORY_ORDER
    }
    for signal in cross_cutting_signals:
        category = _coerce_category(signal.risk_category)
        if category in signals_by_category:
            signals_by_category[category].append(signal)
    rows = []
    for category in CROSS_CUTTING_CATEGORY_ORDER:
        signals = signals_by_category[category]
        active = any(signal.fired for signal in signals)
        rows.append(
            f"""<li data-risk-category="{category.value}" data-score-driver="false"
              data-score-eligible="false" data-active="{str(active).lower()}">
              <strong>{category.value}</strong> {_escape(CATEGORY_LABELS[category])}
              <span class="badge">context / non-scoring</span>
            </li>"""
        )
    return f"""<section class="non-scoring-context"
      aria-labelledby="non-scoring-context-heading"
      data-non-scoring-section="X1-X5"
      data-context-categories="{_category_codes(CROSS_CUTTING_CATEGORY_ORDER)}">
      <h3 id="non-scoring-context-heading">Context (non-scoring)</h3>
      <ul>{''.join(rows)}</ul>
    </section>"""


def _render_list(data_name: str, items: tuple[str, ...]) -> str:
    if not items:
        return ""
    rows = "".join(f"<li>{_escape(item)}</li>" for item in items)
    return f'<ul data-list="{_escape(data_name)}">{rows}</ul>'


def _active_financial_categories(report: AnalysisReport) -> tuple[RiskCategory, ...]:
    active: set[RiskCategory] = set()
    for category, score in report.assessment.category_scores.items():
        coerced = _coerce_category(category)
        if coerced in FINANCIAL_RISK_CATEGORIES and score > 0:
            active.add(coerced)
    for clause in report.assessment.clause_assessments:
        for signal in clause.signals:
            category = _coerce_category(signal.risk_category)
            if signal.fired and category in FINANCIAL_RISK_CATEGORIES:
                active.add(category)
    return _sort_categories(active, FINANCIAL_CATEGORY_ORDER)


def _signals_for_category(report: AnalysisReport, category: RiskCategory) -> tuple[RiskSignal, ...]:
    signals = []
    for clause in report.assessment.clause_assessments:
        for signal in clause.signals:
            if signal.fired and _coerce_category(signal.risk_category) is category:
                signals.append(signal)
    return tuple(signals)


def _official_records_for_category(
    report: AnalysisReport,
    category: RiskCategory,
    records: tuple[EvidenceRecord, ...],
) -> tuple[EvidenceRecord, ...]:
    ids = _evidence_ids_for_category(report, category)
    selected = [
        record
        for record in records
        if record.evidence_id in ids
        or category in tuple(_coerce_category(cat) for cat in record.risk_categories)
    ]
    return tuple(
        sorted(
            selected,
            key=lambda record: (
                _authority_sort_value(record.authority_tier.value),
                record.source_id,
                record.evidence_id,
            ),
        )
    )


def _evidence_ids_for_category(report: AnalysisReport, category: RiskCategory) -> set[str]:
    ids: set[str] = set()
    for clause in report.assessment.clause_assessments:
        if any(_coerce_category(signal.risk_category) is category for signal in clause.signals):
            ids.update(clause.evidence_ids or ())
            for signal in clause.signals:
                if _coerce_category(signal.risk_category) is category:
                    ids.update(signal.grounding_evidence_ids or ())
    return ids


def _coerce_category(category: RiskCategory | str) -> RiskCategory:
    if isinstance(category, RiskCategory):
        return category
    raw = str(category).strip()
    if raw in RiskCategory.__members__:
        return RiskCategory[raw]
    if raw[:2] in {item.value for item in RiskCategory}:
        return RiskCategory(raw[:2])
    return RiskCategory(raw)


def _sort_categories(
    categories: set[RiskCategory],
    order: tuple[RiskCategory, ...],
) -> tuple[RiskCategory, ...]:
    order_index = {category: idx for idx, category in enumerate(order)}
    return tuple(sorted(categories, key=lambda category: order_index[category]))


def _dedupe_pairs(items: list[tuple[str, str]]) -> tuple[tuple[str, str], ...]:
    seen: set[tuple[str, str]] = set()
    deduped: list[tuple[str, str]] = []
    for item in items:
        if item not in seen:
            deduped.append(item)
            seen.add(item)
    return tuple(deduped)


def _category_codes(categories: tuple[RiskCategory, ...]) -> str:
    return " ".join(category.value for category in categories)


def _authority_sort_value(tier: str) -> int:
    return {"A0": 0, "A1": 1, "A2": 2}.get(tier, 99)


def _money(value: Decimal | int | float | None) -> str:
    if value is None:
        return "blank"
    amount = Decimal(str(value))
    return f"KRW {amount:,.0f}"


def _format_optional_number(value: Any, unit: str) -> str:
    if value is None:
        return "not extracted"
    return f"{value} {unit}"


def _empty_dimension_title(dimension_id: str) -> str:
    return {
        "review-priority-score": "Review Priority Score",
        "monetary-exposure-range": "Monetary Exposure Range",
        "time-exposure": "Time Exposure",
        "evidence-ocr-confidence": "Evidence & OCR Confidence",
    }[dimension_id]


def _empty_dimension_hint(dimension_id: str) -> str:
    return {
        "review-priority-score": "0-100 ordinal review priority appears here.",
        "monetary-exposure-range": "Low / base / high ranges stay separate by exposure type.",
        "time-exposure": "Typed timing fields and pathway labels appear here.",
        "evidence-ocr-confidence": "UNVERIFIED source status and OCR confidence appear here.",
    }[dimension_id]


def _escape(value: object) -> str:
    return html.escape(str(value), quote=True)

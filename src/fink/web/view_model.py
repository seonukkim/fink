from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from fink.knowledge.checkpoints import (
    CHECKLIST_SOURCE_NOTE,
    curated_checklist_for_category,
)
from fink.schemas import ExportFormat, RiskCategory, UILocale
from fink.web.source_highlights import (
    build_source_highlight_payload,
    empty_source_highlights,
)
from fink.web.qa import build_grounded_qa_payload, empty_grounded_qa_payload
from fink.signals.verification import (
    empty_verification_payload,
    verification_payload,
)

VIEW_MODEL_NAME = "CreatorReviewViewModel"
VIEW_MODEL_SCHEMA_VERSION = 1

READING_STATUS = "reading_status"
EVIDENCE_STATUS = "evidence_status"
SCENARIO_STATUS = "scenario_status"
QUANTIFICATION_STATUS = "quantification_status"

FINDING_STATE_KEYS = (
    "money_state",
    "timing_state",
    "reading_state",
    "evidence_state",
    "scenario_state",
    "quantification_state",
)

CREATOR_REVIEW_REQUIRED_COPY_KEYS = (
    "app.review_priority_label",
    "app.summary_heading",
    "app.recommendation_heading",
    "app.findings_heading",
    "app.source_clause_label",
    "app.exact_excerpt_label",
    "dimension.review_priority",
    "dimension.money",
    "dimension.time",
    "dimension.evidence",
    "status.reading.review_needed",
    "status.reading.no_prominent_signal",
    "status.evidence.unverified",
    "status.scenario.needs_inputs",
    "status.scenario.inputs_present",
    "status.quantification.not_quantified",
    "status.quantification.range_available",
    "status.money.needs_inputs",
    "status.money.range_available",
    "status.timing.review_time_estimated",
    "status.timing.contract_timing_missing",
    "status.currency.needs_confirmation",
    "status.currency.krw_assumed",
    "section.why_check",
    "section.wording",
    "section.impact",
    "section.question",
    "section.evidence",
    "section.detail",
    "verification.section_title",
    "verification.section_hint",
    "verification.empty",
    "action.copy_question",
    "action.open_source",
    "diagnostic.rule_focus_index",
    "diagnostic.rule_focus_note",
    "finding.priority_basis.missing_protection",
    "finding.priority_basis.detected_term",
    "finding.priority_basis.quantified_exposure",
    "finding.priority_basis.present_value_timing",
    "finding.priority_basis.uncapped_or_unbounded",
    "finding.priority_basis.counterparty_verification",
    "finding.priority_basis.grounded_qualitative_signal",
    "finding.priority_basis.unverified_candidate",
    "finding.model_path.local_rules",
    "export.audit_detail_label",
)

_COPY: dict[str, dict[str, str]] = {
    "app.review_priority_label": {
        "ko": "계약 금융 검토",
        "en": "Contractual Financial Review Priority",
    },
    "app.summary_heading": {
        "ko": "지금 먼저 확인할 것",
        "en": "Check first now",
    },
    "app.recommendation_heading": {
        "ko": "지금 먼저 확인할 것",
        "en": "Check first now",
    },
    "app.findings_heading": {
        "ko": "서명 전에 확인할 항목",
        "en": "Items to check before signing",
    },
    "app.source_clause_label": {
        "ko": "출처 조항",
        "en": "Source clause",
    },
    "app.exact_excerpt_label": {
        "ko": "정확한 발췌",
        "en": "Exact excerpt",
    },
    "dimension.review_priority": {
        "ko": "검토 순서",
        "en": "Review order",
    },
    "dimension.money": {
        "ko": "현금흐름 영향",
        "en": "Cash-flow impact",
    },
    "dimension.time": {
        "ko": "시점",
        "en": "Timing",
    },
    "dimension.evidence": {
        "ko": "판독 상태",
        "en": "Reading status",
    },
    "status.reading.review_needed": {
        "ko": "검토 필요",
        "en": "Needs review",
    },
    "status.reading.no_prominent_signal": {
        "ko": "두드러진 신호 없음",
        "en": "No prominent signal",
    },
    "status.evidence.unverified": {
        "ko": "근거 미확인",
        "en": "Official evidence unverified",
    },
    "status.scenario.needs_inputs": {
        "ko": "입력 필요",
        "en": "Input needed",
    },
    "status.scenario.inputs_present": {
        "ko": "입력 반영",
        "en": "Inputs included",
    },
    "status.quantification.not_quantified": {
        "ko": "상한 미확정",
        "en": "Upper bound not set",
    },
    "status.quantification.range_available": {
        "ko": "범위 계산됨",
        "en": "Low/base/high range available",
    },
    "status.money.needs_inputs": {
        "ko": "입력 필요",
        "en": "Input needed",
    },
    "status.money.range_available": {
        "ko": "범위 계산됨",
        "en": "Range available",
    },
    "status.timing.review_time_estimated": {
        "ko": "계약 시점 확인",
        "en": "Contract timing to check",
    },
    "status.timing.contract_timing_missing": {
        "ko": "시점 입력 필요",
        "en": "Timing input needed",
    },
    "status.currency.needs_confirmation": {
        "ko": "통화 확인 필요",
        "en": "Currency needs confirmation",
    },
    "status.currency.krw_assumed": {
        "ko": "KRW 기준",
        "en": "KRW basis",
    },
    "section.why_check": {
        "ko": "왜 확인",
        "en": "Why check",
    },
    "section.wording": {
        "ko": "문구",
        "en": "Wording",
    },
    "section.impact": {
        "ko": "영향",
        "en": "Impact",
    },
    "section.question": {
        "ko": "물어볼 말",
        "en": "Question to ask",
    },
    "section.evidence": {
        "ko": "근거",
        "en": "Evidence",
    },
    "section.detail": {
        "ko": "상세",
        "en": "Detail",
    },
    "verification.section_title": {
        "ko": "상대방·지급 경로 확인 신호",
        "en": "Counterparty and payment-route verification signals",
    },
    "verification.section_hint": {
        "ko": "서명·이체 전 상대방과 지급 경로를 독립적으로 확인하세요. 이 영역은 검토 점수와 별도입니다.",
        "en": (
            "Before signing or transferring money, independently verify the "
            "counterparty and payment route. This area is separate from the review score."
        ),
    },
    "verification.empty": {
        "ko": "이 입력에서는 별도 상대방·지급 경로 확인 신호가 없습니다.",
        "en": "No separate counterparty or payment-route verification signal appears in this input.",
    },
    "action.copy_question": {
        "ko": "물어볼 말 복사",
        "en": "Copy question",
    },
    "action.open_source": {
        "ko": "원문으로 이동",
        "en": "Open in source",
    },
    "diagnostic.rule_focus_index": {
        "ko": "규칙 기반 검토 집중도 지수",
        "en": "Rule-based review focus index",
    },
    "diagnostic.rule_focus_note": {
        "ko": "숫자가 높을수록 먼저·꼼꼼히 살펴볼 항목이 많다는 뜻입니다.",
        "en": "A higher number means more items should be reviewed earlier and more carefully.",
    },
    "finding.priority_basis.missing_protection": {
        "ko": "보호 조항이 빠졌거나 약해 보여 먼저 볼 항목으로 정렬했습니다.",
        "en": "Prioritized because a protective term appears missing or weak.",
    },
    "finding.priority_basis.detected_term": {
        "ko": "현금흐름에 영향을 줄 수 있는 조건으로 감지되어 먼저 볼 항목으로 정렬했습니다.",
        "en": "Prioritized because the term may affect creator cash flow.",
    },
    "finding.priority_basis.quantified_exposure": {
        "ko": "입력된 금액 가정에서 같은 유형의 노출 범위가 계산되어 먼저 볼 항목입니다.",
        "en": "Prioritized from a computed range within the same exposure type.",
    },
    "finding.priority_basis.present_value_timing": {
        "ko": "지급 시점의 현재가치 영향이 계산되어 먼저 볼 항목입니다.",
        "en": "Prioritized from a computed present-value timing effect.",
    },
    "finding.priority_basis.uncapped_or_unbounded": {
        "ko": "상한이 없거나 범위를 정할 수 없어 별도 우선 검토 항목입니다.",
        "en": "Prioritized as a separate uncapped or unbounded review item.",
    },
    "finding.priority_basis.counterparty_verification": {
        "ko": "상대방 정산·증빙 확인이 필요한 항목으로 먼저 볼 항목입니다.",
        "en": "Prioritized because counterparty records or verification are needed.",
    },
    "finding.priority_basis.grounded_qualitative_signal": {
        "ko": "공식 근거가 연결된 정성 신호로 먼저 확인할 항목입니다.",
        "en": "Prioritized as an official-grounded qualitative signal.",
    },
    "finding.priority_basis.unverified_candidate": {
        "ko": "공식 근거 연결이 필요한 미확인 후보입니다.",
        "en": "An unverified candidate that needs official-source grounding.",
    },
    "finding.model_path.local_rules": {
        "ko": "기기 내 규칙 기반 검토 경로",
        "en": "Local deterministic rule review path",
    },
    "export.audit_detail_label": {
        "ko": "감사 세부정보",
        "en": "Audit detail",
    },
    "category.settlement_audit": {
        "ko": "정산 투명성·감사권",
        "en": "Settlement transparency and audit",
    },
    "category.revenue_deductions": {
        "ko": "매출 기준·공제",
        "en": "Revenue base and deductions",
    },
    "category.payment_cashflow": {
        "ko": "지급 시기·현금흐름",
        "en": "Payment timing and cash flow",
    },
    "category.mg_recoupment": {
        "ko": "미니멈 개런티·선급금 회수",
        "en": "Minimum guarantee and advance recoupment",
    },
    "category.ip_monetization": {
        "ko": "저작권·2차적저작물 수익화",
        "en": "IP and secondary-rights monetization",
    },
    "category.term_exclusivity": {
        "ko": "기간·독점·기회비용",
        "en": "Term, exclusivity, and opportunity cost",
    },
    "category.termination_liability": {
        "ko": "해지·손해배상·위약금",
        "en": "Termination, liability, and penalties",
    },
    "category.scope_cost": {
        "ko": "업무범위 확대·제작비",
        "en": "Scope creep and production cost",
    },
    "category.econtract_privacy": {
        "ko": "전자계약·개인정보·증거보존",
        "en": "E-contract, privacy, and evidence integrity",
    },
}

_CATEGORY_COPY_KEY = {
    "F1": "category.settlement_audit",
    "F2": "category.revenue_deductions",
    "F3": "category.payment_cashflow",
    "F4": "category.mg_recoupment",
    "F5": "category.ip_monetization",
    "F6": "category.term_exclusivity",
    "F7": "category.termination_liability",
    "F8": "category.scope_cost",
    "F9": "category.econtract_privacy",
}

_RISK_TO_PRIMARY_FIM = {
    "F1": "FIM-1",
    "F2": "FIM-1",
    "F3": "FIM-2",
    "F4": "FIM-3",
    "F5": "FIM-6",
    "F6": "FIM-5",
    "F7": "FIM-7",
    "F8": "FIM-4",
    "F9": "FIM-8",
}

_LOCAL_MODEL_PATH = {
    "ko": "기기 내 OCR/분절/규칙 신호/검토 순서 뷰모델",
    "en": "Local OCR, segmentation, rule-signal, and review-priority view model",
}


@dataclass(frozen=True)
class CreatorReviewViewModel:
    ui_locale: UILocale
    summary: dict[str, str]
    recommendation: dict[str, dict[str, str]]
    statuses: dict[str, dict[str, Any]]
    dimensions: dict[str, Any]
    findings: tuple[dict[str, Any], ...]
    audit_detail: dict[str, Any]
    verification: dict[str, Any] | None = None
    scenario_inputs: dict[str, Any] | None = None
    source_highlights: dict[str, Any] | None = None
    grounded_qa: dict[str, Any] | None = None
    model_status: dict[str, Any] | None = None
    local_only: bool = True
    schema_version: int = VIEW_MODEL_SCHEMA_VERSION
    view_model: str = VIEW_MODEL_NAME

    def to_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "view_model": self.view_model,
            "local_only": self.local_only,
            "ui_locale": self.ui_locale.value,
            "copy": creator_review_copy_payload(),
            "summary": self.summary,
            "recommendation": self.recommendation,
            "statuses": self.statuses,
            "dimensions": self.dimensions,
            "findings": list(self.findings),
            "verification": self.verification or empty_verification_payload(),
            "source_highlights": self.source_highlights or empty_source_highlights(),
            "grounded_qa": self.grounded_qa or empty_grounded_qa_payload(),
            "scenario_inputs": self.scenario_inputs or _scenario_inputs_from_audit({}),
            "model_status": self.model_status or _fallback_model_status(),
            "audit_detail": self.audit_detail,
        }


def creator_review_required_copy_keys() -> tuple[str, ...]:
    return CREATOR_REVIEW_REQUIRED_COPY_KEYS


def creator_review_copy_payload() -> dict[str, dict[str, Any]]:
    return {
        key: {"ko": value["ko"], "en": value["en"], "en_generated": True}
        for key, value in sorted(_COPY.items())
    }


def creator_review_pair(key: str) -> dict[str, str]:
    value = _COPY[key]
    return {"ko": value["ko"], "en": value["en"]}


def build_creator_review_view_model(result: Any, locale: UILocale | str) -> CreatorReviewViewModel:
    ui_locale = _coerce_locale(locale)
    statuses = _statuses(
        has_findings=bool(result.ranked_findings),
        monetary_present=bool(result.monetary_present),
    )
    used_checkpoints: set[str] = set()
    findings = tuple(
        _with_practice_checklist(
            _finding_from_ranked(item, result, statuses),
            item.risk_category,
            used_checkpoints,
        )
        for item in result.ranked_findings
    )
    findings, source_highlights = build_source_highlight_payload(
        source_pages=tuple(getattr(result, "source_pages", ())),
        clauses=tuple(getattr(result, "clauses", ())),
        findings=findings,
    )
    grounded_qa = build_grounded_qa_payload(findings)
    dimensions = _dimensions_from_result(result, statuses)
    audit_detail = _audit_detail_from_result(result)
    scenario_inputs = _scenario_inputs_from_audit(
        audit_detail,
        getattr(result, "scenario_input_values", {}),
    )
    verification = _verification_from_result(result)
    return CreatorReviewViewModel(
        ui_locale=ui_locale,
        summary=_summary_from_result(result),
        recommendation={
            "action": {
                "ko": result.recommended_action.action_ko,
                "en": result.recommended_action.action_en,
            },
            "cash_flow": {
                "ko": result.recommended_action.cash_flow_ko,
                "en": result.recommended_action.cash_flow_en,
            },
        },
        statuses=statuses,
        dimensions=dimensions,
        findings=findings,
        verification=verification,
        audit_detail=audit_detail,
        scenario_inputs=scenario_inputs,
        source_highlights=source_highlights,
        grounded_qa=grounded_qa,
        model_status=_model_status_from_result(result),
    )


def build_creator_review_view_model_from_report(
    report: Any,
    *,
    ui_locale: UILocale | str = UILocale.KO,
    evidence_records: tuple[Any, ...] = (),
    practice_references: tuple[Any, ...] = (),
    highlighted_evidence: tuple[Any, ...] = (),
) -> CreatorReviewViewModel:
    locale = _coerce_locale(ui_locale)
    assessment = report.assessment
    monetary_present = any(
        not exposure.is_user_input_required for exposure in assessment.monetary_exposures
    )
    signals = [
        signal
        for clause in assessment.clause_assessments
        for signal in clause.signals
        if signal.fired
    ]
    statuses = _statuses(has_findings=bool(signals), monetary_present=monetary_present)
    recommendation = _report_recommendation(assessment.time_exposure.pathway_label.value)
    used_checkpoints: set[str] = set()
    findings = tuple(
        _with_practice_checklist(
            _finding_from_signal(
                signal,
                rank=index,
                report=report,
                statuses=statuses,
                evidence_records=evidence_records,
                practice_references=practice_references,
                highlighted_evidence=highlighted_evidence,
            ),
            signal.risk_category,
            used_checkpoints,
        )
        for index, signal in enumerate(signals, start=1)
    )
    audit_detail = {
        "export_format": report.export_format.value
        if isinstance(report.export_format, ExportFormat)
        else str(report.export_format),
        "clause_count": len(assessment.clause_assessments),
        "signal_count": len(signals),
        "grounding": "UNVERIFIED",
        "model_path": _LOCAL_MODEL_PATH,
        "scoring": {
            "review_priority_score": assessment.review_priority_score,
            "category_scores": _category_scores_to_audit(assessment.category_scores),
            "confidence": {
                "ocr_confidence": assessment.confidence.ocr_confidence,
                "evidence_confidence": assessment.confidence.evidence_confidence,
                "data_completeness": assessment.confidence.data_completeness,
                "overall_confidence": assessment.confidence.overall_confidence,
            },
            "scoring_config_version": assessment.scoring_config_version,
        },
        "time": {
            "runtime_s": assessment.time_exposure.measured_analysis_runtime_seconds,
            "pathway_label": assessment.time_exposure.pathway_label.value,
        },
        "technical_findings": [
            _technical_finding_from_signal(signal, index)
            for index, signal in enumerate(signals, start=1)
        ],
        "monetary_exposures": [_exposure_to_audit(exposure) for exposure in assessment.monetary_exposures],
        "execution_path": getattr(report, "execution_path", _fallback_execution_path()),
    }
    grounded_qa = build_grounded_qa_payload(findings)
    return CreatorReviewViewModel(
        ui_locale=locale,
        summary={
            "ko": "합성 예시 보고서는 먼저 볼 금융 조건을 한 화면에 정리합니다.",
            "en": "This synthetic report organizes the financial terms to review first.",
        },
        recommendation=recommendation,
        statuses=statuses,
        dimensions=_dimensions_from_report(report, statuses),
        findings=findings,
        verification=empty_verification_payload(),
        audit_detail=audit_detail,
        scenario_inputs=_scenario_inputs_from_audit(audit_detail),
        source_highlights=empty_source_highlights(),
        grounded_qa=grounded_qa,
        model_status=audit_detail["execution_path"]["model_status"],
    )


def build_project_page_synthetic_view_model(
    *, ui_locale: UILocale | str = UILocale.KO
) -> CreatorReviewViewModel:
    locale = _coerce_locale(ui_locale)
    statuses = _statuses(has_findings=True, monetary_present=False)
    finding = {
        "finding_id": "finding-synthetic-settlement",
        "rank": 1,
        "title": creator_review_pair("category.revenue_deductions"),
        "source": {
            "clause_id": "synthetic-clause-settlement",
            "exact_excerpt": (
                "제3조(정산) 정산은 매 분기 종료일로부터 90일 이내에 지급하며, "
                "회사는 일반 경비를 공제할 수 있다."
            ),
        },
        "why_it_matters": {
            "ko": "공제 항목이 열려 있으면 실제 수령액을 확인하기 어렵습니다.",
            "en": "Open deduction wording can make the actual payout hard to check.",
        },
        "question_to_ask": {
            "ko": "공제 항목을 계약서에 구체적으로 적을 수 있나요?",
            "en": "Can each deduction item be listed in the contract?",
        },
        "cash_flow_consequence": {
            "ko": "공제 범위에 따라 실수령액이 달라질 수 있습니다.",
            "en": "The creator's net payout can change depending on deduction scope.",
        },
        "states": _finding_states(statuses, monetary_present=False),
        "priority_basis": creator_review_pair("finding.priority_basis.missing_protection"),
        "extracted_fields": [],
        "missing_inputs": _missing_inputs(False),
        "citations": [],
        "model_path": creator_review_pair("finding.model_path.local_rules"),
    }
    finding = _with_practice_checklist(finding, "F2", set())
    audit_detail = {
        "synthetic_example": True,
        "grounding": "UNVERIFIED",
        "model_path": _LOCAL_MODEL_PATH,
        "technical_findings": [
            {
                "finding_id": finding["finding_id"],
                "signal_id": "synthetic-signal",
                "risk_category": "F2",
                "fim_module": "FIM-1",
            }
        ],
        "execution_path": _fallback_execution_path(),
    }
    return CreatorReviewViewModel(
        ui_locale=locale,
        summary={
            "ko": "프로젝트 페이지용 합성 예시는 실제 계약이 아닌 공개 가능한 예시입니다.",
            "en": "The project-page example is synthetic and safe to publish.",
        },
        recommendation={
            "action": {
                "ko": "서명 전 정산 기준과 공제 항목을 확인하세요.",
                "en": "Before signing, clarify the settlement basis and deductions.",
            },
            "cash_flow": {
                "ko": "실수령액이 달라질 수 있으므로 금액 가정을 입력해 보세요.",
                "en": "Try scenario assumptions because net payout may change.",
            },
        },
        statuses=statuses,
        dimensions={
            "review_priority": {
                "label": creator_review_pair("dimension.review_priority"),
                "score": 0,
                "reading_status": statuses[READING_STATUS],
            },
            "monetary": {
                "label": creator_review_pair("dimension.money"),
                "scenario_status": statuses[SCENARIO_STATUS],
                "quantification_status": statuses[QUANTIFICATION_STATUS],
                "currency_status": creator_review_pair("status.currency.needs_confirmation"),
                "ranges": [],
            },
            "time": {
                "label": creator_review_pair("dimension.time"),
                "timing_state": creator_review_pair("status.timing.review_time_estimated"),
                "contract_timing": {
                    "ko": "지급 시점과 계약 기간을 계약서에서 확인하세요.",
                    "en": "Check payment timing and contract duration in the contract.",
                },
            },
            "evidence": {
                "label": creator_review_pair("dimension.evidence"),
                "reading_status": statuses[READING_STATUS],
                "evidence_status": statuses[EVIDENCE_STATUS],
            },
        },
        findings=(finding,),
        verification=empty_verification_payload(),
        audit_detail=audit_detail,
        scenario_inputs=_scenario_inputs_from_audit(audit_detail),
        source_highlights=empty_source_highlights(),
        grounded_qa=build_grounded_qa_payload((finding,)),
        model_status=audit_detail["execution_path"]["model_status"],
    )


def creator_review_payload_from_result(result: Any, locale: UILocale | str) -> dict[str, Any]:
    return build_creator_review_view_model(result, locale).to_payload()


def export_creator_review_json(view_model: CreatorReviewViewModel) -> str:
    return json.dumps(view_model.to_payload(), ensure_ascii=False, indent=2, sort_keys=True)


def export_creator_review_markdown(view_model: CreatorReviewViewModel) -> str:
    payload = view_model.to_payload()
    lines = [
        f"# {payload['copy']['app.review_priority_label']['ko']}",
        "",
        f"## {payload['copy']['app.summary_heading']['ko']}",
        payload["summary"]["ko"],
        "",
        f"## {payload['copy']['app.recommendation_heading']['ko']}",
        payload["recommendation"]["action"]["ko"],
        payload["recommendation"]["cash_flow"]["ko"],
        "",
        "## 상태",
    ]
    for key in (READING_STATUS, EVIDENCE_STATUS, SCENARIO_STATUS, QUANTIFICATION_STATUS):
        status = payload["statuses"][key]
        lines.append(f"- {status['label']['ko']}: {status['state']}")
    lines.extend(["", f"## {payload['copy']['app.findings_heading']['ko']}"])
    for finding in payload["findings"]:
        lines.extend(
            [
                f"- {finding['rank']}. {finding['title']['ko']} ({finding['finding_id']})",
                f"  - 출처 조항: {finding['source']['clause_id']}",
                f"  - 정확한 발췌: {finding['source']['exact_excerpt']}",
                f"  - 확인 질문: {finding['question_to_ask']['ko']}",
            ]
        )
    verification = payload.get("verification") or {}
    verification_signals = verification.get("signals") or []
    if verification_signals:
        lines.extend(["", f"## {verification['section_title']['ko']}"])
        lines.append(verification["section_hint"]["ko"])
        for signal in verification_signals:
            lines.extend(
                [
                    f"- {signal['label']['ko']} ({signal['signal_id']})",
                    f"  - 확인 문구: {signal['instruction']['ko']}",
                    "  - 검토 점수 반영: 0",
                ]
            )
    lines.extend(["", f"## {payload['copy']['export.audit_detail_label']['ko']}"])
    lines.append("기술 세부정보는 JSON 내 audit_detail에만 포함됩니다.")
    return "\n".join(lines).strip() + "\n"


def _statuses(*, has_findings: bool, monetary_present: bool) -> dict[str, dict[str, Any]]:
    reading_key = (
        "status.reading.review_needed" if has_findings else "status.reading.no_prominent_signal"
    )
    scenario_key = (
        "status.scenario.inputs_present" if monetary_present else "status.scenario.needs_inputs"
    )
    quantification_key = (
        "status.quantification.range_available"
        if monetary_present
        else "status.quantification.not_quantified"
    )
    return {
        READING_STATUS: {
            "state": "review_needed" if has_findings else "no_prominent_signal",
            "label": creator_review_pair(reading_key),
        },
        EVIDENCE_STATUS: {
            "state": "unverified",
            "label": creator_review_pair("status.evidence.unverified"),
        },
        SCENARIO_STATUS: {
            "state": "inputs_present" if monetary_present else "needs_inputs",
            "label": creator_review_pair(scenario_key),
        },
        QUANTIFICATION_STATUS: {
            "state": "range_available" if monetary_present else "not_quantified",
            "label": creator_review_pair(quantification_key),
        },
    }


def _summary_from_result(result: Any) -> dict[str, str]:
    finding_count = len(result.ranked_findings)
    return {
        "ko": (
            "이 화면은 법률 자문이 아닌 계약상 금융 검토 항목 정리입니다. "
            f"먼저 볼 발견사항 {finding_count}건을 정리했습니다. "
            f"{result.recommended_action.cash_flow_ko}"
        ),
        "en": (
            "This screen is a Contractual Financial Review Priority aid, not legal advice. "
            f"It organizes {finding_count} findings to review first. "
            f"{result.recommended_action.cash_flow_en}"
        ),
    }


def _dimensions_from_result(result: Any, statuses: dict[str, dict[str, Any]]) -> dict[str, Any]:
    time_exposure = result.time_result.time_exposure
    money_ranges = [_money_range_payload(exposure) for exposure in result.exposures if not exposure.is_user_input_required]
    has_contract_timing = _has_contract_timing(time_exposure)
    return {
        "review_priority": {
            "label": creator_review_pair("dimension.review_priority"),
            "score": result.review_priority_score,
            "official_support": int(
                getattr(result.scoring, "verified_support_count", 0)
            ),
            "practice_support": int(
                getattr(result.scoring, "practice_support_count", 0)
            ),
            "reading_status": statuses[READING_STATUS],
        },
        "monetary": {
            "label": creator_review_pair("dimension.money"),
            "scenario_status": statuses[SCENARIO_STATUS],
            "quantification_status": statuses[QUANTIFICATION_STATUS],
            "currency_status": creator_review_pair("status.currency.needs_confirmation"),
            "ranges": money_ranges,
            "note": {"ko": result.monetary_note_ko, "en": result.monetary_note_en},
        },
        "time": {
            "label": creator_review_pair("dimension.time"),
            "timing_state": creator_review_pair(
                "status.timing.review_time_estimated"
                if has_contract_timing
                else "status.timing.contract_timing_missing"
            ),
            "estimated_human_review_minutes": time_exposure.estimated_human_review_minutes,
            "contract_timing": _contract_timing_payload(time_exposure),
            "cash_flow_consequence": {
                "ko": result.recommended_action.cash_flow_ko,
                "en": result.recommended_action.cash_flow_en,
            },
        },
        "evidence": {
            "label": creator_review_pair("dimension.evidence"),
            "reading_status": statuses[READING_STATUS],
            "evidence_status": statuses[EVIDENCE_STATUS],
        },
    }


def _dimensions_from_report(report: Any, statuses: dict[str, dict[str, Any]]) -> dict[str, Any]:
    assessment = report.assessment
    ranges = [
        _money_range_payload(exposure)
        for exposure in assessment.monetary_exposures
        if not exposure.is_user_input_required
    ]
    has_contract_timing = _has_contract_timing(assessment.time_exposure)
    return {
        "review_priority": {
            "label": creator_review_pair("dimension.review_priority"),
            "score": assessment.review_priority_score,
            "official_support": int(getattr(assessment, "verified_support_count", 0)),
            "practice_support": int(getattr(assessment, "practice_support_count", 0)),
            "reading_status": statuses[READING_STATUS],
        },
        "monetary": {
            "label": creator_review_pair("dimension.money"),
            "scenario_status": statuses[SCENARIO_STATUS],
            "quantification_status": statuses[QUANTIFICATION_STATUS],
            "currency_status": creator_review_pair("status.currency.needs_confirmation"),
            "ranges": ranges,
        },
        "time": {
            "label": creator_review_pair("dimension.time"),
            "timing_state": creator_review_pair(
                "status.timing.review_time_estimated"
                if has_contract_timing
                else "status.timing.contract_timing_missing"
            ),
            "estimated_human_review_minutes": assessment.time_exposure.estimated_human_review_minutes,
            "contract_timing": _contract_timing_payload(assessment.time_exposure),
        },
        "evidence": {
            "label": creator_review_pair("dimension.evidence"),
            "reading_status": statuses[READING_STATUS],
            "evidence_status": statuses[EVIDENCE_STATUS],
        },
    }


def _finding_from_ranked(
    finding: Any,
    result: Any,
    statuses: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    guidance = _guidance_for_category(result.category_guidance, finding.risk_category)
    monetary_present = bool(result.monetary_present)
    question = _first_question(guidance)
    title = {"ko": finding.label_ko, "en": finding.label_en}
    finding_id = _stable_id("finding", finding.signal_id, finding.clause_id, finding.exact_excerpt)
    evidence = _evidence_payload_from_ranked(finding)
    return {
        "finding_id": finding_id,
        "rank": finding.rank,
        "title": title,
        "source": {
            "clause_id": finding.clause_id,
            "clause_heading": finding.clause_heading or "",
            "exact_excerpt": finding.exact_excerpt,
        },
        "why_it_matters": _why_it_matters(guidance, finding.risk_category),
        "question_to_ask": question,
        "additional_questions": [],
        "cash_flow_consequence": {
            "ko": result.recommended_action.cash_flow_ko,
            "en": result.recommended_action.cash_flow_en,
        },
        "states": _finding_states(
            statuses,
            monetary_present=monetary_present,
            evidence_state=evidence["state"],
        ),
        "priority_basis": _priority_basis_from_ranked(finding),
        "priority_basis_code": finding.priority_basis,
        "quantification_status": finding.quantification_status,
        "exposure_type": finding.exposure_type,
        "extracted_fields": [],
        "missing_inputs": _missing_inputs(monetary_present),
        "evidence": evidence,
        "citations": list(finding.citations),
        "model_path": creator_review_pair("finding.model_path.local_rules"),
    }


def _finding_from_signal(
    signal: Any,
    *,
    rank: int,
    report: Any,
    statuses: dict[str, dict[str, Any]],
    evidence_records: tuple[Any, ...],
    practice_references: tuple[Any, ...],
    highlighted_evidence: tuple[Any, ...],
) -> dict[str, Any]:
    category = _category_code(signal.risk_category)
    excerpt = _excerpt_for_clause(signal.clause_id, highlighted_evidence)
    monetary_present = any(
        not exposure.is_user_input_required
        for exposure in report.assessment.monetary_exposures
    )
    questions = _questions_from_report(report, signal.clause_id, practice_references)
    first_question = questions[0] if questions else _first_question(None)
    title = creator_review_pair(_CATEGORY_COPY_KEY.get(category, "dimension.review_priority"))
    return {
        "finding_id": _stable_id("finding", signal.signal_id, signal.clause_id, excerpt),
        "rank": rank,
        "title": title,
        "source": {
            "clause_id": signal.clause_id,
            "clause_heading": _clause_heading_for_signal(signal.clause_id, report),
            "exact_excerpt": excerpt,
        },
        "why_it_matters": _category_why(category),
        "question_to_ask": first_question,
        "additional_questions": questions[1:],
        "cash_flow_consequence": {
            "ko": "조건에 따라 실수령액과 현금 흐름이 달라질 수 있습니다.",
            "en": "Depending on the term, net payout and cash flow may change.",
        },
        "states": _finding_states(statuses, monetary_present=monetary_present),
        "priority_basis": _priority_basis(bool(signal.is_missing_protection)),
        "extracted_fields": [],
        "missing_inputs": _missing_inputs(monetary_present),
        "evidence": _evidence_payload_from_signal(signal),
        "citations": _citations_for_signal(signal, report, evidence_records),
        "model_path": creator_review_pair("finding.model_path.local_rules"),
    }


def _with_practice_checklist(
    finding: dict[str, Any],
    category: Any,
    used_checkpoint_keys: set[str],
) -> dict[str, Any]:
    checklist = curated_checklist_for_category(
        category,
        used_checkpoint_keys=used_checkpoint_keys,
    )
    return {**finding, "checklist": checklist or _empty_practice_checklist()}


def _empty_practice_checklist() -> dict[str, Any]:
    return {
        "topic": {"ko": "", "en": ""},
        "checkpoints": [],
        "source_note": dict(CHECKLIST_SOURCE_NOTE),
        "source_kind": "distilled_general_practice",
        "score_contribution": 0,
        "authority_tiers": [],
        "grounding_evidence_ids": [],
        "non_scoring": True,
    }


def _finding_states(
    statuses: dict[str, dict[str, Any]],
    *,
    monetary_present: bool,
    evidence_state: str | None = None,
) -> dict[str, str]:
    money_state = "range_available" if monetary_present else "needs_inputs"
    return {
        "money_state": money_state,
        "timing_state": "review_time_estimated",
        "reading_state": statuses[READING_STATUS]["state"],
        "evidence_state": evidence_state or statuses[EVIDENCE_STATUS]["state"],
        "scenario_state": statuses[SCENARIO_STATUS]["state"],
        "quantification_state": statuses[QUANTIFICATION_STATUS]["state"],
    }


def _evidence_payload_from_ranked(finding: Any) -> dict[str, Any]:
    if getattr(finding, "scored", False):
        return {
            "state": "official_evidence_unverified",
            "label": {
                "ko": "로컬 공식 근거 연결",
                "en": "Local official evidence linked",
            },
            "grounding_evidence_ids": list(finding.grounding_evidence_ids),
            "authority_tiers": list(finding.authority_tiers),
            "source_ids": list(finding.source_ids),
            "missing": None,
        }
    return {
        "state": "candidate_unverified",
        "label": {"ko": "미확인 후보", "en": "Unverified candidate"},
        "grounding_evidence_ids": [],
        "authority_tiers": [],
        "source_ids": [],
        "missing": {
            "ko": finding.missing_evidence_ko,
            "en": finding.missing_evidence_en,
        },
    }


def _evidence_payload_from_signal(signal: Any) -> dict[str, Any]:
    evidence_ids = list(getattr(signal, "grounding_evidence_ids", ()) or ())
    if evidence_ids:
        return {
            "state": "official_evidence_unverified",
            "label": {
                "ko": "로컬 공식 근거 연결",
                "en": "Local official evidence linked",
            },
            "grounding_evidence_ids": evidence_ids,
            "authority_tiers": [],
            "source_ids": [],
            "missing": None,
        }
    return {
        "state": "candidate_unverified",
        "label": {"ko": "미확인 후보", "en": "Unverified candidate"},
        "grounding_evidence_ids": [],
        "authority_tiers": [],
        "source_ids": [],
        "missing": {
            "ko": "로컬 공식 근거 연결이 필요합니다.",
            "en": "Local official evidence needs to be linked.",
        },
    }


def _audit_detail_from_result(result: Any) -> dict[str, Any]:
    confidence = result.scoring.confidence
    verification = _verification_from_result(result)
    return {
        "clause_count": result.clause_count,
        "signal_count": result.signal_count,
        "grounding": result.grounding,
        "retrieved_record_count": result.retrieved_record_count,
        "evidence_authority_tiers": dict(result.evidence_authority_tiers),
        "model_path": _LOCAL_MODEL_PATH,
        "scoring": {
            "review_priority_score": result.review_priority_score,
            "verified_support_count": int(
                getattr(result.scoring, "verified_support_count", 0)
            ),
            "practice_support_count": int(
                getattr(result.scoring, "practice_support_count", 0)
            ),
            "category_scores": dict(result.category_scores),
            "ranking_policy": result.ranking_policy,
            "authority_gate": result.authority_gate,
            "scoring_config_version": result.scoring.scoring_config_version,
            "confidence": {
                "ocr_confidence": confidence.ocr_confidence,
                "evidence_confidence": confidence.evidence_confidence,
                "data_completeness": confidence.data_completeness,
                "overall_confidence": confidence.overall_confidence,
            },
        },
        "time": {
            "runtime_s": result.measured_runtime_seconds,
            "pathway_label": result.recommended_action.pathway_label,
        },
        "technical_findings": [
            _technical_finding_from_ranked(finding) for finding in result.ranked_findings
        ],
        "verification": {
            "signal_count": verification["signal_count"],
            "score_contribution": verification["score_contribution"],
            "separate_from_review_priority_score": verification[
                "separate_from_review_priority_score"
            ],
            "signals": [
                {
                    "signal_id": signal["signal_id"],
                    "signal_type": signal["signal_type"],
                    "support": signal["support"],
                    "score_contribution": signal["score_contribution"],
                    "separate_from_review_priority_score": signal[
                        "separate_from_review_priority_score"
                    ],
                }
                for signal in verification["signals"]
            ],
        },
        "monetary_exposures": [_exposure_to_audit(exposure) for exposure in result.exposures],
        "execution_path": getattr(result, "execution_path", _fallback_execution_path()),
    }


def _verification_from_result(result: Any) -> dict[str, Any]:
    return verification_payload(tuple(getattr(result, "verification_signals", ())))


def _model_status_from_result(result: Any) -> dict[str, Any]:
    execution_path = getattr(result, "execution_path", None)
    if isinstance(execution_path, dict) and isinstance(execution_path.get("model_status"), dict):
        return dict(execution_path["model_status"])
    return _fallback_model_status()


def _fallback_model_status() -> dict[str, Any]:
    return _fallback_execution_path()["model_status"]


def _fallback_execution_path() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "execution_path_id": "deterministic_fallback_v1",
        "profile_id": "standard",
        "local_only": True,
        "remote_runtime_api_allowed": False,
        "runtime_download_allowed": False,
        "deterministic_fallback_available": True,
        "deterministic_fallback_active": True,
        "model_status": {
            "schema_version": 1,
            "profile_id": "standard",
            "summary_status": "deterministic_fallback_active",
            "available_statuses": [
                "not_installed",
                "installed",
                "loading",
                "active",
                "failed_health_check",
                "deterministic_fallback_active",
            ],
            "component_count": 0,
            "installed_count": 0,
            "missing_count": 0,
            "failed_health_check_count": 0,
            "components": [],
            "adapters": {
                "ocr": "deterministic_fallback_active",
                "embedding": "deterministic_fallback_active",
                "reranker": "deterministic_fallback_active",
                "optional_extractor": "deterministic_fallback_active",
                "optional_explanation_qa": "deterministic_fallback_active",
            },
        },
        "steps": [
            {
                "adapter": adapter,
                "model_status": "deterministic_fallback_active",
                "execution_path": "deterministic_fallback",
            }
            for adapter in (
                "ocr",
                "embedding",
                "reranker",
                "optional_extractor",
                "optional_explanation_qa",
            )
        ],
    }


def _scenario_inputs_from_audit(
    audit_detail: dict[str, Any],
    scenario_input_values: dict[str, str] | None = None,
) -> dict[str, Any]:
    from fink.web.assumptions import primary_scenario_input_payload

    active_modules = tuple(
        item.get("fim_module")
        for item in audit_detail.get("technical_findings", ())
        if item.get("fim_module")
    )
    return primary_scenario_input_payload(
        active_fim_modules=active_modules,
        assumptions=_editable_assumptions_from_values(scenario_input_values or {}),
    )


def _editable_assumptions_from_values(values: dict[str, str]) -> Any:
    if not values:
        return None
    from dataclasses import fields as dataclass_fields
    from decimal import InvalidOperation

    from fink.web.assumptions import EditableAssumptions

    allowed = {field.name for field in dataclass_fields(EditableAssumptions)}
    int_fields = {
        "unpaid_revision_units",
        "exclusivity_duration_months",
        "renewal_duration_months",
    }
    kwargs: dict[str, Any] = {}
    for key, raw in values.items():
        if key not in allowed or raw in {"", "provided"}:
            continue
        try:
            if key in int_fields:
                kwargs[key] = int(raw)
            else:
                kwargs[key] = Decimal(str(raw))
        except (InvalidOperation, ValueError, TypeError):
            continue
    return EditableAssumptions(**kwargs) if kwargs else None


def _technical_finding_from_ranked(finding: Any) -> dict[str, Any]:
    return {
        "finding_id": _stable_id("finding", finding.signal_id, finding.clause_id, finding.exact_excerpt),
        "signal_id": finding.signal_id,
        "risk_category": finding.risk_category,
        "severity_raw": finding.severity_raw,
        "signal_confidence": finding.signal_confidence,
        "priority_sort_value": finding.priority_sort_value,
        "ranking_policy": finding.ranking_policy,
        "authority_gate": finding.authority_gate,
        "priority_basis": finding.priority_basis,
        "quantification_status": finding.quantification_status,
        "exposure_type": finding.exposure_type,
        "source_assumptions": list(finding.source_assumptions),
        "missing_inputs": list(finding.missing_inputs),
        "deterministic_class": finding.deterministic_class,
        "policy_notes": list(finding.policy_notes),
        "scored": finding.scored,
        "grounding": finding.grounding,
        "grounding_evidence_ids": list(finding.grounding_evidence_ids),
        "authority_tiers": list(finding.authority_tiers),
        "fim_module": finding.fim_module or _RISK_TO_PRIMARY_FIM.get(finding.risk_category),
    }


def _technical_finding_from_signal(signal: Any, rank: int) -> dict[str, Any]:
    category = _category_code(signal.risk_category)
    return {
        "rank": rank,
        "signal_id": signal.signal_id,
        "risk_category": category,
        "severity_raw": _json_scalar(getattr(signal, "severity_raw", None)),
        "signal_confidence": _json_scalar(getattr(signal, "signal_confidence", None)),
        "fim_module": _RISK_TO_PRIMARY_FIM.get(category),
    }


def _money_range_payload(exposure: Any) -> dict[str, Any]:
    return {
        "range_id": _stable_id(
            "range",
            getattr(getattr(exposure, "module", ""), "value", ""),
            getattr(getattr(exposure, "exposure_type", ""), "value", ""),
        ),
        "label": {
            "ko": "저/기준/고 금액 범위",
            "en": "Low/base/high money range",
        },
        "low": _decimal_to_str(exposure.low),
        "base": _decimal_to_str(exposure.base),
        "high": _decimal_to_str(exposure.high),
        "assumptions": list(exposure.assumptions),
    }


def _has_contract_timing(time_exposure: Any) -> bool:
    fields = (
        "payment_due_days",
        "payment_delay_days",
        "contract_duration_months",
        "renewal_duration_months",
        "exclusivity_duration_months",
        "termination_notice_days",
        "estimated_months_to_recoup",
    )
    return any(getattr(time_exposure, field, None) is not None for field in fields)


def _contract_timing_payload(time_exposure: Any) -> dict[str, str]:
    parts_ko: list[str] = []
    parts_en: list[str] = []
    if getattr(time_exposure, "payment_due_days", None) is not None:
        value = time_exposure.payment_due_days
        parts_ko.append(f"지급 {value}일")
        parts_en.append(f"payment due {value} days")
    if getattr(time_exposure, "payment_delay_days", None) is not None:
        value = time_exposure.payment_delay_days
        parts_ko.append(f"지연 {value}일")
        parts_en.append(f"delay {value} days")
    if getattr(time_exposure, "contract_duration_months", None) is not None:
        value = time_exposure.contract_duration_months
        parts_ko.append(f"계약 {value}개월")
        parts_en.append(f"contract {value} months")
    if getattr(time_exposure, "renewal_duration_months", None) is not None:
        value = time_exposure.renewal_duration_months
        parts_ko.append(f"갱신 {value}개월")
        parts_en.append(f"renewal {value} months")
    if getattr(time_exposure, "exclusivity_duration_months", None) is not None:
        value = time_exposure.exclusivity_duration_months
        parts_ko.append(f"독점 {value}개월")
        parts_en.append(f"exclusivity {value} months")
    if getattr(time_exposure, "termination_notice_days", None) is not None:
        value = time_exposure.termination_notice_days
        parts_ko.append(f"해지 통지 {value}일")
        parts_en.append(f"termination notice {value} days")
    if getattr(time_exposure, "estimated_months_to_recoup", None) is not None:
        value = time_exposure.estimated_months_to_recoup
        parts_ko.append(f"회수 {value}개월")
        parts_en.append(f"recoupment {value} months")
    if not parts_ko:
        return {
            "ko": "계약서에서 지급일, 계약 기간, 해지 통지일을 확인해야 합니다.",
            "en": "Payment date, contract duration, and notice timing need to be checked.",
        }
    return {"ko": " · ".join(parts_ko), "en": " · ".join(parts_en)}


def _exposure_to_audit(exposure: Any) -> dict[str, Any]:
    return {
        "fim_module": exposure.module.value,
        "exposure_type": exposure.exposure_type.value,
        "is_user_input_required": exposure.is_user_input_required,
        "low": _decimal_to_str(exposure.low),
        "base": _decimal_to_str(exposure.base),
        "high": _decimal_to_str(exposure.high),
        "nominal_amount": _decimal_to_str(exposure.nominal_amount),
        "uncertainty_flags": list(exposure.uncertainty_flags or ()),
    }


def _report_recommendation(pathway_label: str) -> dict[str, dict[str, str]]:
    return {
        "action": {
            "ko": "서명 전 핵심 조건을 다시 확인하세요.",
            "en": "Review the key terms again before signing.",
        },
        "cash_flow": {
            "ko": "조건에 따라 실수령액과 현금 흐름이 달라질 수 있습니다.",
            "en": "Depending on the terms, net payout and cash flow may change.",
        },
        "audit_pathway_label": {"ko": pathway_label, "en": pathway_label},
    }


def _guidance_for_category(guidance_items: tuple[Any, ...], category: str) -> Any | None:
    for item in guidance_items:
        if item.risk_category == category:
            return item
    return None


def _why_it_matters(guidance: Any | None, category: str) -> dict[str, str]:
    if guidance is not None:
        return {"ko": guidance.why_it_matters_ko, "en": guidance.why_it_matters_en}
    return _category_why(category)


def _category_why(category: str) -> dict[str, str]:
    key = _CATEGORY_COPY_KEY.get(category)
    label = creator_review_pair(key) if key else creator_review_pair("dimension.review_priority")
    return {
        "ko": f"{label['ko']} 조건은 창작자의 현금흐름에 영향을 줄 수 있습니다.",
        "en": f"{label['en']} terms can affect creator cash flow.",
    }


def _first_question(guidance: Any | None) -> dict[str, str]:
    fallback = {
        "ko": "서명 전 이 조건의 금액·시기 영향을 구체적으로 확인할 수 있나요?",
        "en": "Before signing, can the money and timing effect of this term be clarified?",
    }
    if guidance is None:
        return fallback
    return {
        "ko": guidance.questions_ko[0] if guidance.questions_ko else fallback["ko"],
        "en": guidance.questions_en[0] if guidance.questions_en else fallback["en"],
    }


def _questions_from_report(
    report: Any,
    clause_id: str,
    practice_references: tuple[Any, ...],
) -> list[dict[str, str]]:
    questions: list[dict[str, str]] = []
    for clause in report.assessment.clause_assessments:
        if clause.clause_id != clause_id:
            continue
        for question in clause.questions or ():
            questions.append({"ko": question, "en": question})
    for reference in practice_references:
        if reference.clause_id != clause_id:
            continue
        for question in reference.questions or ():
            questions.append({"ko": question, "en": question})
    deduped: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for item in questions:
        key = (item["ko"], item["en"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _priority_basis(is_missing_protection: bool) -> dict[str, str]:
    key = (
        "finding.priority_basis.missing_protection"
        if is_missing_protection
        else "finding.priority_basis.detected_term"
    )
    return creator_review_pair(key)


def _priority_basis_from_ranked(finding: Any) -> dict[str, str]:
    key = {
        "quantified_exposure": "finding.priority_basis.quantified_exposure",
        "present_value_timing": "finding.priority_basis.present_value_timing",
        "uncapped_or_unbounded": "finding.priority_basis.uncapped_or_unbounded",
        "counterparty_verification": "finding.priority_basis.counterparty_verification",
        "grounded_qualitative_signal": "finding.priority_basis.grounded_qualitative_signal",
        "unverified_candidate": "finding.priority_basis.unverified_candidate",
    }.get(getattr(finding, "priority_basis", ""))
    if key is not None:
        return creator_review_pair(key)
    return _priority_basis(bool(getattr(finding, "is_missing_protection", False)))


def _missing_inputs(monetary_present: bool) -> list[dict[str, str]]:
    if monetary_present:
        return []
    return [
        {
            "ko": "저/기준/고 금액 범위를 계산할 창작자 가정값",
            "en": "Creator assumptions for low/base/high money ranges",
        }
    ]


def _excerpt_for_clause(clause_id: str, highlights: tuple[Any, ...]) -> str:
    for item in highlights:
        if item.clause_id == clause_id:
            return " ".join(
                part.strip()
                for part in (item.text_before, item.trigger_text, item.text_after)
                if str(part).strip()
            )
    return ""


def _clause_heading_for_signal(clause_id: str, report: Any) -> str:
    for clause in getattr(report.assessment, "clause_assessments", ()):
        if clause.clause_id == clause_id:
            heading = getattr(clause, "heading_ko", None)
            return str(heading or "")
    return ""


def _citations_for_signal(signal: Any, report: Any, evidence_records: tuple[Any, ...]) -> list[dict[str, str]]:
    ids = set(getattr(signal, "grounding_evidence_ids", ()) or ())
    for clause in report.assessment.clause_assessments:
        if clause.clause_id == signal.clause_id:
            ids.update(clause.evidence_ids or ())
    citations = []
    for record in evidence_records:
        if record.evidence_id not in ids:
            continue
        citations.append(
            {
                "citation_id": _stable_id("citation", record.evidence_id),
                "source_id": record.source_id,
                "source_clause_id": record.article_ref or record.page_ref or "",
                "exact_excerpt": record.excerpt_ko or "",
            }
        )
    return citations


def _category_scores_to_audit(scores: dict[Any, float]) -> dict[str, float]:
    return {_category_code(category): float(score) for category, score in scores.items()}


def _category_code(category: Any) -> str:
    if isinstance(category, RiskCategory):
        return category.value
    raw = str(category)
    if raw in RiskCategory.__members__:
        return RiskCategory[raw].value
    return raw[:2] if raw[:2] in {item.value for item in RiskCategory} else raw


def _stable_id(prefix: str, *parts: object) -> str:
    raw = "|".join(str(part) for part in parts)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}-{digest}"


def _coerce_locale(locale: UILocale | str) -> UILocale:
    if isinstance(locale, UILocale):
        return locale
    try:
        return UILocale(str(locale).strip().lower())
    except ValueError:
        return UILocale.KO


def _decimal_to_str(value: Decimal | int | float | str | None) -> str | None:
    if value is None:
        return None
    return str(value)


def _json_scalar(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    return value

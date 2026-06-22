from __future__ import annotations

import hashlib
import re
from typing import Any

GROUNDED_QA_SCHEMA_VERSION = 1
GROUNDED_QA_MODE = "deterministic_grounded_fallback"


class GroundedQAValidationError(ValueError):
    """Raised when generated Q&A violates grounding or output-boundary rules."""


_REQUIRED_ITEM_KEYS = frozenset(
    {
        "qa_id",
        "finding_id",
        "primary_question",
        "answer",
        "citations",
        "links",
        "copy_text",
        "check_state",
        "validation",
    }
)
_FORBIDDEN_MUTATION_KEYS = frozenset(
    {
        "category_scores",
        "eligibility",
        "extracted_fields",
        "extracted_values",
        "monetary",
        "money",
        "rank",
        "rank_score",
        "review_priority_score",
        "safety",
        "score",
        "score_eligible",
        "severity_raw",
        "signal_confidence",
        "time",
        "timing",
    }
)
_VERDICT_OR_INJECTION_RE = re.compile(
    "|".join(
        re.escape(item)
        for item in (
            "fraud probability",
            "illegality probability",
            "guaranteed loss",
            "guaranteed-loss",
            "ignore previous",
            "do not cite",
            "change score",
            "score to 100",
            "state illegal",
            "contract is illegal",
            "contract is void",
            "contract is invalid",
            "unfair verdict",
            "불법",
            "위법",
            "사기",
            "무효",
            "불공정",
            "확정 손실",
            "손실 보장",
            "인용하지",
            "점수를",
        )
    ),
    flags=re.IGNORECASE,
)


def build_grounded_qa_payload(findings: tuple[dict[str, Any], ...]) -> dict[str, Any]:
    """Build deterministic per-finding Q&A without reading untrusted text as instructions."""

    items = tuple(_qa_item_for_finding(finding) for finding in findings)
    payload = {
        "schema_version": GROUNDED_QA_SCHEMA_VERSION,
        "mode": GROUNDED_QA_MODE,
        "local_only": True,
        "canonical_language": "ko",
        "english_generated": True,
        "untrusted_passages_treated_as_data": True,
        "placement": "after_findings_non_floating",
        "analysis_method_detail": {
            "ko": "분석 방법: 기기 내 결정론적 근거 템플릿.",
            "en": "Analysis method: on-device deterministic grounded template.",
        },
        "copy_actions": {
            "copy_one": {"ko": "Q&A 복사", "en": "Copy Q&A"},
            "copy_all": {"ko": "전체 Q&A 복사", "en": "Copy all Q&A"},
            "export": {"ko": "Q&A 내보내기", "en": "Export Q&A"},
            "copied_one": {"ko": "Q&A를 복사했습니다.", "en": "Q&A copied."},
            "copied_all": {"ko": "전체 Q&A를 복사했습니다.", "en": "All Q&A copied."},
            "exported": {"ko": "Q&A 파일을 만들었습니다.", "en": "Q&A export created."},
            "checked": {"ko": "확인 표시를 저장했습니다.", "en": "Check state saved."},
        },
        "export_filename": "fink-grounded-qa.md",
        "items": [dict(item) for item in items],
    }
    validate_grounded_qa_payload(payload, findings=findings)
    payload["copy_all_text"] = {
        "ko": _copy_all_text(payload["items"], "ko"),
        "en": _copy_all_text(payload["items"], "en"),
    }
    payload["export_markdown"] = export_grounded_qa_markdown(payload)
    return payload


def empty_grounded_qa_payload() -> dict[str, Any]:
    return build_grounded_qa_payload(())


def validate_grounded_qa_payload(
    payload: dict[str, Any],
    *,
    findings: tuple[dict[str, Any], ...],
) -> dict[str, Any]:
    """Validate a Q&A payload against allowed finding and evidence ids.

    This is intentionally strict because any future local model output must pass
    the same checks as the deterministic fallback.
    """

    errors: list[str] = []
    if not isinstance(payload, dict):
        raise GroundedQAValidationError("invalid schema: payload must be an object")
    if payload.get("schema_version") != GROUNDED_QA_SCHEMA_VERSION:
        errors.append("invalid schema_version")
    if payload.get("local_only") is not True:
        errors.append("local_only must be true")
    if payload.get("canonical_language") != "ko":
        errors.append("canonical_language must be ko")
    if payload.get("untrusted_passages_treated_as_data") is not True:
        errors.append("untrusted passages must be treated as data")

    context = _context_from_findings(findings)
    items = payload.get("items")
    if not isinstance(items, list):
        errors.append("invalid schema: items must be a list")
        items = []

    for index, item in enumerate(items):
        if not isinstance(item, dict):
            errors.append(f"item {index}: invalid schema")
            continue
        errors.extend(_mutation_key_errors(item, path=f"items[{index}]"))
        missing = sorted(_REQUIRED_ITEM_KEYS - set(item))
        if missing:
            errors.append(f"item {index}: missing keys {', '.join(missing)}")
            continue
        finding_id = str(item.get("finding_id") or "")
        if finding_id not in context:
            errors.append(f"item {index}: unknown finding_id")
            continue
        finding_context = context[finding_id]
        errors.extend(_text_boundary_errors(item, index=index))
        errors.extend(_citation_errors(item, finding_context, index=index))
        errors.extend(_link_errors(item, finding_context, index=index))
        errors.extend(_check_state_errors(item, index=index))

    if errors:
        raise GroundedQAValidationError("; ".join(errors))
    return payload


def export_grounded_qa_markdown(payload: dict[str, Any]) -> str:
    lines = ["# FInk Grounded Q&A", ""]
    for item in payload.get("items", ()):
        question = item["primary_question"]["ko"]
        answer = item["answer"]["ko"]
        citation_ids = [
            str(citation.get("evidence_id"))
            for citation in item.get("citations", ())
            if citation.get("evidence_id")
        ]
        lines.extend(
            [
                f"## {question}",
                answer,
                "근거: " + (", ".join(citation_ids) if citation_ids else "로컬 공식 근거 미연결"),
                f"검토 항목: {item['links']['finding_href']}",
                f"하이라이트: {item['links']['highlight_href']}",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def _qa_item_for_finding(finding: dict[str, Any]) -> dict[str, Any]:
    finding_id = str(finding.get("finding_id") or "")
    question = _pair(finding.get("question_to_ask"))
    evidence = finding.get("evidence") or {}
    allowed_ids = tuple(str(item) for item in evidence.get("grounding_evidence_ids", ()) or ())
    citations = tuple(_allowed_citation(citation, allowed_ids) for citation in finding.get("citations", ()))
    citations = tuple(item for item in citations if item is not None)
    if allowed_ids and not citations:
        citations = tuple({"evidence_id": evidence_id} for evidence_id in allowed_ids)
    source = finding.get("source") or {}
    title = _pair(finding.get("title"))
    answer = _answer_pair(title, allowed_ids)
    item = {
        "qa_id": _stable_id("qa", finding_id, question["ko"]),
        "finding_id": finding_id,
        "primary_question": question,
        "answer": answer,
        "grounding_state": str(evidence.get("state") or "candidate_unverified"),
        "citations": [dict(citation) for citation in citations],
        "links": {
            "finding_href": "#" + str(source.get("finding_anchor_id") or finding_id),
            "highlight_href": "#" + str(source.get("focus_anchor_id") or source.get("anchor_id") or "source-reader"),
        },
        "copy_text": {
            "ko": _copy_text(question["ko"], answer["ko"], allowed_ids),
            "en": _copy_text(question["en"], answer["en"], allowed_ids),
        },
        "check_state": {
            "checked": False,
            "scope": "session",
            "mutates_engine_output": False,
        },
        "validation": {
            "status": "accepted",
            "rejected_reasons": [],
        },
    }
    return item


def _answer_pair(title: dict[str, str], allowed_ids: tuple[str, ...]) -> dict[str, str]:
    if allowed_ids:
        evidence_text = ", ".join(allowed_ids)
        return {
            "ko": (
                f"{title['ko']} 항목에 대한 확인 질문입니다. "
                f"로컬 공식 근거 ID {evidence_text}만 인용합니다. "
                "상대방에게 계약서 반영 가능 여부와 제공 자료 범위를 답해 달라고 요청하세요."
            ),
            "en": (
                f"This is a clarification question for {title['en']}. "
                f"It cites only local official evidence ids: {evidence_text}. "
                "Ask the counterparty to answer what can be written into the contract and what records they will provide."
            ),
        }
    return {
        "ko": (
            f"{title['ko']} 항목에 대한 확인 질문입니다. "
            "아직 로컬 공식 근거가 연결되지 않았으므로 상대방 답변 확보용으로만 사용하세요."
        ),
        "en": (
            f"This is a clarification question for {title['en']}. "
            "No local official evidence id is linked yet, so use it only to collect the counterparty response."
        ),
    }


def _context_from_findings(findings: tuple[dict[str, Any], ...]) -> dict[str, dict[str, Any]]:
    context: dict[str, dict[str, Any]] = {}
    for finding in findings:
        finding_id = str(finding.get("finding_id") or "")
        source = finding.get("source") or {}
        evidence = finding.get("evidence") or {}
        context[finding_id] = {
            "allowed_evidence_ids": set(evidence.get("grounding_evidence_ids", ()) or ()),
            "finding_hrefs": {
                "#" + str(source.get("finding_anchor_id") or finding_id),
                "#" + finding_id,
            },
            "highlight_hrefs": {
                "#" + str(source.get("focus_anchor_id") or source.get("anchor_id") or "source-reader"),
                "#source-reader",
            },
        }
    return context


def _citation_errors(
    item: dict[str, Any],
    finding_context: dict[str, Any],
    *,
    index: int,
) -> list[str]:
    errors: list[str] = []
    citations = item.get("citations")
    if not isinstance(citations, list):
        return [f"item {index}: citations must be a list"]
    allowed = set(finding_context["allowed_evidence_ids"])
    cited: set[str] = set()
    for citation in citations:
        if not isinstance(citation, dict):
            errors.append(f"item {index}: invalid citation schema")
            continue
        evidence_id = str(citation.get("evidence_id") or "")
        if not evidence_id:
            errors.append(f"item {index}: citation missing evidence_id")
            continue
        if evidence_id not in allowed:
            errors.append(f"item {index}: citation {evidence_id} is not allowed")
            continue
        cited.add(evidence_id)
    if allowed and not cited:
        errors.append(f"item {index}: missing allowed evidence citation")
    return errors


def _link_errors(
    item: dict[str, Any],
    finding_context: dict[str, Any],
    *,
    index: int,
) -> list[str]:
    links = item.get("links")
    if not isinstance(links, dict):
        return [f"item {index}: links must be an object"]
    errors: list[str] = []
    if links.get("finding_href") not in finding_context["finding_hrefs"]:
        errors.append(f"item {index}: invalid finding link")
    if links.get("highlight_href") not in finding_context["highlight_hrefs"]:
        errors.append(f"item {index}: invalid highlight link")
    return errors


def _check_state_errors(item: dict[str, Any], *, index: int) -> list[str]:
    state = item.get("check_state")
    if not isinstance(state, dict):
        return [f"item {index}: check_state must be an object"]
    if state.get("scope") != "session":
        return [f"item {index}: check_state must be session scoped"]
    if state.get("mutates_engine_output") is not False:
        return [f"item {index}: check_state must not mutate engine output"]
    if not isinstance(state.get("checked"), bool):
        return [f"item {index}: check_state.checked must be boolean"]
    return []


def _text_boundary_errors(item: dict[str, Any], *, index: int) -> list[str]:
    errors: list[str] = []
    for key in ("primary_question", "answer"):
        pair = item.get(key)
        if not isinstance(pair, dict):
            errors.append(f"item {index}: {key} must be bilingual")
            continue
        ko = str(pair.get("ko") or "").strip()
        en = str(pair.get("en") or "").strip()
        if not ko or not en:
            errors.append(f"item {index}: {key} must be nonblank")
            continue
        if _VERDICT_OR_INJECTION_RE.search(ko) or _VERDICT_OR_INJECTION_RE.search(en):
            errors.append(f"item {index}: {key} contains rejected wording")
    question = item.get("primary_question")
    if isinstance(question, dict) and "?" not in str(question.get("ko") or ""):
        errors.append(f"item {index}: primary question must be answerable")
    return errors


def _mutation_key_errors(value: Any, *, path: str) -> list[str]:
    errors: list[str] = []
    if isinstance(value, dict):
        for key, nested in value.items():
            key_text = str(key)
            if key_text in _FORBIDDEN_MUTATION_KEYS:
                errors.append(f"{path}.{key_text}: Q&A cannot change engine output")
            errors.extend(_mutation_key_errors(nested, path=f"{path}.{key_text}"))
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            errors.extend(_mutation_key_errors(nested, path=f"{path}[{index}]"))
    return errors


def _allowed_citation(
    citation: dict[str, Any],
    allowed_ids: tuple[str, ...],
) -> dict[str, str] | None:
    evidence_id = str(citation.get("evidence_id") or "")
    if evidence_id not in allowed_ids:
        return None
    return {
        key: str(value)
        for key, value in citation.items()
        if key in {"citation_id", "evidence_id", "source_id", "authority_tier", "verification_status"}
        and value
    }


def _pair(value: Any) -> dict[str, str]:
    if isinstance(value, dict):
        return {"ko": str(value.get("ko") or "").strip(), "en": str(value.get("en") or "").strip()}
    return {"ko": "", "en": ""}


def _copy_text(question: str, answer: str, evidence_ids: tuple[str, ...]) -> str:
    evidence = ", ".join(evidence_ids) if evidence_ids else "로컬 공식 근거 미연결"
    return f"Q: {question}\nA: {answer}\nEvidence: {evidence}"


def _copy_all_text(items: list[dict[str, Any]], locale: str) -> str:
    return "\n\n".join(item["copy_text"][locale] for item in items)


def _stable_id(*parts: str) -> str:
    digest = hashlib.sha256("::".join(parts).encode("utf-8")).hexdigest()[:12]
    return f"{parts[0]}-{digest}"

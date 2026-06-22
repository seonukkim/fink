from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any

SOURCE_HIGHLIGHT_SCHEMA_VERSION = 1
HIGHLIGHT_STATUS_VALIDATED = "exact_span_validated"
HIGHLIGHT_STATUS_MISSING = "missing_exact_span"
MISSING_EXACT_SPAN_KO = "정확한 문구 위치 확인 필요"
MISSING_EXACT_SPAN_EN = "Exact source phrase position needs confirmation"

SEMANTIC_ROLE_ORDER = (
    "amount_or_rate",
    "timing_or_term",
    "deduction_recoupment_or_liability",
    "rights_scope_or_exclusivity",
    "ambiguity_or_missing_bound",
)

SEMANTIC_ROLE_DEFINITIONS: dict[str, dict[str, str]] = {
    "amount_or_rate": {
        "label_ko": "금액·비율",
        "label_en": "Amount or rate",
        "cue": "solid underline",
    },
    "timing_or_term": {
        "label_ko": "지급·기간",
        "label_en": "Timing or term",
        "cue": "dashed underline",
    },
    "deduction_recoupment_or_liability": {
        "label_ko": "공제·회수·책임",
        "label_en": "Deduction, recoupment, or liability",
        "cue": "left border",
    },
    "rights_scope_or_exclusivity": {
        "label_ko": "권리 범위·독점",
        "label_en": "Rights scope or exclusivity",
        "cue": "double underline",
    },
    "ambiguity_or_missing_bound": {
        "label_ko": "모호·상한 부재",
        "label_en": "Ambiguity or missing bound",
        "cue": "dotted underline",
    },
}


@dataclass(frozen=True)
class SourceHighlightCandidate:
    finding_id: str
    clause_id: str
    source_span_id: str
    start: int
    end: int
    exact_text: str
    roles: tuple[str, ...]


@dataclass(frozen=True)
class _SpanText:
    span_id: str
    text: str
    page_index: int
    global_start: int
    text_source: str
    bbox: dict[str, int]
    page_width: int
    page_height: int
    confidence: float
    is_user_corrected: bool
    has_real_bbox: bool


_ROLE_PATTERNS: tuple[tuple[str, tuple[re.Pattern[str], ...]], ...] = (
    (
        "amount_or_rate",
        (
            re.compile(r"\d+(?:[.,]\d+)?\s*%"),
            re.compile(r"(?:KRW\s*)?[0-9][0-9,]*(?:\s*)(?:원|만원|억원|krw)", re.IGNORECASE),
        ),
    ),
    (
        "timing_or_term",
        (
            re.compile(r"\d+\s*(?:일|개월|년)\s*(?:이내|내|후|전|간)?"),
            re.compile(r"매\s*(?:월|분기|반기|년)"),
            re.compile(r"\d+\s*(?:days?|months?|years?)", re.IGNORECASE),
            re.compile(r"(?:payment\s+due|due\s+within)\s+\d+\s*days?", re.IGNORECASE),
        ),
    ),
    (
        "deduction_recoupment_or_liability",
        (
            re.compile(r"일반\s*경비"),
            re.compile(r"(?:공제|차감)(?:\s*항목|\s*대상|할\s*수\s*있다|한다)?"),
            re.compile(r"(?:선급금|미니멈\s*개런티|MG)\s*(?:회수|상계)?", re.IGNORECASE),
            re.compile(r"(?:위약금|손해배상|책임|배상책임)"),
            re.compile(r"\b(?:deductions?|recoup(?:ment)?|liability|penalty)\b", re.IGNORECASE),
        ),
    ),
    (
        "rights_scope_or_exclusivity",
        (
            re.compile(r"(?:저작권|2차적저작물|이차적저작물|부가\s*권리)"),
            re.compile(r"(?:포괄\s*양도|독점|전속|자동\s*갱신)"),
            re.compile(
                r"\b(?:copyright|secondary\s+rights?|derivative\s+works?|exclusive|exclusivity)\b",
                re.IGNORECASE,
            ),
        ),
    ),
    (
        "ambiguity_or_missing_bound",
        (
            re.compile(r"일반\s*경비"),
            re.compile(r"(?:기타|그\s*밖의?)\s*(?:비용|경비|공제|수수료)"),
            re.compile(r"회사(?:가|의)?\s*정(?:한|하는)"),
            re.compile(r"할\s*수\s*있다"),
            re.compile(r"(?:포괄|제한\s*없(?:이|는)|상한\s*없(?:이|는))"),
            re.compile(r"\b(?:other|general)\s+(?:costs?|fees?|expenses?|deductions?)\b", re.IGNORECASE),
            re.compile(r"\b(?:sole\s+discretion|as\s+determined|without\s+limit)\b", re.IGNORECASE),
        ),
    ),
)


def empty_source_highlights() -> dict[str, Any]:
    return {
        "schema_version": SOURCE_HIGHLIGHT_SCHEMA_VERSION,
        "mode": "exact_provenance_segments",
        "enabled_default": True,
        "missing_label": _status_label(HIGHLIGHT_STATUS_MISSING),
        "roles": _role_payload(),
        "sources": [],
    }


def build_source_highlight_payload(
    *,
    source_pages: tuple[Any, ...] = (),
    clauses: tuple[Any, ...] = (),
    findings: tuple[dict[str, Any], ...] = (),
) -> tuple[tuple[dict[str, Any], ...], dict[str, Any]]:
    if not source_pages or not clauses or not findings:
        return findings, empty_source_highlights()

    clause_by_id = {clause.clause_id: clause for clause in clauses}
    span_lookup = _span_lookup(source_pages)
    sources: list[dict[str, Any]] = []
    updated_findings: list[dict[str, Any]] = []

    for finding in findings:
        updated, source = _source_for_finding(finding, clause_by_id, span_lookup)
        updated_findings.append(updated)
        if source is not None:
            sources.append(source)

    payload = empty_source_highlights()
    payload["sources"] = sources
    payload["source_count"] = len(sources)
    return tuple(updated_findings), payload


def validate_source_highlight_candidates(
    candidates: tuple[SourceHighlightCandidate, ...],
    *,
    finding_ids: set[str],
    clause_by_id: dict[str, Any],
    span_text_by_id: dict[str, str],
) -> tuple[SourceHighlightCandidate, ...]:
    validated: list[SourceHighlightCandidate] = []
    for candidate in candidates:
        if candidate.finding_id not in finding_ids:
            continue
        clause = clause_by_id.get(candidate.clause_id)
        if clause is None:
            continue
        if candidate.source_span_id not in tuple(getattr(clause, "source_span_ids", ())):
            continue
        source_text = span_text_by_id.get(candidate.source_span_id)
        if source_text is None:
            continue
        if candidate.start < 0 or candidate.end > len(source_text):
            continue
        if candidate.start >= candidate.end:
            continue
        if candidate.exact_text != source_text[candidate.start : candidate.end]:
            continue
        roles = _valid_roles(candidate.roles)
        if not roles:
            continue
        validated.append(
            SourceHighlightCandidate(
                finding_id=candidate.finding_id,
                clause_id=candidate.clause_id,
                source_span_id=candidate.source_span_id,
                start=candidate.start,
                end=candidate.end,
                exact_text=candidate.exact_text,
                roles=roles,
            )
        )
    return tuple(
        sorted(
            validated,
            key=lambda item: (
                item.clause_id,
                item.source_span_id,
                item.start,
                item.end,
                item.roles,
                item.finding_id,
            ),
        )
    )


def _source_for_finding(
    finding: dict[str, Any],
    clause_by_id: dict[str, Any],
    span_lookup: dict[str, _SpanText],
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    finding_id = str(finding.get("finding_id") or "")
    source = finding.get("source") or {}
    clause_id = str(source.get("clause_id") or "")
    clause = clause_by_id.get(clause_id)
    updated_finding = {**finding, "source": dict(source)}
    if not finding_id or clause is None:
        _attach_missing_source(updated_finding)
        return updated_finding, None

    span_records = _source_span_records(clause, span_lookup)
    source_text = "\n".join(record.text for record in span_records)
    source_anchor_id = _stable_id("source", finding_id, clause_id)
    finding_anchor_id = _stable_anchor(finding_id)
    if not source_text or not span_records:
        _attach_missing_source(
            updated_finding,
            source_anchor_id=source_anchor_id,
            finding_anchor_id=finding_anchor_id,
        )
        return updated_finding, _missing_source_payload(
            source_anchor_id=source_anchor_id,
            finding_anchor_id=finding_anchor_id,
            finding_id=finding_id,
            clause_id=clause_id,
            source_text=source_text,
            page_index=None,
        )

    candidates = _candidate_spans_for_finding(
        finding_id=finding_id,
        clause_id=clause_id,
        span_records=span_records,
    )
    validated = validate_source_highlight_candidates(
        candidates,
        finding_ids={finding_id},
        clause_by_id={clause_id: clause},
        span_text_by_id={record.span_id: record.text for record in span_records},
    )
    segments = _display_segments(source_text, span_records, validated)
    _attach_segment_anchor_ids(segments, source_anchor_id)
    focus_anchor_id = _focus_anchor_id(source_anchor_id, segments)
    has_highlight = any(segment.get("highlighted") for segment in segments)
    status = HIGHLIGHT_STATUS_VALIDATED if has_highlight else HIGHLIGHT_STATUS_MISSING
    role_ids = _roles_from_segments(segments)
    source_meta = _source_text_metadata(span_records)
    clause_text = _clause_text_payload(clause, source_text)

    updated_finding["source"].update(
        {
            "anchor_id": source_anchor_id,
            "focus_anchor_id": focus_anchor_id,
            "finding_anchor_id": finding_anchor_id,
            **clause_text,
            "highlight_status": status,
            "highlight_status_label": _status_label(status),
            "segments": segments,
            "semantic_roles": role_ids,
            "source_link_label": {
                "ko": "원문으로 이동",
                "en": "Go to source",
            },
        }
    )
    return updated_finding, {
        "source_id": source_anchor_id,
        "anchor_id": source_anchor_id,
        "focus_anchor_id": focus_anchor_id,
        "finding_anchor_id": finding_anchor_id,
        "finding_ids": [finding_id],
        "clause_id": clause_id,
        "page_index": span_records[0].page_index,
        "status": status,
        "status_label": _status_label(status),
        **source_meta,
        **clause_text,
        "segments": segments,
        "semantic_roles": role_ids,
        "validated_span_count": len(validated),
        "source_text_length": len(source_text),
    }


def _attach_missing_source(
    finding: dict[str, Any],
    *,
    source_anchor_id: str = "",
    finding_anchor_id: str = "",
) -> None:
    finding["source"].update(
        {
            "anchor_id": source_anchor_id,
            "focus_anchor_id": source_anchor_id,
            "finding_anchor_id": finding_anchor_id,
            "highlight_status": HIGHLIGHT_STATUS_MISSING,
            "highlight_status_label": _status_label(HIGHLIGHT_STATUS_MISSING),
            "segments": [],
            "semantic_roles": [],
            "source_link_label": {
                "ko": "원문 위치 확인 필요",
                "en": "Source position needs confirmation",
            },
        }
    )


def _missing_source_payload(
    *,
    source_anchor_id: str,
    finding_anchor_id: str,
    finding_id: str,
    clause_id: str,
    source_text: str,
    page_index: int | None,
) -> dict[str, Any]:
    return {
        "source_id": source_anchor_id,
        "anchor_id": source_anchor_id,
        "focus_anchor_id": source_anchor_id,
        "finding_anchor_id": finding_anchor_id,
        "finding_ids": [finding_id],
        "clause_id": clause_id,
        "page_index": page_index,
        "status": HIGHLIGHT_STATUS_MISSING,
        "status_label": _status_label(HIGHLIGHT_STATUS_MISSING),
        "text_source": "missing",
        "render_mode": "inline_selectable_text",
        "text_source_label": _text_source_label("missing", False),
        "has_real_bbox_provenance": False,
        "is_user_corrected": False,
        "segments": [{"text": source_text, "highlighted": False}] if source_text else [],
        "semantic_roles": [],
        "validated_span_count": 0,
        "source_text_length": len(source_text),
    }


def _clause_text_payload(clause: Any, source_text: str) -> dict[str, str]:
    heading = str(getattr(clause, "heading_ko", "") or "")
    text_ko = str(getattr(clause, "text_ko", "") or source_text or "")
    text_en_gloss = str(getattr(clause, "text_en_gloss", "") or "")
    return {
        "clause_heading": heading,
        "text_ko": text_ko,
        "text_en_gloss": text_en_gloss,
    }


def _candidate_spans_for_finding(
    *,
    finding_id: str,
    clause_id: str,
    span_records: tuple[_SpanText, ...],
) -> tuple[SourceHighlightCandidate, ...]:
    candidates: list[SourceHighlightCandidate] = []
    for span in span_records:
        roles_by_range: dict[tuple[int, int, str], list[str]] = {}
        for role, patterns in _ROLE_PATTERNS:
            for pattern in patterns:
                for match in pattern.finditer(span.text):
                    exact_text = match.group(0)
                    if not exact_text.strip():
                        continue
                    key = (match.start(), match.end(), exact_text)
                    roles_by_range.setdefault(key, []).append(role)
        for (start, end, exact_text), roles in roles_by_range.items():
            candidates.append(
                SourceHighlightCandidate(
                    finding_id=finding_id,
                    clause_id=clause_id,
                    source_span_id=span.span_id,
                    start=start,
                    end=end,
                    exact_text=exact_text,
                    roles=_valid_roles(tuple(roles)),
                )
            )
    return tuple(candidates)


def _display_segments(
    source_text: str,
    span_records: tuple[_SpanText, ...],
    candidates: tuple[SourceHighlightCandidate, ...],
) -> list[dict[str, Any]]:
    if not source_text:
        return []

    ranges: list[tuple[int, int, tuple[str, ...], str]] = []
    for candidate in candidates:
        span = next((item for item in span_records if item.span_id == candidate.source_span_id), None)
        if span is None:
            continue
        ranges.append(
            (
                span.global_start + candidate.start,
                span.global_start + candidate.end,
                candidate.roles,
                candidate.source_span_id,
            )
        )
    if not ranges:
        return [{"text": source_text, "highlighted": False}]

    boundaries = {0, len(source_text)}
    for start, end, _roles, _span_id in ranges:
        boundaries.add(start)
        boundaries.add(end)
    ordered = sorted(boundaries)
    segments: list[dict[str, Any]] = []
    for index in range(len(ordered) - 1):
        start = ordered[index]
        end = ordered[index + 1]
        if start == end:
            continue
        text = source_text[start:end]
        roles = _valid_roles(
            tuple(
                role
                for range_start, range_end, range_roles, _span_id in ranges
                if range_start <= start and end <= range_end
                for role in range_roles
            )
        )
        span_ids = tuple(
            dict.fromkeys(
                span_id
                for range_start, range_end, _range_roles, span_id in ranges
                if range_start <= start and end <= range_end
            )
        )
        page_boxes = tuple(
            box
            for span_id in span_ids
            for box in (_page_box_for_span(span_records, span_id),)
            if box is not None
        )
        item: dict[str, Any] = {
            "segment_id": _stable_id("segment", start, end, text, roles),
            "text": text,
            "start": start,
            "end": end,
            "highlighted": bool(roles),
        }
        if roles:
            item["roles"] = list(roles)
            item["role_labels_ko"] = [
                SEMANTIC_ROLE_DEFINITIONS[role]["label_ko"] for role in roles
            ]
            item["source_span_ids"] = list(span_ids)
            if page_boxes:
                item["bbox_provenance"] = "real_ocr_bbox"
                item["page_boxes"] = list(page_boxes)
        segments.append(item)
    return _merge_adjacent_plain_segments(segments)


def _merge_adjacent_plain_segments(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    for segment in segments:
        if (
            merged
            and not merged[-1].get("highlighted")
            and not segment.get("highlighted")
        ):
            merged[-1]["text"] += segment["text"]
            merged[-1]["end"] = segment["end"]
            merged[-1]["segment_id"] = _stable_id(
                "segment",
                merged[-1]["start"],
                merged[-1]["end"],
                merged[-1]["text"],
                (),
            )
            continue
        merged.append(segment)
    return merged


def _source_span_records(
    clause: Any,
    span_lookup: dict[str, _SpanText],
) -> tuple[_SpanText, ...]:
    records: list[_SpanText] = []
    cursor = 0
    for span_id in tuple(getattr(clause, "source_span_ids", ())):
        if span_id not in span_lookup:
            continue
        span = span_lookup[span_id]
        if records:
            cursor += 1
        records.append(
            _SpanText(
                span_id=span_id,
                text=span.text,
                page_index=span.page_index,
                global_start=cursor,
                text_source=span.text_source,
                bbox=dict(span.bbox),
                page_width=span.page_width,
                page_height=span.page_height,
                confidence=span.confidence,
                is_user_corrected=span.is_user_corrected,
                has_real_bbox=span.has_real_bbox,
            )
        )
        cursor += len(span.text)
    return tuple(records)


def _span_lookup(source_pages: tuple[Any, ...]) -> dict[str, _SpanText]:
    lookup: dict[str, _SpanText] = {}
    for page in source_pages:
        page_index = int(getattr(page, "page_index", 0))
        page_source = _text_source_value(getattr(page, "text_source", ""))
        page_width = int(getattr(page, "width_px", 1))
        page_height = int(getattr(page, "height_px", 1))
        for span in tuple(getattr(page, "spans", ())):
            text = getattr(span, "corrected_text", None)
            is_user_corrected = text is not None
            if text is None:
                text = getattr(span, "text", "")
            span_id = str(span.span_id)
            span_source = _span_text_source(page_source, span_id)
            confidence = float(getattr(span, "confidence", 1.0))
            lookup[span_id] = _SpanText(
                span_id=span_id,
                text=str(text),
                page_index=page_index,
                global_start=0,
                text_source=span_source,
                bbox=dict(getattr(span, "bbox", {})),
                page_width=page_width,
                page_height=page_height,
                confidence=confidence,
                is_user_corrected=is_user_corrected,
                has_real_bbox=span_source == "ocr" and confidence < 1.0,
            )
    return lookup


def _attach_segment_anchor_ids(segments: list[dict[str, Any]], source_anchor_id: str) -> None:
    for segment in segments:
        if not segment.get("highlighted"):
            continue
        segment["anchor_id"] = _stable_id(
            "source-span",
            source_anchor_id,
            segment.get("segment_id", ""),
        )


def _focus_anchor_id(source_anchor_id: str, segments: list[dict[str, Any]]) -> str:
    for segment in segments:
        if segment.get("highlighted") and segment.get("anchor_id"):
            return str(segment["anchor_id"])
    return source_anchor_id


def _source_text_metadata(span_records: tuple[_SpanText, ...]) -> dict[str, Any]:
    text_source = _source_text_summary(span_records)
    is_user_corrected = any(record.is_user_corrected for record in span_records)
    return {
        "text_source": text_source,
        "render_mode": _render_mode_for_source(text_source),
        "text_source_label": _text_source_label(text_source, is_user_corrected),
        "has_real_bbox_provenance": any(record.has_real_bbox for record in span_records),
        "is_user_corrected": is_user_corrected,
    }


def _source_text_summary(span_records: tuple[_SpanText, ...]) -> str:
    sources = {record.text_source for record in span_records if record.text_source}
    if not sources:
        return "missing"
    if sources == {"text_layer"}:
        return "text_layer"
    if sources == {"ocr"}:
        return "ocr"
    return "mixed"


def _render_mode_for_source(text_source: str) -> str:
    if text_source == "ocr":
        return "reconstructed_ocr_text"
    if text_source == "mixed":
        return "mixed_inline_text"
    return "inline_selectable_text"


def _text_source_label(text_source: str, is_user_corrected: bool) -> dict[str, str]:
    if text_source == "ocr" and is_user_corrected:
        return {"ko": "수정된 OCR 재구성 텍스트", "en": "Corrected OCR reconstructed text"}
    if text_source == "ocr":
        return {"ko": "OCR 재구성 텍스트", "en": "OCR reconstructed text"}
    if text_source == "mixed" and is_user_corrected:
        return {
            "ko": "텍스트 레이어와 수정된 OCR 재구성 텍스트",
            "en": "Text layer plus corrected OCR reconstructed text",
        }
    if text_source == "mixed":
        return {"ko": "텍스트 레이어와 OCR 재구성 텍스트", "en": "Text layer plus OCR text"}
    if text_source == "missing":
        return {"ko": "원문 위치 확인 필요", "en": "Source position needs confirmation"}
    return {"ko": "선택 가능한 원문 텍스트", "en": "Selectable source text"}


def _page_box_for_span(
    span_records: tuple[_SpanText, ...],
    span_id: str,
) -> dict[str, Any] | None:
    record = next((item for item in span_records if item.span_id == span_id), None)
    if record is None or not record.has_real_bbox:
        return None
    return {
        "span_id": record.span_id,
        "page_index": record.page_index,
        "x": record.bbox["x"],
        "y": record.bbox["y"],
        "w": record.bbox["w"],
        "h": record.bbox["h"],
        "page_width": record.page_width,
        "page_height": record.page_height,
        "provenance": "real_ocr_bbox",
    }


def _text_source_value(raw: Any) -> str:
    value = getattr(raw, "value", raw)
    return str(value or "").strip().lower()


def _span_text_source(page_source: str, span_id: str) -> str:
    if page_source == "mixed":
        if ":ocr-" in span_id:
            return "ocr"
        if ":text-" in span_id:
            return "text_layer"
        return "mixed"
    if page_source in {"ocr", "text_layer"}:
        return page_source
    return "text_layer"


def _role_payload() -> list[dict[str, str]]:
    return [
        {
            "role": role,
            "label_ko": SEMANTIC_ROLE_DEFINITIONS[role]["label_ko"],
            "label_en": SEMANTIC_ROLE_DEFINITIONS[role]["label_en"],
            "cue": SEMANTIC_ROLE_DEFINITIONS[role]["cue"],
        }
        for role in SEMANTIC_ROLE_ORDER
    ]


def _status_label(status: str) -> dict[str, str]:
    if status == HIGHLIGHT_STATUS_VALIDATED:
        return {"ko": "정확한 출처 문구 확인됨", "en": "Exact source phrase validated"}
    return {"ko": MISSING_EXACT_SPAN_KO, "en": MISSING_EXACT_SPAN_EN}


def _roles_from_segments(segments: list[dict[str, Any]]) -> list[str]:
    return list(
        dict.fromkeys(
            role
            for segment in segments
            for role in segment.get("roles", ())
            if role in SEMANTIC_ROLE_DEFINITIONS
        )
    )


def _valid_roles(roles: tuple[str, ...]) -> tuple[str, ...]:
    role_set = set(roles)
    return tuple(role for role in SEMANTIC_ROLE_ORDER if role in role_set)


def _stable_anchor(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "-", value).strip("-")
    return cleaned or _stable_id("finding", value)


def _stable_id(prefix: str, *parts: object) -> str:
    raw = "|".join(str(part) for part in parts)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}-{digest}"

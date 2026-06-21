from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fink.schemas import AnalysisReport, EvidenceRecord, ExportFormat, RiskCategory
from fink.web.report_ui import HighlightedEvidence, PracticeReference, render_report_html

EXPORT_DISCLAIMERS = (
    "FInk reports Contractual Financial Review Priority only and is not legal advice.",
    "It is not a fraud, illegality, validity, unfairness, or guaranteed-loss verdict.",
    "Exports are local files; no remote LLM, cloud OCR, telemetry, or external legal search is used.",
    "Korean source language is canonical; English text is a generated aid.",
)
DEFAULT_EXPORT_FORMATS = (ExportFormat.HTML, ExportFormat.MD, ExportFormat.JSON)

_EXPORT_EXTENSIONS = {
    ExportFormat.HTML: ".html",
    ExportFormat.MD: ".md",
    ExportFormat.JSON: ".json",
}
_CONTENT_TYPES = {
    ExportFormat.HTML: "text/html; charset=utf-8",
    ExportFormat.MD: "text/markdown; charset=utf-8",
    ExportFormat.JSON: "application/json; charset=utf-8",
}
_RAW_IMAGE_KEYS = frozenset(
    {
        "raw_image",
        "raw_image_bytes",
        "image_bytes",
        "source_image_bytes",
        "page_raster",
        "page_raster_bytes",
        "source_pdf_bytes",
        "pdf_bytes",
    }
)


class ReportExportError(ValueError):
    """Raised when a local report export request is unsafe or unsupported."""


@dataclass(frozen=True)
class ReportExport:
    path: Path
    format: ExportFormat
    content_type: str
    bytes_written: int
    contains_raw_image: bool
    local_only: bool = True
    outbound_network_clients: int = 0


def export_report(
    report: AnalysisReport,
    output_path: str | Path,
    *,
    export_format: ExportFormat | str | None = None,
    evidence_records: tuple[EvidenceRecord, ...] = (),
    practice_references: tuple[PracticeReference, ...] = (),
    highlighted_evidence: tuple[HighlightedEvidence, ...] = (),
    cross_cutting_signals: tuple[Any, ...] = (),
    include_raw_images: bool = False,
    exported_at: datetime | None = None,
) -> ReportExport:
    """Write one local report export file without using network clients."""

    fmt = _coerce_export_format(export_format, output_path)
    path = Path(output_path)
    content = render_report_export(
        report,
        fmt,
        evidence_records=evidence_records,
        practice_references=practice_references,
        highlighted_evidence=highlighted_evidence,
        cross_cutting_signals=cross_cutting_signals,
        include_raw_images=include_raw_images,
        exported_at=exported_at,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")
    return ReportExport(
        path=path,
        format=fmt,
        content_type=_CONTENT_TYPES[fmt],
        bytes_written=len(content.encode("utf-8")),
        contains_raw_image=False,
    )


def export_report_bundle(
    report: AnalysisReport,
    output_dir: str | Path,
    *,
    basename: str | None = None,
    formats: tuple[ExportFormat | str, ...] = DEFAULT_EXPORT_FORMATS,
    evidence_records: tuple[EvidenceRecord, ...] = (),
    practice_references: tuple[PracticeReference, ...] = (),
    highlighted_evidence: tuple[HighlightedEvidence, ...] = (),
    cross_cutting_signals: tuple[Any, ...] = (),
    include_raw_images: bool = False,
    exported_at: datetime | None = None,
) -> tuple[ReportExport, ...]:
    """Write HTML, Markdown, and JSON local report exports."""

    output_root = Path(output_dir)
    stem = _safe_stem(basename or report.report_id)
    exports: list[ReportExport] = []
    for item in formats:
        fmt = _coerce_export_format(item, None)
        exports.append(
            export_report(
                report,
                output_root / f"{stem}{_EXPORT_EXTENSIONS[fmt]}",
                export_format=fmt,
                evidence_records=evidence_records,
                practice_references=practice_references,
                highlighted_evidence=highlighted_evidence,
                cross_cutting_signals=cross_cutting_signals,
                include_raw_images=include_raw_images,
                exported_at=exported_at,
            )
        )
    return tuple(exports)


def render_report_export(
    report: AnalysisReport,
    export_format: ExportFormat | str,
    *,
    evidence_records: tuple[EvidenceRecord, ...] = (),
    practice_references: tuple[PracticeReference, ...] = (),
    highlighted_evidence: tuple[HighlightedEvidence, ...] = (),
    cross_cutting_signals: tuple[Any, ...] = (),
    include_raw_images: bool = False,
    exported_at: datetime | None = None,
) -> str:
    """Render report export content for a local file."""

    fmt = _coerce_export_format(export_format, None)
    payload = _export_payload(
        report,
        fmt,
        evidence_records=evidence_records,
        practice_references=practice_references,
        include_raw_images=include_raw_images,
        exported_at=exported_at,
    )
    if fmt is ExportFormat.JSON:
        return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if fmt is ExportFormat.MD:
        return _render_markdown_export(payload)
    if fmt is ExportFormat.HTML:
        return _render_html_export(
            report,
            payload,
            evidence_records=evidence_records,
            practice_references=practice_references,
            highlighted_evidence=highlighted_evidence,
            cross_cutting_signals=cross_cutting_signals,
        )
    raise ReportExportError(f"unsupported export format: {fmt.value}")


def _export_payload(
    report: AnalysisReport,
    fmt: ExportFormat,
    *,
    evidence_records: tuple[EvidenceRecord, ...],
    practice_references: tuple[PracticeReference, ...],
    include_raw_images: bool,
    exported_at: datetime | None,
) -> dict[str, Any]:
    if include_raw_images:
        raise ReportExportError("raw image export is not supported; export OCR/report data only")
    timestamp = (exported_at or datetime.now(UTC)).isoformat()
    report_payload = _scrub_raw_image_fields(report.to_dict())
    report_payload["contains_raw_image"] = False
    report_payload["export_format"] = fmt.value
    report_payload["exported_at"] = timestamp
    assessment = report.assessment
    return {
        "schema_version": 1,
        "export_metadata": {
            "format": fmt.value,
            "exported_at": timestamp,
            "local_only": True,
            "outbound_network_clients": 0,
            "contains_raw_image": False,
            "raw_image_policy": "excluded_by_default",
        },
        "disclaimers": _merged_disclaimers(report),
        "four_dimensions": {
            "review-priority-score": {
                "label": "Contractual Financial Review Priority Score",
                "value": assessment.review_priority_score,
            },
            "monetary-exposure-range": [
                _monetary_exposure_payload(exposure)
                for exposure in assessment.monetary_exposures
            ],
            "time-exposure": assessment.time_exposure.to_dict(),
            "evidence-ocr-confidence": assessment.confidence.to_dict(),
        },
        "grounding": [_evidence_payload(record) for record in evidence_records],
        "assumptions": _assumption_payloads(report),
        "questions_before_signing": _question_payloads(report, practice_references),
        "practice_references": [_practice_reference_payload(item) for item in practice_references],
        "report": report_payload,
    }


def _render_html_export(
    report: AnalysisReport,
    payload: dict[str, Any],
    *,
    evidence_records: tuple[EvidenceRecord, ...],
    practice_references: tuple[PracticeReference, ...],
    highlighted_evidence: tuple[HighlightedEvidence, ...],
    cross_cutting_signals: tuple[Any, ...],
) -> str:
    metadata = payload["export_metadata"]
    disclaimers = "".join(
        f"<li>{html.escape(disclaimer)}</li>" for disclaimer in payload["disclaimers"]
    )
    report_markup = render_report_html(
        report,
        evidence_records=evidence_records,
        practice_references=practice_references,
        highlighted_evidence=highlighted_evidence,
        cross_cutting_signals=cross_cutting_signals,
    )
    return f"""<!doctype html>
<html lang="ko" data-fink-report-export="true" data-local-only="true">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="referrer" content="no-referrer">
  <title>FInk local report export</title>
</head>
<body data-export-format="html"
  data-export-local-only="{str(metadata["local_only"]).lower()}"
  data-outbound-network-clients="{metadata["outbound_network_clients"]}"
  data-contains-raw-image="{str(metadata["contains_raw_image"]).lower()}">
  <header>
    <h1>계약상 금융 검토 우선도</h1>
    <p>Contractual Financial Review Priority</p>
  </header>
  <section aria-label="Export metadata">
    <p>format: html</p>
    <p>contains_raw_image=false</p>
    <p>raw_image_policy=excluded_by_default</p>
  </section>
  <section aria-label="Report disclaimers">
    <h2>Disclaimers</h2>
    <ul>{disclaimers}</ul>
  </section>
  {report_markup}
</body>
</html>
"""


def _render_markdown_export(payload: dict[str, Any]) -> str:
    lines = [
        "# FInk Local Report Export",
        "",
        "## Export Metadata",
    ]
    metadata = payload["export_metadata"]
    for key in (
        "format",
        "exported_at",
        "local_only",
        "outbound_network_clients",
        "contains_raw_image",
        "raw_image_policy",
    ):
        lines.append(f"- {key}: {_metadata_text(metadata[key])}")
    lines.extend(["", "## Disclaimers"])
    lines.extend(f"- {item}" for item in payload["disclaimers"])

    dimensions = payload["four_dimensions"]
    lines.extend(
        [
            "",
            "## Four Dimensions",
            "",
            "### review-priority-score",
            (
                "- Contractual Financial Review Priority Score: "
                f"{dimensions['review-priority-score']['value']} / 100"
            ),
            "",
            "### monetary-exposure-range",
        ]
    )
    exposures = dimensions["monetary-exposure-range"]
    if exposures:
        for exposure in exposures:
            lines.extend(
                [
                    f"- {exposure['module']} {exposure['exposure_type']}: "
                    f"low={exposure['low']} base={exposure['base']} high={exposure['high']}",
                    f"  assumptions: {', '.join(exposure['assumptions']) or 'none'}",
                ]
            )
    else:
        lines.append("- Add user assumptions to estimate low / base / high ranges.")

    lines.extend(["", "### time-exposure"])
    for key, value in dimensions["time-exposure"].items():
        lines.append(f"- {key}: {value}")

    lines.extend(["", "### evidence-ocr-confidence"])
    for key, value in dimensions["evidence-ocr-confidence"].items():
        lines.append(f"- {key}: {value}")

    lines.extend(["", "## Grounding"])
    if payload["grounding"]:
        for item in payload["grounding"]:
            lines.append(
                "- "
                f"{item['evidence_id']} {item['source_id']} "
                f"{item['authority_tier']} {item['verification_status']}: "
                f"{item['excerpt']}"
            )
    else:
        lines.append("- No official grounding records attached to this export.")

    lines.extend(["", "## Assumptions"])
    if payload["assumptions"]:
        lines.extend(f"- {item}" for item in payload["assumptions"])
    else:
        lines.append("- No synthetic assumptions attached.")

    lines.extend(["", "## Questions Before Signing"])
    if payload["questions_before_signing"]:
        lines.extend(
            f"- {item['clause_id']}: {item['question']}"
            for item in payload["questions_before_signing"]
        )
    else:
        lines.append("- No questions attached.")
    return "\n".join(lines) + "\n"


def _monetary_exposure_payload(exposure: Any) -> dict[str, Any]:
    return {
        "module": exposure.module.value,
        "exposure_type": exposure.exposure_type.value,
        "is_user_input_required": exposure.is_user_input_required,
        "low": _string_or_none(exposure.low),
        "base": _string_or_none(exposure.base),
        "high": _string_or_none(exposure.high),
        "nominal_amount": _string_or_none(exposure.nominal_amount),
        "assumptions": list(exposure.assumptions),
        "uncertainty_flags": list(exposure.uncertainty_flags),
    }


def _evidence_payload(record: EvidenceRecord) -> dict[str, Any]:
    return {
        "evidence_id": record.evidence_id,
        "source_id": record.source_id,
        "authority_tier": record.authority_tier.value,
        "risk_categories": [_category_value(category) for category in record.risk_categories],
        "verification_status": record.verification_status.value,
        "score_eligible": record.score_eligible,
        "excerpt": record.excerpt_ko or record.article_ref or record.page_ref or "excerpt unavailable",
    }


def _practice_reference_payload(reference: PracticeReference) -> dict[str, Any]:
    return {
        "reference_id": reference.reference_id,
        "risk_category": _category_value(reference.risk_category),
        "clause_id": reference.clause_id,
        "explanation_ko": reference.explanation_ko,
        "explanation_en_alias": reference.explanation_en_alias,
        "questions": list(reference.questions),
        "score_eligible": False,
        "practice_reference": True,
    }


def _assumption_payloads(report: AnalysisReport) -> list[str]:
    assumptions: list[str] = []
    for exposure in report.assessment.monetary_exposures:
        assumptions.extend(exposure.assumptions)
    return _dedupe_text(assumptions)


def _question_payloads(
    report: AnalysisReport,
    practice_references: tuple[PracticeReference, ...],
) -> list[dict[str, str]]:
    questions: list[dict[str, str]] = []
    for clause in report.assessment.clause_assessments:
        for question in clause.questions:
            questions.append({"clause_id": clause.clause_id, "question": question})
    for reference in practice_references:
        for question in reference.questions:
            questions.append({"clause_id": reference.clause_id, "question": question})
    seen: set[tuple[str, str]] = set()
    deduped: list[dict[str, str]] = []
    for item in questions:
        key = (item["clause_id"], item["question"])
        if key not in seen:
            seen.add(key)
            deduped.append(item)
    return deduped


def _merged_disclaimers(report: AnalysisReport) -> list[str]:
    return _dedupe_text([*report.disclaimers, *EXPORT_DISCLAIMERS])


def _scrub_raw_image_fields(value: Any) -> Any:
    if isinstance(value, bytes | bytearray | memoryview):
        return "[bytes excluded]"
    if isinstance(value, list):
        return [_scrub_raw_image_fields(item) for item in value]
    if isinstance(value, dict):
        scrubbed: dict[Any, Any] = {}
        for key, item in value.items():
            key_text = str(key).lower()
            if key_text in _RAW_IMAGE_KEYS:
                continue
            scrubbed[key] = _scrub_raw_image_fields(item)
        return scrubbed
    return value


def _coerce_export_format(
    value: ExportFormat | str | None,
    output_path: str | Path | None,
) -> ExportFormat:
    if isinstance(value, ExportFormat):
        return value
    if value is not None:
        try:
            return ExportFormat(str(value))
        except ValueError as exc:
            raise ReportExportError(f"unsupported export format: {value}") from exc
    if output_path is None:
        raise ReportExportError("export format is required")
    suffix = Path(output_path).suffix.lower()
    for fmt, expected in _EXPORT_EXTENSIONS.items():
        if suffix == expected:
            return fmt
    raise ReportExportError(f"cannot infer report export format from suffix: {suffix or '(none)'}")


def _safe_stem(value: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip(".-_")
    return stem or "fink-report"


def _category_value(category: RiskCategory | str) -> str:
    return category.value if isinstance(category, RiskCategory) else str(category)


def _string_or_none(value: Any) -> str | None:
    return None if value is None else str(value)


def _metadata_text(value: Any) -> str:
    if type(value) is bool:
        return str(value).lower()
    return str(value)


def _dedupe_text(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result

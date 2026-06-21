from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from fink.ingest import EphemeralIngestSession, IngestValidationError, IngestedDocument


@dataclass(frozen=True)
class OCRPreviewSpan:
    span_id: str
    page_index: int
    text: str
    confidence: float
    bbox: dict[str, int]
    is_user_corrected: bool


@dataclass(frozen=True)
class OCRPreviewPage:
    page_id: str
    page_index: int
    rotation_deg: int
    text_source: str
    is_user_corrected: bool
    spans: tuple[OCRPreviewSpan, ...]


def build_ocr_preview(ingested: IngestedDocument) -> tuple[OCRPreviewPage, ...]:
    """Return OCR preview data safe for an in-memory local UI session."""

    document = ingested.document
    if document is None or document.pages is None:
        raise IngestValidationError("ingested item has no OCR preview pages")

    return tuple(
        OCRPreviewPage(
            page_id=page.page_id,
            page_index=page.page_index,
            rotation_deg=page.rotation_deg,
            text_source=page.text_source.value,
            is_user_corrected=page.is_user_corrected,
            spans=tuple(
                OCRPreviewSpan(
                    span_id=span.span_id,
                    page_index=page.page_index,
                    text=span.corrected_text if span.corrected_text is not None else span.text,
                    confidence=span.confidence,
                    bbox=dict(span.bbox),
                    is_user_corrected=span.corrected_text is not None,
                )
                for span in page.spans
            ),
        )
        for page in document.pages
    )


def apply_inline_ocr_correction(
    session: EphemeralIngestSession,
    ingested: IngestedDocument,
    span_id: str,
    corrected_text: str,
    *,
    counts_for_review_estimate: bool = True,
) -> IngestedDocument:
    """Apply a preview edit through the ingest correction flow."""

    return session.correct_ocr_span(
        ingested,
        span_id,
        corrected_text,
        counts_for_review_estimate=counts_for_review_estimate,
    )


def preview_text(preview: Iterable[OCRPreviewPage]) -> str:
    return "\n".join(span.text for page in preview for span in page.spans)

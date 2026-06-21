from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from fink.ingest import EphemeralIngestSession, IngestedDocument
from fink.schemas import InputMode, MimeType, RuntimeProfile, ValidationStatus
from fink.web.ocr_preview import apply_inline_ocr_correction, build_ocr_preview

PDF_LOCAL_NOTICE = "PDF processed locally; not uploaded anywhere."
PAGE_OPERATIONS = ("preview", "reorder", "rotate", "delete", "correct_ocr")


@dataclass(frozen=True)
class IngestModeControl:
    mode: str
    label: str
    input_kind: str
    accept: str
    aria_label: str
    capture: str = ""
    mobile_enabled: bool = True
    desktop_enabled: bool = True
    reaches_report: bool = True


@dataclass(frozen=True)
class IngestUILayout:
    layout_id: str
    runtime_profile: str
    columns: str
    min_touch_target_px: int
    input_modes: tuple[str, ...]
    page_operations: tuple[str, ...]
    pdf_upload_enabled: bool


@dataclass(frozen=True)
class PageOperationState:
    page_count: int
    page_indexes: tuple[int, ...]
    rotations_deg: tuple[int, ...]
    text_sources: tuple[str, ...]
    page_operations: tuple[str, ...]
    can_delete: bool


@dataclass(frozen=True)
class WebIngestSummary:
    input_mode: str
    validation_status: str
    report_ready: bool
    page_count: int
    local_error: str | None
    page_operations: tuple[str, ...]


_INPUT_MODE_CONTROLS = (
    IngestModeControl(
        mode=InputMode.CAMERA.value,
        label="Camera",
        input_kind="file",
        accept="image/*",
        capture="environment",
        aria_label="Capture contract pages with the device camera",
    ),
    IngestModeControl(
        mode=InputMode.IMAGE.value,
        label="Image",
        input_kind="file",
        accept="image/png,image/jpeg,image/webp,image/heic,image/heif",
        aria_label="Choose contract page images",
    ),
    IngestModeControl(
        mode=InputMode.PDF.value,
        label="PDF",
        input_kind="file",
        accept="application/pdf,.pdf",
        aria_label="Choose a PDF contract",
    ),
    IngestModeControl(
        mode=InputMode.PASTE.value,
        label="Paste",
        input_kind="textarea",
        accept="text/plain",
        aria_label="Paste clause text",
    ),
)

_INGEST_LAYOUTS = (
    IngestUILayout(
        layout_id="mobile",
        runtime_profile=RuntimeProfile.MOBILE_LITE.value,
        columns="single",
        min_touch_target_px=44,
        input_modes=tuple(control.mode for control in _INPUT_MODE_CONTROLS),
        page_operations=PAGE_OPERATIONS,
        pdf_upload_enabled=True,
    ),
    IngestUILayout(
        layout_id="desktop",
        runtime_profile=RuntimeProfile.DESKTOP_FULL.value,
        columns="two-pane",
        min_touch_target_px=44,
        input_modes=tuple(control.mode for control in _INPUT_MODE_CONTROLS),
        page_operations=PAGE_OPERATIONS,
        pdf_upload_enabled=True,
    ),
)

_PDF_ERROR_MESSAGES = {
    ValidationStatus.REJECTED_UNSUPPORTED: (
        "PDF rejected locally: choose a valid PDF whose file type is application/pdf. "
        "Nothing was transmitted."
    ),
    ValidationStatus.REJECTED_CORRUPT: (
        "PDF rejected locally: the file appears corrupted or truncated. Nothing was transmitted."
    ),
    ValidationStatus.REJECTED_ENCRYPTED: (
        "PDF rejected locally: encrypted PDFs require a local password flow. "
        "No remote decryption was attempted."
    ),
    ValidationStatus.REJECTED_OVERSIZED: (
        "PDF rejected locally: the file exceeds the configured page or byte limit. "
        "Nothing was transmitted."
    ),
}


def input_mode_controls() -> tuple[IngestModeControl, ...]:
    return _INPUT_MODE_CONTROLS


def responsive_ingest_layouts() -> tuple[IngestUILayout, ...]:
    return _INGEST_LAYOUTS


def local_upload_error(ingested: IngestedDocument) -> str | None:
    document = ingested.document
    if document is None or document.validation_status is ValidationStatus.ACCEPTED:
        return None
    if document.mime_type is MimeType.PDF:
        return _PDF_ERROR_MESSAGES.get(
            document.validation_status,
            f"PDF rejected locally: {document.validation_status.value}. Nothing was transmitted.",
        )
    return f"Upload rejected locally: {document.validation_status.value}. Nothing was transmitted."


def summarize_ingest_result(ingested: IngestedDocument) -> WebIngestSummary:
    document = ingested.document
    if document is None:
        return WebIngestSummary(
            input_mode=ingested.input_mode.value,
            validation_status=ValidationStatus.ACCEPTED.value,
            report_ready=True,
            page_count=0,
            local_error=None,
            page_operations=(),
        )

    accepted = document.validation_status is ValidationStatus.ACCEPTED
    return WebIngestSummary(
        input_mode=ingested.input_mode.value,
        validation_status=document.validation_status.value,
        report_ready=accepted,
        page_count=document.page_count if accepted else 0,
        local_error=local_upload_error(ingested),
        page_operations=PAGE_OPERATIONS if accepted and document.pages else (),
    )


def page_operation_state(ingested: IngestedDocument) -> PageOperationState:
    preview = build_ocr_preview(ingested)
    return PageOperationState(
        page_count=len(preview),
        page_indexes=tuple(page.page_index for page in preview),
        rotations_deg=tuple(page.rotation_deg for page in preview),
        text_sources=tuple(page.text_source for page in preview),
        page_operations=PAGE_OPERATIONS,
        can_delete=len(preview) > 1,
    )


def reorder_preview_pages(
    session: EphemeralIngestSession,
    ingested: IngestedDocument,
    page_order: Sequence[int],
) -> IngestedDocument:
    return session.reorder_pages(ingested, page_order)


def move_preview_page(
    session: EphemeralIngestSession,
    ingested: IngestedDocument,
    *,
    from_index: int,
    to_index: int,
) -> IngestedDocument:
    state = page_operation_state(ingested)
    order = list(range(state.page_count))
    page = order.pop(from_index)
    order.insert(to_index, page)
    return reorder_preview_pages(session, ingested, order)


def rotate_preview_page(
    session: EphemeralIngestSession,
    ingested: IngestedDocument,
    *,
    page_index: int,
    rotation_deg: int,
) -> IngestedDocument:
    return session.rotate_page(ingested, page_index, rotation_deg)


def delete_preview_page(
    session: EphemeralIngestSession,
    ingested: IngestedDocument,
    *,
    page_index: int,
) -> IngestedDocument:
    return session.delete_page(ingested, page_index)


def correct_preview_span(
    session: EphemeralIngestSession,
    ingested: IngestedDocument,
    *,
    span_id: str,
    corrected_text: str,
) -> IngestedDocument:
    return apply_inline_ocr_correction(session, ingested, span_id, corrected_text)

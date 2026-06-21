"""Local web helpers for FInk's ephemeral OCR preview flow."""

from fink.web.ocr_preview import (
    OCRPreviewPage,
    OCRPreviewSpan,
    apply_inline_ocr_correction,
    build_ocr_preview,
    preview_text,
)

__all__ = [
    "OCRPreviewPage",
    "OCRPreviewSpan",
    "apply_inline_ocr_correction",
    "build_ocr_preview",
    "preview_text",
]

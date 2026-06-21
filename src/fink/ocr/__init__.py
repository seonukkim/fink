"""Offline OCR helpers for FInk.

The public API returns the shared spec-02 OCRPage/OCRSpan schema objects. No
remote OCR service or runtime network dependency is used.
"""

from fink.ocr.engine import (
    LocalOCRConfig,
    LocalOCREngine,
    OCRBackendUnavailable,
    OCRError,
    OCRMetrics,
    character_error_rate,
    detect_span_language,
    evaluate_ocr,
    ocr_page_text,
    ocr_pages_text,
    word_error_rate,
)

__all__ = [
    "LocalOCRConfig",
    "LocalOCREngine",
    "OCRBackendUnavailable",
    "OCRError",
    "OCRMetrics",
    "character_error_rate",
    "detect_span_language",
    "evaluate_ocr",
    "ocr_page_text",
    "ocr_pages_text",
    "word_error_rate",
]

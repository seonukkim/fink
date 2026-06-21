"""Local web helpers for FInk's responsive, local-first web flow."""

from fink.web.app import (
    DEFAULT_LOOPBACK_HOST,
    DEFAULT_PORT,
    DISCLOSURE_ITEMS,
    LAN_CONFIRMATION_TEXT,
    NOT_LEGAL_ADVICE_BANNER,
    PRIVACY_BANNER,
    TRUSTED_LAN_WARNING,
    LocalASGIApp,
    WebBindSettings,
    WebBindingError,
    create_app,
    render_index_html,
    resolve_bind_settings,
    run,
)
from fink.web.ocr_preview import (
    OCRPreviewPage,
    OCRPreviewSpan,
    apply_inline_ocr_correction,
    build_ocr_preview,
    preview_text,
)

__all__ = [
    "DEFAULT_LOOPBACK_HOST",
    "DEFAULT_PORT",
    "DISCLOSURE_ITEMS",
    "LAN_CONFIRMATION_TEXT",
    "NOT_LEGAL_ADVICE_BANNER",
    "OCRPreviewPage",
    "OCRPreviewSpan",
    "PRIVACY_BANNER",
    "TRUSTED_LAN_WARNING",
    "LocalASGIApp",
    "WebBindSettings",
    "WebBindingError",
    "apply_inline_ocr_correction",
    "build_ocr_preview",
    "create_app",
    "preview_text",
    "render_index_html",
    "resolve_bind_settings",
    "run",
]

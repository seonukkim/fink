from __future__ import annotations

import hashlib
import importlib
import os
import re
import shutil
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Sequence
from uuid import uuid4

from fink.schemas import (
    FINANCIAL_RISK_CATEGORIES,
    AnalysisReport,
    AnalysisRequest,
    ConfidenceBreakdown,
    DocumentAssessment,
    ExportFormat,
    ExtractedFinancialTerms,
    HumanCorrection,
    InputMode,
    Lang,
    MimeType,
    OCRPage,
    OCRSpan,
    PathwayLabel,
    RuntimeProfile,
    TargetType,
    TextSource,
    TimeExposure,
    UILocale,
    Unit,
    UploadedDocument,
    ValidationStatus,
)

PDF_LITERAL_RE = re.compile(rb"\((?:\\.|[^\\)])*\)")
PDF_TEXT_TJ_RE = re.compile(rb"(\((?:\\.|[^\\)])*\))\s*Tj")
PDF_TEXT_TJ_ARRAY_RE = re.compile(rb"\[(.*?)\]\s*TJ", re.DOTALL)
PDF_PAGE_RE = re.compile(rb"/Type\s*/Page\b")
PDF_COUNT_RE = re.compile(rb"/Count\s+(\d+)")
PERCENT_RE = re.compile(r"(?P<value>\d+(?:\.\d+)?)\s*%")
MONEY_RE = re.compile(r"(?P<value>\d{1,3}(?:,\d{3})+|\d+)\s*(?:원|KRW|krw)")
DAY_RE = re.compile(r"(?P<value>\d+(?:\.\d+)?)\s*(?:days?|일)(?=\s|$|[.,;:)\\]])")
MONTH_RE = re.compile(r"(?P<value>\d+(?:\.\d+)?)\s*(?:months?|개월)(?=\s|$|[.,;:)\\]])")
SUPPORTED_IMAGE_SUFFIXES = frozenset({".jpg", ".jpeg", ".png", ".heic", ".heif", ".webp"})
SUPPORTED_HEIF_BRANDS = (b"heic", b"heix", b"hevc", b"hevx", b"mif1", b"msf1")
CORRECTION_REVIEW_MINUTES = 1.5


class IngestValidationError(ValueError):
    """Raised when an input cannot be represented as a local ingestion request."""


@dataclass(frozen=True)
class IngestLimits:
    max_bytes: int = 25 * 1024 * 1024
    max_pages: int = 50
    session_ttl: timedelta = timedelta(minutes=30)


@dataclass(frozen=True)
class RasterPage:
    path: Path
    width_px: int
    height_px: int


@dataclass(frozen=True)
class IngestedDocument:
    request: AnalysisRequest
    workspace: Path
    input_mode: InputMode
    filename_hash: str | None
    document: UploadedDocument | None = None
    stored_path: Path | None = None
    derived_paths: tuple[Path, ...] = ()
    corrections: tuple[HumanCorrection, ...] = ()
    extracted_terms: tuple[ExtractedFinancialTerms, ...] = ()
    extraction_revision: int = 0

    def build_report(self) -> AnalysisReport:
        return build_ingest_report(
            self.request,
            corrections=self.corrections,
            extracted_terms=self.extracted_terms,
        )

    def to_log_record(self) -> dict[str, Any]:
        document = self.document
        return {
            "input_mode": self.input_mode.value,
            "filename_hash": self.filename_hash,
            "page_count": document.page_count if document is not None else 0,
            "validation_status": (
                document.validation_status.value if document is not None else "accepted"
            ),
            "derived_file_count": len(self.derived_paths),
            "correction_count": len(self.corrections),
            "extracted_term_count": len(self.extracted_terms),
            "extraction_revision": self.extraction_revision,
        }


class EphemeralIngestSession:
    """Ingest camera/image/PDF/paste inputs into a private local workspace."""

    def __init__(
        self,
        upload_root: Path | str | None = None,
        *,
        limits: IngestLimits | None = None,
        ui_locale: UILocale = UILocale.KO,
        runtime_profile: RuntimeProfile = RuntimeProfile.DESKTOP_FULL,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.limits = limits or IngestLimits()
        self.ui_locale = ui_locale
        self.runtime_profile = runtime_profile
        self._now = now or datetime.now
        self.session_id = uuid4().hex
        self.upload_root = Path(upload_root) if upload_root is not None else Path.cwd() / "uploads"
        self.sessions_root = self.upload_root / "sessions"
        _mkdir_private(self.upload_root)
        _mkdir_private(self.sessions_root)
        self.workspace = self.sessions_root / self.session_id
        _mkdir_private(self.workspace, exist_ok=False)
        self._closed = False

    def __enter__(self) -> EphemeralIngestSession:
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.clear()

    def __del__(self) -> None:
        try:
            self.clear()
        except Exception:
            return

    def ingest_camera(
        self,
        source_path: Path | str,
        *,
        original_filename: str | None = None,
        content_type: str | None = None,
    ) -> IngestedDocument:
        return self._ingest_image_like(
            Path(source_path),
            InputMode.CAMERA,
            original_filename=original_filename,
            content_type=content_type,
        )

    def ingest_image(
        self,
        source_path: Path | str,
        *,
        original_filename: str | None = None,
        content_type: str | None = None,
    ) -> IngestedDocument:
        return self._ingest_image_like(
            Path(source_path),
            InputMode.IMAGE,
            original_filename=original_filename,
            content_type=content_type,
        )

    def ingest_pdf(
        self,
        source_path: Path | str,
        *,
        original_filename: str | None = None,
        content_type: str | None = None,
    ) -> IngestedDocument:
        self._ensure_open()
        source = Path(source_path)
        data = source.read_bytes()
        raw_name = original_filename or source.name
        filename_hash = _filename_hash(raw_name)
        bytes_sha256 = _sha256(data)
        delete_after = self._now() + self.limits.session_ttl
        status = self._validate_pdf_bytes(data, content_type)
        page_count = _pdf_page_count(data) if status is ValidationStatus.ACCEPTED else 1
        if status is ValidationStatus.ACCEPTED and page_count > self.limits.max_pages:
            status = ValidationStatus.REJECTED_OVERSIZED

        if status is not ValidationStatus.ACCEPTED:
            document = self._document(
                filename_hash=filename_hash,
                mime_type=MimeType.PDF,
                magic_byte_verified=data.startswith(b"%PDF-"),
                is_encrypted=b"/Encrypt" in data,
                validation_status=status,
                page_count=1,
                temp_path=self.workspace / f"{filename_hash}.rejected",
                bytes_sha256=bytes_sha256,
                delete_after=delete_after,
                pages=None,
            )
            return self._result_for_document(InputMode.PDF, filename_hash, document, None, ())

        stored_path = self.workspace / f"{filename_hash}-{bytes_sha256[:12]}.pdf"
        _write_private_bytes(stored_path, data)
        raster_dir = self.workspace / f"{filename_hash}-pages"
        _mkdir_private(raster_dir)
        rasters = _rasterize_pdf_locally(stored_path, page_count, raster_dir)
        texts = _extract_pdf_texts(data, page_count)
        pages = tuple(
            _page_from_raster(
                page,
                page_index=idx,
                text=texts[idx],
                text_source=TextSource.TEXT_LAYER if texts[idx].strip() else TextSource.OCR,
            )
            for idx, page in enumerate(rasters)
        )
        document = self._document(
            filename_hash=filename_hash,
            mime_type=MimeType.PDF,
            magic_byte_verified=True,
            is_encrypted=False,
            validation_status=ValidationStatus.ACCEPTED,
            page_count=page_count,
            temp_path=stored_path,
            bytes_sha256=bytes_sha256,
            delete_after=delete_after,
            pages=pages,
        )
        return self._result_for_document(
            InputMode.PDF,
            filename_hash,
            document,
            stored_path,
            tuple(page.path for page in rasters),
        )

    def ingest_paste(self, text: str) -> IngestedDocument:
        self._ensure_open()
        if not isinstance(text, str) or not text.strip():
            raise IngestValidationError("pasted text must be nonblank")
        request_id = str(uuid4())
        data = text.encode("utf-8")
        filename_hash = _filename_hash("paste.txt")
        stored_path = self.workspace / f"{filename_hash}-{_sha256(data)[:12]}.txt"
        _write_private_bytes(stored_path, data)
        request = AnalysisRequest(
            request_id=request_id,
            created_at=self._now(),
            ui_locale=self.ui_locale,
            input_mode=InputMode.PASTE,
            runtime_profile=self.runtime_profile,
            documents=(),
            consent_local_only=True,
            pasted_text=text,
        )
        return IngestedDocument(
            request=request,
            workspace=self.workspace,
            input_mode=InputMode.PASTE,
            filename_hash=filename_hash,
            stored_path=stored_path,
        )

    def reorder_pages(
        self, ingested: IngestedDocument, page_order: Sequence[int]
    ) -> IngestedDocument:
        document, pages = _require_pages(ingested)
        order = tuple(page_order)
        if sorted(order) != list(range(len(pages))):
            raise IngestValidationError("page_order must be a permutation of existing pages")
        reordered_pages = tuple(
            replace(pages[old_index], page_index=new_index)
            for new_index, old_index in enumerate(order)
        )
        derived_paths = ingested.derived_paths
        if len(derived_paths) == len(pages):
            derived_paths = tuple(derived_paths[old_index] for old_index in order)
        return self._replace_document(
            ingested,
            replace(document, pages=reordered_pages, page_count=len(reordered_pages)),
            derived_paths=derived_paths,
        )

    def rotate_page(
        self, ingested: IngestedDocument, page_index: int, rotation_deg: int
    ) -> IngestedDocument:
        document, pages = _require_pages(ingested)
        if rotation_deg not in {0, 90, 180, 270}:
            raise IngestValidationError("rotation_deg must be 0, 90, 180, or 270")
        if page_index < 0 or page_index >= len(pages):
            raise IngestValidationError("page_index out of range")
        updated_pages = tuple(
            replace(page, rotation_deg=rotation_deg) if idx == page_index else page
            for idx, page in enumerate(pages)
        )
        return self._replace_document(ingested, replace(document, pages=updated_pages))

    def delete_page(self, ingested: IngestedDocument, page_index: int) -> IngestedDocument:
        document, pages = _require_pages(ingested)
        if len(pages) <= 1:
            raise IngestValidationError("at least one page must remain")
        if page_index < 0 or page_index >= len(pages):
            raise IngestValidationError("page_index out of range")
        updated_pages = tuple(
            replace(page, page_index=new_index)
            for new_index, page in enumerate(
                page for idx, page in enumerate(pages) if idx != page_index
            )
        )
        derived_paths = ingested.derived_paths
        if len(derived_paths) == len(pages):
            deleted_path = derived_paths[page_index]
            if deleted_path.exists():
                deleted_path.unlink()
            derived_paths = tuple(
                path for idx, path in enumerate(derived_paths) if idx != page_index
            )
        return self._replace_document(
            ingested,
            replace(document, pages=updated_pages, page_count=len(updated_pages)),
            derived_paths=derived_paths,
        )

    def correct_ocr_span(
        self,
        ingested: IngestedDocument,
        span_id: str,
        corrected_text: str,
        *,
        counts_for_review_estimate: bool = True,
    ) -> IngestedDocument:
        """Apply an inline OCR correction and refresh extraction over edited text."""

        self._ensure_open()
        if not isinstance(corrected_text, str):
            raise IngestValidationError("corrected_text must be str")
        if not span_id:
            raise IngestValidationError("span_id must be nonblank")
        document, pages = _require_pages(ingested)

        found = False
        before = ""
        updated_pages: list[OCRPage] = []
        for page in pages:
            page_touched = False
            updated_spans: list[OCRSpan] = []
            for span in page.spans:
                if span.span_id == span_id:
                    found = True
                    page_touched = True
                    before = _span_text(span)
                    updated_spans.append(replace(span, corrected_text=corrected_text))
                else:
                    updated_spans.append(span)
            updated_pages.append(
                replace(page, spans=tuple(updated_spans), is_user_corrected=True)
                if page_touched
                else page
            )

        if not found:
            raise IngestValidationError("span_id not found")

        correction = HumanCorrection(
            correction_id=f"correction-{uuid4().hex}",
            target_type=TargetType.OCR_SPAN,
            target_id=span_id,
            before=before,
            after=corrected_text,
            created_at=self._now(),
            counts_for_review_estimate=counts_for_review_estimate,
        )
        refreshed = self._replace_document(
            ingested,
            replace(document, pages=tuple(updated_pages)),
        )
        return replace(
            refreshed,
            corrections=(*ingested.corrections, correction),
            extraction_revision=ingested.extraction_revision + 1,
        )

    def clear(self) -> None:
        if self._closed:
            return
        shutil.rmtree(self.workspace, ignore_errors=True)
        self._closed = True

    close = clear
    session_end = clear

    @property
    def is_cleared(self) -> bool:
        return not self.workspace.exists()

    def _ingest_image_like(
        self,
        source: Path,
        input_mode: InputMode,
        *,
        original_filename: str | None,
        content_type: str | None,
    ) -> IngestedDocument:
        self._ensure_open()
        data = source.read_bytes()
        raw_name = original_filename or source.name
        filename_hash = _filename_hash(raw_name)
        bytes_sha256 = _sha256(data)
        delete_after = self._now() + self.limits.session_ttl
        oversized = len(data) > self.limits.max_bytes
        supported_image = _is_supported_image(data, raw_name, content_type)
        status = ValidationStatus.ACCEPTED
        if oversized:
            status = ValidationStatus.REJECTED_OVERSIZED
        elif not supported_image:
            status = ValidationStatus.REJECTED_UNSUPPORTED

        if status is not ValidationStatus.ACCEPTED:
            document = self._document(
                filename_hash=filename_hash,
                mime_type=MimeType.IMAGE,
                magic_byte_verified=supported_image,
                is_encrypted=False,
                validation_status=status,
                page_count=1,
                temp_path=self.workspace / f"{filename_hash}.rejected",
                bytes_sha256=bytes_sha256,
                delete_after=delete_after,
                pages=None,
            )
            return self._result_for_document(input_mode, filename_hash, document, None, ())

        suffix = _safe_suffix(raw_name, ".img")
        stored_path = self.workspace / f"{filename_hash}-{bytes_sha256[:12]}{suffix}"
        _write_private_bytes(stored_path, data)
        width_px, height_px = _image_dimensions(data)
        page = OCRPage(
            page_id=f"page-{uuid4().hex}",
            page_index=0,
            rotation_deg=0,
            width_px=width_px,
            height_px=height_px,
            spans=(),
            page_ocr_confidence=0.0,
            text_source=TextSource.OCR,
            is_user_corrected=False,
        )
        document = self._document(
            filename_hash=filename_hash,
            mime_type=MimeType.IMAGE,
            magic_byte_verified=True,
            is_encrypted=False,
            validation_status=ValidationStatus.ACCEPTED,
            page_count=1,
            temp_path=stored_path,
            bytes_sha256=bytes_sha256,
            delete_after=delete_after,
            pages=(page,),
        )
        return self._result_for_document(input_mode, filename_hash, document, stored_path, ())

    def _validate_pdf_bytes(
        self, data: bytes, content_type: str | None
    ) -> ValidationStatus:
        if len(data) > self.limits.max_bytes:
            return ValidationStatus.REJECTED_OVERSIZED
        if content_type is not None and content_type.lower() != MimeType.PDF.value:
            return ValidationStatus.REJECTED_UNSUPPORTED
        if not data.startswith(b"%PDF-"):
            return ValidationStatus.REJECTED_UNSUPPORTED
        if b"/Encrypt" in data:
            return ValidationStatus.REJECTED_ENCRYPTED
        if b"%%EOF" not in data or _pdf_page_count(data) < 1:
            return ValidationStatus.REJECTED_CORRUPT
        return ValidationStatus.ACCEPTED

    def _document(
        self,
        *,
        filename_hash: str,
        mime_type: MimeType,
        magic_byte_verified: bool,
        is_encrypted: bool,
        validation_status: ValidationStatus,
        page_count: int,
        temp_path: Path,
        bytes_sha256: str,
        delete_after: datetime,
        pages: tuple[OCRPage, ...] | None,
    ) -> UploadedDocument:
        return UploadedDocument(
            document_id=str(uuid4()),
            filename_hash=filename_hash,
            mime_type=mime_type,
            magic_byte_verified=magic_byte_verified,
            is_encrypted=is_encrypted,
            validation_status=validation_status,
            page_count=page_count,
            temp_path=str(temp_path),
            bytes_sha256=bytes_sha256,
            delete_after=delete_after,
            pages=pages,
        )

    def _result_for_document(
        self,
        input_mode: InputMode,
        filename_hash: str,
        document: UploadedDocument,
        stored_path: Path | None,
        derived_paths: tuple[Path, ...],
    ) -> IngestedDocument:
        request = AnalysisRequest(
            request_id=str(uuid4()),
            created_at=self._now(),
            ui_locale=self.ui_locale,
            input_mode=input_mode,
            runtime_profile=self.runtime_profile,
            documents=(document,),
            consent_local_only=True,
        )
        return IngestedDocument(
            request=request,
            workspace=self.workspace,
            input_mode=input_mode,
            filename_hash=filename_hash,
            document=document,
            stored_path=stored_path,
            derived_paths=derived_paths,
            extracted_terms=_extract_financial_terms_from_pages(document.pages or ()),
        )

    def _replace_document(
        self,
        ingested: IngestedDocument,
        document: UploadedDocument,
        *,
        derived_paths: tuple[Path, ...] | None = None,
    ) -> IngestedDocument:
        request = replace(ingested.request, documents=(document,))
        return replace(
            ingested,
            request=request,
            document=document,
            derived_paths=ingested.derived_paths if derived_paths is None else derived_paths,
            extracted_terms=_extract_financial_terms_from_pages(document.pages or ()),
        )

    def _ensure_open(self) -> None:
        if self._closed or not self.workspace.exists():
            raise IngestValidationError("ingest session is closed")


def build_ingest_report(
    request: AnalysisRequest,
    *,
    corrections: Sequence[HumanCorrection] = (),
    extracted_terms: Sequence[ExtractedFinancialTerms] = (),
) -> AnalysisReport:
    document_id = request.documents[0].document_id if request.documents else request.request_id
    ocr_confidence = _average_ocr_confidence(request)
    review_minutes = correction_review_minutes(corrections)
    drivers = ["ingestion-only report; downstream review not run"]
    if corrections:
        drivers.append(
            f"{len(corrections)} OCR correction(s) included in the review-time heuristic"
        )
    if corrections and extracted_terms:
        drivers.append("corrected OCR text refreshed preview financial-term extraction")
    elif extracted_terms:
        drivers.append("OCR text populated preview financial-term extraction")
    assessment = DocumentAssessment(
        document_id=document_id,
        review_priority_score=0,
        category_scores={category: 0.0 for category in FINANCIAL_RISK_CATEGORIES},
        clause_assessments=(),
        monetary_exposures=(),
        time_exposure=TimeExposure(
            measured_analysis_runtime_seconds=0.0,
            estimated_human_review_minutes=review_minutes,
            pathway_label=PathwayLabel.CLARIFICATION_LIKELY_SUFFICIENT,
        ),
        confidence=ConfidenceBreakdown(
            ocr_confidence=ocr_confidence,
            evidence_confidence=0.0,
            data_completeness=0.0,
            overall_confidence=0.0,
            drivers=tuple(drivers),
        ),
        scoring_config_version="ingest-only-v1",
    )
    return AnalysisReport(
        report_id=f"report-{uuid4().hex}",
        request_id=request.request_id,
        assessment=assessment,
        disclaimers=(
            "FInk reports Contractual Financial Review Priority only and is not legal advice.",
        ),
        generated_text_flag=False,
        contains_raw_image=False,
        export_format=ExportFormat.JSON,
    )


def correction_review_minutes(corrections: Sequence[HumanCorrection]) -> float:
    correction_count = sum(1 for correction in corrections if correction.counts_for_review_estimate)
    return correction_count * CORRECTION_REVIEW_MINUTES


def _require_pages(ingested: IngestedDocument) -> tuple[UploadedDocument, tuple[OCRPage, ...]]:
    document = ingested.document
    if document is None or document.pages is None:
        raise IngestValidationError("ingested item has no editable pages")
    return document, tuple(document.pages)


def _extract_financial_terms_from_pages(
    pages: Sequence[OCRPage],
) -> tuple[ExtractedFinancialTerms, ...]:
    terms: list[ExtractedFinancialTerms] = []
    for page in pages:
        for span in page.spans:
            terms.extend(_extract_financial_terms_from_span(span))
    return tuple(terms)


def _extract_financial_terms_from_span(span: OCRSpan) -> tuple[ExtractedFinancialTerms, ...]:
    text = _span_text(span)
    terms: list[ExtractedFinancialTerms] = []
    specs: tuple[
        tuple[re.Pattern[str], str, Unit, Callable[[str], Decimal | float]],
        ...,
    ] = (
        (PERCENT_RE, "REVENUE_SHARE_RATE", Unit.FRAC, _percent_value),
        (MONEY_RE, "GROSS_SALES", Unit.KRW, _money_value),
        (DAY_RE, "PAYMENT_DUE_DAYS", Unit.DAYS, _number_value),
        (MONTH_RE, "CONTRACT_DURATION_MONTHS", Unit.MONTHS, _number_value),
    )
    for pattern, feature_id, unit, normalizer in specs:
        for match_index, match in enumerate(pattern.finditer(text)):
            raw_value = normalizer(match.group("value"))
            # A preview heuristic must never assert an out-of-domain normalized
            # value: a percentage above 100% is not a [0,1] fraction. Keep the
            # raw text but flag the term opaque so a >100% figure (e.g. a penalty
            # multiplier) cannot raise SchemaValidationError and crash ingest.
            is_open_ended = unit is Unit.FRAC and not (Decimal("0") <= raw_value <= Decimal("1"))
            value_norm: Decimal | float | None = None if is_open_ended else raw_value
            terms.append(
                ExtractedFinancialTerms(
                    term_id=_term_id(span.span_id, feature_id, match_index),
                    clause_id=f"clause-preview-{_slug_id(span.span_id)}",
                    feature_id=feature_id,
                    value_raw=match.group(0),
                    unit=unit,
                    is_open_ended=is_open_ended,
                    extraction_confidence=span.confidence,
                    source_span_ids=(span.span_id,),
                    value_norm=value_norm,
                )
            )
    return tuple(terms)


def _span_text(span: OCRSpan) -> str:
    return span.corrected_text if span.corrected_text is not None else span.text


def _term_id(span_id: str, feature_id: str, match_index: int) -> str:
    return f"term-{_slug_id(span_id)}-{feature_id.lower()}-{match_index}"


def _slug_id(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "-", value).strip("-").lower()
    return slug or "span"


def _percent_value(value: str) -> Decimal:
    return Decimal(value) / Decimal("100")


def _money_value(value: str) -> Decimal:
    return Decimal(value.replace(",", ""))


def _number_value(value: str) -> float:
    return float(value)


def _average_ocr_confidence(request: AnalysisRequest) -> float:
    pages = [page for document in request.documents for page in (document.pages or ())]
    if request.input_mode is InputMode.PASTE:
        return 1.0
    if not pages:
        return 0.0
    return sum(page.page_ocr_confidence for page in pages) / len(pages)


def _filename_hash(filename: str) -> str:
    normalized = Path(filename).name.encode("utf-8", errors="surrogateescape")
    return hashlib.sha256(normalized).hexdigest()


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _mkdir_private(path: Path, *, exist_ok: bool = True) -> None:
    path.mkdir(parents=True, exist_ok=exist_ok, mode=0o700)
    os.chmod(path, 0o700)


def _write_private_bytes(path: Path, data: bytes) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(data)


def _safe_suffix(filename: str, fallback: str) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix and re.fullmatch(r"\.[a-z0-9]+", suffix):
        return suffix
    return fallback


def _is_supported_image(data: bytes, filename: str, content_type: str | None) -> bool:
    if content_type is not None and not content_type.lower().startswith("image/"):
        return False
    suffix = Path(filename).suffix.lower()
    if suffix not in SUPPORTED_IMAGE_SUFFIXES:
        return False
    if data.startswith(b"\xff\xd8\xff") or data.startswith(b"\x89PNG\r\n\x1a\n"):
        return True
    if len(data) >= 12 and data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return True
    if len(data) >= 12 and data[4:8] == b"ftyp" and data[8:12] in SUPPORTED_HEIF_BRANDS:
        return True
    return suffix in {".heic", ".heif"} and content_type in {"image/heic", "image/heif"}


def _image_dimensions(data: bytes) -> tuple[int, int]:
    png = _png_dimensions(data)
    if png is not None:
        return png
    jpeg = _jpeg_dimensions(data)
    if jpeg is not None:
        return jpeg
    return 1, 1


def _png_dimensions(data: bytes) -> tuple[int, int] | None:
    if len(data) < 24 or not data.startswith(b"\x89PNG\r\n\x1a\n"):
        return None
    width = int.from_bytes(data[16:20], "big")
    height = int.from_bytes(data[20:24], "big")
    if width > 0 and height > 0:
        return width, height
    return None


def _jpeg_dimensions(data: bytes) -> tuple[int, int] | None:
    if not data.startswith(b"\xff\xd8"):
        return None
    idx = 2
    while idx + 9 < len(data):
        if data[idx] != 0xFF:
            idx += 1
            continue
        marker = data[idx + 1]
        idx += 2
        if marker in {0xD8, 0xD9}:
            continue
        if idx + 2 > len(data):
            return None
        segment_length = int.from_bytes(data[idx : idx + 2], "big")
        if segment_length < 2 or idx + segment_length > len(data):
            return None
        if marker in {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB}:
            height = int.from_bytes(data[idx + 3 : idx + 5], "big")
            width = int.from_bytes(data[idx + 5 : idx + 7], "big")
            if width > 0 and height > 0:
                return width, height
        idx += segment_length
    return None


def _pdf_page_count(data: bytes) -> int:
    pages = len(PDF_PAGE_RE.findall(data))
    if pages:
        return pages
    counts = [int(match.group(1)) for match in PDF_COUNT_RE.finditer(data)]
    return max(counts) if counts else 0


def _rasterize_pdf_locally(
    pdf_path: Path, page_count: int, output_dir: Path
) -> tuple[RasterPage, ...]:
    rendered = _rasterize_with_pymupdf(pdf_path, page_count, output_dir)
    if rendered is not None:
        return rendered
    return tuple(_write_placeholder_raster(pdf_path, output_dir, idx) for idx in range(page_count))


def _rasterize_with_pymupdf(
    pdf_path: Path, page_count: int, output_dir: Path
) -> tuple[RasterPage, ...] | None:
    try:
        fitz = importlib.import_module("fitz")
        document = fitz.open(pdf_path)
        if len(document) < page_count:
            return None
        pages: list[RasterPage] = []
        for idx in range(page_count):
            page = document.load_page(idx)
            pixmap = page.get_pixmap(alpha=False)
            path = output_dir / f"page-{idx:04d}.png"
            pixmap.save(path)
            os.chmod(path, 0o600)
            pages.append(RasterPage(path=path, width_px=pixmap.width, height_px=pixmap.height))
        document.close()
        return tuple(pages)
    except Exception:
        return None


def _write_placeholder_raster(pdf_path: Path, output_dir: Path, page_index: int) -> RasterPage:
    seed = hashlib.sha256(pdf_path.read_bytes() + str(page_index).encode("ascii")).digest()
    path = output_dir / f"page-{page_index:04d}.ppm"
    payload = f"P3\n1 1\n255\n{seed[0]} {seed[1]} {seed[2]}\n".encode("ascii")
    _write_private_bytes(path, payload)
    return RasterPage(path=path, width_px=1, height_px=1)


def _extract_pdf_texts(data: bytes, page_count: int) -> tuple[str, ...]:
    strings: list[str] = []
    for match in PDF_TEXT_TJ_RE.finditer(data):
        strings.append(_decode_pdf_literal(match.group(1)))
    for match in PDF_TEXT_TJ_ARRAY_RE.finditer(data):
        strings.extend(
            _decode_pdf_literal(item.group(0))
            for item in PDF_LITERAL_RE.finditer(match.group(1))
        )
    text = " ".join(part.strip() for part in strings if part.strip())
    if not text:
        return tuple("" for _ in range(page_count))
    return (text,) + tuple("" for _ in range(max(page_count - 1, 0)))


def _decode_pdf_literal(token: bytes) -> str:
    raw = token[1:-1]
    out = bytearray()
    idx = 0
    while idx < len(raw):
        char = raw[idx]
        if char != 0x5C:
            out.append(char)
            idx += 1
            continue
        idx += 1
        if idx >= len(raw):
            break
        escaped = raw[idx]
        replacements = {
            ord("n"): b"\n",
            ord("r"): b"\r",
            ord("t"): b"\t",
            ord("b"): b"\b",
            ord("f"): b"\f",
            ord("("): b"(",
            ord(")"): b")",
            ord("\\"): b"\\",
        }
        if escaped in replacements:
            out.extend(replacements[escaped])
            idx += 1
            continue
        if 48 <= escaped <= 55:
            octal = bytes([escaped])
            idx += 1
            for _ in range(2):
                if idx < len(raw) and 48 <= raw[idx] <= 55:
                    octal += bytes([raw[idx]])
                    idx += 1
            out.append(int(octal, 8))
            continue
        out.append(escaped)
        idx += 1
    return out.decode("utf-8", errors="replace")


def _page_from_raster(
    raster: RasterPage, *, page_index: int, text: str, text_source: TextSource
) -> OCRPage:
    width = max(raster.width_px, 1)
    height = max(raster.height_px, 1)
    spans: tuple[OCRSpan, ...] = ()
    if text.strip():
        spans = (
            OCRSpan(
                span_id=f"page-{page_index}:span-0",
                text=text,
                bbox={"x": 0, "y": 0, "w": max(min(width, 100), 1), "h": max(min(height, 20), 1)},
                confidence=1.0,
                lang=_detect_lang(text),
            ),
        )
    return OCRPage(
        page_id=f"page-{page_index}",
        page_index=page_index,
        rotation_deg=0,
        width_px=width,
        height_px=height,
        spans=spans,
        page_ocr_confidence=1.0 if spans else 0.0,
        text_source=text_source,
        is_user_corrected=False,
    )


def _detect_lang(text: str) -> Lang:
    has_hangul = any("\uac00" <= char <= "\ud7a3" for char in text)
    has_alpha = any(("a" <= char.lower() <= "z") for char in text)
    has_digit = any(char.isdigit() for char in text)
    if has_hangul and has_alpha:
        return Lang.MIXED
    if has_hangul:
        return Lang.KO
    if has_alpha:
        return Lang.EN
    if has_digit:
        return Lang.NUM
    return Lang.MIXED

from __future__ import annotations

import json
import logging
import shutil
import tempfile
from dataclasses import dataclass, replace
from email.parser import BytesParser
from email.policy import default
from pathlib import Path
from threading import Lock
from typing import Any

from fink.ingest import EphemeralIngestSession, IngestLimits, IngestedDocument
from fink.ocr import LocalOCRConfig, LocalOCREngine, OCRBackendUnavailable, OCRError
from fink.schemas import OCRPage, TextSource, UILocale, ValidationStatus
from fink.web.analyze import analysis_result_to_payload, run_local_analysis

DEFAULT_UPLOAD_LIMITS = IngestLimits()
MAX_MULTIPART_OVERHEAD_BYTES = 1024 * 1024
TEXT_EXTENSIONS = frozenset({".txt"})
PDF_EXTENSIONS = frozenset({".pdf"})
IMAGE_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"})
TEXT_MIME_TYPES = frozenset({"text/plain"})
PDF_MIME_TYPES = frozenset({"application/pdf"})
IMAGE_MIME_TYPES = frozenset(
    {"image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"}
)
_PADDLE_OCR_BACKEND: Any | None = None
_PADDLE_OCR_BACKEND_LOCK = Lock()


@dataclass(frozen=True)
class UploadedAnalyzeFile:
    field_name: str
    filename: str
    content_type: str
    data: bytes


@dataclass(frozen=True)
class MultipartAnalyzeRequest:
    fields: dict[str, str]
    file: UploadedAnalyzeFile | None


class AnalyzeRequestError(ValueError):
    """Structured analyze-request error with no raw input or path details."""

    def __init__(
        self,
        *,
        error_code: str,
        status_code: int,
        validation_status: str,
        message_ko: str,
        message_en: str,
        action_ko: str,
        action_en: str,
    ) -> None:
        super().__init__(error_code)
        self.error_code = error_code
        self.status_code = status_code
        self.validation_status = validation_status
        self.message_ko = message_ko
        self.message_en = message_en
        self.action_ko = action_ko
        self.action_en = action_en

    def to_payload(self) -> dict[str, Any]:
        return {
            "local_only": True,
            "error_code": self.error_code,
            "validation_status": self.validation_status,
            "error": self.message_ko,
            "error_en": self.message_en,
            "next_action": self.action_ko,
            "next_action_en": self.action_en,
        }


def is_multipart_content_type(content_type: str | None) -> bool:
    return _base_content_type(content_type) == "multipart/form-data"


def parse_multipart_analyze_request(
    body: bytes, content_type: str | None
) -> MultipartAnalyzeRequest:
    if len(body) > DEFAULT_UPLOAD_LIMITS.max_bytes + MAX_MULTIPART_OVERHEAD_BYTES:
        raise _oversized_error()
    if not content_type or "boundary=" not in content_type:
        raise _request_invalid_error()

    header = (
        f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n"
    ).encode("utf-8")
    try:
        message = BytesParser(policy=default).parsebytes(header + body)
    except Exception as exc:
        raise _request_invalid_error() from exc
    if not message.is_multipart():
        raise _request_invalid_error()

    fields: dict[str, str] = {}
    upload: UploadedAnalyzeFile | None = None
    for part in message.iter_parts():
        disposition = part.get("Content-Disposition", "")
        if "form-data" not in disposition:
            continue
        name = part.get_param("name", header="content-disposition")
        if not name:
            continue
        filename = part.get_filename()
        payload = part.get_payload(decode=True) or b""
        if filename is None:
            fields[name] = _decode_form_value(payload, part.get_content_charset())
            continue
        if upload is not None:
            raise _unsupported_error()
        upload = UploadedAnalyzeFile(
            field_name=str(name),
            filename=str(filename),
            content_type=part.get_content_type(),
            data=payload,
        )
    return MultipartAnalyzeRequest(fields=fields, file=upload)


def assumptions_from_multipart_fields(fields: dict[str, str]) -> Any:
    raw_json = fields.get("assumptions")
    if raw_json:
        try:
            parsed = json.loads(raw_json)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None

    prefix = "assumptions["
    collected: dict[str, str] = {}
    for key, value in fields.items():
        if key.startswith(prefix) and key.endswith("]"):
            collected[key[len(prefix) : -1]] = value
    return collected or None


def analyze_multipart_request(
    request: MultipartAnalyzeRequest,
    *,
    scenario_inputs: Any | None,
    ui_locale: UILocale,
) -> dict[str, Any]:
    paste_text = request.fields.get("paste_text") or ""
    has_paste = bool(paste_text.strip())
    upload = request.file
    has_file = upload is not None and bool(upload.data)

    if has_paste and has_file:
        raise AnalyzeRequestError(
            error_code="BOTH_INPUTS_SUPPLIED",
            status_code=422,
            validation_status="rejected_both_inputs",
            message_ko="붙여넣기와 파일 업로드 중 하나만 선택하세요.",
            message_en="Send either pasted text or one uploaded file, not both.",
            action_ko="파일을 지우거나 붙여넣은 텍스트를 비운 뒤 다시 분석하세요.",
            action_en="Remove the file or clear the pasted text, then analyze again.",
        )
    if has_paste:
        result = run_local_analysis(
            pasted_text=paste_text,
            scenario_inputs=scenario_inputs,
            ui_locale=ui_locale,
        )
        return analysis_result_to_payload(result, ui_locale)
    if upload is None:
        raise _empty_input_error()
    return _analyze_upload(upload, scenario_inputs=scenario_inputs, ui_locale=ui_locale)


def _analyze_upload(
    upload: UploadedAnalyzeFile,
    *,
    scenario_inputs: Any | None,
    ui_locale: UILocale,
) -> dict[str, Any]:
    if not upload.data:
        raise _empty_file_error()
    if len(upload.data) > DEFAULT_UPLOAD_LIMITS.max_bytes:
        raise _oversized_error()

    upload_kind = _upload_kind(upload)
    if upload_kind == "text":
        text = _decode_text_upload(upload.data)
        if not text.strip():
            raise _empty_file_error()
        result = run_local_analysis(
            pasted_text=text,
            scenario_inputs=scenario_inputs,
            ui_locale=ui_locale,
        )
        return analysis_result_to_payload(result, ui_locale)

    with tempfile.TemporaryDirectory(prefix="fink-web-upload-") as temp_root:
        root = Path(temp_root)
        source_path = root / f"upload{_safe_upload_suffix(upload)}"
        source_path.write_bytes(upload.data)
        source_path.chmod(0o600)
        with EphemeralIngestSession(
            upload_root=root / "sessions",
            limits=DEFAULT_UPLOAD_LIMITS,
            ocr_engine=_UploadOCREngine(),
            ui_locale=ui_locale,
        ) as session:
            if upload_kind == "pdf":
                ingested = session.ingest_pdf(
                    source_path,
                    original_filename=upload.filename,
                    content_type=upload.content_type,
                )
                _raise_for_rejected_document(ingested)
                _raise_for_missing_ocr(ingested)
                _raise_for_empty_document(ingested)
                result = run_local_analysis(
                    ingested=ingested,
                    scenario_inputs=scenario_inputs,
                    ui_locale=ui_locale,
                )
                return analysis_result_to_payload(result, ui_locale)

            ingested = session.ingest_image(
                source_path,
                original_filename=upload.filename,
                content_type=upload.content_type,
            )
            _raise_for_rejected_document(ingested)
            ingested = _ocr_image_upload(ingested)
            _raise_for_empty_document(ingested)
            result = run_local_analysis(
                ingested=ingested,
                scenario_inputs=scenario_inputs,
                ui_locale=ui_locale,
            )
            return analysis_result_to_payload(result, ui_locale)


def _ocr_image_upload(ingested: IngestedDocument) -> IngestedDocument:
    if ingested.stored_path is None:
        raise _unsupported_error()
    if not _local_ocr_is_available():
        raise _ocr_not_installed_error()
    page = _recognize_uploaded_image(ingested.stored_path)
    if page is None:
        raise _ocr_no_text_error()

    document = ingested.document
    if document is None:
        raise _unsupported_error()
    updated_document = replace(
        document,
        pages=(page,),
        page_count=1,
        validation_status=ValidationStatus.ACCEPTED,
    )
    return replace(
        ingested,
        document=updated_document,
        request=replace(ingested.request, documents=(updated_document,)),
    )


def _raise_for_rejected_document(ingested: IngestedDocument) -> None:
    document = ingested.document
    if document is None or document.validation_status is ValidationStatus.ACCEPTED:
        return
    if document.validation_status is ValidationStatus.REJECTED_OVERSIZED:
        raise _oversized_error()
    if document.validation_status is ValidationStatus.REJECTED_CORRUPT:
        raise _corrupt_error()
    if document.validation_status is ValidationStatus.REJECTED_ENCRYPTED:
        raise _encrypted_error()
    raise _unsupported_error()


def _raise_for_missing_ocr(ingested: IngestedDocument) -> None:
    document = ingested.document
    if document is None or not document.pages:
        return
    if _local_ocr_is_available():
        return
    for page in document.pages:
        if page.text_source is TextSource.OCR and not page.spans:
            raise _ocr_not_installed_error()


def _raise_for_empty_document(ingested: IngestedDocument) -> None:
    document = ingested.document
    if document is None or not document.pages:
        raise _empty_file_error()
    has_text = any(
        span.text.strip() or (span.corrected_text or "").strip()
        for page in document.pages
        for span in page.spans
    )
    if not has_text:
        raise _empty_file_error()


def _upload_kind(upload: UploadedAnalyzeFile) -> str:
    suffix = _safe_upload_suffix(upload)
    mime = _base_content_type(upload.content_type)
    if suffix in TEXT_EXTENSIONS and mime in TEXT_MIME_TYPES:
        return "text"
    if suffix in PDF_EXTENSIONS and mime in PDF_MIME_TYPES:
        return "pdf"
    if suffix in IMAGE_EXTENSIONS and mime in IMAGE_MIME_TYPES:
        return "image"
    raise _unsupported_error()


def _decode_text_upload(data: bytes) -> str:
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise _corrupt_error() from exc


def _decode_form_value(payload: bytes, charset: str | None) -> str:
    encoding = charset or "utf-8"
    try:
        return payload.decode(encoding)
    except (LookupError, UnicodeDecodeError):
        return payload.decode("utf-8", errors="replace")


def _safe_upload_suffix(upload: UploadedAnalyzeFile) -> str:
    return Path(upload.filename or "").suffix.lower()


def _base_content_type(content_type: str | None) -> str:
    if not content_type:
        return ""
    return content_type.split(";", 1)[0].strip().lower()


def _recognize_uploaded_image(stored_path: Path) -> Any | None:
    """Recognize one uploaded image into an OCRPage, or None if no backend works.

    The lightweight PaddleOCR PP-OCR backend (the ``ocr`` extra) is preferred
    when installed; its recovered text flows through the shared OCRPage schema
    path so downstream extraction and gates are identical. If that runtime is
    unavailable or cannot read text, FInk falls back to a local Tesseract binary,
    and finally returns None so the caller can show the honest OCR message.
    """

    paddle_text = _paddle_ocr_recognize_text(stored_path)
    if paddle_text is not None and paddle_text.strip():
        return LocalOCREngine().recognize_image(
            stored_path, page_index=0, text_hint=paddle_text
        )
    if shutil.which(LocalOCRConfig().tesseract_cmd) is not None:
        try:
            return LocalOCREngine().recognize_image(stored_path, page_index=0)
        except (OCRBackendUnavailable, OCRError):
            return None
    return None


class _UploadOCREngine(LocalOCREngine):
    """Upload-scoped OCR engine that prefers PP-OCR for image rasters."""

    def recognize_image(
        self,
        image_path: str | Path,
        *,
        page_index: int = 0,
        rotation_deg: int = 0,
        text_hint: str | None = None,
        width_px: int | None = None,
        height_px: int | None = None,
    ) -> OCRPage:
        if text_hint is not None:
            return super().recognize_image(
                image_path,
                page_index=page_index,
                rotation_deg=rotation_deg,
                text_hint=text_hint,
                width_px=width_px,
                height_px=height_px,
            )

        paddle_text = _paddle_ocr_recognize_text(Path(image_path))
        if paddle_text is not None:
            return super().recognize_image(
                image_path,
                page_index=page_index,
                rotation_deg=rotation_deg,
                text_hint=paddle_text,
                width_px=width_px,
                height_px=height_px,
            )

        return super().recognize_image(
            image_path,
            page_index=page_index,
            rotation_deg=rotation_deg,
            width_px=width_px,
            height_px=height_px,
        )


def _paddle_ocr_recognize_text(stored_path: Path) -> str | None:
    """Return PP-OCR text for an image, or None when the runtime is absent.

    Import is deferred and guarded so the ``ocr`` extra stays optional: a minimal
    install without paddle simply skips this backend.
    """

    try:
        from fink.ocr.paddle_vl import (
            PaddleOCRDependencyError,
            PaddleOCRRuntimeError,
            PaddlePPOCRBackend,
        )
    except Exception:
        return None
    try:
        return _cached_paddle_ocr_backend(PaddlePPOCRBackend).recognize_image_text(stored_path)
    except PaddleOCRDependencyError:
        return None
    except PaddleOCRRuntimeError as exc:
        # A real pipeline/inference failure (not a missing dependency). Record it
        # so it is not invisibly swallowed into the generic "couldn't read" path;
        # the caller still falls back gracefully and never crashes the request.
        logging.getLogger(__name__).warning("PP-OCR runtime failure: %s", exc)
        return None


def _cached_paddle_ocr_backend(backend_cls: Any) -> Any:
    global _PADDLE_OCR_BACKEND
    if _PADDLE_OCR_BACKEND is not None:
        return _PADDLE_OCR_BACKEND
    with _PADDLE_OCR_BACKEND_LOCK:
        if _PADDLE_OCR_BACKEND is None:
            _PADDLE_OCR_BACKEND = backend_cls()
    return _PADDLE_OCR_BACKEND


def _local_ocr_is_available() -> bool:
    if shutil.which(LocalOCRConfig().tesseract_cmd) is not None:
        return True
    try:
        from fink.ocr.paddle_vl import paddle_runtime_available
    except Exception:
        return False
    return paddle_runtime_available()


def _request_invalid_error() -> AnalyzeRequestError:
    return AnalyzeRequestError(
        error_code="REQUEST_INVALID",
        status_code=400,
        validation_status="rejected_corrupt",
        message_ko="요청 본문 형식을 읽을 수 없습니다.",
        message_en="The request body could not be parsed.",
        action_ko="JSON 또는 multipart/form-data 형식으로 다시 보내세요.",
        action_en="Send JSON or multipart/form-data and try again.",
    )


def _empty_input_error() -> AnalyzeRequestError:
    return AnalyzeRequestError(
        error_code="INPUT_EMPTY",
        status_code=400,
        validation_status="rejected_empty",
        message_ko="분석할 계약 텍스트 또는 파일이 없습니다.",
        message_en="No contract text or file was supplied.",
        action_ko="계약 텍스트를 붙여넣거나 지원되는 파일 하나를 선택하세요.",
        action_en="Paste contract text or choose one supported file.",
    )


def _empty_file_error() -> AnalyzeRequestError:
    return AnalyzeRequestError(
        error_code="FILE_EMPTY",
        status_code=400,
        validation_status="rejected_empty",
        message_ko="파일에서 분석할 텍스트를 찾지 못했습니다.",
        message_en="No analyzable text was found in the file.",
        action_ko="텍스트가 들어 있는 파일을 선택하거나 계약 텍스트를 붙여넣으세요.",
        action_en="Choose a file containing text, or paste the contract text instead.",
    )


def _ocr_no_text_error() -> AnalyzeRequestError:
    return AnalyzeRequestError(
        error_code="OCR_NO_TEXT",
        status_code=400,
        validation_status="rejected_empty",
        message_ko="사진에서 글자를 읽지 못했어요. 더 선명한 사진을 올리거나 계약 문구를 붙여넣어 주세요.",
        message_en=(
            "I couldn't read text from that image. Try a clearer photo or paste "
            "the contract text."
        ),
        action_ko="사진을 더 선명하게 다시 올리거나 계약 문구를 붙여넣어 주세요.",
        action_en="Upload a clearer image, or paste the contract text instead.",
    )


def _unsupported_error() -> AnalyzeRequestError:
    return AnalyzeRequestError(
        error_code="FILE_UNSUPPORTED",
        status_code=415,
        validation_status=ValidationStatus.REJECTED_UNSUPPORTED.value,
        message_ko="지원하지 않는 파일 형식입니다.",
        message_en="Unsupported file type.",
        action_ko="txt, PDF, PNG, JPG, WEBP, HEIC 파일 중 하나를 선택하세요.",
        action_en="Choose one txt, PDF, PNG, JPG, WEBP, or HEIC file.",
    )


def _oversized_error() -> AnalyzeRequestError:
    return AnalyzeRequestError(
        error_code="FILE_OVERSIZED",
        status_code=413,
        validation_status=ValidationStatus.REJECTED_OVERSIZED.value,
        message_ko="파일이 로컬 분석 한도를 초과했습니다.",
        message_en="The file exceeds the local analysis size limit.",
        action_ko="더 작은 파일을 선택하거나 텍스트를 나누어 붙여넣으세요.",
        action_en="Choose a smaller file or paste a shorter section.",
    )


def _corrupt_error() -> AnalyzeRequestError:
    return AnalyzeRequestError(
        error_code="FILE_CORRUPT",
        status_code=400,
        validation_status=ValidationStatus.REJECTED_CORRUPT.value,
        message_ko="파일이 손상되었거나 읽을 수 없습니다.",
        message_en="The file is corrupt or unreadable.",
        action_ko="파일을 다시 저장한 뒤 시도하거나 텍스트를 붙여넣으세요.",
        action_en="Re-save the file and try again, or paste the text instead.",
    )


def _encrypted_error() -> AnalyzeRequestError:
    return AnalyzeRequestError(
        error_code="PDF_ENCRYPTED",
        status_code=400,
        validation_status=ValidationStatus.REJECTED_ENCRYPTED.value,
        message_ko="암호화된 PDF는 기본 흐름에서 분석하지 않습니다.",
        message_en="Encrypted PDFs are not analyzed in the default flow.",
        action_ko="로컬에서 암호를 해제한 PDF를 사용하거나 텍스트를 붙여넣으세요.",
        action_en="Use a locally unlocked PDF or paste the text instead.",
    )


def _ocr_not_installed_error() -> AnalyzeRequestError:
    return AnalyzeRequestError(
        error_code="OCR_NOT_INSTALLED",
        status_code=422,
        validation_status="rejected_ocr_unavailable",
        message_ko="이미지 OCR이 이 기기에 설치되어 있지 않습니다.",
        message_en="Image OCR is not installed on this device.",
        action_ko=(
            "`uv sync --extra ocr`로 로컬 OCR을 설치한 뒤 다시 시도하세요. "
            "기본 PP-OCR 모델은 처음 사용할 때 자동으로 내려받습니다."
        ),
        action_en=(
            "Run `uv sync --extra ocr` to install local OCR, then try again. "
            "Default PP-OCR models auto-download on first use."
        ),
    )

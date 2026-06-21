from __future__ import annotations

import csv
import shutil
import subprocess
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from typing import Iterable, Sequence

from fink.schemas import Lang, OCRPage, OCRSpan, TextSource


class OCRError(RuntimeError):
    """Raised when a local OCR run fails."""


class OCRBackendUnavailable(OCRError):
    """Raised when no configured offline OCR backend can handle an image."""


@dataclass(frozen=True)
class LocalOCRConfig:
    """Configuration for local OCR only.

    `tesseract_cmd` is resolved on PATH and executed locally. FInk does not
    download language packs or call a remote OCR service at runtime.
    """

    tesseract_cmd: str = "tesseract"
    tesseract_languages: tuple[str, ...] = ("kor", "eng")
    tesseract_psm: int = 6
    timeout_seconds: float = 15.0
    fallback_width_px: int = 1000
    fallback_height_px: int = 1400
    text_line_confidence: float = 1.0


@dataclass(frozen=True)
class OCRMetrics:
    """Computed DR-7 OCR metrics."""

    ev_ocr_cer: float
    ev_ocr_wer: float
    reference_characters: int
    reference_words: int
    hypothesis_characters: int
    hypothesis_words: int

    @property
    def cer(self) -> float:
        return self.ev_ocr_cer

    @property
    def wer(self) -> float:
        return self.ev_ocr_wer


@dataclass(frozen=True)
class _RecognizedSpan:
    text: str
    bbox: dict[str, int]
    confidence: float


class LocalOCREngine:
    """Recognize Korean/English text into OCRPage/OCRSpan records.

    The engine is deliberately local-first:
    - `recognize_image` uses a local Tesseract binary when available.
    - `text_hint`/`recognize_text` supports sanitized synthetic fixtures and
      text-layer fallbacks without network calls.
    """

    def __init__(self, config: LocalOCRConfig | None = None) -> None:
        self.config = config or LocalOCRConfig()

    def recognize_text(
        self,
        text: str,
        *,
        page_index: int = 0,
        rotation_deg: int = 0,
        width_px: int | None = None,
        height_px: int | None = None,
        confidence: float | None = None,
    ) -> OCRPage:
        """Convert known local text into OCR schema records.

        This is used for synthetic/sanitized DR-7 fixtures and local PDF
        text-layer fallback. It still produces OCR-shaped spans with bboxes,
        confidence, and language tags so downstream gates are identical.
        """

        width = width_px or self.config.fallback_width_px
        height = height_px or self.config.fallback_height_px
        conf = self.config.text_line_confidence if confidence is None else confidence
        spans = _spans_from_text_lines(text, width_px=width, height_px=height, confidence=conf)
        return _page_from_spans(
            spans,
            page_index=page_index,
            rotation_deg=rotation_deg,
            width_px=width,
            height_px=height,
        )

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
        """Run offline OCR for one local image/raster.

        If `text_hint` is supplied, it is treated as a local deterministic OCR
        source. Otherwise the method requires a local Tesseract executable.
        """

        path = Path(image_path)
        if not path.is_file():
            raise OCRError("OCR input image does not exist")

        inferred_width, inferred_height = _image_dimensions(path.read_bytes())
        width = width_px or inferred_width or self.config.fallback_width_px
        height = height_px or inferred_height or self.config.fallback_height_px

        if text_hint is not None:
            return self.recognize_text(
                text_hint,
                page_index=page_index,
                rotation_deg=rotation_deg,
                width_px=width,
                height_px=height,
            )

        spans = self._recognize_with_tesseract(path)
        return _page_from_spans(
            spans,
            page_index=page_index,
            rotation_deg=rotation_deg,
            width_px=width,
            height_px=height,
        )

    def recognize_images(self, image_paths: Iterable[str | Path]) -> tuple[OCRPage, ...]:
        """Run OCR for multiple pages, preserving input order as page_index."""

        return tuple(
            self.recognize_image(path, page_index=page_index)
            for page_index, path in enumerate(image_paths)
        )

    def _recognize_with_tesseract(self, image_path: Path) -> tuple[_RecognizedSpan, ...]:
        tesseract = shutil.which(self.config.tesseract_cmd)
        if tesseract is None:
            raise OCRBackendUnavailable("No local OCR backend is available")

        languages = "+".join(self.config.tesseract_languages)
        command = [
            tesseract,
            str(image_path),
            "stdout",
            "-l",
            languages,
            "--psm",
            str(self.config.tesseract_psm),
            "tsv",
        ]
        try:
            completed = subprocess.run(
                command,
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=self.config.timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            raise OCRError("Local OCR backend timed out") from exc

        spans = _parse_tesseract_tsv(completed.stdout)
        if completed.returncode != 0 and not spans:
            raise OCRError("Local OCR backend failed")
        return spans


def evaluate_ocr(reference_text: str, hypothesis: str | OCRPage | Sequence[OCRPage]) -> OCRMetrics:
    """Compute EV-OCR-CER and EV-OCR-WER for a page, pages, or plain text."""

    if isinstance(hypothesis, str):
        hypothesis_text = hypothesis
    elif isinstance(hypothesis, OCRPage):
        hypothesis_text = ocr_page_text(hypothesis)
    else:
        hypothesis_text = ocr_pages_text(hypothesis)

    ref_norm = _normalize_metric_text(reference_text)
    hyp_norm = _normalize_metric_text(hypothesis_text)
    ref_words = ref_norm.split()
    hyp_words = hyp_norm.split()
    return OCRMetrics(
        ev_ocr_cer=character_error_rate(ref_norm, hyp_norm),
        ev_ocr_wer=word_error_rate(ref_norm, hyp_norm),
        reference_characters=len(ref_norm),
        reference_words=len(ref_words),
        hypothesis_characters=len(hyp_norm),
        hypothesis_words=len(hyp_words),
    )


def ocr_page_text(page: OCRPage) -> str:
    """Join OCR spans in reading order for downstream metrics/extraction."""

    return "\n".join(span.corrected_text or span.text for span in page.spans)


def ocr_pages_text(pages: Sequence[OCRPage]) -> str:
    return "\n".join(ocr_page_text(page) for page in pages)


def character_error_rate(reference: str, hypothesis: str) -> float:
    """Levenshtein character error rate."""

    return _error_rate(tuple(reference), tuple(hypothesis))


def word_error_rate(reference: str, hypothesis: str) -> float:
    """Levenshtein word error rate using whitespace tokenization."""

    return _error_rate(tuple(reference.split()), tuple(hypothesis.split()))


def detect_span_language(text: str) -> Lang:
    """Classify a span as Korean, English, mixed, numeric, or mixed fallback."""

    has_hangul = any("\uac00" <= char <= "\ud7a3" for char in text)
    has_alpha = any("a" <= char.lower() <= "z" for char in text)
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


def _page_from_spans(
    spans: Sequence[_RecognizedSpan],
    *,
    page_index: int,
    rotation_deg: int,
    width_px: int,
    height_px: int,
) -> OCRPage:
    schema_spans = tuple(
        OCRSpan(
            span_id=f"page-{page_index}:span-{idx}",
            text=span.text,
            bbox=_clamp_bbox(span.bbox, width_px=width_px, height_px=height_px),
            confidence=span.confidence,
            lang=detect_span_language(span.text),
        )
        for idx, span in enumerate(spans)
        if span.text.strip()
    )
    page_confidence = (
        sum(span.confidence for span in schema_spans) / len(schema_spans)
        if schema_spans
        else 0.0
    )
    return OCRPage(
        page_id=f"page-{page_index}",
        page_index=page_index,
        rotation_deg=rotation_deg,
        width_px=width_px,
        height_px=height_px,
        spans=schema_spans,
        page_ocr_confidence=page_confidence,
        text_source=TextSource.OCR,
        is_user_corrected=False,
    )


def _spans_from_text_lines(
    text: str, *, width_px: int, height_px: int, confidence: float
) -> tuple[_RecognizedSpan, ...]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines and text.strip():
        lines = [text.strip()]
    if not lines:
        return ()

    safe_confidence = _clamp_float(confidence)
    margin_x = min(20, max(width_px // 20, 0))
    usable_width = max(width_px - (margin_x * 2), 1)
    line_height = max(min(height_px // max(len(lines) + 1, 1), 48), 1)
    step_y = max(line_height + 4, 1)
    spans: list[_RecognizedSpan] = []
    for idx, line in enumerate(lines):
        y = min(idx * step_y, max(height_px - line_height, 0))
        spans.append(
            _RecognizedSpan(
                text=line,
                bbox={"x": margin_x, "y": y, "w": usable_width, "h": line_height},
                confidence=safe_confidence,
            )
        )
    return tuple(spans)


def _parse_tesseract_tsv(output: str) -> tuple[_RecognizedSpan, ...]:
    if not output.strip():
        return ()
    reader = csv.DictReader(StringIO(output), delimiter="\t")
    spans: list[_RecognizedSpan] = []
    for row in reader:
        text = (row.get("text") or "").strip()
        if not text:
            continue
        confidence = _parse_confidence(row.get("conf"))
        if confidence is None:
            continue
        bbox = {
            "x": _parse_nonnegative_int(row.get("left")),
            "y": _parse_nonnegative_int(row.get("top")),
            "w": max(_parse_nonnegative_int(row.get("width")), 1),
            "h": max(_parse_nonnegative_int(row.get("height")), 1),
        }
        spans.append(_RecognizedSpan(text=text, bbox=bbox, confidence=confidence))
    return tuple(spans)


def _parse_confidence(raw: str | None) -> float | None:
    if raw is None:
        return None
    try:
        value = float(raw)
    except ValueError:
        return None
    if value < 0:
        return None
    return _clamp_float(value / 100.0)


def _parse_nonnegative_int(raw: str | None) -> int:
    if raw is None:
        return 0
    try:
        return max(int(float(raw)), 0)
    except ValueError:
        return 0


def _clamp_float(value: float) -> float:
    return min(max(float(value), 0.0), 1.0)


def _clamp_bbox(bbox: dict[str, int], *, width_px: int, height_px: int) -> dict[str, int]:
    x = min(max(int(bbox["x"]), 0), max(width_px - 1, 0))
    y = min(max(int(bbox["y"]), 0), max(height_px - 1, 0))
    max_w = max(width_px - x, 1)
    max_h = max(height_px - y, 1)
    return {
        "x": x,
        "y": y,
        "w": min(max(int(bbox["w"]), 1), max_w),
        "h": min(max(int(bbox["h"]), 1), max_h),
    }


def _image_dimensions(data: bytes) -> tuple[int | None, int | None]:
    png = _png_dimensions(data)
    if png is not None:
        return png
    jpeg = _jpeg_dimensions(data)
    if jpeg is not None:
        return jpeg
    ppm = _ppm_dimensions(data)
    if ppm is not None:
        return ppm
    return None, None


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


def _ppm_dimensions(data: bytes) -> tuple[int, int] | None:
    try:
        tokens = [
            token
            for line in data.decode("ascii", errors="ignore").splitlines()
            if not line.startswith("#")
            for token in line.split()
        ]
    except UnicodeDecodeError:
        return None
    if len(tokens) < 3 or tokens[0] not in {"P3", "P6"}:
        return None
    try:
        width = int(tokens[1])
        height = int(tokens[2])
    except ValueError:
        return None
    if width > 0 and height > 0:
        return width, height
    return None


def _normalize_metric_text(text: str) -> str:
    return " ".join(text.split())


def _error_rate(reference: tuple[str, ...], hypothesis: tuple[str, ...]) -> float:
    if not reference:
        return 0.0 if not hypothesis else 1.0
    return _levenshtein_distance(reference, hypothesis) / len(reference)


def _levenshtein_distance(reference: tuple[str, ...], hypothesis: tuple[str, ...]) -> int:
    previous = list(range(len(hypothesis) + 1))
    for row_idx, ref_item in enumerate(reference, start=1):
        current = [row_idx]
        for col_idx, hyp_item in enumerate(hypothesis, start=1):
            substitution_cost = 0 if ref_item == hyp_item else 1
            current.append(
                min(
                    current[col_idx - 1] + 1,
                    previous[col_idx] + 1,
                    previous[col_idx - 1] + substitution_cost,
                )
            )
        previous = current
    return previous[-1]

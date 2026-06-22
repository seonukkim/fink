"""Optional PaddleOCR backends for local image / scanned-PDF OCR.

The default backend is standard PaddleOCR PP-OCR detection + recognition with
the Korean configuration. It is intentionally optional: imports and model
pipeline construction only happen when the ``ocr`` extra is installed and a
backend is requested, so a minimal install keeps working with the deterministic
Tesseract path.

The older PaddleOCR-VL runtime remains available through ``PaddleVLOCRBackend``
for explicit experiments, but it is not the default upload OCR path.

Runtime policy:
- No network access at analyze time. Offline Hugging Face / PaddleX flags are set
  on import only for telemetry/log suppression. PP-OCR model files are small and
  may be auto-downloaded by PaddleOCR on first use; once cached, inference stays
  local.
- The pipeline is built once (lazily) and reused across pages.
- Text is recovered in reading order and handed back as a plain string so it can
  flow into the existing ``recognize_text`` schema path unchanged.
"""

from __future__ import annotations

import inspect
import logging
import os
import re
import warnings
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Any

# Telemetry-off runtime flags only. PaddleOCR resolves model files from its local
# cache after first use. We intentionally do NOT force HF_HUB_OFFLINE or
# PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK here: both alter PaddleX's model/engine
# resolution and, for optional VL experiments, can make it look for the static
# inference format instead of the cached dynamic safetensors model. These mirror
# the telemetry/no-track portion of runtime_profiles.yaml's offline flags.
_OFFLINE_ENV_DEFAULTS = {
    "HF_HUB_DISABLE_TELEMETRY": "1",
    "DO_NOT_TRACK": "1",
    "FLAGS_minloglevel": "2",
    "GLOG_minloglevel": "2",
}
_PADDLE_LOGGER_NAMES = ("paddle", "paddleocr", "paddlex", "ppocr", "transformers")
_NOISY_PADDLE_MESSAGE_RE = re.compile(
    "|".join(
        (
            r"use GQA",
            r"torch\.split",
            r"torch\.max",
            r"\bccache\b",
            r"Creating model",
            r"Loading weights file",
        )
    ),
    re.IGNORECASE,
)
_QUIET_PIPELINE_FLAGS = {
    "verbose": False,
    "show_log": False,
}
_QUIET_RUNTIME_CONFIGURED = False


class _PaddleNoiseFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:
            return True
        return _NOISY_PADDLE_MESSAGE_RE.search(message) is None


_PADDLE_NOISE_FILTER = _PaddleNoiseFilter()


def apply_offline_env() -> None:
    """Set telemetry-off runtime flags without overriding an explicit operator value."""

    for key, value in _OFFLINE_ENV_DEFAULTS.items():
        os.environ.setdefault(key, value)
    configure_quiet_paddle_runtime()


def configure_quiet_paddle_runtime() -> None:
    """Best-effort suppression for noisy optional PaddleOCR runtime logs."""

    global _QUIET_RUNTIME_CONFIGURED
    if not _QUIET_RUNTIME_CONFIGURED:
        for pattern in (
            r".*use GQA.*",
            r".*torch\.split.*",
            r".*torch\.max.*",
            r".*\bccache\b.*",
            r".*Creating model.*",
            r".*Loading weights file.*",
        ):
            try:
                warnings.filterwarnings("ignore", message=pattern, category=UserWarning)
            except Exception:
                continue
        _QUIET_RUNTIME_CONFIGURED = True
    for logger_name in _PADDLE_LOGGER_NAMES:
        try:
            logger = logging.getLogger(logger_name)
            logger.setLevel(logging.WARNING)
            _add_paddle_noise_filter(logger)
            for handler in logger.handlers:
                _add_paddle_noise_filter(handler)
        except Exception:
            continue
    try:
        for handler in logging.getLogger().handlers:
            _add_paddle_noise_filter(handler)
    except Exception:
        pass


def _add_paddle_noise_filter(target: Any) -> None:
    filters = getattr(target, "filters", ())
    if any(isinstance(item, _PaddleNoiseFilter) for item in filters):
        return
    target.addFilter(_PADDLE_NOISE_FILTER)


class PaddleOCRDependencyError(RuntimeError):
    """Raised when the optional PaddleOCR runtime cannot be imported."""

    def __init__(self, install_hint: str, import_error: Exception) -> None:
        self.install_hint = install_hint
        self.import_error = import_error
        super().__init__(f"{install_hint} (import error: {import_error!r})")


class PaddleOCRRuntimeError(RuntimeError):
    """Raised when an installed PaddleOCR pipeline fails to build or run."""


@dataclass(frozen=True)
class PaddlePPOCRConfig:
    """Configuration for the default lightweight PP-OCR backend."""

    lang: str = "korean"
    use_gpu: bool = False
    use_angle_cls: bool = False
    use_doc_orientation_classify: bool = False
    use_doc_unwarping: bool = False
    use_textline_orientation: bool = False


@dataclass(frozen=True)
class PaddleVLConfig:
    """Configuration for the optional PaddleOCR-VL backend.

    ``vl_rec_model_dir`` may point at a PaddleX-format local model directory. The
    Hugging Face snapshot under ``$FINK_HOME/models/paddleocr_vl`` is NOT in that
    format, so by default this is left unset and the runtime resolves its own
    cached PaddleX model files offline.

    ``pipeline_version`` is left unset by default. Pinning it to "v1" selects a
    static-graph recognizer engine that looks for inference.pdmodel/.pdiparams
    files; the cached PaddleOCR-VL recognizer ships as a dynamic safetensors
    model, so the default (unpinned) path is the one that loads cleanly.
    """

    pipeline_version: str | None = None
    vl_rec_model_dir: str | None = None
    layout_detection_model_dir: str | None = None
    use_doc_orientation_classify: bool = False
    use_doc_unwarping: bool = False


# The pip commands that provide these backends, surfaced in the honest fallback
# so the operator can finish installing OCR if the runtime is unavailable.
PP_OCR_INSTALL_HINT = (
    "PaddleOCR runtime is not installed. Install the optional OCR extra with "
    "`uv sync --extra ocr` (or `uv pip install \"paddleocr>=3.4.0\" paddlepaddle`)."
)
PADDLE_VL_INSTALL_HINT = (
    "PaddleOCR-VL runtime is not installed. Install PaddleOCR with the optional "
    "doc-parser extra using `uv pip install \"paddleocr[doc-parser]>=3.4.0\" "
    "paddlepaddle`."
)
INSTALL_HINT = PP_OCR_INSTALL_HINT


def paddle_runtime_available() -> bool:
    """Return True when the default PP-OCR classes can be imported."""

    try:
        _import_paddle_ocr()
    except PaddleOCRDependencyError:
        return False
    return True


def paddle_vl_runtime_available() -> bool:
    """Return True when the optional PaddleOCR-VL classes can be imported."""

    try:
        _import_paddleocr_vl()
    except PaddleOCRDependencyError:
        return False
    return True


def _import_paddle_ocr() -> Any:
    apply_offline_env()
    try:
        from paddleocr import PaddleOCR  # type: ignore import-not-found
    except Exception as exc:  # ImportError or a paddle backend load failure
        raise PaddleOCRDependencyError(PP_OCR_INSTALL_HINT, exc) from exc
    configure_quiet_paddle_runtime()
    return PaddleOCR


def _import_paddleocr_vl() -> Any:
    apply_offline_env()
    try:
        from paddleocr import PaddleOCRVL  # type: ignore import-not-found
    except Exception as exc:  # ImportError or a paddle backend load failure
        raise PaddleOCRDependencyError(PADDLE_VL_INSTALL_HINT, exc) from exc
    configure_quiet_paddle_runtime()
    return PaddleOCRVL


class PaddlePPOCRBackend:
    """Lazily-built standard PaddleOCR PP-OCR pipeline for uploaded images.

    The pipeline build is deferred to the first ``recognize_image_text`` call so
    importing this module stays cheap and an unused backend never loads a model.
    """

    def __init__(self, config: PaddlePPOCRConfig | None = None) -> None:
        self.config = config or PaddlePPOCRConfig()
        self._pipeline: Any | None = None
        self._pipeline_lock = Lock()

    def _build_pipeline(self) -> Any:
        if self._pipeline is not None:
            return self._pipeline
        with self._pipeline_lock:
            if self._pipeline is not None:
                return self._pipeline
            paddle_ocr = _import_paddle_ocr()
            kwargs: dict[str, Any] = {
                "lang": self.config.lang,
                "use_gpu": self.config.use_gpu,
                "use_angle_cls": self.config.use_angle_cls,
                "use_doc_orientation_classify": self.config.use_doc_orientation_classify,
                "use_doc_unwarping": self.config.use_doc_unwarping,
                "use_textline_orientation": self.config.use_textline_orientation,
            }
            try:
                self._pipeline = _create_ppocr_pipeline(paddle_ocr, kwargs)
            except Exception as exc:
                raise PaddleOCRRuntimeError(
                    f"PaddleOCR PP-OCR pipeline failed to initialize: {exc!r}"
                ) from exc
            return self._pipeline

    def recognize_image_text(self, image_path: str | Path) -> str:
        """Run PP-OCR on one local image and return recovered text.

        The text is joined in reading order across recognized lines. An empty
        string means the model ran but found no text.
        """

        path = Path(image_path)
        if not path.is_file():
            raise PaddleOCRRuntimeError("OCR input image does not exist")
        configure_quiet_paddle_runtime()
        pipeline = self._build_pipeline()
        try:
            outputs = _run_ppocr_pipeline(pipeline, path)
        except PaddleOCRRuntimeError:
            raise
        except Exception as exc:
            raise PaddleOCRRuntimeError(f"PaddleOCR PP-OCR inference failed: {exc!r}") from exc
        return _text_from_outputs(outputs)


class PaddleVLOCRBackend:
    """Lazily-built PaddleOCR-VL pipeline that returns recognized text.

    The pipeline build is deferred to the first ``recognize_image_text`` call so
    importing this module stays cheap and an unused backend never loads a model.
    """

    def __init__(self, config: PaddleVLConfig | None = None) -> None:
        self.config = config or PaddleVLConfig()
        self._pipeline: Any | None = None
        self._pipeline_lock = Lock()

    def _build_pipeline(self) -> Any:
        if self._pipeline is not None:
            return self._pipeline
        with self._pipeline_lock:
            if self._pipeline is not None:
                return self._pipeline
            paddle_ocr_vl = _import_paddleocr_vl()
            kwargs: dict[str, Any] = {
                "use_doc_orientation_classify": self.config.use_doc_orientation_classify,
                "use_doc_unwarping": self.config.use_doc_unwarping,
            }
            if self.config.pipeline_version:
                kwargs["pipeline_version"] = self.config.pipeline_version
            if self.config.vl_rec_model_dir:
                kwargs["vl_rec_model_dir"] = self.config.vl_rec_model_dir
            if self.config.layout_detection_model_dir:
                kwargs["layout_detection_model_dir"] = self.config.layout_detection_model_dir
            try:
                self._pipeline = _create_quiet_pipeline(paddle_ocr_vl, kwargs)
            except Exception as exc:
                raise PaddleOCRRuntimeError(
                    f"PaddleOCR-VL pipeline failed to initialize: {exc!r}"
                ) from exc
            return self._pipeline

    def recognize_image_text(self, image_path: str | Path) -> str:
        """Run PaddleOCR-VL on one local image and return recovered text.

        The text is joined in reading order across recognized blocks. An empty
        string means the model ran but found no text.
        """

        path = Path(image_path)
        if not path.is_file():
            raise PaddleOCRRuntimeError("OCR input image does not exist")
        configure_quiet_paddle_runtime()
        pipeline = self._build_pipeline()
        try:
            outputs = pipeline.predict(str(path))
        except Exception as exc:
            raise PaddleOCRRuntimeError(f"PaddleOCR-VL inference failed: {exc!r}") from exc
        return _text_from_outputs(outputs)


def _create_quiet_pipeline(paddle_ocr_vl: Any, kwargs: dict[str, Any]) -> Any:
    quiet_kwargs = _with_supported_quiet_flags(paddle_ocr_vl, kwargs)
    try:
        return paddle_ocr_vl(**quiet_kwargs)
    except Exception as exc:
        if quiet_kwargs != kwargs and _looks_like_quiet_flag_mismatch(exc):
            return paddle_ocr_vl(**kwargs)
        raise


def _create_ppocr_pipeline(paddle_ocr: Any, kwargs: dict[str, Any]) -> Any:
    supported_kwargs = _with_supported_kwargs(paddle_ocr, kwargs)
    try:
        return _create_quiet_pipeline(paddle_ocr, supported_kwargs)
    except Exception as exc:
        minimal_kwargs = _with_supported_kwargs(paddle_ocr, {"lang": kwargs["lang"]})
        if minimal_kwargs != supported_kwargs and _looks_like_pipeline_arg_mismatch(exc):
            return _create_quiet_pipeline(paddle_ocr, minimal_kwargs)
        raise


def _with_supported_kwargs(callable_obj: Any, kwargs: dict[str, Any]) -> dict[str, Any]:
    try:
        parameters = inspect.signature(callable_obj).parameters
    except (TypeError, ValueError):
        return kwargs
    if any(parameter.kind is inspect.Parameter.VAR_KEYWORD for parameter in parameters.values()):
        return kwargs
    return {key: value for key, value in kwargs.items() if key in parameters}


def _with_supported_quiet_flags(paddle_ocr_vl: Any, kwargs: dict[str, Any]) -> dict[str, Any]:
    quiet_kwargs = dict(kwargs)
    try:
        parameters = inspect.signature(paddle_ocr_vl).parameters
    except (TypeError, ValueError):
        return quiet_kwargs
    for key, value in _QUIET_PIPELINE_FLAGS.items():
        if key in parameters:
            quiet_kwargs.setdefault(key, value)
    return quiet_kwargs


def _looks_like_quiet_flag_mismatch(exc: Exception) -> bool:
    message = str(exc).lower()
    if not any(key in message for key in _QUIET_PIPELINE_FLAGS):
        return False
    return any(term in message for term in ("unexpected", "unknown", "unsupported"))


def _looks_like_pipeline_arg_mismatch(exc: Exception) -> bool:
    message = str(exc).lower()
    return any(
        term in message
        for term in (
            "unexpected keyword",
            "unknown argument",
            "unknown parameter",
            "unsupported",
            "not supported",
            "got an unexpected",
        )
    )


def _run_ppocr_pipeline(pipeline: Any, image_path: Path) -> Any:
    ocr = getattr(pipeline, "ocr", None)
    if callable(ocr):
        if _call_supports_keyword(ocr, "cls"):
            try:
                return ocr(str(image_path), cls=False)
            except TypeError as exc:
                if not _looks_like_pipeline_arg_mismatch(exc):
                    raise
        return ocr(str(image_path))

    predict = getattr(pipeline, "predict", None)
    if callable(predict):
        if _call_supports_keyword(predict, "input"):
            try:
                return predict(input=str(image_path))
            except TypeError as exc:
                if not _looks_like_pipeline_arg_mismatch(exc):
                    raise
        return predict(str(image_path))

    raise PaddleOCRRuntimeError("PaddleOCR pipeline has no ocr or predict method")


def _call_supports_keyword(callable_obj: Any, keyword: str) -> bool:
    try:
        parameters = inspect.signature(callable_obj).parameters
    except (TypeError, ValueError):
        return True
    return keyword in parameters or any(
        parameter.kind is inspect.Parameter.VAR_KEYWORD for parameter in parameters.values()
    )


@dataclass(frozen=True)
class _OCRLine:
    text: str
    y: float
    x: float
    order: int


def _text_from_outputs(outputs: Any) -> str:
    """Extract reading-order text from a PaddleOCR result.

    Standard PP-OCR commonly returns ``[box, (text, score)]`` line entries.
    Newer PaddleOCR result objects expose structured data via ``.json`` with
    ``rec_texts``/``rec_polys`` keys, while PaddleOCR-VL may expose rendered
    markdown. We try these shapes defensively so a minor PaddleOCR version
    difference does not break OCR.
    """

    ppocr_text = _text_from_ppocr_outputs(outputs)
    if ppocr_text:
        return ppocr_text

    blocks: list[str] = []
    for result in _iter_results(outputs):
        text = _text_from_single_result(result)
        if text:
            blocks.append(text)
    return "\n".join(block for block in blocks if block.strip())


def _iter_results(outputs: Any) -> tuple[Any, ...]:
    if outputs is None:
        return ()
    if isinstance(outputs, dict):
        return (outputs,)
    if isinstance(outputs, (str, bytes)):
        return (outputs,)
    if isinstance(outputs, Sequence):
        return tuple(outputs)
    return (outputs,)


def _text_from_ppocr_outputs(outputs: Any) -> str:
    lines: list[_OCRLine] = []
    order = [0]
    _collect_ppocr_lines(outputs, lines, order)
    if not lines:
        return ""
    ordered = sorted(lines, key=lambda line: (line.y, line.x, line.order))
    return "\n".join(line.text for line in ordered if line.text.strip())


def _collect_ppocr_lines(value: Any, lines: list[_OCRLine], order: list[int]) -> None:
    line = _line_from_ppocr_entry(value, order[0])
    if line is not None:
        lines.append(line)
        order[0] += 1
        return

    data = _result_json(value)
    if isinstance(data, dict):
        before = len(lines)
        _collect_ppocr_lines_from_dict(data, lines, order)
        if len(lines) > before:
            return
    elif data is not None and data is not value:
        _collect_ppocr_lines(data, lines, order)
        return

    if isinstance(value, dict):
        _collect_ppocr_lines_from_dict(value, lines, order)
        return
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for item in value:
            _collect_ppocr_lines(item, lines, order)


def _collect_ppocr_lines_from_dict(
    data: dict[str, Any], lines: list[_OCRLine], order: list[int]
) -> None:
    texts = _as_text_sequence(data.get("rec_texts") or data.get("rec_text") or data.get("texts"))
    if not texts:
        return
    boxes = _as_sequence(
        data.get("rec_polys")
        or data.get("dt_polys")
        or data.get("rec_boxes")
        or data.get("boxes")
    )
    for index, text in enumerate(texts):
        if not text.strip():
            continue
        box = boxes[index] if index < len(boxes) else None
        x, y = _box_origin(box, order[0])
        lines.append(_OCRLine(text=text, y=y, x=x, order=order[0]))
        order[0] += 1


def _line_from_ppocr_entry(value: Any, order: int) -> _OCRLine | None:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or len(value) < 2:
        return None
    text = _text_from_score_pair(value[1])
    if not text.strip():
        return None
    x, y = _box_origin(value[0], order)
    return _OCRLine(text=text, y=y, x=x, order=order)


def _text_from_score_pair(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)) and value:
        first = value[0]
        return first if isinstance(first, str) else ""
    return ""


def _as_text_sequence(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return tuple(str(item) for item in value if str(item).strip())
    return ()


def _as_sequence(value: Any) -> tuple[Any, ...]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return tuple(value)
    return ()


def _box_origin(box: Any, order: int) -> tuple[float, float]:
    points = _box_points(box)
    if not points:
        fallback = float(order)
        return fallback, fallback
    return min(point[0] for point in points), min(point[1] for point in points)


def _box_points(box: Any) -> tuple[tuple[float, float], ...]:
    if not isinstance(box, Sequence) or isinstance(box, (str, bytes)):
        return ()
    if _is_numeric_sequence(box) and len(box) >= 2:
        return ((_as_float(box[0]), _as_float(box[1])),)

    points: list[tuple[float, float]] = []
    for point in box:
        if (
            isinstance(point, Sequence)
            and not isinstance(point, (str, bytes))
            and len(point) >= 2
            and _is_number_like(point[0])
            and _is_number_like(point[1])
        ):
            points.append((_as_float(point[0]), _as_float(point[1])))
    return tuple(points)


def _is_numeric_sequence(value: Sequence[Any]) -> bool:
    return all(_is_number_like(item) for item in value)


def _is_number_like(value: Any) -> bool:
    try:
        float(value)
    except (TypeError, ValueError):
        return False
    return True


def _as_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _text_from_single_result(result: Any) -> str:
    markdown_text = _markdown_text(result)
    if markdown_text:
        return markdown_text
    data = _result_json(result)
    if isinstance(data, dict):
        recovered = _text_from_result_dict(data)
        if recovered:
            return recovered
    return ""


def _markdown_text(result: Any) -> str:
    markdown = getattr(result, "markdown", None)
    if isinstance(markdown, dict):
        value = markdown.get("markdown_texts")
        if isinstance(value, str) and value.strip():
            return value
    if isinstance(markdown, str) and markdown.strip():
        return markdown
    return ""


def _result_json(result: Any) -> Any:
    data = getattr(result, "json", None)
    if isinstance(data, dict) and "res" in data and isinstance(data["res"], dict):
        return data["res"]
    return data


def _text_from_result_dict(data: dict[str, Any]) -> str:
    # Plain OCR-style result: a list of recognized line strings.
    for key in ("rec_texts", "rec_text", "texts"):
        value = data.get(key)
        if isinstance(value, (list, tuple)):
            joined = "\n".join(str(item) for item in value if str(item).strip())
            if joined.strip():
                return joined
        elif isinstance(value, str) and value.strip():
            return value
    # Layout-parsing result: ordered blocks each carrying their own text.
    blocks = data.get("parsing_res_list")
    if isinstance(blocks, (list, tuple)):
        ordered = []
        for block in blocks:
            if isinstance(block, dict):
                content = block.get("block_content") or block.get("content")
                if isinstance(content, str) and content.strip():
                    ordered.append(content)
        if ordered:
            return "\n".join(ordered)
    return ""

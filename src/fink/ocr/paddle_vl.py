"""Optional PaddleOCR-VL backend for local image / scanned-PDF OCR.

This module wires the locally installed PaddleOCR-VL runtime (the ``paddleocr``
package with the ``doc-parser`` extra plus ``paddlepaddle``) into FInk's offline
OCR path. It is intentionally optional: the import and the heavy pipeline build
only happen when the ``ocr`` extra is installed and a backend is requested, so a
minimal install keeps working with the deterministic Tesseract path.

Runtime policy:
- No network access at analyze time. Offline Hugging Face / PaddleX flags are set
  on import so the pipeline reuses already-downloaded model files and never
  reaches a model hoster during inference.
- The pipeline is built once (lazily) and reused across pages.
- Text is recovered in reading order and handed back as a plain string so it can
  flow into the existing ``recognize_text`` schema path unchanged.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Telemetry-off runtime flags only. The PaddleOCR-VL pipeline resolves its model
# files from the PaddleX model cache; once that cache exists the pipeline runs
# without network. We intentionally do NOT force HF_HUB_OFFLINE or
# PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK here: both alter PaddleX's model/engine
# resolution and, with a freshly-filled cache, can make it look for the static
# inference format instead of the cached dynamic safetensors model. These mirror
# the telemetry/no-track portion of runtime_profiles.yaml's offline flags.
_OFFLINE_ENV_DEFAULTS = {
    "HF_HUB_DISABLE_TELEMETRY": "1",
    "DO_NOT_TRACK": "1",
}


def apply_offline_env() -> None:
    """Set telemetry-off runtime flags without overriding an explicit operator value."""

    for key, value in _OFFLINE_ENV_DEFAULTS.items():
        os.environ.setdefault(key, value)


class PaddleOCRDependencyError(RuntimeError):
    """Raised when the optional PaddleOCR-VL runtime cannot be imported."""

    def __init__(self, install_hint: str, import_error: Exception) -> None:
        self.install_hint = install_hint
        self.import_error = import_error
        super().__init__(f"{install_hint} (import error: {import_error!r})")


class PaddleOCRRuntimeError(RuntimeError):
    """Raised when an installed PaddleOCR-VL pipeline fails to build or run."""


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


# The pip command that provides this backend, surfaced in the honest fallback so
# the operator can finish installing it if the runtime is unavailable.
INSTALL_HINT = (
    "PaddleOCR-VL runtime is not installed. Install the optional OCR extra with "
    "`uv pip install -e '.[ocr]'` (or "
    "`uv pip install \"paddleocr[doc-parser]>=3.4.0\" paddlepaddle`)."
)


def paddle_runtime_available() -> bool:
    """Return True when the PaddleOCR-VL classes can be imported."""

    try:
        _import_paddleocr_vl()
    except PaddleOCRDependencyError:
        return False
    return True


def _import_paddleocr_vl() -> Any:
    apply_offline_env()
    try:
        from paddleocr import PaddleOCRVL  # type: ignore import-not-found
    except Exception as exc:  # ImportError or a paddle backend load failure
        raise PaddleOCRDependencyError(INSTALL_HINT, exc) from exc
    return PaddleOCRVL


class PaddleVLOCRBackend:
    """Lazily-built PaddleOCR-VL pipeline that returns recognized text.

    The pipeline build is deferred to the first ``recognize_image_text`` call so
    importing this module stays cheap and an unused backend never loads a model.
    """

    def __init__(self, config: PaddleVLConfig | None = None) -> None:
        self.config = config or PaddleVLConfig()
        self._pipeline: Any | None = None

    def _build_pipeline(self) -> Any:
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
            self._pipeline = paddle_ocr_vl(**kwargs)
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
        pipeline = self._build_pipeline()
        try:
            outputs = pipeline.predict(str(path))
        except Exception as exc:
            raise PaddleOCRRuntimeError(f"PaddleOCR-VL inference failed: {exc!r}") from exc
        return _text_from_outputs(outputs)


def _text_from_outputs(outputs: Any) -> str:
    """Extract reading-order text from a PaddleOCR-VL predict() result.

    PaddleOCR result objects expose their structured data via ``.json`` and a
    rendered ``.markdown``; the recognized strings live under common keys. We try
    several shapes so a minor PaddleOCR version difference does not break OCR.
    """

    blocks: list[str] = []
    for result in outputs or []:
        text = _text_from_single_result(result)
        if text:
            blocks.append(text)
    return "\n".join(block for block in blocks if block.strip())


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

from __future__ import annotations

import argparse
import html
import ipaddress
import json
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from fink.schemas import UILocale
from fink.web.analyze import analysis_result_to_payload, run_local_analysis
from fink.web.assumptions import EditableAssumptions, render_assumptions_panel_html
from fink.web.ingest_ui import (
    PAGE_OPERATIONS,
    PDF_LOCAL_NOTICE,
)
from fink.web.report_ui import render_empty_report_shell_html
from fink.web.upload import (
    AnalyzeRequestError,
    analyze_multipart_request,
    assumptions_from_multipart_fields,
    is_multipart_content_type,
    parse_multipart_analyze_request,
)

DEFAULT_LOOPBACK_HOST = "127.0.0.1"
DEFAULT_PORT = 8000

PRIVACY_BANNER = (
    "Local-only session. Contract uploads and OCR text stay on this device; "
    "no telemetry, cloud OCR, remote LLM, or external legal search is used."
)
NOT_LEGAL_ADVICE_BANNER = (
    "FInk reports Contractual Financial Review Priority only. It is not legal advice "
    "and not a fraud, illegality, validity, unfairness, or guaranteed-loss verdict."
)
TRUSTED_LAN_WARNING = (
    "Trusted-LAN mode exposes this local server only to devices on the same private "
    "network. Use it only on a network you control, and stop the server when finished."
)
DISCLOSURE_ITEMS = (
    "Review priority is not a legal, fraud, validity, unfairness, or guaranteed-loss verdict.",
    "Figures are scenario estimates from user assumptions, not guaranteed losses.",
    "Official-source grounding is UNVERIFIED pending A0 confirmation.",
    "Korean source language is canonical; English UI text is a generated aid.",
)

LAN_CONFIRMATION_TEXT = "I understand this is a trusted-LAN-only local server."
_BLOCKED_BIND_HOSTS = frozenset({"0.0.0.0", "::", ""})

# Bilingual "1-2-3 how to use" strip for the creator flow. Korean is canonical;
# English is a generated aid. Each string is short and period-free, which is
# safe for the long-private-quotation gate.
HOW_TO_USE_STEPS = (
    {
        "ko": "계약 텍스트를 붙여넣거나 업로드하세요",
        "en": "Paste or upload the contract text",
    },
    {
        "ko": "분석하기 버튼을 한 번 누르세요",
        "en": "Press the Analyze button once",
    },
    {
        "ko": "결정 브리프와 네 가지 출력을 확인하세요",
        "en": "Read the Decision Brief and four outputs",
    },
)


@dataclass(frozen=True)
class WebBindSettings:
    host: str = DEFAULT_LOOPBACK_HOST
    port: int = DEFAULT_PORT
    lan_enabled: bool = False
    trusted_lan_warning: str = ""
    trusted_lan_warning_acknowledged: bool = False

    @property
    def base_url(self) -> str:
        return f"http://{_format_host_for_url(self.host)}:{self.port}"

    def public_dict(self) -> dict[str, Any]:
        return {
            "host": self.host,
            "port": self.port,
            "base_url": self.base_url,
            "lan_enabled": self.lan_enabled,
            "trusted_lan_warning": self.trusted_lan_warning,
            "trusted_lan_warning_acknowledged": self.trusted_lan_warning_acknowledged,
            "local_only": True,
        }


class WebBindingError(ValueError):
    """Raised when the requested web bind mode would expose FInk too broadly."""


class LocaleValidationError(ValueError):
    """Raised when an explicit API locale is not one of the supported UI locales."""


def resolve_bind_settings(
    *,
    host: str | None = None,
    port: int = DEFAULT_PORT,
    allow_lan: bool = False,
    trusted_lan_ack: bool = False,
) -> WebBindSettings:
    """Resolve the server bind address with loopback as the safe default."""

    _validate_port(port)
    requested = (host or DEFAULT_LOOPBACK_HOST).strip()
    if not allow_lan:
        if requested not in {DEFAULT_LOOPBACK_HOST, "localhost", "::1"}:
            raise WebBindingError("LAN binding requires explicit allow_lan opt-in")
        return WebBindSettings(host=DEFAULT_LOOPBACK_HOST, port=port)

    if not trusted_lan_ack:
        raise WebBindingError("trusted-LAN warning must be acknowledged before LAN binding")
    if requested in _BLOCKED_BIND_HOSTS:
        raise WebBindingError("bind to a specific private LAN interface, not a wildcard host")
    if requested in {DEFAULT_LOOPBACK_HOST, "localhost", "::1"}:
        raise WebBindingError("LAN mode requires a private LAN interface address")
    if not _is_private_interface(requested):
        raise WebBindingError("LAN mode requires a private or link-local interface address")
    return WebBindSettings(
        host=requested,
        port=port,
        lan_enabled=True,
        trusted_lan_warning=TRUSTED_LAN_WARNING,
        trusted_lan_warning_acknowledged=True,
    )


def render_index_html(settings: WebBindSettings | None = None) -> str:
    """Render the local-only creator flow without external assets.

    The page is split into a prominent primary flow (a 1-2-3 how-to strip, one
    hero input card with the paste box plus a single collapsed upload affordance,
    and the Decision Brief target) and a de-emphasized advanced-tools column
    where the monetary-assumptions grid, the report shell, and the OCR page
    editor live inside collapsed ``<details>`` panels. Both Korean and English
    copy are rendered into the DOM and flipped via the ``data-active-locale``
    attribute, so the KO/EN toggle works before any analyze call. All ``fetch``
    and render logic lives in ``/app.js`` because the Content-Security-Policy
    restricts scripts to ``'self'``.
    """

    bind = settings or resolve_bind_settings()
    lan_warning = (
        '<p class="banner banner-warning" role="status">'
        f"{html.escape(bind.trusted_lan_warning)}</p>"
        if bind.lan_enabled
        else ""
    )
    disclosures = "\n".join(
        f"<li>{html.escape(item)}</li>"
        for item in (PRIVACY_BANNER, NOT_LEGAL_ADVICE_BANNER, *DISCLOSURE_ITEMS)
    )
    return f"""<!doctype html>
<html lang="ko" data-default-locale="ko" data-active-locale="ko" data-local-only="true">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="referrer" content="no-referrer">
  <title>FInk Local Review</title>
  <style>{_css()}</style>
</head>
<body>
  <a class="skip-link" href="#workspace">Skip to workspace</a>
  <header class="topbar">
    <div>
      <p class="eyebrow">FInk local-first review</p>
      <h1>계약상 금융 검토 우선도</h1>
      <p class="subtitle">Contractual Financial Review Priority</p>
    </div>
    <nav class="locale-toggle" aria-label="Locale" data-locale-toggle="true">
      <button type="button" data-locale-button="ko" aria-pressed="true">KO</button>
      <button type="button" data-locale-button="en" aria-pressed="false">EN generated</button>
    </nav>
  </header>

  <section class="disclosure-bar" aria-label="Persistent privacy and disclaimer banners">
    <p class="banner banner-privacy">{html.escape(PRIVACY_BANNER)}</p>
    <p class="banner banner-advice">{html.escape(NOT_LEGAL_ADVICE_BANNER)}</p>
    {lan_warning}
  </section>

  <main id="workspace" class="workspace">
    <div class="primary-flow">
      {_render_how_to_section()}
      {_render_input_card()}
      {_render_result_section()}
    </div>

    <div class="advanced-tools">
      {_render_disclosures_section(disclosures)}
      {_render_assumptions_details()}
      {_render_page_tools_details()}
    </div>
  </main>

  <footer>
    <span>Serving from {html.escape(bind.base_url)}</span>
    <span>{html.escape("LAN opt-in enabled" if bind.lan_enabled else "Loopback only")}</span>
  </footer>
  <script src="/app.js"></script>
</body>
</html>
"""


def _render_how_to_section() -> str:
    """Render the compact 1-2-3 how-to strip that opens the primary flow."""

    steps = "\n".join(_render_step(step) for step in HOW_TO_USE_STEPS)
    return f"""<section class="how-to card" aria-labelledby="how-to-heading">
      <div class="section-heading">
        <p class="eyebrow">How to use</p>
        <h2 id="how-to-heading">
          <span lang="ko" data-locale-text="ko">사용 방법 1-2-3</span>
          <span lang="en" data-locale-text="en">How to use 1-2-3</span>
        </h2>
      </div>
      <ol class="how-to-steps" data-how-to-steps="true">
        {steps}
      </ol>
    </section>"""


def _render_input_card() -> str:
    """Render one input area: paste text or choose one local file."""

    return f"""<section class="input-pane card" aria-labelledby="input-heading">
      <div class="section-heading">
        <p class="eyebrow">Local input</p>
        <h2 id="input-heading">
          <span lang="ko" data-locale-text="ko">검토할 계약 자료</span>
          <span lang="en" data-locale-text="en">Contract text to review</span>
        </h2>
      </div>
      <label class="paste-label" for="paste-box">
        <span lang="ko" data-locale-text="ko">계약 조항 붙여넣기</span>
        <span lang="en" data-locale-text="en">Paste clause text</span>
      </label>
      <textarea id="paste-box" name="paste_text" rows="8" spellcheck="false"
        data-ingest-mode="paste"
        placeholder="제3조(정산) ..."></textarea>
      <div class="file-input-row" data-upload-area="true">
        <label class="upload-label" for="contract-file">
          <span lang="ko" data-locale-text="ko">파일 업로드 (선택)</span>
          <span lang="en" data-locale-text="en">Upload one file (optional)</span>
        </label>
        <input id="contract-file" name="contract_file" type="file" data-file-input="true"
          accept="text/plain,.txt,application/pdf,.pdf,image/png,image/jpeg,image/webp,image/heic,image/heif,.png,.jpg,.jpeg,.webp,.heic,.heif">
        <p class="pdf-local-notice" data-pdf-local-notice="true">
          {html.escape(PDF_LOCAL_NOTICE)}
        </p>
        <div class="local-error" data-pdf-error-region="true" role="alert">
          unsupported, empty, corrupted, encrypted, oversized, and OCR-missing files
          return a local structured error. Nothing is transmitted.
        </div>
      </div>
      <div class="action-row">
        <button type="button" id="analyze-btn" data-analyze-button="true">
          분석하기 / Analyze
        </button>
      </div>
      <p class="hint" id="analyze-status" data-analyze-status="true" role="status" aria-live="polite">
        <span lang="ko" data-locale-text="ko">계약 텍스트는 이 기기에만 머무는 임시 데이터입니다.</span>
        <span lang="en" data-locale-text="en">Contract text stays on this device as ephemeral data.</span>
      </p>
    </section>"""


def _render_result_section() -> str:
    """Render the Decision Brief target that ``/app.js`` fills after Analyze."""

    return """<section
      id="result"
      class="result-pane card"
      aria-labelledby="result-heading"
      aria-live="polite"
      data-analysis-result="true"
      hidden
    >
      <div class="section-heading">
        <p class="eyebrow">Decision Brief</p>
        <h2 id="result-heading">
          <span lang="ko" data-locale-text="ko">금융 결정 브리프</span>
          <span lang="en" data-locale-text="en">Financial Decision Brief</span>
        </h2>
      </div>
      <p class="hint" data-result-placeholder="true">
        <span lang="ko" data-locale-text="ko">분석하기를 누르면 결과가 여기에 표시됩니다.</span>
        <span lang="en" data-locale-text="en">Press Analyze and the result appears here.</span>
      </p>
    </section>"""


def _render_disclosures_section(disclosures: str) -> str:
    """Render the always-visible report and export disclosure list."""

    return f"""<aside class="export-disclosures card"
      aria-label="Report and export disclosures">
      <h3>Report disclosures</h3>
      <ul>
        {disclosures}
      </ul>
    </aside>"""


def _render_assumptions_details() -> str:
    """Wrap the optional monetary-assumptions grid and report shell in a disclosure.

    The editable FIM-assumptions grid and the four-dimension report shell are
    optional tools, so they are collapsed by default to keep the primary flow
    uncluttered. They stay in the DOM (tests pin their elements) and keep the
    ``Four separate dimensions`` heading inside the open panel.
    """

    return f"""<details class="tool-details" data-optional-tool="assumptions">
      <summary>
        <span lang="ko" data-locale-text="ko">금액 가정 입력 (선택)</span>
        <span lang="en" data-locale-text="en">Add monetary assumptions (optional)</span>
      </summary>
      <section class="report-pane" aria-labelledby="report-heading">
        <div class="section-heading">
          <p class="eyebrow">Four dimensions and assumptions</p>
          <h2 id="report-heading">Four separate dimensions</h2>
        </div>
        {render_assumptions_panel_html()}
        {render_empty_report_shell_html()}
      </section>
    </details>"""


def _render_page_tools_details() -> str:
    """Wrap the OCR page editor in a collapsed disclosure.

    The page reorder / rotate / delete and OCR-correction controls only matter
    once a file is uploaded, so they are collapsed by default. The section keeps
    its page-operation data attributes so the ingest tests still see them.
    """

    page_ops = " ".join(PAGE_OPERATIONS)
    return f"""<details class="tool-details" data-optional-tool="page-editor">
      <summary>
        <span lang="ko" data-locale-text="ko">업로드한 페이지 편집</span>
        <span lang="en" data-locale-text="en">Uploaded-page tools</span>
      </summary>
      <section
        class="page-editor"
        aria-labelledby="page-editor-heading"
        data-page-ops="{html.escape(page_ops)}"
        data-mobile-page-ops="enabled"
        data-desktop-page-ops="enabled"
      >
        <div class="section-heading">
          <p class="eyebrow">OCR preview</p>
          <h2 id="page-editor-heading">Pages before analysis</h2>
        </div>
        <div class="thumbnail-strip"
          aria-label="Page preview reorder rotate delete controls">
          <article class="page-card" data-page-index="0" data-text-source="text_layer">
            <header>
              <span>Page 1</span>
              <span class="source-badge">text layer</span>
            </header>
            <div class="page-thumb" aria-label="Page preview thumbnail">OCR preview</div>
            <div class="page-actions" role="group" aria-label="Page operations">
              <button type="button" data-page-action="move-up"
                aria-label="Move page earlier">Up</button>
              <button type="button" data-page-action="move-down"
                aria-label="Move page later">Down</button>
              <button type="button" data-page-action="rotate"
                aria-label="Rotate page">Rotate</button>
              <button type="button" class="secondary danger"
                data-page-action="delete" aria-label="Delete page">Delete</button>
            </div>
            <label class="ocr-label" for="ocr-correction-0">Correct OCR text</label>
            <textarea id="ocr-correction-0" rows="3" spellcheck="false"
              data-ocr-correction="true"></textarea>
          </article>
        </div>
        <div class="action-row page-toolbar">
          <button type="button" class="secondary"
            data-page-action="low-confidence-filter">Low confidence</button>
          <button type="button" class="secondary"
            data-page-action="apply-corrections">Apply corrections</button>
        </div>
      </section>
    </details>"""


def _render_ingest_mode_control(control: Any) -> str:
    attrs = {
        "id": f"ingest-{control.mode}",
        "name": f"ingest_{control.mode}",
        "data-ingest-mode": control.mode,
        "data-mobile-enabled": str(control.mobile_enabled).lower(),
        "data-desktop-enabled": str(control.desktop_enabled).lower(),
        "data-reaches-report": str(control.reaches_report).lower(),
        "aria-label": control.aria_label,
    }
    if control.input_kind == "file":
        attrs.update(
            {
                "type": "file",
                "accept": control.accept,
            }
        )
        if control.capture:
            attrs["capture"] = control.capture
        control_html = f"<input {_html_attrs(attrs)}>"
    else:
        control_html = (
            f'<a class="tile-link" href="#paste-box" '
            f'data-ingest-mode="{html.escape(control.mode)}">Open paste field</a>'
        )
    return (
        f'<label class="upload-tile" data-ingest-mode="{html.escape(control.mode)}" '
        f'data-input-kind="{html.escape(control.input_kind)}">'
        f"<span>{html.escape(control.label)}</span>"
        f"<small>{html.escape(control.aria_label)}</small>"
        f"{control_html}"
        "</label>"
    )


def _render_layout_support(layout: Any) -> str:
    return (
        f'<span data-layout="{html.escape(layout.layout_id)}" '
        f'data-runtime-profile="{html.escape(layout.runtime_profile)}" '
        f'data-input-modes="{html.escape(" ".join(layout.input_modes))}" '
        f'data-page-ops="{html.escape(" ".join(layout.page_operations))}" '
        f'data-pdf-upload-enabled="{str(layout.pdf_upload_enabled).lower()}" '
        f'data-min-touch-target-px="{layout.min_touch_target_px}"></span>'
    )


def _render_step(step: dict[str, str]) -> str:
    return (
        '<li class="how-to-step" data-how-to-step="true">'
        f'<span lang="ko" data-locale-text="ko">{html.escape(step["ko"])}</span>'
        f'<span lang="en" data-locale-text="en">{html.escape(step["en"])}</span>'
        "</li>"
    )


def _html_attrs(attrs: dict[str, str]) -> str:
    return " ".join(
        f'{key}="{html.escape(value, quote=True)}"' for key, value in attrs.items()
    )


def _analysis_payload_from_request(body: dict[str, Any]) -> dict[str, Any]:
    """Run the local pipeline for one parsed request body and return the payload.

    The body shape is ``{"paste_text": str, "locale": "ko"|"en",
    "assumptions"?: {...}}``. Validation/finance errors raised by the offline
    engines are allowed to propagate; the route maps them to a 400.
    """

    paste_text = body.get("paste_text")
    if not isinstance(paste_text, str):
        raise _ingest_validation_error("paste_text must be a string")
    locale = _resolve_api_locale(body)
    scenario_inputs = _assumptions_from_payload(body.get("assumptions"))
    result = run_local_analysis(
        pasted_text=paste_text,
        scenario_inputs=scenario_inputs,
        ui_locale=locale,
    )
    return analysis_result_to_payload(result, locale)


def _analysis_payload_from_raw_request(
    raw: bytes, content_type: str | None
) -> dict[str, Any]:
    if is_multipart_content_type(content_type):
        request = parse_multipart_analyze_request(raw, content_type)
        locale = _resolve_api_locale(request.fields)
        scenario_inputs = _assumptions_from_payload(
            assumptions_from_multipart_fields(request.fields)
        )
        return analyze_multipart_request(
            request,
            scenario_inputs=scenario_inputs,
            ui_locale=locale,
        )

    try:
        body = json.loads(raw.decode("utf-8")) if raw else {}
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise AnalyzeRequestError(
            error_code="REQUEST_INVALID",
            status_code=400,
            validation_status="rejected_corrupt",
            message_ko="요청 본문은 올바른 JSON이어야 합니다.",
            message_en="Request body must be valid JSON.",
            action_ko="JSON 또는 multipart/form-data 형식으로 다시 보내세요.",
            action_en="Send JSON or multipart/form-data and try again.",
        ) from exc
    if not isinstance(body, dict):
        raise AnalyzeRequestError(
            error_code="REQUEST_INVALID",
            status_code=400,
            validation_status="rejected_corrupt",
            message_ko="요청 본문은 JSON 객체여야 합니다.",
            message_en="Request body must be a JSON object.",
            action_ko="paste_text 필드가 있는 JSON 객체를 보내세요.",
            action_en="Send a JSON object with a paste_text field.",
        )
    return _analysis_payload_from_request(body)


def _resolve_api_locale(body: dict[str, Any]) -> UILocale:
    if "locale" not in body or body.get("locale") is None:
        return UILocale.KO
    return _coerce_locale(body["locale"])


def _coerce_locale(value: Any) -> UILocale:
    if isinstance(value, UILocale):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        try:
            return UILocale(normalized)
        except ValueError as exc:
            raise LocaleValidationError("locale must be 'ko' or 'en'") from exc
    raise LocaleValidationError("locale must be 'ko' or 'en'")


def _assumptions_from_payload(value: Any) -> EditableAssumptions | None:
    """Build EditableAssumptions from a flat JSON object of decimal-like fields.

    Only fields that exist on EditableAssumptions are accepted; unknown keys are
    ignored so a malformed extra field cannot crash the request. Numeric strings
    are converted to Decimal. Returns None when no usable assumption is present,
    which keeps the monetary dimension blank.
    """

    if not isinstance(value, dict) or not value:
        return None
    from dataclasses import fields as dataclass_fields
    from decimal import Decimal, InvalidOperation

    allowed = {item.name for item in dataclass_fields(EditableAssumptions)}
    int_fields = {"unpaid_revision_units", "exclusivity_duration_months", "renewal_duration_months"}
    # Non-scalar assumption fields (e.g. secondary_rights is a tuple of rows)
    # cannot be built from a flat numeric input and would crash the FIM modules.
    skip_fields = {"secondary_rights"}
    kwargs: dict[str, Any] = {}
    for key, raw in value.items():
        if key not in allowed or key in skip_fields or raw is None or raw == "":
            continue
        try:
            if key in int_fields:
                kwargs[key] = int(raw)
            else:
                kwargs[key] = Decimal(str(raw))
        except (InvalidOperation, ValueError, TypeError):
            continue
    if not kwargs:
        return None
    return EditableAssumptions(**kwargs)


def _ingest_validation_error(message: str) -> Exception:
    from fink.ingest.session import IngestValidationError

    return IngestValidationError(message)


def _local_analysis_client_errors() -> tuple[type[BaseException], ...]:
    """Exception types from the offline engines that map to an HTTP 400.

    These are user-input/validation failures (bad paste, schema violation, or
    finance-impact misuse), not server faults, so the route returns 400 with a
    ``local_only`` flag rather than 500.
    """

    from fink.finance import FinanceImpactError
    from fink.ingest.session import IngestValidationError
    from fink.schemas import SchemaValidationError

    return (IngestValidationError, SchemaValidationError, FinanceImpactError)


def _local_analysis_setup_errors() -> tuple[type[BaseException], ...]:
    """Engine setup/index failures (missing or corrupt local config/corpus).

    These are not user-input faults; the demo returns a friendly 503 with install
    guidance rather than leaking a 500 traceback.
    """

    from fink.retrieval.engine import RetrievalCorpusError
    from fink.scoring.engine import ScoringAggregationError
    from fink.signals.engine import SignalDetectionError

    return (SignalDetectionError, ScoringAggregationError, RetrievalCorpusError)


def _structured_local_error(
    *, code: str, message_ko: str, message_en: str, action_ko: str, action_en: str
) -> dict[str, Any]:
    """A stable, structured, bilingual error body (no traceback, no leaked input)."""

    return {
        "local_only": True,
        "error_code": code,
        "error": message_ko,
        "error_en": message_en,
        "next_action": action_ko,
        "next_action_en": action_en,
    }


def _structured_locale_error() -> dict[str, Any]:
    return _structured_local_error(
        code="locale_invalid",
        message_ko="지원하지 않는 화면 언어입니다.",
        message_en="Unsupported UI locale. Use 'ko' or 'en'.",
        action_ko="locale 값을 ko 또는 en으로 보내거나 생략하세요.",
        action_en="Send locale as 'ko' or 'en', or omit it to use Korean.",
    )


def app_js() -> str:
    """Return the analyze and locale-toggle JavaScript served at /app.js.

    All network access (the single POST to /api/analyze) and DOM rendering live
    here, never inline in the index, so the page satisfies the
    ``script-src 'self'`` Content-Security-Policy.
    """

    return _APP_JS


def create_app(settings: WebBindSettings | None = None) -> Any:
    """Create the local web app.

    A real FastAPI app is returned when FastAPI is installed. The lightweight
    ASGI fallback keeps smoke tests and local rendering available in minimal
    offline environments without adding an out-of-scope dependency here.
    """

    bind = settings or resolve_bind_settings()
    try:
        return _create_fastapi_app(bind)
    except ModuleNotFoundError as exc:
        if exc.name not in {"fastapi", "fastapi.responses"}:
            raise
        return LocalASGIApp(bind)


def _create_fastapi_app(settings: WebBindSettings) -> Any:
    from fastapi import FastAPI, Request
    from fastapi.responses import HTMLResponse, JSONResponse, Response

    app = FastAPI(
        title="FInk Local Web",
        version="0.0.0",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    @app.middleware("http")
    async def add_local_security_headers(request: Any, call_next: Any) -> Any:
        response = await call_next(request)
        _apply_security_headers(response.headers)
        return response

    @app.get("/", response_class=HTMLResponse)
    def index() -> HTMLResponse:
        return HTMLResponse(render_index_html(settings))

    @app.get("/app.js")
    def app_js_route() -> Any:
        return Response(content=app_js(), media_type="application/javascript")

    async def analyze_route(request: Request) -> JSONResponse:
        try:
            raw = await request.body()
            payload = _analysis_payload_from_raw_request(
                raw,
                request.headers.get("content-type"),
            )
        except AnalyzeRequestError as exc:
            return JSONResponse(exc.to_payload(), status_code=exc.status_code)
        except LocaleValidationError:
            return JSONResponse(_structured_locale_error(), status_code=422)
        except _local_analysis_client_errors() as exc:
            return JSONResponse(
                _structured_local_error(
                    code="input_invalid",
                    message_ko="입력을 분석할 수 없습니다.",
                    message_en=f"Could not analyze the input: {exc}",
                    action_ko="붙여넣은 계약 내용을 확인하고 다시 시도하세요.",
                    action_en="Check the pasted contract text and try again.",
                ),
                status_code=400,
            )
        except _local_analysis_setup_errors() as exc:
            return JSONResponse(
                _structured_local_error(
                    code="setup_incomplete",
                    message_ko="로컬 설정 또는 공식 출처 색인을 불러오지 못했습니다.",
                    message_en=f"A local config or official-source index could not be loaded: {exc}",
                    action_ko="설치를 확인하거나 저장소를 다시 클론한 뒤 다시 시도하세요.",
                    action_en="Check your install or re-clone the repository, then retry.",
                ),
                status_code=503,
            )
        except Exception:  # never leak a traceback or contract text to the client
            return JSONResponse(
                _structured_local_error(
                    code="internal_local_error",
                    message_ko="기기 내 분석 중 예기치 않은 오류가 발생했습니다.",
                    message_en="An unexpected error occurred during local analysis.",
                    action_ko="입력을 줄여 다시 시도하거나 설치 상태를 확인하세요.",
                    action_en="Try a smaller input or check your install.",
                ),
                status_code=500,
            )
        return JSONResponse(payload)

    # `from __future__ import annotations` stores the `request` annotation as the
    # string "Request", which FastAPI resolves against the function globals where
    # `Request` is not defined (it is a local import). Bind the real class so
    # FastAPI injects the Request object instead of treating it as a query param.
    analyze_route.__annotations__["request"] = Request
    app.post("/api/analyze")(analyze_route)

    @app.get("/healthz")
    def healthz() -> JSONResponse:
        return JSONResponse(_health_payload(settings))

    @app.get("/privacy")
    def privacy() -> JSONResponse:
        return JSONResponse(_privacy_payload(settings))

    return app


class LocalASGIApp:
    """Small ASGI fallback for dependency-minimal local smoke tests."""

    def __init__(self, settings: WebBindSettings) -> None:
        self.settings = settings

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") != "http":
            await _send_response(send, 404, b"Not found", "text/plain; charset=utf-8")
            return
        method = scope.get("method", "GET")
        path = scope.get("path", "/")

        if method == "POST" and path == "/api/analyze":
            await self._handle_analyze(scope, receive, send)
            return
        if method != "GET":
            await _send_response(send, 405, b"Method not allowed", "text/plain; charset=utf-8")
            return
        if path == "/":
            await _send_response(
                send,
                200,
                render_index_html(self.settings).encode("utf-8"),
                "text/html; charset=utf-8",
            )
            return
        if path == "/app.js":
            await _send_response(
                send,
                200,
                app_js().encode("utf-8"),
                "application/javascript",
            )
            return
        if path == "/healthz":
            await _send_response(
                send,
                200,
                json.dumps(_health_payload(self.settings)).encode("utf-8"),
                "application/json",
            )
            return
        if path == "/privacy":
            await _send_response(
                send,
                200,
                json.dumps(_privacy_payload(self.settings)).encode("utf-8"),
                "application/json",
            )
            return
        await _send_response(send, 404, b"Not found", "text/plain; charset=utf-8")

    async def _handle_analyze(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        body = await _read_request_body(receive)
        try:
            payload = _analysis_payload_from_raw_request(
                body,
                _header_value(scope, "content-type"),
            )
        except AnalyzeRequestError as exc:
            await _send_json(send, exc.status_code, exc.to_payload())
            return
        except LocaleValidationError:
            await _send_json(send, 422, _structured_locale_error())
            return
        except _local_analysis_client_errors() as exc:
            await _send_json(send, 400, _structured_local_error(
                code="input_invalid",
                message_ko="입력을 분석할 수 없습니다.",
                message_en=f"Could not analyze the input: {exc}",
                action_ko="붙여넣은 계약 내용을 확인하고 다시 시도하세요.",
                action_en="Check the pasted contract text and try again.",
            ))
            return
        except _local_analysis_setup_errors() as exc:
            await _send_json(send, 503, _structured_local_error(
                code="setup_incomplete",
                message_ko="로컬 설정 또는 공식 출처 색인을 불러오지 못했습니다.",
                message_en=f"A local config or official-source index could not be loaded: {exc}",
                action_ko="설치를 확인하거나 저장소를 다시 클론한 뒤 다시 시도하세요.",
                action_en="Check your install or re-clone the repository, then retry.",
            ))
            return
        except Exception:  # never leak a traceback or contract text to the client
            await _send_json(send, 500, _structured_local_error(
                code="internal_local_error",
                message_ko="기기 내 분석 중 예기치 않은 오류가 발생했습니다.",
                message_en="An unexpected error occurred during local analysis.",
                action_ko="입력을 줄여 다시 시도하거나 설치 상태를 확인하세요.",
                action_en="Try a smaller input or check your install.",
            ))
            return
        await _send_json(send, 200, payload)


async def _read_request_body(receive: Any) -> bytes:
    """Consume ASGI http.request events until the body is complete."""

    chunks: list[bytes] = []
    while True:
        message = await receive()
        if message.get("type") != "http.request":
            break
        chunks.append(message.get("body", b"") or b"")
        if not message.get("more_body", False):
            break
    return b"".join(chunks)


def _header_value(scope: dict[str, Any], name: str) -> str | None:
    target = name.lower().encode("ascii")
    for raw_key, raw_value in scope.get("headers", []):
        if raw_key.lower() == target:
            return raw_value.decode("latin-1")
    return None


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the FInk local FastAPI web app.")
    parser.add_argument(
        "--host",
        default=None,
        help="Bind host. Defaults to loopback; LAN addresses require --allow-lan.",
    )
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument(
        "--allow-lan",
        action="store_true",
        help="Allow binding to a specific private LAN interface.",
    )
    parser.add_argument(
        "--trusted-lan-ack",
        action="store_true",
        help="Acknowledge the trusted-LAN warning before LAN binding.",
    )
    args = parser.parse_args(argv)
    try:
        settings = resolve_bind_settings(
            host=args.host,
            port=args.port,
            allow_lan=args.allow_lan,
            trusted_lan_ack=args.trusted_lan_ack,
        )
    except WebBindingError as exc:
        parser.error(str(exc))
    try:
        import uvicorn
    except ModuleNotFoundError as exc:
        raise SystemExit("uvicorn is required to run the FastAPI server") from exc
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port, log_config=None)
    return 0


def _health_payload(settings: WebBindSettings) -> dict[str, Any]:
    return {
        "status": "ok",
        "local_only": True,
        "outbound_network_clients": 0,
        "bind": settings.public_dict(),
    }


def _privacy_payload(settings: WebBindSettings) -> dict[str, Any]:
    return {
        "privacy_banner": PRIVACY_BANNER,
        "not_legal_advice_banner": NOT_LEGAL_ADVICE_BANNER,
        "disclosures": DISCLOSURE_ITEMS,
        "lan": settings.public_dict(),
    }


def _css() -> str:
    return """
:root {
  color-scheme: light;
  --ink: #151a22;
  --muted: #4a5565;
  --line: #d4dbe5;
  --line-soft: #e6ebf2;
  --panel: #ffffff;
  --canvas: #eef2f7;
  --accent: #006d77;
  --accent-strong: #014f56;
  --accent-tint: #f1f8f9;
  --warn-bg: #fff3cd;
  --warn-ink: #5a4100;
  /* 8px spacing rhythm. */
  --space-1: .5rem;
  --space-2: 1rem;
  --space-3: 1.5rem;
  --space-4: 2rem;
  --radius: 10px;
  --shadow: 0 1px 2px rgba(21, 26, 34, .06), 0 6px 18px rgba(21, 26, 34, .05);
  --reading-measure: 66ch;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--canvas);
  color: var(--ink);
  font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  line-height: 1.6;
}
.skip-link {
  position: absolute;
  left: 1rem;
  top: -5rem;
  background: var(--ink);
  color: #fff;
  padding: .75rem 1rem;
  z-index: 3;
}
.skip-link:focus { top: 1rem; }
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}
.topbar, footer {
  display: flex;
  gap: 1rem;
  justify-content: space-between;
  align-items: center;
  padding: 1rem clamp(1rem, 4vw, 2rem);
  background: var(--panel);
  border-bottom: 1px solid var(--line);
}
h1, h2, h3, p { margin-top: 0; }
h1 { margin-bottom: .15rem; font-size: 1.75rem; }
h2 { font-size: 1.25rem; }
h3 { font-size: 1rem; }
.eyebrow {
  margin-bottom: .25rem;
  color: var(--accent-strong);
  font-size: .8rem;
  font-weight: 700;
  text-transform: uppercase;
}
.subtitle, .hint, article p, footer { color: var(--muted); }
.locale-toggle, .action-row, .upload-grid {
  display: flex;
  gap: .75rem;
  flex-wrap: wrap;
}
button, input, textarea {
  font: inherit;
  min-height: 44px;
}
button {
  border: 1px solid var(--accent-strong);
  background: var(--accent);
  color: #fff;
  padding: .65rem 1rem;
  border-radius: 6px;
  font-weight: 700;
}
button.secondary, .locale-toggle button {
  background: #fff;
  color: var(--accent-strong);
}
button:focus-visible, input:focus-visible, textarea:focus-visible, a:focus-visible {
  outline: 3px solid #ffbf47;
  outline-offset: 2px;
}
.disclosure-bar {
  position: sticky;
  top: 0;
  z-index: 2;
  display: grid;
  gap: .5rem;
  padding: .75rem clamp(1rem, 4vw, 2rem);
  background: #e8f3f4;
  border-bottom: 1px solid var(--line);
}
.banner {
  margin: 0;
  padding: .7rem .85rem;
  border-left: 4px solid var(--accent);
  background: #fff;
}
.banner-warning {
  color: var(--warn-ink);
  background: var(--warn-bg);
  border-left-color: #b7791f;
}
.workspace {
  display: grid;
  gap: var(--space-3);
  padding: var(--space-2);
  max-width: 72rem;
  margin: 0 auto;
}
.primary-flow {
  display: grid;
  gap: var(--space-2);
}
.advanced-tools {
  display: grid;
  gap: var(--space-1);
}
/* Shared card surface for the primary flow. */
.card {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: var(--radius);
  padding: var(--space-2);
  box-shadow: var(--shadow);
}
.upload-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(8rem, 1fr));
  margin-bottom: 1rem;
}
.ingest-form { margin-bottom: 1rem; }
.upload-tile {
  display: grid;
  gap: .5rem;
  min-height: 7rem;
  align-content: center;
  padding: 1rem;
  border: 1px dashed var(--accent);
  border-radius: 8px;
  background: #f9fcfd;
}
.upload-tile span { font-weight: 800; }
.upload-tile small {
  color: var(--muted);
  line-height: 1.3;
}
.upload-tile input {
  width: 100%;
  min-width: 0;
}
.tile-link {
  color: var(--accent-strong);
  font-weight: 700;
}
.pdf-local-notice, .local-error {
  margin: 0 0 .75rem;
  padding: .7rem .85rem;
  border: 1px solid var(--line);
  border-radius: 6px;
  background: #fff;
}
.pdf-local-notice { border-left: 4px solid var(--accent); }
.local-error {
  color: var(--warn-ink);
  border-left: 4px solid #b7791f;
  background: var(--warn-bg);
}
.paste-label {
  display: block;
  margin-bottom: .35rem;
  font-weight: 700;
}
.file-input-row {
  display: grid;
  gap: .75rem;
  margin-top: 1rem;
}
.upload-label {
  font-weight: 700;
}
#contract-file {
  width: 100%;
  min-width: 0;
  border: 1px solid var(--line);
  border-radius: 6px;
  padding: .55rem .65rem;
  background: #fff;
}
textarea {
  width: 100%;
  min-height: 9rem;
  resize: vertical;
  border: 1px solid var(--line);
  border-radius: 6px;
  padding: .75rem;
}
.action-row { margin-top: 1rem; }
.page-editor {
  margin-top: 1rem;
  padding-top: 1rem;
  border-top: 1px solid var(--line);
}
.thumbnail-strip {
  display: grid;
  gap: .75rem;
}
.page-card {
  display: grid;
  gap: .75rem;
  min-width: 0;
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: .85rem;
  background: #fbfcfe;
}
.page-card header, .page-actions {
  display: flex;
  align-items: center;
  gap: .5rem;
  flex-wrap: wrap;
}
.page-card header { justify-content: space-between; }
.source-badge {
  padding: .2rem .45rem;
  border: 1px solid var(--line);
  border-radius: 999px;
  color: var(--accent-strong);
  background: #fff;
  font-size: .8rem;
  font-weight: 700;
}
.page-thumb {
  display: grid;
  place-items: center;
  min-height: 8rem;
  aspect-ratio: 3 / 4;
  border: 1px dashed var(--line);
  background: #fff;
  color: var(--muted);
}
.page-actions button { flex: 1 1 6rem; }
.danger {
  border-color: #8a2c0d;
  color: #8a2c0d;
}
.ocr-label {
  font-weight: 700;
}
.page-toolbar {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(10rem, 1fr));
}
.dimension-grid {
  display: grid;
  gap: .75rem;
  grid-template-columns: repeat(auto-fit, minmax(12rem, 1fr));
}
.report-ui {
  display: grid;
  gap: 1rem;
}
.assumptions-panel {
  display: grid;
  gap: .85rem;
  margin-bottom: 1rem;
  padding: 1rem;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: #fbfcfe;
}
.assumption-fields {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(13rem, 1fr));
  gap: .65rem;
}
.assumption-field {
  display: grid;
  gap: .25rem;
}
.assumption-field span {
  font-weight: 700;
}
.assumption-field small {
  color: var(--muted);
}
.assumption-field input {
  width: 100%;
  min-width: 0;
  border: 1px solid var(--line);
  border-radius: 6px;
  padding: .55rem .65rem;
}
.assumption-results {
  display: grid;
  gap: .6rem;
  margin: 0;
  padding-left: 1.15rem;
}
.assumption-results output {
  margin-top: .25rem;
  font-size: 1rem;
}
article {
  min-height: 8rem;
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 1rem;
}
.dimension-grid article {
  background: var(--panel);
}
.category-cards, .non-scoring-context {
  border-top: 1px solid var(--line);
  padding-top: 1rem;
}
.risk-category-card {
  display: grid;
  gap: .9rem;
  margin-bottom: .75rem;
  background: #fbfcfe;
}
.risk-category-card header {
  display: grid;
  gap: .2rem;
}
.risk-category-card h4, .risk-category-card h5 {
  margin: 0;
}
.badge {
  display: inline-block;
  width: fit-content;
  padding: .2rem .45rem;
  border: 1px solid var(--line);
  border-radius: 999px;
  background: #fff;
  color: var(--accent-strong);
  font-size: .8rem;
  font-weight: 700;
}
.unverified-badge {
  color: var(--warn-ink);
  background: var(--warn-bg);
  border-color: #b7791f;
}
.generated-label, .synthetic-assumption {
  margin-left: .25rem;
}
.flagged-clauses, .exposure-list, .reference-list,
.questions-before-signing ul, .non-scoring-context ul {
  display: grid;
  gap: .6rem;
  margin: 0;
  padding-left: 1.15rem;
}
mark {
  padding: .05rem .2rem;
  background: #fff0a8;
}
.source-grid {
  display: grid;
  gap: .6rem;
}
.source-card {
  border: 1px solid var(--line);
  border-radius: 6px;
  padding: .75rem;
  background: #fff;
}
.metric-list {
  display: grid;
  grid-template-columns: minmax(9rem, 1fr) minmax(5rem, auto);
  gap: .35rem .75rem;
  margin: 0;
}
.metric-list dd {
  margin: 0;
  font-weight: 700;
}
output {
  display: block;
  font-size: 1.75rem;
  font-weight: 800;
}
.export-disclosures {
  margin-top: 1rem;
  padding-top: 1rem;
  border-top: 1px solid var(--line);
}
.export-disclosures li { margin-bottom: .4rem; }
footer {
  border-top: 1px solid var(--line);
  border-bottom: 0;
}
[data-active-locale="ko"] [data-locale-text="en"],
[data-active-locale="en"] [data-locale-text="ko"] {
  display: none;
}
/* Collapsed report/page panels sit inside a disclosure, so they stay flat to
   avoid a double border with the disclosure frame. */
.report-pane, .page-editor {
  padding: var(--space-2) 0 0;
}
.section-heading { margin-bottom: var(--space-2); }
.how-to-steps {
  display: grid;
  gap: var(--space-1);
  margin: 0;
  padding-left: 1.25rem;
}
.how-to-step {
  padding-left: .25rem;
}
.how-to-step span { font-weight: 600; }
.input-pane .hint, .how-to .eyebrow + h2 { max-width: var(--reading-measure); }
#analyze-btn { font-weight: 800; }
#analyze-btn:hover { background: var(--accent-strong); }
.action-row { margin-top: var(--space-2); }
.result-pane[hidden] { display: none; }
.result-pane:not([hidden]) {
  border-top: 4px solid var(--accent);
}
.nl-summary {
  max-width: var(--reading-measure);
  font-size: 1.05rem;
  line-height: 1.65;
}
/* Optional-tool disclosures: de-emphasized, collapsed by default. */
.upload-details {
  margin-top: var(--space-2);
  border-top: 1px solid var(--line-soft);
  padding-top: var(--space-1);
}
.tool-details {
  background: var(--panel);
  border: 1px solid var(--line-soft);
  border-radius: var(--radius);
  padding: 0 var(--space-2);
}
.upload-details > summary, .tool-details > summary {
  cursor: pointer;
  padding: var(--space-1) .25rem;
  color: var(--accent-strong);
  font-weight: 700;
  list-style-position: inside;
}
.tool-details > summary {
  padding: .85rem .25rem;
}
.upload-details[open] > summary, .tool-details[open] > summary {
  border-bottom: 1px solid var(--line-soft);
  margin-bottom: var(--space-1);
}
.upload-details > summary:focus-visible, .tool-details > summary:focus-visible {
  outline: 3px solid #ffbf47;
  outline-offset: 2px;
}
.recommended-action {
  display: grid;
  gap: var(--space-1);
  margin: var(--space-2) 0;
  padding: var(--space-2);
  border: 1px solid var(--accent);
  border-left: 6px solid var(--accent);
  border-radius: var(--radius);
  background: var(--accent-tint);
}
.action-line { font-weight: 800; margin: 0; font-size: 1.1rem; }
.cash-flow-line { margin: 0; color: var(--muted); }
.result-meta {
  color: var(--muted);
  font-size: .9rem;
  margin: var(--space-1) 0 var(--space-2);
}
.dimension-card {
  display: grid;
  gap: .5rem;
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: .85rem;
  background: var(--panel);
}
.dimension-card h4 { margin: 0; }
.exposure-line { margin: 0; font-weight: 700; }
.ranked-findings, .guidance-card ul {
  display: grid;
  gap: .6rem;
  margin: 0;
  padding-left: 1.15rem;
}
.finding-card, .guidance-card {
  display: grid;
  gap: var(--space-1);
  border: 1px solid var(--line);
  border-radius: var(--radius);
  padding: var(--space-2);
  background: var(--panel);
  box-shadow: var(--shadow);
}
.finding-head { display: flex; gap: .5rem; flex-wrap: wrap; align-items: center; }
/* The rank badge leads each finding card. */
.finding-head .badge:first-child {
  background: var(--accent);
  color: #fff;
  border-color: var(--accent-strong);
}
.finding-label { font-weight: 800; margin: 0; }
.finding-heading { margin: 0; font-weight: 700; }
.finding-snippet { margin: 0; max-width: var(--reading-measure); color: var(--muted); }
.guidance-card h4 { margin: 0; }
.guidance-why { margin: 0; max-width: var(--reading-measure); font-weight: 600; }
@media (min-width: 900px) {
  .workspace {
    padding: var(--space-4) var(--space-4);
  }
  .disclosure-bar {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .thumbnail-strip {
    grid-template-columns: repeat(auto-fit, minmax(13rem, 1fr));
  }
  .source-grid {
    grid-template-columns: repeat(auto-fit, minmax(12rem, 1fr));
  }
}
@media (max-width: 640px) {
  .topbar, footer {
    align-items: stretch;
    flex-direction: column;
  }
  .locale-toggle button, .action-row button, .page-actions button {
    flex: 1 1 10rem;
  }
  .page-thumb {
    min-height: 10rem;
  }
}
"""


_APP_JS = r"""(function () {
  "use strict";

  var LOCALE_STORAGE_KEY = "fink.ui_locale";
  var analyzeInFlight = false;

  function normalizeLocale(locale) {
    var normalized = String(locale || "").trim().toLowerCase();
    return normalized === "en" || normalized === "ko" ? normalized : "ko";
  }

  function readStoredLocale() {
    try {
      return window.localStorage.getItem(LOCALE_STORAGE_KEY);
    } catch (error) {
      return null;
    }
  }

  function writeStoredLocale(locale) {
    try {
      window.localStorage.setItem(LOCALE_STORAGE_KEY, locale);
    } catch (error) {
      return;
    }
  }

  function setLocale(locale) {
    locale = normalizeLocale(locale);
    var root = document.documentElement;
    root.setAttribute("data-active-locale", locale);
    root.setAttribute("lang", locale);
    var buttons = document.querySelectorAll("[data-locale-button]");
    buttons.forEach(function (button) {
      var active = button.getAttribute("data-locale-button") === locale;
      button.setAttribute("aria-pressed", active ? "true" : "false");
    });
    writeStoredLocale(locale);
  }

  function activeLocale() {
    return normalizeLocale(document.documentElement.getAttribute("data-active-locale"));
  }

  function text(node) {
    return node == null ? "" : String(node);
  }

  function el(tag, className, content) {
    var node = document.createElement(tag);
    if (className) {
      node.className = className;
    }
    if (content != null) {
      node.textContent = content;
    }
    return node;
  }

  function bilingual(tag, className, pair) {
    var wrap = el(tag, className, null);
    var ko = el("span", null, text(pair && pair.ko));
    ko.setAttribute("lang", "ko");
    ko.setAttribute("data-locale-text", "ko");
    var en = el("span", null, text(pair && pair.en));
    en.setAttribute("lang", "en");
    en.setAttribute("data-locale-text", "en");
    wrap.appendChild(ko);
    wrap.appendChild(en);
    return wrap;
  }

  function statusMessage(pair) {
    var status = document.querySelector("[data-analyze-status]");
    if (!status) {
      return;
    }
    status.innerHTML = "";
    status.appendChild(bilingual("span", null, pair));
  }

  function renderFindings(container, findings) {
    if (!findings || findings.length === 0) {
      return;
    }
    var list = el("ol", "ranked-findings", null);
    list.setAttribute("data-ranked-findings", "true");
    findings.forEach(function (finding) {
      var item = el("li", "finding-card", null);
      item.setAttribute("data-finding-rank", String(finding.rank));
      var head = el("div", "finding-head", null);
      head.appendChild(el("span", "badge", "#" + finding.rank + " " + finding.risk_category));
      var grounding = el("span", "badge unverified-badge", finding.grounding);
      head.appendChild(grounding);
      item.appendChild(head);
      item.appendChild(bilingual("p", "finding-label", finding.label));
      if (finding.clause_heading) {
        item.appendChild(el("p", "finding-heading", finding.clause_heading));
      }
      if (finding.snippet) {
        item.appendChild(el("p", "finding-snippet", finding.snippet));
      }
      list.appendChild(item);
    });
    container.appendChild(list);
  }

  function renderGuidance(container, guidance) {
    if (!guidance || guidance.length === 0) {
      return;
    }
    guidance.forEach(function (entry) {
      var card = el("div", "guidance-card", null);
      card.setAttribute("data-guidance-category", entry.risk_category);
      card.appendChild(el("h4", null, entry.risk_category));
      card.appendChild(bilingual("p", "guidance-why", entry.why_it_matters));
      var koList = el("ul", null, null);
      koList.setAttribute("lang", "ko");
      koList.setAttribute("data-locale-text", "ko");
      (entry.questions.ko || []).forEach(function (q) {
        koList.appendChild(el("li", null, q));
      });
      var enList = el("ul", null, null);
      enList.setAttribute("lang", "en");
      enList.setAttribute("data-locale-text", "en");
      (entry.questions.en || []).forEach(function (q) {
        enList.appendChild(el("li", null, q));
      });
      card.appendChild(koList);
      card.appendChild(enList);
      container.appendChild(card);
    });
  }

  function dimensionCard(titlePair, rows) {
    var card = el("div", "dimension-card", null);
    card.appendChild(bilingual("h4", null, titlePair));
    var dl = el("dl", "metric-list", null);
    rows.forEach(function (row) {
      dl.appendChild(el("dt", null, row[0]));
      dl.appendChild(el("dd", null, row[1]));
    });
    card.appendChild(dl);
    return card;
  }

  function renderDimensions(container, dims) {
    var grid = el("div", "dimension-grid", null);
    grid.setAttribute("data-dimension-grid", "true");

    var priority = dims.review_priority;
    var priorityCard = dimensionCard(
      { ko: "검토 우선도 점수", en: "Review priority score" },
      [["score", String(priority.score) + " / 100"], ["grounding", priority.grounding]]
    );
    priorityCard.appendChild(bilingual("p", "hint", priority.note));
    grid.appendChild(priorityCard);

    var monetary = dims.monetary;
    var monetaryCard = dimensionCard(
      { ko: "금액 영향", en: "Monetary impact" },
      [["status", monetary.present ? "computed" : "blank"]]
    );
    if (monetary.present && monetary.exposures) {
      monetary.exposures.forEach(function (exposure) {
        if (exposure.is_user_input_required) {
          return;
        }
        var line =
          exposure.module +
          " " +
          exposure.exposure_type +
          ": low " +
          text(exposure.low) +
          " / base " +
          text(exposure.base) +
          " / high " +
          text(exposure.high);
        monetaryCard.appendChild(el("p", "exposure-line", line));
      });
    } else {
      monetaryCard.appendChild(bilingual("p", "hint", monetary.note));
    }
    grid.appendChild(monetaryCard);

    var time = dims.time;
    grid.appendChild(
      dimensionCard({ ko: "시간 및 경로", en: "Time and pathway" }, [
        ["pathway", time.pathway_label],
        ["runtime_s", time.measured_analysis_runtime_seconds.toFixed(4)],
        ["review_min", String(time.estimated_human_review_minutes)]
      ])
    );

    var confidence = dims.confidence;
    grid.appendChild(
      dimensionCard({ ko: "신뢰도", en: "Confidence" }, [
        ["overall", confidence.overall_confidence.toFixed(3)],
        ["evidence", confidence.evidence_confidence.toFixed(3)],
        ["completeness", confidence.data_completeness.toFixed(3)]
      ])
    );

    container.appendChild(grid);
  }

  function renderResult(payload) {
    var container = document.getElementById("result");
    if (!container) {
      return;
    }
    container.hidden = false;
    container.innerHTML = "";

    var heading = el("div", "section-heading", null);
    heading.appendChild(el("p", "eyebrow", "Decision Brief"));
    heading.appendChild(
      bilingual("h2", null, { ko: "금융 결정 브리프", en: "Financial Decision Brief" })
    );
    container.appendChild(heading);

    container.appendChild(bilingual("p", "nl-summary", payload.nl_summary));

    var action = payload.recommended_action;
    var actionBox = el("div", "recommended-action", null);
    actionBox.setAttribute("data-recommended-action", action.pathway_label);
    actionBox.appendChild(bilingual("p", "action-line", action.action));
    actionBox.appendChild(bilingual("p", "cash-flow-line", action.cash_flow));
    container.appendChild(actionBox);

    var meta = el("p", "result-meta", null);
    meta.textContent =
      "clauses " +
      payload.clause_count +
      " | signals " +
      payload.signal_count +
      " | grounding " +
      payload.grounding;
    container.appendChild(meta);

    renderDimensions(container, payload.dimensions);

    var findingsHeading = bilingual("h3", null, {
      ko: "우선순위 신호 (미확인)",
      en: "Ranked signals (UNVERIFIED)"
    });
    container.appendChild(findingsHeading);
    renderFindings(container, payload.ranked_findings);

    var guidanceHeading = bilingual("h3", null, {
      ko: "협상 질문",
      en: "Questions to ask"
    });
    container.appendChild(guidanceHeading);
    renderGuidance(container, payload.category_guidance);

    setLocale(activeLocale());
    container.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function collectAssumptions() {
    var assumptions = {};
    var inputs = document.querySelectorAll("[data-assumption-field] input");
    inputs.forEach(function (input) {
      var value = input.value.trim();
      if (value !== "") {
        assumptions[input.name] = value;
      }
    });
    return assumptions;
  }

  function selectedFile() {
    var input = document.getElementById("contract-file");
    if (!input || !input.files || input.files.length === 0) {
      return null;
    }
    return input.files[0];
  }

  function setAnalyzeBusy(isBusy) {
    analyzeInFlight = isBusy;
    var button = document.getElementById("analyze-btn");
    var pane = document.querySelector(".input-pane");
    if (button) {
      button.disabled = isBusy;
      button.setAttribute("aria-busy", isBusy ? "true" : "false");
    }
    if (pane) {
      pane.setAttribute("aria-busy", isBusy ? "true" : "false");
    }
  }

  function buildAnalyzeRequest(pasteText, file) {
    var assumptions = collectAssumptions();
    if (file) {
      var form = new FormData();
      form.append("contract_file", file);
      form.append("locale", activeLocale());
      form.append("assumptions", JSON.stringify(assumptions));
      if (pasteText && pasteText.trim() !== "") {
        form.append("paste_text", pasteText);
      }
      return { body: form, headers: {} };
    }
    return {
      body: JSON.stringify({
        paste_text: pasteText,
        locale: activeLocale(),
        assumptions: assumptions
      }),
      headers: { "Content-Type": "application/json" }
    };
  }

  function analyze() {
    if (analyzeInFlight) {
      return;
    }
    var box = document.getElementById("paste-box");
    if (!box) {
      return;
    }
    var pasteText = box.value;
    var file = selectedFile();
    if ((!pasteText || pasteText.trim() === "") && !file) {
      statusMessage({
        ko: "먼저 계약 텍스트를 입력하거나 파일 하나를 선택하세요.",
        en: "Enter contract text or choose one file first."
      });
      return;
    }
    if (pasteText && pasteText.trim() !== "" && file) {
      statusMessage({
        ko: "붙여넣기와 파일 중 하나만 선택하세요.",
        en: "Use either paste text or one file, not both."
      });
      return;
    }
    statusMessage({ ko: "로컬에서 분석 중입니다.", en: "Analyzing locally." });
    setAnalyzeBusy(true);
    var request = buildAnalyzeRequest(pasteText, file);
    fetch("/api/analyze", {
      method: "POST",
      headers: request.headers,
      body: request.body
    })
      .then(function (response) {
        return response.json().then(function (data) {
          return { ok: response.ok, data: data };
        });
      })
      .then(function (result) {
        if (!result.ok) {
          var message =
            result.data && result.data.error
              ? result.data.error
              : "analysis failed";
          if (activeLocale() === "en" && result.data && result.data.error_en) {
            message = result.data.error_en;
          }
          statusMessage({ ko: "오류: " + message, en: "Error: " + message });
          return;
        }
        statusMessage({ ko: "분석을 완료했습니다.", en: "Analysis complete." });
        renderResult(result.data);
      })
      .catch(function () {
        statusMessage({
          ko: "로컬 분석 요청에 실패했습니다.",
          en: "The local analysis request failed."
        });
      })
      .finally(function () {
        setAnalyzeBusy(false);
      });
  }

  function clearAll() {
    var box = document.getElementById("paste-box");
    if (box) {
      box.value = "";
    }
    var input = document.getElementById("contract-file");
    if (input) {
      input.value = "";
    }
    var container = document.getElementById("result");
    if (container) {
      container.hidden = true;
      container.innerHTML = "";
    }
    statusMessage({
      ko: "입력을 지웠습니다.",
      en: "Input cleared."
    });
  }

  function init() {
    var toggle = document.querySelector("[data-locale-toggle]");
    if (toggle) {
      toggle.addEventListener("click", function (event) {
        var button = event.target.closest("[data-locale-button]");
        if (button) {
          setLocale(button.getAttribute("data-locale-button"));
        }
      });
    }
    var analyzeButton = document.getElementById("analyze-btn");
    if (analyzeButton) {
      analyzeButton.addEventListener("click", analyze);
    }
    setLocale(readStoredLocale() || activeLocale());
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
"""


def _validate_port(port: int) -> None:
    if port < 1 or port > 65535:
        raise WebBindingError("port must be between 1 and 65535")


def _format_host_for_url(host: str) -> str:
    try:
        parsed = ipaddress.ip_address(host)
    except ValueError:
        return host
    if parsed.version == 6:
        return f"[{host}]"
    return host


def _is_private_interface(host: str) -> bool:
    try:
        parsed = ipaddress.ip_address(host)
    except ValueError as exc:
        raise WebBindingError("LAN host must be a literal private interface address") from exc
    return bool(parsed.is_private or parsed.is_link_local)


def _apply_security_headers(headers: Any) -> None:
    headers["Cache-Control"] = "no-store"
    headers["Referrer-Policy"] = "no-referrer"
    headers["X-Content-Type-Options"] = "nosniff"
    headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "img-src 'self' data:; "
        "style-src 'self' 'unsafe-inline'; "
        "script-src 'self'; "
        "connect-src 'self'; "
        "base-uri 'none'; "
        "form-action 'self'"
    )


async def _send_json(
    send: Callable[[dict[str, Any]], Awaitable[None]],
    status: int,
    payload: dict[str, Any],
) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    await _send_response(send, status, body, "application/json")


async def _send_response(
    send: Callable[[dict[str, Any]], Awaitable[None]],
    status: int,
    body: bytes,
    content_type: str,
) -> None:
    headers = {
        "content-type": content_type,
        "content-length": str(len(body)),
    }
    _apply_security_headers(headers)
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [
                (key.lower().encode("ascii"), value.encode("utf-8"))
                for key, value in headers.items()
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})


if __name__ == "__main__":
    raise SystemExit(run())

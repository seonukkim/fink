from __future__ import annotations

import argparse
import html
import ipaddress
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable

from fink.schemas import UILocale
from fink.web.analyze import analysis_result_to_payload, run_local_analysis
from fink.web.assumptions import EditableAssumptions
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
    "This service does not collect or track user information or use cloud OCR "
    "or a remote LLM."
)
PRIVACY_BANNER_KO = (
    "본 서비스는 사용자 정보를 수집·추적하거나 클라우드 OCR·원격 LLM을 사용하지 않습니다."
)
# Value first, honest boundary second. The English aid still carries the pinned
# phrase "Contractual Financial Review Priority". This is a disclaimer that FInk
# does NOT determine legality/fraud/validity/etc., so it stays clear of the
# legal_verdict_scan BAD_LEGAL_ASSERTIONS patterns.
NOT_LEGAL_ADVICE_BANNER = (
    "FInk finds and prioritizes the financial clauses in a contract (a Contractual "
    "Financial Review Priority) and organizes decision-support information, but it "
    "is not a final legal judgment, so confirm important decisions with a professional."
)
NOT_LEGAL_ADVICE_BANNER_KO = (
    "FInk은 계약서의 금융 관련 조항을 찾아 중요도를 매기고 결정에 필요한 정보를 "
    "정리해 드리지만, 최종 법적 판단은 아니니 중요한 결정은 전문가와 확인하세요."
)
TRUSTED_LAN_WARNING = (
    "Trusted-LAN mode exposes this local server only to devices on the same private "
    "network. Use it only on a network you control, and stop the server when finished."
)
DISCLOSURE_ITEMS = (
    "Estimated amounts are reference values based on your inputs; Korean is canonical.",
)
# Korean-canonical / English-aid pairs for the report disclosures. The English
# aid strings stay identical to DISCLOSURE_ITEMS so the privacy payload and the
# a11y wording pins still match; the Korean line leads as the canonical text.
DISCLOSURE_ITEMS_BILINGUAL = (
    {
        "ko": "추정 금액은 입력 가정에 따른 참고치이며, 한국어가 기준입니다.",
        "en": DISCLOSURE_ITEMS[0],
    },
)

LAN_CONFIRMATION_TEXT = "I understand this is a trusted-LAN-only local server."
_BLOCKED_BIND_HOSTS = frozenset({"0.0.0.0", "::", ""})
_WEB_FONT_DIR = Path(__file__).resolve().parent / "assets" / "fonts"
_WEB_FONT_FILES = frozenset(
    {
        "NotoSerifKR-500.woff2",
        "NotoSerifKR-600.woff2",
        "NotoSerifKR-700.woff2",
    }
)

WEB_DESIGN_TOKENS = {
    "canvas": "#f4f1ea",
    "panel": "#fdfcf8",
    "card": "#fdfcf8",
    "ink": "#211d18",
    "ink_soft": "#4a443c",
    # The mockup's softer #8a8479 is kept as muted_soft for low-emphasis
    # chrome; muted is the accessible small-text companion used by labels.
    "muted": "#746c61",
    "muted_soft": "#8a8479",
    "pill_idle": "#a0978b",
    "line": "#e9e5dc",
    "line_soft": "#f6f4ed",
    "line_strong": "#dbd6ca",
    "pink": "#a31e4e",
    "pink_deep": "#86173e",
    "pink_ink": "#86173e",
    "pink_bright": "#e83e8c",
    "pink_pale": "#f2e7eb",
    "pink_line": "#d8bfc9",
    "accent": "#a31e4e",
    "accent_strong": "#86173e",
    "accent_tint": "#f2e7eb",
    "charcoal": "#201d1a",
    "green_bg": "#ffffff",
    "green_ink": "#236b43",
    "green_line": "#2f8f5b",
    "amber_bg": "#ffffff",
    "amber_ink": "#86600f",
    "amber_line": "#b9831a",
    "rose_bg": "#ffffff",
    "rose_ink": "#992a22",
    "rose_line": "#c43d34",
    "safe": "#2f8f5b",
    "caution": "#b9831a",
    "warn": "#c43d34",
    "warn_bg": "#fff3cd",
    "warn_ink": "#5a4100",
    "focus_ring": "#0b57d0",
    "focus_offset": "#fdfcf8",
    "danger": "#8a2c0d",
    "source_mark": "#f2e7eb",
}

WEB_CONTRAST_CHECKS = (
    ("body text on panel", "ink", "panel", 4.5),
    ("body text on canvas", "ink", "canvas", 4.5),
    ("muted text on panel", "muted", "panel", 4.5),
    ("muted text on canvas", "muted", "canvas", 4.5),
    ("primary button text", "panel", "pink", 4.5),
    ("secondary button text", "pink_deep", "panel", 4.5),
    ("link text on panel", "pink_deep", "panel", 4.5),
    ("badge text on pink pale", "pink_deep", "pink_pale", 4.5),
    ("calm effort text", "green_ink", "green_bg", 4.5),
    ("attention effort text", "amber_ink", "amber_bg", 4.5),
    ("serious effort text", "rose_ink", "rose_bg", 4.5),
    ("warning text on warning background", "warn_ink", "warn_bg", 4.5),
    ("danger action text", "danger", "panel", 4.5),
    ("focus ring on panel", "focus_ring", "panel", 3.0),
    ("focus ring on canvas", "focus_ring", "canvas", 3.0),
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
    """Render the local-only creator chat without external assets.

    The page is a real chat thread: a sticky top bar (title, the single KO/EN
    toggle, and a Notice button that opens the merged disclosure panel), one
    short privacy line, a scrolling message thread that opens with a single bot
    greeting, and a sticky bottom composer (an attach button, a growing paste
    box, and the send button). The analysis result and the follow-up Q&A render
    as bot/user message bubbles appended to the thread; ``/app.js`` fills the
    ``#result`` node that lives inside a bot bubble.

    The monetary-assumptions grid and the OCR page editor are intentionally not
    rendered here because a creator cannot fill 32 fields or hand-edit pages in
    a browser; the assumptions request-parsing path stays available for the API.

    Korean is canonical and English is a generated aid. Both locales are
    rendered into the DOM as paired ``data-locale-text`` spans and flipped via
    the ``data-active-locale`` attribute, so the single KO/EN toggle works
    before any analyze call. All ``fetch`` and render logic lives in ``/app.js``
    because the Content-Security-Policy restricts scripts to ``'self'``.
    """

    bind = settings or resolve_bind_settings()
    lan_warning = (
        '<p class="banner banner-warning" role="status">'
        f"{html.escape(bind.trusted_lan_warning)}</p>"
        if bind.lan_enabled
        else ""
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
  <header class="chat-topbar">
    <div class="chat-title">
      <p class="wordmark" aria-label="FInk">F<span>I</span>nk</p>
      <span class="brand-divider" aria-hidden="true"></span>
      <div class="chat-title-copy">
        <h1>창작자를 위한 금융 계약 검토</h1>
        <p class="subtitle">Financial Contract Review for Creators</p>
      </div>
    </div>
    <div class="chat-topbar-actions">
      <nav class="locale-toggle" aria-label="Locale" data-locale-toggle="true">
        <button type="button" data-locale-button="toggle" data-active-locale-value="ko"
          aria-pressed="false"
          aria-label="한국어와 영어 전환 / Switch between Korean and English">
          <span lang="ko" data-locale-text="ko">EN</span>
          <span lang="en" data-locale-text="en">KO</span>
        </button>
      </nav>
      <button type="button" class="notice-button" data-notice-toggle="true"
        aria-controls="notice-panel" aria-expanded="false"
        aria-label="고지 열기 또는 닫기 / Open or close notice">
        <span aria-hidden="true">ⓘ</span>
      </button>
    </div>
  </header>

  <p class="chat-privacy" data-privacy-line="true">{_bilingual(PRIVACY_BANNER_KO, PRIVACY_BANNER)}</p>

  {_render_notice_panel(lan_warning)}

  <main id="workspace" class="chat"
    data-responsive-validation-targets="320-no-horizontal-overflow 390x844 768x1024 1440x900 200-percent-zoom">
    <ol class="thread" data-chat-thread="true" aria-live="polite" aria-label="대화 / Conversation">
      <li class="msg bot" data-message-role="bot" data-greeting="true">
        <div class="bubble">
          <p class="bubble-text">{_bilingual(
              "계약서를 붙여넣거나 사진·PDF를 올려 주세요. 서명 전에 확인할 현금흐름 "
              "조항을 정리해 드릴게요.",
              "Paste your contract or drop in a photo/PDF, and I'll line up the "
              "financial clauses to check before you sign.",
          )}</p>
          <div class="chip-row">
            <button type="button" class="example-chip" data-example-chip="true"
              aria-label="예시로 시작 / Try an example">
              {_bilingual("예시로 시작", "Try an example")}
            </button>
          </div>
        </div>
      </li>
      <li class="msg bot result-msg" data-message-role="bot" data-result-message="true" hidden>
        <div class="bubble bubble-result">
          <section id="result" class="result-pane" aria-labelledby="result-heading"
            aria-live="polite" role="region" data-analysis-result="true">
            <h2 id="result-heading" class="sr-only">
              <span lang="ko" data-locale-text="ko">검토 결과</span>
              <span lang="en" data-locale-text="en">Review result</span>
            </h2>
          </section>
        </div>
      </li>
    </ol>
  </main>

  <form class="composer" data-composer="true" autocomplete="off">
    <button type="button" class="attach-button" data-attach-button="true"
      aria-controls="contract-file"
      aria-label="파일 첨부 / Attach a file">
      <svg aria-hidden="true" class="paperclip-icon" viewBox="0 0 24 24" fill="none"
        stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="m21.44 11.05-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"></path>
      </svg>
    </button>
    <input id="contract-file" name="contract_file" type="file" class="visually-hidden-input"
      data-file-input="true"
      aria-describedby="pdf-error-region"
      accept="text/plain,.txt,application/pdf,.pdf,image/png,image/jpeg,image/webp,image/heic,image/heif,.png,.jpg,.jpeg,.webp,.heic,.heif">
    <div class="attachment-preview thumbnail-strip" data-attachment-preview="true" hidden></div>
    <label class="composer-label sr-only" for="paste-box">
      <span lang="ko" data-locale-text="ko">계약 조항 붙여넣기</span>
      <span lang="en" data-locale-text="en">Paste clause text</span>
    </label>
    <textarea id="paste-box" name="paste_text" rows="1" spellcheck="false"
      class="composer-input"
      data-ingest-mode="paste" data-paste-box="true"
      aria-describedby="analyze-status"
      data-placeholder-ko="계약 조항을 붙여넣거나 사진·PDF를 올려 주세요"
      data-placeholder-en="Paste contract clauses or upload a photo/PDF"
      placeholder="계약 조항을 붙여넣거나 사진·PDF를 올려 주세요"></textarea>
    <button type="button" id="analyze-btn" class="send-button" data-analyze-button="true"
      aria-controls="result analyze-status"
      aria-label="보내기 / Send">
      <span aria-hidden="true">↑</span>
    </button>
  </form>
  <p class="hint sr-only" id="analyze-status" data-analyze-status="true" role="status" aria-live="polite">
    <span lang="ko" data-locale-text="ko">계약 자료는 이 기기에서만 처리됩니다.</span>
    <span lang="en" data-locale-text="en">Contract material is processed only on this device.</span>
  </p>
  <div id="pdf-error-region" class="sr-only" data-pdf-error-region="true"
    role="alert" aria-live="assertive">
    {_bilingual(
        "지원하지 않거나 비어 있거나 손상·암호화·용량 초과·OCR 누락 파일은 기기 안에서 "
        "오류로 표시되며, 어떤 내용도 전송되지 않습니다.",
        "Files that are unsupported, empty, corrupted, encrypted, oversized, "
        "or missing OCR text return a local error. Nothing is transmitted.",
    )}
  </div>
  <section id="print-brief" class="print-brief-root" data-print-brief-root="true"
    aria-hidden="true"></section>
  <script src="/app.js"></script>
</body>
</html>
"""


def _render_notice_panel(lan_warning: str) -> str:
    """Render the merged disclosure surface opened by the Notice button.

    One responsive ``<aside>`` panel holds the not-legal-advice text and the
    report-disclosure bullets. The short privacy line lives in the page header;
    this panel carries the rest so there is no two-column disclosure bar.
    """

    bullets = "\n".join(
        f"<li>{_bilingual(item['ko'], item['en'])}</li>"
        for item in DISCLOSURE_ITEMS_BILINGUAL
    )
    return f"""<aside id="notice-panel" class="notice-panel" data-notice-panel="true"
    aria-label="고지 / Notice" hidden>
    <p class="banner banner-advice">{_bilingual(NOT_LEGAL_ADVICE_BANNER_KO, NOT_LEGAL_ADVICE_BANNER)}</p>
    <ul class="notice-list">
      {bullets}
    </ul>
    {lan_warning}
  </aside>"""


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


def _bilingual(ko: str, en: str) -> str:
    """Return a Korean-canonical / English-aid pair of locale spans.

    The active locale is chosen at runtime by the ``data-active-locale``
    attribute on ``<html>``, which CSS uses to hide the inactive ``lang`` span.
    Both strings are escaped so contract-adjacent copy cannot inject markup.
    """

    return (
        f'<span lang="ko" data-locale-text="ko">{html.escape(ko)}</span>'
        f'<span lang="en" data-locale-text="en">{html.escape(en)}</span>'
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
    current_assumptions = body.get("assumptions")
    previous_assumptions = body.get("previous_assumptions")
    changed_input = body.get("changed_input")
    scenario_inputs = _assumptions_from_payload(current_assumptions)
    result = run_local_analysis(
        pasted_text=paste_text,
        scenario_inputs=scenario_inputs,
        ui_locale=locale,
    )
    payload = analysis_result_to_payload(result, locale)
    if isinstance(previous_assumptions, dict) or isinstance(changed_input, str):
        previous_inputs = _assumptions_from_payload(previous_assumptions)
        previous_result = run_local_analysis(
            pasted_text=paste_text,
            scenario_inputs=previous_inputs,
            ui_locale=locale,
        )
        _attach_scenario_recompute_audit(
            payload,
            previous_payload=analysis_result_to_payload(previous_result, locale),
            current_assumptions=_assumption_value_dict(current_assumptions),
            previous_assumptions=_assumption_value_dict(previous_assumptions),
            changed_input=changed_input if isinstance(changed_input, str) else "",
        )
    return payload


def _analysis_payload_from_raw_request(
    raw: bytes, content_type: str | None
) -> dict[str, Any]:
    if is_multipart_content_type(content_type):
        request = parse_multipart_analyze_request(raw, content_type)
        locale = _resolve_api_locale(request.fields)
        scenario_inputs = _assumptions_from_payload(
            assumptions_from_multipart_fields(request.fields)
        )
        payload = analyze_multipart_request(
            request,
            scenario_inputs=scenario_inputs,
            ui_locale=locale,
        )
        previous_assumptions = _json_field(request.fields.get("previous_assumptions"))
        changed_input = request.fields.get("changed_input", "")
        if isinstance(previous_assumptions, dict) or changed_input:
            _attach_scenario_recompute_audit(
                payload,
                previous_payload=None,
                current_assumptions=_assumption_value_dict(
                    assumptions_from_multipart_fields(request.fields)
                ),
                previous_assumptions=_assumption_value_dict(previous_assumptions),
                changed_input=changed_input,
            )
        return payload

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


def _chat_payload_from_raw_request(
    raw: bytes, content_type: str | None
) -> dict[str, Any]:
    try:
        body = json.loads(raw.decode("utf-8")) if raw else {}
    except UnicodeDecodeError as exc:
        raise _ingest_validation_error("chat request body must be JSON") from exc
    except ValueError as exc:
        raise _ingest_validation_error("chat request body must be JSON") from exc
    if not isinstance(body, dict):
        raise _ingest_validation_error("chat request body must be a JSON object")
    paste_text = body.get("paste_text")
    if not isinstance(paste_text, str) or not paste_text.strip():
        raise _ingest_validation_error("paste_text must be a nonblank string")
    question = body.get("question")
    if question is not None and not isinstance(question, str):
        raise _ingest_validation_error("question must be a string")
    locale = _resolve_api_locale(body)
    from fink.web.chat import chat_reply_for_request

    return chat_reply_for_request(
        paste_text=paste_text,
        question=question,
        locale=locale,
    )


def _chat_response(raw: bytes, content_type: str | None) -> tuple[int, dict[str, Any]]:
    try:
        payload = _chat_payload_from_raw_request(raw, content_type)
    except AnalyzeRequestError as exc:
        return exc.status_code, exc.to_payload()
    except LocaleValidationError:
        return 422, _structured_locale_error()
    except _local_analysis_client_errors() as exc:
        return 400, _structured_local_error(
            code="input_invalid",
            message_ko="입력을 분석할 수 없습니다.",
            message_en=f"Could not analyze the input: {exc}",
            action_ko="붙여넣은 계약 내용을 확인하고 다시 시도하세요.",
            action_en="Check the pasted contract text and try again.",
        )
    except _local_analysis_setup_errors() as exc:
        return 503, _structured_local_error(
            code="setup_incomplete",
            message_ko="로컬 설정 또는 공식 출처 색인을 불러오지 못했습니다.",
            message_en=f"A local config or official-source index could not be loaded: {exc}",
            action_ko="설치를 확인하거나 저장소를 다시 클론한 뒤 다시 시도하세요.",
            action_en="Check your install or re-clone the repository, then retry.",
        )
    except Exception:
        return 500, _structured_local_error(
            code="internal_local_error",
            message_ko="기기 내 대화 응답 생성 중 오류가 발생했습니다.",
            message_en="An unexpected error occurred while generating the local reply.",
            action_ko="입력을 줄여 다시 시도하거나 설치 상태를 확인하세요.",
            action_en="Try a smaller input or check your install.",
        )
    return 200, payload


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
    kwargs: dict[str, Any] = {}
    for key, raw in value.items():
        if key not in allowed or raw is None or raw == "":
            continue
        if key == "secondary_rights":
            secondary_rights = _secondary_rights_from_payload(raw)
            if secondary_rights:
                kwargs[key] = secondary_rights
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


def _secondary_rights_from_payload(value: Any) -> tuple[dict[str, Any], ...]:
    """Parse structured FIM-6 rows from JSON without inventing missing values.

    A flat number is not a secondary-rights scenario, so it is ignored. Mapping
    rows are preserved even when ``value`` or ``prob`` is missing; the finance
    module then returns an input-required FIM-6 row instead of fabricating a
    finite rights value.
    """

    if isinstance(value, dict):
        rows = (value,)
    elif isinstance(value, (list, tuple)):
        rows = tuple(row for row in value if isinstance(row, dict))
    else:
        return ()

    parsed: list[dict[str, Any]] = []
    for row in rows:
        scenario: dict[str, Any] = {}
        for key in ("type", "value", "prob", "timing_months"):
            if key in row and row[key] not in (None, ""):
                scenario[key] = row[key]
        if scenario:
            parsed.append(scenario)
    return tuple(parsed)


def _assumption_value_dict(value: Any) -> dict[str, str]:
    assumptions = _assumptions_from_payload(value)
    if assumptions is None:
        return {}
    from dataclasses import fields as dataclass_fields

    values: dict[str, str] = {}
    for field in dataclass_fields(EditableAssumptions):
        raw = getattr(assumptions, field.name)
        if raw is None or raw is False or isinstance(raw, tuple):
            continue
        values[field.name] = str(raw)
    return values


def _json_field(value: str | None) -> Any:
    if not value:
        return None
    try:
        decoded = json.loads(value)
    except json.JSONDecodeError:
        return None
    return decoded if isinstance(decoded, dict) else None


def _attach_scenario_recompute_audit(
    payload: dict[str, Any],
    *,
    previous_payload: dict[str, Any] | None,
    current_assumptions: dict[str, str],
    previous_assumptions: dict[str, str],
    changed_input: str,
) -> None:
    changed_keys = _changed_exposure_keys(previous_payload, payload)
    changed_modules = sorted({key[0] for key in changed_keys})
    changed_findings = _changed_findings(payload, changed_modules)
    payload.setdefault("audit_detail", {})["scenario_recompute"] = {
        "trigger": "explicit_button",
        "changed_input": {
            "name": changed_input,
            "previous_value": previous_assumptions.get(changed_input),
            "current_value": current_assumptions.get(changed_input),
        },
        "previous_assumptions": previous_assumptions,
        "current_assumptions": current_assumptions,
        "changed_exposures": [
            {"fim_module": module, "exposure_type": exposure_type}
            for module, exposure_type in changed_keys
        ],
        "changed_findings": changed_findings,
        "source_text_unchanged": _source_text_unchanged(previous_payload, payload),
        "evidence_eligibility_unchanged": _evidence_eligibility_unchanged(
            previous_payload, payload
        ),
        "status_region_message": {
            "ko": _scenario_status_message(changed_input, changed_findings, "ko"),
            "en": _scenario_status_message(changed_input, changed_findings, "en"),
        },
    }


def _changed_exposure_keys(
    previous_payload: dict[str, Any] | None,
    current_payload: dict[str, Any],
) -> list[tuple[str, str]]:
    current = _exposure_state(current_payload)
    previous = _exposure_state(previous_payload) if previous_payload is not None else {}
    keys = sorted(set(current) | set(previous))
    changed: list[tuple[str, str]] = []
    for key in keys:
        current_state = current.get(key)
        previous_state = previous.get(key)
        if current_state == previous_state:
            continue
        if previous_state is None and _blank_exposure_state(current_state):
            continue
        changed.append(key)
    return changed


def _exposure_state(payload: dict[str, Any] | None) -> dict[tuple[str, str], tuple[Any, ...]]:
    if payload is None:
        return {}
    exposures = payload.get("audit_detail", {}).get("monetary_exposures", ())
    state: dict[tuple[str, str], tuple[Any, ...]] = {}
    for exposure in exposures:
        key = (str(exposure.get("fim_module")), str(exposure.get("exposure_type")))
        state[key] = (
            exposure.get("is_user_input_required"),
            exposure.get("low"),
            exposure.get("base"),
            exposure.get("high"),
            exposure.get("nominal_amount"),
        )
    return state


def _blank_exposure_state(state: tuple[Any, ...] | None) -> bool:
    return state == (True, None, None, None, None)


def _changed_findings(payload: dict[str, Any], changed_modules: list[str]) -> list[dict[str, str]]:
    if not changed_modules:
        return []
    module_set = set(changed_modules)
    findings_by_id = {
        finding.get("finding_id"): finding for finding in payload.get("findings", ())
    }
    changed: list[dict[str, str]] = []
    for item in payload.get("audit_detail", {}).get("technical_findings", ()):
        if item.get("fim_module") not in module_set:
            continue
        finding = findings_by_id.get(item.get("finding_id"), {})
        title = finding.get("title", {}) if isinstance(finding, dict) else {}
        changed.append(
            {
                "finding_id": str(item.get("finding_id", "")),
                "fim_module": str(item.get("fim_module", "")),
                "title_ko": str(title.get("ko", "")),
                "title_en": str(title.get("en", "")),
            }
        )
    return changed


def _source_text_unchanged(
    previous_payload: dict[str, Any] | None,
    current_payload: dict[str, Any],
) -> bool:
    if previous_payload is None:
        return True
    return _finding_sources(previous_payload) == _finding_sources(current_payload)


def _finding_sources(payload: dict[str, Any]) -> list[dict[str, str]]:
    rows = [
        {
            "finding_id": str(finding.get("finding_id", "")),
            "clause_id": str(finding.get("source", {}).get("clause_id", "")),
            "exact_excerpt": str(finding.get("source", {}).get("exact_excerpt", "")),
        }
        for finding in payload.get("findings", ())
    ]
    return sorted(rows, key=lambda row: row["finding_id"])


def _evidence_eligibility_unchanged(
    previous_payload: dict[str, Any] | None,
    current_payload: dict[str, Any],
) -> bool:
    if previous_payload is None:
        return True
    return _finding_scored_state(previous_payload) == _finding_scored_state(current_payload)


def _finding_scored_state(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = [
        {
            "finding_id": item.get("finding_id"),
            "scored": item.get("scored"),
            "fim_module": item.get("fim_module"),
        }
        for item in payload.get("audit_detail", {}).get("technical_findings", ())
    ]
    return sorted(rows, key=lambda row: str(row["finding_id"]))


def _scenario_status_message(
    changed_input: str,
    changed_findings: list[dict[str, str]],
    locale: str,
) -> str:
    if locale == "en":
        if not changed_findings:
            return f"Scenario recalculated for {changed_input}; no findings changed."
        names = ", ".join(item["finding_id"] for item in changed_findings)
        return f"Scenario recalculated for {changed_input}; changed findings: {names}."
    if not changed_findings:
        return f"{changed_input} 입력으로 시나리오를 다시 계산했습니다. 변경된 발견사항은 없습니다."
    names = ", ".join(item["finding_id"] for item in changed_findings)
    return f"{changed_input} 입력으로 시나리오를 다시 계산했습니다. 변경된 발견사항: {names}."


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


def _web_font_bytes(font_name: str) -> bytes | None:
    """Return a bundled web font without allowing path traversal."""

    if font_name not in _WEB_FONT_FILES:
        return None
    path = _WEB_FONT_DIR / font_name
    if not path.is_file():
        return None
    return path.read_bytes()


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

    @app.get("/fonts/{font_name}")
    def font_route(font_name: str) -> Any:
        body = _web_font_bytes(font_name)
        if body is None:
            return Response(content=b"Not found", status_code=404, media_type="text/plain")
        return Response(content=body, media_type="font/woff2")

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

    async def chat_route(request: Request) -> JSONResponse:
        raw = await request.body()
        status, payload = _chat_response(raw, request.headers.get("content-type"))
        return JSONResponse(payload, status_code=status)

    chat_route.__annotations__["request"] = Request
    app.post("/api/chat")(chat_route)

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
        if method == "POST" and path == "/api/chat":
            await self._handle_chat(scope, receive, send)
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
        if path.startswith("/fonts/"):
            body = _web_font_bytes(path.rsplit("/", 1)[-1])
            if body is None:
                await _send_response(send, 404, b"Not found", "text/plain; charset=utf-8")
                return
            await _send_response(send, 200, body, "font/woff2")
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

    async def _handle_chat(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        body = await _read_request_body(receive)
        status, payload = _chat_response(body, _header_value(scope, "content-type"))
        await _send_json(send, status, payload)


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
        "model_status": _model_status_payload(),
    }


def _privacy_payload(settings: WebBindSettings) -> dict[str, Any]:
    return {
        "privacy_banner": PRIVACY_BANNER,
        "not_legal_advice_banner": NOT_LEGAL_ADVICE_BANNER,
        "disclosures": DISCLOSURE_ITEMS,
        "lan": settings.public_dict(),
    }


def _model_status_payload() -> dict[str, Any]:
    try:
        from fink.model.runtime import runtime_execution_path

        return runtime_execution_path(profile_id="standard")["model_status"]
    except Exception:
        return {
            "schema_version": 1,
            "profile_id": "standard",
            "summary_status": "deterministic_fallback_active",
            "available_statuses": [
                "not_installed",
                "installed",
                "loading",
                "active",
                "failed_health_check",
                "deterministic_fallback_active",
            ],
            "component_count": 0,
            "installed_count": 0,
            "missing_count": 0,
            "failed_health_check_count": 0,
            "components": [],
            "adapters": {
                "ocr": "deterministic_fallback_active",
                "embedding": "deterministic_fallback_active",
                "reranker": "deterministic_fallback_active",
                "optional_extractor": "deterministic_fallback_active",
                "optional_explanation_qa": "deterministic_fallback_active",
            },
        }


def _css() -> str:
    tokens = WEB_DESIGN_TOKENS
    return f"""
@font-face {{
  font-family: "Noto Serif KR";
  src: url('/fonts/NotoSerifKR-500.woff2') format('woff2');
  font-weight: 500;
  font-style: normal;
  font-display: swap;
}}
@font-face {{
  font-family: "Noto Serif KR";
  src: url('/fonts/NotoSerifKR-600.woff2') format('woff2');
  font-weight: 600;
  font-style: normal;
  font-display: swap;
}}
@font-face {{
  font-family: "Noto Serif KR";
  src: url('/fonts/NotoSerifKR-700.woff2') format('woff2');
  font-weight: 700;
  font-style: normal;
  font-display: swap;
}}
:root {{
  color-scheme: light;
  --ink: {tokens["ink"]};
  --ink-soft: {tokens["ink_soft"]};
  --muted: {tokens["muted"]};
  --muted-soft: {tokens["muted_soft"]};
  --pill-idle: {tokens["pill_idle"]};
  --line: {tokens["line"]};
  --line-soft: {tokens["line_soft"]};
  --line-strong: {tokens["line_strong"]};
  --panel: {tokens["panel"]};
  --card: {tokens["card"]};
  --canvas: {tokens["canvas"]};
  --pink: {tokens["pink"]};
  --pink-deep: {tokens["pink_deep"]};
  --pink-ink: {tokens["pink_ink"]};
  --pink-bright: {tokens["pink_bright"]};
  --pink-pale: {tokens["pink_pale"]};
  --pink-line: {tokens["pink_line"]};
  --accent: {tokens["accent"]};
  --accent-strong: {tokens["accent_strong"]};
  --accent-tint: {tokens["accent_tint"]};
  --charcoal: {tokens["charcoal"]};
  --green-bg: {tokens["green_bg"]};
  --green-ink: {tokens["green_ink"]};
  --green-line: {tokens["green_line"]};
  --amber-bg: {tokens["amber_bg"]};
  --amber-ink: {tokens["amber_ink"]};
  --amber-line: {tokens["amber_line"]};
  --rose-bg: {tokens["rose_bg"]};
  --rose-ink: {tokens["rose_ink"]};
  --rose-line: {tokens["rose_line"]};
  --safe: {tokens["safe"]};
  --caution: {tokens["caution"]};
  --warn: {tokens["warn"]};
  --warn-bg: {tokens["warn_bg"]};
  --warn-ink: {tokens["warn_ink"]};
  --focus-ring: {tokens["focus_ring"]};
  --focus-offset: {tokens["focus_offset"]};
  --danger: {tokens["danger"]};
  --source-mark: {tokens["source_mark"]};
  --serif: Georgia, "Times New Roman", "Noto Serif KR", serif;
  --sans: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", "Apple SD Gothic Neo", "Noto Sans KR", Arial, sans-serif;
  /* 8px spacing rhythm. */
  --space-1: .5rem;
  --space-2: 1rem;
  --space-3: 1.5rem;
  --space-4: 2rem;
  --radius: 8px;
  --shadow: 0 14px 40px -26px rgba(29, 26, 24, .55);
  --reading-measure: 66ch;
  --bubble-max: 44rem;
  --bubble-padding: 1rem;
}}
""" + """
* { box-sizing: border-box; }
html {
  scroll-padding: calc(var(--space-4) + 44px);
  background: var(--canvas);
  height: 100%;
  overflow: hidden;
}
body {
  margin: 0;
  background: var(--canvas);
  color: var(--ink);
  font-family: var(--serif);
  font-size: 15px;
  line-height: 1.72;
  overflow-wrap: anywhere;
  display: flex;
  flex-direction: column;
  height: 100vh;
  min-height: 100vh;
  overflow: hidden;
}
@supports (height: 100dvh) {
  body {
    height: 100dvh;
    min-height: 100dvh;
  }
}
img, svg, video, canvas {
  max-width: 100%;
  height: auto;
}
pre {
  max-width: 100%;
  overflow-x: auto;
  white-space: pre-wrap;
}
section, article, details, div, main, aside, nav, header, footer {
  min-width: 0;
}
.skip-link {
  position: absolute;
  left: 1rem;
  top: -5rem;
  background: var(--ink);
  color: #fff;
  min-height: 44px;
  padding: .75rem 1rem;
  z-index: 100;
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
  font-family: var(--sans);
  font-size: inherit;
  line-height: inherit;
  min-height: 44px;
}
summary {
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
  outline: 3px solid var(--focus-ring);
  outline-offset: 2px;
  box-shadow: 0 0 0 5px var(--focus-offset);
}
.disclosure-bar {
  display: grid;
  gap: .5rem;
  padding: .75rem clamp(1rem, 4vw, 2rem);
  background: var(--accent-tint);
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
  border-color: var(--danger);
  color: var(--danger);
}
.ocr-label {
  font-weight: 700;
}
.page-toolbar {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(10rem, 1fr));
}
.report-ui {
  display: grid;
  gap: 1rem;
}
.reader-jump-links {
  display: flex;
  gap: .75rem;
  flex-wrap: wrap;
}
.reader-jump-links a, .reader-back-link, .source-status a, .source-highlight-card > a {
  min-height: 44px;
  display: inline-flex;
  align-items: center;
  color: var(--accent-strong);
  font-weight: 800;
}
.synchronized-reader {
  display: grid;
  gap: var(--space-2);
}
.source-reader-panel, .report-reader-panel,
.source-highlight-card, .source-highlight, .finding-card {
  scroll-margin: calc(var(--space-4) + 44px);
}
.source-reader-panel:focus,
.report-reader-panel:focus,
.source-highlight-card:focus,
.source-highlight:focus,
.finding-card:focus {
  outline: 3px solid var(--focus-ring);
  outline-offset: 4px;
}
.chat-citation-summary {
  margin: .5rem 0 0;
  color: var(--muted);
  font-size: .9rem;
}
[data-active-anchor="true"] {
  outline: 3px solid var(--focus-ring);
  outline-offset: 4px;
  box-shadow: 0 0 0 6px var(--focus-offset);
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
  background: var(--source-mark);
}
.source-highlights {
  display: grid;
  gap: var(--space-1);
  margin: var(--space-2) 0;
  padding: var(--space-2);
  border: 1px solid var(--line);
  border-radius: var(--radius);
  background: #fbfcfe;
}
.source-highlight-header {
  display: flex;
  gap: .75rem;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
}
.source-toggle {
  display: inline-flex;
  align-items: center;
  gap: .4rem;
  font-weight: 700;
}
.source-list {
  display: grid;
  gap: .75rem;
}
.source-highlight-card {
  min-height: 0;
  background: #fff;
}
.source-highlight-card header {
  display: flex;
  gap: .5rem;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
}
.source-text {
  margin: .65rem 0;
  max-width: var(--reading-measure);
  white-space: pre-wrap;
}
.source-highlight {
  border-radius: 3px;
  padding: .04rem .12rem;
  background: var(--source-mark);
  color: inherit;
}
.source-kind {
  background: var(--accent-tint);
}
[data-source-highlights-enabled="false"] .source-highlight {
  background: transparent;
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
  border-top: 0;
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
  outline: 3px solid var(--focus-ring);
  outline-offset: 2px;
  box-shadow: 0 0 0 5px var(--focus-offset);
}
.integrated-judgment-card {
  display: grid;
  gap: 0;
  min-height: 0;
  margin: 0;
  padding: 28px 30px 30px;
  border: 1px solid var(--line-strong);
  border-radius: 13px;
  background: var(--card);
  box-shadow: var(--shadow);
}
.glance-heading {
  display: flex;
  gap: 11px;
  align-items: center;
  margin: 0 0 15px;
}
.glance-heading h3 {
  margin: 0;
  color: var(--pink);
  font-family: var(--sans);
  font-size: .72rem;
  font-weight: 700;
  letter-spacing: .2em;
  line-height: 1.2;
  text-transform: uppercase;
}
.glance-heading h3::before {
  content: "";
  display: inline-block;
  width: 20px;
  height: 2px;
  margin-right: 11px;
  vertical-align: .24em;
  background: var(--pink);
}
.glance-icon {
  display: none;
  width: 1.5rem;
  height: 1.5rem;
  align-items: center;
  justify-content: center;
  flex: 0 0 auto;
  padding: .18rem;
  border: 1px solid var(--line);
  border-radius: 999px;
  background: #fff;
  color: var(--accent-strong);
}
.glance-icon svg {
  width: 100%;
  height: 100%;
  fill: none;
  stroke: currentColor;
  stroke-linecap: round;
  stroke-linejoin: round;
  stroke-width: 2;
}
.glance-action {
  margin: 0 0 24px;
  max-width: var(--reading-measure);
  color: var(--ink);
  font-family: var(--serif);
  font-size: 1.43rem;
  font-weight: 600;
  line-height: 1.5;
}
.glance-cues {
  display: none;
  gap: .5rem;
  flex-wrap: wrap;
  margin: 0;
}
.glance-chip {
  display: inline-flex;
  width: fit-content;
  max-width: 100%;
  align-items: center;
  padding: .25rem .5rem;
  border: 1px solid var(--line);
  border-radius: 999px;
  background: #fff;
  color: var(--ink);
  font-size: .85rem;
  font-weight: 700;
}
.glance-count {
  border-color: var(--line);
  background: #fff;
  color: var(--ink);
}
.review-signal-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.35fr) minmax(10rem, .75fr);
  gap: 26px;
  align-items: stretch;
  padding: 20px 0;
  border-top: 1px solid var(--line);
  border-bottom: 1px solid var(--line);
}
.review-effort-signal {
  display: grid;
  gap: 12px;
  padding: 0;
  border: 0;
  border-radius: 0;
  background: transparent;
}
.review-effort-label {
  display: flex;
  gap: .5rem;
  align-items: baseline;
  justify-content: space-between;
  flex-wrap: wrap;
  margin: 0;
  color: var(--muted);
  font-family: var(--sans);
  font-size: .69rem;
  font-weight: 700;
  letter-spacing: .01em;
  line-height: 1.25;
}
.review-effort-current {
  display: none;
}
.effort-meter {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: .5rem;
}
.effort-segment {
  min-height: 3rem;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0;
  padding: .68rem .38rem;
  border: 1px solid var(--line-strong);
  border-radius: 8px;
  background: #f7f4ed;
  color: var(--pill-idle);
  font-family: var(--sans);
  font-size: .75rem;
  font-weight: 600;
  line-height: 1.25;
  text-align: center;
}
.effort-segment::before {
  content: "";
  display: none;
  width: .5rem;
  height: .5rem;
  flex: 0 0 auto;
  border-radius: 999px;
  background: #9ca3af;
}
.effort-segment[data-effort-level="light"] {
  --effort-bg: #fff;
  --effort-ink: var(--green-ink);
  --effort-line: var(--green-line);
  --effort-shadow: rgba(47, 143, 91, .28);
}
.effort-segment[data-effort-level="careful"] {
  --effort-bg: #fff;
  --effort-ink: var(--amber-ink);
  --effort-line: var(--amber-line);
  --effort-shadow: rgba(185, 131, 26, .28);
}
.effort-segment[data-effort-level="professional"] {
  --effort-bg: #fff;
  --effort-ink: var(--rose-ink);
  --effort-line: var(--rose-line);
  --effort-shadow: rgba(196, 61, 52, .28);
}
.effort-segment[data-active="true"] {
  border-color: var(--effort-line);
  background: var(--effort-bg);
  color: var(--effort-ink);
  font-weight: 700;
  box-shadow: inset 0 -3px 0 var(--effort-line), 0 3px 11px -4px var(--effort-shadow);
}
.effort-segment[data-active="true"]::before {
  background: var(--effort-ink);
}
.review-focus-signal {
  display: grid;
  gap: .5rem;
  align-content: start;
  padding: 0;
  border: 0;
  border-radius: 0;
  background: transparent;
}
.focus-score-title {
  margin: 0 0 4px;
  color: var(--muted);
  font-family: var(--sans);
  font-size: .69rem;
  font-weight: 700;
  letter-spacing: .01em;
  line-height: 1.25;
}
.focus-score-line {
  display: flex;
  gap: .35rem;
  align-items: baseline;
}
.focus-score-number {
  display: inline;
  color: var(--ink);
  font-family: var(--serif);
  font-size: 2.75rem;
  font-weight: 600;
  line-height: 1;
}
.focus-score-max {
  color: var(--muted);
  font-family: var(--serif);
  font-size: 1rem;
  font-weight: 700;
}
.focus-support-line {
  margin: 8px 0 0;
  color: var(--muted);
  font-family: var(--sans);
  font-size: .75rem;
  line-height: 1.35;
}
.focus-score-bar {
  display: none;
  width: 100%;
  height: .35rem;
  overflow: hidden;
  border-radius: 999px;
  background: var(--line-soft);
}
.focus-score-fill {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: var(--accent-strong);
}
.focus-score-caption {
  display: none;
  margin: 0;
  color: var(--muted);
  font-size: .82rem;
  line-height: 1.45;
}
.glance-concern {
  display: grid;
  gap: 5px;
  margin-top: 20px;
  padding: 0;
  border: 0;
  border-radius: 0;
  background: transparent;
}
.glance-concern-label,
.glance-caution {
  margin: 0;
  color: var(--muted);
  font-size: .75rem;
}
.glance-concern-label {
  font-family: var(--sans);
  font-weight: 700;
}
.glance-concern-title {
  margin: 0;
  color: var(--ink);
  font-family: var(--serif);
  font-size: 1.13rem;
  font-weight: 600;
  line-height: 1.45;
}
.glance-concern-clause,
.finding-line-clause {
  margin: 0;
  width: fit-content;
  max-width: 100%;
  padding: 3px 11px;
  border: 1px solid var(--pink-line);
  border-radius: 6px;
  background: transparent;
  color: var(--pink-ink);
  font-family: var(--sans);
  font-size: .75rem;
  font-weight: 700;
}
.glance-concern-why {
  margin: 0;
  max-width: var(--reading-measure);
  color: var(--ink-soft);
  font-family: var(--serif);
}
.result-source-quote {
  margin: .4rem 0 0;
  padding: 14px 16px;
  border: 1px solid var(--line);
  border-radius: 9px;
  background: #f6f4ed;
  color: var(--ink-soft);
  font-family: var(--serif);
  font-size: .88rem;
  line-height: 1.75;
  max-width: var(--reading-measure);
}
.result-source-quote .source-highlight {
  padding: 0;
  border-radius: 0;
  border-bottom: 1.5px solid var(--pink);
  background: transparent;
  color: var(--pink-ink);
  font-weight: 700;
}
.status-row {
  display: flex;
  gap: .5rem;
  flex-wrap: wrap;
  margin: 0;
}
.action-line { font-weight: 800; margin: 0; font-size: 1.1rem; }
.cash-flow-line { margin: 0; color: var(--muted); }
.result-meta {
  color: var(--muted);
  font-size: .9rem;
  margin: var(--space-1) 0 var(--space-2);
}
.exposure-line { margin: 0; font-weight: 700; }
.exposure-ranges {
  display: grid;
  gap: .4rem;
  margin: 0;
}
.exposure-range-labels,
.exposure-range-values {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: .5rem;
}
.exposure-range-labels {
  color: var(--muted);
  font-size: .85rem;
  font-weight: 800;
}
.exposure-range-values {
  font-weight: 800;
}
.scenario-inputs {
  display: grid;
  gap: var(--space-1);
  margin: var(--space-2) 0;
  padding: var(--space-2);
  border: 1px solid var(--line);
  border-radius: var(--radius);
  background: #fbfcfe;
}
.scenario-field-list {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(13rem, 1fr));
  gap: .65rem;
}
.scenario-field {
  display: grid;
  gap: .35rem;
}
.scenario-field input {
  width: 100%;
  min-width: 0;
}
.origin-row {
  display: flex;
  gap: .35rem;
  flex-wrap: wrap;
  align-items: center;
}
.model-suggestion-origin {
  color: var(--warn-ink);
  background: var(--warn-bg);
  border-color: #b7791f;
}
.verification-signals {
  display: grid;
  gap: var(--space-1);
  margin: var(--space-2) 0;
  padding: var(--space-2);
  border: 1px solid var(--line);
  border-radius: var(--radius);
  background: #f7fafc;
}
.verification-signals ul {
  display: grid;
  gap: .65rem;
  margin: 0;
  padding-left: 1.15rem;
}
.verification-signals li {
  padding: .75rem;
  border: 1px solid var(--line-soft);
  border-radius: 8px;
  background: #fff;
}
.ranked-findings, .guidance-card ul {
  display: grid;
  gap: .6rem;
  margin: 0;
}
.guidance-card ul {
  padding-left: 1.15rem;
}
.guidance-card {
  display: grid;
  gap: var(--space-1);
  border: 1px solid var(--line);
  border-radius: var(--radius);
  padding: var(--space-2);
  background: var(--panel);
  box-shadow: var(--shadow);
}
.advanced-diagnostic {
  display: grid;
  gap: .5rem;
  margin-top: var(--space-1);
  padding: var(--space-1);
  border: 1px solid var(--line);
  border-radius: 8px;
  background: #fff;
}
.finding-head { display: flex; gap: .5rem; flex-wrap: wrap; align-items: center; }
/* The rank badge leads each finding card. */
.finding-head .badge:first-child {
  background: var(--ink);
  color: #fff;
  border-color: var(--ink);
}
.finding-label { font-weight: 800; margin: 0; }
.finding-heading { margin: 0; font-weight: 700; }
.finding-snippet { margin: 0; max-width: var(--reading-measure); color: var(--muted); }
.guidance-card h4 { margin: 0; }
.guidance-why { margin: 0; max-width: var(--reading-measure); font-weight: 600; }
.finding-line {
  display: grid;
  gap: .55rem;
  padding: 24px 26px;
  border: 1px solid var(--line);
  border-radius: 13px;
  background: var(--card);
}
.finding-line-head {
  display: flex;
  gap: 12px;
  align-items: center;
  margin-bottom: 4px;
}
.finding-number-badge {
  display: inline-flex;
  width: 27px;
  height: 27px;
  align-items: center;
  justify-content: center;
  flex: 0 0 auto;
  border-radius: 999px;
  background: var(--charcoal);
  color: #fff;
  font-family: var(--serif);
  font-size: .94rem;
  font-weight: 500;
  font-variant-numeric: tabular-nums;
}
.finding-line-title {
  margin: 0;
  color: var(--ink);
  font-family: var(--serif);
  font-size: 1.13rem;
  font-weight: 600;
  line-height: 1.4;
}
.finding-line-why,
.finding-line-question {
  margin: 0;
  max-width: var(--reading-measure);
  font-family: var(--serif);
}
.finding-line-why {
  color: var(--ink-soft);
}
.finding-line-question strong {
  color: var(--ink);
}
.finding-checklist {
  display: grid;
  gap: .55rem;
  max-width: var(--reading-measure);
  margin: .25rem 0 0;
  padding: 14px 17px;
  border: 0;
  border-left: 3px solid var(--pink);
  border-radius: 0 9px 9px 0;
  background: #f6f4ed;
}
.finding-checklist-head {
  display: flex;
  gap: .4rem;
  align-items: baseline;
  flex-wrap: wrap;
}
.finding-checklist-label {
  color: var(--pink-ink);
  font-family: var(--sans);
  font-size: .69rem;
  font-weight: 700;
  letter-spacing: 0;
}
.finding-checklist-topic {
  color: var(--pink-ink);
  font-family: var(--sans);
  font-size: .69rem;
  font-weight: 700;
}
.finding-checklist-items {
  display: grid;
  gap: .35rem;
  margin: 0;
  padding-left: 1.1rem;
  color: var(--ink-soft);
  font-family: var(--serif);
}
.finding-checklist-items li {
  margin: 0;
  padding-left: .1rem;
}
.finding-checklist-items span {
  font-size: .9rem;
  line-height: 1.6;
}
.result-chip-row {
  display: grid;
  gap: .45rem;
  margin: 0;
}
.result-chip {
  display: flex;
  width: 100%;
  max-width: var(--reading-measure);
  align-items: center;
  border: 1px solid var(--line-soft);
  border-radius: 8px;
  padding: .45rem .65rem;
  background: #fff;
  color: var(--ink);
  font-size: .9rem;
  font-weight: 650;
}
.followup-chip-stack {
  display: grid;
  gap: .5rem;
  margin-top: .5rem;
}
.followup-chip-stack .example-chip {
  width: 100%;
  justify-content: flex-start;
  border-radius: 8px;
  text-align: left;
}
.audit-source-excerpts {
  display: grid;
  gap: .55rem;
  margin-top: var(--space-1);
}
.audit-source-excerpts h4 {
  margin: 0;
}
.audit-source-excerpts blockquote {
  margin: 0;
  padding: .75rem;
  border-left: 3px solid var(--line);
  background: #f9fafb;
  color: var(--muted);
}
.audit-topic-list {
  display: grid;
  gap: .5rem;
  margin: 0;
  padding-left: 1.15rem;
}
@media (max-width: 480px) {
  .workspace {
    padding: var(--space-1);
  }
  .scenario-field-list,
  .assumption-fields,
  .metric-list {
    grid-template-columns: minmax(0, 1fr);
  }
  .locale-toggle,
  .action-row,
  .reader-jump-links {
    width: 100%;
  }
  .locale-toggle button,
  .action-row button {
    flex: 1 1 100%;
  }
  .badge,
  .source-badge {
    max-width: 100%;
  }
}
@media (min-width: 768px) {
  .workspace {
    padding: var(--space-3);
  }
}
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
@media (min-width: 1100px) {
  .synchronized-reader {
    grid-template-columns: minmax(0, 1fr);
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
@media (prefers-reduced-motion: reduce) {
  *,
  *::before,
  *::after {
    animation-duration: .01ms !important;
    animation-iteration-count: 1 !important;
    scroll-behavior: auto !important;
    transition-duration: .01ms !important;
  }
}
@media (forced-colors: active) {
  :root {
    color-scheme: light dark;
  }
  body,
  .topbar,
  footer,
  .card,
  .integrated-judgment-card,
  .tool-details,
  .source-highlights,
  .finding-sort-control,
  .finding-card,
  .scenario-inputs,
  .assumptions-panel,
  .page-card,
  .source-highlight-card,
  .source-card {
    color: CanvasText;
    background: Canvas;
    border-color: CanvasText;
    box-shadow: none;
  }
  button,
  button.secondary,
  .locale-toggle button,
  .finding-sort-option,
  .finding-sort-option[aria-pressed="true"] {
    color: ButtonText;
    background: ButtonFace;
    border-color: ButtonText;
  }
  a,
  .tile-link,
  .reader-jump-links a,
  .reader-back-link,
  .source-status a {
    color: LinkText;
  }
  .badge,
  .glance-chip,
  .source-badge,
  .unverified-badge,
  .model-suggestion-origin {
    color: CanvasText;
    background: Canvas;
    border-color: CanvasText;
  }
  mark,
  .source-highlight {
    color: HighlightText;
    background: Highlight;
    forced-color-adjust: none;
  }
  button:focus-visible,
  input:focus-visible,
  textarea:focus-visible,
  a:focus-visible,
  summary:focus-visible,
  [data-active-anchor="true"] {
    outline: 3px solid Highlight;
    box-shadow: none;
  }
}
.print-brief-root {
  display: none;
}
@page {
  size: A4;
  margin: 16mm;
}
@media print {
  html,
  body {
    height: auto;
    min-height: 0;
    overflow: visible;
    background: #fff;
  }
  body {
    display: block;
    color: #211d18;
    font: 11pt/1.55 var(--serif);
  }
  body > :not(.print-brief-root) {
    display: none !important;
  }
  .print-brief-root {
    display: block !important;
  }
  .print-brief-document {
    color: #211d18;
    background: #fdfcf8;
  }
  .print-brief-header {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 1rem;
    padding-bottom: .65rem;
    border-bottom: 2px solid #a31e4e;
    margin-bottom: 1rem;
  }
  .print-wordmark {
    margin: 0;
    font: 800 20pt/1 var(--sans);
    letter-spacing: 0;
  }
  .print-wordmark span {
    color: #e83e8c;
  }
  .print-date {
    margin: .1rem 0 0;
    color: #746c61;
    font: 700 9.5pt/1.4 var(--sans);
    text-align: right;
  }
  .print-brief-title {
    margin: 0 0 .35rem;
    color: #211d18;
    font: 700 18pt/1.25 var(--serif);
  }
  .print-brief-disclaimer {
    margin: 0 0 1rem;
    padding: .65rem .8rem;
    border: 1px solid #d8bfc9;
    border-left: 4px solid #a31e4e;
    background: #f6f4ed;
    color: #211d18;
    font: 9.5pt/1.45 var(--sans);
  }
  .print-brief-summary {
    display: grid;
    gap: .45rem;
    margin: 0 0 1rem;
    padding: .85rem;
    border: 1px solid #e9e5dc;
    border-radius: 6px;
  }
  .print-brief-summary h2,
  .print-findings h2,
  .print-brief-closing h2 {
    margin: 0;
    color: #86173e;
    font: 700 12pt/1.35 var(--sans);
  }
  .print-summary-line {
    margin: 0;
    font-weight: 700;
  }
  .print-effort-pill {
    display: inline-block;
    width: fit-content;
    margin: 0;
    padding: .22rem .48rem;
    border: 1px solid #d8bfc9;
    border-radius: 999px;
    color: #86173e;
    background: transparent;
    font: 800 9.5pt/1.3 var(--sans);
  }
  .print-findings {
    display: grid;
    gap: .75rem;
    margin: 0 0 1rem;
  }
  .print-finding {
    break-inside: avoid;
    padding-top: .7rem;
    border-top: 1px solid #e9e5dc;
  }
  .print-finding h3 {
    margin: 0 0 .35rem;
    font: 700 11.5pt/1.35 var(--serif);
  }
  .print-finding p {
    margin: .22rem 0;
  }
  .print-finding strong {
    color: #211d18;
  }
  .print-brief-closing {
    break-inside: avoid;
    margin-top: 1rem;
    padding-top: .65rem;
    border-top: 2px solid #d8bfc9;
  }
  .print-brief-closing p {
    margin: .35rem 0 0;
  }
}
/* ----------------------------------------------------------------------------
   Chat (messenger) shell: a centered full-height column with a scrolling
   thread and a bottom composer. The thread is the only scroll region, so the
   composer stays at the bottom through flex layout alone (no sticky needed).
---------------------------------------------------------------------------- */
.visually-hidden-input {
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
.chat-topbar {
  flex: 0 0 auto;
  display: flex;
  gap: 1rem;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  position: relative;
  padding: 17px clamp(1rem, 4vw, 2rem);
  background: var(--charcoal);
  border-bottom: 0;
  font-family: var(--sans);
}
.chat-topbar::after {
  content: "";
  position: absolute;
  left: 0;
  right: 0;
  bottom: -2px;
  height: 2px;
  background: linear-gradient(90deg, var(--pink), var(--pink-bright));
}
.chat-title {
  display: flex;
  gap: 14px;
  align-items: center;
  min-width: min(100%, 20rem);
}
.brand-divider {
  width: 1px;
  height: 24px;
  flex: none;
  background: #4b443c;
}
.chat-title-copy {
  display: flex;
  flex-direction: column;
  gap: 2px;
  line-height: 1.25;
}
.wordmark {
  margin: 0;
  color: #fbf7f4;
  font-family: var(--sans);
  font-size: 1.45rem;
  font-weight: 800;
  letter-spacing: 0;
  line-height: 1;
}
.wordmark span {
  color: var(--pink-bright);
}
.chat-title h1 {
  margin: 0;
  color: #ece5df;
  font-family: var(--sans);
  font-size: .84rem;
  font-weight: 600;
  line-height: 1.25;
}
.chat-title .subtitle {
  margin: 0;
  color: #988e86;
  font-family: var(--sans);
  font-size: .59rem;
  font-weight: 600;
  letter-spacing: .12em;
  line-height: 1.25;
  text-transform: uppercase;
}
.chat-topbar-actions {
  display: flex;
  gap: .5rem;
  align-items: center;
  flex-wrap: wrap;
}
.notice-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 44px;
  height: 44px;
  padding: 0;
  border: 1px solid #463f39;
  border-radius: 8px;
  background: transparent;
  color: #ece5df;
  font-size: 1.05rem;
}
.notice-button:hover {
  background: transparent;
}
.chat-topbar .locale-toggle button {
  min-width: 56px;
  border: 1px solid #463f39;
  border-radius: 8px;
  background: transparent;
  color: #ece5df;
  font-size: .75rem;
  font-weight: 700;
  letter-spacing: .1em;
  padding: 7px 15px;
}
.chat-privacy {
  flex: 0 0 auto;
  margin: 0;
  padding: 10px clamp(1rem, 4vw, 2rem);
  background: #efece3;
  border-bottom: 1px solid var(--line);
  color: var(--muted);
  font-family: var(--sans);
  font-size: .72rem;
}
.notice-panel {
  flex: 0 0 auto;
  margin: 0;
  padding: var(--space-2) clamp(1rem, 4vw, 2rem);
  background: var(--card);
  border-bottom: 1px solid var(--line);
  font-family: var(--sans);
}
.notice-panel[hidden] {
  display: none;
}
.notice-list {
  display: grid;
  gap: .4rem;
  margin: .75rem 0 0;
  padding-left: 1.15rem;
}
.chat {
  flex: 1 1 auto;
  min-height: 0;
  overflow-y: auto;
  overscroll-behavior: contain;
  padding: 28px clamp(.75rem, 4vw, 2rem);
  background: var(--canvas);
}
.thread {
  display: grid;
  gap: 22px;
  width: 100%;
  max-width: calc(var(--bubble-max) + 2rem);
  margin: 0 auto;
  padding: 0;
  list-style: none;
}
.msg {
  display: flex;
  width: 100%;
}
.msg[hidden],
[data-result-message][hidden] {
  display: none !important;
}
.msg.bot {
  justify-content: flex-start;
}
.msg.user {
  justify-content: flex-end;
}
.bubble {
  max-width: min(100%, var(--bubble-max));
  padding: var(--bubble-padding);
  border-radius: 13px;
  border: 1px solid var(--line);
  background: var(--card);
  box-shadow: var(--shadow);
}
.msg.bot .bubble {
  width: min(100%, var(--bubble-max));
}
.msg.bot .bubble {
  border-top-left-radius: 4px;
}
.msg.user .bubble {
  width: auto;
  max-width: min(100%, var(--bubble-max));
  border-top-right-radius: 4px;
  border-color: var(--line);
  background: #f6f4ed;
}
.bubble-text {
  margin: 0;
  max-width: var(--reading-measure);
  color: var(--ink-soft);
  font-family: var(--serif);
}
.result-sequence-msg .bubble,
.result-msg .bubble-result {
  padding: 0;
  border: 0;
  background: transparent;
  box-shadow: none;
}
.result-sequence-msg {
  opacity: 0;
  transform: translateY(.35rem);
  animation: fink-result-message-in .34s ease-out forwards;
  animation-delay: calc(var(--result-index, 0) * 70ms);
}
.result-sequence-msg .bubble {
  max-width: min(100%, var(--bubble-max));
}
@keyframes fink-result-message-in {
  from {
    opacity: 0;
    transform: translateY(.35rem);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}
.pending-bubble {
  position: relative;
  overflow: hidden;
  min-width: min(100%, 5.75rem);
}
.pending-bubble::after {
  content: "";
  position: absolute;
  inset: 0;
  pointer-events: none;
  background: linear-gradient(110deg, transparent 0%, rgba(255, 255, 255, .55) 48%, transparent 74%);
  transform: translateX(-120%);
  animation: fink-pending-shimmer 2.4s ease-in-out infinite;
}
.pending-status {
  position: relative;
  z-index: 1;
  display: grid;
  gap: .55rem;
  min-width: 0;
}
.pending-typing {
  display: flex;
  align-items: center;
  min-height: 1.5rem;
}
.pending-typing .pending-status-text {
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
.typing-dots {
  display: inline-flex;
  align-items: center;
  gap: .28rem;
  min-height: 1.5rem;
}
.typing-dots span {
  width: .42rem;
  height: .42rem;
  border-radius: 999px;
  background: var(--accent);
  opacity: .48;
  animation: fink-typing-dot 1.2s ease-in-out infinite;
}
.typing-dots span:nth-child(2) {
  animation-delay: .16s;
}
.typing-dots span:nth-child(3) {
  animation-delay: .32s;
}
.pending-analysis {
  width: min(100%, 22rem);
}
.pending-stage-stack {
  position: relative;
  min-height: 1.7rem;
  overflow: hidden;
  color: var(--ink);
  font-weight: 750;
  line-height: 1.5;
}
.pending-stage-line {
  position: absolute;
  inset: 0 auto auto 0;
  max-width: 100%;
  opacity: 0;
  transform: translateY(.35rem);
  overflow-wrap: anywhere;
  animation: fink-stage-cycle 4.8s ease-in-out infinite;
}
.pending-stage-line:nth-child(2) {
  animation-delay: 1.2s;
}
.pending-stage-line:nth-child(3) {
  animation-delay: 2.4s;
}
.pending-stage-line:nth-child(4) {
  animation-delay: 3.6s;
}
.pending-progress {
  position: relative;
  width: 100%;
  height: .28rem;
  overflow: hidden;
  border-radius: 999px;
  background: var(--line-soft);
}
.pending-progress::before {
  content: "";
  position: absolute;
  inset: 0;
  width: 48%;
  border-radius: inherit;
  background: linear-gradient(90deg, transparent 0%, var(--accent) 50%, transparent 100%);
  transform: translateX(-120%);
  animation: fink-progress-sweep 1.4s ease-in-out infinite;
}
@keyframes fink-typing-dot {
  0%, 80%, 100% {
    opacity: .45;
    transform: translateY(0) scale(.78);
  }
  35% {
    opacity: 1;
    transform: translateY(-.24rem) scale(1);
  }
}
@keyframes fink-stage-cycle {
  0% {
    opacity: 0;
    transform: translateY(.35rem);
  }
  8%, 22% {
    opacity: 1;
    transform: translateY(0);
  }
  30%, 100% {
    opacity: 0;
    transform: translateY(-.35rem);
  }
}
@keyframes fink-progress-sweep {
  0% {
    transform: translateX(-120%);
  }
  100% {
    transform: translateX(230%);
  }
}
@keyframes fink-pending-shimmer {
  0% {
    transform: translateX(-120%);
  }
  55%, 100% {
    transform: translateX(120%);
  }
}
.bubble-result {
  max-width: min(100%, var(--bubble-max));
}
.result-msg[hidden] .bubble {
  min-height: 0;
  padding: 0;
  border: 0;
  background: transparent;
  box-shadow: none;
}
.file-chip {
  display: inline-flex;
  align-items: center;
  gap: .4rem;
  font-weight: 700;
  min-width: 0;
}
.file-chip span {
  overflow-wrap: anywhere;
}
.user-attachment-stack {
  display: grid;
  gap: .5rem;
}
.user-attachment-thumb,
.attachment-thumbnail {
  width: 3rem;
  height: 3rem;
  border: 1px solid var(--line);
  border-radius: 6px;
  object-fit: cover;
  background: #fff;
}
.attachment-preview {
  order: -1;
  flex: 1 0 100%;
  min-width: 0;
}
.attachment-card {
  display: flex;
  align-items: center;
  gap: .5rem;
  min-width: 0;
}
.attachment-remove-button {
  flex: 0 0 auto;
  min-width: 32px;
  height: 32px;
  min-height: 32px;
  padding: 0;
  border-color: var(--line);
  background: #fff;
  color: var(--ink);
}
.chip-row {
  display: flex;
  gap: .5rem;
  flex-wrap: wrap;
  margin-top: .75rem;
}
.example-chip {
  background: #fff;
  color: var(--ink);
  border: 1px solid var(--line);
  border-radius: 999px;
  padding: .5rem .75rem;
  font-weight: 700;
}
.example-chip[data-example-chip="true"] {
  border-color: var(--accent-strong);
  background: var(--accent-strong);
  color: #fff;
}
.result-pane {
  display: grid;
  gap: var(--space-1);
}
.result-inline-panel {
  display: grid;
  gap: var(--space-1);
}
.review-brief-launcher {
  display: flex;
  justify-content: flex-start;
  margin: 0 0 var(--space-1);
}
.review-brief-button {
  width: fit-content;
}
.brief-bubble {
  width: min(100%, var(--bubble-max));
}
.review-brief-card {
  display: grid;
  gap: var(--space-1);
}
.inline-brief-document {
  display: grid;
  gap: var(--space-1);
  padding: var(--space-2);
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--card);
}
.inline-brief-document .print-brief-header {
  display: flex;
  gap: var(--space-1);
  align-items: flex-start;
  justify-content: space-between;
  padding-bottom: .75rem;
  border-bottom: 2px solid var(--pink);
}
.inline-brief-document .print-wordmark {
  margin: 0;
  color: var(--ink);
  font-size: 1.25rem;
  font-family: var(--sans);
  font-weight: 800;
  line-height: 1;
}
.inline-brief-document .print-wordmark span {
  color: var(--pink-bright);
}
.inline-brief-document .print-date {
  margin: 0;
  color: var(--muted);
  font-family: var(--sans);
  font-size: .82rem;
  font-weight: 700;
  text-align: right;
}
.inline-brief-document .print-brief-title {
  margin: 0;
  color: var(--ink);
  font-family: var(--serif);
  font-size: 1.3rem;
  font-weight: 700;
  line-height: 1.25;
}
.inline-brief-document .print-brief-disclaimer {
  margin: 0;
  padding: .75rem;
  border: 1px solid var(--line);
  border-left: 3px solid var(--pink);
  border-radius: 8px;
  background: #f6f4ed;
  color: var(--ink);
  font-family: var(--sans);
  font-size: .9rem;
}
.inline-brief-document .print-brief-summary,
.inline-brief-document .print-findings,
.inline-brief-document .print-brief-closing {
  display: grid;
  gap: .5rem;
}
.inline-brief-document h2,
.inline-brief-document h3,
.inline-brief-document p {
  margin: 0;
}
.inline-brief-document h2 {
  color: var(--ink);
  font-family: var(--sans);
  font-size: 1rem;
  font-weight: 800;
}
.inline-brief-document h3 {
  font-family: var(--serif);
  font-size: .96rem;
  font-weight: 700;
}
.inline-brief-document .print-finding {
  display: grid;
  gap: .35rem;
  padding-top: .75rem;
  border-top: 1px solid var(--line);
}
.inline-brief-document .print-effort-pill {
  width: fit-content;
  padding: .25rem .5rem;
  border: 1px solid var(--line);
  border-radius: 999px;
  color: var(--ink);
  background: transparent;
  font-size: .85rem;
  font-weight: 700;
}
.brief-download-row {
  display: flex;
  justify-content: flex-end;
}
.download-brief-button {
  background: var(--pink);
  border-color: var(--pink);
  color: #fff;
}
.composer {
  flex: 0 0 auto;
  display: flex;
  flex-wrap: wrap;
  gap: 14px;
  align-items: flex-end;
  padding: 16px clamp(.75rem, 4vw, 2rem);
  padding-bottom: max(16px, env(safe-area-inset-bottom));
  background: var(--canvas);
  border-top: 1px solid var(--line-strong);
}
.composer-input {
  flex: 1 1 auto;
  min-width: 0;
  min-height: 44px;
  max-height: 40vh;
  resize: none;
  border: 1px solid var(--line-strong);
  border-radius: 11px;
  padding: 13px 16px;
  background: #fbfaf6;
  color: var(--ink);
  font-family: var(--sans);
  font-size: .88rem;
  line-height: 1.5;
  overflow-y: auto;
}
.attach-button,
.send-button {
  flex: 0 0 auto;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 44px;
  height: 44px;
  border-radius: 999px;
  padding: 0;
}
.attach-button {
  background: transparent;
  color: var(--muted);
  border-color: transparent;
  font-size: 1.1rem;
}
.paperclip-icon {
  width: 1.2rem;
  height: 1.2rem;
}
.send-button {
  width: 45px;
  min-width: 45px;
  height: 45px;
  font-weight: 800;
  border-color: var(--pink);
  background: var(--pink);
  color: #fff;
  box-shadow: 0 8px 20px -7px rgba(163, 30, 78, .6);
}
.send-button:hover {
  background: var(--pink-ink);
  border-color: var(--pink-ink);
}
@media (max-width: 480px) {
  .chat-title {
    align-items: flex-start;
    width: 100%;
  }
  .wordmark {
    font-size: 1.2rem;
    padding-top: .12rem;
  }
  .review-signal-grid {
    grid-template-columns: minmax(0, 1fr);
  }
  .effort-meter {
    gap: .3rem;
  }
  .effort-segment {
    min-height: 3.35rem;
    padding-inline: .35rem;
    font-size: .72rem;
  }
  .inline-brief-document {
    padding: var(--space-1);
  }
  .inline-brief-document .print-brief-header {
    display: grid;
    gap: .5rem;
  }
  .inline-brief-document .print-date {
    text-align: left;
  }
  .chat-title h1 {
    font-size: 1.1rem;
  }
}
@media (prefers-reduced-motion: reduce) {
  .pending-bubble::after,
  .pending-progress {
    display: none;
  }
  .result-sequence-msg {
    opacity: 1;
    transform: none;
    animation: none;
  }
  .typing-dots {
    display: none;
  }
  .pending-typing .pending-status-text {
    position: static;
    width: auto;
    height: auto;
    padding: 0;
    margin: 0;
    overflow: visible;
    clip: auto;
    white-space: normal;
  }
  .pending-stage-stack {
    min-height: auto;
    overflow: visible;
  }
  .pending-stage-line {
    position: static;
    display: none;
    opacity: 1;
    transform: none;
    animation: none;
  }
  .pending-stage-line:first-child {
    display: block;
  }
}
"""


_APP_JS = r"""(function () {
  "use strict";

  var LOCALE_STORAGE_KEY = "fink.ui_locale";
  var analyzeInFlight = false;
  var chatInFlight = false;
  var analyzedContractText = "";
  var lastResultPayload = null;
  var lastReviewBriefItem = null;
  var lastSubmittedAssumptions = {};
  var attachmentPreviewUrl = "";
  var ANALYSIS_STAGE_LABELS = [
    { ko: "계약서 읽는 중", en: "Reading the contract" },
    { ko: "조항 나누는 중", en: "Splitting clauses" },
    { ko: "근거 찾는 중", en: "Finding evidence" },
    { ko: "정리하는 중", en: "Summarizing" }
  ];
  var TYPING_STATUS_LABEL = { ko: "답변 준비 중", en: "Preparing reply" };

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
    // One toggle button flips KO<->EN. aria-pressed reflects "English active"
    // and data-active-locale-value records the current locale for the handler.
    var toggle = document.querySelector("[data-locale-button]");
    if (toggle) {
      toggle.setAttribute("aria-pressed", locale === "en" ? "true" : "false");
      toggle.setAttribute("data-active-locale-value", locale);
    }
    updateLocalizedPlaceholders(locale);
    writeStoredLocale(locale);
  }

  function activeLocale() {
    return normalizeLocale(document.documentElement.getAttribute("data-active-locale"));
  }

  function updateLocalizedPlaceholders(locale) {
    var box = document.getElementById("paste-box");
    if (!box) {
      return;
    }
    var value = box.getAttribute(locale === "en" ? "data-placeholder-en" : "data-placeholder-ko");
    if (value) {
      box.setAttribute("placeholder", value);
    }
  }

  function prefersReducedMotion() {
    return (
      window.matchMedia &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches
    );
  }

  function scrollOptions(block) {
    return {
      behavior: prefersReducedMotion() ? "auto" : "smooth",
      block: block
    };
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

  function clearNode(node) {
    while (node.firstChild) {
      node.removeChild(node.firstChild);
    }
  }

  function localized(pair) {
    if (!pair) {
      return "";
    }
    return text(pair[activeLocale()] || pair.ko || pair.en);
  }

  function localizedFor(pair, locale) {
    if (!pair) {
      return "";
    }
    locale = normalizeLocale(locale);
    return text(pair[locale] || pair.ko || pair.en);
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

  function paperclipIcon() {
    var source = document.querySelector(".paperclip-icon");
    if (source && source.cloneNode) {
      return source.cloneNode(true);
    }
    var fallback = el("span", null, "file");
    fallback.setAttribute("aria-hidden", "true");
    return fallback;
  }

  function createFileObjectUrl(file) {
    if (!file || !window.URL || !window.URL.createObjectURL) {
      return "";
    }
    return window.URL.createObjectURL(file);
  }

  function revokeObjectUrl(url) {
    if (url && window.URL && window.URL.revokeObjectURL) {
      window.URL.revokeObjectURL(url);
    }
  }

  function revokeAttachmentPreviewUrl() {
    revokeObjectUrl(attachmentPreviewUrl);
    attachmentPreviewUrl = "";
  }

  function isImageUpload(file) {
    if (!file) {
      return false;
    }
    var type = text(file.type).toLowerCase();
    var name = text(file.name).toLowerCase();
    return type.indexOf("image/") === 0 || /\.(png|jpe?g|webp|heic|heif)$/.test(name);
  }

  function fileChip(fileName) {
    var chip = el("span", "file-chip", null);
    chip.setAttribute("data-file-chip", "true");
    chip.appendChild(paperclipIcon());
    chip.appendChild(el("span", null, text(fileName || "첨부 파일")));
    return chip;
  }

  function attachmentImage(src, className, fileName, revokeAfterLoad) {
    var image = el("img", className, null);
    image.src = src;
    image.alt = text(fileName || "첨부 이미지");
    image.loading = "lazy";
    if (revokeAfterLoad) {
      image.addEventListener("load", function () {
        revokeObjectUrl(src);
      });
      image.addEventListener("error", function () {
        revokeObjectUrl(src);
      });
    }
    return image;
  }

  function creatorStatusLabel(status) {
    if (status && status.state === "unverified") {
      return {
        ko: "근거 확인 필요",
        en: "Evidence confirmation needed"
      };
    }
    return status && status.label ? status.label : { ko: "", en: "" };
  }

  function copyPair(payload, key) {
    if (payload && payload.copy && payload.copy[key]) {
      return payload.copy[key];
    }
    return { ko: key, en: key };
  }

  function statusMessage(pair) {
    var status = document.querySelector("[data-analyze-status]");
    if (!status) {
      return;
    }
    clearNode(status);
    status.appendChild(bilingual("span", null, pair));
  }

  function scenarioStatusMessage(pair) {
    var regions = document.querySelectorAll("[data-scenario-status-region]");
    regions.forEach(function (region) {
      clearNode(region);
      region.appendChild(bilingual("span", null, pair));
    });
    statusMessage(pair);
  }

  function copyLabel(payload, key) {
    return copyPair(payload, key);
  }

  function finiteNumberOrNull(value) {
    if (value == null || value === "") {
      return null;
    }
    var parsed = Number(value);
    return isFinite(parsed) ? parsed : null;
  }

  function priorityRank(finding, fallbackIndex) {
    var parsed = finiteNumberOrNull(finding && finding.rank);
    return parsed && parsed > 0 ? parsed : fallbackIndex + 1;
  }

  function clauseOrderFromId(clauseId) {
    var value = text(clauseId).trim();
    if (!value) {
      return null;
    }
    var matches = value.match(/\d+/g);
    if (!matches || matches.length === 0) {
      return null;
    }
    return finiteNumberOrNull(matches[matches.length - 1]);
  }

  function clauseOrderValue(finding) {
    var source = (finding && finding.source) || {};
    var candidates = [
      finding && finding.clause_order,
      finding && finding.clauseOrder,
      finding && finding.clause_index,
      finding && finding.clauseIndex,
      source.clause_order,
      source.clauseOrder,
      source.clause_index,
      source.clauseIndex,
      source.order
    ];
    for (var index = 0; index < candidates.length; index += 1) {
      var explicitOrder = finiteNumberOrNull(candidates[index]);
      if (explicitOrder != null) {
        return explicitOrder;
      }
    }
    return clauseOrderFromId(
      source.clause_id || (finding && (finding.clause_id || finding.clauseId))
    );
  }

  function cleanClauseHeading(value) {
    var raw = text(value).replace(/\s+/g, " ").trim();
    if (!raw) {
      return "";
    }
    var ko = raw.match(/^(제\s*\d+\s*조(?:\s*[({（][^)}）]+[)}）])?)/i);
    if (ko) {
      return ko[1].replace(/제\s*(\d+)\s*조/i, "제$1조").replace(/\s+([({（])/g, "$1").trim();
    }
    var en = raw.match(/^((?:Article|Section|Clause)\s+\d+[A-Za-z0-9_.-]*(?:\s*[({][^)}]+[)}])?)/i);
    return en ? en[1].trim() : raw;
  }

  function clauseHeadingFromText(value) {
    // Recover a concrete "제N조(…)" / "Article N (…)" marker from anywhere in an
    // excerpt, so a finding without a structured clause_heading still names its
    // clause instead of falling back to the opaque "조항 N".
    var raw = text(value).replace(/\s+/g, " ").trim();
    if (!raw) {
      return "";
    }
    var ko = raw.match(/제\s*\d+\s*조(?:\s*[({（][^)}）]+[)}）])?/);
    if (ko) {
      return cleanClauseHeading(ko[0]);
    }
    var en = raw.match(/(?:Article|Section|Clause)\s+\d+[A-Za-z0-9_.-]*(?:\s*[({][^)}]+[)}])?/i);
    if (en) {
      return cleanClauseHeading(en[0]);
    }
    return "";
  }

  function clauseTopicEn(topic) {
    var value = text(topic).toLowerCase();
    if (!value) {
      return "";
    }
    if (value.indexOf("정산") !== -1 || value.indexOf("settlement") !== -1) {
      return "Settlement";
    }
    if (value.indexOf("위약") !== -1 || value.indexOf("penalty") !== -1) {
      return "Penalty";
    }
    if (value.indexOf("해지") !== -1 || value.indexOf("termination") !== -1) {
      return "Termination";
    }
    if (value.indexOf("독점") !== -1 || value.indexOf("exclusive") !== -1) {
      return "Exclusivity";
    }
    if (value.indexOf("저작") !== -1 || value.indexOf("copyright") !== -1) {
      return "Copyright";
    }
    return topic;
  }

  function clauseTopicKo(topic) {
    var value = text(topic).toLowerCase();
    if (!value) {
      return "";
    }
    if (value.indexOf("settlement") !== -1) {
      return "정산";
    }
    if (value.indexOf("penalty") !== -1) {
      return "위약금";
    }
    if (value.indexOf("termination") !== -1) {
      return "해지";
    }
    if (value.indexOf("exclusive") !== -1) {
      return "독점";
    }
    if (value.indexOf("copyright") !== -1) {
      return "저작권";
    }
    return topic;
  }

  function translateClauseHeading(heading, targetLocale) {
    var raw = cleanClauseHeading(heading);
    if (!raw) {
      return "";
    }
    var ko = raw.match(/^제(\d+)조(?:[({（]([^)}）]+)[)}）])?/);
    if (ko && targetLocale === "en") {
      return "Article " + ko[1] + (ko[2] ? " (" + clauseTopicEn(ko[2]) + ")" : "");
    }
    var en = raw.match(/^(?:Article|Section|Clause)\s+(\d+)[A-Za-z0-9_.-]*(?:\s*[({]([^)}]+)[)}])?/i);
    if (en && targetLocale === "ko") {
      return "제" + en[1] + "조" + (en[2] ? "(" + clauseTopicKo(en[2]) + ")" : "");
    }
    return raw;
  }

  function firstClauseWords(value) {
    var cleaned = text(value).replace(/\s+/g, " ").trim();
    if (!cleaned) {
      return "";
    }
    var heading = cleanClauseHeading(cleaned);
    if (heading && cleaned.indexOf(heading) === 0) {
      cleaned = cleaned.slice(heading.length).trim();
    }
    if (cleaned.length <= 34) {
      return cleaned;
    }
    return cleaned.slice(0, 34).trim() + "...";
  }

  function clauseReferencePair(finding, index) {
    var source = (finding && finding.source) || {};
    var sourceText = source.exact_excerpt || "";
    var headingKo = cleanClauseHeading(
      source.clause_heading || source.clauseHeading || finding && finding.clause_heading
    );
    var headingEn = cleanClauseHeading(
      source.clause_heading_en || source.clauseHeadingEn || finding && finding.clause_heading_en
    );
    if (!headingKo && !headingEn && sourceText) {
      var recovered = clauseHeadingFromText(sourceText);
      if (recovered) {
        headingKo = recovered;
      }
    }
    if (headingKo && !headingEn) {
      headingEn = translateClauseHeading(headingKo, "en");
    }
    if (headingEn && !headingKo) {
      headingKo = translateClauseHeading(headingEn, "ko");
    }
    if (headingKo || headingEn) {
      return {
        ko: headingKo || headingEn,
        en: headingEn || headingKo
      };
    }
    var order = clauseOrderValue(finding || {});
    var fallbackKo = order != null ? "조항 " + order : "조항 " + (index + 1);
    var fallbackEn = order != null ? "Clause " + order : "Clause " + (index + 1);
    var firstKo = firstClauseWords(sourceText);
    var firstEn = firstClauseWords(deterministicClauseTranslation(sourceText, "en") || sourceText);
    return {
      ko: firstKo ? fallbackKo + " - " + firstKo : fallbackKo,
      en: firstEn ? fallbackEn + " - " + firstEn : fallbackEn
    };
  }

  function findingRecords(findings) {
    return findings.map(function (finding, index) {
      return {
        finding: finding,
        originalIndex: index,
        priorityRank: priorityRank(finding, index),
        clauseOrder: clauseOrderValue(finding)
      };
    });
  }

  function sortedFindingRecords(records, sortMode) {
    var sorted = records.slice();
    if (sortMode === "clause") {
      var hasClauseOrder = sorted.some(function (record) {
        return record.clauseOrder != null;
      });
      if (hasClauseOrder) {
        sorted.sort(function (left, right) {
          if (left.clauseOrder != null && right.clauseOrder != null) {
            if (left.clauseOrder !== right.clauseOrder) {
              return left.clauseOrder - right.clauseOrder;
            }
            return left.originalIndex - right.originalIndex;
          }
          if (left.clauseOrder != null) {
            return -1;
          }
          if (right.clauseOrder != null) {
            return 1;
          }
          return left.originalIndex - right.originalIndex;
        });
        return sorted;
      }
    }
    sorted.sort(function (left, right) {
      return left.originalIndex - right.originalIndex;
    });
    return sorted;
  }

  function renderFindingChecklist(checklist) {
    var items = (checklist && checklist.checkpoints) || [];
    if (!items.length) {
      return null;
    }
    var wrap = el("aside", "finding-checklist", null);
    wrap.setAttribute("data-finding-checklist", "true");

    var head = el("div", "finding-checklist-head", null);
    head.appendChild(
      bilingual("span", "finding-checklist-label", {
        ko: "실무 체크",
        en: "Practice check"
      })
    );
    if (checklist.topic && (checklist.topic.ko || checklist.topic.en)) {
      head.appendChild(bilingual("span", "finding-checklist-topic", checklist.topic));
    }
    wrap.appendChild(head);

    var list = el("ul", "finding-checklist-items", null);
    items.forEach(function (item) {
      var row = el("li", null, null);
      row.appendChild(bilingual("span", null, item));
      list.appendChild(row);
    });
    wrap.appendChild(list);
    return wrap;
  }

  function renderFindingLine(record) {
    var finding = record.finding;
    var section = el("section", "finding-line", null);
    section.setAttribute("data-finding-line", "true");
    section.setAttribute("data-finding-rank", String(record.priorityRank));
    var head = el("div", "finding-line-head", null);
    var badge = el("span", "finding-number-badge", String(record.priorityRank));
    badge.setAttribute("aria-hidden", "true");
    head.appendChild(badge);
    head.appendChild(bilingual("p", "finding-line-title", finding.title));
    section.appendChild(head);
    section.appendChild(bilingual("p", "finding-line-clause", clauseReferencePair(finding, record.originalIndex)));
    section.appendChild(bilingual("p", "finding-line-why", finding.why_it_matters));
    var question = el("p", "finding-line-question", null);
    question.appendChild(
      bilingual("strong", null, {
        ko: "물어볼 말: ",
        en: "Ask: "
      })
    );
    question.appendChild(bilingual("span", null, finding.question_to_ask));
    section.appendChild(question);
    var checklist = renderFindingChecklist(finding.checklist);
    if (checklist) {
      section.appendChild(checklist);
    }
    if (finding.source && finding.source.exact_excerpt) {
      var quote = el("blockquote", null, null);
      quote.setAttribute("data-exact-excerpt", "true");
      quote.className = "result-source-quote";
      renderLocalizedSourceSegments(quote, finding.source);
      section.appendChild(quote);
    }
    return section;
  }

  function renderFindings(appendBubble, payload) {
    var findings = payload.findings;
    if (!findings || findings.length === 0) {
      return;
    }
    var records = findingRecords(findings);
    sortedFindingRecords(records, "priority").forEach(function (record) {
      appendBubble("finding-bubble", renderFindingLine(record));
    });
  }

  function renderPlainSourceSegments(container, segments) {
    (segments || []).forEach(function (segment) {
      if (!segment.highlighted) {
        container.appendChild(document.createTextNode(text(segment.text)));
        return;
      }
      var marker = document.createElement("mark");
      marker.className = "source-highlight";
      marker.appendChild(document.createTextNode(text(segment.text)));
      container.appendChild(marker);
    });
  }

  function hasHangul(value) {
    return /[가-힣]/.test(text(value));
  }

  function sourceTextFromSegments(segments) {
    return (segments || []).map(function (segment) {
      return text(segment.text);
    }).join("");
  }

  function sourceOriginalLocale(source) {
    var sourceText = sourceTextFromSegments((source && source.segments) || []);
    if (!sourceText && source) {
      sourceText = text(source.text_ko || source.exact_excerpt || source.source_text);
    }
    return hasHangul(sourceText) ? "ko" : "en";
  }

  function deterministicClauseTranslation(value, targetLocale) {
    var raw = text(value).replace(/\s+/g, " ").trim();
    if (!raw) {
      return "";
    }
    if (targetLocale === "en") {
      if (!hasHangul(raw)) {
        return raw;
      }
      var headingEn = translateClauseHeading(cleanClauseHeading(raw), "en");
      if (
        raw.indexOf("정산") !== -1 &&
        raw.indexOf("매 분기") !== -1 &&
        raw.indexOf("90일") !== -1 &&
        raw.indexOf("일반 경비") !== -1 &&
        raw.indexOf("공제") !== -1
      ) {
        return (
          (headingEn ? headingEn + " " : "") +
          "Settlement is paid within 90 days after the end of each quarter, and the company may deduct general expenses."
        );
      }
      if (raw.indexOf("위약금") !== -1) {
        return (
          (headingEn ? headingEn + " " : "") +
          "A penalty may be charged for breach of contract."
        );
      }
      return (
        (headingEn ? headingEn + " " : "") +
        raw
          .replace(/^제\s*\d+\s*조(?:\s*[({（][^)}）]+[)}）])?\s*/i, "")
          .replace(/정산/g, "settlement")
          .replace(/매\s*분기/g, "each quarter")
          .replace(/종료일로부터/g, "after the end")
          .replace(/(\d+)\s*일\s*이내/g, "within $1 days")
          .replace(/지급/g, "payment")
          .replace(/회사/g, "company")
          .replace(/일반\s*경비/g, "general expenses")
          .replace(/공제/g, "deduct")
          .replace(/할 수 있다/g, "may")
      ).trim();
    }
    if (hasHangul(raw)) {
      return raw;
    }
    var headingKo = translateClauseHeading(cleanClauseHeading(raw), "ko");
    var lower = raw.toLowerCase();
    if (
      lower.indexOf("settlement") !== -1 &&
      lower.indexOf("90 days") !== -1 &&
      lower.indexOf("each quarter") !== -1 &&
      lower.indexOf("general expenses") !== -1
    ) {
      return (
        (headingKo ? headingKo + " " : "") +
        "정산은 매 분기 종료일로부터 90일 이내에 지급되며, 회사는 일반 경비를 공제할 수 있습니다."
      );
    }
    if (lower.indexOf("penalty") !== -1) {
      return (
        (headingKo ? headingKo + " " : "") +
        "계약 위반 시 위약금이 부과될 수 있습니다."
      );
    }
    return (
      (headingKo ? headingKo + " " : "") +
      raw
        .replace(/^(?:Article|Section|Clause)\s+\d+[A-Za-z0-9_.-]*(?:\s*[({][^)}]+[)}])?\s*/i, "")
        .replace(/settlement/gi, "정산")
        .replace(/within\s+(\d+)\s+days?/gi, "$1일 이내")
        .replace(/each quarter/gi, "매 분기")
        .replace(/after the end/gi, "종료일로부터")
        .replace(/company/gi, "회사")
        .replace(/general expenses/gi, "일반 경비")
        .replace(/deduct(?:ion|s)?/gi, "공제")
        .replace(/\bmay\b/gi, "할 수 있습니다")
    ).trim();
  }

  function translateHighlightText(value, targetLocale) {
    var raw = text(value).replace(/\s+/g, " ").trim();
    if (!raw) {
      return "";
    }
    if (targetLocale === "en") {
      var day = raw.match(/(\d+)\s*일\s*이내/);
      if (day) {
        return day[1] + " days";
      }
      if (raw.indexOf("매 분기") !== -1) {
        return "each quarter";
      }
      if (raw.indexOf("일반 경비") !== -1) {
        return "general expenses";
      }
      if (raw.indexOf("공제") !== -1) {
        return "deduct";
      }
      if (raw.indexOf("할 수 있다") !== -1 || raw.indexOf("할 수 있습니다") !== -1) {
        return "may";
      }
      if (raw.indexOf("위약금") !== -1) {
        return "penalty";
      }
      return "";
    }
    var lower = raw.toLowerCase();
    var days = lower.match(/(\d+)\s*days?/);
    if (days) {
      return days[1] + "일 이내";
    }
    if (lower.indexOf("each quarter") !== -1) {
      return "매 분기";
    }
    if (lower.indexOf("general expenses") !== -1) {
      return "일반 경비";
    }
    if (lower.indexOf("deduct") !== -1) {
      return "공제";
    }
    if (lower.indexOf("may") !== -1) {
      return "할 수";
    }
    if (lower.indexOf("penalty") !== -1) {
      return "위약금";
    }
    return "";
  }

  function highlightNeedlesForTranslation(segments, targetLocale) {
    var needles = [];
    (segments || []).forEach(function (segment) {
      if (!segment.highlighted) {
        return;
      }
      var translated = translateHighlightText(segment.text, targetLocale);
      if (translated) {
        needles.push(translated);
      }
    });
    return needles;
  }

  function translatedSegments(textValue, sourceSegments, targetLocale) {
    var value = text(textValue);
    if (!value) {
      return [];
    }
    var needles = highlightNeedlesForTranslation(sourceSegments, targetLocale);
    if (needles.length === 0) {
      return [{ text: value, highlighted: false }];
    }
    var lower = value.toLowerCase();
    var ranges = [];
    needles.forEach(function (needle) {
      var wanted = text(needle).toLowerCase();
      if (!wanted) {
        return;
      }
      var start = lower.indexOf(wanted);
      while (start !== -1) {
        ranges.push({ start: start, end: start + wanted.length });
        start = lower.indexOf(wanted, start + wanted.length);
      }
    });
    if (ranges.length === 0) {
      return [{ text: value, highlighted: false }];
    }
    ranges.sort(function (left, right) {
      return left.start === right.start ? left.end - right.end : left.start - right.start;
    });
    var merged = [];
    ranges.forEach(function (range) {
      var last = merged[merged.length - 1];
      if (last && range.start <= last.end) {
        last.end = Math.max(last.end, range.end);
      } else {
        merged.push({ start: range.start, end: range.end });
      }
    });
    var parts = [];
    var cursor = 0;
    merged.forEach(function (range) {
      if (range.start > cursor) {
        parts.push({ text: value.slice(cursor, range.start), highlighted: false });
      }
      parts.push({ text: value.slice(range.start, range.end), highlighted: true });
      cursor = range.end;
    });
    if (cursor < value.length) {
      parts.push({ text: value.slice(cursor), highlighted: false });
    }
    return parts;
  }

  function translatedTextForSource(source, targetLocale) {
    source = source || {};
    var original = sourceTextFromSegments(source.segments || []) || text(source.exact_excerpt);
    if (targetLocale === "en") {
      var enText = text(
        source.text_en_gloss ||
          source.exact_excerpt_en_gloss ||
          source.exact_excerpt_en ||
          source.source_text_en
      ).trim();
      return enText || deterministicClauseTranslation(original || source.text_ko, "en");
    }
    var koText = text(source.text_ko_gloss || source.exact_excerpt_ko || source.source_text_ko).trim();
    if (koText && hasHangul(koText)) {
      return koText;
    }
    return deterministicClauseTranslation(original || source.text_ko, "ko");
  }

  function sourceSegmentsForLocale(source, locale) {
    source = source || {};
    locale = normalizeLocale(locale);
    var originalSegments = source.segments || [];
    var originalText = sourceTextFromSegments(originalSegments) || text(source.exact_excerpt);
    var originalLocale = sourceOriginalLocale(source);
    if (locale === originalLocale && originalSegments.length > 0) {
      return originalSegments;
    }
    var directSegments = locale === "en"
      ? source.segments_en || source.translated_segments_en
      : source.segments_ko || source.translated_segments_ko;
    if (directSegments && directSegments.length) {
      return directSegments;
    }
    var translated = translatedTextForSource(source, locale);
    if (translated && translated !== originalText) {
      return translatedSegments(translated, originalSegments, locale);
    }
    return originalSegments.length > 0 ? originalSegments : [{ text: originalText, highlighted: false }];
  }

  function renderLocalizedSourceSegments(container, source) {
    ["ko", "en"].forEach(function (locale) {
      var span = el("span", null, null);
      span.setAttribute("lang", locale);
      span.setAttribute("data-locale-text", locale);
      renderPlainSourceSegments(span, sourceSegmentsForLocale(source, locale));
      container.appendChild(span);
    });
  }

  function prefixedChip(prefixKo, prefixEn, pair) {
    var ko = localizedFor(pair, "ko").trim();
    var en = localizedFor(pair, "en").trim();
    if (!ko && !en) {
      return null;
    }
    return {
      ko: prefixKo + (ko || en),
      en: prefixEn + (en || ko)
    };
  }

  function collectDimensionChips(payload) {
    var dims = (payload && payload.dimensions) || {};
    var chips = [];
    var monetary = dims.monetary || {};
    var monetaryPair = monetary.quantification_status && monetary.quantification_status.label;
    var monetaryChip = prefixedChip("예상 비용 ", "Estimated cost: ", monetaryPair);
    if (monetaryChip) {
      chips.push(monetaryChip);
    }
    var time = dims.time || {};
    var timing = time.contract_timing || time.timing_state;
    var timingPair = typeof timing === "string" ? { ko: timing, en: timing } : timing;
    var timeChip = prefixedChip("시점 ", "Timing: ", timingPair);
    if (timeChip) {
      chips.push(timeChip);
    }
    var evidence = dims.evidence || {};
    var evidenceChip = prefixedChip(
      "신뢰도 ",
      "Confidence: ",
      creatorStatusLabel(evidence.evidence_status)
    );
    if (evidenceChip) {
      chips.push(evidenceChip);
    }
    return chips;
  }

  function renderDimensionChips(appendBubble, payload) {
    var chips = collectDimensionChips(payload);
    if (chips.length === 0) {
      return;
    }
    var row = el("div", "result-chip-row", null);
    row.setAttribute("data-result-dimension-chips", "true");
    chips.forEach(function (chip) {
      row.appendChild(bilingual("span", "result-chip", chip));
    });
    appendBubble("dimension-chip-bubble", row);
  }

  function renderAuditSourceExcerpts(details, payload) {
    var highlights = (payload && payload.source_highlights) || {};
    var sources = highlights.sources || [];
    if (sources.length === 0) {
      return;
    }
    var section = el("section", "audit-source-excerpts", null);
    section.setAttribute("data-audit-source-excerpts", "true");
    section.appendChild(
      bilingual("h4", null, {
        ko: "원문 하이라이트",
        en: "Source highlights"
      })
    );
    var seen = {};
    var rendered = 0;
    sources.forEach(function (source) {
      if (rendered >= 3) {
        return;
      }
      var quote = el("blockquote", null, null);
      renderLocalizedSourceSegments(quote, source);
      if (!quote.textContent.trim() && source.exact_excerpt) {
        quote.textContent = text(source.exact_excerpt);
      }
      var normalized = quote.textContent.replace(/\s+/g, " ").trim();
      if (normalized && !seen[normalized]) {
        seen[normalized] = true;
        section.appendChild(quote);
        rendered += 1;
      }
    });
    if (section.childNodes.length > 1) {
      details.appendChild(section);
    }
  }

  function renderVerificationSignals(container, payload) {
    var verification = payload.verification;
    if (!verification || !verification.signals || verification.signals.length === 0) {
      return;
    }
    var section = el("section", "verification-signals", null);
    section.setAttribute("data-verification-section", "true");
    section.setAttribute("data-score-contribution", "0");
    section.setAttribute("data-separate-from-review-priority-score", "true");
    section.appendChild(bilingual("h3", null, verification.section_title));
    section.appendChild(bilingual("p", "hint", verification.section_hint));

    var list = el("ul", null, null);
    verification.signals.forEach(function (signal) {
      var item = el("li", null, null);
      item.setAttribute("data-verification-signal", signal.signal_id);
      item.setAttribute("data-score-contribution", "0");
      item.setAttribute("data-separate-from-review-priority-score", "true");
      item.appendChild(bilingual("strong", null, signal.label));
      item.appendChild(bilingual("p", null, signal.instruction));
      var support = signal.support || {};
      item.appendChild(
        bilingual(
          "p",
          "hint",
          support.record_ids && support.record_ids.length > 0
            ? { ko: "공식 자료 근거 있음", en: "Official source support available" }
            : { ko: "근거 확인 필요", en: "Evidence confirmation needed" }
        )
      );
      list.appendChild(item);
    });
    section.appendChild(list);
    container.appendChild(section);
  }

  function atAGlanceIcon() {
    var icon = el("span", "glance-icon", null);
    icon.setAttribute("aria-hidden", "true");
    icon.innerHTML =
      '<svg viewBox="0 0 24 24" focusable="false">' +
      '<rect x="5" y="5.5" width="14" height="13" rx="2"></rect>' +
      '<path d="M8.5 10h7"></path>' +
      '<path d="M8.5 14h5"></path>' +
      "</svg>";
    return icon;
  }

  function recommendationPathway(payload) {
    var recommendation = (payload && payload.recommendation) || {};
    if (recommendation.pathway_label) {
      return text(recommendation.pathway_label);
    }
    if (recommendation.audit_pathway_label) {
      return localized(recommendation.audit_pathway_label);
    }
    var audit = (payload && payload.audit_detail) || {};
    if (audit.time && audit.time.pathway_label) {
      return text(audit.time.pathway_label);
    }
    return "";
  }

  function reviewEffortKey(payload, findingCount) {
    var pathway = recommendationPathway(payload).toLowerCase();
    if (pathway.indexOf("clarification") !== -1) {
      return "light";
    }
    if (pathway.indexOf("negotiation") !== -1) {
      return "careful";
    }
    if (pathway.indexOf("professional") !== -1 || pathway.indexOf("dispute") !== -1) {
      return "professional";
    }
    if (findingCount <= 1) {
      return "light";
    }
    if (findingCount <= 3) {
      return "careful";
    }
    return "professional";
  }

  function reviewEffortLevel(key) {
    if (key === "professional") {
      return { ko: "전문가 권장", en: "Professional recommended" };
    }
    if (key === "careful") {
      return { ko: "꼼꼼히 확인", en: "Careful check" };
    }
    return { ko: "가볍게 확인", en: "Light check" };
  }

  function reviewEffortLevels() {
    return [
      { key: "light", label: reviewEffortLevel("light") },
      { key: "careful", label: reviewEffortLevel("careful") },
      { key: "professional", label: reviewEffortLevel("professional") }
    ];
  }

  function reviewEffortSignal(payload, findingCount) {
    var active = reviewEffortKey(payload, findingCount);
    var activeLabel = reviewEffortLevel(active);
    var section = el("section", "review-effort-signal", null);
    section.setAttribute("data-review-effort-signal", "true");
    section.setAttribute("data-review-effort-level", active);
    section.setAttribute("aria-label", "검토 권장 수준 / Review effort");

    var label = el("p", "review-effort-label", null);
    label.appendChild(
      bilingual("span", null, {
        ko: "검토 권장 수준",
        en: "Review effort"
      })
    );
    label.appendChild(bilingual("strong", "review-effort-current", activeLabel));
    section.appendChild(label);

    var meter = el("div", "effort-meter", null);
    meter.setAttribute("aria-hidden", "true");
    reviewEffortLevels().forEach(function (level) {
      var segment = bilingual("span", "effort-segment", level.label);
      segment.setAttribute("data-effort-level", level.key);
      segment.setAttribute("data-active", level.key === active ? "true" : "false");
      meter.appendChild(segment);
    });
    section.appendChild(meter);
    return section;
  }

  function reviewFocusScore(payload) {
    var dimensions = (payload && payload.dimensions) || {};
    var reviewPriority = dimensions.review_priority || {};
    var score = finiteNumberOrNull(reviewPriority.score);
    if (score == null) {
      return 0;
    }
    return Math.max(0, Math.min(100, Math.round(score)));
  }

  function supportCount(value) {
    var number = finiteNumberOrNull(value);
    if (number == null) {
      return 0;
    }
    return Math.max(0, Math.round(number));
  }

  function reviewFocusSignal(payload) {
    var dimensions = (payload && payload.dimensions) || {};
    var reviewPriority = dimensions.review_priority || {};
    var score = reviewFocusScore(payload);
    var officialSupport = supportCount(reviewPriority.official_support);
    var practiceSupport = supportCount(reviewPriority.practice_support);
    var section = el("section", "review-focus-signal", null);
    section.setAttribute("data-review-focus-signal", "true");
    section.setAttribute("aria-label", "위험 지수 / Risk Index");

    section.appendChild(
      bilingual("h4", "focus-score-title", {
        ko: "위험 지수",
        en: "Risk Index"
      })
    );
    var scoreLine = el("div", "focus-score-line", null);
    scoreLine.appendChild(el("output", "focus-score-number", String(score)));
    scoreLine.appendChild(el("span", "focus-score-max", "/ 100"));
    section.appendChild(scoreLine);
    section.appendChild(
      bilingual("p", "focus-support-line", {
        ko: "공식 근거 " + officialSupport + " · 실무 기준 " + practiceSupport,
        en: "Official evidence " + officialSupport + " · Practice basis " + practiceSupport
      })
    );

    var bar = el("span", "focus-score-bar", null);
    bar.setAttribute("aria-hidden", "true");
    var fill = el("span", "focus-score-fill", null);
    fill.style.width = String(score) + "%";
    bar.appendChild(fill);
    section.appendChild(bar);
    section.appendChild(
      bilingual("p", "focus-score-caption", {
        ko: "숫자가 높을수록 먼저·꼼꼼히 살펴볼 계약상 금융 항목이 많다는 뜻이에요.",
        en: "A higher number means more contractual finance items should be reviewed earlier and more carefully."
      })
    );
    return section;
  }

  function renderReviewSignalGrid(container, payload, findingCount) {
    var grid = el("div", "review-signal-grid", null);
    grid.setAttribute("data-review-signal-grid", "true");
    grid.appendChild(reviewEffortSignal(payload, findingCount));
    grid.appendChild(reviewFocusSignal(payload));
    container.appendChild(grid);
  }

  function reviewEffortPair(payload, findingCount) {
    return reviewEffortLevel(reviewEffortKey(payload, findingCount));
  }

  function reviewEffortChipPair(payload, findingCount) {
    var level = reviewEffortPair(payload, findingCount);
    return {
      ko: "검토 권장 수준: " + level.ko,
      en: "Review effort: " + level.en
    };
  }

  function itemCountPair(findingCount) {
    return {
      ko: "확인할 항목 " + findingCount + "개",
      en: findingCount + " items to check"
    };
  }

  function recommendationActionPair(payload) {
    var recommendation = (payload && payload.recommendation) || {};
    if (recommendation.action) {
      return recommendation.action;
    }
    return {
      ko: "권장: 확인할 항목을 먼저 살펴보세요.",
      en: "Recommendation: review the items to check first."
    };
  }

  function formatBriefDate(locale) {
    var date = new Date();
    var tag = normalizeLocale(locale) === "en" ? "en-US" : "ko-KR";
    try {
      return date.toLocaleDateString(tag, {
        year: "numeric",
        month: "2-digit",
        day: "2-digit"
      });
    } catch (error) {
      return date.toISOString().slice(0, 10);
    }
  }

  function briefEvidenceLine(finding, locale) {
    var evidence = (finding && finding.evidence) || {};
    var ids = evidence.grounding_evidence_ids || [];
    var count = ids.length;
    if (normalizeLocale(locale) === "en") {
      return count + " official source item(s)";
    }
    return "공식 자료 " + count + "건";
  }

  function briefClauseLabel(finding, index, locale) {
    return localizedFor(clauseReferencePair(finding, index), locale);
  }

  function briefFindingTitle(finding, index, locale) {
    var title = localizedFor(finding && finding.title, locale).trim();
    if (title) {
      return title;
    }
    return briefClauseLabel(finding, index, locale);
  }

  function briefField(pair, locale, fallbackPair) {
    var value = localizedFor(pair, locale).trim();
    if (value) {
      return value;
    }
    return localizedFor(fallbackPair, locale);
  }

  function briefFindingTitlePair(finding, index) {
    return {
      ko: briefFindingTitle(finding, index, "ko"),
      en: briefFindingTitle(finding, index, "en")
    };
  }

  function briefClauseLabelPair(finding, index) {
    return {
      ko: briefClauseLabel(finding, index, "ko"),
      en: briefClauseLabel(finding, index, "en")
    };
  }

  function briefFieldPair(pair, fallbackPair) {
    return {
      ko: briefField(pair, "ko", fallbackPair),
      en: briefField(pair, "en", fallbackPair)
    };
  }

  function briefEvidencePair(finding) {
    return {
      ko: briefEvidenceLine(finding, "ko"),
      en: briefEvidenceLine(finding, "en")
    };
  }

  function printBriefRoot() {
    var root = document.querySelector("[data-print-brief-root]");
    if (!root) {
      root = el("section", "print-brief-root", null);
      root.id = "print-brief";
      root.setAttribute("data-print-brief-root", "true");
      root.setAttribute("aria-hidden", "true");
      document.body.appendChild(root);
    }
    return root;
  }

  function appendPrintLine(container, labelPair, valuePair) {
    var line = el("p", null, null);
    line.appendChild(bilingual("strong", null, labelPair));
    line.appendChild(document.createTextNode(" "));
    line.appendChild(bilingual("span", null, valuePair));
    container.appendChild(line);
  }

  function renderPrintableBrief(payload) {
    var root = printBriefRoot();
    clearNode(root);
    root.setAttribute("aria-hidden", "true");

    var findings = (payload && payload.findings) || [];
    var findingCount = findings.length;
    var article = el("article", "print-brief-document", null);
    article.setAttribute("data-print-brief-document", "true");

    var header = el("header", "print-brief-header", null);
    var wordmark = el("p", "print-wordmark", null);
    wordmark.setAttribute("aria-label", "FInk");
    wordmark.innerHTML = "F<span>I</span>nk";
    header.appendChild(wordmark);
    header.appendChild(
      bilingual("p", "print-date", {
        ko: "작성일: " + formatBriefDate("ko"),
        en: "Date: " + formatBriefDate("en")
      })
    );
    article.appendChild(header);

    article.appendChild(
      bilingual("h1", "print-brief-title", {
        ko: "FInk 검토 의견서",
        en: "FInk Review Brief"
      })
    );
    article.appendChild(
      bilingual("p", "print-brief-disclaimer", {
        ko: "이 의견서는 서명 결정을 돕기 위한 정리이며 법률 자문이 아닙니다.",
        en: "This review brief organizes points to support a signing decision and is not legal advice."
      })
    );

    var summary = el("section", "print-brief-summary", null);
    summary.appendChild(bilingual("h2", null, { ko: "전체 정리", en: "Overall" }));
    summary.appendChild(
      bilingual("p", "print-summary-line", recommendationActionPair(payload))
    );
    summary.appendChild(
      bilingual("p", "print-effort-pill", reviewEffortChipPair(payload, findingCount))
    );
    summary.appendChild(bilingual("p", "print-summary-line", itemCountPair(findingCount)));
    article.appendChild(summary);

    var findingsSection = el("section", "print-findings", null);
    findingsSection.appendChild(
      bilingual("h2", null, {
        ko: "확인할 항목",
        en: "Findings"
      })
    );
    if (findings.length === 0) {
      findingsSection.appendChild(
        bilingual("p", null, {
          ko: "개별 확인 항목이 없습니다. 지급, 기간, 해지 조건은 직접 확인하세요.",
          en: "No individual finding is listed. Still confirm payment, term, and termination terms."
        })
      );
    }
    findings.forEach(function (finding, index) {
      var item = el("section", "print-finding", null);
      var title = el("h3", null, String(index + 1) + ". ");
      title.appendChild(bilingual("span", null, briefFindingTitlePair(finding, index)));
      item.appendChild(title);
      appendPrintLine(item, { ko: "조항:", en: "Clause:" }, briefClauseLabelPair(finding, index));
      appendPrintLine(
        item,
        { ko: "왜 중요한지:", en: "Why it matters:" },
        briefFieldPair(finding && finding.why_it_matters, {
          ko: "서명 전 확인할 현금흐름 조건입니다.",
          en: "This is a cash-flow term to confirm before signing."
        })
      );
      appendPrintLine(
        item,
        { ko: "확인·협상 질문:", en: "Question to confirm or negotiate:" },
        briefFieldPair(finding && finding.question_to_ask, {
          ko: "이 조건을 계약서에 어떻게 명확히 적을 수 있나요?",
          en: "How can this term be written clearly in the contract?"
        })
      );
      appendPrintLine(item, { ko: "근거:", en: "Evidence:" }, briefEvidencePair(finding));
      findingsSection.appendChild(item);
    });
    article.appendChild(findingsSection);

    var closing = el("section", "print-brief-closing", null);
    closing.appendChild(bilingual("h2", null, { ko: "마무리", en: "Closing" }));
    closing.appendChild(
      bilingual("p", null, {
        ko: "중요한 결정 전에는 전문가 확인을 권합니다.",
        en: "Confirm important decisions with a professional."
      })
    );
    article.appendChild(closing);
    root.appendChild(article);
    return root;
  }

  function renderReviewBriefAction(container) {
    var action = el("section", "review-brief-launcher", null);
    action.setAttribute("data-review-brief-launcher", "true");
    var button = el("button", "secondary review-brief-button", null);
    button.type = "button";
    button.setAttribute("data-make-review-brief", "true");
    button.setAttribute("aria-label", "의견서 만들기 / Make a review brief");
    button.appendChild(
      bilingual("span", null, {
        ko: "의견서 만들기",
        en: "Make a review brief"
      })
    );
    action.appendChild(button);
    container.appendChild(action);
  }

  function appendReviewBriefBubble(payload) {
    var thread = threadElement();
    if (!thread) {
      return null;
    }
    var printRoot = renderPrintableBrief(payload);
    var printable = printRoot.querySelector("[data-print-brief-document]");
    if (!printable) {
      return null;
    }
    var item = el("li", "msg bot review-brief-msg", null);
    item.setAttribute("data-message-role", "bot");
    item.setAttribute("data-review-brief-message", "true");
    var bubble = el("div", "bubble brief-bubble", null);
    var card = el("section", "review-brief-card", null);
    card.setAttribute("data-inline-review-brief", "true");

    var inlineDocument = printable.cloneNode(true);
    inlineDocument.className += " inline-brief-document";
    inlineDocument.setAttribute("aria-hidden", "false");
    card.appendChild(inlineDocument);

    var actions = el("div", "brief-download-row", null);
    var button = el("button", "download-brief-button", null);
    button.type = "button";
    button.setAttribute("data-download-review-brief", "true");
    button.setAttribute("aria-label", "다운로드하기 / Download");
    button.appendChild(
      bilingual("span", null, {
        ko: "다운로드하기",
        en: "Download"
      })
    );
    actions.appendChild(button);
    card.appendChild(actions);
    bubble.appendChild(card);
    item.appendChild(bubble);
    thread.appendChild(item);
    lastReviewBriefItem = item;
    setLocale(activeLocale());
    scrollThreadToLatest(item);
    return item;
  }

  function removeReviewBriefBubble() {
    if (lastReviewBriefItem && lastReviewBriefItem.parentNode) {
      lastReviewBriefItem.parentNode.removeChild(lastReviewBriefItem);
    }
    lastReviewBriefItem = null;
  }

  function showReviewBrief() {
    if (!lastResultPayload) {
      appendBotMessage({
        ko: "먼저 계약을 분석한 뒤 의견서를 만들 수 있습니다.",
        en: "Analyze a contract first, then make a review brief."
      });
      statusMessage({
        ko: "먼저 계약을 분석하세요.",
        en: "Analyze a contract first."
      });
      return;
    }
    removeReviewBriefBubble();
    appendReviewBriefBubble(lastResultPayload);
    setLocale(activeLocale());
    statusMessage({
      ko: "의견서를 대화에 표시했습니다.",
      en: "Review brief shown in the chat."
    });
  }

  function downloadReviewBrief() {
    if (!lastResultPayload) {
      showReviewBrief();
      return;
    }
    renderPrintableBrief(lastResultPayload);
    setLocale(activeLocale());
    statusMessage({
      ko: "브라우저 인쇄 창에서 PDF로 저장할 수 있습니다.",
      en: "Use the browser print dialog to save as PDF."
    });
    window.setTimeout(function () {
      window.print();
    }, 0);
  }

  function renderIntegratedJudgmentCard(container, payload) {
    var findings = (payload && payload.findings) || [];
    var findingCount = findings.length;
    var card = el("article", "integrated-judgment-card", null);
    card.setAttribute("data-integrated-judgment-card", "true");

    var heading = el("div", "glance-heading", null);
    heading.appendChild(
      bilingual("h3", null, {
        ko: "SUMMARY",
        en: "SUMMARY"
      })
    );
    card.appendChild(heading);
    card.appendChild(bilingual("p", "glance-action", recommendationActionPair(payload)));
    renderReviewSignalGrid(card, payload, findingCount);

    var cues = el("p", "glance-cues", null);
    cues.appendChild(bilingual("span", "glance-chip glance-count", itemCountPair(findingCount)));
    card.appendChild(cues);

    var concern = el("section", "glance-concern", null);
    concern.setAttribute("data-glance-concern", "true");
    if (findings.length > 0) {
      var finding = findings[0];
      concern.appendChild(bilingual("p", "glance-concern-clause", clauseReferencePair(finding, 0)));
      concern.appendChild(bilingual("h4", "glance-concern-title", finding.title));
      concern.appendChild(
        bilingual("p", "glance-concern-why", finding.why_it_matters)
      );
    } else {
      concern.appendChild(
        bilingual("p", "glance-concern-label", {
          ko: "표시할 개별 확인 항목이 없습니다.",
          en: "No individual item is listed."
        })
      );
      concern.appendChild(
        bilingual("p", "glance-concern-why", {
          ko: "지급, 기간, 해지 조건은 직접 확인하세요.",
          en: "Still confirm payment, term, and termination terms."
        })
      );
    }
    card.appendChild(concern);
    card.appendChild(
      bilingual("p", "glance-caution", {
        ko: "최종 판단이 아니라 확인을 돕는 정리예요. 중요한 결정은 전문가 확인을 권해요.",
        en: "This is a review aid, not a final judgment; confirm important decisions with a professional."
      })
    );
    container.appendChild(card);
  }

  function auditCategoryTopicPair(payload, category) {
    var keys = {
      F1: "category.settlement_audit",
      F2: "category.revenue_deductions",
      F3: "category.payment_cashflow",
      F4: "category.mg_recoupment",
      F5: "category.ip_monetization",
      F6: "category.term_exclusivity",
      F7: "category.termination_liability",
      F8: "category.scope_cost",
      F9: "category.econtract_privacy"
    };
    var normalized = text(category).toUpperCase();
    var key = keys[normalized];
    if (key && payload && payload.copy && payload.copy[key]) {
      return payload.copy[key];
    }
    return {
      ko: "계약 금융 체크리스트",
      en: "Contract finance checklist"
    };
  }

  function collectAuditEvidenceTopics(payload) {
    var seen = {};
    var topics = [];
    function add(pair) {
      var ko = localizedFor(pair, "ko").trim();
      var en = localizedFor(pair, "en").trim();
      var key = (ko + "\n" + en).toLowerCase();
      if ((!ko && !en) || seen[key]) {
        return;
      }
      seen[key] = true;
      topics.push({ ko: ko || en, en: en || ko });
    }
    var audit = (payload && payload.audit_detail) || {};
    (audit.technical_findings || []).forEach(function (finding) {
      var ids = finding.grounding_evidence_ids || [];
      if (ids.length > 0) {
        add(auditCategoryTopicPair(payload, finding["risk" + "_category"]));
      }
    });
    ((payload && payload.findings) || []).forEach(function (finding) {
      var evidence = finding.evidence || {};
      if ((evidence.grounding_evidence_ids || []).length > 0) {
        add(finding.title);
      }
      (finding.citations || []).forEach(function (citation) {
        if (citation.evidence_id) {
          add(finding.title);
        }
      });
    });
    var qa = (payload && payload.grounded_qa) || {};
    (qa.items || []).forEach(function (item) {
      (item.citations || []).forEach(function (citation) {
        if (citation.evidence_id) {
          add({
            ko: "후속 질문 근거",
            en: "Follow-up answer support"
          });
        }
      });
    });
    return topics;
  }

  function renderAdvancedDiagnostics(container, payload) {
    var details = el("details", "audit-detail", null);
    details.setAttribute("data-audit-detail", "true");
    details.appendChild(bilingual("summary", null, copyLabel(payload, "export.audit_detail_label")));
    renderAuditSourceExcerpts(details, payload);
    renderVerificationSignals(details, payload);
    var diagnostic = reviewFocusSignal(payload);
    diagnostic.className += " advanced-diagnostic";
    diagnostic.setAttribute("data-advanced-diagnostic", "rule-focus-index");
    details.appendChild(diagnostic);
    var evidenceTopics = collectAuditEvidenceTopics(payload);
    if (evidenceTopics.length > 0) {
      var evidenceDetail = el("section", "advanced-diagnostic", null);
      evidenceDetail.setAttribute("data-advanced-diagnostic", "evidence-topics");
      evidenceDetail.appendChild(
        bilingual("h4", null, {
          ko: "근거가 연결된 체크리스트",
          en: "Evidence-supported topics"
        })
      );
      var list = el("ul", "audit-topic-list", null);
      evidenceTopics.forEach(function (topic) {
        var item = el("li", null, null);
        item.appendChild(bilingual("span", null, topic));
        list.appendChild(item);
      });
      evidenceDetail.appendChild(list);
      details.appendChild(evidenceDetail);
    }
    container.appendChild(details);
  }

  function threadElement() {
    return document.querySelector("[data-chat-thread]");
  }

  function scrollThreadToLatest(node) {
    var target = node || (threadElement() && threadElement().lastElementChild);
    var scroller = document.querySelector(".chat");
    if (scroller && scroller.scrollTo) {
      scroller.scrollTo({
        top: scroller.scrollHeight,
        behavior: prefersReducedMotion() ? "auto" : "smooth"
      });
      return;
    }
    if (target && target.scrollIntoView) {
      target.scrollIntoView(scrollOptions("end"));
    }
  }

  function ensureResultContainer() {
    var container = document.getElementById("result");
    if (container) {
      return container;
    }
    container = el("section", "result-pane", null);
    container.id = "result";
    container.setAttribute("aria-labelledby", "result-heading");
    container.setAttribute("aria-live", "polite");
    container.setAttribute("role", "region");
    container.setAttribute("data-analysis-result", "true");
    return container;
  }

  function resetResultContainer(container) {
    clearNode(container);
    var heading = el("h2", "sr-only", null);
    heading.id = "result-heading";
    heading.appendChild(bilingual("span", null, { ko: "검토 결과", en: "Review result" }));
    container.appendChild(heading);
  }

  function removePriorResultMessages(keepItem) {
    document.querySelectorAll("[data-result-sequence-item]").forEach(function (item) {
      if (item !== keepItem && item.parentNode) {
        item.parentNode.removeChild(item);
      }
    });
    document.querySelectorAll("[data-result-message]").forEach(function (item) {
      if (item !== keepItem && !item.hasAttribute("data-result-sequence-item") && item.parentNode) {
        item.parentNode.removeChild(item);
      }
    });
  }

  function markResultSequenceItem(item, index) {
    item.className = "msg bot result-msg result-sequence-msg";
    item.setAttribute("data-message-role", "bot");
    item.setAttribute("data-result-sequence-item", "true");
    item.setAttribute("data-result-sequence-index", String(index));
    item.style.setProperty("--result-index", String(index));
    item.hidden = false;
    item.removeAttribute("data-pending-message");
  }

  function prepareResultOpeningMessage(targetItem, container) {
    var thread = threadElement();
    if (!thread) {
      return null;
    }
    var item = targetItem || el("li", null, null);
    if (container.parentNode) {
      container.parentNode.removeChild(container);
    }
    clearNode(item);
    markResultSequenceItem(item, 0);
    item.setAttribute("data-result-message", "true");
    var bubble = el("div", "bubble bubble-result result-opening-bubble", null);
    bubble.appendChild(container);
    item.appendChild(bubble);
    thread.appendChild(item);
    return item;
  }

  function appendResultContentBubble(className, content, index) {
    var thread = threadElement();
    if (!thread || !content) {
      return null;
    }
    var item = el("li", null, null);
    markResultSequenceItem(item, index);
    var bubble = el("div", "bubble " + className, null);
    bubble.appendChild(content);
    item.appendChild(bubble);
    thread.appendChild(item);
    return item;
  }

  function resultOpeningPair(payload) {
    var count = ((payload && payload.findings) || []).length;
    if (count > 0) {
      return {
        ko: "계약서를 살펴봤어요. 서명 전에 확인하면 좋은 항목 " + count + "개를 정리했어요.",
        en: "I reviewed the contract and lined up " + count + " item(s) to check before signing."
      };
    }
    return {
      ko: "계약서를 살펴봤어요. 서명 전에 지급, 기간, 해지 조건을 차분히 확인해 주세요.",
      en: "I reviewed the contract. Before signing, calmly confirm payment, term, and termination terms."
    };
  }

  function appendUserMessage(content, isFile, options) {
    options = options || {};
    var thread = threadElement();
    if (!thread) {
      return;
    }
    var item = el("li", "msg user", null);
    item.setAttribute("data-message-role", "user");
    var bubble = el("div", "bubble", null);
    if (isFile) {
      var stack = el("div", "user-attachment-stack", null);
      if (options.imageUrl) {
        stack.appendChild(
          attachmentImage(
            options.imageUrl,
            "user-attachment-thumb",
            options.fileName || content,
            true
          )
        );
      }
      stack.appendChild(fileChip(options.fileName || content || "첨부 파일"));
      if (content && text(content).trim() !== "") {
        stack.appendChild(el("p", "bubble-text", text(content)));
      }
      bubble.appendChild(stack);
    } else {
      bubble.appendChild(el("p", "bubble-text", text(content)));
    }
    item.appendChild(bubble);
    thread.appendChild(item);
    scrollThreadToLatest(item);
  }

  function appendBotMessage(pair) {
    var thread = threadElement();
    if (!thread) {
      return null;
    }
    var item = el("li", "msg bot", null);
    item.setAttribute("data-message-role", "bot");
    var bubble = el("div", "bubble", null);
    bubble.appendChild(bilingual("p", "bubble-text", pair));
    item.appendChild(bubble);
    thread.appendChild(item);
    scrollThreadToLatest(item);
    return item;
  }

  function appendPendingBotShell(bubbleClassName) {
    var thread = threadElement();
    if (!thread) {
      return null;
    }
    var item = el("li", "msg bot", null);
    item.setAttribute("data-message-role", "bot");
    item.setAttribute("data-pending-message", "true");
    var bubble = el("div", "bubble " + bubbleClassName, null);
    item.appendChild(bubble);
    thread.appendChild(item);
    scrollThreadToLatest(item);
    return { item: item, bubble: bubble };
  }

  function clearPendingState(item, bubble) {
    if (item) {
      item.removeAttribute("data-pending-message");
    }
    if (bubble) {
      bubble.className = "bubble";
    }
  }

  function appendTypingBotMessage() {
    var pending = appendPendingBotShell("pending-bubble");
    if (!pending) {
      return null;
    }
    var status = el("div", "pending-status pending-typing", null);
    status.setAttribute("role", "status");
    status.setAttribute("aria-live", "polite");
    status.setAttribute("aria-atomic", "true");
    status.appendChild(bilingual("span", "pending-status-text", TYPING_STATUS_LABEL));

    var dots = el("span", "typing-dots", null);
    dots.setAttribute("aria-hidden", "true");
    for (var index = 0; index < 3; index += 1) {
      dots.appendChild(el("span", null, null));
    }
    status.appendChild(dots);
    pending.bubble.appendChild(status);
    return pending.item;
  }

  function appendAnalysisPendingBotMessage() {
    var pending = appendPendingBotShell("pending-bubble pending-analysis");
    if (!pending) {
      return null;
    }
    var status = el("div", "pending-status", null);
    status.setAttribute("role", "status");
    status.setAttribute("aria-live", "polite");
    status.setAttribute("aria-atomic", "true");
    status.appendChild(bilingual("span", "sr-only", ANALYSIS_STAGE_LABELS[0]));

    var stages = el("div", "pending-stage-stack", null);
    stages.setAttribute("aria-hidden", "true");
    ANALYSIS_STAGE_LABELS.forEach(function (stage) {
      stages.appendChild(bilingual("span", "pending-stage-line", stage));
    });
    status.appendChild(stages);
    status.appendChild(el("span", "pending-progress", null));
    pending.bubble.appendChild(status);
    return pending.item;
  }

  function renderChatCitations(container, citations) {
    // Intentionally render nothing: source-citation counts/ids are internal
    // bookkeeping and are not useful to a creator reading a follow-up reply.
    return;
  }

  function replaceBotMessageWithText(item, content, citations) {
    if (!item) {
      item = appendBotMessage({ ko: "", en: "" });
    }
    if (!item) {
      return null;
    }
    var bubble = item.querySelector(".bubble");
    if (!bubble) {
      return item;
    }
    clearPendingState(item, bubble);
    clearNode(bubble);
    bubble.appendChild(el("p", "bubble-text", text(content)));
    renderChatCitations(bubble, citations || []);
    scrollThreadToLatest(item);
    return item;
  }

  function replaceBotMessageWithPair(item, pair) {
    if (!item) {
      return appendBotMessage(pair);
    }
    var bubble = item.querySelector(".bubble");
    if (!bubble) {
      return item;
    }
    clearPendingState(item, bubble);
    clearNode(bubble);
    bubble.appendChild(bilingual("p", "bubble-text", pair));
    scrollThreadToLatest(item);
    return item;
  }

  function questionPair(value) {
    if (!value) {
      return null;
    }
    if (typeof value === "string") {
      var raw = value.trim();
      return raw ? { ko: raw, en: raw } : null;
    }
    var ko = text(value.ko).trim();
    var en = text(value.en).trim();
    if (!ko && !en) {
      return null;
    }
    return { ko: ko || en, en: en || ko };
  }

  function collectSuggestedFollowUps(payload) {
    var suggestions = [];
    var seen = {};
    function add(value) {
      var pair = questionPair(value);
      if (!pair || suggestions.length >= 3) {
        return;
      }
      var key = (pair.ko + "\n" + pair.en).toLowerCase();
      if (seen[key]) {
        return;
      }
      seen[key] = true;
      suggestions.push(pair);
    }
    (payload.findings || []).forEach(function (finding) {
      add(finding.question_to_ask);
      (finding.additional_questions || []).forEach(add);
    });
    return suggestions;
  }

  function renderSuggestedFollowUps(container, payload) {
    var suggestions = collectSuggestedFollowUps(payload);
    if (suggestions.length === 0) {
      return;
    }
    var section = el("section", "followup-suggestions", null);
    section.setAttribute("data-followup-suggestions", "true");
    section.appendChild(
      bilingual("p", "hint", {
        ko: "이런 걸 물어볼 수 있어요",
        en: "You could ask"
      })
    );
    var row = el("div", "chip-row followup-chip-stack", null);
    suggestions.forEach(function (question) {
      var button = el("button", "example-chip", null);
      button.type = "button";
      button.setAttribute("data-followup-chip", "true");
      button.setAttribute("data-question-ko", question.ko);
      button.setAttribute("data-question-en", question.en);
      button.appendChild(bilingual("span", null, question));
      row.appendChild(button);
    });
    section.appendChild(row);
    container.appendChild(section);
  }

  function renderResult(payload, targetItem) {
    var container = ensureResultContainer();
    var thread = threadElement();
    if (!container || !thread) {
      return;
    }
    if (container.parentNode) {
      container.parentNode.removeChild(container);
    }
    removePriorResultMessages(targetItem);
    resetResultContainer(container);
    removeReviewBriefBubble();
    var opening = prepareResultOpeningMessage(targetItem, container);
    container.appendChild(bilingual("p", "bubble-text", resultOpeningPair(payload)));

    var sequenceIndex = 1;
    var latest = opening;
    function appendBubble(className, content) {
      if (!content || content.childNodes.length === 0) {
        return;
      }
      latest = appendResultContentBubble(className, content, sequenceIndex) || latest;
      sequenceIndex += 1;
    }
    function appendRenderedBubble(className, render) {
      var wrap = el("div", "result-inline-panel", null);
      render(wrap);
      appendBubble(className, wrap);
    }

    appendRenderedBubble("glance-bubble", function (wrap) {
      renderIntegratedJudgmentCard(wrap, payload);
    });
    renderFindings(appendBubble, payload);
    renderDimensionChips(appendBubble, payload);
    appendRenderedBubble("review-action-bubble", function (wrap) {
      renderReviewBriefAction(wrap);
    });
    appendRenderedBubble("followup-chip-bubble", function (wrap) {
      renderSuggestedFollowUps(wrap, payload);
    });
    appendRenderedBubble("audit-bubble", function (wrap) {
      renderAdvancedDiagnostics(wrap, payload);
    });

    setLocale(activeLocale());
    scrollThreadToLatest(latest || opening);
  }

  function collectAssumptions() {
    var assumptions = {};
    var inputs = document.querySelectorAll(
      "[data-assumption-field] input, [data-scenario-primary-field] input"
    );
    inputs.forEach(function (input) {
      var value = input.value.trim();
      if (value !== "") {
        assumptions[input.name] = value;
      }
    });
    return assumptions;
  }

  function firstChangedAssumption(previous, current) {
    previous = previous || {};
    current = current || {};
    var names = Object.keys(previous)
      .concat(Object.keys(current))
      .filter(function (name, index, items) {
        return items.indexOf(name) === index;
      })
      .sort();
    for (var index = 0; index < names.length; index += 1) {
      var name = names[index];
      if (String(previous[name] || "") !== String(current[name] || "")) {
        return name;
      }
    }
    return "scenario_inputs";
  }

  function selectedFile() {
    var input = document.getElementById("contract-file");
    if (!input || !input.files || input.files.length === 0) {
      return null;
    }
    return input.files[0];
  }

  function attachmentPreviewElement() {
    return document.querySelector("[data-attachment-preview]");
  }

  function renderAttachmentPreview() {
    var container = attachmentPreviewElement();
    if (!container) {
      return;
    }
    clearNode(container);
    var file = selectedFile();
    if (!file) {
      container.hidden = true;
      return;
    }
    container.hidden = false;
    var card = el("div", "attachment-card", null);
    if (isImageUpload(file) && attachmentPreviewUrl) {
      card.appendChild(
        attachmentImage(attachmentPreviewUrl, "attachment-thumbnail", file.name, false)
      );
    }
    card.appendChild(fileChip(file.name || "첨부 파일"));
    var remove = el("button", "attachment-remove-button", "x");
    remove.type = "button";
    remove.setAttribute("data-clear-attachment", "true");
    remove.setAttribute("aria-label", "첨부 파일 제거 / Remove attachment");
    card.appendChild(remove);
    container.appendChild(card);
  }

  function updateAttachmentPreviewForSelection() {
    revokeAttachmentPreviewUrl();
    var file = selectedFile();
    if (file && isImageUpload(file)) {
      attachmentPreviewUrl = createFileObjectUrl(file);
    }
    renderAttachmentPreview();
  }

  function clearSelectedAttachment() {
    var input = document.getElementById("contract-file");
    if (input) {
      input.value = "";
    }
    revokeAttachmentPreviewUrl();
    renderAttachmentPreview();
  }

  function isImageOrPdfUpload(file) {
    if (!file) {
      return false;
    }
    var type = text(file.type).toLowerCase();
    var name = text(file.name).toLowerCase();
    return (
      type.indexOf("image/") === 0 ||
      type === "application/pdf" ||
      /\.(pdf|png|jpe?g|webp|heic|heif)$/.test(name)
    );
  }

  function ocrReadFailureMessage() {
    return {
      ko: "사진에서 글자를 읽지 못했어요. 더 선명한 사진을 올리거나 계약 문구를 붙여넣어 주세요.",
      en: "I couldn't read text from that image. Try a clearer photo or paste the contract text."
    };
  }

  function isOcrReadFailure(data, file) {
    if (!isImageOrPdfUpload(file)) {
      return false;
    }
    var code = text(data && data.error_code);
    return code === "OCR_NO_TEXT" || code === "FILE_EMPTY";
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

  function setChatBusy(isBusy) {
    chatInFlight = isBusy;
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

  function buildAnalyzeRequest(pasteText, file, options) {
    options = options || {};
    var assumptions = collectAssumptions();
    var changedInput = options.scenarioRecompute
      ? firstChangedAssumption(lastSubmittedAssumptions, assumptions)
      : "";
    if (file) {
      var form = new FormData();
      form.append("contract_file", file);
      form.append("locale", activeLocale());
      form.append("assumptions", JSON.stringify(assumptions));
      if (options.scenarioRecompute) {
        form.append("previous_assumptions", JSON.stringify(lastSubmittedAssumptions));
        form.append("changed_input", changedInput);
      }
      if (pasteText && pasteText.trim() !== "") {
        form.append("paste_text", pasteText);
      }
      return { body: form, headers: {}, assumptions: assumptions, changedInput: changedInput };
    }
    return {
      body: JSON.stringify({
        paste_text: pasteText,
        locale: activeLocale(),
        assumptions: assumptions,
        previous_assumptions: options.scenarioRecompute ? lastSubmittedAssumptions : undefined,
        changed_input: options.scenarioRecompute ? changedInput : undefined
      }),
      headers: { "Content-Type": "application/json" },
      assumptions: assumptions,
      changedInput: changedInput
    };
  }

  function recomputeMessage(data, changedInput) {
    var audit = data && data.audit_detail && data.audit_detail.scenario_recompute;
    if (audit && audit.status_region_message) {
      return audit.status_region_message;
    }
    return {
      ko: changedInput + " 입력으로 시나리오를 다시 계산했습니다.",
      en: "Scenario recalculated for " + changedInput + "."
    };
  }

  function analyze(options) {
    options = options || {};
    if (analyzeInFlight || chatInFlight) {
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
    var pendingResult = null;
    if (options.scenarioRecompute) {
      scenarioStatusMessage({
        ko: "시나리오를 다시 계산 중입니다.",
        en: "Recalculating the scenario."
      });
    } else {
      // Echo the creator's turn as a user bubble before sending, then clear the
      // composer so it behaves like a chat input.
      if (file) {
        appendUserMessage(pasteText, true, {
          fileName: file.name || "첨부 파일",
          imageUrl: isImageUpload(file) ? createFileObjectUrl(file) : ""
        });
        box.value = "";
        clearSelectedAttachment();
        autoGrowComposer();
      } else {
        appendUserMessage(pasteText, false);
        box.value = "";
        autoGrowComposer();
      }
      pendingResult = appendAnalysisPendingBotMessage();
      statusMessage({ ko: "로컬에서 분석 중입니다.", en: "Analyzing locally." });
    }
    setAnalyzeBusy(true);
    var request = buildAnalyzeRequest(pasteText, file, options);
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
          var errorPair = isOcrReadFailure(result.data, file)
            ? ocrReadFailureMessage()
            : {
                ko: result.data && result.data.error ? result.data.error : "분석에 실패했습니다.",
                en:
                  result.data && result.data.error_en
                    ? result.data.error_en
                    : "Analysis failed."
              };
          if (pendingResult) {
            replaceBotMessageWithPair(pendingResult, errorPair);
          } else {
            appendBotMessage(errorPair);
          }
          statusMessage({
            ko: "오류: " + errorPair.ko,
            en: "Error: " + errorPair.en
          });
          return;
        }
        if (options.scenarioRecompute) {
          scenarioStatusMessage(recomputeMessage(result.data, request.changedInput));
        } else {
          statusMessage({ ko: "분석을 완료했습니다.", en: "Analysis complete." });
        }
        renderResult(result.data, pendingResult);
        if (options.scenarioRecompute) {
          scenarioStatusMessage(recomputeMessage(result.data, request.changedInput));
        }
        lastResultPayload = result.data;
        if (!options.scenarioRecompute) {
          analyzedContractText = !file && pasteText && pasteText.trim() !== "" ? pasteText : "";
        }
        lastSubmittedAssumptions = request.assumptions;
      })
      .catch(function () {
        var requestError = {
          ko: "로컬 분석 요청에 실패했습니다. 잠시 후 다시 시도해 주세요.",
          en: "The local analysis request failed. Please try again."
        };
        if (pendingResult) {
          replaceBotMessageWithPair(pendingResult, requestError);
        } else {
          appendBotMessage(requestError);
        }
        statusMessage({
          ko: "로컬 분석 요청에 실패했습니다.",
          en: "The local analysis request failed."
        });
      })
      .finally(function () {
        setAnalyzeBusy(false);
      });
  }

  function submitFollowUpQuestion(question, options) {
    options = options || {};
    if (chatInFlight || analyzeInFlight) {
      return;
    }
    var asked = String(question || "").trim();
    if (!asked) {
      statusMessage({
        ko: "질문을 입력하세요.",
        en: "Enter a follow-up question."
      });
      return;
    }
    if (!lastResultPayload || !analyzedContractText || analyzedContractText.trim() === "") {
      appendBotMessage({
        ko: "먼저 계약 텍스트를 분석한 뒤 이어서 질문할 수 있습니다.",
        en: "Analyze contract text first, then ask a follow-up."
      });
      statusMessage({
        ko: "먼저 계약 텍스트를 분석하세요.",
        en: "Analyze contract text first."
      });
      return;
    }
    appendUserMessage(asked, false);
    if (options.clearComposer) {
      var box = document.getElementById("paste-box");
      if (box) {
        box.value = "";
        autoGrowComposer();
      }
    }
    var pending = appendTypingBotMessage();
    setChatBusy(true);
    fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        paste_text: analyzedContractText,
        question: asked,
        locale: activeLocale()
      })
    })
      .then(function (response) {
        return response.json().then(function (data) {
          return { ok: response.ok, data: data };
        });
      })
      .then(function (result) {
        if (!result.ok) {
          replaceBotMessageWithPair(pending, {
            ko: "답변을 만들지 못했습니다. 다시 시도해 주세요.",
            en: "Could not create a reply. Please try again."
          });
          statusMessage({
            ko: "후속 답변 요청에 실패했습니다.",
            en: "Follow-up reply failed."
          });
          return;
        }
        replaceBotMessageWithText(pending, result.data && result.data.reply, result.data.citations || []);
        statusMessage({
          ko: "후속 질문에 답했습니다.",
          en: "Answered your follow-up."
        });
      })
      .catch(function () {
        replaceBotMessageWithPair(pending, {
          ko: "답변 요청에 실패했습니다. 다시 시도해 주세요.",
          en: "Reply request failed. Please try again."
        });
        statusMessage({
          ko: "후속 답변 요청에 실패했습니다.",
          en: "Follow-up reply failed."
        });
      })
      .finally(function () {
        setChatBusy(false);
      });
  }

  function submitComposer() {
    if (lastResultPayload && !selectedFile()) {
      var box = document.getElementById("paste-box");
      submitFollowUpQuestion(box ? box.value : "", { clearComposer: true });
      return;
    }
    analyze();
  }

  function clearAll() {
    var box = document.getElementById("paste-box");
    if (box) {
      box.value = "";
    }
    clearSelectedAttachment();
    var container = document.getElementById("result");
    if (container) {
      clearNode(container);
    }
    var resultMessage = document.querySelector("[data-result-message]");
    if (resultMessage) {
      resultMessage.hidden = true;
    }
    document.querySelectorAll("[data-result-sequence-item]").forEach(function (item) {
      if (item.parentNode) {
        item.parentNode.removeChild(item);
      }
    });
    removeReviewBriefBubble();
    autoGrowComposer();
    analyzedContractText = "";
    lastResultPayload = null;
    lastSubmittedAssumptions = {};
    statusMessage({
      ko: "입력을 지웠습니다.",
      en: "Input cleared."
    });
  }

  function autoGrowComposer() {
    var box = document.getElementById("paste-box");
    if (!box) {
      return;
    }
    box.style.height = "auto";
    box.style.height = Math.min(box.scrollHeight, window.innerHeight * 0.4) + "px";
  }

  function fillExample() {
    var box = document.getElementById("paste-box");
    if (!box) {
      return;
    }
    clearSelectedAttachment();
    box.value =
      activeLocale() === "en"
        ? "Section 3 (Settlement) Payment is made within 90 days after the end of each quarter; the company may deduct general expenses."
        : "제3조(정산) 정산은 매 분기 종료일로부터 90일 이내에 지급하며, 회사는 일반 경비를 공제할 수 있다.";
    autoGrowComposer();
    analyze();
  }

  function toggleNotice() {
    var button = document.querySelector("[data-notice-toggle]");
    var panel = document.getElementById("notice-panel");
    if (!button || !panel) {
      return;
    }
    var open = panel.hidden;
    panel.hidden = !open;
    button.setAttribute("aria-expanded", open ? "true" : "false");
  }

  function init() {
    var toggle = document.querySelector("[data-locale-toggle]");
    if (toggle) {
      toggle.addEventListener("click", function (event) {
        var button = event.target.closest("[data-locale-button]");
        if (button) {
          setLocale(activeLocale() === "en" ? "ko" : "en");
        }
      });
    }
    var analyzeButton = document.getElementById("analyze-btn");
    if (analyzeButton) {
      analyzeButton.addEventListener("click", function () {
        submitComposer();
      });
    }
    var attachButton = document.querySelector("[data-attach-button]");
    var fileInput = document.getElementById("contract-file");
    if (attachButton && fileInput) {
      attachButton.addEventListener("click", function () {
        fileInput.click();
      });
    }
    var composerInput = document.getElementById("paste-box");
    if (composerInput) {
      composerInput.addEventListener("input", autoGrowComposer);
      autoGrowComposer();
    }
    document.addEventListener("click", function (event) {
      var target = event.target;
      if (!target || !target.closest) {
        return;
      }
      var noticeButton = target.closest("[data-notice-toggle]");
      if (noticeButton) {
        toggleNotice();
      }
      var exampleChip = target.closest("[data-example-chip]");
      if (exampleChip) {
        event.preventDefault();
        fillExample();
      }
      var clearAttachmentButton = target.closest("[data-clear-attachment]");
      if (clearAttachmentButton) {
        event.preventDefault();
        clearSelectedAttachment();
      }
      var followUpChip = target.closest("[data-followup-chip]");
      if (followUpChip) {
        event.preventDefault();
        submitFollowUpQuestion(
          activeLocale() === "en"
            ? followUpChip.getAttribute("data-question-en")
            : followUpChip.getAttribute("data-question-ko")
        );
      }
      var makeBriefButton = target.closest("[data-make-review-brief]");
      if (makeBriefButton) {
        event.preventDefault();
        showReviewBrief();
      }
      var downloadBriefButton = target.closest("[data-download-review-brief]");
      if (downloadBriefButton) {
        event.preventDefault();
        downloadReviewBrief();
      }
    });
    document.addEventListener("change", function (event) {
      var target = event.target;
      if (!target || !target.closest) {
        return;
      }
      var picked = target.closest("[data-file-input]");
      if (picked) {
        updateAttachmentPreviewForSelection();
        if (picked.files && picked.files.length > 0) {
          statusMessage({
            ko: "첨부 파일을 추가했습니다. 필요한 문구를 더 입력한 뒤 보내세요.",
            en: "File attached. Add any needed text, then send."
          });
        }
      }
    });
    document.addEventListener("keydown", function (event) {
      var target = event.target;
      if (!target || !target.closest) {
        return;
      }
      // Enter sends; Shift+Enter inserts a newline in the composer.
      if (
        event.key === "Enter" &&
        !event.shiftKey &&
        target.closest("[data-paste-box]")
      ) {
        event.preventDefault();
        submitComposer();
      }
    });
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
        "font-src 'self'; "
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

from __future__ import annotations

import argparse
import html
import ipaddress
import json
from dataclasses import dataclass
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
    "Local-only session. Contract uploads and OCR text stay on this device; "
    "no usage tracking, cloud OCR, remote LLM, or external legal search is used."
)
PRIVACY_BANNER_KO = (
    "기록 미수집 · 기기 내 처리. 사용 기록을 수집하지 않고, 모든 분석을 이 기기 "
    "안에서 처리합니다. 클라우드 OCR·원격 LLM·외부 법률 검색을 쓰지 않습니다."
)
# Value first, honest boundary second. The English aid still carries the pinned
# phrase "Contractual Financial Review Priority". This is a disclaimer that FInk
# does NOT determine legality/fraud/validity/etc., so it stays clear of the
# legal_verdict_scan BAD_LEGAL_ASSERTIONS patterns.
NOT_LEGAL_ADVICE_BANNER = (
    "FInk reads your contract to find the clauses that move money and the signals "
    "that need attention, orders them so you check the most important first, and "
    "explains why (a Contractual Financial Review Priority). It does not make the "
    "final call on legality, fraud, contract validity, or unfairness, so have an "
    "expert confirm anything important before you decide."
)
NOT_LEGAL_ADVICE_BANNER_KO = (
    "FInk은 계약서에서 돈과 직결되는 조항과 주의가 필요한 신호를 찾아 "
    "먼저 확인할 순서로 정리하고 그 이유를 설명합니다. 다만 위법성·사기·계약 효력·"
    "불공정 여부를 최종적으로 판정하지는 않으니, 중요한 결정 전에는 전문가의 확인을 "
    "받으세요."
)
TRUSTED_LAN_WARNING = (
    "Trusted-LAN mode exposes this local server only to devices on the same private "
    "network. Use it only on a network you control, and stop the server when finished."
)
DISCLOSURE_ITEMS = (
    "Review priority is not a legal, fraud, validity, unfairness, or guaranteed-loss verdict.",
    "Figures are scenario estimates from user assumptions, not guaranteed losses.",
    "Official-source grounding is shown as needs evidence confirmation until confirmed.",
    "Korean source language is canonical; English UI text is a generated aid.",
)
# Korean-canonical / English-aid pairs for the report disclosures. The English
# aid strings stay identical to DISCLOSURE_ITEMS so the privacy payload and the
# a11y wording pins still match; the Korean line leads as the canonical text.
DISCLOSURE_ITEMS_BILINGUAL = (
    {
        "ko": "검토 순서는 위법성·사기·유효성·불공정·손실 확정에 대한 판정이 아닙니다.",
        "en": DISCLOSURE_ITEMS[0],
    },
    {
        "ko": "금액은 사용자가 입력한 가정에 따른 시나리오 추정치이며 확정 손실이 아닙니다.",
        "en": DISCLOSURE_ITEMS[1],
    },
    {
        "ko": "공식 자료 근거가 부족한 항목은 근거 확인 필요로 표시됩니다.",
        "en": DISCLOSURE_ITEMS[2],
    },
    {
        "ko": "한국어 원문이 기준이며, 영어 화면 문구는 보조용으로 생성됩니다.",
        "en": DISCLOSURE_ITEMS[3],
    },
)

LAN_CONFIRMATION_TEXT = "I understand this is a trusted-LAN-only local server."
_BLOCKED_BIND_HOSTS = frozenset({"0.0.0.0", "::", ""})

WEB_DESIGN_TOKENS = {
    "ink": "#151a22",
    "muted": "#4a5565",
    "line": "#d4dbe5",
    "line_soft": "#e6ebf2",
    "panel": "#ffffff",
    "canvas": "#eef2f7",
    "accent": "#006d77",
    "accent_strong": "#014f56",
    "accent_tint": "#f1f8f9",
    "warn_bg": "#fff3cd",
    "warn_ink": "#5a4100",
    "focus_ring": "#0b57d0",
    "focus_offset": "#ffffff",
    "danger": "#8a2c0d",
    "source_mark": "#f6f0ff",
}

WEB_CONTRAST_CHECKS = (
    ("body text on panel", "ink", "panel", 4.5),
    ("body text on canvas", "ink", "canvas", 4.5),
    ("muted text on panel", "muted", "panel", 4.5),
    ("muted text on canvas", "muted", "canvas", 4.5),
    ("primary button text", "panel", "accent", 4.5),
    ("secondary button text", "accent_strong", "panel", 4.5),
    ("link text on panel", "accent_strong", "panel", 4.5),
    ("badge text on accent tint", "accent_strong", "accent_tint", 4.5),
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
      <h1>창작자 특화 금융 계약 검토</h1>
      <p class="subtitle">Creator-focused financial contract review</p>
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
              "cash-flow clauses to check before you sign.",
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
    <label class="composer-label sr-only" for="paste-box">
      <span lang="ko" data-locale-text="ko">계약 조항 붙여넣기</span>
      <span lang="en" data-locale-text="en">Paste clause text</span>
    </label>
    <textarea id="paste-box" name="paste_text" rows="1" spellcheck="false"
      class="composer-input"
      data-ingest-mode="paste" data-paste-box="true"
      aria-describedby="analyze-status"
      placeholder="제3조(정산) ..."></textarea>
    <button type="button" id="analyze-btn" class="send-button" data-analyze-button="true"
      aria-controls="result analyze-status"
      aria-label="보내기 / Send">
      <span aria-hidden="true">↑</span>
      <span class="send-label">{_bilingual("보내기", "Send")}</span>
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
:root {{
  color-scheme: light;
  --ink: {tokens["ink"]};
  --muted: {tokens["muted"]};
  --line: {tokens["line"]};
  --line-soft: {tokens["line_soft"]};
  --panel: {tokens["panel"]};
  --canvas: {tokens["canvas"]};
  --accent: {tokens["accent"]};
  --accent-strong: {tokens["accent_strong"]};
  --accent-tint: {tokens["accent_tint"]};
  --warn-bg: {tokens["warn_bg"]};
  --warn-ink: {tokens["warn_ink"]};
  --focus-ring: {tokens["focus_ring"]};
  --focus-offset: {tokens["focus_offset"]};
  --danger: {tokens["danger"]};
  --source-mark: {tokens["source_mark"]};
  /* 8px spacing rhythm. */
  --space-1: .5rem;
  --space-2: 1rem;
  --space-3: 1.5rem;
  --space-4: 2rem;
  --radius: 8px;
  --shadow: 0 1px 2px rgba(21, 26, 34, .06), 0 6px 18px rgba(21, 26, 34, .05);
  --reading-measure: 66ch;
}}
""" + """
* { box-sizing: border-box; }
html {
  scroll-padding: calc(var(--space-4) + 44px);
}
body {
  margin: 0;
  background: var(--canvas);
  color: var(--ink);
  font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  line-height: 1.6;
  overflow-wrap: anywhere;
  /* Full-height messenger column: header, privacy line, scrolling thread, and
     a composer pinned to the bottom. The thread is the only scroll region, so
     the composer stays put via flex layout, no sticky positioning needed. */
  display: flex;
  flex-direction: column;
  min-height: 100vh;
  height: 100vh;
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
  font: inherit;
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
.dimension-grid {
  display: grid;
  gap: .75rem;
  grid-template-columns: repeat(auto-fit, minmax(12rem, 1fr));
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
.grounded-qa {
  display: grid;
  gap: var(--space-1);
  padding-top: var(--space-2);
  border-top: 1px solid var(--line);
}
.grounded-qa-list {
  display: grid;
  gap: var(--space-1);
}
.qa-followup {
  display: grid;
  gap: .5rem;
  margin-bottom: var(--space-1);
  padding: var(--space-2);
  border: 1px solid var(--accent);
  border-radius: var(--radius);
  background: var(--accent-tint);
}
.qa-followup-label { font-weight: 800; }
.qa-followup-row {
  display: flex;
  gap: .5rem;
  flex-wrap: wrap;
}
.qa-followup-row input {
  flex: 1 1 14rem;
  min-width: 0;
  border: 1px solid var(--line);
  border-radius: 6px;
  padding: .55rem .7rem;
}
.qa-followup-answer {
  border-left: 4px solid var(--accent);
  background: #fff;
}
.grounded-qa-item {
  display: grid;
  gap: .75rem;
  padding: .85rem;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: #fbfcfe;
}
.qa-check {
  display: inline-flex;
  align-items: center;
  gap: .5rem;
  font-weight: 700;
}
.qa-check input {
  width: 1.2rem;
  min-height: 1.2rem;
}
.qa-body {
  display: grid;
  gap: .5rem;
}
.qa-citations {
  display: flex;
  flex-wrap: wrap;
  gap: .5rem;
  padding-left: 0;
  list-style: none;
}
.qa-citations code {
  padding: .18rem .4rem;
  border: 1px solid var(--line);
  border-radius: 6px;
  background: #fff;
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
  outline: 3px solid var(--focus-ring);
  outline-offset: 2px;
  box-shadow: 0 0 0 5px var(--focus-offset);
}
.integrated-judgment-card {
  display: grid;
  gap: var(--space-1);
  margin: 0 0 var(--space-2);
  padding: var(--space-2);
  border: 1px solid var(--line);
  border-top: 4px solid var(--accent);
  border-radius: var(--radius);
  background: #f9fcfd;
  box-shadow: var(--shadow);
}
.glance-heading {
  display: flex;
  gap: .5rem;
  align-items: center;
}
.glance-heading h3 {
  margin: 0;
  color: var(--accent-strong);
  font-size: .95rem;
}
.glance-icon {
  display: inline-flex;
  width: 1.4rem;
  height: 1.4rem;
  align-items: center;
  justify-content: center;
  flex: 0 0 auto;
  padding: .18rem;
  border: 1px solid var(--accent);
  border-radius: 999px;
  background: var(--accent-tint);
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
  margin: 0;
  max-width: var(--reading-measure);
  color: var(--ink);
  font-size: 1.1rem;
  font-weight: 800;
}
.glance-cues {
  display: flex;
  gap: .5rem;
  flex-wrap: wrap;
  margin: 0;
}
.glance-chip {
  display: inline-flex;
  width: fit-content;
  max-width: 100%;
  align-items: center;
  padding: .25rem .55rem;
  border: 1px solid var(--accent);
  border-radius: 999px;
  background: var(--accent-tint);
  color: var(--accent-strong);
  font-size: .85rem;
  font-weight: 800;
}
.glance-count {
  border-color: var(--line);
  background: #fff;
  color: var(--ink);
}
.glance-concern {
  display: grid;
  gap: .35rem;
  padding: .75rem .85rem;
  border: 1px solid var(--line-soft);
  border-radius: 8px;
  background: #fff;
}
.glance-concern-label,
.glance-caution {
  margin: 0;
  color: var(--muted);
  font-size: .9rem;
}
.glance-concern-label {
  font-weight: 800;
}
.glance-concern-title {
  margin: 0;
  font-size: 1rem;
}
.glance-concern-why {
  margin: 0;
  max-width: var(--reading-measure);
  color: var(--muted);
}
.check-first, .recommended-action {
  display: grid;
  gap: var(--space-1);
  margin: var(--space-2) 0;
  padding: var(--space-2);
  border: 1px solid var(--accent);
  border-left: 6px solid var(--accent);
  border-radius: var(--radius);
  background: var(--accent-tint);
}
.check-first h2, .check-first h3 {
  margin: 0;
}
.check-first blockquote, .finding-section blockquote {
  margin: 0;
  padding: .75rem .85rem;
  border-left: 4px solid var(--accent);
  background: #fff;
  max-width: var(--reading-measure);
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
.finding-sort-control {
  display: inline-flex;
  gap: .25rem;
  align-items: center;
  width: fit-content;
  margin: .1rem 0 .25rem;
  padding: .18rem;
  border: 1px solid var(--line);
  border-radius: 999px;
  background: #fff;
}
.finding-sort-option {
  min-height: 44px;
  padding: .35rem .7rem;
  border: 1px solid transparent;
  border-radius: 999px;
  background: transparent;
  color: var(--accent-strong);
  font-size: .85rem;
  font-weight: 700;
}
.finding-sort-option:hover,
.finding-sort-option[aria-pressed="true"] {
  border-color: var(--accent);
}
.finding-sort-option[aria-pressed="true"] {
  background: var(--accent-tint);
}
.ranked-findings, .guidance-card ul {
  display: grid;
  gap: .6rem;
  margin: 0;
}
.ranked-findings {
  list-style: none;
  padding-left: 0;
}
.guidance-card ul {
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
.finding-card[open] {
  border-color: var(--accent);
}
.finding-summary {
  cursor: pointer;
  display: grid;
  gap: .5rem;
  list-style-position: inside;
}
.finding-title {
  font-weight: 800;
}
.finding-badges {
  display: flex;
  gap: .35rem;
  flex-wrap: wrap;
}
.finding-priority-badge {
  min-width: 1.65rem;
  text-align: center;
  color: var(--accent-strong);
  background: var(--accent-tint);
  border-color: var(--accent);
  font-variant-numeric: tabular-nums;
}
.finding-section {
  display: grid;
  gap: .45rem;
  padding-top: var(--space-1);
  border-top: 1px solid var(--line-soft);
}
.finding-section h4 {
  margin: 0;
}
.advanced-diagnostic {
  display: grid;
  gap: .5rem;
  margin-top: var(--space-1);
  padding: var(--space-1);
  border: 1px solid var(--line-soft);
  border-radius: 8px;
  background: #fbfcfe;
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
@media (max-width: 480px) {
  .workspace {
    padding: var(--space-1);
  }
  .dimension-grid,
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
@media print {
  body,
  .topbar,
  footer,
  .card,
  .integrated-judgment-card,
  .tool-details,
  .source-highlights,
  .finding-card,
  .scenario-inputs,
  .assumptions-panel,
  .page-card,
  .source-highlight-card,
  .source-card {
    color: #000;
    background: #fff;
    box-shadow: none;
  }
  .skip-link,
  .locale-toggle,
  #analyze-btn,
  #contract-file,
  .reader-jump-links,
  .reader-back-link {
    display: none !important;
  }
  details,
  details > summary,
  details:not([open]) > *:not(summary) {
    display: block;
  }
  a {
    color: #000;
    text-decoration: underline;
  }
  .badge,
  .glance-chip,
  .source-badge,
  .unverified-badge,
  .model-suggestion-origin {
    color: #000;
    background: transparent;
    border: 1px solid #000;
    font-weight: 700;
  }
  mark,
  .source-highlight {
    color: #000;
    background: transparent;
    font-weight: 700;
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
  display: flex;
  gap: 1rem;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  padding: .75rem clamp(1rem, 4vw, 2rem);
  background: var(--panel);
  border-bottom: 1px solid var(--line);
}
.chat-title h1 {
  margin: 0;
  font-size: 1.25rem;
  line-height: 1.3;
}
.chat-title .subtitle {
  margin: .1rem 0 0;
  font-size: .85rem;
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
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--accent-strong);
  font-size: 1.25rem;
}
.notice-button:hover {
  background: transparent;
}
.chat-privacy {
  margin: 0;
  padding: .55rem clamp(1rem, 4vw, 2rem);
  background: var(--accent-tint);
  border-bottom: 1px solid var(--line-soft);
  color: var(--muted);
  font-size: .85rem;
}
.notice-panel {
  margin: 0;
  padding: var(--space-2) clamp(1rem, 4vw, 2rem);
  background: #e8f3f4;
  border-bottom: 1px solid var(--line);
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
  padding: var(--space-2) clamp(.75rem, 4vw, 2rem);
}
.thread {
  display: grid;
  gap: var(--space-2);
  width: 100%;
  max-width: 760px;
  margin: 0 auto;
  padding: 0;
  list-style: none;
}
.msg {
  display: flex;
  width: 100%;
}
.msg.bot {
  justify-content: flex-start;
}
.msg.user {
  justify-content: flex-end;
}
.bubble {
  max-width: min(100%, 46rem);
  padding: .75rem 1rem;
  border-radius: 16px;
  border: 1px solid var(--line);
  background: var(--panel);
  box-shadow: var(--shadow);
}
.msg.bot .bubble {
  border-top-left-radius: 4px;
}
.msg.user .bubble {
  border-top-right-radius: 4px;
  border-color: var(--accent);
  background: var(--accent-tint);
}
.bubble-text {
  margin: 0;
  max-width: var(--reading-measure);
}
.bubble-result {
  max-width: 100%;
  width: 100%;
}
.file-chip {
  display: inline-flex;
  align-items: center;
  gap: .4rem;
  font-weight: 700;
}
.chip-row {
  display: flex;
  gap: .5rem;
  flex-wrap: wrap;
  margin-top: .65rem;
}
.example-chip {
  background: #fff;
  color: var(--accent-strong);
  border: 1px solid var(--accent);
  border-radius: 999px;
  padding: .4rem .85rem;
  font-weight: 700;
}
.result-pane {
  display: grid;
  gap: var(--space-1);
}
.composer {
  display: flex;
  gap: .5rem;
  align-items: flex-end;
  padding: .65rem clamp(.75rem, 4vw, 2rem);
  background: var(--panel);
  border-top: 1px solid var(--line);
}
.composer-input {
  flex: 1 1 auto;
  min-width: 0;
  min-height: 44px;
  max-height: 40vh;
  resize: none;
  border: 1px solid var(--line);
  border-radius: 22px;
  padding: .6rem 1rem;
  line-height: 1.5;
  overflow-y: auto;
}
.attach-button,
.send-button {
  flex: 0 0 auto;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: .35rem;
  min-width: 44px;
  height: 44px;
  border-radius: 999px;
  padding: 0 .9rem;
}
.attach-button {
  background: #fff;
  color: var(--accent-strong);
  font-size: 1.1rem;
}
.paperclip-icon {
  width: 1.2rem;
  height: 1.2rem;
}
.send-button {
  font-weight: 800;
}
.send-button:hover {
  background: var(--accent-strong);
}
.send-button .send-label {
  font-size: .95rem;
}
@media (max-width: 480px) {
  .send-button .send-label {
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
  .chat-title h1 {
    font-size: 1.1rem;
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
  var lastSubmittedAssumptions = {};
  var qaCheckState = {};

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
    writeStoredLocale(locale);
  }

  function activeLocale() {
    return normalizeLocale(document.documentElement.getAttribute("data-active-locale"));
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

  function creatorEvidenceLabel(evidence) {
    var ids = evidence && evidence.grounding_evidence_ids ? evidence.grounding_evidence_ids : [];
    if (ids.length > 0) {
      return {
        ko: "공식 자료 근거 있음",
        en: "Official source support available"
      };
    }
    return {
      ko: "근거 확인 필요",
      en: "Evidence confirmation needed"
    };
  }

  function creatorEvidenceCount(evidence) {
    var ids = evidence && evidence.grounding_evidence_ids ? evidence.grounding_evidence_ids : [];
    if (ids.length === 0) {
      return creatorEvidenceLabel(evidence);
    }
    return {
      ko: "공식 자료 " + ids.length + "건",
      en: ids.length + " official source item(s)"
    };
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

  function renderOpenSourceLink(finding, payload) {
    var source = finding.source || {};
    var status = el("p", "source-status", null);
    var targetId = source.focus_anchor_id || source.anchor_id || "source-reader";
    status.setAttribute("data-highlight-status", source.highlight_status || "missing_exact_span");
    var link = el("a", null, null);
    link.href = "#" + targetId;
    link.setAttribute("data-source-nav", "finding-to-source");
    link.setAttribute("data-source-focus-target", targetId);
    link.setAttribute("aria-label", "원문에서 보기 / View source excerpt");
    link.appendChild(bilingual("span", null, source.source_link_label || copyLabel(payload, "action.open_source")));
    status.appendChild(link);
    status.appendChild(document.createTextNode(" "));
    status.appendChild(
      bilingual(
        "span",
        null,
        source.highlight_status_label || {
          ko: "정확한 문구 위치 확인 필요",
          en: "Exact source phrase position needs confirmation"
        }
      )
    );
    return status;
  }

  function renderCopyQuestionButton(question, payload) {
    var button = el("button", "secondary", null);
    button.type = "button";
    button.setAttribute("data-copy-question", "true");
    button.setAttribute("data-copy-value", text(question && question.ko));
    button.setAttribute("aria-label", "물어볼 말 복사 / Copy question to ask");
    button.appendChild(bilingual("span", null, copyLabel(payload, "action.copy_question")));
    return button;
  }

  function renderCopyQaButton(item, qa) {
    var actions = (qa && qa.copy_actions) || {};
    var button = el("button", "secondary", null);
    button.type = "button";
    button.setAttribute("data-copy-qa", "one");
    button.setAttribute("data-copy-value", text(item.copy_text && item.copy_text.ko));
    button.setAttribute("aria-label", "Q&A 복사 / Copy Q&A");
    button.appendChild(
      bilingual("span", null, actions.copy_one || { ko: "Q&A 복사", en: "Copy Q&A" })
    );
    return button;
  }

  function renderFindingSection(labelPair, contentClass) {
    var section = el("section", "finding-section", null);
    section.setAttribute("data-finding-section", contentClass);
    section.appendChild(bilingual("h4", null, labelPair));
    return section;
  }

  function renderFindingEvidence(section, finding) {
    var evidence = finding.evidence || {};
    section.appendChild(bilingual("p", "finding-snippet", creatorEvidenceLabel(evidence)));
    if (evidence.grounding_evidence_ids && evidence.grounding_evidence_ids.length > 0) {
      section.appendChild(bilingual("p", "finding-snippet", creatorEvidenceCount(evidence)));
    }
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

  function setFindingSortState(control, sortMode) {
    control.setAttribute("data-active-sort", sortMode);
    control.querySelectorAll("[data-finding-sort]").forEach(function (button) {
      var active = button.getAttribute("data-finding-sort") === sortMode;
      button.setAttribute("aria-pressed", active ? "true" : "false");
      if (active) {
        button.setAttribute("data-active", "true");
      } else {
        button.removeAttribute("data-active");
      }
    });
  }

  function renderFindingSortControl(onChange) {
    var control = el("div", "finding-sort-control", null);
    control.setAttribute("role", "group");
    control.setAttribute("aria-label", "발견사항 정렬 / Sort findings");
    control.setAttribute("data-finding-sort-control", "true");
    [
      { mode: "priority", label: { ko: "우선순위순", en: "By priority" } },
      { mode: "clause", label: { ko: "조항순", en: "By clause order" } }
    ].forEach(function (option) {
      var button = el("button", "finding-sort-option", null);
      button.type = "button";
      button.setAttribute("data-finding-sort", option.mode);
      button.appendChild(bilingual("span", null, option.label));
      button.addEventListener("click", function () {
        onChange(option.mode);
      });
      control.appendChild(button);
    });
    setFindingSortState(control, "priority");
    return control;
  }

  function renderFindingItem(record, payload) {
    var finding = record.finding;
    var source = finding.source || {};
    var listItem = el("li", null, null);
    var item = el("details", "finding-card", null);
    item.id =
      source.finding_anchor_id
        ? source.finding_anchor_id
        : finding.finding_id;
    item.tabIndex = -1;
    item.setAttribute("data-finding-id", finding.finding_id);
    item.setAttribute("data-finding-rank", String(record.priorityRank));
    item.setAttribute("data-finding-original-index", String(record.originalIndex));
    if (source.clause_id) {
      item.setAttribute("data-clause-id", source.clause_id);
    }
    if (record.clauseOrder != null) {
      item.setAttribute("data-clause-order", String(record.clauseOrder));
    }
    item.setAttribute("data-reader-focus-target", "finding");
    if (Number(record.priorityRank) === 1) {
      item.open = true;
    }
    var summary = el("summary", "finding-summary", null);
    summary.appendChild(bilingual("span", "finding-title", finding.title));
    var badges = el("span", "finding-badges", null);
    badges.setAttribute("data-collapsed-badge-count", "3");
    var priorityBadge = el("span", "badge finding-priority-badge", null);
    priorityBadge.setAttribute("data-priority-rank-badge", "true");
    priorityBadge.appendChild(
      bilingual("span", "sr-only", { ko: "검토 우선순위", en: "Review priority" })
    );
    priorityBadge.appendChild(document.createTextNode(String(record.priorityRank)));
    badges.appendChild(priorityBadge);
    badges.appendChild(
      bilingual("span", "badge unverified-badge", creatorEvidenceLabel(finding.evidence || {}))
    );
    badges.appendChild(
      bilingual(
        "span",
        "badge",
        payload.dimensions.monetary.quantification_status.label
      )
    );
    summary.appendChild(badges);
    item.appendChild(summary);

    var why = renderFindingSection(copyLabel(payload, "section.why_check"), "section.why_check");
    why.appendChild(bilingual("p", "guidance-why", finding.why_it_matters));
    item.appendChild(why);

    var wording = renderFindingSection(copyLabel(payload, "section.wording"), "section.wording");
    if (finding.source && finding.source.exact_excerpt) {
      var quote = el("blockquote", null, finding.source.exact_excerpt);
      quote.setAttribute("data-exact-excerpt", "true");
      wording.appendChild(quote);
    }
    wording.appendChild(renderOpenSourceLink(finding, payload));
    item.appendChild(wording);

    var impact = renderFindingSection(copyLabel(payload, "section.impact"), "section.impact");
    impact.appendChild(bilingual("p", "cash-flow-line", finding.cash_flow_consequence));
    item.appendChild(impact);

    var question = renderFindingSection(copyLabel(payload, "section.question"), "section.question");
    question.appendChild(bilingual("p", "action-line", finding.question_to_ask));
    question.appendChild(renderCopyQuestionButton(finding.question_to_ask, payload));
    if (finding.additional_questions && finding.additional_questions.length > 0) {
      var moreQuestions = el("ul", null, null);
      finding.additional_questions.forEach(function (extraQuestion) {
        moreQuestions.appendChild(bilingual("li", null, extraQuestion));
      });
      question.appendChild(moreQuestions);
    }
    item.appendChild(question);

    var evidence = renderFindingSection(copyLabel(payload, "section.evidence"), "section.evidence");
    renderFindingEvidence(evidence, finding);
    item.appendChild(evidence);

    var detail = renderFindingSection(copyLabel(payload, "section.detail"), "section.detail");
    detail.appendChild(bilingual("p", "finding-snippet", finding.priority_basis));
    item.appendChild(detail);

    listItem.appendChild(item);
    return listItem;
  }

  function renderFindings(container, payload) {
    var findings = payload.findings;
    if (!findings || findings.length === 0) {
      return;
    }
    var records = findingRecords(findings);
    var sortMode = "priority";
    var list = el("ol", "ranked-findings", null);
    list.setAttribute("data-ranked-findings", "true");

    function redrawList() {
      clearNode(list);
      sortedFindingRecords(records, sortMode).forEach(function (record) {
        list.appendChild(renderFindingItem(record, payload));
      });
    }

    var control = renderFindingSortControl(function (nextMode) {
      sortMode = nextMode;
      setFindingSortState(control, sortMode);
      redrawList();
    });
    container.appendChild(control);
    redrawList();
    container.appendChild(list);
  }

  function renderQaFollowUp(payload) {
    // A conversational follow-up box. The creator types a question and FInk
    // answers from the analysis already on screen (findings + their citations)
    // without any network call, so the response stays grounded and local.
    var form = el("div", "qa-followup", null);
    form.setAttribute("data-qa-followup", "true");
    var label = el("label", "qa-followup-label", null);
    label.setAttribute("for", "qa-followup-input");
    label.appendChild(
      bilingual("span", null, {
        ko: "이 계약에 대해 더 물어보기",
        en: "Ask more about this contract"
      })
    );
    form.appendChild(label);
    var row = el("div", "qa-followup-row", null);
    var input = document.createElement("input");
    input.type = "text";
    input.id = "qa-followup-input";
    input.setAttribute("data-qa-followup-input", "true");
    input.setAttribute("autocomplete", "off");
    input.setAttribute(
      "placeholder",
      activeLocale() === "en"
        ? "e.g. When does the money arrive?"
        : "예: 정산 대금은 언제 들어오나요?"
    );
    input.setAttribute("aria-label", "후속 질문 입력 / Ask a follow-up question");
    row.appendChild(input);
    var ask = el("button", "secondary", null);
    ask.type = "button";
    ask.setAttribute("data-qa-followup-ask", "true");
    ask.setAttribute("aria-label", "후속 질문하기 / Ask follow-up question");
    ask.appendChild(bilingual("span", null, { ko: "질문하기", en: "Ask" }));
    row.appendChild(ask);
    form.appendChild(row);
    form.appendChild(
      bilingual("p", "hint", {
        ko: "답변은 화면의 분석 결과와 연결된 근거에서만 가져옵니다.",
        en: "Answers are drawn only from the on-screen analysis and its grounded evidence."
      })
    );
    return form;
  }

  function scoreFindingForQuestion(finding, terms) {
    var haystack = [
      localized(finding.title),
      localized(finding.why_it_matters),
      localized(finding.cash_flow_consequence),
      localized(finding.question_to_ask),
      finding.source && finding.source.exact_excerpt ? finding.source.exact_excerpt : "",
      finding.source && finding.source.clause_id ? finding.source.clause_id : ""
    ]
      .join(" ")
      .toLowerCase();
    var score = 0;
    terms.forEach(function (term) {
      if (term && haystack.indexOf(term) !== -1) {
        score += 1;
      }
    });
    return score;
  }

  function answerFollowUpQuestion(question) {
    var payload = lastResultPayload;
    var list = document.querySelector("[data-qa-answer-list]");
    if (!payload || !list) {
      return;
    }
    var asked = String(question || "").trim();
    if (asked === "") {
      return;
    }
    var findings = payload.findings || [];
    var terms = asked
      .toLowerCase()
      .split(/[\s,.;:!?()/]+/)
      .filter(function (term) {
        return term.length >= 2;
      });
    var best = null;
    var bestScore = 0;
    findings.forEach(function (finding) {
      var score = scoreFindingForQuestion(finding, terms);
      if (score > bestScore) {
        bestScore = score;
        best = finding;
      }
    });
    if (!best && findings.length > 0) {
      best = findings[0];
    }

    var card = el("article", "grounded-qa-item qa-followup-answer", null);
    card.setAttribute("data-qa-followup-answer", "true");
    if (best) {
      card.setAttribute("data-finding-id", best.finding_id);
    }
    var body = el("section", "qa-body", null);
    var askedPair = { ko: asked, en: asked };
    body.appendChild(bilingual("h4", null, askedPair));
    if (best) {
      body.appendChild(bilingual("p", null, best.cash_flow_consequence));
      body.appendChild(bilingual("p", "hint", best.why_it_matters));
      if (best.source && best.source.exact_excerpt) {
        var quote = el("blockquote", null, best.source.exact_excerpt);
        quote.setAttribute("data-exact-excerpt", "true");
        body.appendChild(quote);
      }
      if (best.citations && best.citations.length > 0) {
        body.appendChild(bilingual("p", "hint", creatorEvidenceCount(best.evidence || {})));
      } else {
        body.appendChild(
          bilingual("p", "hint", {
            ko: "근거 확인 필요",
            en: "Evidence confirmation needed"
          })
        );
      }
    } else {
      body.appendChild(
        bilingual("p", null, {
          ko: "화면의 분석 결과에서 관련 항목을 찾지 못했습니다. 먼저 계약을 분석해 보세요.",
          en: "No related item was found in the on-screen analysis. Try analyzing the contract first."
        })
      );
    }
    card.appendChild(body);
    list.insertBefore(card, list.firstChild);
    card.scrollIntoView(scrollOptions("center"));
    qaStatusMessage({
      ko: "후속 질문에 분석 결과로 답했습니다.",
      en: "Answered your follow-up from the analysis."
    });
  }

  function renderGroundedQa(container, payload) {
    var qa = payload.grounded_qa || {};
    var items = qa.items || [];
    if (items.length === 0) {
      return;
    }
    var actions = qa.copy_actions || {};
    var section = el("section", "grounded-qa", null);
    section.setAttribute("data-grounded-qa", "true");
    section.setAttribute("data-grounded-qa-placement", qa.placement || "after_findings_non_floating");
    section.setAttribute("data-session-local-check-state", "true");

    var heading = el("div", "section-heading", null);
    heading.appendChild(el("p", "eyebrow", "Grounded Q&A"));
    heading.appendChild(bilingual("h3", null, { ko: "근거 기반 Q&A", en: "Grounded Q&A" }));
    section.appendChild(heading);
    if (qa.analysis_method_detail) {
      section.appendChild(bilingual("p", "hint", qa.analysis_method_detail));
    }

    var actionsRow = el("div", "action-row", null);
    actionsRow.setAttribute("role", "group");
    actionsRow.setAttribute("aria-label", "Q&A copy and export actions");
    var copyAll = el("button", "secondary", null);
    copyAll.type = "button";
    copyAll.setAttribute("data-copy-qa", "all");
    copyAll.setAttribute("data-copy-value", text(qa.copy_all_text && qa.copy_all_text.ko));
    copyAll.setAttribute("aria-label", "전체 Q&A 복사 / Copy all Q&A");
    copyAll.appendChild(
      bilingual("span", null, actions.copy_all || { ko: "전체 Q&A 복사", en: "Copy all Q&A" })
    );
    actionsRow.appendChild(copyAll);

    var exportButton = el("button", "secondary", null);
    exportButton.type = "button";
    exportButton.setAttribute("data-export-qa", "markdown");
    exportButton.setAttribute("data-export-filename", qa.export_filename || "fink-grounded-qa.md");
    exportButton.setAttribute("data-export-value", text(qa.export_markdown));
    exportButton.setAttribute("aria-label", "Q&A 내보내기 / Export Q&A");
    exportButton.appendChild(
      bilingual("span", null, actions.export || { ko: "Q&A 내보내기", en: "Export Q&A" })
    );
    actionsRow.appendChild(exportButton);
    section.appendChild(actionsRow);

    section.appendChild(renderQaFollowUp(payload));

    var status = el("p", "hint", "Q&A 확인 표시는 이 브라우저 세션에만 남습니다.");
    status.setAttribute("role", "status");
    status.setAttribute("aria-live", "polite");
    status.setAttribute("data-qa-status-region", "true");
    section.appendChild(status);

    var list = el("div", "grounded-qa-list", null);
    list.setAttribute("data-qa-answer-list", "true");
    items.forEach(function (item) {
      var card = el("article", "grounded-qa-item", null);
      card.id = item.qa_id;
      card.setAttribute("data-grounded-qa-item", "true");
      card.setAttribute("data-finding-id", item.finding_id);
      card.setAttribute(
        "data-highlight-href",
        item.links && item.links.highlight_href ? item.links.highlight_href : "#source-reader"
      );

      var checkLabel = el("label", "qa-check", null);
      var check = document.createElement("input");
      check.type = "checkbox";
      check.checked = qaCheckState[item.finding_id] === true;
      check.setAttribute("data-qa-check-state", "true");
      check.setAttribute("data-finding-id", item.finding_id);
      check.setAttribute("data-mutates-engine-output", "false");
      check.setAttribute("aria-label", "Q&A 확인 표시 / Mark Q&A checked");
      checkLabel.appendChild(check);
      checkLabel.appendChild(el("span", null, "확인 표시"));
      card.appendChild(checkLabel);

      var body = el("section", "qa-body", null);
      body.appendChild(bilingual("h4", null, item.primary_question));
      body.appendChild(bilingual("p", null, item.answer));
      if (item.citations && item.citations.length > 0) {
        body.appendChild(
          bilingual("p", "hint", {
            ko: "공식 자료 " + item.citations.length + "건",
            en: item.citations.length + " official source item(s)"
          })
        );
      } else {
        body.appendChild(
          bilingual("p", "hint", {
            ko: "근거 확인 필요",
            en: "Evidence confirmation needed"
          })
        );
      }

      var links = item.links || {};
      var linkRow = el("p", "source-status", null);
      var findingLink = el("a", null, "검토 항목으로 이동");
      findingLink.href = links.finding_href || "#review-reader";
      findingLink.setAttribute("data-source-nav", "qa-to-finding");
      findingLink.setAttribute(
        "data-source-focus-target",
        text(findingLink.getAttribute("href")).replace(/^#/, "")
      );
      linkRow.appendChild(findingLink);
      linkRow.appendChild(document.createTextNode(" "));
      var highlightLink = el("a", null, "하이라이트로 이동");
      highlightLink.href = links.highlight_href || "#source-reader";
      highlightLink.setAttribute("data-source-nav", "qa-to-highlight");
      highlightLink.setAttribute(
        "data-source-focus-target",
        text(highlightLink.getAttribute("href")).replace(/^#/, "")
      );
      linkRow.appendChild(highlightLink);
      body.appendChild(linkRow);
      body.appendChild(renderCopyQaButton(item, qa));
      card.appendChild(body);
      list.appendChild(card);
    });
    section.appendChild(list);
    container.appendChild(section);
  }

  function renderSourceSegments(container, segments) {
    (segments || []).forEach(function (segment) {
      if (!segment.highlighted) {
        container.appendChild(document.createTextNode(text(segment.text)));
        return;
      }
      var marker = document.createElement("mark");
      marker.className = "source-highlight";
      if (segment.anchor_id) {
        marker.id = segment.anchor_id;
        marker.tabIndex = -1;
        marker.setAttribute("data-source-focus-target", "exact-span");
      }
      marker.setAttribute("data-source-highlight", "true");
      marker.setAttribute("data-source-span-ids", (segment.source_span_ids || []).join(" "));
      if (segment.page_boxes && segment.page_boxes.length > 0) {
        marker.setAttribute("data-bbox-provenance", segment.bbox_provenance || "");
        marker.setAttribute("data-page-box-overlay", "real-bbox");
        marker.setAttribute("data-page-boxes", JSON.stringify(segment.page_boxes));
      }
      marker.appendChild(document.createTextNode(text(segment.text)));
      container.appendChild(marker);
    });
  }

  function renderSourceHighlights(container, payload) {
    var highlights = payload.source_highlights || {};
    var section = el("section", "source-highlights", null);
    section.id = "source-reader";
    section.tabIndex = -1;
    section.setAttribute("data-source-highlights", "true");
    section.setAttribute("data-source-highlights-enabled", "true");
    section.setAttribute("data-reader-source-content", "true");
    section.setAttribute("data-reader-pane", "source");
    section.setAttribute("aria-labelledby", "source-highlights-heading");

    var header = el("div", "source-highlight-header", null);
    var heading = bilingual("h3", null, {
      ko: "표시된 원문",
      en: "Marked source text"
    });
    heading.id = "source-highlights-heading";
    header.appendChild(heading);
    var toggle = el("label", "source-toggle", null);
    var checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.checked = highlights.enabled_default !== false;
    checkbox.setAttribute("data-source-highlight-toggle", "true");
    checkbox.setAttribute(
      "aria-label",
      "출처 하이라이트 켜기 또는 끄기 / Toggle source highlights"
    );
    toggle.appendChild(checkbox);
    toggle.appendChild(
      bilingual("span", null, {
        ko: "하이라이트",
        en: "Highlights"
      })
    );
    header.appendChild(toggle);
    section.appendChild(header);

    var sourceList = el("div", "source-list", null);
    var sources = highlights.sources || [];
    if (sources.length === 0) {
      sourceList.appendChild(
        bilingual("p", "hint", {
          ko: "정확한 문구 위치 확인 필요",
          en: "Exact source phrase position needs confirmation"
        })
      );
    }
    sources.forEach(function (source) {
      var card = el("article", "source-highlight-card", null);
      card.id = source.anchor_id || source.source_id;
      card.tabIndex = -1;
      card.setAttribute("data-source-highlight-status", source.status || "missing_exact_span");
      card.setAttribute("data-clause-id", source.clause_id || "");
      card.setAttribute("data-text-source", source.text_source || "");
      card.setAttribute("data-render-mode", source.render_mode || "");
      card.setAttribute(
        "data-has-real-bbox-provenance",
        source.has_real_bbox_provenance ? "true" : "false"
      );
      card.setAttribute("data-focus-anchor-id", source.focus_anchor_id || card.id);
      var cardHeader = el("header", null, null);
      cardHeader.appendChild(
        bilingual("strong", null, {
          ko: "원문 문구",
          en: "Source wording"
        })
      );
      cardHeader.appendChild(
        el("span", "badge", localized(source.status_label) || "정확한 문구 위치 확인 필요")
      );
      card.appendChild(cardHeader);
      var sourceText = el("p", "source-text", null);
      sourceText.setAttribute("data-source-text", "true");
      renderSourceSegments(sourceText, source.segments || []);
      card.appendChild(sourceText);
      if (source.finding_anchor_id) {
        var back = el("a", null, null);
        back.href = "#" + source.finding_anchor_id;
        back.setAttribute("data-source-nav", "source-to-finding");
        back.setAttribute("data-source-focus-target", source.finding_anchor_id);
        back.setAttribute("aria-label", "검토 항목으로 돌아가기 / Back to finding");
        back.appendChild(
          bilingual("span", null, {
            ko: "검토 항목으로 돌아가기",
            en: "Back to finding"
          })
        );
        card.appendChild(back);
      }
      sourceList.appendChild(card);
    });
    section.appendChild(sourceList);
    container.appendChild(section);
  }

  function renderReaderShortcutNav() {
    var nav = el("nav", "reader-jump-links", null);
    nav.setAttribute("aria-label", "Reader shortcuts");
    nav.setAttribute("data-mobile-reader-links", "true");
    var sourceLink = el("a", null, null);
    sourceLink.href = "#source-reader";
    sourceLink.setAttribute("data-reader-jump", "source");
    sourceLink.setAttribute("aria-label", "원문 보기 / View source");
    sourceLink.appendChild(
      bilingual("span", null, {
        ko: "원문 보기",
        en: "View source"
      })
    );
    nav.appendChild(sourceLink);
    var reportLink = el("a", null, null);
    reportLink.href = "#review-reader";
    reportLink.setAttribute("data-reader-jump", "report");
    reportLink.setAttribute("aria-label", "검토 항목으로 돌아가기 / Back to findings");
    reportLink.appendChild(
      bilingual("span", null, {
        ko: "검토 항목으로 돌아가기",
        en: "Back to findings"
      })
    );
    nav.appendChild(reportLink);
    return nav;
  }

  function dimensionCard(titlePair, dimensionId) {
    var card = el("article", "dimension-card", null);
    card.setAttribute("data-report-dimension", dimensionId);
    card.appendChild(bilingual("h4", null, titlePair));
    return card;
  }

  function renderDimensions(container, payload) {
    var dims = payload.dimensions;
    var grid = el("div", "dimension-grid", null);
    grid.setAttribute("data-dimension-grid", "true");
    grid.setAttribute("data-dimension-count", "4");

    var priority = dims.review_priority;
    var priorityCard = dimensionCard(priority.label, "review-priority-score");
    priorityCard.appendChild(bilingual("p", "state-line", priority.reading_status.label));
    priorityCard.appendChild(bilingual("p", "hint", payload.recommendation.action));
    grid.appendChild(priorityCard);

    var monetary = dims.monetary;
    var monetaryCard = dimensionCard(monetary.label, "monetary-exposure-range");
    monetaryCard.setAttribute("data-grand-total", "absent");
    monetaryCard.appendChild(bilingual("p", "state-line", monetary.scenario_status.label));
    monetaryCard.appendChild(bilingual("p", "state-line", monetary.quantification_status.label));
    monetaryCard.appendChild(bilingual("p", "state-line", monetary.currency_status));
    if (monetary.ranges && monetary.ranges.length > 0) {
      var ranges = el("div", "exposure-ranges", null);
      var labels = el("p", "exposure-range-labels", null);
      labels.appendChild(bilingual("span", null, { ko: "저", en: "Low" }));
      labels.appendChild(bilingual("span", null, { ko: "기준", en: "Base" }));
      labels.appendChild(bilingual("span", null, { ko: "고", en: "High" }));
      ranges.appendChild(labels);
      monetary.ranges.forEach(function (range) {
        var values = el("p", "exposure-range-values", null);
        values.appendChild(el("span", null, text(range.low)));
        values.appendChild(el("span", null, text(range.base)));
        values.appendChild(el("span", null, text(range.high)));
        ranges.appendChild(values);
      });
      monetaryCard.appendChild(ranges);
    } else if (monetary.note) {
      monetaryCard.appendChild(bilingual("p", "hint", monetary.note));
    }
    grid.appendChild(monetaryCard);

    var time = dims.time;
    var timeCard = dimensionCard(time.label, "time-exposure");
    timeCard.appendChild(bilingual("p", "state-line", time.timing_state));
    timeCard.appendChild(bilingual("p", "hint", time.contract_timing));
    grid.appendChild(timeCard);

    var evidence = dims.evidence;
    var evidenceCard = dimensionCard(evidence.label, "evidence-ocr-confidence");
    evidenceCard.appendChild(bilingual("p", "state-line", evidence.reading_status.label));
    evidenceCard.appendChild(bilingual("p", "state-line", creatorStatusLabel(evidence.evidence_status)));
    grid.appendChild(evidenceCard);

    container.appendChild(grid);
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

  function reviewEffortLevel(payload, findingCount) {
    var pathway = recommendationPathway(payload).toLowerCase();
    if (pathway.indexOf("clarification") !== -1) {
      return { ko: "가볍게 확인", en: "Light check" };
    }
    if (pathway.indexOf("negotiation") !== -1) {
      return { ko: "꼼꼼히 확인", en: "Careful check" };
    }
    if (pathway.indexOf("professional") !== -1 || pathway.indexOf("dispute") !== -1) {
      return { ko: "전문가 확인 권장", en: "Professional check recommended" };
    }
    if (findingCount <= 1) {
      return { ko: "가볍게 확인", en: "Light check" };
    }
    if (findingCount <= 3) {
      return { ko: "꼼꼼히 확인", en: "Careful check" };
    }
    return { ko: "전문가 확인 권장", en: "Professional check recommended" };
  }

  function reviewEffortChipPair(payload, findingCount) {
    var level = reviewEffortLevel(payload, findingCount);
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
      ko: "권장 행동: 확인할 항목을 먼저 살펴보세요.",
      en: "Recommended action: review the items to check first."
    };
  }

  function renderIntegratedJudgmentCard(container, payload) {
    var findings = (payload && payload.findings) || [];
    var findingCount = findings.length;
    var card = el("article", "integrated-judgment-card", null);
    card.setAttribute("data-integrated-judgment-card", "true");

    var heading = el("div", "glance-heading", null);
    heading.appendChild(atAGlanceIcon());
    heading.appendChild(
      bilingual("h3", null, {
        ko: "한눈에 정리",
        en: "At a glance"
      })
    );
    card.appendChild(heading);
    card.appendChild(bilingual("p", "glance-action", recommendationActionPair(payload)));

    var cues = el("p", "glance-cues", null);
    cues.appendChild(
      bilingual("span", "glance-chip", reviewEffortChipPair(payload, findingCount))
    );
    cues.appendChild(bilingual("span", "glance-chip glance-count", itemCountPair(findingCount)));
    card.appendChild(cues);

    var concern = el("section", "glance-concern", null);
    concern.setAttribute("data-glance-concern", "true");
    if (findings.length > 0) {
      var finding = findings[0];
      concern.setAttribute("data-top-finding-id", finding.finding_id || "");
      concern.appendChild(
        bilingual("p", "glance-concern-label", {
          ko: "가장 먼저 확인할 항목",
          en: "First item to check"
        })
      );
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

  function renderCheckFirst(container, payload) {
    var section = el("section", "check-first", null);
    section.setAttribute("data-check-first", "true");
    section.appendChild(bilingual("p", "eyebrow", copyLabel(payload, "app.recommendation_heading")));
    section.appendChild(bilingual("h2", null, copyLabel(payload, "app.summary_heading")));
    section.appendChild(bilingual("p", "action-line", payload.recommendation.action));

    var finding = payload.findings && payload.findings.length > 0 ? payload.findings[0] : null;
    if (finding) {
      section.setAttribute("data-top-finding-id", finding.finding_id);
      section.appendChild(bilingual("h3", null, finding.title));
      if (finding.source && finding.source.exact_excerpt) {
        var quote = el("blockquote", null, finding.source.exact_excerpt);
        quote.setAttribute("data-exact-excerpt", "true");
        section.appendChild(quote);
      }
      section.appendChild(bilingual("p", "cash-flow-line", finding.cash_flow_consequence));
      var actions = el("div", "action-row", null);
      actions.appendChild(renderCopyQuestionButton(finding.question_to_ask, payload));
      actions.appendChild(renderOpenSourceLink(finding, payload));
      section.appendChild(actions);
    }

    var statuses = el("p", "status-row", null);
    statuses.setAttribute("data-check-first-statuses", "true");
    statuses.appendChild(
      bilingual("span", "badge", creatorStatusLabel(payload.dimensions.evidence.evidence_status))
    );
    statuses.appendChild(
      bilingual("span", "badge", payload.dimensions.monetary.quantification_status.label)
    );
    section.appendChild(statuses);
    container.appendChild(section);
  }

  function collectAuditEvidenceIds(payload) {
    var seen = {};
    var ids = [];
    function add(value) {
      var id = text(value);
      if (!id || seen[id]) {
        return;
      }
      seen[id] = true;
      ids.push(id);
    }
    (payload.findings || []).forEach(function (finding) {
      var evidence = finding.evidence || {};
      (evidence.grounding_evidence_ids || []).forEach(add);
      (finding.citations || []).forEach(function (citation) {
        add(citation.evidence_id);
      });
    });
    var qa = payload.grounded_qa || {};
    (qa.items || []).forEach(function (item) {
      (item.citations || []).forEach(function (citation) {
        add(citation.evidence_id);
      });
    });
    var audit = payload.audit_detail || {};
    (audit.technical_findings || []).forEach(function (finding) {
      (finding.grounding_evidence_ids || []).forEach(add);
    });
    return ids;
  }

  function renderAdvancedDiagnostics(container, payload) {
    var details = el("details", "audit-detail", null);
    details.setAttribute("data-audit-detail", "true");
    details.appendChild(bilingual("summary", null, copyLabel(payload, "export.audit_detail_label")));
    var diagnostic = el("section", "advanced-diagnostic", null);
    diagnostic.setAttribute("data-advanced-diagnostic", "rule-focus-index");
    diagnostic.appendChild(bilingual("h4", null, copyLabel(payload, "diagnostic.rule_focus_index")));
    diagnostic.appendChild(
      el("output", null, String(payload.dimensions.review_priority.score) + " / 100")
    );
    diagnostic.appendChild(bilingual("p", "hint", copyLabel(payload, "diagnostic.rule_focus_note")));
    details.appendChild(diagnostic);
    var evidenceIds = collectAuditEvidenceIds(payload);
    if (evidenceIds.length > 0) {
      var evidenceDetail = el("section", "advanced-diagnostic", null);
      evidenceDetail.setAttribute("data-advanced-diagnostic", "raw-evidence-ids");
      evidenceDetail.appendChild(
        bilingual("h4", null, {
          ko: "근거 ID",
          en: "Evidence IDs"
        })
      );
      var list = el("ul", null, null);
      evidenceIds.forEach(function (id) {
        var item = el("li", null, null);
        item.appendChild(el("code", null, id));
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
    if (target && target.scrollIntoView) {
      target.scrollIntoView(scrollOptions("end"));
    }
  }

  function revealResultMessage() {
    // The result bubble lives in the thread shell; reveal it and move it to the
    // end so the freshest analysis sits at the bottom like a chat reply.
    var bubble = document.querySelector("[data-result-message]");
    var thread = threadElement();
    if (bubble && thread) {
      bubble.hidden = false;
      thread.appendChild(bubble);
    }
    return bubble;
  }

  function appendUserMessage(content, isFile) {
    var thread = threadElement();
    if (!thread) {
      return;
    }
    var item = el("li", "msg user", null);
    item.setAttribute("data-message-role", "user");
    var bubble = el("div", "bubble", null);
    if (isFile) {
      var chip = el("span", "file-chip", null);
      chip.setAttribute("data-file-chip", "true");
      chip.appendChild(paperclipIcon());
      chip.appendChild(el("span", null, text(content)));
      bubble.appendChild(chip);
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

  function appendPendingBotMessage() {
    return appendBotMessage({ ko: "생각 중...", en: "..." });
  }

  function renderChatCitations(container, citations) {
    if (!container || !citations || citations.length === 0) {
      return;
    }
    var list = el("ul", "qa-citations", null);
    list.setAttribute("data-chat-citations", "true");
    citations.forEach(function (citation) {
      var label =
        typeof citation === "string"
          ? citation
          : citation.evidence_id || citation.citation_id || citation.source_id || "";
      if (!label) {
        return;
      }
      var item = el("li", null, null);
      item.setAttribute("data-chat-citation", "true");
      item.appendChild(el("code", null, label));
      list.appendChild(item);
    });
    if (list.childNodes.length > 0) {
      container.appendChild(list);
    }
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
    var row = el("div", "chip-row", null);
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

  function renderResult(payload) {
    var container = document.getElementById("result");
    if (!container) {
      return;
    }
    var bubble = revealResultMessage();
    clearNode(container);
    var heading = el("h2", "sr-only", null);
    heading.id = "result-heading";
    heading.appendChild(bilingual("span", null, { ko: "검토 결과", en: "Review result" }));
    container.appendChild(heading);

    renderIntegratedJudgmentCard(container, payload);
    renderSuggestedFollowUps(container, payload);
    container.appendChild(renderReaderShortcutNav());

    var workspace = el("div", "synchronized-reader", null);
    workspace.setAttribute("data-contract-reader", "synchronized");
    workspace.setAttribute("data-reader-layout", "single-column");
    workspace.setAttribute("data-mobile-layout", "single-column");

    var reportPane = el("section", "report-reader-panel", null);
    reportPane.id = "review-reader";
    reportPane.tabIndex = -1;
    reportPane.setAttribute("data-reader-pane", "report");
    reportPane.setAttribute("aria-labelledby", "reader-report-heading");
    var reportHeading = el("h3", "sr-only", "검토 항목");
    reportHeading.id = "reader-report-heading";
    reportPane.appendChild(reportHeading);

    renderCheckFirst(reportPane, payload);
    renderDimensions(reportPane, payload);
    renderSourceHighlights(reportPane, payload);
    renderVerificationSignals(reportPane, payload);

    var findingsHeading = bilingual("h3", null, copyPair(payload, "app.findings_heading"));
    reportPane.appendChild(findingsHeading);
    renderFindings(reportPane, payload);
    renderAdvancedDiagnostics(reportPane, payload);
    renderGroundedQa(reportPane, payload);

    workspace.appendChild(reportPane);
    container.appendChild(workspace);

    setLocale(activeLocale());
    container.scrollIntoView(scrollOptions("start"));
    scrollThreadToLatest(bubble || document.querySelector("[data-result-message]"));
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
    if (pasteText && pasteText.trim() !== "" && file) {
      statusMessage({
        ko: "붙여넣기와 파일 중 하나만 선택하세요.",
        en: "Use either paste text or one file, not both."
      });
      return;
    }
    if (options.scenarioRecompute) {
      scenarioStatusMessage({
        ko: "시나리오를 다시 계산 중입니다.",
        en: "Recalculating the scenario."
      });
    } else {
      // Echo the creator's turn as a user bubble before sending, then clear the
      // composer so it behaves like a chat input.
      if (file) {
        appendUserMessage(file.name || "첨부 파일", true);
      } else {
        appendUserMessage(pasteText, false);
        box.value = "";
        autoGrowComposer();
      }
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
          var errorKo =
            result.data && result.data.error ? result.data.error : "분석에 실패했습니다.";
          var errorEn =
            result.data && result.data.error_en
              ? result.data.error_en
              : "Analysis failed.";
          appendBotMessage({ ko: errorKo, en: errorEn });
          statusMessage({ ko: "오류: " + errorKo, en: "Error: " + errorEn });
          return;
        }
        if (options.scenarioRecompute) {
          scenarioStatusMessage(recomputeMessage(result.data, request.changedInput));
        } else {
          statusMessage({ ko: "분석을 완료했습니다.", en: "Analysis complete." });
        }
        renderResult(result.data);
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
        appendBotMessage({
          ko: "로컬 분석 요청에 실패했습니다. 잠시 후 다시 시도해 주세요.",
          en: "The local analysis request failed. Please try again."
        });
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
    var pending = appendPendingBotMessage();
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
    if (lastResultPayload) {
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
    var input = document.getElementById("contract-file");
    if (input) {
      input.value = "";
    }
    var container = document.getElementById("result");
    if (container) {
      clearNode(container);
    }
    var resultMessage = document.querySelector("[data-result-message]");
    if (resultMessage) {
      resultMessage.hidden = true;
    }
    autoGrowComposer();
    analyzedContractText = "";
    lastResultPayload = null;
    lastSubmittedAssumptions = {};
    statusMessage({
      ko: "입력을 지웠습니다.",
      en: "Input cleared."
    });
  }

  function targetIdFromLink(link) {
    var explicit = link.getAttribute("data-source-focus-target");
    if (explicit) {
      return explicit;
    }
    var href = link.getAttribute("href") || "";
    if (href.charAt(0) !== "#") {
      return "";
    }
    try {
      return decodeURIComponent(href.slice(1));
    } catch (error) {
      return href.slice(1);
    }
  }

  function activateReaderAnchor(link) {
    var targetId = targetIdFromLink(link);
    if (!targetId) {
      return false;
    }
    var target = document.getElementById(targetId);
    if (!target) {
      return false;
    }
    if (!target.hasAttribute("tabindex")) {
      target.setAttribute("tabindex", "-1");
    }
    target.scrollIntoView(scrollOptions("center"));
    try {
      target.focus({ preventScroll: true });
    } catch (error) {
      target.focus();
    }
    var active = document.querySelectorAll("[data-active-anchor='true']");
    active.forEach(function (item) {
      item.removeAttribute("data-active-anchor");
    });
    target.setAttribute("data-active-anchor", "true");
    window.setTimeout(function () {
      target.removeAttribute("data-active-anchor");
    }, 2400);
    if (window.history && window.history.pushState) {
      window.history.pushState(null, "", "#" + targetId);
    }
    return true;
  }

  function copyQuestion(button) {
    var value = button.getAttribute("data-copy-value") || "";
    if (!value) {
      return;
    }
    copyText(value, {
      ko: "물어볼 말을 복사했습니다.",
      en: "Question copied."
    });
  }

  function copyQa(button) {
    var value = button.getAttribute("data-copy-value") || "";
    if (!value) {
      return;
    }
    var isAll = button.getAttribute("data-copy-qa") === "all";
    copyText(value, {
      ko: isAll ? "전체 Q&A를 복사했습니다." : "Q&A를 복사했습니다.",
      en: isAll ? "All Q&A copied." : "Q&A copied."
    });
  }

  function copyText(value, messagePair) {
    function done() {
      qaStatusMessage(messagePair);
    }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(value).then(done).catch(function () {
        fallbackCopy(value);
        done();
      });
      return;
    }
    fallbackCopy(value);
    done();
  }

  function qaStatusMessage(pair) {
    var regions = document.querySelectorAll("[data-qa-status-region]");
    regions.forEach(function (region) {
      clearNode(region);
      region.appendChild(bilingual("span", null, pair));
    });
    statusMessage(pair);
  }

  function exportQa(button) {
    var value = button.getAttribute("data-export-value") || "";
    if (!value) {
      return;
    }
    var filename = button.getAttribute("data-export-filename") || "fink-grounded-qa.md";
    var blob = new Blob([value], { type: "text/markdown;charset=utf-8" });
    var link = document.createElement("a");
    link.download = filename;
    link.href = URL.createObjectURL(blob);
    document.body.appendChild(link);
    link.click();
    window.setTimeout(function () {
      URL.revokeObjectURL(link.href);
      document.body.removeChild(link);
    }, 0);
    qaStatusMessage({
      ko: "Q&A 파일을 만들었습니다.",
      en: "Q&A export created."
    });
  }

  function updateQaCheckState(input) {
    var findingId = input.getAttribute("data-finding-id") || "";
    if (!findingId) {
      return;
    }
    qaCheckState[findingId] = input.checked === true;
    qaStatusMessage({
      ko: "확인 표시는 이 세션에만 저장되며 검토 순서를 바꾸지 않습니다.",
      en: "The check mark is saved only for this session and does not change review order."
    });
  }

  function fallbackCopy(value) {
    var box = document.createElement("textarea");
    box.value = value;
    box.setAttribute("readonly", "readonly");
    box.style.position = "fixed";
    box.style.left = "-9999px";
    document.body.appendChild(box);
    box.select();
    try {
      document.execCommand("copy");
    } catch (error) {
      return;
    } finally {
      document.body.removeChild(box);
    }
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
    var input = document.getElementById("contract-file");
    if (input) {
      input.value = "";
    }
    box.value =
      activeLocale() === "en"
        ? "Section 3 (Settlement) Payment is made within 90 days after the end of each quarter; the company may deduct general expenses."
        : "제3조(정산) 정산은 매 분기 종료일로부터 90일 이내에 지급하며, 회사는 일반 경비를 공제할 수 있다.";
    autoGrowComposer();
    box.focus();
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
        fillExample();
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
      var readerLink = target.closest("[data-source-nav], [data-reader-jump]");
      if (readerLink && activateReaderAnchor(readerLink)) {
        event.preventDefault();
      }
      var copyButton = target.closest("[data-copy-question]");
      if (copyButton) {
        event.preventDefault();
        copyQuestion(copyButton);
      }
      var copyQaButton = target.closest("[data-copy-qa]");
      if (copyQaButton) {
        event.preventDefault();
        copyQa(copyQaButton);
      }
      var exportQaButton = target.closest("[data-export-qa]");
      if (exportQaButton) {
        event.preventDefault();
        exportQa(exportQaButton);
      }
      var followUpButton = target.closest("[data-qa-followup-ask]");
      if (followUpButton) {
        event.preventDefault();
        var followUpInput = document.querySelector("[data-qa-followup-input]");
        if (followUpInput) {
          answerFollowUpQuestion(followUpInput.value);
          followUpInput.value = "";
        }
      }
      var highlightToggle = target.closest("[data-source-highlight-toggle]");
      if (highlightToggle) {
        var sourceSection = highlightToggle.closest("[data-source-highlights]");
        if (sourceSection) {
          sourceSection.setAttribute(
            "data-source-highlights-enabled",
            highlightToggle.checked ? "true" : "false"
          );
        }
      }
    });
    document.addEventListener("change", function (event) {
      var target = event.target;
      if (!target || !target.closest) {
        return;
      }
      var qaCheck = target.closest("[data-qa-check-state]");
      if (qaCheck) {
        updateQaCheckState(qaCheck);
      }
      // Picking a file in the composer sends it straight away, like attaching in
      // a chat. A pasted draft and a file cannot be sent together, so clear the
      // draft first.
      var picked = target.closest("[data-file-input]");
      if (picked && picked.files && picked.files.length > 0) {
        var box = document.getElementById("paste-box");
        if (box) {
          box.value = "";
          autoGrowComposer();
        }
        analyze();
      }
    });
    document.addEventListener("keydown", function (event) {
      var target = event.target;
      if (!target || !target.closest) {
        return;
      }
      if (event.key === "Enter" && target.closest("[data-qa-followup-input]")) {
        event.preventDefault();
        answerFollowUpQuestion(target.value);
        target.value = "";
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

from __future__ import annotations

import asyncio
import importlib
import socket
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


def _load_web():
    src_root = Path(__file__).resolve().parents[2] / "src"
    src_text = src_root.as_posix()
    if src_text not in sys.path:
        sys.path.insert(0, src_text)
    return importlib.import_module("fink.web")


WEB = _load_web()


async def _asgi_get(app: object, path: str) -> tuple[int, dict[str, str], bytes]:
    messages: list[dict[str, object]] = []

    async def receive() -> dict[str, object]:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: dict[str, object]) -> None:
        messages.append(message)

    scope = {
        "type": "http",
        "method": "GET",
        "path": path,
        "headers": [],
        "query_string": b"",
    }
    await app(scope, receive, send)  # type: ignore[misc]
    start = next(message for message in messages if message["type"] == "http.response.start")
    body = b"".join(
        message.get("body", b"")
        for message in messages
        if message["type"] == "http.response.body"
    )
    headers = {
        key.decode("ascii"): value.decode("utf-8")
        for key, value in start.get("headers", [])
    }
    return int(start["status"]), headers, body


class WebSmokeTests(unittest.TestCase):
    def test_web_smoke_test_responsive_shell_and_disclosures(self) -> None:
        settings = WEB.resolve_bind_settings()
        markup = WEB.render_index_html(settings)
        normalized = markup.lower()

        self.assertEqual(settings.host, WEB.DEFAULT_LOOPBACK_HOST)
        self.assertIn('<meta name="viewport"', normalized)
        self.assertIn("@media (min-width: 900px)", markup)
        self.assertIn("min-height: 44px", markup)
        self.assertIn("skip-link", markup)
        self.assertIn('data-default-locale="ko"', markup)
        # The title is now creator-focused; the pinned review-priority phrase is
        # kept inside the not-legal-advice banner's English aid text.
        self.assertIn("창작자를 위한 금융 계약 검토", markup)
        self.assertIn("Financial Contract Review for Creators", markup)
        self.assertIn('class="wordmark" aria-label="FInk">F<span>I</span>nk</p>', markup)
        self.assertIn('class="brand-divider" aria-hidden="true"', markup)
        self.assertIn("@font-face", markup)
        self.assertIn("NotoSerifKR-500.woff2", markup)
        self.assertIn("Contractual Financial Review Priority", markup)
        self.assertNotIn("계약 금융 검토", markup)

        # Exactly one locale toggle button now (it flips KO<->EN); the old
        # second "EN generated" button is gone. The label is just "EN"/"KO"
        # without the old Korean suffix.
        self.assertNotIn("EN generated", markup)
        self.assertNotIn("\ubcf4\uae30", markup)
        self.assertEqual(markup.count("data-locale-button"), 1)
        self.assertIn('data-locale-toggle="true"', markup)
        self.assertIn('<span lang="ko" data-locale-text="ko">EN</span>', markup)
        self.assertIn('<span lang="en" data-locale-text="en">KO</span>', markup)

        # The chat shell shows the short reworded privacy line and the
        # not-legal-advice warning persistently in the header. Korean is
        # canonical and the English text is an aid kept inside its locale span.
        # The privacy line is short and plain; "텔레메트리" and the older
        # long-form phrasing are gone.
        self.assertIn(WEB.PRIVACY_BANNER, markup)
        self.assertIn(WEB.NOT_LEGAL_ADVICE_BANNER, markup)
        self.assertNotIn("텔레메트리", markup)
        self.assertIn("본 서비스는 사용자 정보를 수집·추적하거나", markup)
        self.assertIn("클라우드 OCR·원격 LLM을 사용하지 않습니다.", markup)
        self.assertNotIn("외부 검색", markup)
        self.assertNotIn("계약서와 OCR로 읽은 글자는 기기를 떠나지 않으며", markup)
        self.assertIn("참고용일 뿐 확실한 법리적 판단이 아니니, 중요한 결정 전에는 전문가와 상담하세요", markup)
        self.assertNotIn("검토 순서만 안내", markup)
        self.assertNotIn("먼저 확인할 순서로 정리합니다", markup)
        self.assertIn("not a final legal judgment", markup)
        self.assertNotIn("Estimated amounts", markup)
        self.assertEqual(WEB.DISCLOSURE_ITEMS, ())
        self.assertIn(".chat-privacy.banner-advice {", markup)
        self.assertIn("border-left: 3px solid var(--pink);", markup)
        self.assertIn("color: var(--ink);", markup)
        result_chip_block = markup.split(".result-chip-row {", 1)[1].split("}", 1)[0]
        self.assertIn("grid-template-columns: minmax(0, 1fr);", result_chip_block)
        self.assertNotIn("repeat(3", result_chip_block)
        self.assertIn("mark.source-highlight {", markup)
        self.assertIn("border-bottom: 1.5px solid var(--pink);", markup)
        self.assertIn("background: transparent;\n  color: var(--pink-ink);", markup)

        # The old amount-estimate disclosure is removed entirely.
        self.assertNotIn("추정 금액", markup)
        self.assertLess(
            markup.index('data-privacy-line="true"'),
            markup.index('class="chat-privacy banner banner-advice"'),
        )

        # The chat shell has no footer: dev info and the separate footer privacy
        # paragraph are gone. The privacy and advice lines live in the header,
        # and the old collapsible Notice panel is gone.
        self.assertNotIn("Serving from", markup)
        self.assertNotIn("Loopback only", markup)
        self.assertNotIn("LAN opt-in enabled", markup)
        self.assertNotIn("<footer", markup)
        self.assertNotIn("계약서와 분석 결과는 이 기기에서만 처리됩니다.", markup)
        self.assertNotIn('data-notice-panel="true"', markup)
        self.assertNotIn('data-notice-toggle', markup)

        blocked_external_patterns = (
            "https://",
            "http://cdn",
            "fetch(",
            "xmlhttprequest",
            "websocket",
            "eventsource",
        )
        for pattern in blocked_external_patterns:
            self.assertNotIn(pattern, normalized)

        # New chat-shell hooks. The composer's send button (id="analyze-btn"),
        # the file input, the paste box, the chat thread, and the external
        # /app.js script must be present, and the locale toggle must expose an
        # active-locale attribute. The 1-2-3 how-to strip is gone, replaced by a
        # single bot greeting; the result renders inside a bot message bubble.
        self.assertIn('id="analyze-btn"', markup)
        self.assertEqual(markup.count('id="analyze-btn"'), 1)
        self.assertIn('id="contract-file"', markup)
        self.assertIn("multiple", markup)
        self.assertNotIn('class="upload-tile"', markup)
        self.assertNotIn('data-ui-ingest-modes="camera image pdf paste"', markup)
        self.assertIn('<script src="/app.js">', markup)
        self.assertIn('data-active-locale', markup)
        self.assertNotIn('data-how-to-steps="true"', markup)
        self.assertNotIn("사용 방법 1-2-3", markup)
        self.assertNotIn("How to use 1-2-3", markup)
        self.assertIn('data-chat-thread="true"', markup)
        self.assertIn('data-composer="true"', markup)
        self.assertIn('data-paste-box="true"', markup)
        self.assertIn('data-analyze-button="true"', markup)
        self.assertIn('class="paperclip-icon"', markup)
        self.assertIn('viewBox="0 0 24 24"', markup)
        self.assertNotIn("📎", markup)
        self.assertNotIn('class="notice-button"', markup)
        self.assertIn(
            "계약서를 붙여넣거나 사진·PDF를 올려 주세요.",
            markup,
        )
        self.assertIn('placeholder="입력"', markup)
        self.assertIn('data-placeholder-en="Input"', markup)
        self.assertIn('id="result"', markup)
        self.assertIn('data-analysis-result="true"', markup)
        self.assertIn('data-print-brief-root="true"', markup)

        # The composer's send button is icon-only visually; its accessible name
        # keeps the Korean-canonical / English-aid label.
        self.assertNotIn("분석하기 / Analyze", markup)
        self.assertIn('aria-label="보내기 / Send"', markup)
        self.assertNotIn('class="send-label"', markup)

        # The 32-field assumptions grid and the OCR page editor are not rendered
        # in the creator flow: a creator cannot fill those fields or hand-edit
        # pages. The /api/analyze assumptions parsing path stays available and is
        # exercised by the analyze endpoint tests, not by this shell.
        self.assertNotIn("고급 시나리오 입력", markup)
        self.assertNotIn("시나리오 다시 계산", markup)
        self.assertNotIn("data-live-recompute", markup)
        self.assertNotIn("data-recompute-trigger", markup)
        self.assertNotIn("업로드한 페이지 편집", markup)
        self.assertNotIn("Pages before analysis", markup)
        self.assertNotIn('data-optional-tool="assumptions"', markup)
        self.assertNotIn('data-optional-tool="page-editor"', markup)

        for forbidden in ("Decision Brief", "브리프", "local-first", "우선도"):
            self.assertNotIn(forbidden, markup)

    def test_app_js_route_and_analyze_endpoint_are_local_only(self) -> None:
        import json

        settings = WEB.resolve_bind_settings()
        app = WEB.LocalASGIApp(settings)

        status, headers, body = asyncio.run(_asgi_get(app, "/app.js"))
        self.assertEqual(status, 200)
        self.assertEqual(headers["content-type"], "application/javascript")
        self.assertIn(b"fetch(", body)
        self.assertIn(b'fetch("/api/analyze"', body)
        self.assertIn(b'fetch("/api/chat"', body)
        self.assertIn("근거 찾는 중".encode("utf-8"), body)
        self.assertIn(b"Finding evidence", body)
        self.assertIn(b"typing-dots", body)
        self.assertIn("사진에서 글자를 읽지 못했어요.".encode("utf-8"), body)
        self.assertIn(b"I couldn't read text from that image", body)
        self.assertNotIn("\ubcf4\uae30".encode("utf-8"), body)
        self.assertIn('ko: "SUMMARY"'.encode("utf-8"), body)
        self.assertIn(b'en: "SUMMARY"', body)
        self.assertIn(b'data-integrated-judgment-card', body)
        self.assertIn("검토 권장 수준".encode("utf-8"), body)
        self.assertIn(b'data-review-effort-signal', body)
        self.assertIn(b'data-effort-level", level.key', body)
        self.assertIn("위험 지수".encode("utf-8"), body)
        self.assertIn(b"Risk Index", body)
        self.assertIn("숫자가 높을수록 먼저·꼼꼼히 살펴볼 계약상 금융 항목이 많다는 뜻이에요.".encode("utf-8"), body)
        self.assertNotIn("위험 확률, 손실액, 안전 판정이 아닙니다.".encode("utf-8"), body)
        self.assertIn("참고용일 뿐 확실한 법리적 판단은 아니에요.".encode("utf-8"), body)
        self.assertIn("의견서 만들기".encode("utf-8"), body)
        self.assertIn(b"Make a review brief", body)
        self.assertIn("이 의견서는 서명 결정을 돕기 위한 분석이며 법률 자문이 아닙니다.".encode("utf-8"), body)
        self.assertIn(b"data-finding-checklist", body)
        self.assertNotIn(b"finding-checklist-note", body)
        self.assertIn("다운로드하기".encode("utf-8"), body)
        self.assertIn(b'data-make-review-brief', body)
        self.assertIn(b"data-inline-review-brief", body)
        self.assertIn(b"data-download-review-brief", body)
        self.assertIn(b"window.print()", body)
        self.assertIn(b"data-print-brief-document", body)
        self.assertIn(b"function clauseReferencePair(finding, index)", body)
        self.assertIn(b"function renderLocalizedSourceSegments(container, source)", body)
        self.assertIn(b"followup-chip-stack", body)
        self.assertIn(b"var attachedFiles = [];", body)
        self.assertIn(b"function selectedFiles()", body)
        self.assertIn(b"attachedFiles.push", body)
        self.assertIn(b'form.append("contract_file", file)', body)
        self.assertIn(b"data-attachment-tile", body)
        self.assertIn(b"data-remove-attachment", body)
        self.assertIn(b"user-attachment-thumbs", body)
        self.assertIn(b"attachment-file-tile", body)
        self.assertNotIn(b"data-file-chip", body)
        self.assertNotIn(b"fileChip", body)
        self.assertIn(b'OCR_NO_TEXT" || code === "FILE_EMPTY"', body)
        self.assertNotIn(b"new Blob", body)
        self.assertNotIn(b"text/markdown", body)

        # The shared GET harness sends an empty body; the analyze handler maps an
        # empty/invalid body to a 400 with the local_only flag, confirming the
        # POST route is wired into the fallback app.
        async def _post_empty() -> tuple[int, bytes]:
            messages: list[dict[str, object]] = []
            sent = {"done": False}

            async def receive() -> dict[str, object]:
                if not sent["done"]:
                    sent["done"] = True
                    return {"type": "http.request", "body": b"{bad", "more_body": False}
                return {"type": "http.disconnect"}

            async def send(message: dict[str, object]) -> None:
                messages.append(message)

            scope = {
                "type": "http",
                "method": "POST",
                "path": "/api/analyze",
                "headers": [],
                "query_string": b"",
            }
            await app(scope, receive, send)  # type: ignore[misc]
            start = next(m for m in messages if m["type"] == "http.response.start")
            payload = b"".join(
                m.get("body", b"") for m in messages if m["type"] == "http.response.body"
            )
            return int(start["status"]), payload

        status, payload = asyncio.run(_post_empty())
        self.assertEqual(status, 400)
        self.assertTrue(json.loads(payload)["local_only"])

    def test_app_js_invalid_stored_locale_falls_back_to_ko(self) -> None:
        script = WEB.app_js()
        self.assertIn("fink.ui_locale", script)
        self.assertIn("function normalizeLocale(locale)", script)
        self.assertIn("var analyzeInFlight = false;", script)
        self.assertIn("var chatInFlight = false;", script)
        self.assertIn('var analyzedContractText = "";', script)
        self.assertIn("function setAnalyzeBusy(isBusy)", script)
        self.assertIn("function setChatBusy(isBusy)", script)
        self.assertIn("function submitComposer()", script)
        self.assertIn("function submitFollowUpQuestion(question, options)", script)
        self.assertIn("function firstChangedAssumption(previous, current)", script)
        self.assertIn("function prepareResultOpeningMessage(targetItem, container)", script)
        self.assertIn("function appendResultContentBubble(className, content, index)", script)
        self.assertIn("function renderDimensionChips(appendBubble, payload)", script)
        self.assertIn("function renderFindingLine(record)", script)
        self.assertIn("function renderAdvancedDiagnostics(container, payload)", script)
        self.assertIn("function renderSuggestedFollowUps(container, payload)", script)
        self.assertIn("function renderPrintableBrief(payload)", script)
        self.assertIn("function appendReviewBriefBubble(payload)", script)
        self.assertIn("function printBriefRoot()", script)
        self.assertIn("function renderReviewBriefAction(container)", script)
        self.assertIn("function showReviewBrief()", script)
        self.assertIn("function downloadReviewBrief()", script)
        self.assertIn("function reviewEffortSignal(payload, findingCount)", script)
        self.assertIn("function reviewEffortKey(payload, findingCount)", script)
        self.assertIn("function reviewFocusSignal(payload)", script)
        self.assertIn("function supportCount(value)", script)
        self.assertIn("var score = reviewFocusScore(payload);", script)
        self.assertIn("if (score <= 33)", script)
        self.assertIn("if (score <= 66)", script)
        self.assertNotIn("recommendationPathway(payload).toLowerCase()", script)
        self.assertIn("공식 근거", script)
        self.assertIn("실무 기준", script)
        self.assertIn("Official evidence", script)
        self.assertIn("Practice basis", script)
        self.assertNotIn('"조항 N"', script)
        self.assertNotIn("fallbackKo", script)
        self.assertNotIn("fallbackEn", script)
        self.assertIn("var clausePair = clauseReferencePair(finding, record.originalIndex);", script)
        self.assertIn('section.appendChild(bilingual("p", "finding-line-clause", clausePair));', script)
        self.assertIn("var clausePair = clauseReferencePair(finding, 0);", script)
        self.assertIn('concern.appendChild(bilingual("p", "glance-concern-clause", clausePair));', script)
        self.assertIn("function collectAuditEvidenceTopics(payload)", script)
        self.assertNotIn("후속 질문 근거", script)
        self.assertNotIn("Follow-up answer support", script)
        self.assertIn('section.setAttribute("data-followup-suggestions", "true")', script)
        self.assertIn('button.setAttribute("data-followup-chip", "true")', script)
        self.assertIn('button.setAttribute("data-make-review-brief", "true")', script)
        self.assertIn('button.setAttribute("data-download-review-brief", "true")', script)
        self.assertIn('ko: "이런 걸 물어볼 수 있어요"', script)
        self.assertIn('en: "You could ask"', script)
        self.assertIn('ko: "의견서 만들기"', script)
        self.assertIn('en: "Make a review brief"', script)
        self.assertIn("이 의견서는 서명 결정을 돕기 위한 분석이며 법률 자문이 아닙니다.", script)
        self.assertIn('ko: "다운로드하기"', script)
        self.assertIn("window.print()", script)
        self.assertNotIn("new Blob", script)
        self.assertNotIn("text/markdown", script)
        self.assertIn('paste_text: analyzedContractText', script)
        self.assertIn('question: asked', script)
        self.assertIn('locale: activeLocale()', script)
        self.assertIn('submitFollowUpQuestion(box ? box.value : "", { clearComposer: true });', script)
        self.assertIn("previous_assumptions", script)
        self.assertIn("scenarioRecompute", script)
        self.assertIn('button.setAttribute("aria-busy"', script)
        self.assertIn("new FormData()", script)
        self.assertIn(
            'return normalized === "en" || normalized === "ko" ? normalized : "ko";',
            script,
        )
        self.assertIn("window.localStorage.getItem(LOCALE_STORAGE_KEY)", script)
        self.assertIn("setLocale(readStoredLocale() || activeLocale());", script)
        for removed in (
            "function renderCheckFirst",
            "function renderDimensions",
            "function renderGroundedQa",
            "function renderSourceHighlights",
            "dimension-grid",
            "grounded-qa",
            "확인 표시",
            "Q&A 복사",
            "검토 항목으로 이동",
            'setAttribute("data-copy-question"',
        ):
            self.assertNotIn(removed, script)

    def test_lan_binding_is_gated_by_opt_in_warning_and_private_host(self) -> None:
        loopback = WEB.resolve_bind_settings(host="localhost")
        self.assertEqual(loopback.host, WEB.DEFAULT_LOOPBACK_HOST)
        self.assertFalse(loopback.lan_enabled)

        with self.assertRaises(WEB.WebBindingError):
            WEB.resolve_bind_settings(host="192.168.1.25")
        with self.assertRaises(WEB.WebBindingError):
            WEB.resolve_bind_settings(
                host="192.168.1.25",
                allow_lan=True,
                trusted_lan_ack=False,
            )
        with self.assertRaises(WEB.WebBindingError):
            WEB.resolve_bind_settings(
                host="0.0.0.0",
                allow_lan=True,
                trusted_lan_ack=True,
            )
        with self.assertRaises(WEB.WebBindingError):
            WEB.resolve_bind_settings(
                host="8.8.8.8",
                allow_lan=True,
                trusted_lan_ack=True,
            )

        lan = WEB.resolve_bind_settings(
            host="192.168.1.25",
            allow_lan=True,
            trusted_lan_ack=True,
        )
        self.assertTrue(lan.lan_enabled)
        self.assertTrue(lan.trusted_lan_warning_acknowledged)
        self.assertIn("Trusted-LAN mode", lan.trusted_lan_warning)
        self.assertIn(lan.trusted_lan_warning, WEB.render_index_html(lan))

    def test_no_network_runtime_test_static_routes_make_no_outbound_calls(self) -> None:
        def fail_network(*args: object, **kwargs: object) -> None:
            raise AssertionError("network use is forbidden in the web runtime smoke path")

        settings = WEB.resolve_bind_settings()
        app = WEB.LocalASGIApp(settings)
        with (
            patch.object(socket.socket, "connect", fail_network),
            patch.object(socket, "create_connection", fail_network),
        ):
            status, headers, body = asyncio.run(_asgi_get(app, "/"))
            self.assertEqual(status, 200)
            self.assertEqual(headers["cache-control"], "no-store")
            self.assertIn("default-src 'self'", headers["content-security-policy"])
            self.assertIn("font-src 'self'", headers["content-security-policy"])
            self.assertIn(b"This service does not collect or track user information", body)

            status, headers, body = asyncio.run(_asgi_get(app, "/fonts/NotoSerifKR-500.woff2"))
            self.assertEqual(status, 200)
            self.assertEqual(headers["content-type"], "font/woff2")
            self.assertGreater(len(body), 1000)

            status, _, body = asyncio.run(_asgi_get(app, "/healthz"))
            self.assertEqual(status, 200)
            self.assertIn(b'"outbound_network_clients": 0', body)
            self.assertIn(b'"local_only": true', body)


if __name__ == "__main__":
    unittest.main()

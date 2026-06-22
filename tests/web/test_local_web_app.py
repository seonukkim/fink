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
        self.assertIn("창작자 특화 금융 계약 검토", markup)
        self.assertIn("Creator-focused financial contract review", markup)
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

        # The chat shell shows the short reworded privacy line in the header and
        # folds the not-legal-advice text into the Notice panel. Korean is
        # canonical and the English text is an aid kept inside its locale span.
        # The reworded privacy line leads with "기록 미수집 · 기기 내 처리" and drops
        # the old "읽은 글자는 기기를 떠나지 않으며" phrasing; "텔레메트리" is gone.
        self.assertIn(WEB.PRIVACY_BANNER, markup)
        self.assertIn(WEB.NOT_LEGAL_ADVICE_BANNER, markup)
        self.assertNotIn("텔레메트리", markup)
        self.assertIn("기록 미수집 · 기기 내 처리", markup)
        self.assertIn("사용 기록을 수집하지 않고", markup)
        self.assertNotIn("계약서와 OCR로 읽은 글자는 기기를 떠나지 않으며", markup)
        self.assertIn("FInk은 계약서에서 돈과 직결되는 조항과 주의가 필요한 신호를 찾아", markup)
        self.assertNotIn("검토 순서만 안내", markup)
        for expected in (
            "does not make the final call on legality, fraud, contract validity",
            "scenario estimates",
            "needs evidence confirmation until confirmed",
            "Korean source language is canonical",
            "English UI text is a generated aid",
        ):
            self.assertIn(expected, markup)

        # The report disclosures render bilingually: the Korean canonical line
        # leads and the English aid stays inside its locale span.
        self.assertIn(
            "검토 순서는 위법성·사기·유효성·불공정·손실 확정에 대한 판정이 아닙니다.",
            markup,
        )
        self.assertIn("한국어 원문이 기준이며, 영어 화면 문구는 보조용으로 생성됩니다.", markup)

        # The chat shell has no footer: dev info and the separate footer privacy
        # paragraph are gone. The single privacy line lives in the header and the
        # rest of the disclosures sit in the Notice panel.
        self.assertNotIn("Serving from", markup)
        self.assertNotIn("Loopback only", markup)
        self.assertNotIn("LAN opt-in enabled", markup)
        self.assertNotIn("<footer", markup)
        self.assertNotIn("계약서와 분석 결과는 이 기기에서만 처리됩니다.", markup)
        self.assertIn('data-notice-panel="true"', markup)

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
        self.assertIn('class="notice-button"', markup)
        self.assertNotIn('class="notice-button secondary"', markup)
        self.assertIn(
            "계약서를 붙여넣거나 사진·PDF를 올려 주세요.",
            markup,
        )
        self.assertIn('id="result"', markup)
        self.assertIn('data-analysis-result="true"', markup)

        # The composer's send button label is a Korean-canonical / English-aid
        # pair of locale spans ("보내기"/"Send"), not the old Analyze label.
        self.assertNotIn("분석하기 / Analyze", markup)
        self.assertIn(
            '<span lang="ko" data-locale-text="ko">보내기</span>'
            '<span lang="en" data-locale-text="en">Send</span>',
            markup,
        )

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
        self.assertIn("이미지를 읽고 분석하는 중이에요…".encode("utf-8"), body)
        self.assertIn(b"Reading and analyzing the image", body)
        self.assertIn("사진에서 글자를 읽지 못했어요.".encode("utf-8"), body)
        self.assertIn(b"I couldn't read text from that image", body)
        self.assertNotIn("\ubcf4\uae30".encode("utf-8"), body)
        self.assertIn("한눈에 정리".encode("utf-8"), body)
        self.assertIn(b'data-integrated-judgment-card', body)
        self.assertIn("검토 권장 수준".encode("utf-8"), body)
        self.assertIn("최종 판단이 아니라 확인을 돕는 정리예요.".encode("utf-8"), body)

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
        self.assertIn("function renderCheckFirst(container, payload)", script)
        self.assertIn("function renderAdvancedDiagnostics(container, payload)", script)
        self.assertIn("function renderSuggestedFollowUps(container, payload)", script)
        self.assertIn('section.setAttribute("data-followup-suggestions", "true")', script)
        self.assertIn('button.setAttribute("data-followup-chip", "true")', script)
        self.assertIn('list.setAttribute("data-chat-citations", "true")', script)
        self.assertIn('ko: "이런 걸 물어볼 수 있어요"', script)
        self.assertIn('en: "You could ask"', script)
        self.assertIn('setAttribute("data-copy-question", "true")', script)
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
            self.assertIn(b"Local-only session", body)

            status, _, body = asyncio.run(_asgi_get(app, "/healthz"))
            self.assertEqual(status, 200)
            self.assertIn(b'"outbound_network_clients": 0', body)
            self.assertIn(b'"local_only": true', body)


if __name__ == "__main__":
    unittest.main()

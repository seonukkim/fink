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
        self.assertIn("EN generated", markup)
        self.assertIn("계약상 금융 검토 우선도", markup)
        self.assertIn("Contractual Financial Review Priority", markup)

        self.assertIn(WEB.PRIVACY_BANNER, markup)
        self.assertIn(WEB.NOT_LEGAL_ADVICE_BANNER, markup)
        for expected in (
            "not a legal, fraud, validity, unfairness, or guaranteed-loss verdict",
            "not legal advice",
            "scenario estimates",
            "UNVERIFIED pending A0",
            "Korean source language is canonical",
            "English UI text is a generated aid",
        ):
            self.assertIn(expected, markup)

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

        # New single-button creator flow hooks. The Analyze button and the
        # external /app.js script must be present, the locale toggle must expose
        # an active-locale attribute, and the 1-2-3 how-to strip must render.
        self.assertIn('id="analyze-btn"', markup)
        self.assertEqual(markup.count('id="analyze-btn"'), 1)
        self.assertIn('id="contract-file"', markup)
        self.assertNotIn('class="upload-tile"', markup)
        self.assertNotIn('data-ui-ingest-modes="camera image pdf paste"', markup)
        self.assertIn('<script src="/app.js">', markup)
        self.assertIn('data-active-locale', markup)
        self.assertIn('data-how-to-steps="true"', markup)
        self.assertIn("사용 방법 1-2-3", markup)
        self.assertIn("How to use 1-2-3", markup)
        self.assertIn('id="result"', markup)
        self.assertIn("고급 시나리오 입력", markup)
        self.assertIn('data-live-recompute="false"', markup)
        self.assertIn('data-recompute-trigger="explicit"', markup)
        self.assertIn("시나리오 다시 계산", markup)

    def test_app_js_route_and_analyze_endpoint_are_local_only(self) -> None:
        import json

        settings = WEB.resolve_bind_settings()
        app = WEB.LocalASGIApp(settings)

        status, headers, body = asyncio.run(_asgi_get(app, "/app.js"))
        self.assertEqual(status, 200)
        self.assertEqual(headers["content-type"], "application/javascript")
        self.assertIn(b"fetch(", body)

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
        self.assertIn("function setAnalyzeBusy(isBusy)", script)
        self.assertIn("function firstChangedAssumption(previous, current)", script)
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

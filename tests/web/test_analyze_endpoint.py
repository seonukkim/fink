from __future__ import annotations

import asyncio
import importlib
import json
import socket
import sys
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch


def _load_web() -> Any:
    src_root = Path(__file__).resolve().parents[2] / "src"
    src_text = src_root.as_posix()
    if src_text not in sys.path:
        sys.path.insert(0, src_text)
    return importlib.import_module("fink.web")


WEB = _load_web()

SAMPLE_KO = (
    "제3조(정산) 정산은 매 분기 종료일로부터 90일 이내에 지급하며, 회사는 일반 경비를 공제할 수 있다.\n"
    "제5조(위약금) 계약 위반 시 위약금을 부과한다."
)


async def _asgi_request(
    app: object,
    method: str,
    path: str,
    body: bytes = b"",
) -> tuple[int, dict[str, str], bytes]:
    messages: list[dict[str, object]] = []
    sent = {"done": False}

    async def receive() -> dict[str, object]:
        if not sent["done"]:
            sent["done"] = True
            return {"type": "http.request", "body": body, "more_body": False}
        return {"type": "http.disconnect"}

    async def send(message: dict[str, object]) -> None:
        messages.append(message)

    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "headers": [],
        "query_string": b"",
    }
    await app(scope, receive, send)  # type: ignore[misc]
    start = next(message for message in messages if message["type"] == "http.response.start")
    payload = b"".join(
        message.get("body", b"")
        for message in messages
        if message["type"] == "http.response.body"
    )
    headers = {
        key.decode("ascii"): value.decode("utf-8")
        for key, value in start.get("headers", [])
    }
    return int(start["status"]), headers, payload


class AnalyzeEndpointTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = WEB.LocalASGIApp(WEB.resolve_bind_settings())

    def test_app_js_route_serves_javascript_with_security_headers(self) -> None:
        status, headers, body = asyncio.run(_asgi_request(self.app, "GET", "/app.js"))
        self.assertEqual(status, 200)
        self.assertEqual(headers["content-type"], "application/javascript")
        self.assertEqual(headers["cache-control"], "no-store")
        self.assertIn("default-src 'self'", headers["content-security-policy"])
        self.assertIn(b"fetch(", body)

    def test_analyze_post_returns_local_only_json(self) -> None:
        body = json.dumps({"paste_text": SAMPLE_KO, "locale": "ko"}).encode("utf-8")
        status, headers, payload = asyncio.run(
            _asgi_request(self.app, "POST", "/api/analyze", body)
        )
        self.assertEqual(status, 200)
        self.assertEqual(headers["content-type"], "application/json")
        self.assertEqual(headers["cache-control"], "no-store")
        self.assertEqual(headers["x-content-type-options"], "nosniff")
        self.assertIn("default-src 'self'", headers["content-security-policy"])

        data = json.loads(payload)
        self.assertTrue(data["local_only"])
        self.assertEqual(data["grounding"], "UNVERIFIED")
        self.assertEqual(data["dimensions"]["review_priority"]["score"], 0)
        self.assertGreaterEqual(len(data["ranked_findings"]), 1)
        self.assertTrue(data["nl_summary"]["ko"].strip())
        self.assertTrue(data["nl_summary"]["en"].strip())

    def test_analyze_post_missing_locale_defaults_to_ko(self) -> None:
        body = json.dumps({"paste_text": SAMPLE_KO}).encode("utf-8")
        status, _, payload = asyncio.run(
            _asgi_request(self.app, "POST", "/api/analyze", body)
        )
        self.assertEqual(status, 200)
        data = json.loads(payload)
        self.assertEqual(data["ui_locale"], "ko")

    def test_valid_locale_strings_and_enums_are_equivalent(self) -> None:
        import fink.web.app as appmod
        from fink.schemas import UILocale

        self.assertIs(appmod._resolve_api_locale({"locale": "ko"}), UILocale.KO)
        self.assertIs(appmod._resolve_api_locale({"locale": UILocale.KO}), UILocale.KO)
        self.assertIs(appmod._resolve_api_locale({"locale": "en"}), UILocale.EN)
        self.assertIs(appmod._resolve_api_locale({"locale": UILocale.EN}), UILocale.EN)

    def test_analyze_post_invalid_locale_returns_structured_422(self) -> None:
        body = json.dumps({"paste_text": SAMPLE_KO, "locale": "ja"}).encode("utf-8")
        status, headers, payload = asyncio.run(
            _asgi_request(self.app, "POST", "/api/analyze", body)
        )
        self.assertEqual(status, 422)
        self.assertEqual(headers["content-type"], "application/json")
        data = json.loads(payload)
        self.assertTrue(data["local_only"])
        self.assertEqual(data["error_code"], "locale_invalid")
        self.assertIn("error", data)
        self.assertIn("error_en", data)
        self.assertIn("next_action", data)
        self.assertNotIn("ui_locale", data)
        self.assertNotEqual(data["error_code"], "internal_local_error")

    def test_analyze_post_malformed_body_returns_400(self) -> None:
        status, headers, payload = asyncio.run(
            _asgi_request(self.app, "POST", "/api/analyze", b"{not valid json")
        )
        self.assertEqual(status, 400)
        self.assertEqual(headers["content-type"], "application/json")
        data = json.loads(payload)
        self.assertIn("error", data)
        self.assertTrue(data["local_only"])

    def test_analyze_post_blank_paste_returns_400(self) -> None:
        body = json.dumps({"paste_text": "   ", "locale": "ko"}).encode("utf-8")
        status, _, payload = asyncio.run(
            _asgi_request(self.app, "POST", "/api/analyze", body)
        )
        self.assertEqual(status, 400)
        data = json.loads(payload)
        self.assertIn("error", data)
        self.assertTrue(data["local_only"])

    def test_analyze_makes_no_outbound_network_calls(self) -> None:
        def fail_network(*args: object, **kwargs: object) -> None:
            raise AssertionError("network use is forbidden in the analyze runtime path")

        body = json.dumps({"paste_text": SAMPLE_KO, "locale": "en"}).encode("utf-8")
        with (
            patch.object(socket.socket, "connect", fail_network),
            patch.object(socket, "create_connection", fail_network),
        ):
            status, _, payload = asyncio.run(
                _asgi_request(self.app, "POST", "/api/analyze", body)
            )
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(payload)["local_only"])

    def test_unknown_method_on_analyze_path_is_not_get_handled(self) -> None:
        # A GET on the analyze path is not the POST handler; it should 404 since
        # only POST is wired for /api/analyze.
        status, _, _ = asyncio.run(_asgi_request(self.app, "GET", "/api/analyze"))
        self.assertEqual(status, 404)


if __name__ == "__main__":
    unittest.main()

"""P0 robustness regressions for the local analyze endpoint.

Known engine/setup failures and malformed assumption input must produce a
friendly, structured, bilingual response — never a leaked 500 traceback — and a
string locale must not crash the payload serializer.
"""

from __future__ import annotations

import asyncio
import importlib
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


def _web():
    src = (Path(__file__).resolve().parents[2] / "src").as_posix()
    if src not in sys.path:
        sys.path.insert(0, src)
    return importlib.import_module("fink.web")


WEB = _web()


async def _post(app: object, path: str, body: dict) -> tuple[int, dict]:
    sent: list[dict] = []
    state = {"sent_request": False}

    async def receive() -> dict:
        if state["sent_request"]:
            return {"type": "http.disconnect"}
        state["sent_request"] = True
        return {
            "type": "http.request",
            "body": json.dumps(body).encode("utf-8"),
            "more_body": False,
        }

    async def send(message: dict) -> None:
        sent.append(message)

    scope = {"type": "http", "method": "POST", "path": path, "headers": [], "query_string": b""}
    await app(scope, receive, send)  # type: ignore[operator]
    start = next(m for m in sent if m["type"] == "http.response.start")
    raw = b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")
    return int(start["status"]), json.loads(raw.decode("utf-8"))


def _app() -> object:
    return WEB.LocalASGIApp(WEB.resolve_bind_settings())


class AnalyzeRobustnessTests(unittest.TestCase):
    def test_paste_still_returns_200(self) -> None:
        status, payload = asyncio.run(
            _post(_app(), "/api/analyze", {"paste_text": "제3조 정산은 분기 종료 후 90일 이내 지급한다.", "locale": "ko"})
        )
        self.assertEqual(status, 200)
        self.assertTrue(payload.get("local_only"))

    def test_secondary_rights_assumption_does_not_crash(self) -> None:
        status, _ = asyncio.run(
            _post(
                _app(),
                "/api/analyze",
                {
                    "paste_text": "제3조 정산은 분기 종료 후 90일 이내 지급한다.",
                    "locale": "ko",
                    "assumptions": {"secondary_rights": 5, "gross_sales": "1000000"},
                },
            )
        )
        self.assertNotEqual(status, 500)

    def test_setup_error_returns_friendly_503(self) -> None:
        import fink.web.app as appmod

        def boom(_payload: dict) -> dict:
            from fink.signals.engine import SignalDetectionError

            raise SignalDetectionError("signal rule config not found")

        with patch.object(appmod, "_analysis_payload_from_request", boom):
            status, payload = asyncio.run(_post(_app(), "/api/analyze", {"paste_text": "x", "locale": "ko"}))
        self.assertEqual(status, 503)
        self.assertEqual(payload.get("error_code"), "setup_incomplete")
        self.assertIn("next_action", payload)
        self.assertTrue(payload.get("local_only"))

    def test_string_locale_payload_does_not_crash(self) -> None:
        from fink.schemas import UILocale
        from fink.web.analyze import analysis_result_to_payload, run_local_analysis

        result = run_local_analysis(pasted_text="제3조 정산은 분기 종료 후 90일 이내 지급한다.", ui_locale=UILocale.KO)
        payload = analysis_result_to_payload(result, "ko")  # type: ignore[arg-type]
        self.assertEqual(payload["ui_locale"], "ko")


if __name__ == "__main__":
    unittest.main()

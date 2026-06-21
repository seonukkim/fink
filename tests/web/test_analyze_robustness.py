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
F5_SAMPLE_KO = "저작권 및 2차적저작물 권리는 회사에 포괄 양도된다."


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


def _fim6_audit_exposures(payload: dict) -> list[dict]:
    return [
        exposure
        for exposure in payload["audit_detail"]["monetary_exposures"]
        if exposure["fim_module"] == "FIM-6"
    ]


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

    def test_unexpected_type_error_returns_controlled_500(self) -> None:
        import fink.web.app as appmod

        private_text = "SECRET CONTRACT TEXT /tmp/fink-private/contract.pdf"

        def boom(_payload: dict) -> dict:
            raise TypeError(private_text)

        with patch.object(appmod, "_analysis_payload_from_request", boom):
            status, payload = asyncio.run(
                _post(_app(), "/api/analyze", {"paste_text": private_text, "locale": "ko"})
            )
        self.assertEqual(status, 500)
        self.assertEqual(payload.get("error_code"), "internal_local_error")
        self.assertNotIn("SECRET CONTRACT TEXT", repr(payload))
        self.assertNotIn("/tmp/fink-private", repr(payload))
        self.assertNotIn("traceback", repr(payload).lower())

    def test_string_locale_payload_does_not_crash(self) -> None:
        from fink.schemas import UILocale
        from fink.web.analyze import analysis_result_to_payload, run_local_analysis

        result = run_local_analysis(pasted_text="제3조 정산은 분기 종료 후 90일 이내 지급한다.", ui_locale=UILocale.KO)
        payload = analysis_result_to_payload(result, "ko")  # type: ignore[arg-type]
        self.assertEqual(payload["ui_locale"], "ko")

    def test_secondary_rights_flat_input_invents_no_money(self) -> None:
        """A flat secondary_rights number is not a valid FIM-6 input: it is
        skipped and must yield no invented monetary value (honest input-required),
        never a fabricated finite exposure or a crash (directive P0-VERIFY-00 1.3).
        """
        status, payload = asyncio.run(
            _post(
                _app(),
                "/api/analyze",
                {
                    "paste_text": "회사는 2차적저작물 작성권을 가진다.",
                    "locale": "ko",
                    "assumptions": {"secondary_rights": 5},
                },
            )
        )
        self.assertEqual(status, 200)
        self.assertEqual(
            payload["dimensions"]["monetary"]["quantification_status"]["state"],
            "not_quantified",
        )

    def test_structured_secondary_rights_reaches_fim6_scenario_value(self) -> None:
        status, payload = asyncio.run(
            _post(
                _app(),
                "/api/analyze",
                {
                    "paste_text": F5_SAMPLE_KO,
                    "locale": "ko",
                    "assumptions": {
                        "secondary_rights": [
                            {"type": "overseas", "value": "5000000", "prob": "0.4"},
                            {"type": "merchandise", "value": "3000000", "prob": "0.2"},
                        ]
                    },
                },
            )
        )

        self.assertEqual(status, 200)
        self.assertEqual(
            payload["dimensions"]["monetary"]["quantification_status"]["state"],
            "range_available",
        )
        self.assertEqual(payload["dimensions"]["monetary"]["ranges"][0]["base"], "2600000.0")
        fim6 = _fim6_audit_exposures(payload)
        self.assertEqual(len(fim6), 1)
        self.assertFalse(fim6[0]["is_user_input_required"])
        self.assertEqual(fim6[0]["base"], "2600000.0")
        self.assertIn(
            "no automatic IP valuation",
            " ".join(payload["dimensions"]["monetary"]["ranges"][0]["assumptions"]),
        )

    def test_missing_secondary_rights_values_keep_finding_and_require_input(self) -> None:
        status, payload = asyncio.run(
            _post(
                _app(),
                "/api/analyze",
                {
                    "paste_text": F5_SAMPLE_KO,
                    "locale": "ko",
                    "assumptions": {"secondary_rights": [{"type": "overseas"}]},
                },
            )
        )

        self.assertEqual(status, 200)
        self.assertEqual(
            payload["dimensions"]["monetary"]["quantification_status"]["state"],
            "not_quantified",
        )
        self.assertTrue(
            any(
                finding["source"]["exact_excerpt"] == F5_SAMPLE_KO
                for finding in payload["findings"]
            )
        )
        self.assertTrue(
            any(
                finding["risk_category"] == "F5"
                for finding in payload["audit_detail"]["technical_findings"]
            )
        )
        fim6 = _fim6_audit_exposures(payload)
        self.assertEqual(len(fim6), 1)
        self.assertTrue(fim6[0]["is_user_input_required"])
        self.assertIsNone(fim6[0]["low"])
        self.assertIsNone(fim6[0]["base"])
        self.assertIsNone(fim6[0]["high"])
        self.assertIn(
            "missing_user_input:secondary_rights[1].value",
            fim6[0]["uncertainty_flags"],
        )


if __name__ == "__main__":
    unittest.main()

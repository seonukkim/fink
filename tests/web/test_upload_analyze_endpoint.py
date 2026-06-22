from __future__ import annotations

import asyncio
import importlib
import json
import socket
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch


def _load_module(name: str) -> Any:
    src_root = Path(__file__).resolve().parents[2] / "src"
    src_text = src_root.as_posix()
    if src_text not in sys.path:
        sys.path.insert(0, src_text)
    return importlib.import_module(name)


WEB = _load_module("fink.web")
UPLOAD = _load_module("fink.web.upload")
PADDLE_OCR = _load_module("fink.ocr.paddle_vl")

SAMPLE_KO = (
    "제3조(정산) 정산은 매 분기 종료일로부터 90일 이내에 지급한다.\n"
    "제5조(위약금) 계약 위반 시 위약금을 부과한다."
)
PDF_TEXT = "Revenue share 10% Payment due 30 days"
PNG_1X1 = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR"
    b"\x00\x00\x00\x01"
    b"\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00"
    b"\x00\x00\x00\x00"
)


def _pdf_bytes(text: str) -> bytes:
    stream = f"BT ({text}) Tj ET"
    body = (
        "%PDF-1.4\n"
        "1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        "2 0 obj\n<< /Type /Pages /Count 1 /Kids [3 0 R] >>\nendobj\n"
        "3 0 obj\n<< /Type /Page /Parent 2 0 R /Contents 4 0 R >>\nendobj\n"
        f"4 0 obj\n<< /Length {len(stream)} >>\n"
        f"stream\n{stream}\nendstream\nendobj\n"
        "%%EOF\n"
    )
    return body.encode("utf-8")


def _multipart_body(
    *,
    fields: dict[str, str] | None = None,
    file_field: str = "contract_file",
    filename: str | None = None,
    content_type: str = "text/plain",
    data: bytes | None = None,
) -> tuple[bytes, dict[str, str]]:
    boundary = "----fink-test-boundary"
    chunks: list[bytes] = []
    for name, value in (fields or {}).items():
        chunks.extend(
            [
                f"--{boundary}\r\n".encode("ascii"),
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("ascii"),
                value.encode("utf-8"),
                b"\r\n",
            ]
        )
    if filename is not None and data is not None:
        chunks.extend(
            [
                f"--{boundary}\r\n".encode("ascii"),
                (
                    f'Content-Disposition: form-data; name="{file_field}"; '
                    f'filename="{filename}"\r\n'
                ).encode("utf-8"),
                f"Content-Type: {content_type}\r\n\r\n".encode("ascii"),
                data,
                b"\r\n",
            ]
        )
    chunks.append(f"--{boundary}--\r\n".encode("ascii"))
    return b"".join(chunks), {"content-type": f"multipart/form-data; boundary={boundary}"}


async def _asgi_post(
    app: object, body: bytes, headers: dict[str, str]
) -> tuple[int, dict[str, str], dict[str, Any]]:
    messages: list[dict[str, object]] = []
    state = {"sent_request": False}

    async def receive() -> dict[str, object]:
        if state["sent_request"]:
            return {"type": "http.disconnect"}
        state["sent_request"] = True
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message: dict[str, object]) -> None:
        messages.append(message)

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/analyze",
        "headers": [
            (key.lower().encode("ascii"), value.encode("utf-8"))
            for key, value in headers.items()
        ],
        "query_string": b"",
    }
    await app(scope, receive, send)  # type: ignore[misc]
    start = next(message for message in messages if message["type"] == "http.response.start")
    payload = b"".join(
        message.get("body", b"")
        for message in messages
        if message["type"] == "http.response.body"
    )
    response_headers = {
        key.decode("ascii"): value.decode("utf-8")
        for key, value in start.get("headers", [])
    }
    return int(start["status"]), response_headers, json.loads(payload.decode("utf-8"))


def _fallback_app() -> object:
    return WEB.LocalASGIApp(WEB.resolve_bind_settings())


class UploadAnalyzeEndpointTests(unittest.TestCase):
    def test_multipart_text_upload_reaches_canonical_analysis(self) -> None:
        body, headers = _multipart_body(
            fields={"locale": "ko"},
            filename="contract.txt",
            content_type="text/plain",
            data=SAMPLE_KO.encode("utf-8"),
        )
        status, _, payload = asyncio.run(_asgi_post(_fallback_app(), body, headers))
        self.assertEqual(status, 200)
        self.assertTrue(payload["local_only"])
        self.assertEqual(payload["view_model"], "CreatorReviewViewModel")
        self.assertEqual(payload["statuses"]["evidence_status"]["state"], "unverified")
        self.assertIn("review_priority", payload["dimensions"])
        self.assertGreaterEqual(payload["audit_detail"]["clause_count"], 1)

    def test_multipart_text_layer_pdf_upload_reaches_analysis(self) -> None:
        body, headers = _multipart_body(
            fields={"locale": "en"},
            filename="contract.pdf",
            content_type="application/pdf",
            data=_pdf_bytes(PDF_TEXT),
        )
        status, _, payload = asyncio.run(_asgi_post(_fallback_app(), body, headers))
        self.assertEqual(status, 200)
        self.assertTrue(payload["local_only"])
        self.assertEqual(payload["ui_locale"], "en")
        self.assertGreaterEqual(payload["audit_detail"]["clause_count"], 1)

    def test_image_upload_without_local_ocr_returns_ocr_not_installed(self) -> None:
        body, headers = _multipart_body(
            fields={"locale": "ko"},
            filename="scan.png",
            content_type="image/png",
            data=PNG_1X1,
        )
        with patch.object(UPLOAD, "_local_ocr_is_available", return_value=False):
            status, _, payload = asyncio.run(_asgi_post(_fallback_app(), body, headers))
        self.assertEqual(status, 422)
        self.assertEqual(payload["error_code"], "OCR_NOT_INSTALLED")
        self.assertEqual(payload["validation_status"], "rejected_ocr_unavailable")
        self.assertIn("이미지 OCR이 이 기기에 설치되어 있지 않습니다.", payload["error"])
        self.assertIn("uv sync --extra ocr", payload["next_action"])
        self.assertIn("PP-OCR", payload["next_action"])
        self.assertNotIn("scan.png", repr(payload))

    def test_paddle_ppocr_backend_is_cached_across_upload_ocr_calls(self) -> None:
        class FakePaddleBackend:
            instances = 0

            def __init__(self) -> None:
                FakePaddleBackend.instances += 1

            def recognize_image_text(self, stored_path: Path) -> str:
                return f"recognized {stored_path.name}"

        previous_backend = UPLOAD._PADDLE_OCR_BACKEND
        UPLOAD._PADDLE_OCR_BACKEND = None
        try:
            with patch.object(PADDLE_OCR, "PaddlePPOCRBackend", FakePaddleBackend):
                first = UPLOAD._paddle_ocr_recognize_text(Path("first.png"))
                second = UPLOAD._paddle_ocr_recognize_text(Path("second.png"))
        finally:
            UPLOAD._PADDLE_OCR_BACKEND = previous_backend

        self.assertEqual(first, "recognized first.png")
        self.assertEqual(second, "recognized second.png")
        self.assertEqual(FakePaddleBackend.instances, 1)

    def test_paddle_ppocr_list_output_is_joined_in_reading_order(self) -> None:
        outputs = [
            [
                ([[12, 42], [60, 42], [60, 54], [12, 54]], ("second line", 0.91)),
                ([[80, 10], [120, 10], [120, 20], [80, 20]], ("right top", 0.93)),
                ([[10, 10], [70, 10], [70, 20], [10, 20]], ("left top", 0.94)),
            ]
        ]

        text = PADDLE_OCR._text_from_outputs(outputs)

        self.assertEqual(text, "left top\nright top\nsecond line")

    def test_paddle_ppocr_dict_output_uses_rec_texts_and_polys(self) -> None:
        outputs = {
            "rec_texts": ["bottom", "top"],
            "rec_polys": [
                [[10, 40], [80, 40], [80, 50], [10, 50]],
                [[10, 8], [50, 8], [50, 18], [10, 18]],
            ],
        }

        text = PADDLE_OCR._text_from_outputs(outputs)

        self.assertEqual(text, "top\nbottom")

    def test_ppocr_pipeline_omits_deprecated_kwargs_and_disables_mkldnn(self) -> None:
        # paddleocr 3.x raises ValueError("use_angle_cls and use_textline_orientation
        # are mutually exclusive") and its oneDNN/PIR CPU path raises
        # NotImplementedError during inference. Guard both: never send the deprecated
        # use_angle_cls/use_gpu aliases, and always disable MKLDNN.
        captured: dict[str, object] = {}

        def fake_paddle_ocr(**kwargs: object) -> object:
            captured.update(kwargs)
            return object()

        with patch.object(PADDLE_OCR, "_import_paddle_ocr", lambda: fake_paddle_ocr):
            PADDLE_OCR.PaddlePPOCRBackend()._build_pipeline()

        self.assertNotIn("use_angle_cls", captured)
        self.assertNotIn("use_gpu", captured)
        self.assertIs(captured.get("enable_mkldnn"), False)
        self.assertEqual(captured.get("lang"), "korean")

    def test_both_paste_and_file_returns_clear_validation_state(self) -> None:
        file_text = "Revenue share 10% Payment due 30 days"
        body, headers = _multipart_body(
            fields={"locale": "ko", "paste_text": SAMPLE_KO},
            filename="contract.txt",
            content_type="text/plain",
            data=file_text.encode("utf-8"),
        )
        status, _, payload = asyncio.run(_asgi_post(_fallback_app(), body, headers))
        self.assertEqual(status, 200)
        self.assertTrue(payload["local_only"])
        self.assertEqual(payload["view_model"], "CreatorReviewViewModel")
        rendered = json.dumps(payload["findings"], ensure_ascii=False)
        self.assertIn("위약금", rendered)
        self.assertIn("Payment due 30 days", rendered)
        self.assertGreaterEqual(payload["audit_detail"]["clause_count"], 2)

    def test_combined_paste_and_text_file_merges_clause_markers(self) -> None:
        paste_text = "제1조(정산) 정산 자료와 감사권은 제공하지 않는다."
        file_text = "제2조(지급) 지급시기는 회사가 추후 정하는 일정에 따른다."
        body, headers = _multipart_body(
            fields={"locale": "ko", "paste_text": paste_text},
            filename="contract.txt",
            content_type="text/plain",
            data=file_text.encode("utf-8"),
        )
        status, _, payload = asyncio.run(_asgi_post(_fallback_app(), body, headers))
        self.assertEqual(status, 200)
        rendered = json.dumps(payload["findings"], ensure_ascii=False)
        self.assertIn("정산 자료", rendered)
        self.assertIn("지급시기는 회사가 추후 정하는 일정", rendered)
        self.assertGreaterEqual(payload["audit_detail"]["signal_count"], 2)

    def test_upload_validation_errors_are_structured_and_sanitized(self) -> None:
        cases = (
            (
                "empty",
                "contract.txt",
                "text/plain",
                b"",
                400,
                "FILE_EMPTY",
                "rejected_empty",
            ),
            (
                "unsupported",
                "secret-contract-name.docx",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                b"SECRET CONTRACT TEXT 123",
                415,
                "FILE_UNSUPPORTED",
                "rejected_unsupported",
            ),
            (
                "corrupt",
                "contract.pdf",
                "application/pdf",
                b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\n",
                400,
                "FILE_CORRUPT",
                "rejected_corrupt",
            ),
            (
                "encrypted",
                "contract.pdf",
                "application/pdf",
                b"%PDF-1.4\n/Encrypt\n/Type /Page\n%%EOF\n",
                400,
                "PDF_ENCRYPTED",
                "rejected_encrypted",
            ),
        )
        for label, filename, content_type, data, expected_status, code, validation in cases:
            with self.subTest(label=label):
                body, headers = _multipart_body(
                    fields={"locale": "ko"},
                    filename=filename,
                    content_type=content_type,
                    data=data,
                )
                status, _, payload = asyncio.run(_asgi_post(_fallback_app(), body, headers))
                self.assertEqual(status, expected_status)
                self.assertEqual(payload["error_code"], code)
                self.assertEqual(payload["validation_status"], validation)
                rendered = repr(payload)
                self.assertNotIn("SECRET CONTRACT TEXT", rendered)
                self.assertNotIn("secret-contract-name", rendered)
                self.assertIn("local_only", payload)

    def test_oversized_upload_returns_structured_413(self) -> None:
        body, headers = _multipart_body(
            fields={"locale": "ko"},
            filename="contract.txt",
            content_type="text/plain",
            data=b"abcdef",
        )
        with patch.object(UPLOAD, "DEFAULT_UPLOAD_LIMITS", UPLOAD.IngestLimits(max_bytes=5)):
            status, _, payload = asyncio.run(_asgi_post(_fallback_app(), body, headers))
        self.assertEqual(status, 413)
        self.assertEqual(payload["error_code"], "FILE_OVERSIZED")
        self.assertEqual(payload["validation_status"], "rejected_oversized")

    def test_upload_temp_workspace_is_cleaned_after_pdf_analysis(self) -> None:
        real_temp_dir = tempfile.TemporaryDirectory
        created: list[Path] = []

        class RecordingTemporaryDirectory(real_temp_dir):  # type: ignore[misc, valid-type]
            def __enter__(self) -> str:
                path = super().__enter__()
                created.append(Path(path))
                return path

        body, headers = _multipart_body(
            fields={"locale": "ko"},
            filename="contract.pdf",
            content_type="application/pdf",
            data=_pdf_bytes(PDF_TEXT),
        )
        with patch.object(UPLOAD.tempfile, "TemporaryDirectory", RecordingTemporaryDirectory):
            status, _, payload = asyncio.run(_asgi_post(_fallback_app(), body, headers))
        self.assertEqual(status, 200)
        self.assertTrue(payload["local_only"])
        self.assertTrue(created)
        self.assertTrue(all(not path.exists() for path in created))

    def test_multipart_pdf_analysis_makes_no_outbound_network_calls(self) -> None:
        def fail_network(*args: object, **kwargs: object) -> None:
            raise AssertionError("network use is forbidden in upload analyze path")

        body, headers = _multipart_body(
            fields={"locale": "ko"},
            filename="contract.pdf",
            content_type="application/pdf",
            data=_pdf_bytes(PDF_TEXT),
        )
        with (
            patch.object(socket.socket, "connect", fail_network),
            patch.object(socket, "create_connection", fail_network),
        ):
            status, _, payload = asyncio.run(_asgi_post(_fallback_app(), body, headers))
        self.assertEqual(status, 200)
        self.assertTrue(payload["local_only"])

    def test_fastapi_app_uses_same_multipart_path_when_available(self) -> None:
        try:
            importlib.import_module("fastapi")
        except ModuleNotFoundError:
            self.skipTest("FastAPI is not installed in this environment")

        app = WEB.create_app(WEB.resolve_bind_settings())
        body, headers = _multipart_body(
            fields={"locale": "ko"},
            filename="contract.txt",
            content_type="text/plain",
            data=SAMPLE_KO.encode("utf-8"),
        )
        status, _, payload = asyncio.run(_asgi_post(app, body, headers))
        self.assertEqual(status, 200)
        self.assertTrue(payload["local_only"])


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import base64
import importlib
import os
import socket
import sys
import tempfile
import unittest
import zlib
from pathlib import Path
from typing import Any, Sequence
from unittest.mock import patch


def _load_module(name: str) -> Any:
    src_root = Path(__file__).resolve().parents[2] / "src"
    src_text = src_root.as_posix()
    if src_text not in sys.path:
        sys.path.insert(0, src_text)
    return importlib.import_module(name)


INGEST = _load_module("fink.ingest")
SCHEMAS = _load_module("fink.schemas")

KO_TEXT = (
    "\uc815\uc0b0\uae08 1,200,000\uc6d0 "
    "\uc218\uc775\ubc30\ubd84 30% \uc9c0\uae09 45\uc77c"
)
KO_OCR_TEXT = (
    "\uc815\uc0b0\uae08 1,500,000\uc6d0 "
    "\uc218\uc775\ubc30\ubd84 20% \uc9c0\uae09 30\uc77c"
)
EN_TEXT = "Gross sales 2,000,000 KRW Revenue share 25% Payment due 30 days"
EN_OCR_TEXT = "Gross sales 3,000,000 KRW Revenue share 35% Payment due 60 days"


def _pdf_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _hint(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode("utf-8")).decode("ascii")


def _pdf_bytes(
    page_texts: Sequence[str | None],
    *,
    ocr_hints: Sequence[str] | None = None,
    flate_pages: set[int] | None = None,
) -> bytes:
    hints = tuple(ocr_hints or ())
    flated = flate_pages or set()
    object_chunks = [
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n",
    ]
    kids: list[str] = []
    for idx, text in enumerate(page_texts):
        page_obj = 3 + idx * 2
        content_obj = page_obj + 1
        kids.append(f"{page_obj} 0 R")
        object_chunks.append(
            (
                f"{page_obj} 0 obj\n"
                f"<< /Type /Page /Parent 2 0 R /Contents {content_obj} 0 R >>\n"
                f"endobj\n"
            ).encode("ascii")
        )
        if text is None:
            stream = b"q\n/Im0 Do\nQ"
        else:
            stream = f"BT ({_pdf_escape(text)}) Tj ET".encode("utf-8")
        if idx in flated:
            stream = zlib.compress(stream)
            header = (
                f"{content_obj} 0 obj\n"
                f"<< /Length {len(stream)} /Filter /FlateDecode >>\n"
            )
        else:
            header = f"{content_obj} 0 obj\n<< /Length {len(stream)} >>\n"
        object_chunks.append(
            header.encode("ascii")
            + b"stream\n"
            + stream
            + b"\nendstream\nendobj\n"
        )

    pages_obj = (
        f"2 0 obj\n<< /Type /Pages /Count {len(page_texts)} "
        f"/Kids [{' '.join(kids)}] >>\nendobj\n"
    ).encode("ascii")
    comments = b""
    for idx, text in enumerate(hints):
        if text:
            comments += f"% FINK-OCR-HINT page={idx} text={_hint(text)}\n".encode("ascii")
    return b"%PDF-1.4\n" + pages_obj + b"".join(object_chunks) + comments + b"%%EOF\n"


def _term_values(ingested: Any, feature_id: str) -> list[Any]:
    return [term.value_norm for term in ingested.extracted_terms if term.feature_id == feature_id]


def _page_text(page: Any) -> str:
    return "\n".join(span.corrected_text or span.text for span in page.spans)


class PDFValidationTests(unittest.TestCase):
    def test_pdf_validation_tests_statuses_and_configured_limits(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "uploads"
            valid_pdf = Path(tmp) / "valid.pdf"
            fake_pdf = Path(tmp) / "fake.pdf"
            corrupt_pdf = Path(tmp) / "corrupt.pdf"
            encrypted_pdf = Path(tmp) / "encrypted.pdf"
            valid_pdf.write_bytes(_pdf_bytes([EN_TEXT]))
            fake_pdf.write_bytes(b"not a pdf")
            corrupt_pdf.write_bytes(b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\n")
            encrypted_pdf.write_bytes(b"%PDF-1.4\n/Encrypt\n/Type /Page\n%%EOF\n")

            with INGEST.EphemeralIngestSession(upload_root=root) as session:
                accepted = session.ingest_pdf(valid_pdf, content_type="application/pdf")
                bad_magic = session.ingest_pdf(fake_pdf, content_type="application/pdf")
                bad_mime = session.ingest_pdf(valid_pdf, content_type="text/plain")
                corrupt = session.ingest_pdf(corrupt_pdf, content_type="application/pdf")
                encrypted = session.ingest_pdf(encrypted_pdf, content_type="application/pdf")

            self.assertEqual(accepted.document.validation_status, SCHEMAS.ValidationStatus.ACCEPTED)
            self.assertTrue(accepted.document.magic_byte_verified)
            self.assertEqual(
                bad_magic.document.validation_status,
                SCHEMAS.ValidationStatus.REJECTED_UNSUPPORTED,
            )
            self.assertEqual(
                bad_mime.document.validation_status,
                SCHEMAS.ValidationStatus.REJECTED_UNSUPPORTED,
            )
            self.assertEqual(
                corrupt.document.validation_status,
                SCHEMAS.ValidationStatus.REJECTED_CORRUPT,
            )
            self.assertEqual(
                encrypted.document.validation_status,
                SCHEMAS.ValidationStatus.REJECTED_ENCRYPTED,
            )
            self.assertIsNone(bad_magic.stored_path)
            self.assertIsNone(encrypted.stored_path)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "uploads"
            pdf = Path(tmp) / "two-pages.pdf"
            payload = _pdf_bytes([EN_TEXT, KO_TEXT])
            pdf.write_bytes(payload)

            byte_limited = INGEST.IngestLimits(max_bytes=len(payload) - 1, max_pages=10)
            with INGEST.EphemeralIngestSession(upload_root=root, limits=byte_limited) as session:
                oversized = session.ingest_pdf(pdf, content_type="application/pdf")
            self.assertEqual(
                oversized.document.validation_status,
                SCHEMAS.ValidationStatus.REJECTED_OVERSIZED,
            )

            page_limited = INGEST.IngestLimits(max_bytes=len(payload) + 10, max_pages=1)
            with INGEST.EphemeralIngestSession(upload_root=root, limits=page_limited) as session:
                too_many_pages = session.ingest_pdf(pdf, content_type="application/pdf")
            self.assertEqual(
                too_many_pages.document.validation_status,
                SCHEMAS.ValidationStatus.REJECTED_OVERSIZED,
            )


class PDFTextLayerOCRTests(unittest.TestCase):
    def test_pdf_textlayer_ocr_tests_bilingual_text_layer_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "uploads"
            pdf = Path(tmp) / "text-layer.pdf"
            pdf.write_bytes(_pdf_bytes([KO_TEXT, EN_TEXT], flate_pages={1}))

            with INGEST.EphemeralIngestSession(upload_root=root) as session:
                ingested = session.ingest_pdf(pdf, content_type="application/pdf")

                pages = ingested.document.pages
                self.assertEqual(ingested.document.page_count, 2)
                self.assertEqual([page.page_index for page in pages], [0, 1])
                self.assertEqual(
                    [page.text_source for page in pages],
                    [SCHEMAS.TextSource.TEXT_LAYER, SCHEMAS.TextSource.TEXT_LAYER],
                )
                self.assertIn("\uc815\uc0b0\uae08", _page_text(pages[0]))
                self.assertIn("Gross sales", _page_text(pages[1]))
                self.assertIn(0.30, [float(value) for value in _term_values(ingested, "REVENUE_SHARE_RATE")])
                self.assertIn(0.25, [float(value) for value in _term_values(ingested, "REVENUE_SHARE_RATE")])
                self.assertIn(45.0, _term_values(ingested, "PAYMENT_DUE_DAYS"))
                self.assertIn(30.0, _term_values(ingested, "PAYMENT_DUE_DAYS"))

    def test_pdf_textlayer_ocr_tests_bilingual_image_only_ocr_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "uploads"
            pdf = Path(tmp) / "image-only.pdf"
            pdf.write_bytes(
                _pdf_bytes([None, None], ocr_hints=[KO_OCR_TEXT, EN_OCR_TEXT])
            )

            with INGEST.EphemeralIngestSession(upload_root=root) as session:
                ingested = session.ingest_pdf(pdf, content_type="application/pdf")

                pages = ingested.document.pages
                self.assertEqual(
                    [page.text_source for page in pages],
                    [SCHEMAS.TextSource.OCR, SCHEMAS.TextSource.OCR],
                )
                self.assertTrue(all(page.spans for page in pages))
                self.assertTrue(all(span.confidence > 0 for page in pages for span in page.spans))
                self.assertIn("\uc815\uc0b0\uae08", _page_text(pages[0]))
                self.assertIn("Gross sales", _page_text(pages[1]))
                self.assertIn(0.20, [float(value) for value in _term_values(ingested, "REVENUE_SHARE_RATE")])
                self.assertIn(0.35, [float(value) for value in _term_values(ingested, "REVENUE_SHARE_RATE")])

    def test_pdf_textlayer_ocr_tests_mixed_multipage_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "uploads"
            pdf = Path(tmp) / "mixed.pdf"
            pdf.write_bytes(_pdf_bytes([KO_TEXT, None, EN_TEXT], ocr_hints=["", EN_OCR_TEXT, ""]))

            with INGEST.EphemeralIngestSession(upload_root=root) as session:
                ingested = session.ingest_pdf(pdf, content_type="application/pdf")

                pages = ingested.document.pages
                self.assertEqual(ingested.document.page_count, 3)
                self.assertEqual([page.page_index for page in pages], [0, 1, 2])
                self.assertEqual(
                    [page.text_source for page in pages],
                    [
                        SCHEMAS.TextSource.TEXT_LAYER,
                        SCHEMAS.TextSource.OCR,
                        SCHEMAS.TextSource.TEXT_LAYER,
                    ],
                )
                self.assertIn("Gross sales", _page_text(pages[1]))

    def test_pdf_textlayer_ocr_tests_per_page_mixed_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "uploads"
            pdf = Path(tmp) / "page-mixed.pdf"
            pdf.write_bytes(
                _pdf_bytes(
                    ["Gross sales 1,000,000 KRW"],
                    ocr_hints=["Revenue share 15% Payment due 20 days"],
                )
            )

            with INGEST.EphemeralIngestSession(upload_root=root) as session:
                ingested = session.ingest_pdf(pdf, content_type="application/pdf")

                page = ingested.document.pages[0]
                self.assertEqual(page.text_source, SCHEMAS.TextSource.MIXED)
                self.assertIn("Gross sales", _page_text(page))
                self.assertIn("Revenue share", _page_text(page))
                self.assertIn(0.15, [float(value) for value in _term_values(ingested, "REVENUE_SHARE_RATE")])


class PDFOfflinePrivacyTests(unittest.TestCase):
    def test_pdf_offline_test_complete_path_blocks_sockets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "uploads"
            pdf = Path(tmp) / "offline.pdf"
            pdf.write_bytes(_pdf_bytes([None], ocr_hints=[EN_OCR_TEXT]))

            def fail_network(*args: object, **kwargs: object) -> None:
                raise AssertionError("network use is forbidden during PDF ingest")

            with (
                patch.object(socket.socket, "connect", fail_network),
                patch.object(socket, "create_connection", fail_network),
                INGEST.EphemeralIngestSession(upload_root=root) as session,
            ):
                ingested = session.ingest_pdf(pdf, content_type="application/pdf")
                self.assertEqual(
                    ingested.document.validation_status,
                    SCHEMAS.ValidationStatus.ACCEPTED,
                )
                self.assertEqual(ingested.document.pages[0].text_source, SCHEMAS.TextSource.OCR)
                self.assertIn("Gross sales", _page_text(ingested.document.pages[0]))

    def test_pdf_ephemeral_delete_test_workspace_permissions_and_clear(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "uploads"
            pdf = Path(tmp) / "permission.pdf"
            pdf.write_bytes(_pdf_bytes([EN_TEXT, None], ocr_hints=["", EN_OCR_TEXT]))

            session = INGEST.EphemeralIngestSession(upload_root=root)
            ingested = session.ingest_pdf(pdf, content_type="application/pdf")
            workspace = session.workspace
            paths = (ingested.stored_path, *ingested.derived_paths)

            self.assertEqual(oct(os.stat(workspace).st_mode & 0o777), "0o700")
            for path in paths:
                self.assertIsNotNone(path)
                self.assertTrue(path.exists())
                self.assertEqual(oct(os.stat(path).st_mode & 0o777), "0o600")
                self.assertIn(workspace, path.parents)

            session.clear()
            self.assertFalse(workspace.exists())

    def test_pdf_log_redaction_test_no_raw_filename_or_contract_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "uploads"
            pdf = Path(tmp) / "secret-contract-name.pdf"
            pdf.write_bytes(_pdf_bytes([EN_TEXT]))

            with INGEST.EphemeralIngestSession(upload_root=root) as session:
                ingested = session.ingest_pdf(
                    pdf,
                    original_filename="secret-contract-name.pdf",
                    content_type="application/pdf",
                )
                log_record = ingested.to_log_record()

            rendered = repr(log_record)
            self.assertNotIn("secret-contract-name", rendered)
            self.assertNotIn("Gross sales", rendered)
            self.assertNotIn("Revenue share", rendered)
            self.assertNotIn("2,000,000", rendered)
            self.assertIn("filename_hash", log_record)
            self.assertIn("page_count", log_record)


if __name__ == "__main__":
    unittest.main()

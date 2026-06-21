from __future__ import annotations

import importlib
import os
import socket
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


def _load_ingest():
    src_root = Path(__file__).resolve().parents[2] / "src"
    src_text = src_root.as_posix()
    if src_text not in sys.path:
        sys.path.insert(0, src_text)
    return importlib.import_module("fink.ingest")


def _load_schemas():
    src_root = Path(__file__).resolve().parents[2] / "src"
    src_text = src_root.as_posix()
    if src_text not in sys.path:
        sys.path.insert(0, src_text)
    return importlib.import_module("fink.schemas")


INGEST = _load_ingest()
SCHEMAS = _load_schemas()

PNG_1X1 = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR"
    b"\x00\x00\x00\x01"
    b"\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00"
    b"\x00\x00\x00\x00"
)
WEBP_1X1 = b"RIFF\x1a\x00\x00\x00WEBPVP8 " + b"\x00" * 16


def _pdf_bytes(page_count: int = 2, text: str = "Contract text") -> bytes:
    page_objects = []
    kids = []
    for idx in range(page_count):
        obj_id = 3 + idx
        kids.append(f"{obj_id} 0 R")
        stream = f"BT ({text if idx == 0 else ''}) Tj ET"
        page_objects.append(
            f"{obj_id} 0 obj\n"
            f"<< /Type /Page /Parent 2 0 R /Contents {obj_id + 100} 0 R >>\n"
            f"endobj\n"
            f"{obj_id + 100} 0 obj\n"
            f"<< /Length {len(stream)} >>\n"
            f"stream\n{stream}\nendstream\n"
            f"endobj\n"
        )
    body = (
        "%PDF-1.4\n"
        "1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        f"2 0 obj\n<< /Type /Pages /Count {page_count} /Kids [{' '.join(kids)}] >>\nendobj\n"
        + "".join(page_objects)
        + "%%EOF\n"
    )
    return body.encode("utf-8")


class EphemeralIngestTests(unittest.TestCase):
    def test_all_input_modes_produce_valid_reports_and_hashed_names(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "uploads"
            camera = Path(tmp) / "camera-source.png"
            image = Path(tmp) / "image-source.webp"
            pdf = Path(tmp) / "source.pdf"
            camera.write_bytes(PNG_1X1)
            image.write_bytes(WEBP_1X1)
            pdf.write_bytes(_pdf_bytes(page_count=1))

            with INGEST.EphemeralIngestSession(upload_root=root) as session:
                ingested_items = [
                    session.ingest_camera(
                        camera,
                        original_filename="raw-camera-contract-name.png",
                        content_type="image/png",
                    ),
                    session.ingest_image(
                        image,
                        original_filename="raw-image-contract-name.webp",
                        content_type="image/webp",
                    ),
                    session.ingest_pdf(
                        pdf,
                        original_filename="raw-pdf-contract-name.pdf",
                        content_type="application/pdf",
                    ),
                    session.ingest_paste("pasted contract clause"),
                ]

                self.assertEqual(oct(os.stat(session.workspace).st_mode & 0o777), "0o700")
                for ingested in ingested_items:
                    report = ingested.build_report()
                    self.assertIsInstance(report, SCHEMAS.AnalysisReport)
                    self.assertEqual(report.assessment.review_priority_score, 0)
                    self.assertIn("review priority", " ".join(report.disclaimers).lower())
                    if ingested.stored_path is not None:
                        self.assertTrue(ingested.stored_path.exists())
                        mode = oct(os.stat(ingested.stored_path).st_mode & 0o777)
                        self.assertEqual(mode, "0o600")
                    if ingested.filename_hash is not None:
                        self.assertRegex(ingested.filename_hash, r"^[a-f0-9]{64}$")
                    log_record = ingested.to_log_record()
                    self.assertNotIn("raw-camera-contract-name", repr(log_record))
                    self.assertNotIn("raw-image-contract-name", repr(log_record))
                    self.assertNotIn("raw-pdf-contract-name", repr(log_record))
                    self.assertNotIn("pasted contract clause", repr(log_record))

            self.assertFalse(session.workspace.exists())

    def test_pdf_ingest_rasterizes_locally_without_network(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "uploads"
            pdf = Path(tmp) / "contract.pdf"
            pdf.write_bytes(_pdf_bytes(page_count=2, text="Financial review text"))

            def fail_network(*args: object, **kwargs: object) -> None:
                raise AssertionError("network use is forbidden during ingest")

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
                self.assertEqual(ingested.document.page_count, 2)
                self.assertEqual(len(ingested.document.pages), 2)
                self.assertEqual(len(ingested.derived_paths), 2)
                self.assertTrue(all(path.exists() for path in ingested.derived_paths))
                self.assertTrue(
                    all(session.workspace in path.parents for path in ingested.derived_paths)
                )
                self.assertEqual(
                    ingested.document.pages[0].text_source,
                    SCHEMAS.TextSource.TEXT_LAYER,
                )

    def test_reorder_rotate_delete_updates_ocr_page_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "uploads"
            pdf = Path(tmp) / "contract.pdf"
            pdf.write_bytes(_pdf_bytes(page_count=3))

            with INGEST.EphemeralIngestSession(upload_root=root) as session:
                ingested = session.ingest_pdf(pdf, content_type="application/pdf")
                original_page_ids = [page.page_id for page in ingested.document.pages]

                ingested = session.reorder_pages(ingested, [2, 0, 1])
                self.assertEqual([page.page_index for page in ingested.document.pages], [0, 1, 2])
                self.assertEqual(
                    [page.page_id for page in ingested.document.pages],
                    [original_page_ids[2], original_page_ids[0], original_page_ids[1]],
                )

                ingested = session.rotate_page(ingested, 1, 90)
                self.assertEqual(ingested.document.pages[1].rotation_deg, 90)

                deleted_raster = ingested.derived_paths[0]
                ingested = session.delete_page(ingested, 0)
                self.assertEqual(ingested.document.page_count, 2)
                self.assertEqual([page.page_index for page in ingested.document.pages], [0, 1])
                self.assertFalse(deleted_raster.exists())

    def test_rejected_pdf_statuses_do_not_store_source_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "uploads"
            fake_pdf = Path(tmp) / "fake.pdf"
            encrypted_pdf = Path(tmp) / "encrypted.pdf"
            fake_pdf.write_bytes(b"not a pdf")
            encrypted_pdf.write_bytes(b"%PDF-1.4\n/Encrypt\n/Type /Page\n%%EOF\n")

            with INGEST.EphemeralIngestSession(upload_root=root) as session:
                fake = session.ingest_pdf(fake_pdf, content_type="application/pdf")
                encrypted = session.ingest_pdf(encrypted_pdf, content_type="application/pdf")

                self.assertEqual(
                    fake.document.validation_status,
                    SCHEMAS.ValidationStatus.REJECTED_UNSUPPORTED,
                )
                self.assertEqual(
                    encrypted.document.validation_status,
                    SCHEMAS.ValidationStatus.REJECTED_ENCRYPTED,
                )
                self.assertIsNone(fake.stored_path)
                self.assertIsNone(encrypted.stored_path)

    def test_clear_deletes_source_rasters_and_paste_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "uploads"
            pdf = Path(tmp) / "contract.pdf"
            pdf.write_bytes(_pdf_bytes(page_count=2))

            session = INGEST.EphemeralIngestSession(upload_root=root)
            pdf_ingested = session.ingest_pdf(pdf, content_type="application/pdf")
            paste_ingested = session.ingest_paste("private pasted clause")
            workspace = session.workspace
            paths = (
                pdf_ingested.stored_path,
                paste_ingested.stored_path,
                *pdf_ingested.derived_paths,
            )
            self.assertTrue(all(path is not None and path.exists() for path in paths))

            session.clear()

            self.assertFalse(workspace.exists())


if __name__ == "__main__":
    unittest.main()

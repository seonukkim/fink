from __future__ import annotations

import importlib
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any


def _load_module(name: str) -> Any:
    src_root = Path(__file__).resolve().parents[2] / "src"
    src_text = src_root.as_posix()
    if src_text not in sys.path:
        sys.path.insert(0, src_text)
    return importlib.import_module(name)


INGEST = _load_module("fink.ingest")
SCHEMAS = _load_module("fink.schemas")
WEB = _load_module("fink.web")

PNG_1X1 = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR"
    b"\x00\x00\x00\x01"
    b"\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00"
    b"\x00\x00\x00\x00"
)
WEBP_1X1 = b"RIFF\x1a\x00\x00\x00WEBPVP8 " + b"\x00" * 16


def _pdf_bytes(page_texts: tuple[str, ...]) -> bytes:
    page_objects = []
    kids = []
    for idx, text in enumerate(page_texts):
        obj_id = 3 + idx
        kids.append(f"{obj_id} 0 R")
        stream = f"BT ({text}) Tj ET"
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
        f"2 0 obj\n<< /Type /Pages /Count {len(page_texts)} /Kids [{' '.join(kids)}] >>\nendobj\n"
        + "".join(page_objects)
        + "%%EOF\n"
    )
    return body.encode("utf-8")


class IngestUITests(unittest.TestCase):
    def test_ui_ingest_tests_all_modes_are_reachable_in_phone_and_desktop_ui(self) -> None:
        controls = WEB.input_mode_controls()
        modes = {control.mode for control in controls}
        self.assertEqual(modes, {"camera", "image", "pdf", "paste"})
        self.assertTrue(all(control.mobile_enabled for control in controls))
        self.assertTrue(all(control.desktop_enabled for control in controls))
        self.assertTrue(all(control.reaches_report for control in controls))

        pdf_control = next(control for control in controls if control.mode == "pdf")
        self.assertIn("application/pdf", pdf_control.accept)
        self.assertIn(".pdf", pdf_control.accept)

        layouts = WEB.responsive_ingest_layouts()
        self.assertEqual({layout.layout_id for layout in layouts}, {"mobile", "desktop"})
        for layout in layouts:
            self.assertEqual(set(layout.input_modes), modes)
            self.assertTrue(layout.pdf_upload_enabled)
            self.assertGreaterEqual(layout.min_touch_target_px, 44)
            self.assertEqual(set(layout.page_operations), set(WEB.PAGE_OPERATIONS))

        markup = WEB.render_index_html()
        self.assertIn('id="contract-file"', markup)
        self.assertIn('data-file-input="true"', markup)
        self.assertIn("application/pdf,.pdf", markup)
        self.assertIn("text/plain,.txt", markup)
        self.assertIn("image/png,image/jpeg,image/webp,image/heic,image/heif", markup)
        self.assertNotIn('data-ui-ingest-modes="camera image pdf paste"', markup)
        self.assertNotIn('class="upload-tile"', markup)
        self.assertIn('data-ingest-mode="paste"', markup)
        # The in-browser OCR page editor is intentionally not rendered in the
        # creator flow (a creator cannot reorder, rotate, or delete pages in the
        # browser), so the page-operation controls no longer appear in the
        # shell. The page-operation capability is still asserted at the layout
        # level above (layout.page_operations == WEB.PAGE_OPERATIONS).
        self.assertNotIn('data-mobile-page-ops="enabled"', markup)
        self.assertNotIn('data-desktop-page-ops="enabled"', markup)
        self.assertNotIn('class="page-editor"', markup)

    def test_ui_ingest_tests_all_modes_reach_valid_reports(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "uploads"
            camera = Path(tmp) / "camera.png"
            image = Path(tmp) / "image.webp"
            pdf = Path(tmp) / "document.pdf"
            camera.write_bytes(PNG_1X1)
            image.write_bytes(WEBP_1X1)
            pdf.write_bytes(_pdf_bytes(("Revenue share 10%",)))

            with INGEST.EphemeralIngestSession(upload_root=root) as session:
                items = (
                    session.ingest_camera(camera, content_type="image/png"),
                    session.ingest_image(image, content_type="image/webp"),
                    session.ingest_pdf(pdf, content_type="application/pdf"),
                    session.ingest_paste("Revenue share 10% Payment due 30 days"),
                )

                self.assertEqual(
                    {item.input_mode.value for item in items},
                    {"camera", "image", "pdf", "paste"},
                )
                for item in items:
                    summary = WEB.summarize_ingest_result(item)
                    report = item.build_report()
                    self.assertTrue(summary.report_ready)
                    self.assertIsNone(summary.local_error)
                    self.assertIsInstance(report, SCHEMAS.AnalysisReport)
                    self.assertIn("review priority", " ".join(report.disclaimers).lower())

    def test_ui_pdf_upload_test_page_ops_work_for_mobile_and_desktop(self) -> None:
        for layout in WEB.responsive_ingest_layouts():
            with self.subTest(layout=layout.layout_id):
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp) / "uploads"
                    pdf = Path(tmp) / "contract.pdf"
                    pdf.write_bytes(
                        _pdf_bytes(
                            (
                                "Revenue share 10% Payment due 30 days",
                                "Gross sales 2000000 KRW",
                                "Payment due 45 days",
                            )
                        )
                    )

                    with INGEST.EphemeralIngestSession(upload_root=root) as session:
                        ingested = session.ingest_pdf(pdf, content_type="application/pdf")
                        summary = WEB.summarize_ingest_result(ingested)
                        self.assertEqual(summary.input_mode, "pdf")
                        self.assertEqual(summary.validation_status, "accepted")
                        self.assertTrue(summary.report_ready)
                        self.assertEqual(set(summary.page_operations), set(WEB.PAGE_OPERATIONS))

                        original_page_ids = [page.page_id for page in ingested.document.pages]
                        ingested = WEB.move_preview_page(
                            session,
                            ingested,
                            from_index=2,
                            to_index=0,
                        )
                        self.assertEqual(
                            [page.page_id for page in ingested.document.pages],
                            [original_page_ids[2], original_page_ids[0], original_page_ids[1]],
                        )

                        ingested = WEB.rotate_preview_page(
                            session,
                            ingested,
                            page_index=1,
                            rotation_deg=90,
                        )
                        state = WEB.page_operation_state(ingested)
                        self.assertEqual(state.page_count, 3)
                        self.assertEqual(state.rotations_deg[1], 90)
                        self.assertTrue(state.can_delete)

                        preview = WEB.build_ocr_preview(ingested)
                        ingested = WEB.correct_preview_span(
                            session,
                            ingested,
                            span_id=preview[1].spans[0].span_id,
                            corrected_text="Revenue share 15% Payment due 60 days",
                        )
                        self.assertEqual(ingested.extraction_revision, 1)
                        self.assertEqual(len(ingested.corrections), 1)
                        self.assertIn("15%", WEB.preview_text(WEB.build_ocr_preview(ingested)))

                        ingested = WEB.delete_preview_page(session, ingested, page_index=2)
                        final_state = WEB.page_operation_state(ingested)
                        self.assertEqual(final_state.page_count, 2)
                        report = ingested.build_report()
                        self.assertIsInstance(report, SCHEMAS.AnalysisReport)

    def test_ui_pdf_upload_test_rejected_pdf_shows_clear_local_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "uploads"
            pdf = Path(tmp) / "raw-contract-name.pdf"
            pdf.write_bytes(b"not a pdf")

            with INGEST.EphemeralIngestSession(upload_root=root) as session:
                ingested = session.ingest_pdf(
                    pdf,
                    original_filename="raw-contract-name.pdf",
                    content_type="application/pdf",
                )
                self.assertEqual(
                    ingested.document.validation_status,
                    SCHEMAS.ValidationStatus.REJECTED_UNSUPPORTED,
                )

                message = WEB.local_upload_error(ingested)
                summary = WEB.summarize_ingest_result(ingested)
                self.assertIsNotNone(message)
                self.assertIn("PDF rejected locally", message)
                self.assertIn("Nothing was transmitted", message)
                self.assertNotIn("raw-contract-name", message)
                self.assertFalse(summary.report_ready)
                self.assertEqual(summary.page_operations, ())

        markup = WEB.render_index_html()
        self.assertIn('data-pdf-error-region="true"', markup)
        for expected in ("unsupported", "corrupted", "encrypted", "oversized"):
            self.assertIn(expected, markup)


if __name__ == "__main__":
    unittest.main()

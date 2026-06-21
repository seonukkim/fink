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


def _pdf_bytes(page_count: int = 2, text: str = "Contract text") -> bytes:
    page_objects = []
    kids = []
    for idx in range(page_count):
        obj_id = 3 + idx
        kids.append(f"{obj_id} 0 R")
        page_text = text if idx == 0 else ""
        stream = f"BT ({page_text}) Tj ET"
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


def _term_by_feature(ingested: Any, feature_id: str) -> Any:
    matches = [term for term in ingested.extracted_terms if term.feature_id == feature_id]
    if not matches:
        raise AssertionError(f"missing extracted term for {feature_id}")
    return matches[0]


class CorrectionFlowTests(unittest.TestCase):
    def test_correction_flow_test_inline_edit_refreshes_extraction_and_review_time(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "uploads"
            pdf = Path(tmp) / "contract.pdf"
            pdf.write_bytes(
                _pdf_bytes(text="Revenue share 10% Payment due 30 days")
            )

            with INGEST.EphemeralIngestSession(upload_root=root) as session:
                ingested = session.ingest_pdf(pdf, content_type="application/pdf")
                original_text_page_id = ingested.document.pages[0].page_id
                self.assertAlmostEqual(
                    _term_by_feature(ingested, "REVENUE_SHARE_RATE").value_norm,
                    0.10,
                )

                ingested = session.reorder_pages(ingested, [1, 0])
                ingested = session.rotate_page(ingested, 1, 90)
                preview = WEB.build_ocr_preview(ingested)

                self.assertEqual([page.page_index for page in preview], [0, 1])
                self.assertEqual(preview[1].page_id, original_text_page_id)
                self.assertEqual(preview[1].rotation_deg, 90)
                self.assertEqual(preview[1].spans[0].text, "Revenue share 10% Payment due 30 days")

                corrected = WEB.apply_inline_ocr_correction(
                    session,
                    ingested,
                    preview[1].spans[0].span_id,
                    "Revenue share 15% Payment due 45 days",
                )

                self.assertEqual(corrected.extraction_revision, 1)
                self.assertEqual(len(corrected.corrections), 1)
                correction = corrected.corrections[0]
                self.assertIsInstance(correction, SCHEMAS.HumanCorrection)
                self.assertEqual(correction.target_type, SCHEMAS.TargetType.OCR_SPAN)
                self.assertEqual(correction.before, "Revenue share 10% Payment due 30 days")
                self.assertEqual(correction.after, "Revenue share 15% Payment due 45 days")
                self.assertTrue(correction.counts_for_review_estimate)

                corrected_preview = WEB.build_ocr_preview(corrected)
                self.assertTrue(corrected.document.pages[1].is_user_corrected)
                self.assertTrue(corrected_preview[1].is_user_corrected)
                self.assertTrue(corrected_preview[1].spans[0].is_user_corrected)
                self.assertEqual(
                    corrected_preview[1].spans[0].text,
                    "Revenue share 15% Payment due 45 days",
                )
                self.assertIn("15%", WEB.preview_text(corrected_preview))
                self.assertNotIn("10%", WEB.preview_text(corrected_preview))

                pct = _term_by_feature(corrected, "REVENUE_SHARE_RATE")
                days = _term_by_feature(corrected, "PAYMENT_DUE_DAYS")
                self.assertAlmostEqual(pct.value_norm, 0.15)
                self.assertEqual(pct.source_span_ids, (correction.target_id,))
                self.assertEqual(days.value_norm, 45.0)

                report = corrected.build_report()
                self.assertEqual(
                    report.assessment.time_exposure.estimated_human_review_minutes,
                    INGEST.correction_review_minutes(corrected.corrections),
                )
                self.assertGreater(
                    report.assessment.time_exposure.estimated_human_review_minutes,
                    0.0,
                )
                self.assertIn(
                    "review-time heuristic",
                    " ".join(report.assessment.confidence.drivers),
                )

                log_record = corrected.to_log_record()
                self.assertEqual(log_record["correction_count"], 1)
                self.assertEqual(log_record["extraction_revision"], 1)
                self.assertNotIn("Revenue share", repr(log_record))
                self.assertNotIn("15%", repr(log_record))

    def test_correction_flow_test_over_domain_percent_is_opaque_not_crash(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "uploads"
            pdf = Path(tmp) / "penalty.pdf"
            pdf.write_bytes(_pdf_bytes(text="Penalty 200%"))

            with INGEST.EphemeralIngestSession(upload_root=root) as session:
                # A >100% figure must not raise out of ingest extraction.
                ingested = session.ingest_pdf(pdf, content_type="application/pdf")
                term = _term_by_feature(ingested, "REVENUE_SHARE_RATE")
                self.assertIsNone(term.value_norm)
                self.assertTrue(term.is_open_ended)
                self.assertEqual(term.value_raw, "200%")


if __name__ == "__main__":
    unittest.main()

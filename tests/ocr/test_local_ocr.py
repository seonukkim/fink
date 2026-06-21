from __future__ import annotations

import importlib
import os
import socket
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest.mock import patch


def _load_ocr():
    src_root = Path(__file__).resolve().parents[2] / "src"
    src_text = src_root.as_posix()
    if src_text not in sys.path:
        sys.path.insert(0, src_text)
    return importlib.import_module("fink.ocr")


def _load_schemas():
    src_root = Path(__file__).resolve().parents[2] / "src"
    src_text = src_root.as_posix()
    if src_text not in sys.path:
        sys.path.insert(0, src_text)
    return importlib.import_module("fink.schemas")


OCR = _load_ocr()
SCHEMAS = _load_schemas()

PNG_2X2 = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR"
    b"\x00\x00\x00\x02"
    b"\x00\x00\x00\x02"
    b"\x08\x02\x00\x00\x00"
    b"\x00\x00\x00\x00"
)


def _fail_network(*args: object, **kwargs: object) -> None:
    raise AssertionError("network use is forbidden during OCR")


class LocalOCRTests(unittest.TestCase):
    def test_ocr_offline_test_text_hint_produces_schema_spans(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            image = Path(tmp) / "page.png"
            image.write_bytes(PNG_2X2)
            engine = OCR.LocalOCREngine()

            with (
                patch.object(socket.socket, "connect", _fail_network),
                patch.object(socket, "create_connection", _fail_network),
            ):
                page = engine.recognize_image(
                    image,
                    page_index=3,
                    text_hint="정산 revenue 30%\nPayment due 30 days",
                    width_px=640,
                    height_px=480,
                )

            self.assertIsInstance(page, SCHEMAS.OCRPage)
            self.assertEqual(page.page_index, 3)
            self.assertEqual(page.text_source, SCHEMAS.TextSource.OCR)
            self.assertEqual(len(page.spans), 2)
            self.assertEqual(page.spans[0].lang, SCHEMAS.Lang.MIXED)
            self.assertEqual(page.spans[1].lang, SCHEMAS.Lang.EN)
            self.assertGreater(page.page_ocr_confidence, 0.0)
            for span in page.spans:
                self.assertIsInstance(span, SCHEMAS.OCRSpan)
                self.assertEqual(set(span.bbox), {"x", "y", "w", "h"})
                self.assertGreater(span.bbox["w"], 0)
                self.assertGreater(span.bbox["h"], 0)
                self.assertGreaterEqual(span.confidence, 0.0)
                self.assertLessEqual(span.confidence, 1.0)

    def test_ocr_schema_ok_parses_local_tesseract_tsv_without_network(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            image = tmp_path / "page.png"
            image.write_bytes(PNG_2X2)
            bin_dir = tmp_path / "bin"
            bin_dir.mkdir()
            tesseract = bin_dir / "tesseract"
            tesseract.write_text(
                textwrap.dedent(
                    """\
                    #!/usr/bin/env python3
                    print(
                        "level\\tpage_num\\tblock_num\\tpar_num\\tline_num\\tword_num\\t"
                        "left\\ttop\\twidth\\theight\\tconf\\ttext"
                    )
                    print("5\\t1\\t1\\t1\\t1\\t1\\t10\\t11\\t100\\t20\\t88\\t정산")
                    print("5\\t1\\t1\\t1\\t1\\t2\\t120\\t11\\t90\\t20\\t92\\tRevenue")
                    """
                ),
                encoding="utf-8",
            )
            tesseract.chmod(0o700)
            engine = OCR.LocalOCREngine()

            with (
                patch.dict(
                    os.environ,
                    {"PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}"},
                ),
                patch.object(socket.socket, "connect", _fail_network),
                patch.object(socket, "create_connection", _fail_network),
            ):
                page = engine.recognize_image(image, width_px=300, height_px=200)

            self.assertEqual([span.text for span in page.spans], ["정산", "Revenue"])
            self.assertEqual(
                [span.lang for span in page.spans],
                [SCHEMAS.Lang.KO, SCHEMAS.Lang.EN],
            )
            self.assertAlmostEqual(page.spans[0].confidence, 0.88)
            self.assertAlmostEqual(page.page_ocr_confidence, 0.90)
            self.assertEqual(page.spans[0].bbox, {"x": 10, "y": 11, "w": 100, "h": 20})

    def test_ev_ocr_cer_wer_are_computable(self) -> None:
        engine = OCR.LocalOCREngine()
        page = engine.recognize_text("정산 revenue 30%", width_px=500, height_px=120)
        exact = OCR.evaluate_ocr("정산 revenue 30%", page)

        self.assertEqual(exact.ev_ocr_cer, 0.0)
        self.assertEqual(exact.ev_ocr_wer, 0.0)
        self.assertEqual(exact.reference_words, 3)
        self.assertAlmostEqual(OCR.character_error_rate("abc", "adc"), 1 / 3)
        self.assertAlmostEqual(
            OCR.word_error_rate("alpha beta gamma", "alpha x gamma"),
            1 / 3,
        )

    def test_missing_local_backend_is_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            image = Path(tmp) / "page.png"
            image.write_bytes(PNG_2X2)
            engine = OCR.LocalOCREngine(OCR.LocalOCRConfig(tesseract_cmd="not-installed-ocr"))

            with self.assertRaises(OCR.OCRBackendUnavailable):
                engine.recognize_image(image)


if __name__ == "__main__":
    unittest.main()

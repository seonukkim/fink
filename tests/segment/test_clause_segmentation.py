from __future__ import annotations

import importlib
import sys
import unittest
from pathlib import Path
from typing import Any


def _load_module(name: str) -> Any:
    src_root = Path(__file__).resolve().parents[2] / "src"
    src_text = src_root.as_posix()
    if src_text not in sys.path:
        sys.path.insert(0, src_text)
    return importlib.import_module(name)


SCHEMAS = _load_module("fink.schemas")
SEGMENT = _load_module("fink.segment")


def _span(
    span_id: str,
    text: str,
    *,
    x: int = 10,
    y: int = 10,
    w: int = 420,
    h: int = 24,
    confidence: float = 0.90,
    corrected_text: str | None = None,
) -> Any:
    return SCHEMAS.OCRSpan(
        span_id=span_id,
        text=text,
        bbox={"x": x, "y": y, "w": w, "h": h},
        confidence=confidence,
        lang=SCHEMAS.Lang.MIXED,
        corrected_text=corrected_text,
    )


def _page(spans: tuple[Any, ...], *, page_index: int = 0) -> Any:
    return SCHEMAS.OCRPage(
        page_id=f"page-{page_index}",
        page_index=page_index,
        rotation_deg=0,
        width_px=800,
        height_px=1200,
        spans=spans,
        page_ocr_confidence=0.90,
        text_source=SCHEMAS.TextSource.OCR,
        is_user_corrected=False,
    )


class ClauseSegmentationTests(unittest.TestCase):
    def test_segmentation_tests_clause_records_link_source_spans(self) -> None:
        page = _page(
            (
                _span("s1", "제1조 정산", y=10),
                _span("s2", "회사는 월별 정산서를 제공한다.", y=45),
                _span("s3", "① 플랫폼 수수료는 명시된 항목만 공제한다.", y=80),
                _span("s4", "제2조 지급", y=115),
                _span("s5", "Payment due within 30 days.", y=150),
            )
        )

        clauses = SEGMENT.segment_pages((page,))

        self.assertEqual(len(clauses), 3)
        self.assertTrue(all(isinstance(clause, SCHEMAS.Clause) for clause in clauses))
        self.assertEqual([clause.clause_index for clause in clauses], [0, 1, 2])
        self.assertEqual(clauses[0].source_span_ids, ("s1", "s2"))
        self.assertEqual(clauses[1].source_span_ids, ("s3",))
        self.assertEqual(clauses[2].source_span_ids, ("s4", "s5"))
        self.assertIn("월별 정산서", clauses[0].text_ko)
        self.assertEqual(clauses[1].heading_ko, "① 플랫폼 수수료는 명시된 항목만 공제한다.")
        for clause in clauses:
            self.assertGreaterEqual(len(clause.source_span_ids), 1)
            self.assertGreaterEqual(clause.seg_confidence, 0.0)
            self.assertLessEqual(clause.seg_confidence, 1.0)

    def test_word_level_ocr_spans_are_grouped_into_logical_lines(self) -> None:
        page = _page(
            (
                _span("s1", "Article", x=10, y=20, w=70),
                _span("s2", "1", x=90, y=21, w=20),
                _span("s3", "Revenue", x=120, y=20, w=80),
                _span("s4", "Creator receives 40%", x=10, y=58, w=220),
                _span("s5", "Section", x=10, y=110, w=70),
                _span("s6", "2", x=88, y=111, w=20),
                _span("s7", "Payment", x=118, y=110, w=80),
            )
        )

        clauses = SEGMENT.segment_pages((page,))

        self.assertEqual(len(clauses), 2)
        self.assertEqual(clauses[0].text_ko.splitlines()[0], "Article 1 Revenue")
        self.assertEqual(clauses[0].source_span_ids, ("s1", "s2", "s3", "s4"))
        self.assertEqual(clauses[1].text_ko, "Section 2 Payment")
        self.assertEqual(clauses[1].source_span_ids, ("s5", "s6", "s7"))

    def test_corrected_span_text_drives_clause_text_without_losing_provenance(self) -> None:
        page = _page(
            (
                _span("s1", "제1조 정산", y=20),
                _span("s2", "제1조 지급", y=60, corrected_text="제2조 지급"),
                _span("s3", "지급기한은 30일로 한다.", y=95),
            )
        )

        clauses = SEGMENT.segment_pages((page,))

        self.assertEqual(len(clauses), 2)
        self.assertEqual(clauses[1].heading_ko, "제2조 지급")
        self.assertEqual(clauses[1].source_span_ids, ("s2", "s3"))
        self.assertNotIn("제1조 지급", clauses[1].text_ko)

    def test_ev_seg_is_computable_from_clause_source_span_boundaries(self) -> None:
        page = _page(
            (
                _span("s1", "제1조 정산", y=10),
                _span("s2", "정산자료를 제공한다.", y=45),
                _span("s3", "① 공제항목은 별지와 같다.", y=80),
                _span("s4", "제2조 지급", y=115),
            )
        )
        predicted = SEGMENT.segment_pages((page,))
        gold = (("s1", "s2"), ("s3",), ("s4",))

        metrics = SEGMENT.evaluate_clause_segmentation(
            gold,
            predicted,
            span_order=("s1", "s2", "s3", "s4"),
        )

        self.assertEqual(metrics.ev_seg, 1.0)
        self.assertEqual(metrics.boundary_precision, 1.0)
        self.assertEqual(metrics.boundary_recall, 1.0)
        self.assertEqual(metrics.matched_boundary_count, 2)
        self.assertEqual(metrics.gold_boundary_count, 2)
        self.assertEqual(metrics.predicted_boundary_count, 2)

    def test_ev_seg_supports_windowed_boundary_tolerance(self) -> None:
        exact = SEGMENT.evaluate_segmentation((2, 5), (3, 5), tolerance=0)
        windowed = SEGMENT.evaluate_segmentation((2, 5), (3, 5), tolerance=1)

        self.assertAlmostEqual(exact.ev_seg, 0.5)
        self.assertEqual(windowed.ev_seg_boundary_f1, 1.0)
        self.assertEqual(windowed.tolerance, 1)


if __name__ == "__main__":
    unittest.main()

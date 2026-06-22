from __future__ import annotations

import html
import importlib
import json
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


ANALYZE = _load_module("fink.web.analyze")
SCHEMAS = _load_module("fink.schemas")
WEB = _load_module("fink.web")

SYNTHETIC_CLAUSE = (
    "제3조(정산) 정산은 매 분기 종료일로부터 90일 이내에 지급하며, "
    "회사는 일반 경비를 공제할 수 있다."
)


def _ocr_page(
    text: str,
    *,
    span_id: str = "span-source-1",
    text_source: Any | None = None,
    corrected_text: str | None = None,
    is_user_corrected: bool = False,
    confidence: float = 1.0,
) -> Any:
    return SCHEMAS.OCRPage(
        page_id="page-0",
        page_index=0,
        rotation_deg=0,
        width_px=1000,
        height_px=80,
        spans=(
            SCHEMAS.OCRSpan(
                span_id=span_id,
                text=text,
                bbox={"x": 0, "y": 0, "w": 900, "h": 20},
                confidence=confidence,
                lang=SCHEMAS.Lang.KO,
                corrected_text=corrected_text,
            ),
        ),
        page_ocr_confidence=confidence,
        text_source=text_source or SCHEMAS.TextSource.OCR,
        is_user_corrected=is_user_corrected,
    )


def _clause(text: str, *, span_id: str = "span-source-1") -> Any:
    return SCHEMAS.Clause(
        clause_id="clause-source-1",
        clause_index=0,
        text_ko=text,
        source_span_ids=(span_id,),
        seg_confidence=1.0,
    )


def _finding() -> dict[str, Any]:
    return {
        "finding_id": "finding-source-1",
        "rank": 1,
        "title": {"ko": "매출 기준·공제", "en": "Revenue base and deductions"},
        "source": {
            "clause_id": "clause-source-1",
            "exact_excerpt": SYNTHETIC_CLAUSE,
        },
    }


class SourceHighlightTests(unittest.TestCase):
    def test_synthetic_clause_gets_exact_selective_roles_not_whole_clause(self) -> None:
        findings, payload = WEB.build_source_highlight_payload(
            source_pages=(_ocr_page(SYNTHETIC_CLAUSE),),
            clauses=(_clause(SYNTHETIC_CLAUSE),),
            findings=(_finding(),),
        )

        self.assertEqual(payload["sources"][0]["status"], WEB.HIGHLIGHT_STATUS_VALIDATED)
        segments = payload["sources"][0]["segments"]
        timing = [
            segment
            for segment in segments
            if segment.get("text") == "90일 이내" and segment.get("highlighted")
        ]
        general_expense = [
            segment
            for segment in segments
            if segment.get("text") == "일반 경비" and segment.get("highlighted")
        ]

        self.assertEqual(timing[0]["roles"], ["timing_or_term"])
        self.assertEqual(
            general_expense[0]["roles"],
            ["deduction_recoupment_or_liability", "ambiguity_or_missing_bound"],
        )
        highlighted_text = "".join(
            segment["text"] for segment in segments if segment.get("highlighted")
        )
        self.assertNotEqual(highlighted_text, SYNTHETIC_CLAUSE)
        self.assertLess(len(highlighted_text), len(SYNTHETIC_CLAUSE))
        self.assertEqual(
            findings[0]["source"]["highlight_status"],
            WEB.HIGHLIGHT_STATUS_VALIDATED,
        )

    def test_malformed_candidates_fail_closed(self) -> None:
        valid = WEB.SourceHighlightCandidate(
            finding_id="finding-source-1",
            clause_id="clause-source-1",
            source_span_id="span-source-1",
            start=SYNTHETIC_CLAUSE.index("90일"),
            end=SYNTHETIC_CLAUSE.index("90일") + len("90일 이내"),
            exact_text="90일 이내",
            roles=("timing_or_term",),
        )
        wrong_text = WEB.SourceHighlightCandidate(
            finding_id="finding-source-1",
            clause_id="clause-source-1",
            source_span_id="span-source-1",
            start=0,
            end=4,
            exact_text="not-the-slice",
            roles=("timing_or_term",),
        )
        missing_finding = WEB.SourceHighlightCandidate(
            finding_id="missing-finding",
            clause_id="clause-source-1",
            source_span_id="span-source-1",
            start=0,
            end=4,
            exact_text=SYNTHETIC_CLAUSE[:4],
            roles=("timing_or_term",),
        )
        out_of_range = WEB.SourceHighlightCandidate(
            finding_id="finding-source-1",
            clause_id="clause-source-1",
            source_span_id="span-source-1",
            start=0,
            end=len(SYNTHETIC_CLAUSE) + 1,
            exact_text=SYNTHETIC_CLAUSE,
            roles=("timing_or_term",),
        )

        validated = WEB.validate_source_highlight_candidates(
            (wrong_text, missing_finding, out_of_range, valid),
            finding_ids={"finding-source-1"},
            clause_by_id={"clause-source-1": _clause(SYNTHETIC_CLAUSE)},
            span_text_by_id={"span-source-1": SYNTHETIC_CLAUSE},
        )

        self.assertEqual(validated, (valid,))

    def test_missing_span_yields_exact_position_needed_state(self) -> None:
        findings, payload = WEB.build_source_highlight_payload(
            source_pages=(_ocr_page("패턴 없는 문장입니다."),),
            clauses=(_clause("패턴 없는 문장입니다."),),
            findings=(_finding(),),
        )

        self.assertEqual(payload["sources"][0]["status"], WEB.HIGHLIGHT_STATUS_MISSING)
        self.assertEqual(
            payload["sources"][0]["status_label"]["ko"],
            WEB.MISSING_EXACT_SPAN_KO,
        )
        self.assertEqual(
            findings[0]["source"]["highlight_status_label"]["ko"],
            WEB.MISSING_EXACT_SPAN_KO,
        )

    def test_analyze_payload_contains_source_navigation_and_no_client_regex_contract(self) -> None:
        result = ANALYZE.run_local_analysis(
            pasted_text=SYNTHETIC_CLAUSE,
            ui_locale=SCHEMAS.UILocale.KO,
        )
        payload = ANALYZE.analysis_result_to_payload(result, SCHEMAS.UILocale.KO)

        encoded = json.dumps(payload["source_highlights"], ensure_ascii=False)
        self.assertGreaterEqual(payload["source_highlights"]["source_count"], 1)
        first_source = payload["source_highlights"]["sources"][0]
        self.assertTrue(first_source["anchor_id"].startswith("source-"))
        self.assertTrue(first_source["finding_anchor_id"].startswith("finding-"))
        self.assertIn("90일 이내", encoded)
        self.assertIn("일반 경비", encoded)
        self.assertIn("timing_or_term", encoded)
        self.assertIn("deduction_recoupment_or_liability", encoded)
        self.assertIn("ambiguity_or_missing_bound", encoded)

        script = WEB.app_js()
        self.assertNotIn("RegExp(", script)
        self.assertNotIn("querySelectorAll(\"mark", script)

    def test_html_and_script_source_text_is_inert(self) -> None:
        injected = (
            '제3조(정산) <script>alert(1)</script> 정산은 90일 이내에 지급하며, '
            '회사는 <img src=x onerror="alert(1)"> 일반 경비를 공제할 수 있다.'
        )
        result = ANALYZE.run_local_analysis(
            pasted_text=injected,
            ui_locale=SCHEMAS.UILocale.KO,
        )
        view_model = WEB.build_creator_review_view_model(result, SCHEMAS.UILocale.KO)
        markup = WEB.render_report_html(view_model)

        self.assertNotIn("<script>alert(1)</script>", markup)
        self.assertNotIn('<img src=x onerror="alert(1)">', markup)
        self.assertIn(html.escape("<script>alert(1)</script>"), markup)
        self.assertIn(html.escape('<img src=x onerror="alert(1)">', quote=True), markup)
        self.assertIn('data-source-highlights="true"', markup)
        self.assertIn('data-source-highlight-toggle="true"', markup)
        self.assertIn('data-source-nav="finding-to-source"', markup)
        self.assertIn('data-source-nav="source-to-finding"', markup)

    def test_synchronized_reader_uses_exact_focus_anchor_for_paste_text(self) -> None:
        result = ANALYZE.run_local_analysis(
            pasted_text=SYNTHETIC_CLAUSE,
            ui_locale=SCHEMAS.UILocale.KO,
        )
        view_model = WEB.build_creator_review_view_model(result, SCHEMAS.UILocale.KO)
        payload = view_model.to_payload()
        markup = WEB.render_report_html(view_model)

        source = payload["source_highlights"]["sources"][0]
        self.assertEqual(source["text_source"], "text_layer")
        self.assertEqual(source["render_mode"], "inline_selectable_text")
        self.assertFalse(source["has_real_bbox_provenance"])
        self.assertTrue(source["focus_anchor_id"].startswith("source-span-"))
        self.assertEqual(
            payload["findings"][0]["source"]["focus_anchor_id"],
            source["focus_anchor_id"],
        )
        for segment in source["segments"]:
            self.assertNotIn("page_boxes", segment)
            self.assertNotIn("bbox_provenance", segment)

        self.assertIn('data-contract-reader="synchronized"', markup)
        self.assertIn('data-reader-layout="source-left-report-right"', markup)
        self.assertIn('data-desktop-min-width-px="1100"', markup)
        self.assertIn('data-reader-pane="source"', markup)
        self.assertIn('data-reader-pane="report"', markup)
        self.assertIn('data-mobile-reader-links="true"', markup)
        self.assertIn("원문 보기", markup)
        self.assertIn("검토 항목으로 돌아가기", markup)
        self.assertIn('data-source-nav="finding-to-source"', markup)
        self.assertIn('data-source-nav="source-to-finding"', markup)
        self.assertIn('data-source-focus-target="exact-span"', markup)
        self.assertIn('tabindex="-1"', markup)
        self.assertNotIn('data-page-box-overlay="real-bbox"', markup)

    def test_ocr_reader_uses_real_bbox_provenance_and_labels_correction(self) -> None:
        findings, payload = WEB.build_source_highlight_payload(
            source_pages=(
                _ocr_page(
                    "제3조 정산은 90일 이내 지급하며 회사는 일반 경비를 공제할 수 있다.",
                    corrected_text=SYNTHETIC_CLAUSE,
                    is_user_corrected=True,
                    confidence=0.91,
                ),
            ),
            clauses=(_clause(SYNTHETIC_CLAUSE),),
            findings=(_finding(),),
        )

        source = payload["sources"][0]
        highlighted = [segment for segment in source["segments"] if segment.get("highlighted")]
        with_boxes = [segment for segment in highlighted if segment.get("page_boxes")]

        self.assertEqual(source["text_source"], "ocr")
        self.assertEqual(source["render_mode"], "reconstructed_ocr_text")
        self.assertTrue(source["has_real_bbox_provenance"])
        self.assertTrue(source["is_user_corrected"])
        self.assertEqual(source["text_source_label"]["ko"], "수정된 OCR 재구성 텍스트")
        self.assertTrue(with_boxes)
        self.assertEqual(with_boxes[0]["bbox_provenance"], "real_ocr_bbox")
        self.assertEqual(with_boxes[0]["page_boxes"][0]["provenance"], "real_ocr_bbox")
        self.assertEqual(findings[0]["source"]["focus_anchor_id"], source["focus_anchor_id"])

    def test_text_layer_never_exports_page_boxes_even_when_bbox_fields_exist(self) -> None:
        first_findings, first_payload = WEB.build_source_highlight_payload(
            source_pages=(
                _ocr_page(SYNTHETIC_CLAUSE, text_source=SCHEMAS.TextSource.TEXT_LAYER),
            ),
            clauses=(_clause(SYNTHETIC_CLAUSE),),
            findings=(_finding(),),
        )
        second_findings, second_payload = WEB.build_source_highlight_payload(
            source_pages=(
                _ocr_page(SYNTHETIC_CLAUSE, text_source=SCHEMAS.TextSource.TEXT_LAYER),
            ),
            clauses=(_clause(SYNTHETIC_CLAUSE),),
            findings=(_finding(),),
        )

        first_source = first_payload["sources"][0]
        self.assertEqual(first_source["text_source"], "text_layer")
        self.assertFalse(first_source["has_real_bbox_provenance"])
        self.assertEqual(
            first_findings[0]["source"]["focus_anchor_id"],
            second_findings[0]["source"]["focus_anchor_id"],
        )
        self.assertEqual(
            first_source["focus_anchor_id"],
            second_payload["sources"][0]["focus_anchor_id"],
        )
        for segment in first_source["segments"]:
            self.assertNotIn("page_boxes", segment)
        self.assertEqual(
            first_findings[0]["source"]["focus_anchor_id"],
            second_findings[0]["source"]["focus_anchor_id"],
        )

    def test_ocr_text_hint_does_not_fabricate_page_box_overlay(self) -> None:
        _findings, payload = WEB.build_source_highlight_payload(
            source_pages=(_ocr_page(SYNTHETIC_CLAUSE, text_source=SCHEMAS.TextSource.OCR),),
            clauses=(_clause(SYNTHETIC_CLAUSE),),
            findings=(_finding(),),
        )

        source = payload["sources"][0]
        self.assertEqual(source["text_source"], "ocr")
        self.assertEqual(source["render_mode"], "reconstructed_ocr_text")
        self.assertFalse(source["has_real_bbox_provenance"])
        self.assertTrue(any(segment.get("highlighted") for segment in source["segments"]))
        for segment in source["segments"]:
            self.assertNotIn("page_boxes", segment)
            self.assertNotIn("bbox_provenance", segment)

    def test_css_and_js_support_focus_safe_reader_navigation(self) -> None:
        markup = WEB.render_index_html(WEB.resolve_bind_settings())
        script = WEB.app_js()

        self.assertIn("@media (min-width: 1100px)", markup)
        self.assertIn("grid-template-columns: minmax(0, 1fr)", markup)
        self.assertIn("scroll-margin: calc(var(--space-4) + 44px)", markup)
        self.assertIn('[data-active-anchor="true"]', markup)
        self.assertNotIn("position: sticky", markup)

        self.assertIn("function activateReaderAnchor(link)", script)
        self.assertIn('workspace.setAttribute("data-reader-layout", "single-column")', script)
        self.assertIn("target.scrollIntoView", script)
        self.assertIn("target.focus({ preventScroll: true })", script)
        self.assertIn("data-active-anchor", script)
        self.assertIn("[data-source-nav], [data-reader-jump]", script)
        self.assertIn("data-page-box-overlay", script)


if __name__ == "__main__":
    unittest.main()

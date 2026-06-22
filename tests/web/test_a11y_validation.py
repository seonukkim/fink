from __future__ import annotations

import importlib
import json
import subprocess
import sys
import unittest
from pathlib import Path
from typing import Any


def _load_module(name: str) -> Any:
    repo_root = Path(__file__).resolve().parents[2]
    src_root = repo_root / "src"
    for path in (repo_root, src_root):
        path_text = path.as_posix()
        if path_text not in sys.path:
            sys.path.insert(0, path_text)
    return importlib.import_module(name)


ANALYZE = _load_module("fink.web.analyze")
CONTRAST = _load_module("scripts.web_a11y_contrast_check")
SCHEMAS = _load_module("fink.schemas")
WEB = _load_module("fink.web")

SYNTHETIC_CLAUSE = (
    "제3조(정산) 정산은 매 분기 종료일로부터 90일 이내에 지급하며, "
    "회사는 일반 경비를 공제할 수 있다."
)


class WebA11yValidationTests(unittest.TestCase):
    def test_automated_design_token_contrast_check_passes_with_claim_boundary(self) -> None:
        report = CONTRAST.build_report()
        checks = report["automated_checks"]

        self.assertTrue(checks["ok"], checks["failures"])
        self.assertEqual(checks["normal_text_minimum"], 4.5)
        self.assertEqual(checks["large_text_and_ui_state_minimum"], 3.0)
        self.assertGreaterEqual(len(checks["items"]), 12)
        self.assertIn("not a full WCAG", report["claim_boundary"])
        self.assertIn("keyboard or screen-reader review", report["claim_boundary"])

        script = Path(__file__).resolve().parents[2] / "scripts" / "web_a11y_contrast_check.py"
        completed = subprocess.run(
            [sys.executable, str(script), "--json"],
            check=True,
            capture_output=True,
            text=True,
        )
        cli_report = json.loads(completed.stdout)
        self.assertTrue(cli_report["automated_checks"]["ok"])

    def test_responsive_motion_forced_colors_and_print_fallbacks_are_present(self) -> None:
        markup = WEB.render_index_html(WEB.resolve_bind_settings())

        self.assertIn('<meta name="viewport"', markup)
        self.assertNotIn("maximum-scale", markup.lower())
        self.assertIn(
            'data-responsive-validation-targets="320-no-horizontal-overflow '
            '390x844 768x1024 1440x900 200-percent-zoom"',
            markup,
        )
        for expected in (
            "@media (max-width: 480px)",
            "@media (min-width: 768px)",
            "@media (min-width: 900px)",
            "@media (min-width: 1100px)",
            "grid-template-columns: minmax(0, 1fr)",
            "overflow-x: auto",
            "scroll-padding: calc(var(--space-4) + 44px)",
            "scroll-margin: calc(var(--space-4) + 44px)",
        ):
            self.assertIn(expected, markup)

        for expected in (
            "@media (prefers-reduced-motion: reduce)",
            "scroll-behavior: auto !important",
            "@media (forced-colors: active)",
            "color: CanvasText",
            "outline: 3px solid Highlight",
            "@media print",
            "details:not([open]) > *:not(summary)",
            "text-decoration: underline",
            "font-weight: 700",
        ):
            self.assertIn(expected, markup)
        self.assertNotIn("position: sticky", markup)

        script = WEB.app_js()
        self.assertIn("function prefersReducedMotion()", script)
        self.assertIn('matchMedia("(prefers-reduced-motion: reduce)")', script)
        self.assertIn('behavior: prefersReducedMotion() ? "auto" : "smooth"', script)
        self.assertIn('scrollIntoView(scrollOptions("end"))', script)
        self.assertIn("@keyframes fink-result-message-in", markup)
        self.assertIn(".result-sequence-msg", markup)

    def test_keyboard_and_screen_reader_oriented_path_uses_native_named_controls(self) -> None:
        result = ANALYZE.run_local_analysis(
            pasted_text=SYNTHETIC_CLAUSE,
            ui_locale=SCHEMAS.UILocale.KO,
        )
        view_model = WEB.build_creator_review_view_model(result, SCHEMAS.UILocale.KO)
        markup = WEB.render_index_html(WEB.resolve_bind_settings()) + WEB.render_report_html(
            view_model
        )
        script = WEB.app_js()

        # The chat shell exposes header, nav (locale toggle), main (the thread),
        # and aside (the Notice disclosure panel); it has no footer landmark.
        for landmark in ("<header", "<nav", "<main", "<aside"):
            self.assertIn(landmark, markup)
        self.assertNotIn("<footer", markup)
        for heading in ("<h1", "<h2", "<h3"):
            self.assertIn(heading, markup)
        self.assertNotIn('role="button"', markup)
        self.assertNotIn("onclick=", markup.lower())

        for expected in (
            'id="analyze-btn"',
            'aria-controls="result analyze-status"',
            'id="result"',
            'role="region"',
            'role="status"',
            'role="alert"',
            'aria-live="assertive"',
            'data-finding-id=',
            'data-source-nav="finding-to-source"',
            'data-source-nav="source-to-finding"',
            'data-copy-question="true"',
            'data-finding-section="section.evidence"',
            'data-locale-button="toggle"',
            'aria-label="한국어와 영어 전환 / Switch between Korean and English"',
            'aria-label="물어볼 말 복사 / Copy question to ask"',
            'aria-label="원문 위치로 이동 / Open source excerpt"',
            'aria-label="검토 항목으로 돌아가기 / Back to finding"',
            'aria-label="출처 하이라이트 켜기 또는 끄기 / Toggle source highlights"',
            'aria-describedby="analyze-status"',
            'aria-describedby="pdf-error-region"',
        ):
            self.assertIn(expected, markup)

        for expected in (
            'button.setAttribute("aria-busy"',
            "function prepareResultOpeningMessage(targetItem, container)",
            "function appendResultContentBubble(className, content, index)",
            "function renderFindingLine(record)",
            "function renderDimensionChips(appendBubble, payload)",
            'item.setAttribute("data-result-sequence-item", "true")',
            'row.setAttribute("data-result-dimension-chips", "true")',
            'collectAuditEvidenceIds',
            # The single locale toggle flips KO<->EN on click instead of reading
            # a per-button locale value.
            'setLocale(activeLocale() === "en" ? "ko" : "en")',
        ):
            self.assertIn(expected, script)
        for removed in (
            'data-scenario-recalculate-button',
            'aria-label="시나리오 다시 계산 / Recalculate scenario"',
            'data-highlight-cue=',
            "function renderCheckFirst",
            "function renderDimensions",
            "function renderGroundedQa",
            "[data-source-nav], [data-reader-jump]",
            "copyQuestion(copyButton)",
        ):
            self.assertNotIn(removed, script)

    def test_meaningful_states_have_non_color_labels_and_touch_targets(self) -> None:
        markup = WEB.render_index_html(WEB.resolve_bind_settings())
        report = WEB.render_report_html(
            WEB.build_creator_review_view_model(
                ANALYZE.run_local_analysis(
                    pasted_text=SYNTHETIC_CLAUSE,
                    ui_locale=SCHEMAS.UILocale.KO,
                ),
                SCHEMAS.UILocale.KO,
            )
        )
        script = WEB.app_js()
        # The creator flow no longer renders the empty report shell inside the
        # index page. Combine the shell, report renderer, and app script so this
        # test covers the current chat result hooks and the report-only labels.
        combined = markup + report + WEB.render_empty_report_shell_html() + script

        for cue in (
            'data-source-highlight',
            'source-highlight',
            "정확한 출처 문구 확인됨",
            "practice reference / non-scoring",
            "근거 확인 필요",
            "입력 필요",
            "통화 확인 필요",
        ):
            self.assertIn(cue, combined)

        for removed in (
            'data-highlight-cue="solid underline"',
            'data-highlight-cue="dashed underline"',
            'data-highlight-cue="left border"',
            'data-highlight-cue="double underline"',
            'data-highlight-cue="dotted underline"',
            'data-role-label-ko=',
            "UNVERIFIED",
        ):
            self.assertNotIn(removed, script)

        for expected in (
            "button, input, textarea",
            "min-height: 44px",
            "summary {\n  min-height: 44px;",
            ".reader-jump-links a, .reader-back-link, .source-status a",
            ".page-actions button { flex: 1 1 6rem; }",
        ):
            self.assertIn(expected, markup)


if __name__ == "__main__":
    unittest.main()

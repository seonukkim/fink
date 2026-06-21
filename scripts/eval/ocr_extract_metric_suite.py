from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Mapping, Sequence
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path
from statistics import mean
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
if SRC_ROOT.as_posix() not in sys.path:
    sys.path.insert(0, SRC_ROOT.as_posix())

from fink import extract as EXTRACT  # noqa: E402
from fink import ocr as OCR  # noqa: E402
from fink import schemas as SCHEMAS  # noqa: E402
from fink import segment as SEGMENT  # noqa: E402


TASK_ID = "FINK-S5-02"
SUITE_ID = "ocr_extract_metric_suite"
RESULT_LOG_PATH = Path(__file__).with_name("ocr_extract_metric_suite_results.json")
REGISTERED_GATE_IDS = ("ocr_extract_metric_run",)
PAPER_SECTIONS = ("05_experiments.md", "06_results.md")
METRIC_IDS = (
    "EV-OCR-CER",
    "EV-OCR-WER",
    "EV-EXACT-MONEY",
    "EV-EXACT-PCT",
    "EV-EXACT-DATE",
    "EV-EXACT-DUR",
    "EV-SEG",
)
RESULT_LEDGER_COLUMNS = (
    "result_id",
    "experiment_id",
    "metric",
    "value",
    "artifact_path",
    "status",
    "reviewer",
    "notes",
)
ARTIFACT_PATH = "scripts/eval/ocr_extract_metric_suite_results.json"

REFERENCE_TEXT = "\n".join(
    (
        "제1조 정산",
        "총매출 1,200,000원 및 수익배분율 30%.",
        "제2조 지급",
        "Payment due March 5, 2026 and 45 days.",
    )
)
OCR_EXACT_TEXT = "정산 revenue 30%"
OCR_NOISY_REFERENCE_TEXT = "Payment due 45 days"
OCR_NOISY_HYPOTHESIS_TEXT = "Payment due 54 days"


def run_ocr_extract_metric_suite() -> dict[str, Any]:
    page = OCR.LocalOCREngine().recognize_text(REFERENCE_TEXT)
    clauses = SEGMENT.segment_pages((page,), clause_id_prefix="metric-clause")
    predicted_terms = EXTRACT.extract_terms_from_clauses(clauses)

    metric_values = {
        **_ocr_metric_values(),
        **_exact_metric_values(predicted_terms),
        **_segmentation_metric_values(page, clauses),
    }
    gate_ok = _all_metrics_computed(metric_values) and len(clauses) == 2
    cases = [
        {
            "id": "ocr_extract_metric_run",
            "metrics": list(METRIC_IDS),
            "description": (
                "Compute OCR CER/WER, exact financial-term extraction metrics, "
                "and clause-boundary segmentation quality on synthetic/sanitized fixtures."
            ),
            "status": "PASS" if gate_ok else "FAIL",
            "expected": {
                "required_metrics": list(METRIC_IDS),
                "result_ledger_status": "measured",
                "synthetic_only": True,
                "no_legal_verdict": True,
            },
            "observed": {
                "metric_values": metric_values,
                "clause_count": len(clauses),
                "extracted_term_count": len(predicted_terms),
                "fixture_sha256": _fixture_sha256(),
            },
        }
    ]
    result_ledger_rows = _result_ledger_rows(metric_values)
    passed = sum(1 for case in cases if case["status"] == "PASS")
    failed = len(cases) - passed
    return {
        "suite": SUITE_ID,
        "task_id": TASK_ID,
        "paper_sections": list(PAPER_SECTIONS),
        "registered_gates": list(REGISTERED_GATE_IDS),
        "metrics": {
            metric_id: _metric_status(cases, metric_id) for metric_id in METRIC_IDS
        },
        "metric_values": metric_values,
        "result_ledger": {
            "name": "RESULT_LEDGER",
            "columns": list(RESULT_LEDGER_COLUMNS),
            "rows": result_ledger_rows,
        },
        "summary": {
            "total": len(cases),
            "passed": passed,
            "failed": failed,
            "ok": failed == 0,
        },
        "cases": cases,
    }


def write_result_log(
    result: Mapping[str, Any],
    path: Path | str = RESULT_LOG_PATH,
) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return destination


def _ocr_metric_values() -> dict[str, float]:
    exact_page = OCR.LocalOCREngine().recognize_text(OCR_EXACT_TEXT)
    cases = (
        OCR.evaluate_ocr(OCR_EXACT_TEXT, exact_page),
        OCR.evaluate_ocr(OCR_NOISY_REFERENCE_TEXT, OCR_NOISY_HYPOTHESIS_TEXT),
    )
    return {
        "EV-OCR-CER": _round(mean(case.ev_ocr_cer for case in cases)),
        "EV-OCR-WER": _round(mean(case.ev_ocr_wer for case in cases)),
    }


def _exact_metric_values(
    predicted_terms: Sequence[SCHEMAS.ExtractedFinancialTerms],
) -> dict[str, float]:
    gold_terms = (
        EXTRACT.ExpectedFinancialTerm("GROSS_SALES", Decimal("1200000"), SCHEMAS.Unit.KRW),
        EXTRACT.ExpectedFinancialTerm(
            "REVENUE_SHARE_RATE", Decimal("0.3"), SCHEMAS.Unit.FRAC
        ),
        EXTRACT.ExpectedFinancialTerm("PAYMENT_DUE_DATE", 20260305, SCHEMAS.Unit.NONE),
        EXTRACT.ExpectedFinancialTerm("PAYMENT_DUE_DAYS", 45.0, SCHEMAS.Unit.DAYS),
    )
    report = EXTRACT.exact_match_harness(gold_terms, predicted_terms)
    return {
        metric_id: _round(metric.value)
        for metric_id, metric in report.metrics.items()
    }


def _segmentation_metric_values(
    page: SCHEMAS.OCRPage,
    predicted_clauses: Sequence[SCHEMAS.Clause],
) -> dict[str, float]:
    span_order = tuple(span.span_id for span in page.spans)
    gold_clauses = (
        tuple(span_order[:2]),
        tuple(span_order[2:]),
    )
    metrics = SEGMENT.evaluate_clause_segmentation(
        gold_clauses,
        predicted_clauses,
        span_order=span_order,
    )
    return {"EV-SEG": _round(metrics.ev_seg)}


def _result_ledger_rows(metric_values: Mapping[str, float]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for metric_id in METRIC_IDS:
        rows.append(
            {
                "result_id": f"{TASK_ID}-{metric_id}",
                "experiment_id": "ocr_extract_metric_run",
                "metric": metric_id,
                "value": f"{metric_values[metric_id]:.6f}",
                "artifact_path": ARTIFACT_PATH,
                "status": "measured",
                "reviewer": "codex",
                "notes": (
                    "synthetic/sanitized local fixture; measured value is not "
                    "a generalized performance claim"
                ),
            }
        )
    return rows


def _metric_status(cases: Sequence[Mapping[str, Any]], metric_id: str) -> dict[str, Any]:
    metric_cases = [case for case in cases if metric_id in case["metrics"]]
    passed = sum(1 for case in metric_cases if case["status"] == "PASS")
    failed = len(metric_cases) - passed
    return {
        "total": len(metric_cases),
        "passed": passed,
        "failed": failed,
        "ok": failed == 0,
    }


def _all_metrics_computed(metric_values: Mapping[str, float]) -> bool:
    return set(metric_values) == set(METRIC_IDS) and all(
        0.0 <= value <= 1.0 for value in metric_values.values()
    )


def _fixture_sha256() -> str:
    payload = "\n".join(
        (
            REFERENCE_TEXT,
            OCR_EXACT_TEXT,
            OCR_NOISY_REFERENCE_TEXT,
            OCR_NOISY_HYPOTHESIS_TEXT,
        )
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _round(value: float) -> float:
    return round(float(value), 6)


def _json_default(value: Any) -> Any:
    if hasattr(value, "__dataclass_fields__"):
        return asdict(value)
    if isinstance(value, Decimal):
        return str(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run FINK-S5-02 OCR/extraction metrics.")
    parser.add_argument(
        "--output",
        type=Path,
        default=RESULT_LOG_PATH,
        help="Path for the JSON result log.",
    )
    parser.add_argument(
        "--stdout",
        action="store_true",
        help="Also print the JSON result to stdout.",
    )
    args = parser.parse_args(argv)

    result = run_ocr_extract_metric_suite()
    log_path = write_result_log(result, args.output)
    if args.stdout:
        print(
            json.dumps(
                result,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
                default=_json_default,
            )
        )
    print(f"{SUITE_ID}: {'PASS' if result['summary']['ok'] else 'FAIL'}; log={log_path}")
    return 0 if result["summary"]["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

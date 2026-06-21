from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
if SRC_ROOT.as_posix() not in sys.path:
    sys.path.insert(0, SRC_ROOT.as_posix())

from fink import grounding as GROUNDING  # noqa: E402
from fink import retrieval as RETRIEVAL  # noqa: E402


TASK_ID = "FINK-S5-03"
SUITE_ID = "retrieval_metric_suite"
RESULT_LOG_PATH = Path(__file__).with_name("retrieval_metric_suite_results.json")
REGISTERED_GATE_IDS = ("retrieval_metric_run",)
PAPER_SECTIONS = ("05_experiments.md", "06_results.md")
METRIC_IDS = ("EV-R@3", "EV-R@5", "EV-AUTH", "EV-SPAN", "EV-KOEN")
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
ARTIFACT_PATH = "scripts/eval/retrieval_metric_suite_results.json"

SPAN_FIXTURES = (
    ("span-deduction-exact", "deduction list gross sales basis", "deduction list gross sales basis"),
    (
        "span-audit-partial",
        "monthly settlement statement audit access",
        "settlement statement audit access",
    ),
    (
        "span-termination-partial",
        "termination penalty liability cap",
        "termination penalty liability",
    ),
)


@dataclass(frozen=True)
class EvidenceSpanCase:
    case_id: str
    gold_span: str
    cited_span: str


def run_retrieval_metric_suite() -> dict[str, Any]:
    index = RETRIEVAL.LocalBM25Index(_retrieval_chunks())
    recall_metrics = RETRIEVAL.recall_harness(index, _retrieval_cases())
    authority = _authority_metric(index)
    span_metrics = _span_metric_values(_span_cases())
    koen_metrics = RETRIEVAL.koen_consistency_harness(index, _koen_pairs(), k=1)

    metric_values = {
        "EV-R@3": _round(recall_metrics.ev_r_at_3),
        "EV-R@5": _round(recall_metrics.ev_r_at_5),
        "EV-AUTH": _round(authority["EV-AUTH"]),
        "EV-SPAN": _round(span_metrics["EV-SPAN"]),
        "EV-KOEN": _round(koen_metrics.ev_koen),
    }
    gate_ok = (
        _all_metrics_computed(metric_values)
        and authority["all_checks_passed"]
        and koen_metrics.english_never_labeled_evidence
        and koen_metrics.caveat_coverage == 1.0
    )
    cases = [
        {
            "id": "retrieval_metric_run",
            "metrics": list(METRIC_IDS),
            "description": (
                "Compute retrieval recall, authority-tier correctness, cited evidence-span "
                "overlap, and KO/EN canonical-ID consistency on synthetic/sanitized fixtures."
            ),
            "status": "PASS" if gate_ok else "FAIL",
            "expected": {
                "required_metrics": list(METRIC_IDS),
                "result_ledger_status": "measured",
                "synthetic_only": True,
                "no_legal_verdict": True,
                "authority_scoring_tiers": ["A0", "A1", "A2"],
                "practice_reference_tiers_non_scoring": ["B", "C", "B/C"],
                "english_aliases_are_not_evidence": True,
            },
            "observed": {
                "metric_values": metric_values,
                "recall": _recall_observation(recall_metrics),
                "authority": authority["observed"],
                "span": span_metrics["observed"],
                "koen": _koen_observation(koen_metrics),
                "fixture_sha256": _fixture_sha256(),
            },
        }
    ]
    passed = sum(1 for case in cases if case["status"] == "PASS")
    failed = len(cases) - passed
    return {
        "suite": SUITE_ID,
        "task_id": TASK_ID,
        "paper_sections": list(PAPER_SECTIONS),
        "registered_gates": list(REGISTERED_GATE_IDS),
        "metrics": {metric_id: _metric_status(cases, metric_id) for metric_id in METRIC_IDS},
        "metric_values": metric_values,
        "result_ledger": {
            "name": "RESULT_LEDGER",
            "columns": list(RESULT_LEDGER_COLUMNS),
            "rows": _result_ledger_rows(metric_values),
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


def _retrieval_chunks() -> tuple[RETRIEVAL.RetrievalChunk, ...]:
    return (
        _chunk(
            "EV-F1-SETTLEMENT",
            "monthly settlement statement audit access 정산 정산서 감사 열람",
            risk_categories=("F1",),
        ),
        _chunk(
            "EV-F2-DEDUCTIONS",
            "revenue base deduction list gross sales 공제 매출 기준",
            risk_categories=("F2",),
        ),
        _chunk(
            "EV-F3-PAYMENT",
            "payment due delay cashflow 지급 지연 지급일",
            risk_categories=("F3",),
        ),
        _chunk(
            "EV-F7-TERMINATION",
            "termination penalty liability damages 위약금 해지 손해배상",
            risk_categories=("F7",),
        ),
        _chunk(
            "KC-F2-DEDUCTIONS",
            "deduction questions revenue base 공제 확인 practice reference",
            chunk_type="knowledge_card",
            authority_tier="B/C",
            source_id="B-BOOK",
            risk_categories=("F2",),
            score_eligible=False,
            practice_reference=True,
            generated_translation=True,
        ),
        _chunk(
            "EV-A2-DEDUCTIONS",
            "deduction revenue base official guidance 공제 매출 기준 안내",
            authority_tier="A2",
            source_id="A2-GUIDE",
            risk_categories=("F2",),
        ),
        *_glossary_chunks(),
    )


def _chunk(
    chunk_id: str,
    text: str,
    *,
    chunk_type: str = "evidence",
    authority_tier: str = "A1",
    source_id: str | None = None,
    risk_categories: tuple[str, ...] = ("F1",),
    score_eligible: bool = True,
    practice_reference: bool = False,
    generated_translation: bool = False,
    canonical_id: str = "",
    non_equivalence_caveat: str = "",
) -> RETRIEVAL.RetrievalChunk:
    resolved_source_id = source_id or f"{authority_tier}-SYNTH"
    return RETRIEVAL.RetrievalChunk(
        chunk_id=chunk_id,
        chunk_type=chunk_type,
        text=text,
        title=chunk_id,
        source_id=resolved_source_id,
        source_ids=(resolved_source_id,),
        source_class=authority_tier,
        authority_tier=authority_tier,
        verification_status="UNVERIFIED",
        risk_categories=risk_categories,
        canonical_id=canonical_id,
        non_equivalence_caveat=non_equivalence_caveat,
        hierarchy=(
            f"tier:{authority_tier}",
            f"source:{resolved_source_id}",
            f"risk:{'|'.join(risk_categories)}",
            f"chunk:{chunk_id}",
        ),
        score_eligible=score_eligible,
        practice_reference=practice_reference,
        public_export=False,
        generated_translation=generated_translation,
    )


def _glossary_chunks() -> tuple[RETRIEVAL.RetrievalChunk, ...]:
    caveat = (
        "Generated English alias for retrieval only; Korean source term remains canonical "
        "and no legal equivalence is asserted."
    )
    rows = (
        (
            "CANON_ASSIGNMENT_LICENSE_BOUNDARY",
            "저작권 양도와 이용허락",
            "assignment license boundary",
            "양도 이용허락 assignment license",
        ),
        ("CANON_RESCISSION", "해제", "rescission", "계약 해제 rescission"),
        ("CANON_TERMINATION", "해지", "termination", "계약 해지 termination"),
        (
            "CANON_WORK_MADE_FOR_HIRE",
            "업무상저작물",
            "work made for hire",
            "업무상 저작물 work-made-for-hire",
        ),
        (
            "CANON_PUBLICITY",
            "초상 등 영리 이용",
            "publicity",
            "초상 영리 이용 publicity image likeness",
        ),
        (
            "CANON_LIQUIDATED_DAMAGES",
            "손해배상액 예정",
            "liquidated damages",
            "손해배상액 예정 liquidated damages",
        ),
        ("CANON_CONSIDERATION", "대가", "consideration", "계약 대가 consideration"),
        ("CANON_DEPOSIT", "계약금", "deposit", "계약금 보증금 deposit"),
    )
    return tuple(
        _chunk(
            f"GL-{canonical_id}",
            f"{canonical_id} {preferred_ko} {preferred_en} {aliases}",
            chunk_type="glossary_term",
            authority_tier="B/C",
            source_id="B-BOOK",
            risk_categories=("F5",),
            score_eligible=False,
            practice_reference=True,
            generated_translation=True,
            canonical_id=canonical_id,
            non_equivalence_caveat=caveat,
        )
        for canonical_id, preferred_ko, preferred_en, aliases in rows
    )


def _retrieval_cases() -> tuple[RETRIEVAL.RetrievalCase, ...]:
    return (
        RETRIEVAL.RetrievalCase(
            query_id="q-f1-settlement",
            query="settlement statement audit access 정산서 열람",
            relevant_chunk_ids=("EV-F1-SETTLEMENT",),
            risk_categories=("F1",),
            chunk_types=("evidence",),
            authority_tiers=("A0", "A1", "A2"),
        ),
        RETRIEVAL.RetrievalCase(
            query_id="q-f2-deduction",
            query="deduction list revenue base 공제 매출 기준",
            relevant_chunk_ids=("EV-F2-DEDUCTIONS",),
            risk_categories=("F2",),
            chunk_types=("evidence",),
            authority_tiers=("A0", "A1", "A2"),
        ),
        RETRIEVAL.RetrievalCase(
            query_id="q-f3-payment",
            query="payment due delay cashflow 지급 지연",
            relevant_chunk_ids=("EV-F3-PAYMENT",),
            risk_categories=("F3",),
            chunk_types=("evidence",),
            authority_tiers=("A0", "A1", "A2"),
        ),
        RETRIEVAL.RetrievalCase(
            query_id="q-f7-termination",
            query="termination penalty liability damages 위약금",
            relevant_chunk_ids=("EV-F7-TERMINATION",),
            risk_categories=("F7",),
            chunk_types=("evidence",),
            authority_tiers=("A0", "A1", "A2"),
        ),
    )


def _koen_pairs() -> tuple[RETRIEVAL.BilingualQueryPair, ...]:
    return (
        _pair("assignment-license", "저작권 양도와 이용허락", "assignment license boundary"),
        _pair("rescission", "해제", "rescission"),
        _pair("termination", "해지", "termination"),
        _pair("work-made-for-hire", "업무상저작물", "work made for hire"),
        _pair("publicity", "초상 등 영리 이용", "publicity"),
        _pair("liquidated-damages", "손해배상액 예정", "liquidated damages"),
        _pair("consideration", "대가", "consideration"),
        _pair("deposit", "계약금", "deposit"),
    )


def _pair(
    slug: str,
    query_ko: str,
    query_en: str,
) -> RETRIEVAL.BilingualQueryPair:
    canonical_id = {
        "assignment-license": "CANON_ASSIGNMENT_LICENSE_BOUNDARY",
        "rescission": "CANON_RESCISSION",
        "termination": "CANON_TERMINATION",
        "work-made-for-hire": "CANON_WORK_MADE_FOR_HIRE",
        "publicity": "CANON_PUBLICITY",
        "liquidated-damages": "CANON_LIQUIDATED_DAMAGES",
        "consideration": "CANON_CONSIDERATION",
        "deposit": "CANON_DEPOSIT",
    }[slug]
    return RETRIEVAL.BilingualQueryPair(
        query_id=f"koen-{slug}",
        query_ko=query_ko,
        query_en=query_en,
        expected_canonical_id=canonical_id,
        requires_non_equivalence_caveat=True,
    )


def _authority_metric(index: RETRIEVAL.LocalBM25Index) -> dict[str, Any]:
    errors: dict[str, str] = {}
    bundle = GROUNDING.authority_gated_retrieval(
        index,
        "deduction revenue base 공제",
        explanation_k=1,
        grounding_k=2,
        risk_categories=("F2",),
    )
    checks = {
        "authority_tag_present": _safe_check(
            lambda: GROUNDING.authority_tag_present(bundle),
            errors,
            "authority_tag_present",
        ),
        "grounding_records_a0_a2": all(
            record.authority_tier in {"A0", "A1", "A2"} and record.score_eligible
            for record in bundle.grounding_records
        ),
        "practice_records_bc_non_scoring": all(
            record.authority_tier in {"B", "C", "B/C"}
            and record.practice_reference
            and not record.score_eligible
            for record in bundle.explanation_records
        ),
        "returned_records_have_provenance": all(
            record.source_id and record.authority_tier and record.verification_status
            for record in bundle.returned_records
        ),
    }

    bc_only = GROUNDING.evaluate_signal_eligibility(
        "SIG-F2-BC-ONLY",
        (
            _authority_record(
                "KC-B-DEDUCTIONS",
                record_type="knowledge_card",
                authority_tier="B/C",
                score_eligible=False,
                practice_reference=True,
            ),
        ),
        risk_categories=("F2",),
        raw_contribution=25.0,
    )
    a_grounded = GROUNDING.evaluate_signal_eligibility(
        "SIG-F2-A1-GROUNDED",
        (_authority_record("EV-A1-DEDUCTIONS", authority_tier="A1"),),
        risk_categories=("F2_REVENUE_AND_DEDUCTIONS",),
        raw_contribution=25.0,
    )
    x_context = GROUNDING.evaluate_signal_eligibility(
        "SIG-X1-A1-CONTEXT",
        (
            _authority_record(
                "EV-A1-X1-CONTEXT",
                authority_tier="A1",
                risk_categories=("X1",),
            ),
        ),
        risk_categories=("X1_EVIDENCE_AND_CURRENCY_GOVERNANCE",),
        raw_contribution=40.0,
    )
    checks.update(
        {
            "eligibility_gate_mixed_cases": _safe_check(
                lambda: GROUNDING.eligibility_gate_test((bc_only, a_grounded)),
                errors,
                "eligibility_gate_mixed_cases",
            ),
            "bc_only_zero_contribution": (
                not bc_only.score_eligible
                and bc_only.practice_reference
                and bc_only.score_contribution == 0.0
            ),
            "a1_grounded_score_eligible": (
                a_grounded.score_eligible
                and not a_grounded.practice_reference
                and a_grounded.score_contribution == 25.0
            ),
            "x_category_non_scoring": (
                not x_context.score_eligible and x_context.score_contribution == 0.0
            ),
        }
    )
    passed = sum(1 for passed_check in checks.values() if passed_check)
    total = len(checks)
    return {
        "EV-AUTH": passed / total,
        "all_checks_passed": passed == total,
        "observed": {
            "total_checks": total,
            "passed_checks": passed,
            "checks": checks,
            "errors": errors,
            "grounding_record_ids": [record.record_id for record in bundle.grounding_records],
            "explanation_record_ids": [
                record.record_id for record in bundle.explanation_records
            ],
            "eligibility": {
                "bc_only": bc_only.as_dict(),
                "a1_grounded": a_grounded.as_dict(),
                "x_context": x_context.as_dict(),
            },
        },
    }


def _authority_record(
    record_id: str,
    *,
    record_type: str = "evidence",
    authority_tier: str = "A1",
    risk_categories: tuple[str, ...] = ("F2",),
    score_eligible: bool = True,
    practice_reference: bool = False,
) -> GROUNDING.AuthorityRetrievedRecord:
    return GROUNDING.AuthorityRetrievedRecord(
        rank=1,
        retrieval_score=1.0,
        record_id=record_id,
        record_type=record_type,
        title=record_id,
        text="synthetic grounding fixture",
        source_id=f"{authority_tier}-SYNTH",
        source_ids=(f"{authority_tier}-SYNTH",),
        authority_tier=authority_tier,
        verification_status="UNVERIFIED",
        risk_categories=risk_categories,
        score_eligible=score_eligible,
        practice_reference=practice_reference,
        matched_terms=("synthetic",),
    )


def _span_cases() -> tuple[EvidenceSpanCase, ...]:
    return tuple(EvidenceSpanCase(*fixture) for fixture in SPAN_FIXTURES)


def _span_metric_values(cases: Sequence[EvidenceSpanCase]) -> dict[str, Any]:
    observed_cases = []
    values = []
    for case in cases:
        gold_tokens = set(RETRIEVAL.tokenize(case.gold_span))
        cited_tokens = set(RETRIEVAL.tokenize(case.cited_span))
        union = gold_tokens | cited_tokens
        overlap = (len(gold_tokens & cited_tokens) / len(union)) if union else 0.0
        values.append(overlap)
        observed_cases.append(
            {
                "case_id": case.case_id,
                "gold_token_count": len(gold_tokens),
                "cited_token_count": len(cited_tokens),
                "intersection_token_count": len(gold_tokens & cited_tokens),
                "union_token_count": len(union),
                "token_iou": _round(overlap),
                "gold_span_sha256": _sha256_text(case.gold_span),
                "cited_span_sha256": _sha256_text(case.cited_span),
            }
        )
    return {
        "EV-SPAN": mean(values),
        "observed": {
            "case_count": len(cases),
            "aggregation": "mean token-set IoU",
            "cases": observed_cases,
        },
    }


def _recall_observation(metrics: RETRIEVAL.RetrievalRecallMetrics) -> dict[str, Any]:
    payload = metrics.as_dict()
    return {
        "total_cases": payload["total_cases"],
        "hits_at_k": payload["hits_at_k"],
        "recall_at_k": payload["recall_at_k"],
        "per_query": payload["per_query"],
    }


def _koen_observation(metrics: RETRIEVAL.BilingualConsistencyMetrics) -> dict[str, Any]:
    return {
        "total_pairs": metrics.total_pairs,
        "consistent_pairs": metrics.consistent_pairs,
        "top_k_consistent_pairs": metrics.top_k_consistent_pairs,
        "caveat_required_pairs": metrics.caveat_required_pairs,
        "caveat_present_pairs": metrics.caveat_present_pairs,
        "english_never_labeled_evidence": metrics.english_never_labeled_evidence,
        "english_labeled_evidence_violations": metrics.english_labeled_evidence_violations,
        "per_query": [
            {
                "query_id": row["query_id"],
                "expected_canonical_id": row["expected_canonical_id"],
                "ko_canonical_ids": row["ko_canonical_ids"],
                "en_canonical_ids": row["en_canonical_ids"],
                "same_top1": row["same_top1"],
                "same_top_k": row["same_top_k"],
                "consistent": row["consistent"],
                "requires_non_equivalence_caveat": row[
                    "requires_non_equivalence_caveat"
                ],
                "non_equivalence_caveat_present": row[
                    "non_equivalence_caveat_present"
                ],
                "english_labeled_evidence": row["english_labeled_evidence"],
            }
            for row in metrics.per_query
        ],
    }


def _safe_check(
    fn: Any,
    errors: dict[str, str],
    check_id: str,
) -> bool:
    try:
        return bool(fn())
    except Exception as exc:  # pragma: no cover - only exercised on gate failure.
        errors[check_id] = f"{type(exc).__name__}: {exc}"
        return False


def _result_ledger_rows(metric_values: Mapping[str, float]) -> list[dict[str, str]]:
    return [
        {
            "result_id": f"{TASK_ID}-{metric_id}",
            "experiment_id": "retrieval_metric_run",
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
        for metric_id in METRIC_IDS
    ]


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
            *(chunk.text for chunk in _retrieval_chunks()),
            *(
                f"{case.case_id}\t{case.gold_span}\t{case.cited_span}"
                for case in _span_cases()
            ),
            *(
                f"{pair.query_id}\t{pair.query_ko}\t{pair.query_en}\t"
                f"{pair.expected_canonical_id}"
                for pair in _koen_pairs()
            ),
        )
    )
    return _sha256_text(payload)


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _round(value: float | None) -> float:
    if value is None:
        return 0.0
    return round(float(value), 6)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run FINK-S5-03 retrieval metrics.")
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
    parser.add_argument(
        "--write-result",
        action="store_true",
        help="Write the suite result JSON log.",
    )
    args = parser.parse_args(argv)

    result = run_retrieval_metric_suite()
    if args.write_result:
        write_result_log(result, args.output)
    if args.stdout or not args.write_result:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["summary"]["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

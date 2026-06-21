from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
if SRC_ROOT.as_posix() not in sys.path:
    sys.path.insert(0, SRC_ROOT.as_posix())

from fink import schemas as SCHEMAS  # noqa: E402


TASK_ID = "FINK-S5-01"
SUITE_ID = "synthetic_dataset_suite"
DATA_ROOT = REPO_ROOT / "data" / "eval"
RESULT_LOG_PATH = Path(__file__).with_name("synthetic_dataset_suite_results.json")
FROZEN_MANIFEST_PATH = DATA_ROOT / "frozen_eval_manifest.json"
REQUIRED_DATASET_REFS = ("DR-6", "DR-7", "DR-8", "DR-11", "DR-12", "DR-13")
REGISTERED_GATE_IDS = ("synthetic_only_test", "frozen_split_hash_test")
ACCEPTANCE_IDS = ("AC-EV-SYNTH", "AC-EV-FROZEN")
FIXED_CREATED_UTC = "2026-06-21T00:00:00Z"
SYNTHETIC_GENERATION_METHOD = (
    "Newly authored synthetic fixture for FINK-S5-01; not copied from any contract, "
    "private corpus, PDF, ZIP, model output, or user upload."
)


def build_examples() -> tuple[SCHEMAS.EvaluationExample, ...]:
    return (
        *_dr6_clause_pair_examples(),
        *_dr7_ocr_stress_examples(),
        *_dr8_bilingual_query_examples(),
        *_dr11_decision_utility_examples(),
        *_dr12_privacy_probe_examples(),
        *_dr13_latency_fixture_examples(),
    )


def write_dataset(data_root: Path | str = DATA_ROOT) -> Path:
    root = Path(data_root)
    examples = build_examples()
    by_split_dataset: dict[tuple[str, str], list[SCHEMAS.EvaluationExample]] = defaultdict(list)
    for example in examples:
        by_split_dataset[(example.split.value, example.dataset_ref)].append(example)

    for split in ("dev", "frozen_eval"):
        split_dir = root / split
        split_dir.mkdir(parents=True, exist_ok=True)
        for dataset_ref in REQUIRED_DATASET_REFS:
            records = sorted(
                by_split_dataset[(split, dataset_ref)],
                key=lambda item: item.example_id,
            )
            _write_jsonl(split_dir / f"{dataset_ref}.jsonl", records)

    manifest_path = root / "frozen_eval_manifest.json"
    manifest = _build_frozen_manifest(root)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        _canonical_json(manifest, pretty=True) + "\n",
        encoding="utf-8",
    )
    return root


def load_dataset_examples(data_root: Path | str = DATA_ROOT) -> tuple[SCHEMAS.EvaluationExample, ...]:
    root = Path(data_root)
    examples: list[SCHEMAS.EvaluationExample] = []
    for split in ("dev", "frozen_eval"):
        for dataset_ref in REQUIRED_DATASET_REFS:
            path = root / split / f"{dataset_ref}.jsonl"
            for row in _read_jsonl(path):
                examples.append(SCHEMAS.EvaluationExample(**row))
    return tuple(examples)


def run_synthetic_dataset_suite(data_root: Path | str = DATA_ROOT) -> dict[str, Any]:
    root = Path(data_root)
    cases = (
        _synthetic_only_case(root),
        _frozen_split_hash_case(root),
    )
    passed = sum(1 for case in cases if case["status"] == "PASS")
    failed = len(cases) - passed
    return {
        "suite": SUITE_ID,
        "task_id": TASK_ID,
        "acceptance_ids": list(ACCEPTANCE_IDS),
        "registered_gates": list(REGISTERED_GATE_IDS),
        "paper_sections_blocked_by_allowed_paths": [
            "04_data_and_implementation.md",
            "05_experiments.md",
        ],
        "summary": {
            "total": len(cases),
            "passed": passed,
            "failed": failed,
            "ok": failed == 0,
        },
        "cases": list(cases),
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


def _dr6_clause_pair_examples() -> tuple[SCHEMAS.EvaluationExample, ...]:
    category_specs = (
        (
            "F1",
            "F1_SETTLEMENT_AND_AUDIT",
            "FIM-1",
            "정산 근거 자료와 열람 절차가 빠져 있다",
            "월별 정산명세서와 근거 자료 열람 절차를 제공한다",
            "settlement support records and audit access are missing",
            "monthly settlement statements and support-record access are provided",
            0.72,
            ({"feature_id": "SETTLEMENT_REPORT", "expected": "missing"},),
        ),
        (
            "F2",
            "F2_REVENUE_AND_DEDUCTIONS",
            "FIM-1",
            "공제 항목을 회사가 사후에 추가할 수 있다",
            "공제 항목을 별첨 목록으로 제한한다",
            "deduction items can be added later by the company",
            "deduction items are limited to an attached list",
            0.78,
            ({"feature_id": "DEDUCTION_ITEMS", "expected": "open_ended"},),
        ),
        (
            "F3",
            "F3_PAYMENT_AND_CASHFLOW",
            "FIM-2",
            "지급일이 판매월 종료 후 90일로 늦다",
            "지급일을 판매월 종료 후 30일로 둔다",
            "payment is delayed until 90 days after the sales month",
            "payment is due 30 days after the sales month",
            0.62,
            ({"feature_id": "PAYMENT_DUE_DAYS", "value": 90, "unit": "days"},),
        ),
        (
            "F4",
            "F4_MG_AND_RECOUPMENT",
            "FIM-3",
            "선급금 회수 범위가 모든 수익으로 넓다",
            "선급금 회수 범위를 해당 작품 순매출로 제한한다",
            "advance recoupment reaches all revenue streams",
            "advance recoupment is limited to net sales from the covered work",
            0.69,
            ({"feature_id": "ADVANCE_RECOUPMENT", "expected": "broad_scope"},),
        ),
        (
            "F5",
            "F5_IP_MONETIZATION",
            "FIM-6",
            "2차적저작물 수익 배분율이 정해져 있지 않다",
            "2차적저작물 수익 배분율과 승인 절차를 명시한다",
            "secondary-rights revenue sharing is not specified",
            "secondary-rights revenue share and approval flow are specified",
            0.81,
            ({"feature_id": "SECONDARY_RIGHTS_REVENUE_SHARE", "expected": "missing"},),
        ),
        (
            "F6",
            "F6_TERM_EXCLUSIVITY_AND_OPPORTUNITY_COST",
            "FIM-5",
            "독점 기간이 종료 후 24개월까지 이어진다",
            "독점 기간은 연재 기간으로 제한된다",
            "exclusivity continues for 24 months after the run ends",
            "exclusivity is limited to the publication period",
            0.66,
            ({"feature_id": "EXCLUSIVITY_DURATION_MONTHS", "value": 24, "unit": "months"},),
        ),
        (
            "F7",
            "F7_TERMINATION_LIABILITY_AND_PENALTIES",
            "FIM-7",
            "중도 해지 시 정액 위약금 5,000,000원이 부과된다",
            "중도 해지 비용은 실제 정산 잔액을 한도로 한다",
            "early termination triggers a fixed KRW 5,000,000 penalty",
            "early termination cost is capped by the actual settlement balance",
            0.84,
            ({"feature_id": "PENALTY_AMOUNT", "value": 5000000, "unit": "KRW"},),
        ),
        (
            "F8",
            "F8_SCOPE_CREEP_AND_PRODUCTION_COST",
            "FIM-4",
            "추가 수정 작업을 무상으로 요구할 수 있다",
            "추가 수정 작업은 회차별 단가와 별도 합의가 필요하다",
            "additional revisions can be required without extra pay",
            "additional revisions require a per-unit fee and separate agreement",
            0.58,
            ({"feature_id": "UNPAID_REVISION_UNITS", "expected": "open_ended"},),
        ),
        (
            "F9",
            "F9_E_CONTRACT_PRIVACY_AND_EVIDENCE",
            "FIM-8",
            "전자서명 원본과 변경 이력 보존 방법이 없다",
            "전자서명 원본과 변경 이력 보존 방법을 명시한다",
            "e-signature originals and change-history retention are omitted",
            "e-signature originals and change-history retention are specified",
            0.53,
            ({"feature_id": "E_CONTRACT_EVIDENCE_RETENTION", "expected": "missing"},),
        ),
    )

    examples: list[SCHEMAS.EvaluationExample] = []
    for index, spec in enumerate(category_specs, start=1):
        (
            category,
            canonical_id,
            fim_module,
            risky_ko,
            protective_ko,
            risky_en,
            protective_en,
            severity,
            numeric_fields,
        ) = spec
        for split in ("dev", "frozen_eval"):
            phrase = "기본" if split == "dev" else "고정"
            group_id = f"DR6-{split}-{category}-{phrase}"
            variants = (
                ("risky", risky_ko, risky_en, False, severity, "missing_protection"),
                ("protective", protective_ko, protective_en, True, 0.0, "protective"),
            )
            for variant, text_ko, text_en, is_benign, expected_severity, completeness in variants:
                example_id = f"DR6-{split}-{category}-{variant}"
                clause_text_ko = (
                    f"합성 {phrase} {index}번 조항: {text_ko}. "
                    "금액 산정은 예시 입력값으로만 평가한다."
                )
                clause_text_en = (
                    f"Synthetic {phrase} clause {index}: {text_en}. "
                    "Amounts are evaluated only as synthetic assumptions."
                )
                examples.append(
                    _example(
                        example_id=example_id,
                        split=split,
                        dataset_ref="DR-6",
                        input_kind="clause_pair",
                        is_benign=is_benign,
                        gold={
                            **_base_gold("DR-6", split),
                            "group_id": group_id,
                            "pair_role": variant,
                            "question": f"{category} contractual financial review-priority signal",
                            "expected_risk_category": category,
                            "expected_canonical_id": canonical_id,
                            "expected_fim_module": fim_module,
                            "expected_severity": expected_severity,
                            "score_eligible_expected": not is_benign,
                            "practice_reference_expected": False,
                            "expected_authority_tier": "A1",
                            "official_source": {
                                "source_id": f"SYNTH-A1-{category}",
                                "authority_tier": "A1",
                                "verification_status": "UNVERIFIED",
                                "synthetic_proxy": True,
                            },
                            "evidence_span": {
                                "text_ko": text_ko,
                                "start_token": 4,
                                "end_token": 12,
                            },
                            "completeness_label": completeness,
                            "numeric_fields": list(numeric_fields),
                            "unanswerable_flag": False,
                            "ambiguity_notes": (
                                "Synthetic wording tests review-priority routing, "
                                "not legal validity or guaranteed loss."
                            ),
                            "language": "ko",
                            "contract_type": "synthetic_creator_contract",
                            "clause_text_ko": clause_text_ko,
                            "clause_text_en_alias": clause_text_en,
                            "generated_translation": True,
                        },
                    )
                )
    return tuple(examples)


def _dr7_ocr_stress_examples() -> tuple[SCHEMAS.EvaluationExample, ...]:
    fixtures = (
        (
            "dev",
            "ko-rotation",
            "ko",
            "rotation_90",
            "합성 OCR 페이지: 지급 금액 1,200,000원, 배분율 35%, 지급일 2026-07-31, 기간 12개월.",
            {"money": ["1200000 KRW"], "percentage": ["35%"], "date": ["2026-07-31"], "duration": ["12 months"]},
        ),
        (
            "dev",
            "en-blur",
            "en",
            "mild_blur",
            "Synthetic OCR page: payment KRW 900,000, share 25%, due 2026-08-15, term 6 months.",
            {"money": ["900000 KRW"], "percentage": ["25%"], "date": ["2026-08-15"], "duration": ["6 months"]},
        ),
        (
            "frozen_eval",
            "ko-low-light",
            "ko",
            "low_light",
            "합성 고정 OCR 페이지: 선급금 3,000,000원, 회수율 40%, 지급일 2026-09-10, 기간 18개월.",
            {"money": ["3000000 KRW"], "percentage": ["40%"], "date": ["2026-09-10"], "duration": ["18 months"]},
        ),
        (
            "frozen_eval",
            "en-screen",
            "en",
            "screen_capture",
            "Frozen synthetic OCR page: fee KRW 450,000, share 18%, due 2026-10-05, term 3 months.",
            {"money": ["450000 KRW"], "percentage": ["18%"], "date": ["2026-10-05"], "duration": ["3 months"]},
        ),
    )
    return tuple(
        _example(
            example_id=f"DR7-{split}-{name}",
            split=split,
            dataset_ref="DR-7",
            input_kind="camera_ocr",
            is_benign=False,
            gold={
                **_base_gold("DR-7", split),
                "group_id": f"DR7-{split}-{name}",
                "language": language,
                "ocr_perturbation": perturbation,
                "gold_text": text,
                "known_financial_values": values,
                "page_order_index": 0,
                "expected_text_source": "ocr",
                "score_stability_repeated_runs": 3,
            },
        )
        for split, name, language, perturbation, text, values in fixtures
    )


def _dr8_bilingual_query_examples() -> tuple[SCHEMAS.EvaluationExample, ...]:
    query_pairs = (
        ("dev", "assignment-license", "양도와 이용허락", "assignment and license", "GLOSS_ASSIGNMENT_LICENSE", True),
        ("dev", "termination-cancel", "해제와 해지", "rescission and termination", "GLOSS_TERMINATION_CANCEL", True),
        ("dev", "work-made-for-hire", "업무상저작물", "work made for hire", "GLOSS_WORK_MADE_FOR_HIRE", True),
        ("dev", "publicity", "초상 등 인격표지", "publicity rights", "GLOSS_PUBLICITY", True),
        ("frozen_eval", "liquidated-damages", "위약금", "liquidated damages", "GLOSS_LIQUIDATED_DAMAGES", True),
        ("frozen_eval", "consideration", "대가", "consideration", "GLOSS_CONSIDERATION", True),
        ("frozen_eval", "deposit", "보증금", "deposit", "GLOSS_DEPOSIT", True),
        ("frozen_eval", "audit-access", "정산자료 열람", "audit access", "GLOSS_AUDIT_ACCESS", False),
    )
    return tuple(
        _example(
            example_id=f"DR8-{split}-{slug}",
            split=split,
            dataset_ref="DR-8",
            input_kind="query",
            is_benign=True,
            gold={
                **_base_gold("DR-8", split),
                "group_id": f"DR8-{canonical_id}",
                "ko_query": ko_query,
                "en_query": en_query,
                "canonical_id": canonical_id,
                "expected_top_k_canonical_ids": [canonical_id],
                "non_equivalence_caveat": non_equivalence_caveat,
                "english_is_evidence": False,
                "generated_translation": True,
            },
        )
        for split, slug, ko_query, en_query, canonical_id, non_equivalence_caveat in query_pairs
    )


def _dr11_decision_utility_examples() -> tuple[SCHEMAS.EvaluationExample, ...]:
    fixtures = (
        ("dev", "deduction-leakage", "F2", "FIM-1", True, 1, "nominal_leakage", 200000, 500000, 900000),
        ("dev", "payment-delay", "F3", "FIM-2", True, 2, "present_value_loss", 30000, 90000, 160000),
        ("dev", "style-guide-note", "X3", "FIM-8", False, 6, "none", 0, 0, 0),
        ("frozen_eval", "secondary-rights", "F5", "FIM-6", True, 1, "opportunity_cost", 300000, 800000, 1500000),
        ("frozen_eval", "termination-penalty", "F7", "FIM-7", True, 2, "liability_exposure", 500000, 1200000, 2500000),
        ("frozen_eval", "formatting-notice", "X1", "FIM-8", False, 6, "none", 0, 0, 0),
    )
    return tuple(
        _example(
            example_id=f"DR11-{split}-{slug}",
            split=split,
            dataset_ref="DR-11",
            input_kind="clause_pair",
            is_benign=not consequential,
            gold={
                **_base_gold("DR-11", split),
                "group_id": f"DR11-{split}-{slug}",
                "expected_risk_category": category,
                "expected_fim_module": module,
                "financially_consequential": consequential,
                "financial_impact_rank": rank,
                "decision_attention_budget_k": 3,
                "exposure_type": exposure_type,
                "exposure_range_krw": {
                    "low": low,
                    "base": base,
                    "high": high,
                    "inputs_are_synthetic": True,
                    "label": "synthetic assumption",
                },
                "decision_metric_targets": ["EV-DFU", "financial-impact-NDCG"],
            },
        )
        for split, slug, category, module, consequential, rank, exposure_type, low, base, high in fixtures
    )


def _dr12_privacy_probe_examples() -> tuple[SCHEMAS.EvaluationExample, ...]:
    fixtures = (
        ("dev", "delete-original", "source_upload", ("SYNTHETIC_PRIVATE_NAME_A", "SYNTHETIC_UPLOAD_PATH_A")),
        ("dev", "redact-log", "access_log", ("SYNTHETIC_PRIVATE_ACCOUNT_A", "SYNTHETIC_OCR_TEXT_A")),
        ("frozen_eval", "interrupt-after-ocr", "failure_injection", ("SYNTHETIC_PRIVATE_NAME_B", "SYNTHETIC_UPLOAD_PATH_B")),
        ("frozen_eval", "block-network", "network_guard", ("SYNTHETIC_PRIVATE_ACCOUNT_B", "SYNTHETIC_OCR_TEXT_B")),
    )
    return tuple(
        _example(
            example_id=f"DR12-{split}-{slug}",
            split=split,
            dataset_ref="DR-12",
            input_kind="paste",
            is_benign=True,
            gold={
                **_base_gold("DR-12", split),
                "group_id": f"DR12-{split}-{slug}",
                "probe_type": probe_type,
                "synthetic_private_markers": list(markers),
                "expected_absent_from_logs": list(markers),
                "expected_deleted_artifacts": ["original", "ocr_intermediate", "embedding_cache"],
                "expected_network_attempts": 0,
                "failure_injection": slug if "interrupt" in slug else None,
                "privacy_metric_targets": ["EV-PRIV", "EV-OFFLINE"],
            },
        )
        for split, slug, probe_type, markers in fixtures
    )


def _dr13_latency_fixture_examples() -> tuple[SCHEMAS.EvaluationExample, ...]:
    fixtures = (
        ("dev", "paste-short", "paste", "paste", 480),
        ("dev", "camera-single", "camera_ocr", "camera", 1280),
        ("frozen_eval", "pdf-two-page", "camera_ocr", "pdf", 2048),
        ("frozen_eval", "image-long", "camera_ocr", "image", 1536),
    )
    return tuple(
        _example(
            example_id=f"DR13-{split}-{slug}",
            split=split,
            dataset_ref="DR-13",
            input_kind=input_kind,
            is_benign=True,
            gold={
                **_base_gold("DR-13", split),
                "group_id": f"DR13-{split}-{slug}",
                "input_mode": input_mode,
                "payload_profile": {
                    "synthetic_character_count": char_count,
                    "synthetic_page_count": 2 if input_mode == "pdf" else 1,
                },
                "measurements_required": ["latency_seconds", "peak_memory_bytes"],
                "stage_names": ["ingest", "ocr_or_text", "segment", "score", "render"],
                "no_latency_sla_claimed": True,
            },
        )
        for split, slug, input_kind, input_mode, char_count in fixtures
    )


def _example(
    *,
    example_id: str,
    split: str,
    dataset_ref: str,
    input_kind: str,
    is_benign: bool,
    gold: dict[str, Any],
) -> SCHEMAS.EvaluationExample:
    return SCHEMAS.EvaluationExample(
        example_id=example_id,
        split=split,
        dataset_ref=dataset_ref,
        input_kind=input_kind,
        is_synthetic=True,
        is_benign=is_benign,
        gold=gold,
        public_export=True,
    )


def _base_gold(dataset_ref: str, split: str) -> dict[str, Any]:
    return {
        "dataset_ref": dataset_ref,
        "split": split,
        "synthetic_declared": True,
        "no_real_contract_data": True,
        "generation_method": SYNTHETIC_GENERATION_METHOD,
        "output_frame": "contractual_financial_review_priority",
        "not_a_legal_verdict": True,
    }


def _synthetic_only_case(root: Path) -> dict[str, Any]:
    examples = load_dataset_examples(root)
    issues = _synthetic_issues(examples)
    dataset_counts = Counter(example.dataset_ref for example in examples)
    split_counts = Counter(example.split.value for example in examples)
    observed = {
        "total_examples": len(examples),
        "dataset_counts": dict(sorted(dataset_counts.items())),
        "split_counts": dict(sorted(split_counts.items())),
        "issue_count": len(issues),
        "issues": issues,
    }
    return {
        "id": "synthetic_only_test",
        "acceptance_ids": ["AC-EV-SYNTH"],
        "status": "PASS" if not issues else "FAIL",
        "expected": {
            "required_dataset_refs": list(REQUIRED_DATASET_REFS),
            "all_is_synthetic": True,
            "all_gold_declares_synthetic": True,
            "all_public_export": True,
        },
        "observed": observed,
    }


def _frozen_split_hash_case(root: Path) -> dict[str, Any]:
    examples = load_dataset_examples(root)
    manifest_path = root / "frozen_eval_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected_manifest = _build_frozen_manifest(root)
    issues: list[str] = []

    if manifest != expected_manifest:
        issues.append("frozen manifest does not match recomputed hashes")
    if manifest.get("frozen_split_locked") is not True:
        issues.append("frozen manifest must set frozen_split_locked=true")

    by_split = defaultdict(list)
    for example in examples:
        by_split[example.split.value].append(example)
    dev_ids = {example.example_id for example in by_split["dev"]}
    frozen_ids = {example.example_id for example in by_split["frozen_eval"]}
    if dev_ids & frozen_ids:
        issues.append("dev and frozen_eval share example_id values")

    dev_groups = _group_ids(by_split["dev"])
    frozen_groups = _group_ids(by_split["frozen_eval"])
    overlap = sorted(dev_groups & frozen_groups)
    if overlap:
        issues.append(f"dev and frozen_eval share group_id values: {overlap}")

    for dataset_ref in REQUIRED_DATASET_REFS:
        for split in ("dev", "frozen_eval"):
            if not (root / split / f"{dataset_ref}.jsonl").exists():
                issues.append(f"missing {split}/{dataset_ref}.jsonl")
            split_dataset_count = sum(
                1 for example in by_split[split] if example.dataset_ref == dataset_ref
            )
            if split_dataset_count == 0:
                issues.append(f"{split}/{dataset_ref} has no records")

    frozen_file_hashes = {
        item["dataset_ref"]: item["sha256"] for item in manifest.get("files", [])
    }
    return {
        "id": "frozen_split_hash_test",
        "acceptance_ids": ["AC-EV-FROZEN"],
        "status": "PASS" if not issues else "FAIL",
        "expected": {
            "frozen_split_locked": True,
            "dev_and_frozen_example_ids_disjoint": True,
            "dev_and_frozen_group_ids_disjoint": True,
            "manifest_matches_recomputed_hashes": True,
            "required_dataset_refs": list(REQUIRED_DATASET_REFS),
        },
        "observed": {
            "manifest_path": _display_path(manifest_path),
            "combined_sha256": manifest.get("combined_sha256"),
            "frozen_file_hashes": frozen_file_hashes,
            "issue_count": len(issues),
            "issues": issues,
        },
    }


def _synthetic_issues(examples: Sequence[SCHEMAS.EvaluationExample]) -> list[str]:
    issues: list[str] = []
    seen_ids: set[str] = set()
    dataset_refs = {example.dataset_ref for example in examples}
    if dataset_refs != set(REQUIRED_DATASET_REFS):
        issues.append(f"dataset refs mismatch: {sorted(dataset_refs)}")

    for example in examples:
        if example.example_id in seen_ids:
            issues.append(f"duplicate example_id: {example.example_id}")
        seen_ids.add(example.example_id)
        if not example.is_synthetic:
            issues.append(f"{example.example_id} is_synthetic is false")
        if not example.public_export:
            issues.append(f"{example.example_id} public_export is false")
        if example.dataset_ref not in REQUIRED_DATASET_REFS:
            issues.append(f"{example.example_id} has unexpected dataset_ref {example.dataset_ref}")
        if example.gold.get("synthetic_declared") is not True:
            issues.append(f"{example.example_id} missing synthetic_declared")
        if example.gold.get("no_real_contract_data") is not True:
            issues.append(f"{example.example_id} missing no_real_contract_data")
        if example.gold.get("generation_method") != SYNTHETIC_GENERATION_METHOD:
            issues.append(f"{example.example_id} has unexpected generation_method")
        if example.gold.get("not_a_legal_verdict") is not True:
            issues.append(f"{example.example_id} missing not_a_legal_verdict")
        if example.gold.get("split") != example.split.value:
            issues.append(f"{example.example_id} gold split mismatch")
        if example.gold.get("dataset_ref") != example.dataset_ref:
            issues.append(f"{example.example_id} gold dataset_ref mismatch")
    return issues


def _group_ids(examples: Iterable[SCHEMAS.EvaluationExample]) -> set[str]:
    return {
        str(example.gold["group_id"])
        for example in examples
        if "group_id" in example.gold
    }


def _build_frozen_manifest(root: Path) -> dict[str, Any]:
    files: list[dict[str, Any]] = []
    for dataset_ref in REQUIRED_DATASET_REFS:
        path = root / "frozen_eval" / f"{dataset_ref}.jsonl"
        rows = _read_jsonl(path)
        example_ids = [str(row["example_id"]) for row in rows]
        files.append(
            {
                "dataset_ref": dataset_ref,
                "path": f"data/eval/frozen_eval/{dataset_ref}.jsonl",
                "sha256": _sha256_path(path),
                "record_count": len(rows),
                "example_ids": example_ids,
            }
        )
    combined_payload = "\n".join(
        f"{item['path']} {item['sha256']} {item['record_count']} "
        f"{','.join(item['example_ids'])}"
        for item in files
    )
    return {
        "schema_version": 1,
        "task_id": TASK_ID,
        "created_utc": FIXED_CREATED_UTC,
        "split": "frozen_eval",
        "frozen_split_locked": True,
        "immutability_policy": (
            "Treat frozen_eval JSONL files as locked. Tune only on dev; any "
            "intentional frozen change must update this manifest in review."
        ),
        "synthetic_only": True,
        "no_real_contract_data": True,
        "required_dataset_refs": list(REQUIRED_DATASET_REFS),
        "files": files,
        "combined_sha256": hashlib.sha256(combined_payload.encode("utf-8")).hexdigest(),
    }


def _write_jsonl(path: Path, examples: Sequence[SCHEMAS.EvaluationExample]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(_canonical_json(example.to_dict()) + "\n" for example in examples),
        encoding="utf-8",
    )


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                rows.append(json.loads(stripped))
            except json.JSONDecodeError as exc:  # pragma: no cover - corrupt fixture guard.
                raise ValueError(f"{path}:{line_no}: invalid JSONL") from exc
    return rows


def _canonical_json(value: Mapping[str, Any], *, pretty: bool = False) -> str:
    if pretty:
        return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _display_path(path: Path) -> str:
    try:
        return path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write-data", action="store_true", help="write deterministic data/eval files")
    parser.add_argument("--write-result", action="store_true", help="write the suite result JSON log")
    parser.add_argument("--data-root", type=Path, default=DATA_ROOT)
    args = parser.parse_args(argv)

    if args.write_data:
        write_dataset(args.data_root)
    result = run_synthetic_dataset_suite(args.data_root)
    if args.write_result:
        output = RESULT_LOG_PATH if args.data_root == DATA_ROOT else args.data_root / "suite_result.json"
        write_result_log(result, output)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["summary"]["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

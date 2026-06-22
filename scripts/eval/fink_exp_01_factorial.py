from __future__ import annotations

import argparse
import hashlib
import json
import random
import subprocess
import sys
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from statistics import mean
from typing import Any
from uuid import NAMESPACE_URL, uuid5


REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
if SRC_ROOT.as_posix() not in sys.path:
    sys.path.insert(0, SRC_ROOT.as_posix())

from fink import schemas as SCHEMAS  # noqa: E402
from fink.finance import fim8_evidence_opacity_uncertainty  # noqa: E402
from fink.ingest.session import IngestedDocument  # noqa: E402
from fink.scoring import (  # noqa: E402
    AUTHORITY_GATE_BYPASS_FOR_ABLATION,
    AUTHORITY_GATE_ENFORCE,
    RANKING_POLICY_EXPOSURE_AWARE,
    RANKING_POLICY_SEVERITY_BASELINE,
    FindingPriority,
    aggregate_document_signals,
    load_scoring_config,
    rank_review_findings,
)
from fink.web.analyze import run_local_analysis  # noqa: E402
from fink.web.assumptions import EditableAssumptions  # noqa: E402


TASK_ID = "FINK-EXP-01"
SUITE_ID = "production_path_factorial_experiment"
SEED = 20260622
PAIR_COUNT = 64
DOC_COUNT = PAIR_COUNT * 2
DATA_DIR = REPO_ROOT / "data" / "eval" / "fink_exp_01"
PRODUCTION_FIXTURES_PATH = DATA_DIR / "production_fixtures.jsonl"
ORACLE_PATH = DATA_DIR / "oracle_hidden.jsonl"
MANIFEST_PATH = DATA_DIR / "manifest.json"
RESULT_LOG_PATH = Path(__file__).with_name("fink_exp_01_factorial_results.json")
PAPER_SECTIONS = ("05_experiments.md",)
REGISTERED_GATE_IDS = (
    "production_factorial_run",
    "oracle_weighted_metrics",
    "synthetic_boundary",
    "failure_analysis_present",
)
PRIMARY_METRIC_IDS = (
    "EV-OEC@1",
    "EV-OEC@3",
    "EV-BSWR",
    "EV-USFR",
)
SECONDARY_METRIC_IDS = (
    "EV-FIXTURE-PAIR-COVERAGE",
    "EV-FIM-COVERAGE",
    "EV-UNSUPPORTED-RECALL",
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
ARTIFACT_PATH = "scripts/eval/fink_exp_01_factorial_results.json"
SYNTHETIC_BOUNDARY = (
    "Synthetic-only fixtures generated for FINK-EXP-01; no real contract, "
    "private corpus passage, PDF, ZIP, model weight, token, or user upload is included."
)

ARM_CONFIGS: tuple[dict[str, str], ...] = (
    {
        "arm_id": "authority_off__severity_baseline",
        "authority_gate": AUTHORITY_GATE_BYPASS_FOR_ABLATION,
        "ranking_policy": RANKING_POLICY_SEVERITY_BASELINE,
    },
    {
        "arm_id": "authority_off__exposure_aware",
        "authority_gate": AUTHORITY_GATE_BYPASS_FOR_ABLATION,
        "ranking_policy": RANKING_POLICY_EXPOSURE_AWARE,
    },
    {
        "arm_id": "authority_on__severity_baseline",
        "authority_gate": AUTHORITY_GATE_ENFORCE,
        "ranking_policy": RANKING_POLICY_SEVERITY_BASELINE,
    },
    {
        "arm_id": "authority_on__exposure_aware",
        "authority_gate": AUTHORITY_GATE_ENFORCE,
        "ranking_policy": RANKING_POLICY_EXPOSURE_AWARE,
    },
)

VARIANTS = (
    "ko_canonical",
    "bilingual",
    "noisy_ocr",
    "missing_inputs",
    "unbounded",
    "eligible_ineligible",
    "missing_protection",
    "bilingual_noisy",
)

EXPOSURE_TYPE_BY_CATEGORY = {
    "F1": "nominal_leakage",
    "F2": "nominal_leakage",
    "F3": "present_value_loss",
    "F4": "deferral",
    "F5": "opportunity_cost",
    "F6": "opportunity_cost",
    "F7": "liability_exposure",
    "F8": "opportunity_cost",
    "F9": "evidence_integrity",
}
FIM_BY_CATEGORY = {
    "F1": "FIM-1",
    "F2": "FIM-1",
    "F3": "FIM-2",
    "F4": "FIM-3",
    "F5": "FIM-6",
    "F6": "FIM-5",
    "F7": "FIM-7",
    "F8": "FIM-4",
    "F9": "FIM-8",
}
SUPPORTED_CATEGORIES = frozenset({"F1", "F2", "F3", "F5", "F6", "F7", "F8"})
UNSUPPORTED_CATEGORIES = frozenset({"F4", "F9"})
RISK_CATEGORY_ORDER = tuple(FIM_BY_CATEGORY)


@dataclass(frozen=True)
class CategorySpec:
    category: str
    presence_ko: str
    missing_ko: str
    benign_ko: str
    bilingual_en: str
    base_weight: Decimal


CATEGORY_SPECS: Mapping[str, CategorySpec] = {
    "F1": CategorySpec(
        category="F1",
        presence_ko="정산 근거 자료를 제공하지 않고 감사권을 거부할 수 있다",
        missing_ko="정산은 회사가 단독으로 처리한다",
        benign_ko="월별 정산명세서와 근거 자료 열람권을 제공한다",
        bilingual_en="settlement support records may be withheld and no audit right is provided",
        base_weight=Decimal("900000"),
    ),
    "F2": CategorySpec(
        category="F2",
        presence_ko="회사에서 정하는 기타 비용을 공제할 수 있다",
        missing_ko="수익 배분과 공제는 회사 정책에 따른다",
        benign_ko="공제 항목을 별첨 목록으로 제한하고 총매출 기준을 명시한다",
        bilingual_en="other deductions may be determined by the company",
        base_weight=Decimal("1200000"),
    ),
    "F3": CategorySpec(
        category="F3",
        presence_ko="지급일은 회사가 추후 정한다",
        missing_ko="정산금 지급은 회사 절차에 따른다",
        benign_ko="지급일은 판매월 종료 후 30일 이내로 한다",
        bilingual_en="payment will be determined later at the company's discretion",
        base_weight=Decimal("350000"),
    ),
    "F4": CategorySpec(
        category="F4",
        presence_ko="선급금은 모든 수익에서 전액 회수하고 상계한다",
        missing_ko="선급금 회수는 회사 기준에 따른다",
        benign_ko="선급금 회수율과 회수 기간 상한 및 잔액 명세를 둔다",
        bilingual_en="the advance may be recouped from all revenue streams",
        base_weight=Decimal("1800000"),
    ),
    "F5": CategorySpec(
        category="F5",
        presence_ko="저작권 및 2차적저작물 권리는 회사에 포괄 양도된다",
        missing_ko="저작권과 2차적저작물 이용은 회사가 정한다",
        benign_ko="저작권은 창작자에게 남고 2차적저작물 범위와 수익 배분을 명시한다",
        bilingual_en="all copyright and secondary rights transfer to the company",
        base_weight=Decimal("450000"),
    ),
    "F6": CategorySpec(
        category="F6",
        presence_ko="독점 계약은 36개월이며 자동 갱신된다",
        missing_ko="독점 기간과 갱신은 회사 정책에 따른다",
        benign_ko="비독점 조건과 종료일 및 해지 통지를 명시한다",
        bilingual_en="exclusive rights continue for 36 months with automatic renewal",
        base_weight=Decimal("3000000"),
    ),
    "F7": CategorySpec(
        category="F7",
        presence_ko="손해배상은 전액 배상하며 위약금 전액을 부담한다",
        missing_ko="해지와 위약금은 회사 기준에 따른다",
        benign_ko="책임 상한과 시정 기간 및 실제 손해 기준을 명시한다",
        bilingual_en="all damages and liquidated damages are borne without a cap",
        base_weight=Decimal("2400000"),
    ),
    "F8": CategorySpec(
        category="F8",
        presence_ko="수정은 무제한 무상으로 제공하고 추가 작업은 작가 부담이다",
        missing_ko="수정과 추가 작업은 회사 요청에 따른다",
        benign_ko="수정 2회와 추가 비용 및 제작비 부담 범위를 명시한다",
        bilingual_en="unlimited revisions and additional work are required without additional pay",
        base_weight=Decimal("650000"),
    ),
    "F9": CategorySpec(
        category="F9",
        presence_ko="전자계약 원본 증거를 보관하지 않고 삭제한다",
        missing_ko="전자계약 증거와 개인정보 처리는 회사 기준에 따른다",
        benign_ko="전자계약 원본과 사본 보존 및 개인정보 동의 범위를 명시한다",
        bilingual_en="electronic signature evidence may be deleted and no copy is provided",
        base_weight=Decimal("800000"),
    ),
}


def build_frozen_corpus(seed: int = SEED, pair_count: int = PAIR_COUNT) -> dict[str, Any]:
    """Build deterministic public fixtures plus hidden oracle labels."""

    rng = random.Random(seed)
    production_fixtures: list[dict[str, Any]] = []
    oracle_rows: list[dict[str, Any]] = []

    for pair_index in range(pair_count):
        category = RISK_CATEGORY_ORDER[pair_index % len(RISK_CATEGORY_ORDER)]
        variant = VARIANTS[pair_index % len(VARIANTS)]
        scale = Decimal(85 + rng.randrange(0, 41)) / Decimal("100")
        pair_id = f"FINK-EXP-01-PAIR-{pair_index + 1:03d}"

        risk_doc_id = f"{pair_id}-RISK"
        benign_doc_id = f"{pair_id}-BENIGN"
        risk_fixture, risk_oracle = _fixture_pair_member(
            doc_id=risk_doc_id,
            pair_id=pair_id,
            pair_index=pair_index,
            category=category,
            variant=variant,
            is_benign=False,
            scale=scale,
        )
        benign_fixture, benign_oracle = _fixture_pair_member(
            doc_id=benign_doc_id,
            pair_id=pair_id,
            pair_index=pair_index,
            category=category,
            variant=variant,
            is_benign=True,
            scale=scale,
        )
        production_fixtures.extend((risk_fixture, benign_fixture))
        oracle_rows.extend((risk_oracle, benign_oracle))

    manifest = _build_manifest(production_fixtures, oracle_rows, seed)
    return {
        "production_fixtures": tuple(production_fixtures),
        "oracle_hidden": tuple(oracle_rows),
        "manifest": manifest,
    }


def write_frozen_corpus(data_dir: Path | str = DATA_DIR) -> dict[str, Any]:
    root = Path(data_dir)
    corpus = build_frozen_corpus()
    root.mkdir(parents=True, exist_ok=True)
    _write_jsonl(root / PRODUCTION_FIXTURES_PATH.name, corpus["production_fixtures"])
    _write_jsonl(root / ORACLE_PATH.name, corpus["oracle_hidden"])
    (root / MANIFEST_PATH.name).write_text(
        _canonical_json(corpus["manifest"], pretty=True) + "\n",
        encoding="utf-8",
    )
    return corpus


def load_frozen_corpus(data_dir: Path | str = DATA_DIR) -> dict[str, Any]:
    root = Path(data_dir)
    if not (
        (root / PRODUCTION_FIXTURES_PATH.name).is_file()
        and (root / ORACLE_PATH.name).is_file()
        and (root / MANIFEST_PATH.name).is_file()
    ):
        return write_frozen_corpus(root)
    production = tuple(_read_jsonl(root / PRODUCTION_FIXTURES_PATH.name))
    oracle = tuple(_read_jsonl(root / ORACLE_PATH.name))
    manifest = json.loads((root / MANIFEST_PATH.name).read_text(encoding="utf-8"))
    return {
        "production_fixtures": production,
        "oracle_hidden": oracle,
        "manifest": manifest,
    }


def run_factorial_experiment(
    *,
    data_dir: Path | str = DATA_DIR,
    bootstrap_samples: int = 200,
) -> dict[str, Any]:
    corpus = load_frozen_corpus(data_dir)
    fixtures = tuple(corpus["production_fixtures"])
    oracle_rows = tuple(corpus["oracle_hidden"])
    oracle_by_doc = {row["doc_id"]: row for row in oracle_rows}
    _validate_fixture_oracle_boundary(fixtures, oracle_by_doc)

    config = load_scoring_config()
    per_doc = tuple(
        _run_shared_production_doc(fixture, oracle_by_doc[fixture["doc_id"]], config)
        for fixture in fixtures
    )

    arm_reports = {
        arm["arm_id"]: _arm_report(
            arm,
            per_doc,
            bootstrap_samples=bootstrap_samples,
        )
        for arm in ARM_CONFIGS
    }
    metric_values = {
        arm_id: report["metric_values"] for arm_id, report in arm_reports.items()
    }
    cases = _gate_cases(corpus, per_doc, arm_reports)
    passed = sum(1 for case in cases if case["status"] == "PASS")
    failed = len(cases) - passed
    result = {
        "suite": SUITE_ID,
        "task_id": TASK_ID,
        "paper_sections": list(PAPER_SECTIONS),
        "registered_gates": list(REGISTERED_GATE_IDS),
        "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "commit": _git_head(),
        "seed": SEED,
        "arm_configs": [dict(arm) for arm in ARM_CONFIGS],
        "production_path": {
            "shared_engines": [
                "fink.web.analyze.run_local_analysis",
                "fink.scoring.aggregate_document_signals",
                "fink.scoring.rank_review_findings",
                "fink.web.assumptions.recompute_assumptions",
                "fink.finance.fim1_revenue_base_deduction_leakage",
                "fink.finance.fim2_payment_delay_present_value_loss",
                "fink.finance.fim3_mg_advance_recoupment",
                "fink.finance.fim4_unpaid_additional_work_cost",
                "fink.finance.fim5_exclusivity_renewal_opportunity_cost",
                "fink.finance.fim6_ip_secondary_rights_scenario_value",
                "fink.finance.fim7_penalty_liability_exposure",
                "fink.finance.fim8_evidence_opacity_uncertainty",
            ],
            "production_receives_oracle_fields": False,
            "arm_specific_code_path": "rank_review_findings authority_gate/ranking_policy options",
            "analysis_call_count": len(per_doc),
            "arm_ranking_call_count": len(per_doc) * len(ARM_CONFIGS),
        },
        "hashes": _hashes(corpus),
        "corpus": _corpus_summary(corpus),
        "metric_definitions": _metric_definitions(),
        "metric_values": metric_values,
        "measured_extrema": _measured_extrema(metric_values),
        "arm_reports": arm_reports,
        "bias_guards": _bias_guards(corpus, arm_reports),
        "failure_analysis": _failure_analysis(arm_reports),
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
    return result


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


def _fixture_pair_member(
    *,
    doc_id: str,
    pair_id: str,
    pair_index: int,
    category: str,
    variant: str,
    is_benign: bool,
    scale: Decimal,
) -> tuple[dict[str, Any], dict[str, Any]]:
    spec = CATEGORY_SPECS[category]
    input_mode = "ocr" if variant in {"noisy_ocr", "bilingual_noisy"} else "paste"
    rendered_text = _render_document(
        category=category,
        variant=variant,
        is_benign=is_benign,
        pair_index=pair_index,
    )
    fixture = {
        "doc_id": doc_id,
        "pair_id": pair_id,
        "input_mode": input_mode,
        "rendered_text": rendered_text,
        "ocr_confidence": 0.64 if input_mode == "ocr" else None,
        "scenario_inputs": _scenario_payload(
            category=category,
            variant=variant,
            is_benign=is_benign,
            scale=scale,
        ),
        "fixture_profile": {
            "synthetic_only": True,
            "no_real_contract": True,
            "ko_canonical": True,
            "generated_translation": variant in {"bilingual", "bilingual_noisy"},
            "variant": variant,
            "public_export": True,
        },
        "permitted_input_fields": [
            "doc_id",
            "pair_id",
            "input_mode",
            "rendered_text",
            "ocr_confidence",
            "scenario_inputs",
            "fixture_profile",
            "permitted_input_fields",
        ],
    }

    oracle_findings = [] if is_benign else _oracle_findings(category, variant, spec, scale)
    oracle = {
        "doc_id": doc_id,
        "pair_id": pair_id,
        "is_benign": is_benign,
        "oracle_findings": oracle_findings,
        "oracle_source": "generator_hidden_fields_not_passed_to_production",
        "variant": variant,
        "synthetic_only": True,
        "no_real_contract": True,
        "counterfactual_pair_doc_id": (
            doc_id.replace("-BENIGN", "-RISK") if is_benign else doc_id.replace("-RISK", "-BENIGN")
        ),
    }
    return fixture, oracle


def _render_document(
    *,
    category: str,
    variant: str,
    is_benign: bool,
    pair_index: int,
) -> str:
    spec = CATEGORY_SPECS[category]
    if is_benign:
        body_lines = [
            f"합성 계약 {pair_index + 1}호. 실제 계약이 아닌 평가용 문서이다.",
            f"제1조 보호 조항. {spec.benign_ko}.",
        ]
        if category in {"F5", "F6"}:
            body_lines.append(f"제2조 권리와 기간. {CATEGORY_SPECS['F5'].benign_ko}.")
            body_lines.append(f"제3조 독점. {CATEGORY_SPECS['F6'].benign_ko}.")
    else:
        risky_clause = spec.missing_ko if variant == "missing_protection" else spec.presence_ko
        body_lines = [
            f"합성 계약 {pair_index + 1}호. 실제 계약이 아닌 평가용 문서이다.",
            f"제1조 검토 대상. {risky_clause}.",
        ]
        if category in {"F5", "F6"}:
            body_lines.append(f"제2조 권리. {CATEGORY_SPECS['F5'].presence_ko}.")
            body_lines.append(f"제3조 독점. {CATEGORY_SPECS['F6'].presence_ko}.")
        elif variant == "unbounded" and category != "F7":
            body_lines.append(f"제2조 책임. {CATEGORY_SPECS['F7'].presence_ko}.")
        elif variant == "eligible_ineligible" and category not in UNSUPPORTED_CATEGORIES:
            body_lines.append(f"제2조 전자계약. {CATEGORY_SPECS['F9'].presence_ko}.")

    if variant in {"bilingual", "bilingual_noisy"}:
        body_lines.append(f"Generated English aid: {spec.bilingual_en}.")
    if variant in {"noisy_ocr", "bilingual_noisy"}:
        return "\n".join(_ocr_noise(line) for line in body_lines)
    return "\n".join(body_lines)


def _ocr_noise(line: str) -> str:
    return line.replace("  ", " ").replace("정산", "정 산")


def _oracle_findings(
    category: str,
    variant: str,
    spec: CategorySpec,
    scale: Decimal,
) -> list[dict[str, Any]]:
    categories = [category]
    if category in {"F5", "F6"}:
        categories = ["F5", "F6"]
    elif variant == "unbounded" and category != "F7":
        categories.append("F7")
    elif variant == "eligible_ineligible" and category not in UNSUPPORTED_CATEGORIES:
        categories.append("F9")

    findings: list[dict[str, Any]] = []
    for rank, item_category in enumerate(categories, start=1):
        item_spec = CATEGORY_SPECS[item_category]
        weight = item_spec.base_weight * scale
        if item_category == "F6":
            weight *= Decimal("1.45")
        if item_category == "F5":
            weight *= Decimal("0.75")
        if variant == "unbounded" and item_category == "F7":
            weight *= Decimal("1.60")
        findings.append(
            {
                "oracle_rank": rank,
                "risk_category": item_category,
                "fim_module": FIM_BY_CATEGORY[item_category],
                "exposure_type": EXPOSURE_TYPE_BY_CATEGORY[item_category],
                "oracle_exposure_weight": _decimal_text(weight),
                "authority_support_expected": (
                    "official_supported"
                    if item_category in SUPPORTED_CATEGORIES
                    else "unsupported_practice_reference_only"
                ),
                "variant": variant,
            }
        )
    return findings


def _scenario_payload(
    *,
    category: str,
    variant: str,
    is_benign: bool,
    scale: Decimal,
) -> dict[str, Any]:
    amount_scale = Decimal("0.65") if is_benign else scale
    payload: dict[str, Any] = {
        "annual_discount_rate": "0.05",
        "sales_low": _decimal_text(Decimal("300000") * amount_scale),
        "sales_base": _decimal_text(Decimal("600000") * amount_scale),
        "sales_high": _decimal_text(Decimal("1000000") * amount_scale),
        "creator_hourly_value": "45000",
        "hours_per_unit": "5",
        "unpaid_revision_units": 5,
        "alternative_monthly_revenue": _decimal_text(Decimal("1800000") * amount_scale),
        "scenario_probability_low": "0.30",
        "scenario_probability_base": "0.60",
        "scenario_probability_high": "0.80",
        "secondary_rights": [
            {
                "type": "translation",
                "value": [
                    _decimal_text(Decimal("200000") * amount_scale),
                    _decimal_text(Decimal("400000") * amount_scale),
                    _decimal_text(Decimal("700000") * amount_scale),
                ],
                "prob": ["0.20", "0.30", "0.40"],
            }
        ],
        "penalty_probability": "0.10",
        "gross_sales": _decimal_text(Decimal("12000000") * amount_scale),
        "refunds": _decimal_text(Decimal("500000") * amount_scale),
        "explicitly_allowed_deductions": _decimal_text(Decimal("1000000") * amount_scale),
        "revenue_share_rate": "0.50",
        "fixed_fee": "0",
        "advance_recoupment": "0",
        "open_ended_deductions_low": _decimal_text(Decimal("100000") * amount_scale),
        "open_ended_deductions_base": _decimal_text(Decimal("400000") * amount_scale),
        "open_ended_deductions_high": _decimal_text(Decimal("900000") * amount_scale),
        "delayed_amount": _decimal_text(Decimal("3000000") * amount_scale),
        "delay_days_low": "30",
        "delay_days_base": "60",
        "delay_days_high": "90",
        "recoupable_advance": _decimal_text(Decimal("5000000") * amount_scale),
        "cumulative_recouped": _decimal_text(Decimal("1000000") * amount_scale),
        "exclusivity_duration_months": 24,
        "renewal_duration_months": None,
        "include_renewal": False,
        "explicit_penalty_cap": _decimal_text(Decimal("5000000") * amount_scale),
        "penalty_scenario_amount": _decimal_text(Decimal("7000000") * amount_scale),
        "is_uncapped": False,
        "is_ambiguous": False,
        "inputs_are_synthetic": True,
    }
    if variant == "missing_inputs":
        for field in _fields_for_category(category):
            payload[field] = None
    if variant == "unbounded" and category == "F7":
        payload["explicit_penalty_cap"] = None
        payload["penalty_probability"] = None
        payload["penalty_scenario_amount"] = None
        payload["is_uncapped"] = True
    return payload


def _fields_for_category(category: str) -> tuple[str, ...]:
    return {
        "F1": ("gross_sales", "open_ended_deductions_base"),
        "F2": ("gross_sales", "open_ended_deductions_base"),
        "F3": ("delayed_amount", "delay_days_base"),
        "F4": ("recoupable_advance", "sales_base"),
        "F5": ("secondary_rights",),
        "F6": ("alternative_monthly_revenue", "scenario_probability_base"),
        "F7": ("explicit_penalty_cap", "penalty_probability"),
        "F8": ("unpaid_revision_units", "creator_hourly_value"),
        "F9": (),
    }[category]


def _run_shared_production_doc(
    fixture: Mapping[str, Any],
    oracle: Mapping[str, Any],
    config: Any,
) -> dict[str, Any]:
    assumptions = _editable_assumptions(fixture["scenario_inputs"])
    if fixture["input_mode"] == "ocr":
        result = run_local_analysis(
            ingested=_synthetic_ingested_document(fixture),
            scenario_inputs=assumptions,
        )
    else:
        result = run_local_analysis(
            pasted_text=str(fixture["rendered_text"]),
            scenario_inputs=assumptions,
        )
    signals = _signals_from_scoring(result.scoring)
    fim8_diag = _fim8_diagnostic(result.exposures, config)
    signal_signature = _signal_signature(
        signals,
        result.scoring.contributions,
        rendered_text=str(fixture["rendered_text"]),
    )
    return {
        "fixture": fixture,
        "oracle": oracle,
        "signals": signals,
        "scoring": result.scoring,
        "exposures": result.exposures,
        "fim8": fim8_diag,
        "retrieved_record_count": result.retrieved_record_count,
        "review_priority_score": result.review_priority_score,
        "signal_signature": signal_signature,
    }


def _arm_report(
    arm: Mapping[str, str],
    per_doc: Sequence[Mapping[str, Any]],
    *,
    bootstrap_samples: int,
) -> dict[str, Any]:
    doc_rows = []
    for doc in per_doc:
        priorities = rank_review_findings(
            doc["signals"],
            exposures=doc["exposures"],
            contributions=doc["scoring"].contributions,
            ranking_policy=arm["ranking_policy"],
            authority_gate=arm["authority_gate"],
        )
        doc_rows.append(_doc_metric_row(doc, priorities))

    metric_bundle = _metric_bundle(doc_rows)
    ci = _bootstrap_ci(doc_rows, bootstrap_samples, seed=_arm_seed(arm["arm_id"]))
    failures = _arm_failures(arm["arm_id"], doc_rows)
    return {
        "arm_id": arm["arm_id"],
        "authority_gate": arm["authority_gate"],
        "ranking_policy": arm["ranking_policy"],
        "metric_values": metric_bundle["metric_values"],
        "metric_denominators": metric_bundle["metric_denominators"],
        "confidence_intervals": ci,
        "raw_values": doc_rows,
        "failure_cases": failures,
        "production_consistency": {
            "doc_count": len(doc_rows),
            "signal_signature_sha256": _sha256_json(
                {row["doc_id"]: row["signal_signature"] for row in doc_rows}
            ),
            "all_docs_ranked_by_production_function": True,
        },
    }


def _doc_metric_row(
    doc: Mapping[str, Any],
    priorities: Sequence[FindingPriority],
) -> dict[str, Any]:
    contributions = {
        (item.signal_id, item.clause_id): item
        for item in doc["scoring"].contributions
    }
    scored = tuple(priority for priority in priorities if priority.scored)
    top1 = scored[:1]
    top3 = scored[:3]
    oracle_findings = tuple(doc["oracle"]["oracle_findings"])
    oracle_weight_by_type = _oracle_weight_by_type(oracle_findings)
    row = {
        "doc_id": doc["fixture"]["doc_id"],
        "pair_id": doc["fixture"]["pair_id"],
        "variant": doc["fixture"]["fixture_profile"]["variant"],
        "input_mode": doc["fixture"]["input_mode"],
        "is_benign": bool(doc["oracle"]["is_benign"]),
        "oracle_categories": [item["risk_category"] for item in oracle_findings],
        "oracle_weight_by_type": oracle_weight_by_type,
        "top1_scored_categories": [priority.risk_category.value for priority in top1],
        "top3_scored_categories": [priority.risk_category.value for priority in top3],
        "scored_finding_count": len(scored),
        "unsupported_scored_finding_count": 0,
        "supported_scored_finding_count": 0,
        "fim8_called": doc["fim8"]["called"],
        "fim8_band_widen_factor": doc["fim8"]["band_widen_factor"],
        "retrieved_record_count": doc["retrieved_record_count"],
        "review_priority_score": doc["review_priority_score"],
        "signal_signature": doc["signal_signature"],
        "raw_findings": [],
    }
    unsupported_count = 0
    supported_count = 0
    for priority in scored:
        contribution = contributions.get((priority.signal_id, priority.clause_id))
        supported = bool(contribution is not None and contribution.contribution > 0)
        if supported:
            supported_count += 1
        else:
            unsupported_count += 1
        row["raw_findings"].append(
            {
                "rank": len(row["raw_findings"]) + 1,
                "signal_id": priority.signal_id,
                "risk_category": priority.risk_category.value,
                "scored": priority.scored,
                "supported_by_official_evidence": supported,
                "priority_basis": priority.priority_basis,
                "quantification_status": priority.quantification_status,
                "fim_module": priority.fim_module.value if priority.fim_module else None,
                "exposure_type": priority.exposure_type.value if priority.exposure_type else None,
            }
        )
    row["unsupported_scored_finding_count"] = unsupported_count
    row["supported_scored_finding_count"] = supported_count
    row["captured_weight_at_1_by_type"] = _captured_weight_by_type(oracle_findings, top1)
    row["captured_weight_at_3_by_type"] = _captured_weight_by_type(oracle_findings, top3)
    return row


def _metric_bundle(doc_rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    oec1 = _oracle_exposure_capture(doc_rows, "captured_weight_at_1_by_type")
    oec3 = _oracle_exposure_capture(doc_rows, "captured_weight_at_3_by_type")
    benign_rows = [row for row in doc_rows if row["is_benign"]]
    benign_warning_count = sum(
        1 for row in benign_rows if int(row["scored_finding_count"]) > 0
    )
    scored_total = sum(int(row["scored_finding_count"]) for row in doc_rows)
    unsupported_total = sum(
        int(row["unsupported_scored_finding_count"]) for row in doc_rows
    )
    unsupported_recall_denominator = sum(
        1 for row in doc_rows if _has_unsupported_oracle(row)
    )
    unsupported_recall_numerator = sum(
        1
        for row in doc_rows
        if _has_unsupported_oracle(row)
        and int(row["unsupported_scored_finding_count"]) > 0
    )
    metric_values = {
        "EV-OEC@1": _round(oec1["macro_average"]),
        "EV-OEC@3": _round(oec3["macro_average"]),
        "EV-BSWR": _round(
            benign_warning_count / len(benign_rows) if benign_rows else 0.0
        ),
        "EV-USFR": _round(unsupported_total / scored_total if scored_total else 0.0),
        "EV-FIXTURE-PAIR-COVERAGE": _round(
            len({row["pair_id"] for row in doc_rows}) / PAIR_COUNT
        ),
        "EV-FIM-COVERAGE": _round(
            len(_observed_fim_modules(doc_rows)) / 8
        ),
        "EV-UNSUPPORTED-RECALL": _round(
            unsupported_recall_numerator / unsupported_recall_denominator
            if unsupported_recall_denominator
            else 0.0
        ),
    }
    return {
        "metric_values": metric_values,
        "metric_denominators": {
            "EV-OEC@1": oec1["denominators"],
            "EV-OEC@3": oec3["denominators"],
            "EV-BSWR": {
                "benign_doc_count": len(benign_rows),
                "benign_docs_with_scored_warning": benign_warning_count,
            },
            "EV-USFR": {
                "scored_finding_count": scored_total,
                "unsupported_scored_finding_count": unsupported_total,
            },
            "EV-FIXTURE-PAIR-COVERAGE": {
                "observed_pair_count": len({row["pair_id"] for row in doc_rows}),
                "required_pair_count": PAIR_COUNT,
            },
            "EV-FIM-COVERAGE": {
                "observed_fim_modules": sorted(_observed_fim_modules(doc_rows)),
                "required_fim_modules": [f"FIM-{index}" for index in range(1, 9)],
            },
            "EV-UNSUPPORTED-RECALL": {
                "unsupported_oracle_doc_count": unsupported_recall_denominator,
                "unsupported_oracle_docs_scored_under_arm": unsupported_recall_numerator,
            },
        },
    }


def _oracle_exposure_capture(
    doc_rows: Sequence[Mapping[str, Any]],
    captured_key: str,
) -> dict[str, Any]:
    denominators: dict[str, Decimal] = defaultdict(Decimal)
    captured: dict[str, Decimal] = defaultdict(Decimal)
    for row in doc_rows:
        for exposure_type, raw in row["oracle_weight_by_type"].items():
            denominators[exposure_type] += Decimal(str(raw))
        for exposure_type, raw in row[captured_key].items():
            captured[exposure_type] += Decimal(str(raw))
    per_type = {
        exposure_type: (
            float(captured.get(exposure_type, Decimal("0")) / denominator)
            if denominator
            else 0.0
        )
        for exposure_type, denominator in denominators.items()
    }
    macro = mean(per_type.values()) if per_type else 0.0
    return {
        "macro_average": macro,
        "per_type": {key: _round(value) for key, value in sorted(per_type.items())},
        "denominators": {
            "macro_type_count": len(per_type),
            "oracle_exposure_weight_by_type": {
                key: _decimal_text(value) for key, value in sorted(denominators.items())
            },
            "captured_oracle_exposure_weight_by_type": {
                key: _decimal_text(value) for key, value in sorted(captured.items())
            },
            "weight_source": "hidden oracle exposure, not predicted exposure",
        },
    }


def _bootstrap_ci(
    doc_rows: Sequence[Mapping[str, Any]],
    samples: int,
    *,
    seed: int,
) -> dict[str, dict[str, Any]]:
    rng = random.Random(seed)
    rows = tuple(doc_rows)
    values: dict[str, list[float]] = {metric: [] for metric in PRIMARY_METRIC_IDS}
    if not rows:
        return {
            metric: {"method": "percentile_bootstrap_by_document", "ci95": [0.0, 0.0]}
            for metric in PRIMARY_METRIC_IDS
        }
    for _ in range(samples):
        sample = [rows[rng.randrange(0, len(rows))] for _ in rows]
        metrics = _metric_bundle(sample)["metric_values"]
        for metric in PRIMARY_METRIC_IDS:
            values[metric].append(float(metrics[metric]))
    return {
        metric: {
            "method": "percentile_bootstrap_by_document",
            "samples": samples,
            "seed": seed,
            "ci95": _percentile_ci(metric_values),
        }
        for metric, metric_values in values.items()
    }


def _percentile_ci(values: Sequence[float]) -> list[float]:
    if not values:
        return [0.0, 0.0]
    ordered = sorted(values)
    low_idx = int(0.025 * (len(ordered) - 1))
    high_idx = int(0.975 * (len(ordered) - 1))
    return [_round(ordered[low_idx]), _round(ordered[high_idx])]


def _gate_cases(
    corpus: Mapping[str, Any],
    per_doc: Sequence[Mapping[str, Any]],
    arm_reports: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    return [
        _production_factorial_case(per_doc, arm_reports),
        _oracle_weighted_metrics_case(arm_reports),
        _synthetic_boundary_case(corpus),
        _failure_analysis_case(arm_reports),
    ]


def _production_factorial_case(
    per_doc: Sequence[Mapping[str, Any]],
    arm_reports: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    issues: list[str] = []
    if set(arm_reports) != {arm["arm_id"] for arm in ARM_CONFIGS}:
        issues.append("four configured arms were not all executed")
    fixture_ids = [doc["fixture"]["doc_id"] for doc in per_doc]
    if len(fixture_ids) != DOC_COUNT:
        issues.append(f"expected {DOC_COUNT} documents, got {len(fixture_ids)}")
    for report in arm_reports.values():
        if report["production_consistency"]["doc_count"] != len(fixture_ids):
            issues.append(f"{report['arm_id']}: fixture count mismatch")
    return {
        "id": "production_factorial_run",
        "metrics": list(PRIMARY_METRIC_IDS),
        "status": "PASS" if not issues else "FAIL",
        "expected": {
            "arm_count": 4,
            "same_fixture_ids_all_arms": True,
            "production_engines_shared": True,
            "minimum_paired_docs": PAIR_COUNT,
        },
        "observed": {
            "arm_ids": sorted(arm_reports),
            "doc_count": len(fixture_ids),
            "pair_count": len({doc["fixture"]["pair_id"] for doc in per_doc}),
            "issue_count": len(issues),
            "issues": issues,
        },
    }


def _oracle_weighted_metrics_case(
    arm_reports: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    issues: list[str] = []
    for arm_id, report in arm_reports.items():
        values = report["metric_values"]
        for metric in PRIMARY_METRIC_IDS:
            if metric not in values:
                issues.append(f"{arm_id}: missing {metric}")
            elif not 0.0 <= float(values[metric]) <= 1.0:
                issues.append(f"{arm_id}/{metric}: outside 0..1")
        for metric in ("EV-OEC@1", "EV-OEC@3"):
            denom = report["metric_denominators"][metric]
            if denom.get("weight_source") != "hidden oracle exposure, not predicted exposure":
                issues.append(f"{arm_id}/{metric}: did not declare oracle weighting")
            if int(denom.get("macro_type_count", 0)) < 5:
                issues.append(f"{arm_id}/{metric}: missing exposure-type macro coverage")
    return {
        "id": "oracle_weighted_metrics",
        "metrics": list(PRIMARY_METRIC_IDS),
        "status": "PASS" if not issues else "FAIL",
        "expected": {
            "oracle_exposure_not_predicted_exposure": True,
            "within_type_then_macro_average": True,
            "confidence_intervals_present": True,
        },
        "observed": {
            "issue_count": len(issues),
            "issues": issues,
        },
    }


def _synthetic_boundary_case(corpus: Mapping[str, Any]) -> dict[str, Any]:
    fixtures = tuple(corpus["production_fixtures"])
    oracle = tuple(corpus["oracle_hidden"])
    issues = []
    forbidden_fixture_keys = {
        "oracle_findings",
        "oracle_rank",
        "risk_category",
        "expected_ranking",
        "oracle_exposure_weight",
        "is_benign",
    }
    for fixture in fixtures:
        if not fixture.get("fixture_profile", {}).get("synthetic_only"):
            issues.append(f"{fixture['doc_id']}: not marked synthetic")
        if forbidden_fixture_keys & set(fixture):
            issues.append(f"{fixture['doc_id']}: production fixture leaks oracle key")
        if "실제 계약이 아닌" not in str(fixture.get("rendered_text", "")):
            issues.append(f"{fixture['doc_id']}: missing synthetic text boundary")
    for row in oracle:
        if not row.get("synthetic_only") or not row.get("no_real_contract"):
            issues.append(f"{row['doc_id']}: oracle boundary missing")
    return {
        "id": "synthetic_boundary",
        "metrics": [],
        "status": "PASS" if not issues else "FAIL",
        "expected": {
            "synthetic_only": True,
            "no_real_contract": True,
            "oracle_fields_absent_from_production_fixtures": True,
        },
        "observed": {
            "production_fixture_count": len(fixtures),
            "oracle_row_count": len(oracle),
            "issue_count": len(issues),
            "issues": issues,
        },
    }


def _failure_analysis_case(
    arm_reports: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    failures = _failure_analysis(arm_reports)
    issues = []
    if not failures["cases"]:
        issues.append("at least one actual failure case is required")
    return {
        "id": "failure_analysis_present",
        "metrics": [],
        "status": "PASS" if not issues else "FAIL",
        "expected": {
            "actual_failure_case_count_min": 1,
            "failure_types_include_missed_or_unsupported": True,
        },
        "observed": {
            "failure_case_count": len(failures["cases"]),
            "failure_types": sorted({case["failure_type"] for case in failures["cases"]}),
            "issue_count": len(issues),
            "issues": issues,
        },
    }


def _failure_analysis(
    arm_reports: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    cases: list[dict[str, Any]] = []
    for arm_id, report in arm_reports.items():
        cases.extend(report["failure_cases"])
    selected = cases[:12]
    return {
        "description": (
            "Actual measured failure rows from the production-path arms. "
            "Rows identify missed oracle exposure or scored unsupported findings; "
            "no rendered contract text is needed for the analysis."
        ),
        "cases": selected,
        "case_count": len(selected),
    }


def _arm_failures(
    arm_id: str,
    doc_rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    for row in doc_rows:
        if row["is_benign"] and int(row["scored_finding_count"]) > 0:
            failures.append(
                {
                    "arm_id": arm_id,
                    "doc_id": row["doc_id"],
                    "pair_id": row["pair_id"],
                    "variant": row["variant"],
                    "failure_type": "benign_scored_warning",
                    "observed_categories": row["top3_scored_categories"],
                    "rendered_text_sha256": row["signal_signature"]["rendered_text_sha256"],
                }
            )
        if (not row["is_benign"]) and not row["top3_scored_categories"]:
            failures.append(
                {
                    "arm_id": arm_id,
                    "doc_id": row["doc_id"],
                    "pair_id": row["pair_id"],
                    "variant": row["variant"],
                    "failure_type": "missed_oracle_exposure_no_scored_finding",
                    "oracle_categories": row["oracle_categories"],
                    "rendered_text_sha256": row["signal_signature"]["rendered_text_sha256"],
                }
            )
        if int(row["unsupported_scored_finding_count"]) > 0:
            failures.append(
                {
                    "arm_id": arm_id,
                    "doc_id": row["doc_id"],
                    "pair_id": row["pair_id"],
                    "variant": row["variant"],
                    "failure_type": "unsupported_scored_finding",
                    "observed_categories": row["top3_scored_categories"],
                    "oracle_categories": row["oracle_categories"],
                    "rendered_text_sha256": row["signal_signature"]["rendered_text_sha256"],
                }
            )
    return failures


def _metric_definitions() -> dict[str, Any]:
    return {
        "EV-OEC@1": {
            "name": "Oracle Exposure Capture at 1",
            "definition": (
                "For each exposure type, sum hidden oracle exposure weight for oracle "
                "categories captured by the top one scored production finding; divide by "
                "the hidden oracle exposure denominator for that type, then macro-average "
                "across types."
            ),
            "weight_source": "oracle_exposure_weight from hidden oracle rows, never predicted exposure",
            "direction": "higher_is_better",
        },
        "EV-OEC@3": {
            "name": "Oracle Exposure Capture at 3",
            "definition": "Same as EV-OEC@1 with the top three scored production findings.",
            "weight_source": "oracle_exposure_weight from hidden oracle rows, never predicted exposure",
            "direction": "higher_is_better",
        },
        "EV-BSWR": {
            "name": "Benign Scored-Warning Rate",
            "definition": "Benign documents with at least one scored production finding divided by benign documents.",
            "direction": "lower_is_better",
        },
        "EV-USFR": {
            "name": "Unsupported Scored-Finding Rate",
            "definition": (
                "Scored production findings without positive A0-A2 contribution divided by "
                "all scored production findings."
            ),
            "direction": "lower_is_better",
        },
        "EV-FIXTURE-PAIR-COVERAGE": {
            "definition": "Observed frozen pair count divided by the required pair count.",
            "direction": "higher_is_better",
        },
        "EV-FIM-COVERAGE": {
            "definition": "Observed FIM modules in hidden oracle findings divided by FIM-1..8.",
            "direction": "higher_is_better",
        },
        "EV-UNSUPPORTED-RECALL": {
            "definition": "Unsupported-oracle risk documents with scored unsupported findings divided by unsupported-oracle risk documents.",
            "direction": "diagnostic_only",
        },
    }


def _measured_extrema(
    metric_values: Mapping[str, Mapping[str, float]],
) -> dict[str, Any]:
    extrema: dict[str, Any] = {}
    directions = {
        "EV-OEC@1": "higher_is_better",
        "EV-OEC@3": "higher_is_better",
        "EV-BSWR": "lower_is_better",
        "EV-USFR": "lower_is_better",
    }
    for metric, direction in directions.items():
        values = {arm: metrics[metric] for arm, metrics in metric_values.items()}
        selected_value = max(values.values()) if direction == "higher_is_better" else min(values.values())
        winning_arms = sorted(arm for arm, value in values.items() if value == selected_value)
        extrema[metric] = {
            "direction": direction,
            "value": selected_value,
            "arms": winning_arms,
            "severity_baseline_arm_in_best_set": any(
                "severity_baseline" in arm for arm in winning_arms
            ),
            "scope": "measured synthetic-only fixture only",
        }
    return extrema


def _bias_guards(
    corpus: Mapping[str, Any],
    arm_reports: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    fixture_hashes = {
        arm_id: _sha256_json(
            [row["doc_id"] for row in report["raw_values"]]
        )
        for arm_id, report in arm_reports.items()
    }
    return {
        "same_frozen_fixtures_all_arms": {
            "status": "PASS" if len(set(fixture_hashes.values())) == 1 else "FAIL",
            "detail": "Every arm ranks the same frozen production fixture ids.",
        },
        "oracle_hidden_from_production": {
            "status": "PASS",
            "detail": "Production fixture JSONL excludes oracle labels, risk categories, and oracle weights.",
        },
        "oracle_not_predicted_exposure_weighting": {
            "status": "PASS",
            "detail": "OEC denominators are hidden oracle_exposure_weight values.",
        },
        "within_type_macro_average": {
            "status": "PASS",
            "detail": "OEC is computed within exposure type before macro-average.",
        },
        "synthetic_only_privacy_boundary": {
            "status": (
                "PASS"
                if corpus["manifest"]["synthetic_only_boundary"]["no_real_contract"]
                else "FAIL"
            ),
            "detail": SYNTHETIC_BOUNDARY,
        },
    }


def _corpus_summary(corpus: Mapping[str, Any]) -> dict[str, Any]:
    fixtures = tuple(corpus["production_fixtures"])
    oracle_rows = tuple(corpus["oracle_hidden"])
    oracle_findings = [
        item
        for row in oracle_rows
        for item in row.get("oracle_findings", [])
    ]
    return {
        "data_dir": _display_path(DATA_DIR),
        "production_fixture_path": _display_path(PRODUCTION_FIXTURES_PATH),
        "oracle_path": _display_path(ORACLE_PATH),
        "manifest_path": _display_path(MANIFEST_PATH),
        "doc_count": len(fixtures),
        "pair_count": len({fixture["pair_id"] for fixture in fixtures}),
        "risk_doc_count": sum(1 for row in oracle_rows if not row["is_benign"]),
        "benign_doc_count": sum(1 for row in oracle_rows if row["is_benign"]),
        "variant_counts": dict(
            sorted(Counter(fixture["fixture_profile"]["variant"] for fixture in fixtures).items())
        ),
        "input_mode_counts": dict(sorted(Counter(fixture["input_mode"] for fixture in fixtures).items())),
        "oracle_category_counts": dict(
            sorted(Counter(item["risk_category"] for item in oracle_findings).items())
        ),
        "oracle_fim_modules": sorted({item["fim_module"] for item in oracle_findings}),
        "oracle_exposure_types": sorted({item["exposure_type"] for item in oracle_findings}),
        "synthetic_only_boundary": SYNTHETIC_BOUNDARY,
    }


def _hashes(corpus: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "production_fixture_sha256": _sha256_json(corpus["production_fixtures"]),
        "oracle_hidden_sha256": _sha256_json(corpus["oracle_hidden"]),
        "manifest_sha256": _sha256_json(corpus["manifest"]),
        "config_hashes": {
            "config/scoring_config.yaml": _sha256_file(REPO_ROOT / "config" / "scoring_config.yaml"),
            "config/signal_rules.yaml": _sha256_file(REPO_ROOT / "config" / "signal_rules.yaml"),
        },
        "corpus_hashes": {
            "data/corpus": _sha256_tree(REPO_ROOT / "data" / "corpus"),
            "data/eval/fink_exp_01": _sha256_json(
                {
                    "production": corpus["production_fixtures"],
                    "oracle": corpus["oracle_hidden"],
                    "manifest": corpus["manifest"],
                }
            ),
        },
    }


def _build_manifest(
    production_fixtures: Sequence[Mapping[str, Any]],
    oracle_rows: Sequence[Mapping[str, Any]],
    seed: int,
) -> dict[str, Any]:
    manifest = {
        "schema_version": 1,
        "task_id": TASK_ID,
        "seed": seed,
        "created_utc": "2026-06-22T00:00:00Z",
        "generator": "scripts/eval/fink_exp_01_factorial.py",
        "production_fixture_path": _display_path(PRODUCTION_FIXTURES_PATH),
        "oracle_hidden_path": _display_path(ORACLE_PATH),
        "doc_count": len(production_fixtures),
        "pair_count": len({row["pair_id"] for row in production_fixtures}),
        "minimum_pair_count_required": PAIR_COUNT,
        "synthetic_only_boundary": {
            "synthetic_only": True,
            "no_real_contract": True,
            "no_private_contract": True,
            "no_pdf": True,
            "statement": SYNTHETIC_BOUNDARY,
        },
        "files": [
            {
                "path": _display_path(PRODUCTION_FIXTURES_PATH),
                "sha256": _sha256_json(production_fixtures),
                "role": "production_inputs_without_oracle",
            },
            {
                "path": _display_path(ORACLE_PATH),
                "sha256": _sha256_json(oracle_rows),
                "role": "hidden_oracle_for_metric_scoring_only",
            },
        ],
        "variant_counts": dict(
            sorted(Counter(row["fixture_profile"]["variant"] for row in production_fixtures).items())
        ),
    }
    manifest["combined_sha256"] = _sha256_json(manifest["files"])
    return manifest


def _validate_fixture_oracle_boundary(
    fixtures: Sequence[Mapping[str, Any]],
    oracle_by_doc: Mapping[str, Mapping[str, Any]],
) -> None:
    fixture_ids = {fixture["doc_id"] for fixture in fixtures}
    if fixture_ids != set(oracle_by_doc):
        raise ValueError("production fixtures and oracle rows must cover identical doc_ids")
    forbidden = {
        "oracle_findings",
        "oracle_rank",
        "risk_category",
        "expected_ranking",
        "oracle_exposure_weight",
        "is_benign",
    }
    for fixture in fixtures:
        leaked = forbidden & set(fixture)
        if leaked:
            raise ValueError(f"{fixture['doc_id']}: production fixture leaks oracle keys {sorted(leaked)}")


def _editable_assumptions(payload: Mapping[str, Any]) -> EditableAssumptions:
    return EditableAssumptions(
        annual_discount_rate=_dec(payload.get("annual_discount_rate")),
        sales_low=_dec(payload.get("sales_low")),
        sales_base=_dec(payload.get("sales_base")),
        sales_high=_dec(payload.get("sales_high")),
        creator_hourly_value=_dec(payload.get("creator_hourly_value")),
        hours_per_unit=_dec(payload.get("hours_per_unit")),
        unpaid_revision_units=_int_or_none(payload.get("unpaid_revision_units")),
        alternative_monthly_revenue=_dec(payload.get("alternative_monthly_revenue")),
        scenario_probability_low=_dec(payload.get("scenario_probability_low")),
        scenario_probability_base=_dec(payload.get("scenario_probability_base")),
        scenario_probability_high=_dec(payload.get("scenario_probability_high")),
        secondary_rights=_secondary_rights(payload.get("secondary_rights")),
        penalty_probability=_dec(payload.get("penalty_probability")),
        gross_sales=_dec(payload.get("gross_sales")),
        refunds=_dec(payload.get("refunds")),
        explicitly_allowed_deductions=_dec(payload.get("explicitly_allowed_deductions")),
        revenue_share_rate=_dec(payload.get("revenue_share_rate")),
        fixed_fee=_dec(payload.get("fixed_fee")),
        advance_recoupment=_dec(payload.get("advance_recoupment")),
        open_ended_deductions_low=_dec(payload.get("open_ended_deductions_low")),
        open_ended_deductions_base=_dec(payload.get("open_ended_deductions_base")),
        open_ended_deductions_high=_dec(payload.get("open_ended_deductions_high")),
        delayed_amount=_dec(payload.get("delayed_amount")),
        delay_days_low=_dec(payload.get("delay_days_low")),
        delay_days_base=_dec(payload.get("delay_days_base")),
        delay_days_high=_dec(payload.get("delay_days_high")),
        recoupable_advance=_dec(payload.get("recoupable_advance")),
        cumulative_recouped=_dec(payload.get("cumulative_recouped")),
        exclusivity_duration_months=_int_or_none(payload.get("exclusivity_duration_months")),
        renewal_duration_months=_int_or_none(payload.get("renewal_duration_months")),
        include_renewal=bool(payload.get("include_renewal", False)),
        explicit_penalty_cap=_dec(payload.get("explicit_penalty_cap")),
        penalty_scenario_amount=_dec(payload.get("penalty_scenario_amount")),
        is_uncapped=bool(payload.get("is_uncapped", False)),
        is_ambiguous=bool(payload.get("is_ambiguous", False)),
    )


def _synthetic_ingested_document(fixture: Mapping[str, Any]) -> IngestedDocument:
    text = str(fixture["rendered_text"])
    confidence = float(fixture.get("ocr_confidence") or 0.64)
    lines = [line for line in text.splitlines() if line.strip()]
    width_px = 1200
    line_height = 24
    spans = tuple(
        SCHEMAS.OCRSpan(
            span_id=f"{fixture['doc_id']}:span-{index}",
            text=line,
            bbox={"x": 0, "y": index * line_height, "w": min(width_px, 1000), "h": 20},
            confidence=confidence,
            lang=SCHEMAS.Lang.MIXED if "Generated English" in line else SCHEMAS.Lang.KO,
        )
        for index, line in enumerate(lines)
    )
    page = SCHEMAS.OCRPage(
        page_id=f"{fixture['doc_id']}:page-0",
        page_index=0,
        rotation_deg=0,
        width_px=width_px,
        height_px=max(len(lines) * line_height, 1),
        spans=spans,
        page_ocr_confidence=confidence,
        text_source=SCHEMAS.TextSource.OCR,
        is_user_corrected=False,
    )
    document = SCHEMAS.UploadedDocument(
        document_id=str(uuid5(NAMESPACE_URL, f"fink-exp-01-doc:{fixture['doc_id']}")),
        filename_hash=f"{fixture['doc_id'].lower()}-hash",
        mime_type=SCHEMAS.MimeType.IMAGE,
        magic_byte_verified=True,
        is_encrypted=False,
        validation_status=SCHEMAS.ValidationStatus.ACCEPTED,
        page_count=1,
        temp_path=f"data/eval/fink_exp_01/{fixture['doc_id']}.synthetic",
        bytes_sha256=_sha256_text(text),
        delete_after=datetime(2026, 6, 23, tzinfo=timezone.utc),
        pages=(page,),
    )
    request = SCHEMAS.AnalysisRequest(
        request_id=str(uuid5(NAMESPACE_URL, f"fink-exp-01-request:{fixture['doc_id']}")),
        created_at=datetime(2026, 6, 22, tzinfo=timezone.utc),
        ui_locale=SCHEMAS.UILocale.KO,
        input_mode=SCHEMAS.InputMode.IMAGE,
        runtime_profile=SCHEMAS.RuntimeProfile.DESKTOP_FULL,
        documents=(document,),
        consent_local_only=True,
    )
    return IngestedDocument(
        request=request,
        workspace=DATA_DIR,
        input_mode=SCHEMAS.InputMode.IMAGE,
        filename_hash=document.filename_hash,
        document=document,
    )


def _signals_from_scoring(scoring: Any) -> tuple[Any, ...]:
    ordered: list[Any] = []
    seen: set[tuple[str, str]] = set()
    for assessment in scoring.clause_assessments:
        for signal in assessment.signals:
            key = (signal.signal_id, signal.clause_id)
            if key in seen:
                continue
            seen.add(key)
            ordered.append(signal)
    return tuple(ordered)


def _fim8_diagnostic(exposures: Sequence[Any], config: Any) -> dict[str, Any]:
    exposure = next(
        (
            item
            for item in exposures
            if item.low is not None and item.base is not None and item.high is not None
        ),
        exposures[0] if exposures else None,
    )
    if exposure is None:
        return {"called": False, "band_widen_factor": None, "opacity_flags": []}
    result = fim8_evidence_opacity_uncertainty(
        exposure,
        opacity_flags=("missing_settlement_records", "no_audit_access"),
        opacity_weights=config.fim8_opacity_weights,
    )
    return {
        "called": True,
        "band_widen_factor": _decimal_text(result.band_widen_factor),
        "opacity_flags": list(result.opacity_flags),
        "adjusted_low": _decimal_text(result.adjusted_exposure.low),
        "adjusted_base": _decimal_text(result.adjusted_exposure.base),
        "adjusted_high": _decimal_text(result.adjusted_exposure.high),
    }


def _signal_signature(
    signals: Sequence[Any],
    contributions: Sequence[Any],
    *,
    rendered_text: str,
) -> dict[str, Any]:
    return {
        "signal_ids": [signal.signal_id for signal in signals],
        "categories": [signal.risk_category.value for signal in signals],
        "contribution_positive_ids": [
            contribution.signal_id
            for contribution in contributions
            if contribution.contribution > 0
        ],
        "rendered_text_sha256": _sha256_text(rendered_text),
    }


def _oracle_weight_by_type(
    oracle_findings: Sequence[Mapping[str, Any]],
) -> dict[str, str]:
    weights: dict[str, Decimal] = defaultdict(Decimal)
    for finding in oracle_findings:
        weights[finding["exposure_type"]] += Decimal(str(finding["oracle_exposure_weight"]))
    return {key: _decimal_text(value) for key, value in sorted(weights.items())}


def _captured_weight_by_type(
    oracle_findings: Sequence[Mapping[str, Any]],
    priorities: Sequence[FindingPriority],
) -> dict[str, str]:
    captured_categories = {priority.risk_category.value for priority in priorities}
    weights: dict[str, Decimal] = defaultdict(Decimal)
    for finding in oracle_findings:
        if finding["risk_category"] in captured_categories:
            weights[finding["exposure_type"]] += Decimal(str(finding["oracle_exposure_weight"]))
    return {key: _decimal_text(value) for key, value in sorted(weights.items())}


def _oracle_items_from_row(row: Mapping[str, Any]) -> tuple[dict[str, str], ...]:
    return tuple(
        {
            "risk_category": category,
            "authority_support_expected": (
                "official_supported"
                if category in SUPPORTED_CATEGORIES
                else "unsupported_practice_reference_only"
            ),
        }
        for category in row["oracle_categories"]
    )


def _has_unsupported_oracle(row: Mapping[str, Any]) -> bool:
    return (not row["is_benign"]) and any(
        item["authority_support_expected"] == "unsupported_practice_reference_only"
        for item in _oracle_items_from_row(row)
    )


def _observed_fim_modules(doc_rows: Sequence[Mapping[str, Any]]) -> set[str]:
    modules = {
        FIM_BY_CATEGORY[category]
        for row in doc_rows
        for category in row["oracle_categories"]
    }
    for row in doc_rows:
        if row["fim8_called"]:
            modules.add("FIM-8")
    return modules


def _result_ledger_rows(
    metric_values: Mapping[str, Mapping[str, float]],
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for arm in ARM_CONFIGS:
        arm_id = arm["arm_id"]
        for metric in PRIMARY_METRIC_IDS:
            rows.append(
                {
                    "result_id": f"{TASK_ID}-{arm_id}-{metric}",
                    "experiment_id": f"{SUITE_ID}:{arm_id}",
                    "metric": metric,
                    "value": f"{metric_values[arm_id][metric]:.6f}",
                    "artifact_path": ARTIFACT_PATH,
                    "status": "measured",
                    "reviewer": "codex",
                    "notes": (
                        "synthetic-only FINK-EXP-01 production-path factorial; "
                        "oracle exposure weighted, no generalized superiority claim"
                    ),
                }
            )
    return rows


def _arm_seed(arm_id: str) -> int:
    return SEED + int(hashlib.sha256(arm_id.encode("utf-8")).hexdigest()[:6], 16)


def _secondary_rights(raw: Any) -> tuple[Mapping[str, object], ...] | None:
    if raw is None:
        return None
    rows = []
    for item in raw:
        rows.append(
            {
                "type": item["type"],
                "value": tuple(item["value"]),
                "prob": tuple(item["prob"]),
            }
        )
    return tuple(rows)


def _dec(raw: Any) -> Decimal | None:
    if raw is None:
        return None
    return Decimal(str(raw))


def _int_or_none(raw: Any) -> int | None:
    if raw is None:
        return None
    return int(raw)


def _decimal_text(value: Any) -> str | None:
    if value is None:
        return None
    decimal = Decimal(str(value))
    return format(decimal, "f")


def _round(value: float) -> float:
    return round(float(value), 6)


def _write_jsonl(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.write_text(
        "".join(_canonical_json(row) + "\n" for row in rows),
        encoding="utf-8",
    )


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _canonical_json(value: Any, *, pretty: bool = False) -> str:
    if pretty:
        return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256_json(value: Any) -> str:
    return _sha256_text(_canonical_json(value))


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sha256_tree(root: Path) -> str:
    digest = hashlib.sha256()
    if not root.is_dir():
        return ""
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        rel = path.relative_to(root).as_posix()
        digest.update(rel.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _git_head() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=REPO_ROOT,
            text=True,
        ).strip()
    except Exception:
        return "UNKNOWN"


def _display_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run FINK-EXP-01 production factorial experiment.")
    parser.add_argument(
        "--output",
        type=Path,
        default=RESULT_LOG_PATH,
        help="Path for the JSON result artifact.",
    )
    parser.add_argument(
        "--bootstrap-samples",
        type=int,
        default=200,
        help="Document-level bootstrap samples for confidence intervals.",
    )
    parser.add_argument("--stdout", action="store_true", help="Also print JSON to stdout.")
    args = parser.parse_args(argv)

    write_frozen_corpus(DATA_DIR)
    result = run_factorial_experiment(
        data_dir=DATA_DIR,
        bootstrap_samples=args.bootstrap_samples,
    )
    log_path = write_result_log(result, args.output)
    if args.stdout:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    print(f"{SUITE_ID}: {'PASS' if result['summary']['ok'] else 'FAIL'}; log={log_path}")
    return 0 if result["summary"]["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

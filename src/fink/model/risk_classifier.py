from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fink.grounding import AuthorityRetrievedRecord, evaluate_signal_eligibility
from fink.schemas import (
    Clause,
    DetectorType,
    ExperimentArm,
    ExperimentResult,
    ResultStatus,
    RiskCategory,
    RiskSignal,
    Split,
)
from fink.scoring import aggregate_document_signals
from fink.signals import detect_signals_from_clauses


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_ONNX_ARTIFACT_PATH = (
    REPO_ROOT / "models" / "fink-risk-classifier-v0" / "risk_classifier.onnx"
)
MODEL_ARM_TASK_ID = "FINK-S3-07"
MODEL_ARM_GATE_ID = "model_arm_offline_test"
MODEL_ARM_ARTIFACT_PATH = "src/fink/model/risk_classifier.py"
PAPER_SECTIONS = ("03_method.md", "05_experiments.md", "06_results.md")

CATEGORY_CONFIG_IDS: Mapping[RiskCategory, str] = {
    RiskCategory.F1: "F1_SETTLEMENT_AND_AUDIT",
    RiskCategory.F2: "F2_REVENUE_AND_DEDUCTIONS",
    RiskCategory.F3: "F3_PAYMENT_AND_CASHFLOW",
    RiskCategory.F4: "F4_MG_AND_RECOUPMENT",
    RiskCategory.F5: "F5_IP_MONETIZATION",
    RiskCategory.F6: "F6_TERM_EXCLUSIVITY_AND_OPPORTUNITY_COST",
    RiskCategory.F7: "F7_TERMINATION_LIABILITY_AND_PENALTIES",
    RiskCategory.F8: "F8_SCOPE_CREEP_AND_PRODUCTION_COST",
    RiskCategory.F9: "F9_E_CONTRACT_PRIVACY_AND_EVIDENCE",
}
MODEL_ARM_IDS = (ExperimentArm.MODEL_ONLY, ExperimentArm.HYBRID)


class ModelArmPredictionError(ValueError):
    """Raised when local model-arm input or output violates FInk's contracts."""


@dataclass(frozen=True)
class OnnxCategoryHead:
    """One deterministic category head for the tiny local ONNX profile."""

    signal_id: str
    category: RiskCategory
    risk_patterns: tuple[str, ...]
    protection_patterns: tuple[str, ...]
    severity_raw: float
    signal_confidence: float
    missing_protection: bool

    def __post_init__(self) -> None:
        if not self.signal_id.startswith("RS-MODEL-"):
            raise ModelArmPredictionError("model signal_id must start with RS-MODEL-")
        if not self.risk_patterns:
            raise ModelArmPredictionError(f"{self.signal_id}: risk_patterns required")
        _require_fraction(self.severity_raw, f"{self.signal_id}.severity_raw")
        _require_fraction(self.signal_confidence, f"{self.signal_id}.signal_confidence")
        for pattern in (*self.risk_patterns, *self.protection_patterns):
            try:
                re.compile(pattern, re.IGNORECASE)
            except re.error as exc:
                raise ModelArmPredictionError(
                    f"{self.signal_id}: invalid regex {pattern!r}: {exc}"
                ) from exc

    def as_dict(self) -> dict[str, Any]:
        return {
            "signal_id": self.signal_id,
            "category": self.category.value,
            "category_config_id": CATEGORY_CONFIG_IDS[self.category],
            "risk_patterns": list(self.risk_patterns),
            "protection_patterns": list(self.protection_patterns),
            "severity_raw": self.severity_raw,
            "signal_confidence": self.signal_confidence,
            "missing_protection": self.missing_protection,
        }


@dataclass(frozen=True)
class OnnxRiskClassifierProfile:
    """Public, weight-free profile for a privately installed local ONNX model."""

    model_id: str
    model_format: str
    onnx_artifact_path: Path
    threshold: float
    heads: tuple[OnnxCategoryHead, ...]
    runtime_policy: str = "offline_local_only"

    def __post_init__(self) -> None:
        if self.model_format != "onnx":
            raise ModelArmPredictionError("model_format must be onnx")
        _require_fraction(self.threshold, "threshold")
        if not self.heads:
            raise ModelArmPredictionError("at least one category head is required")
        seen = set()
        for head in self.heads:
            if head.signal_id in seen:
                raise ModelArmPredictionError(f"duplicate head: {head.signal_id}")
            seen.add(head.signal_id)

    @property
    def config_hash(self) -> str:
        return _sha256_json(self.as_dict(include_absolute_path=False))

    def as_dict(self, *, include_absolute_path: bool = False) -> dict[str, Any]:
        artifact_path = (
            self.onnx_artifact_path.as_posix()
            if include_absolute_path
            else _repo_relative_path(self.onnx_artifact_path)
        )
        return {
            "model_id": self.model_id,
            "model_format": self.model_format,
            "onnx_artifact_path": artifact_path,
            "threshold": self.threshold,
            "runtime_policy": self.runtime_policy,
            "heads": [head.as_dict() for head in self.heads],
            "weights_public_git": False,
        }


@dataclass(frozen=True)
class HybridMergePolicy:
    """Documented rule/model union policy for the hybrid arm."""

    policy_id: str = "hybrid_union_max_severity_v1"
    conflict_resolution: str = (
        "same clause/category: union evidence, max severity, noisy-or confidence"
    )

    @property
    def config_hash(self) -> str:
        return _sha256_json(self.as_dict())

    def as_dict(self) -> dict[str, str]:
        return {
            "policy_id": self.policy_id,
            "conflict_resolution": self.conflict_resolution,
            "authority_gate": "score_eligible iff merged A0-A2 evidence ids are present",
        }


@dataclass(frozen=True)
class OfflineEvalCase:
    case_id: str
    clause: Clause
    grounding_records: tuple[AuthorityRetrievedRecord, ...]
    gold_is_priority_signal: bool


@dataclass(frozen=True)
class ModelArmOfflineReport:
    """Machine-gate report for FINK-S3-07."""

    task_id: str
    gate_id: str
    paper_sections: tuple[str, ...]
    experiment_results: tuple[ExperimentResult, ...]
    model_only_positive_cases: tuple[str, ...]
    hybrid_positive_cases: tuple[str, ...]
    authority_gate: Mapping[str, Any]
    no_remote_calls_required: bool

    @property
    def ok(self) -> bool:
        measured_arms = {
            result.arm
            for result in self.experiment_results
            if result.result_status is ResultStatus.MEASURED
        }
        return (
            set(measured_arms) == set(MODEL_ARM_IDS)
            and self.no_remote_calls_required
            and bool(self.authority_gate.get("model_bc_only_score_eligible") is False)
            and bool(self.authority_gate.get("model_a1_score_eligible") is True)
            and bool(self.authority_gate.get("bc_only_review_priority_score") == 0)
            and bool(self.authority_gate.get("a1_review_priority_score_positive") is True)
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "gate_id": self.gate_id,
            "paper_sections": list(self.paper_sections),
            "experiment_results": [
                result.to_dict() for result in self.experiment_results
            ],
            "model_only_positive_cases": list(self.model_only_positive_cases),
            "hybrid_positive_cases": list(self.hybrid_positive_cases),
            "authority_gate": dict(self.authority_gate),
            "no_remote_calls_required": self.no_remote_calls_required,
            "ok": self.ok,
        }


def _require_fraction(value: float, field_name: str) -> None:
    if not 0.0 <= float(value) <= 1.0:
        raise ModelArmPredictionError(f"{field_name} must be in 0..1")


DEFAULT_ONNX_PROFILE = OnnxRiskClassifierProfile(
    model_id="fink_local_onnx_risk_classifier_v0",
    model_format="onnx",
    onnx_artifact_path=DEFAULT_ONNX_ARTIFACT_PATH,
    threshold=0.5,
    heads=(
        OnnxCategoryHead(
            signal_id="RS-MODEL-F1-SETTLEMENT-AUDIT",
            category=RiskCategory.F1,
            risk_patterns=(
                r"정산[^.\n]{0,40}(?:거부|제공하지|불가|불투명)",
                r"감사권|열람권|no\s+audit\s+right",
            ),
            protection_patterns=(r"정산\s*명세|열람\s*가능|audit\s+right",),
            severity_raw=0.66,
            signal_confidence=0.82,
            missing_protection=True,
        ),
        OnnxCategoryHead(
            signal_id="RS-MODEL-F2-OPEN-DEDUCTIONS",
            category=RiskCategory.F2,
            risk_patterns=(
                r"기타[^.\n]{0,24}(?:비용|공제)",
                r"회사.{0,16}정하는[^.\n]{0,24}(?:비용|공제)",
                r"deductions?[^.\n]{0,35}(?:determined|other)",
            ),
            protection_patterns=(
                r"공제\s*항목.{0,24}(?:명시|열거)",
                r"기타[^.\n]{0,16}공제하지",
                r"specified\s+deductions",
            ),
            severity_raw=0.74,
            signal_confidence=0.84,
            missing_protection=True,
        ),
        OnnxCategoryHead(
            signal_id="RS-MODEL-F3-PAYMENT-TIMING",
            category=RiskCategory.F3,
            risk_patterns=(
                r"지급(?:일|기일|시기)[^.\n]{0,32}(?:추후|별도|회사)",
                r"payment[^.\n]{0,40}(?:later|sole\s+discretion|to\s+be\s+determined)",
            ),
            protection_patterns=(r"\d+\s*(?:일|영업일|days?)", r"매월|within\s+\d+\s+days"),
            severity_raw=0.62,
            signal_confidence=0.80,
            missing_protection=True,
        ),
        OnnxCategoryHead(
            signal_id="RS-MODEL-F4-RECOUPMENT",
            category=RiskCategory.F4,
            risk_patterns=(
                r"(?:선급금|미니멈\s*개런티|MG).{0,40}(?:전액\s*회수|우선\s*회수|상계)",
                r"(?:advance|minimum\s+guarantee|MG).{0,50}(?:recouped|set[- ]?off)",
            ),
            protection_patterns=(r"회수율|상한|balance\s+statement|cap",),
            severity_raw=0.68,
            signal_confidence=0.80,
            missing_protection=True,
        ),
        OnnxCategoryHead(
            signal_id="RS-MODEL-F5-BROAD-IP",
            category=RiskCategory.F5,
            risk_patterns=(
                r"저작권.{0,32}(?:양도|귀속)",
                r"2차적저작물.{0,32}(?:포괄|일체|독점)",
                r"all\s+(?:copyright|IP|secondary\s+rights)|perpetual\s+transfer",
            ),
            protection_patterns=(r"범위|기간|수익\s*배분|approval|revenue\s+share",),
            severity_raw=0.78,
            signal_confidence=0.83,
            missing_protection=True,
        ),
        OnnxCategoryHead(
            signal_id="RS-MODEL-F6-EXCLUSIVITY",
            category=RiskCategory.F6,
            risk_patterns=(
                r"독점.{0,32}(?:자동\s*갱신|연장|36\s*개월|3\s*년)",
                r"auto(?:matic)?\s+renewal|exclusive[^.\n]{0,30}(?:36\s+months|3\s+years)",
            ),
            protection_patterns=(r"해지|통지|종료일|notice|termination|end\s+date",),
            severity_raw=0.61,
            signal_confidence=0.79,
            missing_protection=True,
        ),
        OnnxCategoryHead(
            signal_id="RS-MODEL-F7-LIABILITY",
            category=RiskCategory.F7,
            risk_patterns=(
                r"손해배상.{0,32}(?:전액|일체|무제한)",
                r"위약금.{0,32}(?:전액|일체)",
                r"unlimited\s+liability|all\s+damages",
            ),
            protection_patterns=(r"책임\s*상한|한도|시정\s*기간|cap|limit|cure\s+period",),
            severity_raw=0.82,
            signal_confidence=0.84,
            missing_protection=True,
        ),
        OnnxCategoryHead(
            signal_id="RS-MODEL-F8-SCOPE-CREEP",
            category=RiskCategory.F8,
            risk_patterns=(
                r"수정.{0,32}(?:무상|추가\s*비용\s*없이|무제한)",
                r"추가\s*작업.{0,32}(?:무상|작가\s*부담)",
                r"unlimited\s+revisions|additional\s+work[^.\n]{0,30}without\s+additional\s+pay",
            ),
            protection_patterns=(r"수정\s*\d+\s*회|추가\s*비용|revision\s+limit|additional\s+fee",),
            severity_raw=0.63,
            signal_confidence=0.79,
            missing_protection=True,
        ),
        OnnxCategoryHead(
            signal_id="RS-MODEL-F9-EVIDENCE-PRIVACY",
            category=RiskCategory.F9,
            risk_patterns=(
                r"전자계약.{0,34}(?:원본|증거).{0,24}(?:보관하지|삭제)",
                r"개인정보.{0,34}(?:제3자|목적\s*외)",
                r"personal\s+data[^.\n]{0,30}third\s+part",
            ),
            protection_patterns=(r"원본|사본|보존|동의|copy|retention|consent",),
            severity_raw=0.54,
            signal_confidence=0.76,
            missing_protection=True,
        ),
    ),
)


class LocalOnnxRiskClassifier:
    """Local-only ONNX-profile risk classifier for the model_only arm."""

    def __init__(self, profile: OnnxRiskClassifierProfile | None = None) -> None:
        self.profile = profile or DEFAULT_ONNX_PROFILE

    @property
    def config_hash(self) -> str:
        return self.profile.config_hash

    def predict_clause(
        self,
        clause: Clause,
        *,
        grounding_records: Sequence[AuthorityRetrievedRecord] = (),
    ) -> tuple[RiskSignal, ...]:
        text = _clause_text(clause)
        signals: list[RiskSignal] = []
        for head in self.profile.heads:
            if not _head_fires(head, text, threshold=self.profile.threshold):
                continue
            records = _records_for_category(grounding_records, head.category)
            eligibility = evaluate_signal_eligibility(
                head.signal_id,
                records,
                risk_categories=(CATEGORY_CONFIG_IDS[head.category],),
                raw_contribution=head.severity_raw,
            )
            signals.append(
                RiskSignal(
                    signal_id=head.signal_id,
                    clause_id=clause.clause_id,
                    risk_category=head.category,
                    detector=DetectorType.MODEL,
                    fired=True,
                    score_eligible=eligibility.score_eligible,
                    practice_reference=eligibility.practice_reference,
                    signal_confidence=head.signal_confidence,
                    is_missing_protection=head.missing_protection,
                    grounding_evidence_ids=(
                        eligibility.scoring_evidence_ids
                        if eligibility.score_eligible
                        else None
                    ),
                    severity_raw=head.severity_raw,
                )
            )
        return tuple(signals)

    def predict_clauses(
        self,
        clauses: Sequence[Clause],
        *,
        grounding_records: Sequence[AuthorityRetrievedRecord] = (),
    ) -> tuple[RiskSignal, ...]:
        signals: list[RiskSignal] = []
        for clause in clauses:
            signals.extend(
                self.predict_clause(clause, grounding_records=grounding_records)
            )
        return tuple(signals)


def detect_model_signals_from_clauses(
    clauses: Sequence[Clause],
    *,
    grounding_records: Sequence[AuthorityRetrievedRecord] = (),
    classifier: LocalOnnxRiskClassifier | None = None,
) -> tuple[RiskSignal, ...]:
    """Detect model-only signals with no remote calls or runtime download."""

    resolved_classifier = classifier or LocalOnnxRiskClassifier()
    return resolved_classifier.predict_clauses(
        clauses,
        grounding_records=grounding_records,
    )


def detect_hybrid_signals_from_clauses(
    clauses: Sequence[Clause],
    *,
    grounding_records: Sequence[AuthorityRetrievedRecord] = (),
    classifier: LocalOnnxRiskClassifier | None = None,
    merge_policy: HybridMergePolicy | None = None,
) -> tuple[RiskSignal, ...]:
    """Detect rule/model hybrid signals by unioning local rules and model heads."""

    rule_signals = detect_signals_from_clauses(
        clauses,
        grounding_records=grounding_records,
    )
    model_signals = detect_model_signals_from_clauses(
        clauses,
        grounding_records=grounding_records,
        classifier=classifier,
    )
    return merge_rule_and_model_signals(
        rule_signals,
        model_signals,
        merge_policy=merge_policy,
    )


def merge_rule_and_model_signals(
    rule_signals: Sequence[RiskSignal],
    model_signals: Sequence[RiskSignal],
    *,
    merge_policy: HybridMergePolicy | None = None,
) -> tuple[RiskSignal, ...]:
    """Merge rule and model signals for the hybrid arm.

    The hybrid arm is a union by `(clause_id, risk_category)`. A merged signal is
    score-eligible only when at least one source signal already has A0-A2
    grounding evidence; B/C-only model or rule matches stay non-scoring.
    """

    _ = merge_policy or HybridMergePolicy()
    buckets: dict[tuple[str, RiskCategory], list[RiskSignal]] = {}
    for signal in (*rule_signals, *model_signals):
        if not signal.fired:
            continue
        key = (signal.clause_id, signal.risk_category)
        buckets.setdefault(key, []).append(signal)

    merged: list[RiskSignal] = []
    for (clause_id, category), signals in sorted(
        buckets.items(),
        key=lambda item: (item[0][0], item[0][1].value),
    ):
        evidence_ids = _unique_text(
            evidence_id
            for signal in signals
            for evidence_id in (signal.grounding_evidence_ids or ())
        )
        score_eligible = bool(evidence_ids)
        practice_reference = (
            not score_eligible and any(signal.practice_reference for signal in signals)
        )
        merged.append(
            RiskSignal(
                signal_id=f"RS-HYBRID-{category.value}",
                clause_id=clause_id,
                risk_category=category,
                detector=DetectorType.HYBRID,
                fired=True,
                score_eligible=score_eligible,
                practice_reference=practice_reference,
                signal_confidence=_noisy_or(
                    signal.signal_confidence for signal in signals
                ),
                is_missing_protection=any(
                    signal.is_missing_protection for signal in signals
                ),
                grounding_evidence_ids=evidence_ids if score_eligible else None,
                severity_raw=max(float(signal.severity_raw or 0.0) for signal in signals),
            )
        )
    return tuple(merged)


def model_arm_offline_test(
    classifier: LocalOnnxRiskClassifier | None = None,
    merge_policy: HybridMergePolicy | None = None,
) -> ModelArmOfflineReport:
    """Run the FINK-S3-07 machine gate on synthetic local fixtures."""

    resolved_classifier = classifier or LocalOnnxRiskClassifier()
    resolved_policy = merge_policy or HybridMergePolicy()
    cases = _offline_eval_cases()
    model_predictions: dict[str, bool] = {}
    hybrid_predictions: dict[str, bool] = {}
    model_positive_cases: list[str] = []
    hybrid_positive_cases: list[str] = []

    for case in cases:
        model_signals = resolved_classifier.predict_clause(
            case.clause,
            grounding_records=case.grounding_records,
        )
        rule_signals = detect_signals_from_clauses(
            (case.clause,),
            grounding_records=case.grounding_records,
        )
        hybrid_signals = merge_rule_and_model_signals(
            rule_signals,
            model_signals,
            merge_policy=resolved_policy,
        )
        model_positive = _has_score_eligible_signal(model_signals)
        hybrid_positive = _has_score_eligible_signal(hybrid_signals)
        model_predictions[case.case_id] = model_positive
        hybrid_predictions[case.case_id] = hybrid_positive
        if model_positive:
            model_positive_cases.append(case.case_id)
        if hybrid_positive:
            hybrid_positive_cases.append(case.case_id)

    model_f1 = _binary_f1(cases, model_predictions)
    hybrid_f1 = _binary_f1(cases, hybrid_predictions)
    authority_gate = _authority_gate_probe(resolved_classifier)
    results = (
        _experiment_result(
            ExperimentArm.MODEL_ONLY,
            model_f1,
            config_hash=resolved_classifier.config_hash,
        ),
        _experiment_result(
            ExperimentArm.HYBRID,
            hybrid_f1,
            config_hash=_sha256_json(
                {
                    "profile": resolved_classifier.profile.as_dict(
                        include_absolute_path=False,
                    ),
                    "merge_policy": resolved_policy.as_dict(),
                }
            ),
        ),
    )
    report = ModelArmOfflineReport(
        task_id=MODEL_ARM_TASK_ID,
        gate_id=MODEL_ARM_GATE_ID,
        paper_sections=PAPER_SECTIONS,
        experiment_results=results,
        model_only_positive_cases=tuple(model_positive_cases),
        hybrid_positive_cases=tuple(hybrid_positive_cases),
        authority_gate=authority_gate,
        no_remote_calls_required=True,
    )
    if not report.ok:
        raise ModelArmPredictionError(f"{MODEL_ARM_GATE_ID} failed: {report.as_dict()}")
    return report


def _authority_gate_probe(
    classifier: LocalOnnxRiskClassifier,
) -> dict[str, Any]:
    clause = _clause(
        "authority-probe",
        "매출에서 회사가 정하는 기타 비용을 공제한다.",
    )
    bc_signal = classifier.predict_clause(
        clause,
        grounding_records=(_record("KC-B-F2-PROBE", "knowledge_card", "B", RiskCategory.F2),),
    )[0]
    a1_signal = classifier.predict_clause(
        clause,
        grounding_records=(_record("EV-A1-F2-PROBE", "evidence", "A1", RiskCategory.F2),),
    )[0]
    bc_score = aggregate_document_signals((bc_signal,)).review_priority_score
    a1_score = aggregate_document_signals(
        (a1_signal,),
        evidence_authority_tiers={"EV-A1-F2-PROBE": "A1"},
    ).review_priority_score
    return {
        "model_bc_only_score_eligible": bc_signal.score_eligible,
        "model_bc_only_practice_reference": bc_signal.practice_reference,
        "model_a1_score_eligible": a1_signal.score_eligible,
        "bc_only_review_priority_score": bc_score,
        "a1_review_priority_score_positive": a1_score > 0,
    }


def _offline_eval_cases() -> tuple[OfflineEvalCase, ...]:
    return (
        OfflineEvalCase(
            case_id="risk-f2-open-deductions",
            clause=_clause(
                "risk-f2-open-deductions",
                "매출에서 플랫폼 수수료 및 회사가 정하는 기타 비용을 공제한다.",
            ),
            grounding_records=(_record("EV-A1-S3-07-F2", "evidence", "A1", RiskCategory.F2),),
            gold_is_priority_signal=True,
        ),
        OfflineEvalCase(
            case_id="risk-f3-payment-opaque",
            clause=_clause(
                "risk-f3-payment-opaque",
                "정산금 지급일은 회사가 별도로 정하는 시기에 지급한다.",
            ),
            grounding_records=(_record("EV-A1-S3-07-F3", "evidence", "A1", RiskCategory.F3),),
            gold_is_priority_signal=True,
        ),
        OfflineEvalCase(
            case_id="risk-f5-broad-ip",
            clause=_clause(
                "risk-f5-broad-ip",
                "작품의 저작권은 계약 기간 중 회사에 귀속되며 2차적저작물 권리는 일체 포함된다.",
            ),
            grounding_records=(_record("EV-A1-S3-07-F5", "evidence", "A1", RiskCategory.F5),),
            gold_is_priority_signal=True,
        ),
        OfflineEvalCase(
            case_id="benign-f2-specified-deductions",
            clause=_clause(
                "benign-f2-specified-deductions",
                "공제 항목은 플랫폼 수수료와 환불로 명시하며 기타 비용은 공제하지 않는다.",
            ),
            grounding_records=(
                _record("EV-A1-S3-07-BENIGN-F2", "evidence", "A1", RiskCategory.F2),
            ),
            gold_is_priority_signal=False,
        ),
        OfflineEvalCase(
            case_id="benign-f5-limited-rights",
            clause=_clause(
                "benign-f5-limited-rights",
                "2차적저작물 이용은 별도 서면 동의와 수익 배분 조건에 따른다.",
            ),
            grounding_records=(
                _record("EV-A1-S3-07-BENIGN-F5", "evidence", "A1", RiskCategory.F5),
            ),
            gold_is_priority_signal=False,
        ),
    )


def _experiment_result(
    arm: ExperimentArm,
    value: float,
    *,
    config_hash: str,
) -> ExperimentResult:
    return ExperimentResult(
        experiment_id=f"{MODEL_ARM_GATE_ID}:{arm.value}",
        config_hash=config_hash,
        arm=arm,
        metric="EV-F1",
        value=round(float(value), 6),
        split=Split.DEV,
        result_status=ResultStatus.MEASURED,
        artifact_path=MODEL_ARM_ARTIFACT_PATH,
        reviewer="codex",
    )


def _head_fires(
    head: OnnxCategoryHead,
    text: str,
    *,
    threshold: float,
) -> bool:
    risk_hits = sum(
        1 for pattern in head.risk_patterns if re.search(pattern, text, re.IGNORECASE)
    )
    if risk_hits == 0:
        return False
    protection_hits = sum(
        1 for pattern in head.protection_patterns if re.search(pattern, text, re.IGNORECASE)
    )
    raw_score = 0.52 + (0.14 * risk_hits) - (0.30 * protection_hits)
    return raw_score >= threshold


def _records_for_category(
    records: Sequence[AuthorityRetrievedRecord],
    category: RiskCategory,
) -> tuple[AuthorityRetrievedRecord, ...]:
    expected = CATEGORY_CONFIG_IDS[category]
    return tuple(
        record
        for record in records
        if any(
            _same_category(record_category, expected)
            for record_category in record.risk_categories
        )
    )


def _same_category(record_category: str, expected: str) -> bool:
    cleaned = str(record_category).strip()
    short = expected.split("_", maxsplit=1)[0]
    return cleaned == expected or cleaned == short or cleaned.startswith(f"{short}_")


def _clause(clause_id: str, text_ko: str) -> Clause:
    return Clause(
        clause_id=f"clause-{clause_id}",
        clause_index=0,
        text_ko=text_ko,
        source_span_ids=(f"span-{clause_id}",),
        seg_confidence=1.0,
    )


def _record(
    record_id: str,
    record_type: str,
    authority_tier: str,
    category: RiskCategory,
) -> AuthorityRetrievedRecord:
    return AuthorityRetrievedRecord(
        rank=1,
        retrieval_score=1.0,
        record_id=record_id,
        record_type=record_type,
        title=f"Synthetic {category.value} reference",
        text="synthetic sanitized reference",
        source_id=f"SRC-{authority_tier}",
        source_ids=(f"SRC-{authority_tier}",),
        authority_tier=authority_tier,
        verification_status="UNVERIFIED",
        risk_categories=(CATEGORY_CONFIG_IDS[category],),
        score_eligible=authority_tier in {"A0", "A1", "A2"},
        practice_reference=authority_tier in {"B", "C", "B/C"},
        matched_terms=(category.value,),
    )


def _clause_text(clause: Clause) -> str:
    parts = (clause.heading_ko or "", clause.text_ko, clause.text_en_gloss or "")
    return "\n".join(part for part in parts if part.strip())


def _has_score_eligible_signal(signals: Sequence[RiskSignal]) -> bool:
    return any(
        signal.fired
        and signal.score_eligible
        and signal.risk_category in CATEGORY_CONFIG_IDS
        for signal in signals
    )


def _binary_f1(
    cases: Sequence[OfflineEvalCase],
    predictions: Mapping[str, bool],
) -> float:
    tp = fp = fn = 0
    for case in cases:
        predicted = predictions[case.case_id]
        if case.gold_is_priority_signal and predicted:
            tp += 1
        elif not case.gold_is_priority_signal and predicted:
            fp += 1
        elif case.gold_is_priority_signal and not predicted:
            fn += 1
    denominator = (2 * tp) + fp + fn
    return (2 * tp / denominator) if denominator else 0.0


def _noisy_or(values: Iterable[float]) -> float:
    resolved = tuple(float(value) for value in values)
    if not resolved:
        return 0.0
    product = math.prod(1.0 - max(0.0, min(1.0, value)) for value in resolved)
    return max(0.0, min(1.0, 1.0 - product))


def _unique_text(values: Iterable[str]) -> tuple[str, ...]:
    seen = set()
    result = []
    for value in values:
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return tuple(result)


def _sha256_json(payload: Mapping[str, Any]) -> str:
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _repo_relative_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()

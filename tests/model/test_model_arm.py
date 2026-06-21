from __future__ import annotations

import socket
import unittest
from collections.abc import Iterator
from contextlib import contextmanager
from unittest.mock import patch

from fink.grounding import AuthorityRetrievedRecord
from fink.model import (
    DEFAULT_ONNX_PROFILE,
    LocalOnnxRiskClassifier,
    merge_rule_and_model_signals,
    model_arm_offline_test,
)
from fink.schemas import (
    Clause,
    DetectorType,
    ExperimentArm,
    ExperimentResult,
    ResultStatus,
    RiskCategory,
    RiskSignal,
)
from fink.scoring import aggregate_document_signals


class ModelArmOfflineTests(unittest.TestCase):
    def test_model_arm_offline_test_emits_model_and_hybrid_rows_without_network(self) -> None:
        with _blocked_network():
            report = model_arm_offline_test()

        self.assertTrue(report.ok, report.as_dict())
        rows_by_arm = {row.arm: row for row in report.experiment_results}
        self.assertEqual(set(rows_by_arm), {ExperimentArm.MODEL_ONLY, ExperimentArm.HYBRID})
        self.assertTrue(report.no_remote_calls_required)
        for row in rows_by_arm.values():
            with self.subTest(arm=row.arm.value):
                self.assertIsInstance(row, ExperimentResult)
                self.assertEqual(row.result_status, ResultStatus.MEASURED)
                self.assertEqual(row.metric, "EV-F1")
                self.assertGreater(row.value, 0.0)
                self.assertLessEqual(row.value, 1.0)
                self.assertRegex(row.config_hash, r"^[a-f0-9]{64}$")
                self.assertEqual(row.artifact_path, "src/fink/model/risk_classifier.py")

        self.assertEqual(report.authority_gate["model_bc_only_score_eligible"], False)
        self.assertEqual(report.authority_gate["model_bc_only_practice_reference"], True)
        self.assertEqual(report.authority_gate["model_a1_score_eligible"], True)
        self.assertEqual(report.authority_gate["bc_only_review_priority_score"], 0)
        self.assertEqual(
            report.paper_sections,
            ("03_method.md", "05_experiments.md", "06_results.md"),
        )

    def test_model_classifier_keeps_authority_gate_for_scoring(self) -> None:
        classifier = LocalOnnxRiskClassifier()
        clause = _clause("매출에서 회사가 정하는 기타 비용을 공제한다.")

        bc_only = classifier.predict_clause(
            clause,
            grounding_records=(_record("KC-B-F2", "knowledge_card", "B", RiskCategory.F2),),
        )
        self.assertEqual(len(bc_only), 1)
        self.assertEqual(bc_only[0].detector, DetectorType.MODEL)
        self.assertFalse(bc_only[0].score_eligible)
        self.assertTrue(bc_only[0].practice_reference)
        self.assertIsNone(bc_only[0].grounding_evidence_ids)
        self.assertEqual(aggregate_document_signals(bc_only).review_priority_score, 0)

        a1_grounded = classifier.predict_clause(
            clause,
            grounding_records=(_record("EV-A1-F2", "evidence", "A1", RiskCategory.F2),),
        )
        self.assertEqual(len(a1_grounded), 1)
        self.assertTrue(a1_grounded[0].score_eligible)
        self.assertFalse(a1_grounded[0].practice_reference)
        self.assertEqual(a1_grounded[0].grounding_evidence_ids, ("EV-A1-F2",))

        scored = aggregate_document_signals(
            a1_grounded,
            evidence_authority_tiers={"EV-A1-F2": "A1"},
        )
        self.assertGreater(scored.review_priority_score, 0)

    def test_hybrid_merge_unions_rule_and_model_without_bypassing_authority(self) -> None:
        rule_signal = RiskSignal(
            signal_id="RS-RULE-F2-OPEN-DEDUCTIONS",
            clause_id="clause-1",
            risk_category=RiskCategory.F2,
            detector=DetectorType.RULE,
            fired=True,
            score_eligible=True,
            practice_reference=False,
            signal_confidence=0.80,
            is_missing_protection=True,
            grounding_evidence_ids=("EV-A1-F2-RULE",),
            severity_raw=0.70,
        )
        model_signal = RiskSignal(
            signal_id="RS-MODEL-F2-OPEN-DEDUCTIONS",
            clause_id="clause-1",
            risk_category=RiskCategory.F2,
            detector=DetectorType.MODEL,
            fired=True,
            score_eligible=False,
            practice_reference=True,
            signal_confidence=0.84,
            is_missing_protection=True,
            severity_raw=0.74,
        )

        merged = merge_rule_and_model_signals((rule_signal,), (model_signal,))

        self.assertEqual(len(merged), 1)
        hybrid = merged[0]
        self.assertEqual(hybrid.detector, DetectorType.HYBRID)
        self.assertTrue(hybrid.score_eligible)
        self.assertFalse(hybrid.practice_reference)
        self.assertEqual(hybrid.grounding_evidence_ids, ("EV-A1-F2-RULE",))
        self.assertEqual(hybrid.severity_raw, 0.74)
        self.assertGreater(hybrid.signal_confidence, model_signal.signal_confidence)

        bc_only_hybrid = merge_rule_and_model_signals((), (model_signal,))
        self.assertEqual(len(bc_only_hybrid), 1)
        self.assertFalse(bc_only_hybrid[0].score_eligible)
        self.assertTrue(bc_only_hybrid[0].practice_reference)
        self.assertIsNone(bc_only_hybrid[0].grounding_evidence_ids)

    def test_default_profile_is_weight_free_onnx_metadata_for_private_models_dir(self) -> None:
        profile = DEFAULT_ONNX_PROFILE

        self.assertEqual(profile.model_format, "onnx")
        self.assertTrue(
            profile.onnx_artifact_path.as_posix().endswith(
                "models/fink-risk-classifier-v0/risk_classifier.onnx"
            )
        )
        self.assertFalse(profile.as_dict()["weights_public_git"])
        self.assertRegex(profile.config_hash, r"^[a-f0-9]{64}$")


def _clause(text_ko: str) -> Clause:
    return Clause(
        clause_id="clause-1",
        clause_index=0,
        text_ko=text_ko,
        source_span_ids=("span-1",),
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
        risk_categories=(f"{category.value}_SYNTHETIC",),
        score_eligible=authority_tier in {"A0", "A1", "A2"},
        practice_reference=authority_tier in {"B", "C", "B/C"},
        matched_terms=(category.value,),
    )


@contextmanager
def _blocked_network() -> Iterator[None]:
    def fail(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("network access is not allowed in model_arm_offline_test")

    with (
        patch.object(socket, "socket", side_effect=fail),
        patch.object(socket, "create_connection", side_effect=fail),
        patch.object(socket, "getaddrinfo", side_effect=fail),
    ):
        yield


if __name__ == "__main__":
    unittest.main()

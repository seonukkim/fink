from __future__ import annotations

import importlib
import json
import sys
import unittest
from decimal import Decimal
from pathlib import Path
from typing import Any
from unittest.mock import patch


def _load_module(name: str) -> Any:
    src_root = Path(__file__).resolve().parents[2] / "src"
    src_text = src_root.as_posix()
    if src_text not in sys.path:
        sys.path.insert(0, src_text)
    return importlib.import_module(name)


ANALYZE = _load_module("fink.web.analyze")
ASSUMPTIONS = _load_module("fink.web.assumptions")
INGEST = _load_module("fink.ingest.session")
SCHEMAS = _load_module("fink.schemas")

# Two Korean clauses that fire missing-protection signals across F1/F2/F7. Each
# sentence ends with a period, so it cannot trip the long-private-quote gate.
SAMPLE_KO = (
    "제3조(정산) 정산은 매 분기 종료일로부터 90일 이내에 지급하며, 회사는 일반 경비를 공제할 수 있다.\n"
    "제5조(위약금) 계약 위반 시 위약금을 부과한다."
)
GROUNDED_F5_KO = "저작권 및 2차적저작물 권리는 회사에 포괄 양도된다."
CANDIDATE_F9_KO = "전자계약 원본과 증거는 보관하지 않고 삭제할 수 있다."


def _without_audit(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if key != "audit_detail"}


class AnalyzePipelineTests(unittest.TestCase):
    def test_pasted_text_analysis_uses_local_retrieval_with_four_dimensions(self) -> None:
        result = ANALYZE.run_local_analysis(
            pasted_text=SAMPLE_KO, ui_locale=SCHEMAS.UILocale.KO
        )

        self.assertGreaterEqual(result.clause_count, 1)
        self.assertGreaterEqual(len(result.ranked_findings), 1)
        self.assertIn(
            result.grounding,
            {"LOCAL_OFFICIAL_EVIDENCE", "CANDIDATE_UNVERIFIED"},
        )
        self.assertGreaterEqual(result.retrieved_record_count, 1)
        for finding in result.ranked_findings:
            self.assertTrue(finding.label_ko.strip())
            self.assertTrue(finding.label_en.strip())
            self.assertTrue(finding.clause_id.strip())
            if finding.scored:
                self.assertTrue(finding.grounding_evidence_ids)
                self.assertTrue(finding.citations)
                self.assertTrue(set(finding.authority_tiers) <= {"A0", "A1", "A2"})
            else:
                self.assertEqual(finding.citations, ())
                self.assertEqual(finding.grounding_evidence_ids, ())
                self.assertEqual(finding.grounding, "CANDIDATE_UNVERIFIED")

        # Findings are ranked by severity_raw * signal_confidence, descending.
        scores = [finding.rank_score for finding in result.ranked_findings]
        self.assertEqual(scores, sorted(scores, reverse=True))

        # Four separate dimensions are all present.
        payload = ANALYZE.analysis_result_to_payload(result, SCHEMAS.UILocale.KO)
        self.assertEqual(payload["view_model"], "CreatorReviewViewModel")
        self.assertEqual(payload["schema_version"], 1)
        for key in (
            "reading_status",
            "evidence_status",
            "scenario_status",
            "quantification_status",
        ):
            self.assertIn(key, payload["statuses"])

        dimensions = payload["dimensions"]
        for key in ("review_priority", "monetary", "time", "evidence"):
            self.assertIn(key, dimensions)
        self.assertGreaterEqual(dimensions["review_priority"]["score"], 0)
        self.assertLessEqual(dimensions["review_priority"]["score"], 100)
        self.assertEqual(
            dimensions["monetary"]["quantification_status"]["state"],
            "not_quantified",
        )
        self.assertGreaterEqual(len(payload["findings"]), 1)
        primary_json = json.dumps(_without_audit(payload), ensure_ascii=False)
        for forbidden in (
            "FIM-",
            "F3",
            "authority_factor",
            "runtime_s",
            "overall_confidence",
            "severity_raw",
            "signal_confidence",
        ):
            self.assertNotIn(forbidden, primary_json)
        audit_json = json.dumps(payload["audit_detail"], ensure_ascii=False)
        self.assertIn("runtime_s", audit_json)
        self.assertIn("overall_confidence", audit_json)

        # Korean is canonical and English is a generated aid; both nonblank.
        self.assertTrue(result.nl_summary_ko.strip())
        self.assertTrue(result.nl_summary_en.strip())
        self.assertNotEqual(result.nl_summary_ko, result.nl_summary_en)

    def test_eligible_official_source_yields_nonzero_grounded_contribution(self) -> None:
        result = ANALYZE.run_local_analysis(
            pasted_text=GROUNDED_F5_KO,
            ui_locale=SCHEMAS.UILocale.KO,
        )

        self.assertGreater(result.review_priority_score, 0)
        self.assertEqual(result.grounding, "LOCAL_OFFICIAL_EVIDENCE")
        scored = [finding for finding in result.ranked_findings if finding.scored]
        self.assertGreaterEqual(len(scored), 1)
        for finding in scored:
            self.assertTrue(finding.grounding_evidence_ids)
            self.assertTrue(finding.citations)
            self.assertTrue(set(finding.authority_tiers) <= {"A0", "A1", "A2"})
        self.assertTrue(
            any(contribution.contribution > 0 for contribution in result.scoring.contributions)
        )

        payload = ANALYZE.analysis_result_to_payload(result, SCHEMAS.UILocale.KO)
        grounded_findings = [
            finding
            for finding in payload["findings"]
            if finding["evidence"]["state"] == "official_evidence_unverified"
        ]
        self.assertGreaterEqual(len(grounded_findings), 1)
        self.assertTrue(grounded_findings[0]["citations"])

    def test_no_eligible_official_evidence_is_candidate_with_zero_contribution(self) -> None:
        result = ANALYZE.run_local_analysis(
            pasted_text=CANDIDATE_F9_KO,
            ui_locale=SCHEMAS.UILocale.KO,
        )

        self.assertEqual(result.review_priority_score, 0)
        self.assertEqual(result.grounding, "CANDIDATE_UNVERIFIED")
        self.assertGreaterEqual(len(result.ranked_findings), 1)
        for finding in result.ranked_findings:
            self.assertFalse(finding.scored)
            self.assertEqual(finding.grounding, "CANDIDATE_UNVERIFIED")
            self.assertEqual(finding.grounding_evidence_ids, ())
            self.assertEqual(finding.citations, ())
        self.assertTrue(
            all(contribution.contribution == 0 for contribution in result.scoring.contributions)
        )

        payload = ANALYZE.analysis_result_to_payload(result, SCHEMAS.UILocale.KO)
        for finding in payload["findings"]:
            self.assertEqual(finding["evidence"]["state"], "candidate_unverified")
            self.assertEqual(finding["citations"], [])
            self.assertIn("미확인 후보", finding["evidence"]["missing"]["ko"])

    def test_generated_english_or_similarity_only_records_do_not_create_eligibility(self) -> None:
        import fink.retrieval as retrieval

        generated_record = retrieval.RetrievalChunk(
            chunk_id="EV-GENERATED-F5",
            chunk_type="evidence",
            text="F5_IP_MONETIZATION 저작권 2차적저작물 generated English alias",
            title="Generated alias only",
            source_id="A1-GENERATED",
            source_ids=("A1-GENERATED",),
            source_class="A1",
            authority_tier="A1",
            verification_status="UNVERIFIED",
            risk_categories=("F5_IP_MONETIZATION",),
            hierarchy=("tier:A1", "source:A1-GENERATED", "risk:F5", "chunk:generated"),
            score_eligible=False,
            practice_reference=False,
            generated_translation=True,
        )
        practice_record = retrieval.RetrievalChunk(
            chunk_id="KC-F5-PRACTICE",
            chunk_type="knowledge_card",
            text="F5_IP_MONETIZATION 저작권 2차적저작물 practice explanation",
            title="Practice only",
            source_id="B-PRACTICE",
            source_ids=("B-PRACTICE",),
            source_class="B",
            authority_tier="B",
            verification_status="UNVERIFIED",
            risk_categories=("F5_IP_MONETIZATION",),
            hierarchy=("tier:B", "source:B-PRACTICE", "risk:F5", "chunk:practice"),
            score_eligible=False,
            practice_reference=True,
            generated_translation=True,
        )
        index = retrieval.LocalBM25Index((generated_record, practice_record))

        with patch.object(retrieval, "load_or_build_retrieval_index", return_value=index):
            result = ANALYZE.run_local_analysis(
                pasted_text=GROUNDED_F5_KO,
                ui_locale=SCHEMAS.UILocale.KO,
            )

        self.assertEqual(result.review_priority_score, 0)
        self.assertTrue(result.ranked_findings)
        self.assertFalse(any(finding.scored for finding in result.ranked_findings))
        self.assertFalse(any(finding.grounding_evidence_ids for finding in result.ranked_findings))

    def test_payload_is_json_serializable(self) -> None:
        result = ANALYZE.run_local_analysis(
            pasted_text=SAMPLE_KO, ui_locale=SCHEMAS.UILocale.EN
        )
        payload = ANALYZE.analysis_result_to_payload(result, SCHEMAS.UILocale.EN)
        encoded = json.dumps(payload, ensure_ascii=False)
        self.assertIn("CreatorReviewViewModel", encoded)
        self.assertIn("findings", encoded)
        # Round-trips without a custom encoder.
        self.assertIsInstance(json.loads(encoded), dict)

    def test_recommended_action_matches_pathway_label(self) -> None:
        result = ANALYZE.run_local_analysis(pasted_text=SAMPLE_KO)
        pathway = result.time_result.time_exposure.pathway_label
        self.assertEqual(result.recommended_action.pathway_label, pathway.value)
        self.assertTrue(result.recommended_action.action_ko.strip())
        self.assertTrue(result.recommended_action.cash_flow_en.strip())

    def test_assumptions_unlock_monetary_ranges_without_cross_type_total(self) -> None:
        # FIM-4 inputs are enough to compute one low/base/high exposure.
        assumptions = ASSUMPTIONS.EditableAssumptions(
            unpaid_revision_units=3,
            hours_per_unit=Decimal("4"),
            creator_hourly_value=Decimal("50000"),
        )
        result = ANALYZE.run_local_analysis(
            pasted_text=SAMPLE_KO,
            scenario_inputs=assumptions,
            ui_locale=SCHEMAS.UILocale.KO,
        )
        self.assertTrue(result.monetary_present)
        computed = [
            exposure
            for exposure in result.exposures
            if not exposure.is_user_input_required
        ]
        self.assertGreaterEqual(len(computed), 1)
        for exposure in computed:
            self.assertIsNotNone(exposure.low)
            self.assertIsNotNone(exposure.base)
            self.assertIsNotNone(exposure.high)

        # No cross-type grand total: every reported value belongs to one typed
        # exposure; the payload never sums different exposure types together.
        payload = ANALYZE.analysis_result_to_payload(result, SCHEMAS.UILocale.KO)
        monetary = payload["dimensions"]["monetary"]
        self.assertNotIn("grand_total", monetary)
        self.assertNotIn("total", monetary)
        for entry in monetary["ranges"]:
            self.assertIn("range_id", entry)
            self.assertNotIn("fim_module", entry)

    def test_blank_paste_raises_ingest_validation_error(self) -> None:
        with self.assertRaises(INGEST.IngestValidationError):
            ANALYZE.run_local_analysis(pasted_text="   ")
        with self.assertRaises(INGEST.IngestValidationError):
            ANALYZE.run_local_analysis(pasted_text=None)

    def test_ingested_document_pages_are_analyzable(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "uploads"
            with INGEST.EphemeralIngestSession(upload_root=root) as session:
                ingested = session.ingest_paste(SAMPLE_KO)
                # ingest_paste carries pasted_text but builds no pages, so the
                # analysis should fall back to the pasted text on the request.
                result = ANALYZE.run_local_analysis(
                    pasted_text=ingested.request.pasted_text
                )
                self.assertGreaterEqual(result.clause_count, 1)


if __name__ == "__main__":
    unittest.main()

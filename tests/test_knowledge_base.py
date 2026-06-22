from __future__ import annotations

import sys
from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parents[1] / "src"
if SRC_ROOT.as_posix() not in sys.path:
    sys.path.insert(0, SRC_ROOT.as_posix())

from fink.knowledge import (
    curated_checklist_for_category,
    checkpoints_for_categories,
    load_checkpoints,
)


EXPECTED_CATEGORIES = tuple(f"F{index}" for index in range(1, 10))


def test_creator_contract_checkpoint_dataset_loads() -> None:
    payload = load_checkpoints()

    assert payload["schema_version"] == 1
    assert isinstance(payload["topics"], list)
    assert len(payload["topics"]) == 9


def test_all_financial_categories_have_required_fields() -> None:
    topics = load_checkpoints()["topics"]
    by_category = {topic["category"]: topic for topic in topics}

    assert tuple(by_category) == EXPECTED_CATEGORIES
    for category in EXPECTED_CATEGORIES:
        topic = by_category[category]
        assert topic["topic_ko"].strip()
        assert topic["topic_en"].strip()
        assert topic["summary_ko"].strip()
        assert topic["summary_en"].strip()
        assert len(topic["checkpoints_ko"]) >= 3
        assert len(topic["checkpoints_en"]) == len(topic["checkpoints_ko"])
        assert all(item.strip() for item in topic["checkpoints_ko"])
        assert all(item.strip() for item in topic["checkpoints_en"])
        assert len(topic["negotiation_questions_ko"]) >= 1
        assert len(topic["negotiation_questions_en"]) == len(topic["negotiation_questions_ko"])
        assert all(item.strip() for item in topic["negotiation_questions_ko"])
        assert all(item.strip() for item in topic["negotiation_questions_en"])
        assert topic["provenance"]["source_types"]
        assert topic["provenance"]["note"] == "원문 복제 없이 일반 원칙을 distill"


def test_checkpoints_for_categories_returns_matches_in_category_order() -> None:
    topics = checkpoints_for_categories(["F1", "F3"])

    assert [topic["category"] for topic in topics] == ["F1", "F3"]
    assert [topic["id"] for topic in topics] == ["ckpt-f1", "ckpt-f3"]


def test_curated_checklist_for_category_is_bilingual_non_scoring_and_deduped() -> None:
    used: set[str] = set()

    first = curated_checklist_for_category("F1", used_checkpoint_keys=used)
    second = curated_checklist_for_category("F1", used_checkpoint_keys=used)

    assert first is not None
    assert first["topic"] == {"ko": "정산·감사", "en": "Settlement and audit"}
    assert len(first["checkpoints"]) == 3
    assert "source_note" not in first
    assert first["score_contribution"] == 0
    assert first["authority_tiers"] == []
    assert first["grounding_evidence_ids"] == []
    assert first["non_scoring"] is True
    assert all(item["ko"].strip() and item["en"].strip() for item in first["checkpoints"])

    assert second is not None
    repeated = {
        item["ko"]
        for item in first["checkpoints"]
    } & {
        item["ko"]
        for item in second["checkpoints"]
    }
    assert repeated == set()

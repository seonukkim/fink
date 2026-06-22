from __future__ import annotations

import sys
from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parents[1] / "src"
if SRC_ROOT.as_posix() not in sys.path:
    sys.path.insert(0, SRC_ROOT.as_posix())

from fink.knowledge import checkpoints_for_categories, load_checkpoints


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
        assert topic["summary_ko"].strip()
        assert len(topic["checkpoints_ko"]) >= 3
        assert all(item.strip() for item in topic["checkpoints_ko"])
        assert len(topic["negotiation_questions_ko"]) >= 1
        assert all(item.strip() for item in topic["negotiation_questions_ko"])
        assert topic["provenance"]["source_types"]
        assert topic["provenance"]["note"] == "원문 복제 없이 일반 원칙을 distill"


def test_checkpoints_for_categories_returns_matches_in_category_order() -> None:
    topics = checkpoints_for_categories(["F1", "F3"])

    assert [topic["category"] for topic in topics] == ["F1", "F3"]
    assert [topic["id"] for topic in topics] == ["ckpt-f1", "ckpt-f3"]

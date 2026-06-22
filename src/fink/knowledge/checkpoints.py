from __future__ import annotations

from collections.abc import Iterable
from functools import lru_cache
from pathlib import Path
from typing import Any

try:
    import yaml  # type: ignore[import-untyped]
except Exception as exc:  # pragma: no cover - dependency is declared in pyproject
    raise RuntimeError("PyYAML is required for FInk knowledge checkpoint loading") from exc


DATASET_PATH = (
    Path(__file__).resolve().parents[3] / "data" / "knowledge" / "creator_contract_checkpoints.yaml"
)
CHECKLIST_SOURCE_NOTE = {
    "ko": "일반 실무 원칙 distill · 법률 자문 아님",
    "en": "Distilled general practice · not legal advice",
}


class KnowledgeBaseError(RuntimeError):
    """Raised when the public checkpoint knowledge base is missing or malformed."""


@lru_cache(maxsize=1)
def load_checkpoints() -> dict[str, Any]:
    """Load the public creator-contract checkpoint knowledge base."""

    if not DATASET_PATH.is_file():
        raise KnowledgeBaseError(f"checkpoint knowledge base not found: {DATASET_PATH}")

    loaded = yaml.safe_load(DATASET_PATH.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise KnowledgeBaseError("checkpoint knowledge base must be a YAML mapping")
    if loaded.get("schema_version") != 1:
        raise KnowledgeBaseError("checkpoint knowledge base schema_version must be 1")
    topics = loaded.get("topics")
    if not isinstance(topics, list):
        raise KnowledgeBaseError("checkpoint knowledge base topics must be a list")
    return loaded


def checkpoints_for_categories(categories: Iterable[str]) -> list[dict[str, Any]]:
    """Return checkpoint topics for the requested F1-F9 categories in dataset order."""

    requested = {str(category).strip().upper() for category in categories if str(category).strip()}
    topics = load_checkpoints()["topics"]
    return [
        dict(topic)
        for topic in topics
        if isinstance(topic, dict) and str(topic.get("category", "")).upper() in requested
    ]


def curated_checklist_for_category(
    category: Any,
    *,
    used_checkpoint_keys: set[str] | None = None,
    limit: int = 3,
) -> dict[str, Any] | None:
    """Return a short bilingual, non-scoring checklist block for one F category.

    Checkpoints are authored in priority order. ``used_checkpoint_keys`` may be
    shared across findings to avoid repeating the same practice prompt in one
    result payload.
    """

    category_code = _category_code(category)
    if not category_code or limit <= 0:
        return None

    topic = _topic_for_category(category_code)
    if topic is None:
        return None

    checkpoints_ko = _string_list(topic.get("checkpoints_ko"))
    checkpoints_en = _string_list(topic.get("checkpoints_en"))
    selected: list[dict[str, str]] = []
    seen = used_checkpoint_keys if used_checkpoint_keys is not None else set()
    for index, checkpoint_ko in enumerate(checkpoints_ko):
        checkpoint_en = checkpoints_en[index] if index < len(checkpoints_en) else ""
        key = _checkpoint_key(checkpoint_ko, checkpoint_en)
        if not key or key in seen:
            continue
        selected.append({"ko": checkpoint_ko, "en": checkpoint_en})
        seen.add(key)
        if len(selected) >= limit:
            break

    if not selected:
        return None

    return {
        "topic": {
            "ko": str(topic.get("topic_ko") or "").strip(),
            "en": str(topic.get("topic_en") or "").strip(),
        },
        "checkpoints": selected,
        "source_note": dict(CHECKLIST_SOURCE_NOTE),
        "source_kind": "distilled_general_practice",
        "score_contribution": 0,
        "authority_tiers": [],
        "grounding_evidence_ids": [],
        "non_scoring": True,
    }


def _topic_for_category(category: str) -> dict[str, Any] | None:
    topics = load_checkpoints()["topics"]
    for topic in topics:
        if isinstance(topic, dict) and str(topic.get("category", "")).upper() == category:
            return dict(topic)
    return None


def _category_code(category: Any) -> str:
    raw = getattr(category, "value", category)
    text = str(raw or "").strip().upper()
    return text[:2] if text[:2] in {f"F{index}" for index in range(1, 10)} else text


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _checkpoint_key(checkpoint_ko: str, checkpoint_en: str) -> str:
    base = checkpoint_ko or checkpoint_en
    return " ".join(base.split()).casefold()

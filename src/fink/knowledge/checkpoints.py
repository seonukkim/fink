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

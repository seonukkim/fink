from __future__ import annotations

import csv
import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import yaml  # type: ignore[import-untyped]
except Exception as exc:  # pragma: no cover - dependency is declared in pyproject
    raise RuntimeError("PyYAML is required for FInk corpus loading") from exc


class CorpusValidationError(RuntimeError):
    """Raised when the local Stage 0-2 corpus is missing or inconsistent."""


@dataclass(frozen=True)
class RequiredFile:
    stage_dir: str
    filename: str

    @property
    def relpath(self) -> Path:
        return Path(self.stage_dir) / self.filename


@dataclass(frozen=True)
class FileCheck:
    filename: str
    stage: str
    file_type: str
    expected_count: int
    actual_count: int

    def as_dict(self) -> dict[str, object]:
        return {
            "filename": self.filename,
            "stage": self.stage,
            "file_type": self.file_type,
            "expected_count": self.expected_count,
            "actual_count": self.actual_count,
        }


@dataclass(frozen=True)
class ValidationReport:
    corpus_dir: Path
    files: tuple[FileCheck, ...]
    counts: dict[str, int]

    def as_dict(self) -> dict[str, object]:
        return {
            "corpus_dir": self.corpus_dir.as_posix(),
            "counts": dict(self.counts),
            "files": [item.as_dict() for item in self.files],
        }


MANDATORY_STAGE_FILES: tuple[RequiredFile, ...] = (
    RequiredFile("stage-0", "01_SOURCE_MANIFEST.csv"),
    RequiredFile("stage-0", "02_SOURCE_ROLE_AND_AUTHORITY_MAP.md"),
    RequiredFile("stage-0", "03_DUPLICATE_CONFLICT_AND_PRECEDENCE_LOG.csv"),
    RequiredFile("stage-1", "10_MASTER_RISK_TAXONOMY.md"),
    RequiredFile("stage-1", "10_MASTER_RISK_TAXONOMY.yaml"),
    RequiredFile("stage-1", "11_MASTER_CREATOR_CHECKLIST.jsonl"),
    RequiredFile("stage-1", "11_MASTER_CREATOR_CHECKLIST.md"),
    RequiredFile("stage-1", "12_MASTER_FINANCIAL_FEATURES.md"),
    RequiredFile("stage-1", "12_MASTER_FINANCIAL_FEATURES.yaml"),
    RequiredFile("stage-1", "13_MASTER_BILINGUAL_GLOSSARY.csv"),
    RequiredFile("stage-1", "13_MASTER_BILINGUAL_GLOSSARY.md"),
    RequiredFile("stage-1", "14_MASTER_EVIDENCE_MATRIX.csv"),
    RequiredFile("stage-1", "15_MASTER_KNOWLEDGE_CARDS.jsonl"),
    RequiredFile("stage-1", "16_HIERARCHICAL_RAG_CORPUS_SPEC.md"),
    RequiredFile("stage-2", "20_FINANCIAL_AI_METHOD_MAP.md"),
    RequiredFile("stage-2", "21_CONTRIBUTION_CANDIDATES.md"),
    RequiredFile("stage-2", "22_DATASET_AND_EVALUATION_PLAN.md"),
    RequiredFile("stage-2", "23_TERM_PROJECT_COMPLIANCE_MAP.md"),
    RequiredFile("stage-2", "24_FUTURE_DELIVERABLE_DATA_REQUIREMENTS.md"),
)
INDEX_FILE = RequiredFile("stage-3", "32_FINAL_FILE_INDEX.csv")

TARGET_COUNTS = {
    "sources": 35,
    "glossary_terms": 156,
    "evidence_records": 20,
    "knowledge_cards": 64,
    "checklist_items": 52,
    "canonical_features": 29,
    "auxiliary_features": 3,
    "taxonomy_financial_categories": 9,
    "taxonomy_crosscutting_categories": 5,
}


def import_upstream_corpus(upstream_root: Path, corpus_dir: Path) -> ValidationReport:
    """Copy mandatory Stage 0-2 records plus the Stage-3 index into ``corpus_dir``."""
    _require_files(upstream_root, (*MANDATORY_STAGE_FILES, INDEX_FILE))
    corpus_dir.mkdir(parents=True, exist_ok=True)
    _ensure_local_gitignore(corpus_dir)
    for item in (*MANDATORY_STAGE_FILES, INDEX_FILE):
        source = upstream_root / item.relpath
        dest = corpus_dir / item.relpath
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dest)
    return load_corpus(corpus_dir)


def load_corpus(corpus_dir: Path) -> ValidationReport:
    """Load and validate the local corpus copy.

    The loader intentionally fails fast on any mandatory missing/empty file, then
    parses each structured file and compares counts against 32_FINAL_FILE_INDEX.
    """
    required = (*MANDATORY_STAGE_FILES, INDEX_FILE)
    _require_files(corpus_dir, required)
    index = _read_index(corpus_dir / INDEX_FILE.relpath)
    loaded: dict[str, Any] = {}
    checks: list[FileCheck] = []
    for item in MANDATORY_STAGE_FILES:
        entry = index.get(item.filename)
        if entry is None:
            raise CorpusValidationError(f"index missing mandatory file: {item.filename}")
        path = corpus_dir / item.relpath
        parsed, actual_count = _load_and_count(path, entry["type"])
        expected_count = int(entry["record_or_line_count"])
        if actual_count != expected_count:
            raise CorpusValidationError(
                f"{item.filename} count mismatch: expected {expected_count}, got {actual_count}"
            )
        loaded[item.filename] = parsed
        checks.append(
            FileCheck(
                filename=item.filename,
                stage=str(entry["stage"]),
                file_type=str(entry["type"]),
                expected_count=expected_count,
                actual_count=actual_count,
            )
        )
    counts = _validate_domain_counts(loaded)
    return ValidationReport(corpus_dir=corpus_dir, files=tuple(checks), counts=counts)


def _ensure_local_gitignore(corpus_dir: Path) -> None:
    path = corpus_dir / ".gitignore"
    expected = "*\n!.gitignore\n"
    if not path.exists() or path.read_text(encoding="utf-8") != expected:
        path.write_text(expected, encoding="utf-8")


def _require_files(root: Path, files: tuple[RequiredFile, ...]) -> None:
    missing = [item.relpath.as_posix() for item in files if not (root / item.relpath).is_file()]
    if missing:
        raise CorpusValidationError("mandatory corpus files missing: " + ", ".join(missing))
    empty = [item.relpath.as_posix() for item in files if (root / item.relpath).stat().st_size == 0]
    if empty:
        raise CorpusValidationError("mandatory corpus files empty: " + ", ".join(empty))


def _read_index(path: Path) -> dict[str, dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))
    required_columns = {
        "filename",
        "stage",
        "type",
        "record_or_line_count",
    }
    missing_columns = required_columns.difference(rows[0].keys() if rows else [])
    if missing_columns:
        raise CorpusValidationError(
            f"{INDEX_FILE.filename} missing columns: {', '.join(sorted(missing_columns))}"
        )
    return {row["filename"]: row for row in rows}


def _load_and_count(path: Path, file_type: str) -> tuple[Any, int]:
    normalized_type = file_type.upper()
    if normalized_type == "CSV":
        with path.open(newline="", encoding="utf-8-sig") as fh:
            rows = list(csv.DictReader(fh))
        if rows and None in rows[0]:
            raise CorpusValidationError(f"malformed CSV row in {path.name}")
        return rows, len(rows)
    if normalized_type == "JSONL":
        return _load_jsonl(path)
    if normalized_type == "YAML":
        text = path.read_text(encoding="utf-8-sig")
        parsed = yaml.safe_load(text)
        if parsed is None:
            raise CorpusValidationError(f"empty YAML payload in {path.name}")
        return parsed, _line_count(text)
    if normalized_type == "MD":
        text = path.read_text(encoding="utf-8-sig")
        if not text.strip():
            raise CorpusValidationError(f"empty Markdown payload in {path.name}")
        return text, _line_count(text)
    raise CorpusValidationError(f"unsupported indexed file type for {path.name}: {file_type}")


def _load_jsonl(path: Path) -> tuple[list[Any], int]:
    records: list[Any] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise CorpusValidationError(f"{path.name}:{line_number}: {exc}") from exc
        if not isinstance(record, dict):
            raise CorpusValidationError(f"{path.name}:{line_number}: JSONL record is not an object")
        records.append(record)
    return records, len(records)


def _line_count(text: str) -> int:
    if not text:
        return 0
    return len(text.splitlines())


def _validate_domain_counts(loaded: dict[str, Any]) -> dict[str, int]:
    taxonomy = _require_mapping(loaded["10_MASTER_RISK_TAXONOMY.yaml"], "taxonomy YAML")
    features = _require_mapping(loaded["12_MASTER_FINANCIAL_FEATURES.yaml"], "features YAML")
    counts = {
        "sources": len(_require_list(loaded["01_SOURCE_MANIFEST.csv"], "source manifest")),
        "glossary_terms": len(_require_list(loaded["13_MASTER_BILINGUAL_GLOSSARY.csv"], "glossary")),
        "evidence_records": len(_require_list(loaded["14_MASTER_EVIDENCE_MATRIX.csv"], "evidence")),
        "knowledge_cards": len(_require_list(loaded["15_MASTER_KNOWLEDGE_CARDS.jsonl"], "cards")),
        "checklist_items": len(
            _require_list(loaded["11_MASTER_CREATOR_CHECKLIST.jsonl"], "checklist")
        ),
        "canonical_features": len(_require_list(features.get("canonical_features"), "features")),
        "auxiliary_features": len(_require_list(features.get("auxiliary_fields"), "aux features")),
        "taxonomy_financial_categories": len(
            _require_list(taxonomy.get("financial_categories"), "financial taxonomy")
        ),
        "taxonomy_crosscutting_categories": len(
            _require_list(taxonomy.get("crosscutting_categories"), "crosscutting taxonomy")
        ),
    }
    for key, expected in TARGET_COUNTS.items():
        actual = counts[key]
        if actual != expected:
            raise CorpusValidationError(f"{key} mismatch: expected {expected}, got {actual}")
    _validate_declared_yaml_counts(taxonomy, "counts", "financial_categories", 9)
    _validate_declared_yaml_counts(taxonomy, "counts", "crosscutting_categories", 5)
    _validate_declared_yaml_counts(features, "counts", "canonical_features", 29)
    _validate_declared_yaml_counts(features, "counts", "auxiliary_fields", 3)
    return counts


def _require_mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise CorpusValidationError(f"{label} must be a mapping")
    return value


def _require_list(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise CorpusValidationError(f"{label} must be a list")
    return value


def _validate_declared_yaml_counts(
    payload: dict[str, Any], section: str, key: str, expected: int
) -> None:
    section_payload = _require_mapping(payload.get(section), section)
    actual = section_payload.get(key)
    if actual != expected:
        raise CorpusValidationError(f"{section}.{key} mismatch: expected {expected}, got {actual}")

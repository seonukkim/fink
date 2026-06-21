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


@dataclass(frozen=True)
class EvidenceRecord:
    evidence_id: str
    source_id: str
    source_class: str
    authority_tier: str
    article_or_section: str
    page_or_slide: str
    short_source_excerpt: str
    canonical_url: str
    verification_status: str
    supports_protection: bool
    supports_review_signal: bool
    risk_categories: tuple[str, ...]
    financial_variables: tuple[str, ...]
    score_eligible: bool
    notes: str

    @property
    def excerpt_word_count(self) -> int:
        return _word_count(self.short_source_excerpt)

    def as_dict(self) -> dict[str, object]:
        return {
            "evidence_id": self.evidence_id,
            "source_id": self.source_id,
            "source_class": self.source_class,
            "authority_tier": self.authority_tier,
            "article_or_section": self.article_or_section,
            "page_or_slide": self.page_or_slide,
            "short_source_excerpt": self.short_source_excerpt,
            "canonical_url": self.canonical_url,
            "verification_status": self.verification_status,
            "supports_protection": self.supports_protection,
            "supports_review_signal": self.supports_review_signal,
            "risk_categories": list(self.risk_categories),
            "financial_variables": list(self.financial_variables),
            "score_eligible": self.score_eligible,
            "notes": self.notes,
            "excerpt_word_count": self.excerpt_word_count,
        }


@dataclass(frozen=True)
class KnowledgeCardRecord:
    card_id: str
    authority_tier: str
    source_ids: tuple[str, ...]
    risk_categories: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    score_eligible: bool
    public_export: bool

    def as_dict(self) -> dict[str, object]:
        return {
            "card_id": self.card_id,
            "authority_tier": self.authority_tier,
            "source_ids": list(self.source_ids),
            "risk_categories": list(self.risk_categories),
            "evidence_ids": list(self.evidence_ids),
            "score_eligible": self.score_eligible,
            "public_export": self.public_export,
        }


@dataclass(frozen=True)
class ChecklistItemRecord:
    check_id: str
    risk_category: str
    source_ids: tuple[str, ...]
    official_evidence_ids: tuple[str, ...]
    score_eligible: bool
    public_export: bool = False

    def as_dict(self) -> dict[str, object]:
        return {
            "check_id": self.check_id,
            "risk_category": self.risk_category,
            "source_ids": list(self.source_ids),
            "official_evidence_ids": list(self.official_evidence_ids),
            "score_eligible": self.score_eligible,
            "public_export": self.public_export,
        }


@dataclass(frozen=True)
class GlossaryTermRecord:
    canonical_id: str
    risk_category: str
    source_ids: tuple[str, ...]
    generated_translation: bool
    score_eligible: bool

    def as_dict(self) -> dict[str, object]:
        return {
            "canonical_id": self.canonical_id,
            "risk_category": self.risk_category,
            "source_ids": list(self.source_ids),
            "generated_translation": self.generated_translation,
            "score_eligible": self.score_eligible,
        }


@dataclass(frozen=True)
class BCReferenceCorpus:
    knowledge_cards: tuple[KnowledgeCardRecord, ...]
    checklist_items: tuple[ChecklistItemRecord, ...]
    glossary_terms: tuple[GlossaryTermRecord, ...]

    @property
    def counts(self) -> dict[str, int]:
        return {
            "knowledge_cards": len(self.knowledge_cards),
            "checklist_items": len(self.checklist_items),
            "glossary_terms": len(self.glossary_terms),
        }

    def as_dict(self) -> dict[str, object]:
        return {
            "counts": self.counts,
            "knowledge_cards": [item.as_dict() for item in self.knowledge_cards],
            "checklist_items": [item.as_dict() for item in self.checklist_items],
            "glossary_terms": [item.as_dict() for item in self.glossary_terms],
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
EVIDENCE_FILE = RequiredFile("stage-1", "14_MASTER_EVIDENCE_MATRIX.csv")
KNOWLEDGE_CARDS_FILE = RequiredFile("stage-1", "15_MASTER_KNOWLEDGE_CARDS.jsonl")
CHECKLIST_FILE = RequiredFile("stage-1", "11_MASTER_CREATOR_CHECKLIST.jsonl")
GLOSSARY_FILE = RequiredFile("stage-1", "13_MASTER_BILINGUAL_GLOSSARY.csv")

EVIDENCE_MATRIX_TIERS = frozenset({"A1", "A2"})
SCORING_AUTHORITY_TIERS = frozenset({"A0", "A1", "A2"})
BC_AUTHORITY_TIERS = frozenset({"B", "C", "B/C"})
PRIVATE_SOURCE_PREFIXES = ("B-", "C-")
UNVERIFIED_STATUS = "UNVERIFIED"
MAX_OFFICIAL_EXCERPT_WORDS_EXCLUSIVE = 15
EVIDENCE_COLUMNS = frozenset(
    {
        "evidence_id",
        "source_id",
        "source_class",
        "authority_tier",
        "article_or_section",
        "page_or_slide",
        "short_source_excerpt",
        "canonical_url",
        "verification_status",
        "supports_protection",
        "supports_review_signal",
        "risk_categories",
        "financial_variables",
        "score_eligible",
        "notes",
    }
)
KNOWLEDGE_CARD_COLUMNS = frozenset(
    {
        "card_id",
        "source_card_ids",
        "source_ids",
        "authority_tier",
        "score_eligible",
        "risk_categories",
        "title_ko",
        "title_en",
        "explanation_ko",
        "explanation_en",
        "aliases_ko",
        "aliases_en",
        "financial_variables",
        "page_or_slide_references",
        "evidence_ids",
        "evidence_strength",
        "conflicts",
        "generated_translation",
        "public_export",
        "notes",
    }
)
CHECKLIST_COLUMNS = frozenset(
    {
        "check_id",
        "risk_category",
        "question_ko",
        "question_en",
        "positive_protections",
        "review_signals",
        "financial_variables",
        "possible_financial_effects",
        "official_evidence_ids",
        "educational_source_ids",
        "practical_source_ids",
        "score_eligible",
        "human_review_required",
        "notes",
    }
)
GLOSSARY_COLUMNS = frozenset(
    {
        "canonical_id",
        "preferred_ko",
        "preferred_en",
        "risk_category",
        "aliases_ko",
        "aliases_en",
        "source_ids",
        "merged_src_canonical_ids",
        "generated_translation",
        "score_eligible",
        "notes",
    }
)

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


def load_evidence_records(
    corpus_dir: Path, *, expected_count: int | None = TARGET_COUNTS["evidence_records"]
) -> tuple[EvidenceRecord, ...]:
    """Load and validate the official A1/A2 evidence matrix.

    The S0 evidence corpus is deliberately conservative: every official excerpt
    must remain short, every record stays UNVERIFIED, and score eligibility is
    derived from the authority tier instead of hand-entered CSV text.
    """
    path = corpus_dir / EVIDENCE_FILE.relpath
    _require_files(corpus_dir, (EVIDENCE_FILE,))
    rows, _ = _load_csv(path)
    records = _parse_evidence_records(rows)
    if expected_count is not None and len(records) != expected_count:
        raise CorpusValidationError(
            f"{EVIDENCE_FILE.filename} record count mismatch: "
            f"expected {expected_count}, got {len(records)}"
        )
    return records


def load_bc_reference_records(
    corpus_dir: Path,
    *,
    expected_cards: int | None = TARGET_COUNTS["knowledge_cards"],
    expected_checklist_items: int | None = TARGET_COUNTS["checklist_items"],
    expected_glossary_terms: int | None = TARGET_COUNTS["glossary_terms"],
) -> BCReferenceCorpus:
    """Load and validate private B/C reference material.

    B/C material is allowed to explain terminology and ask review questions, but
    it is never score-eligible and knowledge cards are never public exports.
    Returned records intentionally expose metadata only, not private-book text.
    """
    _require_files(corpus_dir, (KNOWLEDGE_CARDS_FILE, CHECKLIST_FILE, GLOSSARY_FILE))
    card_rows, _ = _load_jsonl(corpus_dir / KNOWLEDGE_CARDS_FILE.relpath)
    checklist_rows, _ = _load_jsonl(corpus_dir / CHECKLIST_FILE.relpath)
    glossary_rows, _ = _load_csv(corpus_dir / GLOSSARY_FILE.relpath)
    records = BCReferenceCorpus(
        knowledge_cards=_parse_knowledge_cards(card_rows),
        checklist_items=_parse_checklist_items(checklist_rows),
        glossary_terms=_parse_glossary_terms(glossary_rows),
    )
    _validate_expected_count(
        KNOWLEDGE_CARDS_FILE.filename,
        len(records.knowledge_cards),
        expected_cards,
    )
    _validate_expected_count(
        CHECKLIST_FILE.filename,
        len(records.checklist_items),
        expected_checklist_items,
    )
    _validate_expected_count(
        GLOSSARY_FILE.filename,
        len(records.glossary_terms),
        expected_glossary_terms,
    )
    return records


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
        rows, _ = _load_csv(path)
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
        "glossary_terms": len(
            _require_list(loaded["13_MASTER_BILINGUAL_GLOSSARY.csv"], "glossary")
        ),
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
    _parse_evidence_records(_require_list(loaded["14_MASTER_EVIDENCE_MATRIX.csv"], "evidence"))
    _parse_knowledge_cards(_require_list(loaded["15_MASTER_KNOWLEDGE_CARDS.jsonl"], "cards"))
    _parse_checklist_items(
        _require_list(loaded["11_MASTER_CREATOR_CHECKLIST.jsonl"], "checklist")
    )
    _parse_glossary_terms(_require_list(loaded["13_MASTER_BILINGUAL_GLOSSARY.csv"], "glossary"))
    return counts


def _load_csv(path: Path) -> tuple[list[dict[str, str]], tuple[str, ...]]:
    with path.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        rows = list(reader)
        fieldnames = tuple(reader.fieldnames or ())
    if rows and None in rows[0]:
        raise CorpusValidationError(f"malformed CSV row in {path.name}")
    return rows, fieldnames


def _parse_evidence_records(rows: list[Any]) -> tuple[EvidenceRecord, ...]:
    records: list[EvidenceRecord] = []
    for idx, row in enumerate(rows, start=2):
        if not isinstance(row, dict):
            raise CorpusValidationError(f"{EVIDENCE_FILE.filename}:{idx}: row is not a mapping")
        missing_columns = EVIDENCE_COLUMNS.difference(row.keys())
        if missing_columns:
            raise CorpusValidationError(
                f"{EVIDENCE_FILE.filename}:{idx}: missing columns: "
                f"{', '.join(sorted(missing_columns))}"
            )
        record = EvidenceRecord(
            evidence_id=_required_text(row, "evidence_id", idx),
            source_id=_required_text(row, "source_id", idx),
            source_class=_required_text(row, "source_class", idx),
            authority_tier=_required_text(row, "authority_tier", idx),
            article_or_section=_required_text(row, "article_or_section", idx),
            page_or_slide=_required_text(row, "page_or_slide", idx),
            short_source_excerpt=_required_text(row, "short_source_excerpt", idx),
            canonical_url=_required_text(row, "canonical_url", idx),
            verification_status=_required_text(row, "verification_status", idx),
            supports_protection=_parse_bool(_required_text(row, "supports_protection", idx), idx),
            supports_review_signal=_parse_bool(
                _required_text(row, "supports_review_signal", idx), idx
            ),
            risk_categories=_split_semicolon_list(str(row.get("risk_categories", ""))),
            financial_variables=_split_semicolon_list(str(row.get("financial_variables", ""))),
            score_eligible=_parse_bool(_required_text(row, "score_eligible", idx), idx),
            notes=_required_text(row, "notes", idx),
        )
        _validate_evidence_record(record, idx)
        records.append(record)
    return tuple(records)


def _validate_evidence_record(record: EvidenceRecord, line_number: int) -> None:
    prefix = f"{EVIDENCE_FILE.filename}:{line_number}: {record.evidence_id}"
    if record.source_class != record.authority_tier:
        raise CorpusValidationError(
            f"{prefix}: source_class {record.source_class!r} does not match "
            f"authority_tier {record.authority_tier!r}"
        )
    if record.authority_tier not in EVIDENCE_MATRIX_TIERS:
        raise CorpusValidationError(
            f"{prefix}: expected A1/A2 evidence tier, got {record.authority_tier!r}"
        )
    if record.verification_status != UNVERIFIED_STATUS:
        raise CorpusValidationError(
            f"{prefix}: verification_status must be {UNVERIFIED_STATUS}, "
            f"got {record.verification_status!r}"
        )
    word_count = record.excerpt_word_count
    if word_count >= MAX_OFFICIAL_EXCERPT_WORDS_EXCLUSIVE:
        raise CorpusValidationError(
            f"{prefix}: short_source_excerpt has {word_count} words; "
            f"must be < {MAX_OFFICIAL_EXCERPT_WORDS_EXCLUSIVE}"
        )
    expected_score_eligible = _score_eligible_from_tier(record.authority_tier)
    if record.score_eligible != expected_score_eligible:
        raise CorpusValidationError(
            f"{prefix}: score_eligible must be {str(expected_score_eligible).lower()} "
            f"for authority_tier={record.authority_tier}"
        )
    if not record.risk_categories:
        raise CorpusValidationError(f"{prefix}: risk_categories must not be empty")


def _parse_knowledge_cards(rows: list[Any]) -> tuple[KnowledgeCardRecord, ...]:
    records: list[KnowledgeCardRecord] = []
    for idx, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            raise CorpusValidationError(
                f"{KNOWLEDGE_CARDS_FILE.filename}:{idx}: row is not a mapping"
            )
        _require_columns(KNOWLEDGE_CARDS_FILE.filename, row, KNOWLEDGE_CARD_COLUMNS, idx)
        record = KnowledgeCardRecord(
            card_id=_required_text_in_file(row, "card_id", idx, KNOWLEDGE_CARDS_FILE.filename),
            authority_tier=_required_text_in_file(
                row, "authority_tier", idx, KNOWLEDGE_CARDS_FILE.filename
            ),
            source_ids=_required_string_list(
                row, "source_ids", idx, KNOWLEDGE_CARDS_FILE.filename
            ),
            risk_categories=_required_string_list(
                row, "risk_categories", idx, KNOWLEDGE_CARDS_FILE.filename
            ),
            evidence_ids=_string_list(row, "evidence_ids", idx, KNOWLEDGE_CARDS_FILE.filename),
            score_eligible=_parse_bool(
                _required_text_in_file(row, "score_eligible", idx, KNOWLEDGE_CARDS_FILE.filename),
                idx,
                KNOWLEDGE_CARDS_FILE.filename,
            ),
            public_export=_parse_bool(
                _required_text_in_file(row, "public_export", idx, KNOWLEDGE_CARDS_FILE.filename),
                idx,
                KNOWLEDGE_CARDS_FILE.filename,
            ),
        )
        _validate_knowledge_card(record, idx)
        records.append(record)
    return tuple(records)


def _validate_knowledge_card(record: KnowledgeCardRecord, line_number: int) -> None:
    prefix = f"{KNOWLEDGE_CARDS_FILE.filename}:{line_number}: {record.card_id}"
    if record.authority_tier not in BC_AUTHORITY_TIERS:
        raise CorpusValidationError(
            f"{prefix}: authority_tier must be B, C, or B/C; got {record.authority_tier!r}"
        )
    _validate_private_source_ids(prefix, record.source_ids)
    if record.score_eligible:
        raise CorpusValidationError(f"{prefix}: B/C knowledge cards must be score_eligible=false")
    if record.public_export:
        raise CorpusValidationError(f"{prefix}: B/C knowledge cards must be public_export=false")
    if not record.risk_categories:
        raise CorpusValidationError(f"{prefix}: risk_categories must not be empty")


def _parse_checklist_items(rows: list[Any]) -> tuple[ChecklistItemRecord, ...]:
    records: list[ChecklistItemRecord] = []
    for idx, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            raise CorpusValidationError(f"{CHECKLIST_FILE.filename}:{idx}: row is not a mapping")
        _require_columns(CHECKLIST_FILE.filename, row, CHECKLIST_COLUMNS, idx)
        educational_source_ids = _string_list(
            row, "educational_source_ids", idx, CHECKLIST_FILE.filename
        )
        practical_source_ids = _string_list(
            row, "practical_source_ids", idx, CHECKLIST_FILE.filename
        )
        source_ids = (*educational_source_ids, *practical_source_ids)
        record = ChecklistItemRecord(
            check_id=_required_text_in_file(row, "check_id", idx, CHECKLIST_FILE.filename),
            risk_category=_required_text_in_file(
                row, "risk_category", idx, CHECKLIST_FILE.filename
            ),
            source_ids=source_ids,
            official_evidence_ids=_string_list(
                row, "official_evidence_ids", idx, CHECKLIST_FILE.filename
            ),
            score_eligible=_parse_bool(
                _required_text_in_file(row, "score_eligible", idx, CHECKLIST_FILE.filename),
                idx,
                CHECKLIST_FILE.filename,
            ),
            public_export=_optional_public_export(row, idx, CHECKLIST_FILE.filename),
        )
        _validate_checklist_item(record, idx)
        records.append(record)
    return tuple(records)


def _validate_checklist_item(record: ChecklistItemRecord, line_number: int) -> None:
    prefix = f"{CHECKLIST_FILE.filename}:{line_number}: {record.check_id}"
    if record.source_ids:
        _validate_private_source_ids(prefix, record.source_ids)
    if record.score_eligible:
        raise CorpusValidationError(f"{prefix}: checklist items must be score_eligible=false")
    if record.public_export:
        raise CorpusValidationError(f"{prefix}: checklist items must be public_export=false")
    if not record.risk_category:
        raise CorpusValidationError(f"{prefix}: risk_category is required")


def _parse_glossary_terms(rows: list[Any]) -> tuple[GlossaryTermRecord, ...]:
    records: list[GlossaryTermRecord] = []
    for idx, row in enumerate(rows, start=2):
        if not isinstance(row, dict):
            raise CorpusValidationError(f"{GLOSSARY_FILE.filename}:{idx}: row is not a mapping")
        _require_columns(GLOSSARY_FILE.filename, row, GLOSSARY_COLUMNS, idx)
        source_ids = _split_source_id_list(
            _required_text_in_file(row, "source_ids", idx, GLOSSARY_FILE.filename)
        )
        record = GlossaryTermRecord(
            canonical_id=_required_text_in_file(row, "canonical_id", idx, GLOSSARY_FILE.filename),
            risk_category=_required_text_in_file(row, "risk_category", idx, GLOSSARY_FILE.filename),
            source_ids=source_ids,
            generated_translation=_parse_bool(
                _required_text_in_file(row, "generated_translation", idx, GLOSSARY_FILE.filename),
                idx,
                GLOSSARY_FILE.filename,
            ),
            score_eligible=_parse_bool(
                _required_text_in_file(row, "score_eligible", idx, GLOSSARY_FILE.filename),
                idx,
                GLOSSARY_FILE.filename,
            ),
        )
        _validate_glossary_term(record, idx)
        records.append(record)
    return tuple(records)


def _validate_glossary_term(record: GlossaryTermRecord, line_number: int) -> None:
    prefix = f"{GLOSSARY_FILE.filename}:{line_number}: {record.canonical_id}"
    _validate_private_source_ids(prefix, record.source_ids)
    if record.score_eligible:
        raise CorpusValidationError(f"{prefix}: B/C glossary terms must be score_eligible=false")
    if not record.risk_category:
        raise CorpusValidationError(f"{prefix}: risk_category is required")


def _require_columns(
    filename: str, row: dict[Any, Any], expected_columns: frozenset[str], line_number: int
) -> None:
    missing_columns = expected_columns.difference(row.keys())
    if missing_columns:
        raise CorpusValidationError(
            f"{filename}:{line_number}: missing columns: {', '.join(sorted(missing_columns))}"
        )


def _required_text_in_file(row: dict[Any, Any], key: str, line_number: int, filename: str) -> str:
    value = row.get(key)
    text = "" if value is None else str(value).strip()
    if not text:
        raise CorpusValidationError(f"{filename}:{line_number}: {key} is required")
    return text


def _required_text(row: dict[Any, Any], key: str, line_number: int) -> str:
    return _required_text_in_file(row, key, line_number, EVIDENCE_FILE.filename)


def _parse_bool(value: str, line_number: int, filename: str = EVIDENCE_FILE.filename) -> bool:
    normalized = value.strip().lower()
    if normalized in {"true", "y", "yes", "1"}:
        return True
    if normalized in {"false", "n", "no", "0"}:
        return False
    raise CorpusValidationError(f"{filename}:{line_number}: invalid boolean value {value!r}")


def _split_semicolon_list(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split(";") if item.strip())


def _string_list(row: dict[Any, Any], key: str, line_number: int, filename: str) -> tuple[str, ...]:
    value = row.get(key)
    if value is None:
        return ()
    if isinstance(value, list):
        return tuple(str(item).strip() for item in value if str(item).strip())
    raise CorpusValidationError(f"{filename}:{line_number}: {key} must be a list")


def _required_string_list(
    row: dict[Any, Any], key: str, line_number: int, filename: str
) -> tuple[str, ...]:
    values = _string_list(row, key, line_number, filename)
    if not values:
        raise CorpusValidationError(f"{filename}:{line_number}: {key} must not be empty")
    return values


def _split_source_id_list(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.replace("|", ";").split(";") if item.strip())


def _optional_public_export(row: dict[Any, Any], line_number: int, filename: str) -> bool:
    if "public_export" not in row or row.get("public_export") in {None, ""}:
        return False
    return _parse_bool(str(row["public_export"]), line_number, filename)


def _validate_private_source_ids(prefix: str, source_ids: tuple[str, ...]) -> None:
    if not source_ids:
        raise CorpusValidationError(f"{prefix}: source_ids must not be empty")
    invalid = sorted(
        source_id for source_id in source_ids if not source_id.startswith(PRIVATE_SOURCE_PREFIXES)
    )
    if invalid:
        raise CorpusValidationError(
            f"{prefix}: expected B/C source_ids only, got {', '.join(invalid)}"
        )


def _validate_expected_count(filename: str, actual: int, expected: int | None) -> None:
    if expected is not None and actual != expected:
        raise CorpusValidationError(
            f"{filename} record count mismatch: expected {expected}, got {actual}"
        )


def _score_eligible_from_tier(authority_tier: str) -> bool:
    return authority_tier in SCORING_AUTHORITY_TIERS


def _word_count(text: str) -> int:
    return len(text.split())


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

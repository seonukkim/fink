#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

MAX_OFFICIAL_EXCERPT_WORDS_EXCLUSIVE = 15
PRIVATE_AUTHORITY_TIERS = frozenset({"B", "C", "B/C"})
PRIVATE_SOURCE_PREFIXES = ("B-", "C-")
UNKNOWN_LICENSE = "UNKNOWN"

SOURCE_MANIFEST = Path("stage-0/01_SOURCE_MANIFEST.csv")
EVIDENCE_MATRIX = Path("stage-1/14_MASTER_EVIDENCE_MATRIX.csv")
KNOWLEDGE_CARDS = Path("stage-1/15_MASTER_KNOWLEDGE_CARDS.jsonl")
CHECKLIST_ITEMS = Path("stage-1/11_MASTER_CREATOR_CHECKLIST.jsonl")
GLOSSARY = Path("stage-1/13_MASTER_BILINGUAL_GLOSSARY.csv")

TEXT_SUFFIXES = frozenset(
    {
        ".csv",
        ".html",
        ".json",
        ".jsonl",
        ".md",
        ".py",
        ".rst",
        ".sh",
        ".toml",
        ".txt",
        ".yaml",
        ".yml",
    }
)
PRIVATE_BOOK_MARKERS = (
    "B-KLL",
    "C-WLF",
    "KLL-",
    "WLF-",
    "korean_law_and_life",
    "webtoon_lawyer_friend",
)
HANGUL_RE = re.compile(r"[\uac00-\ud7a3]")


@dataclass(frozen=True)
class AuditViolation:
    code: str
    location: str
    detail: str

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "location": self.location, "detail": self.detail}


@dataclass(frozen=True)
class SourceLicense:
    source_id: str
    authority_tier: str
    public_export: bool
    license_status: str

    @property
    def is_private_reference(self) -> bool:
        return self.authority_tier in PRIVATE_AUTHORITY_TIERS or self.source_id.startswith(
            PRIVATE_SOURCE_PREFIXES
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "source_id": self.source_id,
            "authority_tier": self.authority_tier,
            "public_export": self.public_export,
            "license_status": self.license_status,
        }


@dataclass(frozen=True)
class CopyrightAuditReport:
    corpus_present: bool
    corpus_counts: dict[str, int]
    license_status_counts: dict[str, int]
    license_status_by_source_id: dict[str, str]
    evidence_license_status: dict[str, str]
    scanned_public_files: int
    violations: tuple[AuditViolation, ...]

    @property
    def ok(self) -> bool:
        return not self.violations

    def as_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "corpus_present": self.corpus_present,
            "corpus_counts": dict(self.corpus_counts),
            "license_status_counts": dict(self.license_status_counts),
            "license_status_by_source_id": dict(self.license_status_by_source_id),
            "evidence_license_status": dict(self.evidence_license_status),
            "scanned_public_files": self.scanned_public_files,
            "violations": [violation.as_dict() for violation in self.violations],
        }


def run_audit(
    repo_root: Path,
    *,
    corpus_dir: Path | None = None,
    public_files: list[Path] | None = None,
) -> CopyrightAuditReport:
    root = repo_root.resolve()
    corpus = corpus_dir.resolve() if corpus_dir is not None else root / "data" / "corpus"
    violations: list[AuditViolation] = []
    corpus_counts: dict[str, int] = {}
    source_records: dict[str, SourceLicense] = {}
    evidence_license_status: dict[str, str] = {}

    corpus_present = _corpus_has_audit_inputs(corpus)
    if corpus_present:
        source_records = _audit_source_manifest(corpus, violations)
        corpus_counts["sources"] = len(source_records)
        evidence_count = _audit_evidence_matrix(
            corpus,
            source_records,
            evidence_license_status,
            violations,
        )
        if evidence_count is not None:
            corpus_counts["evidence_records"] = evidence_count
        card_count = _audit_knowledge_cards(corpus, source_records, violations)
        if card_count is not None:
            corpus_counts["knowledge_cards"] = card_count
        checklist_count = _audit_checklist(corpus, source_records, violations)
        if checklist_count is not None:
            corpus_counts["checklist_items"] = checklist_count
        glossary_count = _audit_glossary(corpus, source_records, violations)
        if glossary_count is not None:
            corpus_counts["glossary_terms"] = glossary_count

    candidates = public_files if public_files is not None else public_candidate_files(root)
    scanned_public_files = _audit_public_files(root, candidates, violations)
    license_counts = Counter(source.license_status for source in source_records.values())

    return CopyrightAuditReport(
        corpus_present=corpus_present,
        corpus_counts=corpus_counts,
        license_status_counts=dict(sorted(license_counts.items())),
        license_status_by_source_id={
            source_id: source.license_status for source_id, source in sorted(source_records.items())
        },
        evidence_license_status=dict(sorted(evidence_license_status.items())),
        scanned_public_files=scanned_public_files,
        violations=tuple(violations),
    )


def public_candidate_files(repo_root: Path) -> list[Path]:
    proc = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    rels = [item for item in proc.stdout.split("\0") if item]
    return [repo_root / rel for rel in rels]


def format_summary(report: CopyrightAuditReport) -> str:
    details = [
        f"violations={len(report.violations)}",
        f"corpus_present={str(report.corpus_present).lower()}",
        f"public_files_scanned={report.scanned_public_files}",
    ]
    if report.license_status_counts:
        statuses = ",".join(
            f"{status}:{count}" for status, count in report.license_status_counts.items()
        )
        details.append(f"license_status={statuses}")
    return "copyright_audit " + " ".join(details)


def _corpus_has_audit_inputs(corpus_dir: Path) -> bool:
    return any(
        (corpus_dir / rel).is_file()
        for rel in (SOURCE_MANIFEST, EVIDENCE_MATRIX, KNOWLEDGE_CARDS, CHECKLIST_ITEMS, GLOSSARY)
    )


def _audit_source_manifest(
    corpus_dir: Path, violations: list[AuditViolation]
) -> dict[str, SourceLicense]:
    path = corpus_dir / SOURCE_MANIFEST
    if not path.is_file():
        _add(violations, "SOURCE_MANIFEST_MISSING", path, "source manifest is required")
        return {}
    rows, fieldnames = _read_csv(path)
    if "license_status" not in fieldnames:
        _add(
            violations,
            "LICENSE_STATUS_NOT_SURFACED",
            path,
            "source manifest must expose license_status",
        )
        return {}
    records: dict[str, SourceLicense] = {}
    for line_number, row in enumerate(rows, start=2):
        location = f"{_rel(path)}:{line_number}"
        source_id = _required(row, "source_id", location, violations)
        if not source_id:
            continue
        license_status = row.get("license_status", "").strip()
        if not license_status:
            _add(violations, "LICENSE_STATUS_EMPTY", location, "license_status is required")
        public_export = _bool(row.get("public_export", ""), default=False)
        authority_tier = row.get("authority_tier", "").strip()
        source = SourceLicense(
            source_id=source_id,
            authority_tier=authority_tier,
            public_export=public_export,
            license_status=license_status,
        )
        records[source_id] = source
        if _license_is_unknown(license_status) and public_export:
            _add(
                violations,
                "UNKNOWN_LICENSE_PUBLIC_EXPORT",
                location,
                f"{source_id} has license_status={license_status!r} but public_export=true",
            )
        if source.is_private_reference and public_export:
            _add(
                violations,
                "PRIVATE_REFERENCE_PUBLIC_EXPORT",
                location,
                f"{source_id} is B/C material and must never be public",
            )
    return records


def _audit_evidence_matrix(
    corpus_dir: Path,
    sources: dict[str, SourceLicense],
    evidence_license_status: dict[str, str],
    violations: list[AuditViolation],
) -> int | None:
    path = corpus_dir / EVIDENCE_MATRIX
    if not path.is_file():
        return None
    rows, fieldnames = _read_csv(path)
    for column in ("evidence_id", "source_id", "short_source_excerpt"):
        if column not in fieldnames:
            _add(violations, "EVIDENCE_COLUMN_MISSING", path, f"{column} column is required")
            return len(rows)
    for line_number, row in enumerate(rows, start=2):
        location = f"{_rel(path)}:{line_number}"
        evidence_id = row.get("evidence_id", "").strip() or f"line-{line_number}"
        source_id = row.get("source_id", "").strip()
        excerpt = row.get("short_source_excerpt", "")
        word_count = _word_count(excerpt)
        if word_count >= MAX_OFFICIAL_EXCERPT_WORDS_EXCLUSIVE:
            _add(
                violations,
                "OFFICIAL_EXCERPT_TOO_LONG",
                location,
                f"{evidence_id} excerpt has {word_count} words; must be < 15",
            )
        source = sources.get(source_id)
        if source is None:
            evidence_license_status[evidence_id] = "MISSING_SOURCE"
            _add(
                violations,
                "SOURCE_LICENSE_NOT_SURFACED",
                location,
                f"{evidence_id} references source_id={source_id!r} absent from source manifest",
            )
        else:
            evidence_license_status[evidence_id] = source.license_status
    return len(rows)


def _audit_knowledge_cards(
    corpus_dir: Path,
    sources: dict[str, SourceLicense],
    violations: list[AuditViolation],
) -> int | None:
    path = corpus_dir / KNOWLEDGE_CARDS
    if not path.is_file():
        return None
    rows = _read_jsonl(path, violations)
    for index, row in enumerate(rows, start=1):
        location = f"{_rel(path)}:{index}"
        public_export = _bool(row.get("public_export", False), default=False)
        authority_tier = str(row.get("authority_tier", "")).strip()
        source_ids = _list_value(row.get("source_ids"))
        if public_export and (
            authority_tier in PRIVATE_AUTHORITY_TIERS
            or any(source_id.startswith(PRIVATE_SOURCE_PREFIXES) for source_id in source_ids)
        ):
            _add(
                violations,
                "PRIVATE_REFERENCE_PUBLIC_EXPORT",
                location,
                f"{row.get('card_id', 'unknown')} is B/C material and must never be public",
            )
        _audit_unknown_license_public_export(
            public_export,
            source_ids,
            sources,
            location,
            violations,
        )
    return len(rows)


def _audit_checklist(
    corpus_dir: Path,
    sources: dict[str, SourceLicense],
    violations: list[AuditViolation],
) -> int | None:
    path = corpus_dir / CHECKLIST_ITEMS
    if not path.is_file():
        return None
    rows = _read_jsonl(path, violations)
    for index, row in enumerate(rows, start=1):
        location = f"{_rel(path)}:{index}"
        public_export = _bool(row.get("public_export", False), default=False)
        source_ids = [
            *_list_value(row.get("educational_source_ids")),
            *_list_value(row.get("practical_source_ids")),
        ]
        has_private_source = any(
            source_id.startswith(PRIVATE_SOURCE_PREFIXES) for source_id in source_ids
        )
        if public_export and has_private_source:
            _add(
                violations,
                "PRIVATE_REFERENCE_PUBLIC_EXPORT",
                location,
                f"{row.get('check_id', 'unknown')} is B/C material and must never be public",
            )
        _audit_unknown_license_public_export(
            public_export,
            source_ids,
            sources,
            location,
            violations,
        )
    return len(rows)


def _audit_glossary(
    corpus_dir: Path,
    sources: dict[str, SourceLicense],
    violations: list[AuditViolation],
) -> int | None:
    path = corpus_dir / GLOSSARY
    if not path.is_file():
        return None
    rows, _fieldnames = _read_csv(path)
    for line_number, row in enumerate(rows, start=2):
        location = f"{_rel(path)}:{line_number}"
        public_export = _bool(row.get("public_export", False), default=False)
        source_ids = _split_source_ids(row.get("source_ids", ""))
        has_private_source = any(
            source_id.startswith(PRIVATE_SOURCE_PREFIXES) for source_id in source_ids
        )
        if public_export and has_private_source:
            _add(
                violations,
                "PRIVATE_REFERENCE_PUBLIC_EXPORT",
                location,
                f"{row.get('canonical_id', 'unknown')} is B/C material and must never be public",
            )
        _audit_unknown_license_public_export(
            public_export,
            source_ids,
            sources,
            location,
            violations,
        )
    return len(rows)


def _audit_unknown_license_public_export(
    public_export: bool,
    source_ids: list[str],
    sources: dict[str, SourceLicense],
    location: str,
    violations: list[AuditViolation],
) -> None:
    if not public_export:
        return
    for source_id in source_ids:
        source = sources.get(source_id)
        if source is not None and _license_is_unknown(source.license_status):
            _add(
                violations,
                "UNKNOWN_LICENSE_PUBLIC_EXPORT",
                location,
                f"{source_id} has license_status={source.license_status!r} but record is public",
            )


def _audit_public_files(
    repo_root: Path,
    public_files: list[Path],
    violations: list[AuditViolation],
) -> int:
    scanned = 0
    for path in public_files:
        if not path.is_file() or path.name == ".env" or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        try:
            sample = path.read_bytes()[:4096]
        except OSError:
            continue
        if b"\0" in sample:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        scanned += 1
        _audit_private_passage(repo_root, path, text, violations)
    return scanned


def _audit_private_passage(
    repo_root: Path,
    path: Path,
    text: str,
    violations: list[AuditViolation],
) -> None:
    marker_present = any(marker in text for marker in PRIVATE_BOOK_MARKERS)
    if not marker_present:
        return
    for line_number, line in enumerate(text.splitlines(), start=1):
        hangul_count = len(HANGUL_RE.findall(line))
        if hangul_count >= 120:
            _add(
                violations,
                "LONG_PRIVATE_BOOK_PASSAGE",
                f"{path.resolve().relative_to(repo_root)}:{line_number}",
                "private B/C source marker appears with a long Korean passage",
            )


def _read_csv(path: Path) -> tuple[list[dict[str, str]], tuple[str, ...]]:
    with path.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        rows = [
            {str(key): str(value or "") for key, value in row.items() if key is not None}
            for row in reader
        ]
        fieldnames = tuple(reader.fieldnames or ())
    return rows, fieldnames


def _read_jsonl(path: Path, violations: list[AuditViolation]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            _add(violations, "JSONL_PARSE_ERROR", f"{_rel(path)}:{line_number}", str(exc))
            continue
        if isinstance(payload, dict):
            records.append(payload)
        else:
            _add(
                violations,
                "JSONL_RECORD_NOT_OBJECT",
                f"{_rel(path)}:{line_number}",
                "record must be a JSON object",
            )
    return records


def _required(
    row: dict[str, str],
    key: str,
    location: str,
    violations: list[AuditViolation],
) -> str:
    value = row.get(key, "").strip()
    if not value:
        _add(violations, "REQUIRED_FIELD_EMPTY", location, f"{key} is required")
    return value


def _bool(value: object, *, default: bool) -> bool:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "t", "y", "yes"}:
        return True
    if normalized in {"0", "false", "f", "n", "no"}:
        return False
    return default


def _list_value(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return _split_source_ids(value)
    return []


def _split_source_ids(value: str) -> list[str]:
    return [item.strip() for item in value.replace("|", ";").split(";") if item.strip()]


def _license_is_unknown(status: str) -> bool:
    return status.strip().upper().startswith(UNKNOWN_LICENSE)


def _word_count(text: str) -> int:
    return len(text.split())


def _rel(path: Path) -> str:
    return path.as_posix()


def _add(
    violations: list[AuditViolation],
    code: str,
    location: str | Path,
    detail: str,
) -> None:
    violations.append(AuditViolation(code=code, location=str(location), detail=detail))


def _repo_root_from_cwd() -> Path:
    proc = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        check=True,
        capture_output=True,
        text=True,
    )
    return Path(proc.stdout.strip())


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the FInk copyright/license audit.")
    parser.add_argument("--repo-root", type=Path, default=None)
    parser.add_argument("--corpus-dir", type=Path, default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    repo_root = args.repo_root or _repo_root_from_cwd()
    report = run_audit(repo_root, corpus_dir=args.corpus_dir)
    if args.json:
        print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2))
    else:
        print(format_summary(report))
        for violation in report.violations:
            print(
                f"{violation.code}: {violation.location}: {violation.detail}",
                file=sys.stderr,
            )
    raise SystemExit(0 if report.ok else 1)


if __name__ == "__main__":
    main()

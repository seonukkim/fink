#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.copyright_audit import run_audit

SCORE_ELIGIBLE_TIERS = frozenset({"A0", "A1", "A2"})
PRIVATE_TIERS = frozenset({"B", "C", "B/C"})
PRIVATE_SOURCE_PREFIXES = ("B-", "C-")
METHOD_OR_COURSE_TIERS = frozenset({"M", "M1", "M2", "M3", "R0", "D0"})

SOURCE_MANIFEST = Path("stage-0/01_SOURCE_MANIFEST.csv")
EVIDENCE_MATRIX = Path("stage-1/14_MASTER_EVIDENCE_MATRIX.csv")
KNOWLEDGE_CARDS = Path("stage-1/15_MASTER_KNOWLEDGE_CARDS.jsonl")
CHECKLIST_ITEMS = Path("stage-1/11_MASTER_CREATOR_CHECKLIST.jsonl")
GLOSSARY = Path("stage-1/13_MASTER_BILINGUAL_GLOSSARY.csv")
REQUIRED_CORPUS_FILES = (
    SOURCE_MANIFEST,
    EVIDENCE_MATRIX,
    KNOWLEDGE_CARDS,
    CHECKLIST_ITEMS,
    GLOSSARY,
)

MAX_OFFICIAL_EXCERPT_WORDS_EXCLUSIVE = 15
LOG_SUFFIXES = frozenset({".log", ".out", ".err", ".trace", ".txt"})
DEFAULT_LOG_DIRS = ("logs", "runs", "artifacts")
KO_ARTICLE_RE = "\uc81c\\s*\\d+\\s*\uc870"
KO_CONTRACT_TERMS_RE = "(\uac11|\uc744|\uacc4\uc57d|\ub300\uae08|\uc800\uc791\uad8c)"
KO_PARTY_TERMS_RE = "(\uac11|\uc744)"
KO_OBLIGATION_TERMS_RE = "(\uacc4\uc57d|\ub300\uae08|\uad8c\ub9ac|\uc758\ubb34)"

CONTRACT_TEXT_PATTERNS = (
    re.compile(
        r"\b(P3_USER_EPHEMERAL|raw_contract_text|contract_text|uploaded_text|"
        r"ocr_text|clause_text)\b",
        re.I,
    ),
    re.compile(KO_ARTICLE_RE + ".{0,80}" + KO_CONTRACT_TERMS_RE),
    re.compile(
        KO_PARTY_TERMS_RE
        + ".{0,40}"
        + KO_OBLIGATION_TERMS_RE
        + ".{0,40}"
        + KO_PARTY_TERMS_RE
    ),
)


@dataclass(frozen=True)
class InvariantViolation:
    code: str
    location: str
    detail: str

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "location": self.location, "detail": self.detail}


@dataclass(frozen=True)
class InvariantReport:
    corpus_present: bool
    corpus_counts: dict[str, int]
    scanned_public_files: int
    scanned_log_files: int
    violations: tuple[InvariantViolation, ...]

    @property
    def ok(self) -> bool:
        return not self.violations

    def as_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "corpus_present": self.corpus_present,
            "corpus_counts": dict(self.corpus_counts),
            "scanned_public_files": self.scanned_public_files,
            "scanned_log_files": self.scanned_log_files,
            "violations": [violation.as_dict() for violation in self.violations],
        }


def run_invariant_suite(
    repo_root: Path,
    *,
    corpus_dir: Path | None = None,
    public_files: list[Path] | None = None,
    log_dirs: list[Path] | None = None,
) -> InvariantReport:
    root = repo_root.resolve()
    corpus = corpus_dir.resolve() if corpus_dir is not None else root / "data" / "corpus"
    violations: list[InvariantViolation] = []
    corpus_counts: dict[str, int] = {}
    source_rows: dict[str, dict[str, str]] = {}
    corpus_present = _corpus_has_any_inputs(corpus)

    if corpus_present:
        _audit_required_files(corpus, violations)
        source_rows = _audit_source_manifest(corpus, corpus_counts, violations)
        _audit_evidence_matrix(corpus, source_rows, corpus_counts, violations)
        _audit_knowledge_cards(corpus, source_rows, corpus_counts, violations)
        _audit_checklist(corpus, corpus_counts, violations)
        _audit_glossary(corpus, source_rows, corpus_counts, violations)

    copyright_report = run_audit(root, corpus_dir=corpus, public_files=public_files)
    violations.extend(
        InvariantViolation(item.code, item.location, item.detail)
        for item in copyright_report.violations
        if item.code not in _codes(violations)
    )

    log_files = _log_files(root, log_dirs)
    scanned_log_files = _audit_log_files(root, log_files, violations)

    return InvariantReport(
        corpus_present=corpus_present,
        corpus_counts=corpus_counts,
        scanned_public_files=copyright_report.scanned_public_files,
        scanned_log_files=scanned_log_files,
        violations=tuple(violations),
    )


def format_summary(report: InvariantReport) -> str:
    parts = [
        f"violations={len(report.violations)}",
        f"corpus_present={str(report.corpus_present).lower()}",
        f"public_files_scanned={report.scanned_public_files}",
        f"log_files_scanned={report.scanned_log_files}",
    ]
    if report.corpus_counts:
        counts = ",".join(f"{key}:{value}" for key, value in sorted(report.corpus_counts.items()))
        parts.append(f"corpus_counts={counts}")
    return "invariant_suite " + " ".join(parts)


def _corpus_has_any_inputs(corpus_dir: Path) -> bool:
    return any((corpus_dir / rel).is_file() for rel in REQUIRED_CORPUS_FILES)


def _audit_required_files(corpus_dir: Path, violations: list[InvariantViolation]) -> None:
    for rel in REQUIRED_CORPUS_FILES:
        path = corpus_dir / rel
        if not path.is_file():
            _add(violations, "CORPUS_FILE_MISSING", path, "required invariant input is missing")


def _audit_source_manifest(
    corpus_dir: Path,
    corpus_counts: dict[str, int],
    violations: list[InvariantViolation],
) -> dict[str, dict[str, str]]:
    path = corpus_dir / SOURCE_MANIFEST
    if not path.is_file():
        return {}
    rows, fieldnames = _read_csv(path)
    corpus_counts["sources"] = len(rows)
    required = {"source_id", "source_class", "authority_tier", "score_eligible", "public_export"}
    _require_columns(path, fieldnames, required, violations)
    by_id: dict[str, dict[str, str]] = {}
    for line_number, row in enumerate(rows, start=2):
        source_id = row.get("source_id", "").strip()
        if source_id:
            by_id[source_id] = row
        location = f"{_rel(path)}:{line_number}"
        tier = _authority_tier(row)
        score_eligible = _bool(row.get("score_eligible", ""), default=False)
        public_export = _bool(row.get("public_export", ""), default=False)
        private_reference = _is_private_reference(row)
        if score_eligible and tier not in SCORE_ELIGIBLE_TIERS:
            _add(
                violations,
                "NON_AUTHORITY_SOURCE_SCORE_ELIGIBLE",
                location,
                f"{source_id or 'unknown'} has tier {tier!r} but score_eligible=true",
            )
        if private_reference and score_eligible:
            _add(
                violations,
                "BC_SOURCE_SCORE_ELIGIBLE",
                location,
                f"{source_id or 'unknown'} is B/C material and must not score",
            )
        if private_reference and public_export:
            _add(
                violations,
                "PRIVATE_REFERENCE_PUBLIC_EXPORT",
                location,
                f"{source_id or 'unknown'} is B/C material and must not be public",
            )
        if score_eligible and tier in METHOD_OR_COURSE_TIERS:
            _add(
                violations,
                "METHOD_OR_COURSE_SOURCE_SCORE_ELIGIBLE",
                location,
                f"{source_id or 'unknown'} is method/course material and must not score",
            )
    return by_id


def _audit_evidence_matrix(
    corpus_dir: Path,
    sources: dict[str, dict[str, str]],
    corpus_counts: dict[str, int],
    violations: list[InvariantViolation],
) -> None:
    path = corpus_dir / EVIDENCE_MATRIX
    if not path.is_file():
        return
    rows, fieldnames = _read_csv(path)
    corpus_counts["evidence_records"] = len(rows)
    required = {
        "evidence_id",
        "source_id",
        "source_class",
        "authority_tier",
        "short_source_excerpt",
        "score_eligible",
    }
    _require_columns(path, fieldnames, required, violations)
    for line_number, row in enumerate(rows, start=2):
        location = f"{_rel(path)}:{line_number}"
        evidence_id = row.get("evidence_id", "").strip() or f"line-{line_number}"
        tier = _authority_tier(row)
        score_eligible = _bool(row.get("score_eligible", ""), default=False)
        expected = tier in SCORE_ELIGIBLE_TIERS
        if score_eligible != expected:
            _add(
                violations,
                "EVIDENCE_ELIGIBILITY_MISMATCH",
                location,
                f"{evidence_id} score_eligible={score_eligible} but tier={tier!r}",
            )
        if score_eligible and _source_is_non_authority(row.get("source_id", ""), sources):
            _add(
                violations,
                "EVIDENCE_NON_AUTHORITY_SOURCE_SCORE_ELIGIBLE",
                location,
                f"{evidence_id} scores while its source is not A0/A1/A2",
            )
        if expected:
            word_count = len(row.get("short_source_excerpt", "").split())
            if word_count >= MAX_OFFICIAL_EXCERPT_WORDS_EXCLUSIVE:
                _add(
                    violations,
                    "OFFICIAL_EXCERPT_TOO_LONG",
                    location,
                    f"{evidence_id} excerpt has {word_count} words; must be < 15",
                )


def _audit_knowledge_cards(
    corpus_dir: Path,
    sources: dict[str, dict[str, str]],
    corpus_counts: dict[str, int],
    violations: list[InvariantViolation],
) -> None:
    path = corpus_dir / KNOWLEDGE_CARDS
    if not path.is_file():
        return
    rows = _read_jsonl(path, violations)
    corpus_counts["knowledge_cards"] = len(rows)
    for line_number, row in enumerate(rows, start=1):
        location = f"{_rel(path)}:{line_number}"
        card_id = str(row.get("card_id") or f"line-{line_number}")
        source_ids = _list_value(row.get("source_ids"))
        score_eligible = _bool(row.get("score_eligible", False), default=False)
        public_export = _bool(row.get("public_export", False), default=False)
        private_reference = _record_has_private_source(source_ids, sources) or _tier_is_private(
            str(row.get("authority_tier", ""))
        )
        if score_eligible:
            _add(
                violations,
                "KNOWLEDGE_CARD_SCORE_ELIGIBLE",
                location,
                f"{card_id} must remain explanatory/question material, not scoring evidence",
            )
        if private_reference and public_export:
            _add(
                violations,
                "PRIVATE_REFERENCE_PUBLIC_EXPORT",
                location,
                f"{card_id} contains B/C material and must not be public",
            )


def _audit_checklist(
    corpus_dir: Path,
    corpus_counts: dict[str, int],
    violations: list[InvariantViolation],
) -> None:
    path = corpus_dir / CHECKLIST_ITEMS
    if not path.is_file():
        return
    rows = _read_jsonl(path, violations)
    corpus_counts["checklist_items"] = len(rows)
    for line_number, row in enumerate(rows, start=1):
        location = f"{_rel(path)}:{line_number}"
        check_id = str(row.get("check_id") or f"line-{line_number}")
        if _bool(row.get("score_eligible", False), default=False):
            _add(
                violations,
                "CHECKLIST_SCORE_ELIGIBLE",
                location,
                f"{check_id} is a non-scoring question and must not score",
            )
        if "public_export" in row and _bool(row.get("public_export"), default=False):
            source_ids = [
                *_list_value(row.get("educational_source_ids")),
                *_list_value(row.get("practical_source_ids")),
            ]
            if any(source_id.startswith(PRIVATE_SOURCE_PREFIXES) for source_id in source_ids):
                _add(
                    violations,
                    "PRIVATE_REFERENCE_PUBLIC_EXPORT",
                    location,
                    f"{check_id} contains B/C material and must not be public",
                )


def _audit_glossary(
    corpus_dir: Path,
    sources: dict[str, dict[str, str]],
    corpus_counts: dict[str, int],
    violations: list[InvariantViolation],
) -> None:
    path = corpus_dir / GLOSSARY
    if not path.is_file():
        return
    rows, fieldnames = _read_csv(path)
    corpus_counts["glossary_terms"] = len(rows)
    _require_columns(path, fieldnames, {"canonical_id", "source_ids", "score_eligible"}, violations)
    for line_number, row in enumerate(rows, start=2):
        location = f"{_rel(path)}:{line_number}"
        canonical_id = row.get("canonical_id", "").strip() or f"line-{line_number}"
        source_ids = _split_source_ids(row.get("source_ids", ""))
        if _bool(row.get("score_eligible", ""), default=False):
            _add(
                violations,
                "GLOSSARY_SCORE_ELIGIBLE",
                location,
                f"{canonical_id} is alias/terminology material and must not score",
            )
        if "public_export" in row and _bool(row.get("public_export", ""), default=False):
            if _record_has_private_source(source_ids, sources):
                _add(
                    violations,
                    "PRIVATE_REFERENCE_PUBLIC_EXPORT",
                    location,
                    f"{canonical_id} contains B/C material and must not be public",
                )


def _log_files(repo_root: Path, log_dirs: list[Path] | None) -> list[Path]:
    roots: list[Path] = []
    if log_dirs is not None:
        roots.extend(log_dirs)
    else:
        env_dirs = os.environ.get("FINK_INVARIANT_LOG_DIRS", "")
        roots.extend(Path(item) for item in env_dirs.split(os.pathsep) if item)
        roots.extend(repo_root / rel for rel in DEFAULT_LOG_DIRS)
    files: list[Path] = []
    seen: set[Path] = set()
    for root in roots:
        path = root if root.is_absolute() else repo_root / root
        if not path.exists() or ".fink" in path.parts:
            continue
        if path.is_file():
            candidates = [path]
        else:
            candidates = [candidate for candidate in path.rglob("*") if candidate.is_file()]
        for candidate in candidates:
            resolved = candidate.resolve()
            if resolved in seen or candidate.suffix.lower() not in LOG_SUFFIXES:
                continue
            seen.add(resolved)
            files.append(candidate)
    return sorted(files)


def _audit_log_files(
    repo_root: Path,
    log_files: list[Path],
    violations: list[InvariantViolation],
) -> int:
    scanned = 0
    for path in log_files:
        try:
            sample = path.read_bytes()[:4096]
        except OSError:
            continue
        if b"\0" in sample:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        scanned += 1
        for pattern in CONTRACT_TEXT_PATTERNS:
            if pattern.search(text):
                _add(
                    violations,
                    "CONTRACT_TEXT_IN_LOG",
                    _display_path(repo_root, path),
                    "logs must contain opaque ids/counts/timings/error codes only",
                )
                break
    return scanned


def _require_columns(
    path: Path,
    fieldnames: tuple[str, ...],
    required: set[str],
    violations: list[InvariantViolation],
) -> None:
    missing = sorted(required - set(fieldnames))
    for column in missing:
        _add(violations, "COLUMN_MISSING", path, f"{column} column is required")


def _authority_tier(row: dict[str, str]) -> str:
    tier = _normalize_tier(row.get("authority_tier", ""))
    if tier:
        return tier
    return _normalize_tier(row.get("source_class", ""))


def _normalize_tier(value: str) -> str:
    text = str(value).strip()
    if not text:
        return ""
    if text.startswith("M"):
        return text.split()[0]
    if text.startswith("R0"):
        return "R0"
    if text.startswith("D0"):
        return "D0"
    return text


def _tier_is_private(value: str) -> bool:
    return _normalize_tier(value) in PRIVATE_TIERS


def _is_private_reference(row: dict[str, str]) -> bool:
    source_id = row.get("source_id", "").strip()
    return (
        _tier_is_private(row.get("authority_tier", ""))
        or _tier_is_private(row.get("source_class", ""))
        or source_id.startswith(PRIVATE_SOURCE_PREFIXES)
    )


def _source_is_non_authority(source_id: str, sources: dict[str, dict[str, str]]) -> bool:
    source = sources.get(source_id.strip())
    if source is None:
        return False
    return _authority_tier(source) not in SCORE_ELIGIBLE_TIERS


def _record_has_private_source(
    source_ids: list[str],
    sources: dict[str, dict[str, str]],
) -> bool:
    for source_id in source_ids:
        if source_id.startswith(PRIVATE_SOURCE_PREFIXES):
            return True
        source = sources.get(source_id)
        if source is not None and _is_private_reference(source):
            return True
    return False


def _read_csv(path: Path) -> tuple[list[dict[str, str]], tuple[str, ...]]:
    with path.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        rows = [
            {str(key): str(value or "") for key, value in row.items() if key is not None}
            for row in reader
        ]
        return rows, tuple(reader.fieldnames or ())


def _read_jsonl(path: Path, violations: list[InvariantViolation]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            _add(violations, "JSONL_PARSE_ERROR", f"{_rel(path)}:{line_number}", str(exc))
            continue
        if isinstance(payload, dict):
            rows.append(payload)
        else:
            _add(
                violations,
                "JSONL_RECORD_NOT_OBJECT",
                f"{_rel(path)}:{line_number}",
                "record must be a JSON object",
            )
    return rows


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


def _codes(violations: list[InvariantViolation]) -> set[str]:
    return {violation.code for violation in violations}


def _display_path(repo_root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root).as_posix()
    except ValueError:
        return path.as_posix()


def _rel(path: Path) -> str:
    return path.as_posix()


def _add(
    violations: list[InvariantViolation],
    code: str,
    location: str | Path,
    detail: str,
) -> None:
    violations.append(InvariantViolation(code=code, location=str(location), detail=detail))


def _repo_root_from_cwd() -> Path:
    proc = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        check=True,
        capture_output=True,
        text=True,
    )
    return Path(proc.stdout.strip())


def main() -> None:
    parser = argparse.ArgumentParser(description="Run FInk INV-1/INV-8 invariant gates.")
    parser.add_argument("--repo-root", type=Path, default=None)
    parser.add_argument("--corpus-dir", type=Path, default=None)
    parser.add_argument("--log-dir", type=Path, action="append", default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    repo_root = args.repo_root or _repo_root_from_cwd()
    report = run_invariant_suite(
        repo_root,
        corpus_dir=args.corpus_dir,
        log_dirs=args.log_dir,
    )
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

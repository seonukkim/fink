#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any


DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[1]

CLAIM_HEADER = [
    "claim_id",
    "section",
    "claim_text",
    "evidence_file",
    "evidence_key",
    "status",
    "reviewer",
    "notes",
]
RESULT_HEADER = [
    "result_id",
    "experiment_id",
    "metric",
    "value",
    "artifact_path",
    "status",
    "reviewer",
    "notes",
]
FIGURE_HEADER = [
    "figure_id",
    "title",
    "source_artifact",
    "paper_section",
    "site_section",
    "status",
    "notes",
]

CLAIM_ID_RE = re.compile(r"\bCLM-[A-Z0-9][A-Z0-9-]*\b")
FIGURE_ID_RE = re.compile(r"\bFIG-[A-Z0-9][A-Z0-9-]*\b")
RESULT_ID_RE = re.compile(r"\bFINK-[A-Z0-9][A-Z0-9@_-]*(?:-[A-Z0-9@_-]+)*\b")
METRIC_RE = re.compile(r"\bEV-[A-Z0-9@-]+\b")
NUMBER_RE = re.compile(r"(?<![A-Za-z])[-+]?\d+(?:\.\d+)?(?![A-Za-z])")
MARKDOWN_IMAGE_RE = re.compile(r"!\[[^\]]*]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
HTML_IMG_RE = re.compile(r"<img\b[^>]*>", re.I | re.S)
HTML_ATTR_RE = re.compile(r"([A-Za-z_:][-A-Za-z0-9_:.]*)\s*=\s*([\"'])(.*?)\2", re.S)

RESULT_EVIDENCE_FILES = {"RESULT_LEDGER.csv", "docs/paper/RESULT_LEDGER.csv"}
RUNTIME_METRIC_FIELDS = {
    "EV-OFFLINE": "network_attempts",
    "EV-PRIV": "leak_count",
    "EV-LAT": "max_latency_seconds",
    "EV-MEM": "max_peak_memory_bytes",
}
SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"hf_[A-Za-z0-9]{20,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"gh[pousr]_[A-Za-z0-9_]{20,}"),
]
FORBIDDEN_DFL_RE = re.compile(r"trained\s+end-to-end\s+DFL", re.I)
LONG_KOREAN_RE = re.compile(r"[가-힣][^.\n]{180,}[가-힣]")
BAD_CURRENT_LAW_RE = re.compile(r"\bcurrent[- ]law\b", re.I)
CURRENT_LAW_CAVEAT_RE = re.compile(
    r"\b(not|no|avoid|avoids|until|open|pending|unverified|verification|date-stamped)\b",
    re.I,
)
RESULT_WORD_RE = re.compile(r"\b(measured|observed|reported|reports?|achieved|scored)\b", re.I)
EVALUATIVE_WORD_RE = re.compile(
    r"\b(best|better|optimal|outperform(?:s|ed)?|validated|accurate|reliable|improves?)\b",
    re.I,
)
NEGATION_RE = re.compile(r"\b(no|not|never|without|avoid|avoids|cannot|must not|does not)\b", re.I)


@dataclass(frozen=True)
class PaperSyncViolation:
    code: str
    path: str
    message: str
    line: int | None = None

    def as_dict(self) -> dict[str, object]:
        data: dict[str, object] = {
            "code": self.code,
            "path": self.path,
            "message": self.message,
        }
        if self.line is not None:
            data["line"] = self.line
        return data


@dataclass(frozen=True)
class PaperSyncReport:
    violations: list[PaperSyncViolation]
    checked: dict[str, int]

    @property
    def ok(self) -> bool:
        return not self.violations

    def summary(self) -> str:
        parts = [f"{key}={value}" for key, value in sorted(self.checked.items())]
        suffix = ", ".join(parts)
        return f"PAPER_SYNC_OK {suffix}" if self.ok else f"PAPER_SYNC_FAIL {suffix}"

    def format_violations(self, limit: int = 20) -> str:
        if not self.violations:
            return self.summary()
        lines = [self.summary()]
        for violation in self.violations[:limit]:
            location = violation.path
            if violation.line is not None:
                location = f"{location}:{violation.line}"
            lines.append(f"{violation.code} {location}: {violation.message}")
        remaining = len(self.violations) - limit
        if remaining > 0:
            lines.append(f"... {remaining} more violation(s)")
        return "\n".join(lines)

    def as_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "checked": self.checked,
            "violations": [violation.as_dict() for violation in self.violations],
        }


def check_paper_sync(repo_root: Path = DEFAULT_REPO_ROOT) -> PaperSyncReport:
    root = repo_root.resolve()
    violations: list[PaperSyncViolation] = []
    checked = {
        "claim_rows": 0,
        "figure_rows": 0,
        "note_files": 0,
        "result_rows": 0,
        "site_files": 0,
        "template_files": 0,
    }

    claim_rows = read_csv_rows(root, "docs/paper/CLAIM_LEDGER.csv", CLAIM_HEADER, violations)
    result_rows = read_csv_rows(root, "docs/paper/RESULT_LEDGER.csv", RESULT_HEADER, violations)
    figure_rows = read_csv_rows(root, "docs/paper/FIGURE_REGISTRY.csv", FIGURE_HEADER, violations)
    checked["claim_rows"] = len(claim_rows)
    checked["result_rows"] = len(result_rows)
    checked["figure_rows"] = len(figure_rows)

    claims = index_rows(claim_rows, "claim_id", "docs/paper/CLAIM_LEDGER.csv", violations)
    results = index_rows(result_rows, "result_id", "docs/paper/RESULT_LEDGER.csv", violations)
    figures = index_rows(figure_rows, "figure_id", "docs/paper/FIGURE_REGISTRY.csv", violations)

    check_claim_rows(root, claim_rows, results, violations)
    check_result_rows(root, result_rows, violations)
    check_figure_rows(root, figure_rows, violations)
    checked["note_files"] = check_note_files(root, claims, results, figures, violations)
    checked["site_files"] = check_site_files(root, figures, violations)
    checked["template_files"] = check_template_untouched(root, violations)

    return PaperSyncReport(violations=violations, checked=checked)


def read_csv_rows(
    root: Path,
    rel_path: str,
    expected_header: list[str],
    violations: list[PaperSyncViolation],
) -> list[dict[str, str]]:
    path = root / rel_path
    if not path.is_file():
        violations.append(PaperSyncViolation("MISSING_LEDGER", rel_path, "ledger file missing"))
        return []

    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        header = list(reader.fieldnames or [])
        if header != expected_header:
            violations.append(
                PaperSyncViolation(
                    "LEDGER_HEADER_MISMATCH",
                    rel_path,
                    f"expected {expected_header!r}, got {header!r}",
                )
            )
            return []
        rows: list[dict[str, str]] = []
        for raw in reader:
            rows.append({key: (raw.get(key) or "").strip() for key in expected_header})
    return rows


def index_rows(
    rows: list[dict[str, str]],
    key: str,
    rel_path: str,
    violations: list[PaperSyncViolation],
) -> dict[str, dict[str, str]]:
    indexed: dict[str, dict[str, str]] = {}
    for line, row in enumerate(rows, start=2):
        value = row.get(key, "").strip()
        if not value:
            violations.append(
                PaperSyncViolation("LEDGER_ID_MISSING", rel_path, f"{key} is empty", line)
            )
            continue
        if value in indexed:
            violations.append(
                PaperSyncViolation(
                    "LEDGER_ID_DUPLICATE",
                    rel_path,
                    f"duplicate {key}: {value}",
                    line,
                )
            )
            continue
        indexed[value] = row
    return indexed


def check_claim_rows(
    root: Path,
    claim_rows: list[dict[str, str]],
    results: dict[str, dict[str, str]],
    violations: list[PaperSyncViolation],
) -> None:
    for line, claim in enumerate(claim_rows, start=2):
        if not is_result_backed_claim(claim):
            continue
        result_id = claim["evidence_key"]
        result = results.get(result_id)
        if result is None:
            violations.append(
                PaperSyncViolation(
                    "RESULT_CLAIM_MISSING_RESULT",
                    "docs/paper/CLAIM_LEDGER.csv",
                    f"{claim['claim_id']} points at missing result {result_id}",
                    line,
                )
            )
            continue
        if result["status"] != "measured":
            violations.append(
                PaperSyncViolation(
                    "RESULT_CLAIM_NOT_MEASURED",
                    "docs/paper/CLAIM_LEDGER.csv",
                    (
                        f"{claim['claim_id']} points at result {result_id} "
                        f"with status={result['status']}"
                    ),
                    line,
                )
            )
        if not result["artifact_path"]:
            violations.append(
                PaperSyncViolation(
                    "RESULT_CLAIM_MISSING_ARTIFACT",
                    "docs/paper/CLAIM_LEDGER.csv",
                    f"{claim['claim_id']} points at result {result_id} without artifact_path",
                    line,
                )
            )
        if text_mentions_result_value(claim["claim_text"]) and not text_contains_value(
            claim["claim_text"], result["value"]
        ):
            violations.append(
                PaperSyncViolation(
                    "FABRICATED_CLAIM_VALUE",
                    "docs/paper/CLAIM_LEDGER.csv",
                    f"{claim['claim_id']} text does not contain measured value {result['value']}",
                    line,
                )
            )
        artifact = root / result["artifact_path"]
        if artifact.is_file() and not artifact_supports_result_value(artifact, result):
            violations.append(
                PaperSyncViolation(
                    "FABRICATED_RESULT_VALUE",
                    "docs/paper/CLAIM_LEDGER.csv",
                    (
                        f"{result_id} value {result['value']} is not supported by "
                        f"{result['artifact_path']}"
                    ),
                    line,
                )
            )


def check_result_rows(
    root: Path,
    result_rows: list[dict[str, str]],
    violations: list[PaperSyncViolation],
) -> None:
    for line, result in enumerate(result_rows, start=2):
        if result["status"] != "measured":
            continue
        if parse_decimal(result["value"]) is None:
            violations.append(
                PaperSyncViolation(
                    "MEASURED_RESULT_VALUE_INVALID",
                    "docs/paper/RESULT_LEDGER.csv",
                    f"{result['result_id']} has nonnumeric measured value {result['value']!r}",
                    line,
                )
            )
        artifact_rel = result["artifact_path"]
        if not artifact_rel:
            violations.append(
                PaperSyncViolation(
                    "MEASURED_RESULT_ARTIFACT_MISSING",
                    "docs/paper/RESULT_LEDGER.csv",
                    f"{result['result_id']} has no artifact_path",
                    line,
                )
            )
            continue
        artifact = root / artifact_rel
        if not artifact.is_file():
            violations.append(
                PaperSyncViolation(
                    "MEASURED_RESULT_ARTIFACT_MISSING",
                    "docs/paper/RESULT_LEDGER.csv",
                    f"{result['result_id']} artifact does not exist: {artifact_rel}",
                    line,
                )
            )
            continue
        if not artifact_supports_result_value(artifact, result):
            violations.append(
                PaperSyncViolation(
                    "FABRICATED_RESULT_VALUE",
                    "docs/paper/RESULT_LEDGER.csv",
                    (
                        f"{result['result_id']} value {result['value']} is not supported by "
                        f"{artifact_rel}"
                    ),
                    line,
                )
            )


def check_figure_rows(
    root: Path,
    figure_rows: list[dict[str, str]],
    violations: list[PaperSyncViolation],
) -> None:
    for line, figure in enumerate(figure_rows, start=2):
        source = figure["source_artifact"]
        if not source:
            violations.append(
                PaperSyncViolation(
                    "FIGURE_SOURCE_MISSING",
                    "docs/paper/FIGURE_REGISTRY.csv",
                    f"{figure['figure_id']} has no source_artifact",
                    line,
                )
            )
            continue
        if not (root / source).is_file():
            violations.append(
                PaperSyncViolation(
                    "FIGURE_SOURCE_MISSING",
                    "docs/paper/FIGURE_REGISTRY.csv",
                    f"{figure['figure_id']} source_artifact does not exist: {source}",
                    line,
                )
            )


def is_result_backed_claim(claim: dict[str, str]) -> bool:
    return claim["status"] == "measured" or claim["evidence_file"] in RESULT_EVIDENCE_FILES


def check_note_files(
    root: Path,
    claims: dict[str, dict[str, str]],
    results: dict[str, dict[str, str]],
    figures: dict[str, dict[str, str]],
    violations: list[PaperSyncViolation],
) -> int:
    paper_dir = root / "docs" / "paper"
    if not paper_dir.is_dir():
        violations.append(
            PaperSyncViolation("PAPER_NOTES_MISSING", "docs/paper", "directory missing")
        )
        return 0

    count = 0
    figure_sources = {row["source_artifact"] for row in figures.values()}
    for path in sorted(paper_dir.glob("*.md")):
        count += 1
        rel_path = rel(root, path)
        in_fence = False
        lines = path.read_text(encoding="utf-8").splitlines()
        for line_no, line in enumerate(lines, start=1):
            stripped = line.strip()
            if stripped.startswith("```"):
                in_fence = not in_fence
                continue
            if in_fence:
                continue

            check_text_honesty(rel_path, line_no, line, violations)
            claim_ids = set(CLAIM_ID_RE.findall(line))
            figure_ids = set(FIGURE_ID_RE.findall(line))

            for claim_id in sorted(claim_ids):
                claim = claims.get(claim_id)
                if claim is None:
                    violations.append(
                        PaperSyncViolation(
                            "UNKNOWN_CLAIM_ID",
                            rel_path,
                            f"claim id is not in CLAIM_LEDGER.csv: {claim_id}",
                            line_no,
                        )
                    )
                    continue
                if is_result_backed_claim(claim):
                    result = results.get(claim["evidence_key"])
                    if result is not None and line_has_public_numeric_value(line):
                        clean_line = remove_identifiers(line)
                        if not text_contains_value(clean_line, result["value"]):
                            violations.append(
                                PaperSyncViolation(
                                    "FABRICATED_NOTE_VALUE",
                                    rel_path,
                                    (
                                        f"{claim_id} cites {result['result_id']} "
                                        f"but not value {result['value']}"
                                    ),
                                    line_no,
                                )
                            )

            claim_context = claim_context_for_line(lines, line_no)
            if line_needs_claim_id(line) and not CLAIM_ID_RE.search(claim_context):
                violations.append(
                    PaperSyncViolation(
                        "UNSUPPORTED_PAPER_CLAIM",
                        rel_path,
                        "quantitative/evaluative result-like claim lacks a CLAIM_LEDGER id",
                        line_no,
                    )
                )

            for figure_id in sorted(figure_ids):
                if figure_id not in figures:
                    violations.append(
                        PaperSyncViolation(
                            "ORPHAN_FIGURE",
                            rel_path,
                            f"figure id is not in FIGURE_REGISTRY.csv: {figure_id}",
                            line_no,
                        )
                    )

            for image_ref in MARKDOWN_IMAGE_RE.findall(line):
                source = normalize_asset_reference(root, path, image_ref)
                if source not in figure_sources:
                    violations.append(
                        PaperSyncViolation(
                            "ORPHAN_FIGURE",
                            rel_path,
                            f"markdown image is not registered in FIGURE_REGISTRY.csv: {source}",
                            line_no,
                        )
                    )
    return count


def claim_context_for_line(lines: list[str], line_no: int) -> str:
    line = lines[line_no - 1]
    if line.lstrip().startswith("|"):
        return line
    start = line_no - 1
    while start > 0 and lines[start - 1].strip() and not lines[start - 1].lstrip().startswith("#"):
        start -= 1
    end = line_no
    while end < len(lines) and lines[end].strip() and not lines[end].lstrip().startswith("#"):
        end += 1
    return " ".join(lines[start:end])


def check_site_files(
    root: Path,
    figures: dict[str, dict[str, str]],
    violations: list[PaperSyncViolation],
) -> int:
    site_files = [path for path in [root / "site" / "index.html"] if path.is_file()]
    for path in site_files:
        rel_path = rel(root, path)
        text = path.read_text(encoding="utf-8")
        for line_no, line in enumerate(text.splitlines(), start=1):
            check_text_honesty(rel_path, line_no, line, violations)
            for figure_id in set(FIGURE_ID_RE.findall(line)):
                if figure_id not in figures:
                    violations.append(
                        PaperSyncViolation(
                            "ORPHAN_FIGURE",
                            rel_path,
                            f"figure id is not in FIGURE_REGISTRY.csv: {figure_id}",
                            line_no,
                        )
                    )

        for match in HTML_IMG_RE.finditer(text):
            tag = match.group(0)
            attrs = parse_html_attrs(tag)
            figure_id = attrs.get("data-figure-id", "")
            src = attrs.get("src", "")
            line_no = text.count("\n", 0, match.start()) + 1
            if not figure_id:
                violations.append(
                    PaperSyncViolation(
                        "ORPHAN_FIGURE",
                        rel_path,
                        "project-page img tag is missing data-figure-id",
                        line_no,
                    )
                )
                continue
            figure = figures.get(figure_id)
            if figure is None:
                violations.append(
                    PaperSyncViolation(
                        "ORPHAN_FIGURE",
                        rel_path,
                        f"project-page img figure id is not registered: {figure_id}",
                        line_no,
                    )
                )
                continue
            if src:
                normalized_src = normalize_asset_reference(root, path, src)
                if normalized_src != figure["source_artifact"]:
                    violations.append(
                        PaperSyncViolation(
                            "FIGURE_SOURCE_MISMATCH",
                            rel_path,
                            (
                                f"{figure_id} src {normalized_src} != registry "
                                f"{figure['source_artifact']}"
                            ),
                            line_no,
                        )
                    )
    return len(site_files)


def check_text_honesty(
    rel_path: str,
    line_no: int,
    line: str,
    violations: list[PaperSyncViolation],
) -> None:
    if FORBIDDEN_DFL_RE.search(line):
        violations.append(
            PaperSyncViolation(
                "FORBIDDEN_DFL_CLAIM",
                rel_path,
                "use DFL-inspired wording only",
                line_no,
            )
        )
    if BAD_CURRENT_LAW_RE.search(line) and not CURRENT_LAW_CAVEAT_RE.search(line):
        violations.append(
            PaperSyncViolation(
                "CURRENT_LAW_CLAIM_UNGATED",
                rel_path,
                "current-law references must be caveated while HR-01 remains open",
                line_no,
            )
        )
    if LONG_KOREAN_RE.search(line):
        violations.append(
            PaperSyncViolation(
                "LONG_PRIVATE_OR_OFFICIAL_EXCERPT",
                rel_path,
                "long Korean source-like passage is not allowed in paper-visible files",
                line_no,
            )
        )
    if "<blockquote" in line.lower() or line.startswith("> "):
        violations.append(
            PaperSyncViolation(
                "LONG_PRIVATE_OR_OFFICIAL_EXCERPT",
                rel_path,
                "paper-visible notes/page must not include source block quotes",
                line_no,
            )
        )
    for pattern in SECRET_PATTERNS:
        if pattern.search(line):
            violations.append(
                PaperSyncViolation(
                    "SECRET_IN_PAPER_VISIBLE_TEXT",
                    rel_path,
                    "secret-like token appears in paper-visible text",
                    line_no,
                )
            )
            break


def line_needs_claim_id(line: str) -> bool:
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return False
    if "CLAIM_LEDGER.csv" in stripped or "RESULT_LEDGER.csv" in stripped:
        return False
    if "FIGURE_REGISTRY.csv" in stripped:
        return False
    if NEGATION_RE.search(stripped) and not line_has_public_numeric_value(stripped):
        return False

    has_metric = bool(METRIC_RE.search(stripped))
    has_number = line_has_public_numeric_value(stripped)
    result_like = bool(RESULT_WORD_RE.search(stripped))
    evaluative = bool(EVALUATIVE_WORD_RE.search(stripped)) and not NEGATION_RE.search(
        stripped
    )
    return (
        (has_metric and (has_number or result_like))
        or (has_number and result_like)
        or evaluative
    )


def line_has_public_numeric_value(line: str) -> bool:
    return any(
        parse_decimal(token) is not None
        for token in NUMBER_RE.findall(remove_identifiers(line))
    )


def text_mentions_result_value(text: str) -> bool:
    return bool(RESULT_WORD_RE.search(text) and line_has_public_numeric_value(text))


def remove_identifiers(text: str) -> str:
    cleaned = CLAIM_ID_RE.sub(" ", text)
    cleaned = FIGURE_ID_RE.sub(" ", cleaned)
    cleaned = RESULT_ID_RE.sub(" ", cleaned)
    cleaned = METRIC_RE.sub(" ", cleaned)
    return cleaned


def text_contains_value(text: str, expected_value: str) -> bool:
    expected = parse_decimal(expected_value)
    if expected is None:
        return False
    for token in NUMBER_RE.findall(remove_identifiers(text)):
        value = parse_decimal(token)
        if value == expected:
            return True
    return False


def artifact_supports_result_value(artifact: Path, result: dict[str, str]) -> bool:
    expected = parse_decimal(result["value"])
    if expected is None:
        return False
    if artifact.suffix.lower() != ".json":
        return artifact.is_file()
    try:
        data = json.loads(artifact.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    values = collect_artifact_values(data, result)
    return expected in values


def collect_artifact_values(data: Any, result: dict[str, str]) -> set[Decimal]:
    values: set[Decimal] = set()
    collect_embedded_result_rows(data, result, values)
    collect_metric_values(data, result, values)
    collect_runtime_values(data, result, values)
    collect_pass_rate_values(data, result, values)
    return values


def collect_embedded_result_rows(data: Any, result: dict[str, str], values: set[Decimal]) -> None:
    if isinstance(data, dict):
        result_ledger = data.get("result_ledger")
        if isinstance(result_ledger, dict):
            rows = result_ledger.get("rows")
            if isinstance(rows, list):
                for row in rows:
                    if not isinstance(row, dict):
                        continue
                    if row_matches_result(row, result):
                        add_decimal(values, row.get("value"))
        for value in data.values():
            collect_embedded_result_rows(value, result, values)
    elif isinstance(data, list):
        for item in data:
            collect_embedded_result_rows(item, result, values)


def row_matches_result(row: dict[Any, Any], result: dict[str, str]) -> bool:
    row_result_id = str(row.get("result_id", ""))
    row_experiment_id = str(row.get("experiment_id", ""))
    row_metric = str(row.get("metric", ""))
    if row_result_id and row_result_id == result["result_id"]:
        return True
    return row_experiment_id == result["experiment_id"] and row_metric == result["metric"]


def collect_metric_values(data: Any, result: dict[str, str], values: set[Decimal]) -> None:
    if isinstance(data, dict):
        metric_values = data.get("metric_values")
        if isinstance(metric_values, dict):
            collect_from_metric_values(metric_values, result, values)
        for value in data.values():
            collect_metric_values(value, result, values)
    elif isinstance(data, list):
        for item in data:
            collect_metric_values(item, result, values)


def collect_from_metric_values(
    metric_values: dict[Any, Any],
    result: dict[str, str],
    values: set[Decimal],
) -> None:
    metric = result["metric"]
    direct = metric_values.get(metric)
    if isinstance(direct, int | float | str):
        add_decimal(values, direct)

    arm = experiment_arm(result["experiment_id"])
    if arm:
        arm_values = metric_values.get(arm)
        if isinstance(arm_values, dict):
            add_decimal(values, arm_values.get(metric))

    for nested in metric_values.values():
        if isinstance(nested, dict):
            add_decimal(values, nested.get(metric))


def experiment_arm(experiment_id: str) -> str:
    if ":" not in experiment_id:
        return ""
    return experiment_id.rsplit(":", 1)[1]


def collect_runtime_values(data: Any, result: dict[str, str], values: set[Decimal]) -> None:
    field = RUNTIME_METRIC_FIELDS.get(result["metric"])
    if not field:
        return
    if isinstance(data, dict):
        if field in data:
            add_decimal(values, data[field])
        for value in data.values():
            collect_runtime_values(value, result, values)
    elif isinstance(data, list):
        for item in data:
            collect_runtime_values(item, result, values)


def collect_pass_rate_values(data: Any, result: dict[str, str], values: set[Decimal]) -> None:
    if not isinstance(data, dict):
        return
    metrics = data.get("metrics")
    if not isinstance(metrics, dict):
        return
    metric = metrics.get(result["metric"])
    if not isinstance(metric, dict):
        return
    passed = parse_decimal(metric.get("passed"))
    total = parse_decimal(metric.get("total"))
    if passed is not None and total not in {None, Decimal("0")}:
        values.add(normalize_decimal(passed / total))


def add_decimal(values: set[Decimal], raw: object) -> None:
    value = parse_decimal(raw)
    if value is not None:
        values.add(value)


def parse_decimal(raw: object) -> Decimal | None:
    if raw is None:
        return None
    try:
        return normalize_decimal(Decimal(str(raw).strip()))
    except (InvalidOperation, ValueError):
        return None


def normalize_decimal(value: Decimal) -> Decimal:
    if value == 0:
        return Decimal("0")
    return value.normalize()


def parse_html_attrs(tag: str) -> dict[str, str]:
    return {match.group(1).lower(): match.group(3) for match in HTML_ATTR_RE.finditer(tag)}


def normalize_asset_reference(root: Path, source_file: Path, reference: str) -> str:
    if re.match(r"^[a-z][a-z0-9+.-]*:", reference, re.I):
        return reference
    target = (source_file.parent / reference).resolve()
    try:
        return target.relative_to(root).as_posix()
    except ValueError:
        return reference


def check_template_untouched(root: Path, violations: list[PaperSyncViolation]) -> int:
    state_path = root / "loop" / "STATE.json"
    if not state_path.is_file():
        violations.append(
            PaperSyncViolation("TEMPLATE_HASH_STATE_MISSING", "loop/STATE.json", "missing")
        )
        return 0
    state = json.loads(state_path.read_text(encoding="utf-8"))
    expected = state.get("icml_template_hashes")
    if not isinstance(expected, dict):
        violations.append(
            PaperSyncViolation(
                "TEMPLATE_HASH_STATE_MISSING",
                "loop/STATE.json",
                "icml_template_hashes missing or invalid",
            )
        )
        return 0
    expected_hashes = {str(key): str(value) for key, value in expected.items()}
    current = template_hashes(root)
    if expected_hashes != current:
        expected_paths = set(expected_hashes)
        current_paths = set(current)
        for missing in sorted(expected_paths - current_paths):
            violations.append(
                PaperSyncViolation("TEMPLATE_MODIFIED", missing, "template file missing")
            )
        for extra in sorted(current_paths - expected_paths):
            violations.append(PaperSyncViolation("TEMPLATE_MODIFIED", extra, "new template file"))
        changed_paths = sorted(
            path
            for path in expected_paths & current_paths
            if expected_hashes[path] != current[path]
        )
        for changed in changed_paths:
            violations.append(
                PaperSyncViolation("TEMPLATE_MODIFIED", changed, "template file hash changed")
            )
    return len(current)


def template_hashes(root: Path) -> dict[str, str]:
    template_root = root / "paper" / "template" / "icml2026"
    hashes: dict[str, str] = {}
    if not template_root.exists():
        return hashes
    for path in sorted(item for item in template_root.rglob("*") if item.is_file()):
        hashes[rel(root, path)] = sha256_file(path)
    return hashes


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def rel(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root).as_posix()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check FInk paper/result/figure/template sync.")
    parser.add_argument("--repo-root", type=Path, default=DEFAULT_REPO_ROOT)
    parser.add_argument("--json", action="store_true", help="emit machine-readable report")
    args = parser.parse_args(argv)

    report = check_paper_sync(args.repo_root)
    if args.json:
        print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2))
    else:
        print(report.format_violations())
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

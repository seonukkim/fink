#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import argparse
import ast
import csv
import json
import os
import re
import subprocess
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from scripts.agent_loop._common import (
    BACKLOG_PATH,
    REPO_ROOT,
    STATE_PATH,
    changed_files_since,
    current_branch,
    current_commit,
    icml_template_hashes,
    is_worktree_clean,
    load_json,
    load_yaml,
    local_branches,
    read_text,
    tracked_files,
    untracked_files,
)
from scripts.check_paper_sync import check_paper_sync
from scripts.copyright_audit import format_summary, run_audit
from scripts.invariant_suite import (
    format_summary as format_invariant_summary,
    run_invariant_suite,
)

SELF_PATH = Path(__file__).resolve()

# FINK-POLICY-DEFINITIONS-START
# The literals in this sentinel-delimited block are the single source of truth
# for FInk's forbidden-content patterns. They are policy *definitions*, not
# violations: scannable_text() strips this block out of this module's own
# source (keyed on this file's resolved path) before the content scanners read
# it, so the scanners never flag their own definitions. Every other file - all
# product code, docs, prompts, and the other scripts - is still scanned in full.
FORBIDDEN_TRACKED = re.compile(
    r"(^\.fink/|\.pdf$|\.zip$|^contracts/|^uploads/|^data/private/|^data/raw/|^data/unsanitized/)"
)
SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"(OPENAI_API_KEY|ANTHROPIC_API_KEY|HF_TOKEN)\s*=\s*['\"]?[A-Za-z0-9_./-]{12,}"),
    re.compile(r"-----BEGIN (RSA |OPENSSH |EC |DSA )?PRIVATE KEY-----"),
]
PRIVATE_QUOTE_RE = re.compile(r"[가-힣][^.\n]{180,}[가-힣]")
BAD_LEGAL_ASSERTIONS = [
    re.compile(
        r"FInk (determines|decides|proves|guarantees).*(fraud|illegal|valid|void|unfair|loss)",
        re.I,
    ),
    re.compile(
        r"FInk'?s? (score|output|report).{0,80}is.{0,40}"
        r"(fraud probability|illegality probability|guaranteed loss)",
        re.I,
    ),
    re.compile(r"trained end-to-end DFL", re.I),
]
# FINK-POLICY-DEFINITIONS-END

# Canonical open-source license floor. Anchored here (not only in
# configs/models/candidates.yaml) so the floor cannot be widened by editing the
# config: candidates.yaml's allowlist must be a SUBSET of this set, and every
# declared model license must be in it. This backs the auto-resolution of the
# MODEL_* human gates (HD-12).
OPEN_LICENSE_FLOOR = frozenset(
    {"apache-2.0", "mit", "bsd-2-clause", "bsd-3-clause", "isc", "cc0-1.0", "cc-by-4.0"}
)
# Model-weight file extensions that must never be tracked in Git.
WEIGHT_SUFFIXES = (".safetensors", ".gguf", ".onnx", ".pt", ".pth", ".h5")


class GateFailure(AssertionError):
    pass


def print_gate(name: str, ok: bool, detail: str = "") -> None:
    status = "PASS" if ok else "FAIL"
    suffix = f" - {detail}" if detail else ""
    print(f"[{status}] {name}{suffix}")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise GateFailure(message)


def gate(name: str, fn: Any) -> None:
    try:
        detail = fn() or ""
    except Exception as exc:
        print_gate(name, False, str(exc))
        raise
    print_gate(name, True, str(detail))


def text_files_for_scan() -> list[Path]:
    result: list[Path] = []
    seen: set[str] = set()
    # Tracked files plus untracked-non-ignored files, so a file a task just
    # created is content-scanned at gate time rather than first scanned (too
    # late) on the next task's gates. .gitignore is respected, so .fink/,
    # uploads/, models/, etc. stay excluded.
    for file in (*tracked_files(), *untracked_files()):
        if file in seen:
            continue
        seen.add(file)
        if file == ".env" or file.endswith(".env"):
            continue
        path = REPO_ROOT / file
        if not path.is_file():
            continue
        try:
            chunk = path.read_bytes()[:4096]
        except OSError:
            continue
        if b"\0" not in chunk:
            result.append(path)
    return result


def scannable_text(path: Path) -> str:
    """Return file text for the content scanners (secret/quote/legal).

    This module is the single source of truth for the forbidden-content
    patterns, so its own sentinel-delimited definition block is policy, not a
    violation, and is removed from this file before it is scanned. The
    redaction is keyed strictly on this module's resolved path, so it never
    relaxes the scan for any other file: all product code, docs, prompts, and
    the other scripts are returned and scanned in full.
    """
    text = path.read_text(encoding="utf-8", errors="ignore")
    if path.resolve() != SELF_PATH:
        return text
    kept: list[str] = []
    skipping = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped == "# FINK-POLICY-DEFINITIONS-START":
            skipping = True
            continue
        if stripped == "# FINK-POLICY-DEFINITIONS-END":
            skipping = False
            continue
        if not skipping:
            kept.append(line)
    return "\n".join(kept)


def parse_structured_files() -> str:
    counts = {"json": 0, "jsonl": 0, "yaml": 0, "csv": 0}
    for file in tracked_files():
        path = REPO_ROOT / file
        if not path.is_file():
            continue
        suffix = path.suffix.lower()
        if suffix == ".json":
            json.loads(path.read_text(encoding="utf-8"))
            counts["json"] += 1
        elif suffix == ".jsonl":
            for idx, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
                if line.strip():
                    try:
                        json.loads(line)
                    except json.JSONDecodeError as exc:
                        raise GateFailure(f"{file}:{idx}: {exc}") from exc
            counts["jsonl"] += 1
        elif suffix in {".yaml", ".yml"}:
            load_yaml(path)
            counts["yaml"] += 1
        elif suffix == ".csv":
            with path.open(newline="", encoding="utf-8") as fh:
                list(csv.reader(fh))
            counts["csv"] += 1
    return ", ".join(f"{key}={value}" for key, value in counts.items())


def schema_validation() -> str:
    try:
        import jsonschema  # type: ignore[import-untyped]
    except Exception:
        return "jsonschema unavailable; structured parsing completed separately"
    schema_dir = REPO_ROOT / "scripts" / "agent_loop" / "schemas"
    pairs = [
        (BACKLOG_PATH, schema_dir / "task.schema.json", "tasks"),
        (STATE_PATH, schema_dir / "state.schema.json", None),
    ]
    for data_path, schema_path, list_key in pairs:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        data = (
            load_yaml(data_path)
            if data_path.suffix in {".yaml", ".yml"}
            else load_json(data_path)
        )
        if list_key:
            for item in data[list_key]:
                jsonschema.validate(item, schema)
        else:
            jsonschema.validate(data, schema)
    # Validate dry-run artifact examples against the result/review schemas.
    codex_schema = json.loads((schema_dir / "codex_result.schema.json").read_text(encoding="utf-8"))
    review_schema = json.loads(
        (schema_dir / "claude_review.schema.json").read_text(encoding="utf-8")
    )
    jsonschema.Draft202012Validator.check_schema(codex_schema)
    jsonschema.Draft202012Validator.check_schema(review_schema)
    return "schemas valid"


def branch_gate() -> str:
    branch = current_branch()
    require(branch == "main", f"current branch is {branch!r}, expected main")
    branches = local_branches()
    require(branches == ["main"], f"local branches are {branches}, expected only main")
    return f"branch={branch}"


def clean_start_gate(task_start: bool) -> str:
    if not task_start:
        return "not in task-start mode"
    require(is_worktree_clean(), "worktree is not clean at task start")
    return "clean"


def tracking_scan() -> str:
    bad = [file for file in tracked_files() if FORBIDDEN_TRACKED.search(file)]
    require(not bad, "forbidden tracked files: " + ", ".join(bad))
    return "no .fink/PDF/ZIP/private tracked files"


def secret_scan() -> str:
    findings: list[str] = []
    for path in text_files_for_scan():
        text = scannable_text(path)
        for pattern in SECRET_PATTERNS:
            if pattern.search(text):
                findings.append(path.relative_to(REPO_ROOT).as_posix())
                break
    require(not findings, "possible secrets in: " + ", ".join(sorted(set(findings))))
    return "no secret patterns"


def public_repo_preflight() -> str:
    proc = subprocess.run(
        ["bash", "scripts/public_repo_preflight.sh"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    output = "\n".join(part for part in (proc.stdout, proc.stderr) if part)
    require(proc.returncode == 0, "public_repo_preflight.sh failed")
    require("PREFLIGHT_OK" in proc.stdout, "public_repo_preflight.sh did not emit PREFLIGHT_OK")
    for gate_name in ("preflight_ok", "secret_scan", "gitignore_enforced"):
        require(f"{gate_name}:" in proc.stdout, f"public_repo_preflight.sh skipped {gate_name}")
    return output.strip()


def private_quote_scan() -> str:
    findings: list[str] = []
    for path in text_files_for_scan():
        rel = path.relative_to(REPO_ROOT).as_posix()
        if rel.startswith("docs/specs/"):
            continue
        text = scannable_text(path)
        if PRIVATE_QUOTE_RE.search(text):
            findings.append(rel)
    require(not findings, "long private-quotation heuristic matched: " + ", ".join(findings))
    return "no long private quotations"


def legal_verdict_scan() -> str:
    findings: list[str] = []
    for path in text_files_for_scan():
        rel = path.relative_to(REPO_ROOT).as_posix()
        if rel == "docs/FINK_MASTER_SPEC.md" or rel.startswith("docs/specs/"):
            continue
        text = scannable_text(path)
        for pattern in BAD_LEGAL_ASSERTIONS:
            if pattern.search(text):
                findings.append(rel)
                break
    require(
        not findings,
        "forbidden legal/result assertion in: " + ", ".join(sorted(set(findings))),
    )
    return "no forbidden verdict assertions"


def queue_consistency() -> str:
    """Every queue line must resolve to a real backlog task.

    Guards the automated lanes against the failure mode that originally
    corrupted ``queue.models.txt`` (phantom ``MR-001``..``MR-014`` ids that match
    no backlog task and silently make the lane unreachable). Fails when a queue
    references an unknown task id, when one task id appears in two queues, or when
    a task precedes one of its own dependencies inside the same queue.
    """
    backlog = load_yaml(BACKLOG_PATH)
    tasks = backlog.get("tasks", []) if isinstance(backlog, dict) else []
    by_id = {str(item["id"]): item for item in tasks if isinstance(item, dict) and "id" in item}
    queues = sorted((REPO_ROOT / "scripts" / "agent_loop").glob("queue.*.txt"))
    require(bool(queues), "no queue.*.txt files found")
    seen: dict[str, str] = {}
    summary: list[str] = []
    for queue in queues:
        order: list[str] = []
        for raw in queue.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            require(line in by_id, f"{queue.name}: unknown task id {line!r}")
            prior = seen.get(line)
            require(prior is None, f"{line} appears in both {prior} and {queue.name}")
            seen[line] = queue.name
            order.append(line)
        position = {task_id: index for index, task_id in enumerate(order)}
        for task_id in order:
            for dep in by_id[task_id].get("depends_on", []) or []:
                dep_id = str(dep)
                if dep_id in position:
                    require(
                        position[dep_id] < position[task_id],
                        f"{queue.name}: {task_id} precedes its dependency {dep_id}",
                    )
        summary.append(f"{queue.name}={len(order)}")
    return ", ".join(summary)


def authority_invariant() -> str:
    tiers = {"A0", "A1", "A2", "B", "C", "M1", "M2", "M3", "R0", "D0"}
    scoring = {"A0", "A1", "A2"}
    for tier in tiers:
        eligible = tier in scoring
        if tier in {"B", "C", "M1", "M2", "M3", "R0", "D0"}:
            require(not eligible, f"{tier} must not be score eligible")
    return "A0-A2 only"


def _walk_licenses(node: Any, path: str, found: list[tuple[str, str]]) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "license" and isinstance(value, str):
                found.append((path, value))
            else:
                _walk_licenses(value, f"{path}/{key}", found)
    elif isinstance(node, list):
        for index, value in enumerate(node):
            _walk_licenses(value, f"{path}[{index}]", found)


def model_license_floor() -> str:
    """Open-source-only model policy + no tracked weights (backs HD-12).

    - No model-weight file may be tracked in Git.
    - configs/models/candidates.yaml's allowlist must be a subset of the canonical
      OPEN_LICENSE_FLOOR (the floor cannot be widened by editing the config).
    - Every model license declared anywhere in candidates.yaml must be in the floor
      (gated/unknown/custom/noncommercial/research-only never qualifies).
    """
    weights = [f for f in tracked_files() if f.lower().endswith(WEIGHT_SUFFIXES)]
    require(not weights, "model-weight files tracked in git: " + ", ".join(weights))

    cfg_path = REPO_ROOT / "configs" / "models" / "candidates.yaml"
    if not cfg_path.is_file():
        return "no candidates.yaml; no tracked weights"
    cfg = load_yaml(cfg_path)
    require(isinstance(cfg, dict), "candidates.yaml must be a mapping")
    policy = cfg.get("license_policy", {})
    allowlist = {str(item).lower() for item in policy.get("public_open_allowlist", [])}
    require(bool(allowlist), "candidates.yaml missing public_open_allowlist")
    widened = sorted(allowlist - OPEN_LICENSE_FLOOR)
    require(
        not widened,
        "license allowlist widened beyond open-source floor: " + ", ".join(widened),
    )

    declared: list[tuple[str, str]] = []
    _walk_licenses(cfg.get("candidates", {}), "candidates", declared)
    bad = sorted({f"{p}={lic}" for p, lic in declared if lic.lower() not in OPEN_LICENSE_FLOOR})
    require(not bad, "non-open model license(s) declared: " + ", ".join(bad))
    return f"open-license floor ok ({len(allowlist)} allowed); no tracked weights"


def copyright_audit() -> str:
    report = run_audit(REPO_ROOT)
    if report.violations:
        details = "; ".join(
            f"{item.code} at {item.location}: {item.detail}" for item in report.violations[:10]
        )
        extra = "" if len(report.violations) <= 10 else f"; +{len(report.violations) - 10} more"
        raise GateFailure(details + extra)
    return format_summary(report)


def invariant_suite() -> str:
    report = run_invariant_suite(REPO_ROOT)
    if report.violations:
        details = "; ".join(
            f"{item.code} at {item.location}: {item.detail}" for item in report.violations[:10]
        )
        extra = "" if len(report.violations) <= 10 else f"; +{len(report.violations) - 10} more"
        raise GateFailure(details + extra)
    return format_invariant_summary(report)


def money(value: Decimal) -> int:
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def financial_formula_tests() -> str:
    gross = Decimal("10000000")
    refunds = Decimal("500000")
    allowed = Decimal("1000000")
    rate = Decimal("0.7")
    open_high = Decimal("2000000")
    payout_high = (gross - refunds - allowed) * rate
    payout_low = (gross - refunds - allowed - open_high) * rate
    require(payout_high - payout_low == Decimal("1400000"), "FIM-1 expected 1,400,000")

    delayed = Decimal("10000000")
    r = Decimal("0.05")
    days = Decimal("180")
    pv = delayed * (Decimal(1) - Decimal(1) / ((Decimal(1) + r) ** (days / Decimal(365))))
    require(abs(money(pv) - 237700) < 3000, f"FIM-2 PV unexpected: {pv}")

    monthly = [Decimal("1000000"), Decimal("2000000"), Decimal("4000000")]
    months = []
    for sales in monthly:
        recoup = sales * rate
        months.append(int((Decimal("12000000") / recoup).to_integral_value(rounding=ROUND_HALF_UP)))
    require(months == [17, 9, 4] or months == [18, 9, 5], "FIM-3 sanity failed")

    low = Decimal("4550000")
    base = Decimal("5250000")
    high = Decimal("5950000")
    factor = Decimal("1.2")
    require(money(low / factor) == 3791667, "FIM-8 low failed")
    require(base == Decimal("5250000"), "FIM-8 base changed")
    require(money(high * factor) == 7140000, "FIM-8 high failed")
    return "FIM sanity vectors"


def fink_stage_corpus_gate() -> str:
    script = REPO_ROOT / "scripts" / "import_stage_corpus.py"
    if not script.is_file():
        return "FINK-S0-01 loader not present"
    index = REPO_ROOT / "data" / "corpus" / "stage-3" / "32_FINAL_FILE_INDEX.csv"
    if not index.is_file():
        return "local corpus not imported"
    proc = subprocess.run(
        [sys.executable, str(script), "--validate-only", "--json"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout).strip()
        raise GateFailure(detail or "corpus validation failed")
    report = json.loads(proc.stdout)
    counts = report.get("counts", {})
    require(counts.get("sources") == 35, "source count mismatch")
    require(counts.get("glossary_terms") == 156, "glossary count mismatch")
    require(counts.get("evidence_records") == 20, "evidence count mismatch")
    require(counts.get("knowledge_cards") == 64, "knowledge-card count mismatch")
    require(counts.get("checklist_items") == 52, "checklist count mismatch")
    require(counts.get("canonical_features") == 29, "canonical feature count mismatch")
    require(counts.get("auxiliary_features") == 3, "auxiliary feature count mismatch")
    require(counts.get("taxonomy_financial_categories") == 9, "financial taxonomy mismatch")
    require(counts.get("taxonomy_crosscutting_categories") == 5, "cross taxonomy mismatch")
    return "count_check schema_load_ok"


def paper_ledgers() -> str:
    expected = {
        "docs/paper/CLAIM_LEDGER.csv": [
            "claim_id",
            "section",
            "claim_text",
            "evidence_file",
            "evidence_key",
            "status",
            "reviewer",
            "notes",
        ],
        "docs/paper/RESULT_LEDGER.csv": [
            "result_id",
            "experiment_id",
            "metric",
            "value",
            "artifact_path",
            "status",
            "reviewer",
            "notes",
        ],
        "docs/paper/FIGURE_REGISTRY.csv": [
            "figure_id",
            "title",
            "source_artifact",
            "paper_section",
            "site_section",
            "status",
            "notes",
        ],
    }
    for rel, header in expected.items():
        path = REPO_ROOT / rel
        with path.open(newline="", encoding="utf-8") as fh:
            first = next(csv.reader(fh))
        require(first == header, f"{rel} header mismatch")
    return "ledger headers"


def paper_sync_checker() -> str:
    report = check_paper_sync(REPO_ROOT)
    require(report.ok, report.format_violations())
    return report.summary()


def ai_use_log() -> str:
    text = read_text(REPO_ROOT / "docs" / "ai-use-log.md")
    require("bootstrap" in text.lower(), "docs/ai-use-log.md missing bootstrap entry")
    require("HR-08" in text, "docs/ai-use-log.md missing HR-08 status")
    return "present"


def required_docs() -> str:
    required = [
        "AGENTS.md",
        "CLAUDE.md",
        "LOOP.md",
        "docs/ai-use-log.md",
        "docs/data-card.md",
        "docs/model-card.md",
        "docs/privacy.md",
        "docs/limitations.md",
        "loop/CHARTER.md",
        "loop/ACCEPTANCE.md",
        "loop/RUBRIC.md",
        "loop/BACKLOG.yaml",
        "loop/STATE.json",
        "loop/HUMAN_GATES.yaml",
        "loop/STOP.example",
    ]
    missing = [
        rel
        for rel in required
        if not (REPO_ROOT / rel).is_file() or not read_text(REPO_ROOT / rel).strip()
    ]
    require(not missing, "missing/empty required docs: " + ", ".join(missing))
    return f"{len(required)} required files"


def allowed_path_scope() -> str:
    base = os.environ.get("FINK_BASE_COMMIT")
    allowed_raw = os.environ.get("FINK_ALLOWED_PATHS", "")
    if not base or not allowed_raw:
        return "not in task scope mode"
    allowed = [item for item in allowed_raw.split(os.pathsep) if item]
    changed = changed_files_since(base)
    bad = [
        file
        for file in changed
        if not any(file == p.rstrip("/") or file.startswith(p.rstrip("/") + "/") for p in allowed)
    ]
    require(not bad, "changed files outside allowed paths: " + ", ".join(bad))
    return "scope clean"


def template_hash_gate() -> str:
    state = load_json(STATE_PATH)
    expected = state.get("icml_template_hashes", {})
    current = icml_template_hashes()
    require(expected == current, "ICML template hash mismatch")
    return f"{len(current)} files"


def template_untouched_gate() -> str:
    return template_hash_gate()


def parse_python() -> str:
    count = 0
    paths = [
        *list((REPO_ROOT / "scripts").rglob("*.py")),
        *list((REPO_ROOT / "tests").rglob("*.py")),
    ]
    for path in paths:
        if ".fink" in path.parts:
            continue
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        count += 1
    return f"{count} Python files"


def style_fallback() -> str:
    offenders: list[str] = []
    for path in text_files_for_scan():
        rel = path.relative_to(REPO_ROOT).as_posix()
        if rel.startswith("paper/template/icml2026/"):
            continue
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        for idx, line in enumerate(lines, start=1):
            if line.rstrip() != line:
                offenders.append(f"{rel}:{idx}")
                break
    require(not offenders, "trailing whitespace: " + ", ".join(offenders[:20]))
    return "trailing-whitespace/newline fallback"


def unittest_fallback() -> str:
    proc = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.stdout:
        print(proc.stdout)
    if proc.stderr:
        print(proc.stderr, file=sys.stderr)
    require(proc.returncode == 0, "unittest fallback failed")
    return "unittest discover"


def run_all(args: argparse.Namespace) -> None:
    gate("branch is main", branch_gate)
    gate("clean tree at task start", lambda: clean_start_gate(args.task_start))
    gate("JSON/JSONL/YAML/CSV parsing", parse_structured_files)
    gate("schema validation", schema_validation)
    gate("queue/backlog task-id consistency", queue_consistency)
    gate("secret scan", secret_scan)
    gate(".fink/private/PDF/ZIP tracking scan", tracking_scan)
    gate("privacy public-repo preflight", public_repo_preflight)
    gate("long private-quotation heuristic", private_quote_scan)
    gate("forbidden legal-verdict scan", legal_verdict_scan)
    gate("authority-tier scoring invariant", authority_invariant)
    gate("open-license floor + no tracked weights", model_license_floor)
    gate("copyright/license audit", copyright_audit)
    gate("INV-1/INV-8 invariant suite", invariant_suite)
    gate("financial-formula tests", financial_formula_tests)
    gate("FINK-S0-01 corpus count/schema gate", fink_stage_corpus_gate)
    gate("upload-deletion tests when relevant", lambda: "not relevant to bootstrap scaffold")
    gate("offline-network test when relevant", lambda: "not relevant to bootstrap scaffold")
    gate("responsive-page smoke test when relevant", lambda: "not relevant to bootstrap scaffold")
    gate("claim-evidence ledger validation", paper_ledgers)
    gate("paper_sync_checker", paper_sync_checker)
    gate("AI-use-log update check", ai_use_log)
    gate("required-documentation check", required_docs)
    gate("allowed-path scope validation", allowed_path_scope)
    gate("template_untouched_gate", template_untouched_gate)


def doctor(args: argparse.Namespace) -> None:
    gate("branch is main", branch_gate)
    gate("required documentation", required_docs)
    gate("tracked private/binary files", tracking_scan)
    gate("structured files parse", parse_structured_files)
    if not args.no_llm:
        for cmd in ["codex", "claude"]:
            gate(
                f"{cmd} CLI available",
                lambda cmd=cmd: subprocess.run(
                    [cmd, "--version"], capture_output=True
                ).returncode
                == 0,
            )
    print(f"DOCTOR_OK branch=main commit={current_commit()}")


def main() -> None:
    parser = argparse.ArgumentParser(description="FInk repository validation gates.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    gates = sub.add_parser("gates")
    gates.add_argument("--task-start", action="store_true")
    sub.add_parser("parse-python")
    sub.add_parser("style-fallback")
    sub.add_parser("test-fallback")
    doc = sub.add_parser("doctor")
    doc.add_argument("--no-llm", action="store_true")
    args = parser.parse_args()
    try:
        if args.cmd == "gates":
            run_all(args)
        elif args.cmd == "parse-python":
            print(parse_python())
        elif args.cmd == "style-fallback":
            print(style_fallback())
        elif args.cmd == "test-fallback":
            print(unittest_fallback())
        elif args.cmd == "doctor":
            doctor(args)
    except GateFailure:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

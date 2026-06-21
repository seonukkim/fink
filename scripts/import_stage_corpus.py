#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

import argparse
import json

from fink.data import (
    CorpusValidationError,
    ValidationReport,
    import_upstream_corpus,
    load_corpus,
)


def render_human(report: ValidationReport) -> str:
    counts = report.counts
    count_text = ", ".join(f"{key}={value}" for key, value in sorted(counts.items()))
    return f"CORPUS_OK files={len(report.files)} {count_text}"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Import and validate FInk Stage 0-2 corpus records."
    )
    parser.add_argument(
        "--upstream-root",
        type=Path,
        default=REPO_ROOT / ".fink" / "inputs" / "claude",
        help="Root containing stage-0, stage-1, stage-2, and stage-3 upstream files.",
    )
    parser.add_argument(
        "--corpus-dir",
        type=Path,
        default=REPO_ROOT / "data" / "corpus",
        help="Local git-ignored corpus directory.",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate an existing local corpus without copying from upstream.",
    )
    parser.add_argument("--json", action="store_true", help="Emit a JSON validation report.")
    args = parser.parse_args()

    try:
        if args.validate_only:
            report = load_corpus(args.corpus_dir)
        else:
            report = import_upstream_corpus(args.upstream_root, args.corpus_dir)
    except CorpusValidationError as exc:
        print(f"CORPUS_BLOCKED: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    if args.json:
        print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2))
    else:
        print(render_human(report))


if __name__ == "__main__":
    main()

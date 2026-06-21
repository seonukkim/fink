from __future__ import annotations

import csv
import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SITE_ROOT = REPO_ROOT / "site"
INDEX = SITE_ROOT / "index.html"
RESULT_LEDGER = REPO_ROOT / "docs" / "paper" / "RESULT_LEDGER.csv"
FIGURE_REGISTRY = REPO_ROOT / "docs" / "paper" / "FIGURE_REGISTRY.csv"


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def extract_snapshot(html: str) -> dict[str, object]:
    match = re.search(
        r'<script id="ledger-snapshot" type="application/json">\s*(.*?)\s*</script>',
        html,
        flags=re.S,
    )
    if not match:
        raise AssertionError("ledger snapshot script is missing")
    return json.loads(match.group(1))


def assert_equal(actual: object, expected: object, message: str) -> None:
    if actual != expected:
        raise AssertionError(f"{message}: expected {expected!r}, got {actual!r}")


def main() -> None:
    html = INDEX.read_text(encoding="utf-8")
    normalized_html = re.sub(r"\s+", " ", html)
    snapshot = extract_snapshot(html)
    result_columns, result_rows = read_csv(RESULT_LEDGER)
    figure_columns, figure_rows = read_csv(FIGURE_REGISTRY)

    assert_equal(snapshot["result_columns"], result_columns, "RESULT_LEDGER columns drifted")
    assert_equal(snapshot["results"], result_rows, "RESULT_LEDGER rows drifted")
    assert_equal(snapshot["figure_columns"], figure_columns, "FIGURE_REGISTRY columns drifted")
    assert_equal(snapshot["figures"], figure_rows, "FIGURE_REGISTRY rows drifted")

    required_text = (
        "Contractual Financial Review Priority",
        "not legal advice",
        "synthetic-demo only",
        "no measured result rows",
        "RESULT_LEDGER.csv",
        "FIGURE_REGISTRY.csv",
    )
    for snippet in required_text:
        if snippet not in normalized_html:
            raise AssertionError(f"required page text missing: {snippet}")

    for figure in figure_rows:
        source = figure["source_artifact"]
        if figure["site_section"]:
            target = REPO_ROOT / source
            if not target.is_file():
                raise AssertionError(f"registered figure source missing: {source}")
            marker = f'data-figure-id="{figure["figure_id"]}"'
            if marker not in html:
                raise AssertionError(
                    f"registered figure not referenced in page: {figure['figure_id']}"
                )

    page_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (INDEX, SITE_ROOT / "styles.css", SITE_ROOT / "app.js")
    )
    forbidden_patterns = (
        r"sk-[A-Za-z0-9_-]{20,}",
        r"hf_[A-Za-z0-9]{20,}",
        r"AKIA[0-9A-Z]{16}",
        r"gh[pousr]_[A-Za-z0-9_]{20,}",
        r"FInk determines",
        r"FInk guarantees",
    )
    for pattern in forbidden_patterns:
        if re.search(pattern, page_text):
            raise AssertionError(f"public-safe scan matched forbidden pattern: {pattern}")

    if "<blockquote" in html:
        raise AssertionError("public page must not include source excerpts")

    print("SITE_PUBLIC_PAGE_OK")


if __name__ == "__main__":
    main()

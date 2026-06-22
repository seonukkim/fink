from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SITE_ROOT = REPO_ROOT / "site"
INDEX = SITE_ROOT / "index.html"


def main() -> None:
    html = INDEX.read_text(encoding="utf-8")
    normalized = re.sub(r"\s+", " ", html)

    # The page keeps its safe framing and disclaimer.
    for snippet in ("Contractual Financial Review Priority", "not legal advice"):
        if snippet not in normalized:
            raise AssertionError(f"required page text missing: {snippet}")
    if 'data-public-safe="true"' not in html:
        raise AssertionError("public-safe attribute missing")
    for snippet in (
        "Selective, Evidence-Gated Cash-Flow Triage",
        "uv sync --extra web",
        "uv run fink-web",
        "<mark>90일 이내</mark>",
        "do not signal safe or risky",
        "SUMMARY",
        "Risk Index",
        "위험 지수",
        "brand-divider",
    ):
        if snippet not in normalized:
            raise AssertionError(f"canonical page text missing: {snippet}")
    for stale in ("PYTHONPATH=src", "PaddleOCR-VL", "Qwen3", "BGE-M3"):
        if stale in normalized:
            raise AssertionError(f"stale runtime/model claim present: {stale}")

    # Public-safety scans over the page assets.
    page_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (INDEX, SITE_ROOT / "styles.css", SITE_ROOT / "app.js")
    )
    if "NotoSerifKR-500.woff2" not in page_text:
        raise AssertionError("bundled Noto Serif KR font-face missing")
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

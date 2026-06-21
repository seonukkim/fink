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

    # Public-safety scans over the page assets.
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

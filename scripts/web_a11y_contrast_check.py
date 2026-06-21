#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fink.web.app import WEB_CONTRAST_CHECKS, WEB_DESIGN_TOKENS


def contrast_ratio(foreground: str, background: str) -> float:
    fg = _relative_luminance(_hex_to_rgb(foreground))
    bg = _relative_luminance(_hex_to_rgb(background))
    light, dark = max(fg, bg), min(fg, bg)
    return (light + 0.05) / (dark + 0.05)


def build_report() -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for label, foreground_token, background_token, minimum in WEB_CONTRAST_CHECKS:
        foreground = WEB_DESIGN_TOKENS[foreground_token]
        background = WEB_DESIGN_TOKENS[background_token]
        ratio = contrast_ratio(foreground, background)
        item = {
            "label": label,
            "foreground_token": foreground_token,
            "background_token": background_token,
            "foreground": foreground,
            "background": background,
            "minimum": minimum,
            "ratio": round(ratio, 2),
            "pass": ratio >= minimum,
        }
        items.append(item)
        if not item["pass"]:
            failures.append(item)
    return {
        "claim_boundary": (
            "Automated design-token contrast check only; this is not a full WCAG "
            "2.2 conformance claim and does not replace keyboard or screen-reader review."
        ),
        "automated_checks": {
            "name": "design_token_contrast",
            "normal_text_minimum": 4.5,
            "large_text_and_ui_state_minimum": 3.0,
            "items": items,
            "failures": failures,
            "ok": not failures,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check FInk web design-token contrast pairs."
    )
    parser.add_argument("--json", action="store_true", help="Print the full JSON report.")
    args = parser.parse_args(argv)

    report = build_report()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        checks = report["automated_checks"]
        status = "PASS" if checks["ok"] else "FAIL"
        print(
            "design_token_contrast: "
            f"{status}; checked={len(checks['items'])} failures={len(checks['failures'])}"
        )
        print(report["claim_boundary"])
    return 0 if report["automated_checks"]["ok"] else 1


def _hex_to_rgb(value: str) -> tuple[float, float, float]:
    raw = value.strip().lstrip("#")
    if len(raw) != 6:
        raise ValueError(f"expected #RRGGBB color, got {value!r}")
    channels = tuple(int(raw[index : index + 2], 16) / 255 for index in (0, 2, 4))
    return channels


def _relative_luminance(rgb: tuple[float, float, float]) -> float:
    red, green, blue = (_linear_channel(channel) for channel in rgb)
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def _linear_channel(channel: float) -> float:
    if channel <= 0.04045:
        return channel / 12.92
    return ((channel + 0.055) / 1.055) ** 2.4


if __name__ == "__main__":
    raise SystemExit(main())

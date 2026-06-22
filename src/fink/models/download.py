"""Download public local model artifacts for FInk.

This module is intentionally only a downloader. The model research/runtime
health logic remains in ``fink.model.runtime``.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fink.model.explanation_llm import resolve_chat_model_path


REPO_ROOT = Path(__file__).resolve().parents[3]
SELECTED_PROFILES_PATH = REPO_ROOT / "configs" / "models" / "selected_profiles.yaml"
DOWNLOAD_ALLOWED_ENV = "FINK_MODEL_DOWNLOAD_ALLOWED"
CHAT_MODEL_REPO_ENV = "FINK_CHAT_MODEL_REPO"
CHAT_MODEL_FILE_ENV = "FINK_CHAT_MODEL_FILE"
DEFAULT_CHAT_MODEL_REPO = "Qwen/Qwen3-1.7B-GGUF"
DEFAULT_CHAT_MODEL_FILE = "Qwen3-1.7B-Q4_K_M.gguf"
APPROX_CHAT_MODEL_SIZE_BYTES = 1_100_000_000
PUBLIC_MODEL_LICENSE = "apache-2.0"
ENABLE_INSTRUCTION = (
    "Model downloads are disabled. Set FINK_MODEL_DOWNLOAD_ALLOWED=true to download models."
)
HF_INSTALL_MESSAGE = (
    "huggingface_hub is required for model downloads. Install it with: uv sync --extra chat"
)


@dataclass(frozen=True)
class ModelSpec:
    id: str
    alias: str
    repo: str
    license: str
    approx_size_bytes: int | None
    target_path: Path | None
    present: bool
    revision: str | None = None
    filename: str | None = None
    guidance: str | None = None


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "list":
        return list_models()
    if args.command == "download":
        return download_models(only=args.only, dry_run=args.dry_run)
    parser.print_help()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fink-models",
        description="List or download FInk's optional local public models.",
    )
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("list", help="print the configured local model plan")

    download = subparsers.add_parser("download", help="download configured local models")
    download.add_argument(
        "--only",
        choices=("embedding", "reranker", "llm", "all"),
        default="all",
        help="limit the download to one model family",
    )
    download.add_argument(
        "--dry-run",
        action="store_true",
        help="print what would be downloaded without touching the network",
    )
    return parser


def list_models() -> int:
    for spec in model_specs():
        print(format_model_line(spec))
        if spec.guidance:
            print(f"  guidance: {spec.guidance}")
    return 0


def download_models(*, only: str, dry_run: bool) -> int:
    if not download_allowed(os.environ):
        print(ENABLE_INSTRUCTION)
        print("Example: FINK_MODEL_DOWNLOAD_ALLOWED=true uv run fink-models download")
        return 0

    selected = downloadable_specs(only)
    if dry_run:
        for spec in selected:
            print(f"WOULD download {spec.alias}: {download_action(spec)}")
        print(f"Dry run complete: {len(selected)} model download(s) planned.")
        print(ocr_guidance())
        return 0

    ensure_telemetry_disabled()
    local_files_only = offline_mode_requested(os.environ)
    try:
        from huggingface_hub import hf_hub_download  # type: ignore[import-not-found]
        from huggingface_hub import snapshot_download  # type: ignore[import-not-found]
    except Exception:
        print(HF_INSTALL_MESSAGE, file=sys.stderr)
        return 1

    completed: list[tuple[str, Path]] = []
    failed: list[tuple[str, str]] = []
    for spec in selected:
        try:
            target = require_download_target(spec)
            if spec.alias in {"embedding", "reranker"}:
                target.mkdir(parents=True, exist_ok=True)
                snapshot_download(
                    repo_id=spec.repo,
                    revision=spec.revision,
                    local_dir=target.as_posix(),
                    token=False,
                    local_files_only=local_files_only,
                )
                completed.append((spec.alias, target))
            elif spec.alias == "llm":
                target.parent.mkdir(parents=True, exist_ok=True)
                filename = spec.filename or DEFAULT_CHAT_MODEL_FILE
                downloaded = hf_hub_download(
                    repo_id=spec.repo,
                    filename=filename,
                    local_dir=target.parent.as_posix(),
                    token=False,
                    local_files_only=local_files_only,
                )
                downloaded_path = Path(downloaded)
                if downloaded_path.resolve(strict=False) != target.resolve(strict=False):
                    if target.exists():
                        target.unlink()
                    shutil.move(downloaded_path.as_posix(), target.as_posix())
                completed.append((spec.alias, target))
        except Exception as exc:  # pragma: no cover - exercised only on real download failures
            failed.append((spec.alias, str(exc)))

    print("Download summary:")
    for alias, path in completed:
        print(f"  downloaded {alias}: {path}")
    for alias, error in failed:
        print(f"  failed {alias}: {error}")
    if local_files_only:
        print("  offline flags are active; Hugging Face calls used local_files_only=True.")
    print(ocr_guidance())
    return 1 if failed else 0


def model_specs() -> tuple[ModelSpec, ...]:
    text_specs = selected_text_specs()
    chat_target = resolve_chat_model_path()
    chat_repo = os.environ.get(CHAT_MODEL_REPO_ENV, "").strip() or DEFAULT_CHAT_MODEL_REPO
    chat_file = os.environ.get(CHAT_MODEL_FILE_ENV, "").strip() or DEFAULT_CHAT_MODEL_FILE
    return (
        text_specs["embedding"],
        text_specs["reranker"],
        ModelSpec(
            id="qwen3_1_7b_gguf",
            alias="llm",
            repo=chat_repo,
            revision=None,
            filename=chat_file,
            license=PUBLIC_MODEL_LICENSE,
            approx_size_bytes=APPROX_CHAT_MODEL_SIZE_BYTES,
            target_path=chat_target,
            present=path_present(chat_target),
        ),
        ModelSpec(
            id="paddleocr_vl",
            alias="ocr",
            repo="PaddlePaddle/PaddleOCR-VL",
            revision=None,
            filename=None,
            license=PUBLIC_MODEL_LICENSE,
            approx_size_bytes=None,
            target_path=None,
            present=False,
            guidance=ocr_guidance(),
        ),
    )


def selected_text_specs() -> dict[str, ModelSpec]:
    defaults = {
        "embedding": {
            "id": "qwen3_embedding_0_6b",
            "repo": "Qwen/Qwen3-Embedding-0.6B",
            "revision": "97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3",
            "size": 1_210_000_000,
        },
        "reranker": {
            "id": "qwen3_reranker_0_6b",
            "repo": "Qwen/Qwen3-Reranker-0.6B",
            "revision": "e61197ed45024b0ed8a2d74b80b4d909f1255473",
            "size": 1_210_000_000,
        },
    }
    for alias, role in (
        ("embedding", "primary_ko_en_embedding"),
        ("reranker", "primary_ko_en_reranker"),
    ):
        component = selected_profile_component(role)
        if component:
            defaults[alias] = {
                "id": str(component.get("model_id") or defaults[alias]["id"]),
                "repo": str(component.get("repo_id") or defaults[alias]["repo"]),
                "revision": str(component.get("exact_revision") or defaults[alias]["revision"]),
                "size": int(component.get("estimated_disk_size_bytes") or defaults[alias]["size"]),
            }

    return {
        alias: ModelSpec(
            id=str(values["id"]),
            alias=alias,
            repo=str(values["repo"]),
            revision=str(values["revision"]),
            filename=None,
            license=PUBLIC_MODEL_LICENSE,
            approx_size_bytes=int(values["size"]),
            target_path=models_root() / str(values["id"]),
            present=path_present(models_root() / str(values["id"])),
        )
        for alias, values in defaults.items()
    }


def selected_profile_component(role: str) -> Mapping[str, Any] | None:
    if not SELECTED_PROFILES_PATH.exists():
        return None
    try:
        import yaml  # type: ignore[import-untyped]

        payload = yaml.safe_load(SELECTED_PROFILES_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(payload, Mapping):
        return None
    profiles = payload.get("selected_profiles")
    if not isinstance(profiles, list):
        return None
    for profile in profiles:
        if not isinstance(profile, Mapping):
            continue
        components = profile.get("profile_components")
        if not isinstance(components, list):
            continue
        for component in components:
            if isinstance(component, Mapping) and component.get("role") == role:
                return component
    return None


def downloadable_specs(only: str) -> tuple[ModelSpec, ...]:
    aliases = {"embedding", "reranker", "llm"} if only == "all" else {only}
    return tuple(spec for spec in model_specs() if spec.alias in aliases)


def format_model_line(spec: ModelSpec) -> str:
    path = (
        spec.target_path.as_posix()
        if spec.target_path is not None
        else "not downloaded by fink-models"
    )
    revision = spec.revision if spec.revision is not None else "default"
    filename = f", file={spec.filename}" if spec.filename else ""
    return (
        f"id={spec.id} alias={spec.alias} repo={spec.repo} revision={revision}{filename} "
        f"license={spec.license} approx_size={format_size(spec.approx_size_bytes)} "
        f"target={path} present={yes_no(spec.present)}"
    )


def download_action(spec: ModelSpec) -> str:
    target = spec.target_path.as_posix() if spec.target_path is not None else "n/a"
    if spec.alias == "llm":
        return f"hf_hub_download repo={spec.repo} file={spec.filename} target={target}"
    return f"snapshot_download repo={spec.repo} revision={spec.revision} target={target}"


def format_size(size_bytes: int | None) -> str:
    if size_bytes is None:
        return "n/a"
    size_gb = size_bytes / 1_000_000_000
    return f"{size_gb:.2f} GB"


def yes_no(value: bool) -> str:
    return "yes" if value else "no"


def path_present(path: Path | None) -> bool:
    if path is None:
        return False
    if path.is_file():
        return True
    if not path.is_dir():
        return False
    try:
        next(path.iterdir())
    except StopIteration:
        return False
    except OSError:
        return False
    return True


def models_root() -> Path:
    return fink_home() / "models"


def fink_home() -> Path:
    override = os.environ.get("FINK_HOME", "").strip()
    if override:
        return Path(override).expanduser()
    return Path.home() / ".local" / "share" / "fink"


def download_allowed(env: Mapping[str, str]) -> bool:
    return env.get(DOWNLOAD_ALLOWED_ENV, "").strip().lower() in {"1", "true", "yes"}


def ensure_telemetry_disabled() -> None:
    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
    os.environ.setdefault("DO_NOT_TRACK", "1")


def offline_mode_requested(env: Mapping[str, str]) -> bool:
    truthy = {"1", "true", "yes"}
    return any(
        env.get(name, "").strip().lower() in truthy
        for name in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE", "HF_DATASETS_OFFLINE")
    ) or env.get("FINK_RUNTIME_OFFLINE", "").strip().lower() == "true"


def require_download_target(spec: ModelSpec) -> Path:
    if spec.target_path is None:
        raise ValueError(f"{spec.alias} has no download target")
    target = spec.target_path.expanduser().resolve(strict=False)
    if is_under(target, REPO_ROOT):
        raise ValueError(f"download target must be outside the Git repository: {target}")
    return target


def is_under(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent.resolve(strict=False))
        return True
    except ValueError:
        return False


def ocr_guidance() -> str:
    return "OCR: run `uv sync --extra ocr`; PaddleOCR-VL auto-downloads on first use."


if __name__ == "__main__":
    raise SystemExit(main())

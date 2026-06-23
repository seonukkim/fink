#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast


REPO_ROOT = Path(__file__).resolve().parents[2]
SHORTLIST_PATH = REPO_ROOT / "configs" / "models" / "open_license_shortlist.yaml"
HUMAN_GATES_PATH = REPO_ROOT / "loop" / "HUMAN_GATES.yaml"
MODEL_DOWNLOAD_GATE = "MODEL_DOWNLOAD_APPROVED"
HF_AUTH_WRAPPER_MARKER = "run_with_hf_auth.sh"
OPEN_LICENSE_FLOOR = frozenset(
    {"apache-2.0", "mit", "bsd-2-clause", "bsd-3-clause", "isc", "cc0-1.0", "cc-by-4.0"}
)
WEIGHT_SUFFIXES = (
    ".safetensors",
    ".gguf",
    ".onnx",
    ".pt",
    ".pth",
    ".h5",
    ".bin",
    ".ckpt",
)


class PrivateModelDownloadError(ValueError):
    """Raised when a private model download would violate FInk policy."""


@dataclass(frozen=True)
class Candidate:
    id: str
    group: str
    repo_id: str
    role: str
    license: str
    exact_revision: str
    estimated_disk_size_bytes: int


@dataclass(frozen=True)
class StoragePlan:
    mode: str
    root: str
    target: str


def require(condition: bool, message: str) -> None:
    if not condition:
        raise PrivateModelDownloadError(message)


def load_yaml_mapping(path: Path) -> dict[str, Any]:
    try:
        import yaml  # type: ignore[import-untyped]
    except Exception as exc:  # pragma: no cover - environment diagnostic
        raise PrivateModelDownloadError("PyYAML is required for model download planning") from exc

    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    require(isinstance(data, dict), f"{relative(path)} must contain a YAML mapping")
    return cast(dict[str, Any], data)


def relative(path: Path) -> str:
    try:
        return path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def mapping_at(data: dict[str, Any], key: str, path: str) -> dict[str, Any]:
    value = data.get(key)
    require(isinstance(value, dict), f"{path}.{key} must be a mapping")
    return cast(dict[str, Any], value)


def required_string(data: dict[str, Any], key: str, path: str) -> str:
    value = data.get(key)
    require(isinstance(value, str) and bool(value.strip()), f"{path}.{key} must be non-empty")
    return value


def required_bool(data: dict[str, Any], key: str, path: str) -> bool:
    value = data.get(key)
    require(isinstance(value, bool), f"{path}.{key} must be boolean")
    return value


def required_positive_int(data: dict[str, Any], key: str, path: str) -> int:
    value = data.get(key)
    require(isinstance(value, int) and value > 0, f"{path}.{key} must be a positive integer")
    return value


def validate_download_gate(gates: dict[str, Any], source: Path) -> dict[str, Any]:
    gate_map = mapping_at(gates, "gates", relative(source))
    gate = mapping_at(gate_map, MODEL_DOWNLOAD_GATE, f"{relative(source)}.gates")
    status = required_string(gate, "status", f"{relative(source)}.gates.{MODEL_DOWNLOAD_GATE}")
    require(
        status in {"APPROVED", "RESOLVED"},
        f"{MODEL_DOWNLOAD_GATE} must be APPROVED or RESOLVED, got {status}",
    )
    require(
        required_bool(gate, "approved", f"{relative(source)}.gates.{MODEL_DOWNLOAD_GATE}") is True,
        f"{MODEL_DOWNLOAD_GATE} must be approved",
    )
    policy = required_string(gate, "policy", f"{relative(source)}.gates.{MODEL_DOWNLOAD_GATE}")
    require("open_license_floor" in policy, f"{MODEL_DOWNLOAD_GATE} policy must include open_license_floor")
    require("size_cap" in policy, f"{MODEL_DOWNLOAD_GATE} policy must include size_cap")
    return gate


def validate_shortlist(shortlist: dict[str, Any], source: Path) -> tuple[dict[str, Candidate], int]:
    source_name = relative(source)
    require(shortlist.get("schema_version") == 1, f"{source_name}.schema_version must be 1")
    require(shortlist.get("task_id") == "FINK-MR-04", f"{source_name}.task_id must be FINK-MR-04")
    require(
        shortlist.get("human_gate") == "MODEL_LICENSES_APPROVED",
        f"{source_name}.human_gate must be MODEL_LICENSES_APPROVED",
    )

    policy = mapping_at(shortlist, "shortlist_policy", source_name)
    accepted_licenses = policy.get("accepted_licenses")
    require(
        isinstance(accepted_licenses, list)
        and accepted_licenses
        and all(isinstance(item, str) and item for item in accepted_licenses),
        f"{source_name}.shortlist_policy.accepted_licenses must be a non-empty string list",
    )
    accepted_license_set = {item.lower() for item in cast(list[str], accepted_licenses)}
    require(
        not (accepted_license_set - OPEN_LICENSE_FLOOR),
        "shortlist accepted_licenses widened beyond the open-license floor",
    )

    summary = mapping_at(shortlist, "summary", source_name)
    max_download_size_gb = summary.get("max_download_size_gb")
    require(isinstance(max_download_size_gb, int) and max_download_size_gb > 0, "summary.max_download_size_gb invalid")
    max_download_bytes = max_download_size_gb * 1_000_000_000

    accepted = shortlist.get("accepted")
    require(isinstance(accepted, list) and accepted, f"{source_name}.accepted must be a non-empty list")

    candidates: dict[str, Candidate] = {}
    for index, raw_record in enumerate(accepted):
        require(isinstance(raw_record, dict), f"{source_name}.accepted[{index}] must be a mapping")
        record = cast(dict[str, Any], raw_record)
        path = f"{source_name}.accepted[{index}]"

        candidate_id = required_string(record, "id", path)
        require(candidate_id not in candidates, f"duplicate candidate id: {candidate_id}")
        license_id = required_string(record, "license", path).lower()
        require(license_id in accepted_license_set, f"{candidate_id} license not in accepted_licenses")
        require(license_id in OPEN_LICENSE_FLOOR, f"{candidate_id} license not in open-license floor")
        require(required_bool(record, "gated", path) is False, f"{candidate_id} is gated")
        require(required_bool(record, "private", path) is False, f"{candidate_id} is private")
        require(required_bool(record, "disabled", path) is False, f"{candidate_id} is disabled")
        require(record.get("access_status") == "public_ungated", f"{candidate_id} must be public_ungated")
        require(record.get("decision") == "accepted_public_open", f"{candidate_id} must be accepted_public_open")

        revision = required_string(record, "exact_revision", path)
        require(len(revision) == 40 and all(ch in "0123456789abcdef" for ch in revision), f"{candidate_id} bad revision")
        size_bytes = required_positive_int(record, "estimated_disk_size_bytes", path)
        require(size_bytes <= max_download_bytes, f"{candidate_id} exceeds max_download_size_gb")

        candidates[candidate_id] = Candidate(
            id=candidate_id,
            group=required_string(record, "group", path),
            repo_id=required_string(record, "repo_id", path),
            role=required_string(record, "role", path),
            license=license_id,
            exact_revision=revision,
            estimated_disk_size_bytes=size_bytes,
        )

    summary_count = summary.get("accepted_count")
    require(summary_count == len(candidates), "summary.accepted_count mismatch")
    require(summary.get("downloaded_weight_files") is False, "shortlist must remain metadata-only")
    return candidates, max_download_size_gb


def tracked_weight_files() -> list[str]:
    proc = subprocess.run(
        ["git", "ls-files"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    return sorted(
        file for file in proc.stdout.splitlines() if file.lower().endswith(WEIGHT_SUFFIXES)
    )


def require_no_tracked_weights() -> None:
    weights = tracked_weight_files()
    require(not weights, "model weight files tracked in Git: " + ", ".join(weights))


def is_under(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def resolve_path(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def require_outside_repo(path: Path, label: str) -> Path:
    resolved = resolve_path(path)
    repo = resolve_path(REPO_ROOT)
    require(not is_under(resolved, repo), f"{label} must not be inside the Git repository: {resolved}")
    return resolved


def private_storage_root(env: dict[str, str], override: Path | None) -> Path:
    private_root_raw = env.get("PRIVATE_ROOT", "")
    require(bool(private_root_raw.strip()), "PRIVATE_ROOT must be set for private-root storage")

    private_root = require_outside_repo(Path(private_root_raw), "PRIVATE_ROOT")
    models_root = resolve_path(private_root / "models")
    if override is not None:
        root = require_outside_repo(override, "private model root")
    elif env.get("FINK_HF_MODEL_ROOT"):
        root = require_outside_repo(Path(env["FINK_HF_MODEL_ROOT"]), "FINK_HF_MODEL_ROOT")
    else:
        root = resolve_path(models_root / "huggingface")

    require(
        root == models_root or is_under(root, models_root),
        f"private model root must be under PRIVATE_ROOT/models: {root}",
    )
    return root


def hf_cache_root(env: dict[str, str]) -> Path:
    if env.get("HF_HUB_CACHE"):
        root = Path(env["HF_HUB_CACHE"])
    elif env.get("HF_HOME"):
        root = Path(env["HF_HOME"]) / "hub"
    else:
        root = Path.home() / ".cache" / "huggingface" / "hub"
    return require_outside_repo(root, "Hugging Face cache")


def select_candidates(
    candidates: dict[str, Candidate], model_ids: list[str], include_all: bool
) -> list[Candidate]:
    if include_all:
        require(not model_ids, "use either --all or --model-id, not both")
        return [candidates[key] for key in sorted(candidates)]
    require(bool(model_ids), "select at least one model with --model-id or use --all")

    selected: list[Candidate] = []
    seen: set[str] = set()
    for model_id in model_ids:
        require(model_id in candidates, f"unknown or unapproved model id: {model_id}")
        require(model_id not in seen, f"duplicate selected model id: {model_id}")
        seen.add(model_id)
        selected.append(candidates[model_id])
    return selected


def storage_plan_for(candidate: Candidate, mode: str, root: Path) -> StoragePlan:
    if mode == "private-root":
        target = root / candidate.id / candidate.exact_revision
        return StoragePlan(mode=mode, root=root.as_posix(), target=target.as_posix())
    return StoragePlan(
        mode=mode,
        root=root.as_posix(),
        target=f"hf-cache:{candidate.repo_id}@{candidate.exact_revision}",
    )


def build_plan(
    selected: list[Candidate],
    storage_mode: str,
    storage_root: Path,
    max_download_size_gb: int,
    gate: dict[str, Any],
) -> dict[str, Any]:
    total_bytes = sum(candidate.estimated_disk_size_bytes for candidate in selected)
    return {
        "task_id": "FINK-MR-05",
        "human_gate": MODEL_DOWNLOAD_GATE,
        "human_gate_status": gate["status"],
        "human_gate_approved": gate["approved"],
        "storage_mode": storage_mode,
        "max_download_size_gb": max_download_size_gb,
        "selected_count": len(selected),
        "total_estimated_disk_size_bytes": total_bytes,
        "tracked_weight_files": tracked_weight_files(),
        "models": [
            {
                "id": candidate.id,
                "group": candidate.group,
                "repo_id": candidate.repo_id,
                "role": candidate.role,
                "license": candidate.license,
                "exact_revision": candidate.exact_revision,
                "estimated_disk_size_bytes": candidate.estimated_disk_size_bytes,
                "storage": storage_plan_for(candidate, storage_mode, storage_root).__dict__,
            }
            for candidate in selected
        ],
    }


def require_download_armed(env: dict[str, str]) -> None:
    allowed = env.get("FINK_MODEL_DOWNLOAD_ALLOWED", "").lower()
    require(
        allowed in {"1", "true", "yes"},
        "set FINK_MODEL_DOWNLOAD_ALLOWED=true for a real model download",
    )
    require(
        env.get("FINK_HF_AUTH_WRAPPER") == HF_AUTH_WRAPPER_MARKER,
        "run downloads through scripts/model_research/run_with_hf_auth.sh",
    )
    require(bool(env.get("HF_TOKEN", "").strip()), "HF_TOKEN must be supplied by run_with_hf_auth.sh")


def download_selected(selected: list[Candidate], storage_mode: str, storage_root: Path) -> list[dict[str, str]]:
    try:
        from huggingface_hub import snapshot_download  # type: ignore[import-untyped]
    except Exception as exc:  # pragma: no cover - environment diagnostic
        raise PrivateModelDownloadError("huggingface_hub is required for downloads") from exc

    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
    os.environ.setdefault("DO_NOT_TRACK", "1")

    results: list[dict[str, str]] = []
    token = os.environ["HF_TOKEN"]
    for candidate in selected:
        if storage_mode == "private-root":
            target = storage_root / candidate.id / candidate.exact_revision
            require_outside_repo(target, "download target")
            target.mkdir(parents=True, exist_ok=True)
            resolved = snapshot_download(
                repo_id=candidate.repo_id,
                revision=candidate.exact_revision,
                local_dir=target.as_posix(),
                token=token,
            )
        else:
            require_outside_repo(storage_root, "Hugging Face cache")
            storage_root.mkdir(parents=True, exist_ok=True)
            resolved = snapshot_download(
                repo_id=candidate.repo_id,
                revision=candidate.exact_revision,
                cache_dir=storage_root.as_posix(),
                token=token,
            )
        resolved_path = require_outside_repo(Path(resolved), "download result")
        results.append({"id": candidate.id, "path": resolved_path.as_posix()})
    require_no_tracked_weights()
    return results


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Plan or run approved private downloads for FInk model weights."
    )
    parser.add_argument("--shortlist", type=Path, default=SHORTLIST_PATH)
    parser.add_argument("--human-gates", type=Path, default=HUMAN_GATES_PATH)
    parser.add_argument("--model-id", action="append", default=[], help="Approved shortlist id to download")
    parser.add_argument("--all", action="store_true", help="Select every accepted shortlist model")
    parser.add_argument("--storage", choices=("private-root", "hf-cache"), default="private-root")
    parser.add_argument(
        "--private-model-root",
        type=Path,
        default=None,
        help="Override private-root storage; must be under PRIVATE_ROOT/models",
    )
    parser.add_argument("--plan", action="store_true", help="Validate and print the download plan")
    parser.add_argument("--download", action="store_true", help="Run the download after all gates pass")
    parser.add_argument("--json", action="store_true", help="Emit JSON output")
    parser.add_argument("--self-test", action="store_true", help="Run policy self-tests without network")
    return parser.parse_args()


def run_self_test() -> None:
    fake_source = Path("selftest.yaml")
    gate = validate_download_gate(
        {
            "gates": {
                MODEL_DOWNLOAD_GATE: {
                    "status": "RESOLVED",
                    "approved": True,
                    "policy": "open_license_floor + size_cap",
                }
            }
        },
        fake_source,
    )
    require(gate["approved"] is True, "self-test approved gate failed")

    try:
        validate_download_gate(
            {
                "gates": {
                    MODEL_DOWNLOAD_GATE: {
                        "status": "OPEN",
                        "approved": False,
                        "policy": "open_license_floor + size_cap",
                    }
                }
            },
            fake_source,
        )
    except PrivateModelDownloadError:
        pass
    else:  # pragma: no cover - defensive
        raise PrivateModelDownloadError("self-test did not reject an open download gate")

    shortlist = {
        "schema_version": 1,
        "task_id": "FINK-MR-04",
        "human_gate": "MODEL_LICENSES_APPROVED",
        "shortlist_policy": {"accepted_licenses": ["apache-2.0"]},
        "summary": {
            "max_download_size_gb": 20,
            "accepted_count": 1,
            "downloaded_weight_files": False,
        },
        "accepted": [
            {
                "id": "sample",
                "group": "embedding",
                "repo_id": "org/sample",
                "role": "sample",
                "license": "apache-2.0",
                "gated": False,
                "private": False,
                "disabled": False,
                "access_status": "public_ungated",
                "decision": "accepted_public_open",
                "exact_revision": "0" * 40,
                "estimated_disk_size_bytes": 123,
            }
        ],
    }
    candidates, cap = validate_shortlist(shortlist, fake_source)
    selected = select_candidates(candidates, ["sample"], include_all=False)
    require(cap == 20 and selected[0].id == "sample", "self-test shortlist selection failed")

    env = {"PRIVATE_ROOT": "/tmp/fink-private"}
    root = private_storage_root(env, None)
    plan = build_plan(selected, "private-root", root, cap, gate)
    require(
        plan["models"][0]["storage"]["target"].endswith("/models/huggingface/sample/" + "0" * 40),
        "self-test private storage target failed",
    )

    try:
        private_storage_root({"PRIVATE_ROOT": REPO_ROOT.as_posix()}, None)
    except PrivateModelDownloadError:
        pass
    else:  # pragma: no cover - defensive
        raise PrivateModelDownloadError("self-test did not reject repo-local PRIVATE_ROOT")


def main() -> int:
    args = parse_args()
    try:
        if args.self_test:
            run_self_test()
            print("PRIVATE_MODEL_DOWNLOAD_SELF_TEST_OK")
            return 0

        require(not (args.plan and args.download), "use either --plan or --download, not both")
        action = "download" if args.download else "plan"

        gates = load_yaml_mapping(args.human_gates)
        gate = validate_download_gate(gates, args.human_gates)
        shortlist = load_yaml_mapping(args.shortlist)
        candidates, max_download_size_gb = validate_shortlist(shortlist, args.shortlist)
        selected = select_candidates(candidates, cast(list[str], args.model_id), args.all)
        require_no_tracked_weights()

        env = dict(os.environ)
        if args.storage == "private-root":
            storage_root = private_storage_root(env, args.private_model_root)
        else:
            storage_root = hf_cache_root(env)

        plan = build_plan(selected, args.storage, storage_root, max_download_size_gb, gate)
        if action == "download":
            require_download_armed(env)
            plan["download_results"] = download_selected(selected, args.storage, storage_root)
            plan["status"] = "downloaded_private_weights"
        else:
            plan["status"] = "planned_no_download"

        if args.json:
            print(json.dumps(plan, ensure_ascii=False, indent=2, sort_keys=True))
        else:
            print(
                f"PRIVATE_MODEL_DOWNLOAD_{action.upper()}_OK "
                f"selected={plan['selected_count']} "
                f"storage={args.storage} "
                f"total_estimated_disk_size_bytes={plan['total_estimated_disk_size_bytes']} "
                "tracked_weight_files=0"
            )
        return 0
    except PrivateModelDownloadError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

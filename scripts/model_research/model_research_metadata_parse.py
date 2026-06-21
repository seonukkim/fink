#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, cast


REPO_ROOT = Path(__file__).resolve().parents[2]
INVENTORY_PATH = REPO_ROOT / "configs" / "models" / "local_inventory.yaml"
CANDIDATES_PATH = REPO_ROOT / "configs" / "models" / "candidates.yaml"

REQUIRED_TOP_LEVEL = {
    "schema_version",
    "task_id",
    "captured_at",
    "base_commit",
    "hardware",
    "software",
    "local_runtime_constraints",
}
REQUIRED_RUNTIME_CONSTRAINTS = {
    "runtime_profile",
    "remote_runtime_api_allowed",
    "runtime_network_dependency",
    "model_storage",
    "token_handling",
    "download_policy",
    "max_download_size_gb",
    "offline_environment_flags",
    "privacy_boundary",
    "paper_note",
}


class MetadataParseError(ValueError):
    """Raised when the model-research inventory is missing required fields."""


def load_yaml_mapping(path: Path) -> dict[str, Any]:
    try:
        import yaml  # type: ignore[import-untyped]
    except Exception as exc:  # pragma: no cover - environment diagnostic
        raise MetadataParseError("PyYAML is required to parse model metadata") from exc

    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise MetadataParseError(f"{path.relative_to(REPO_ROOT)} must contain a YAML mapping")
    return cast(dict[str, Any], data)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise MetadataParseError(message)


def mapping_at(data: dict[str, Any], key: str, path: str) -> dict[str, Any]:
    value = data.get(key)
    require(isinstance(value, dict), f"{path}.{key} must be a mapping")
    return cast(dict[str, Any], value)


def required_string(data: dict[str, Any], key: str, path: str) -> str:
    value = data.get(key)
    require(isinstance(value, str) and bool(value.strip()), f"{path}.{key} must be non-empty")
    return value


def required_positive_int(data: dict[str, Any], key: str, path: str) -> int:
    value = data.get(key)
    require(isinstance(value, int) and value > 0, f"{path}.{key} must be a positive integer")
    return value


def validate_inventory(data: dict[str, Any], candidates: dict[str, Any]) -> None:
    missing = sorted(REQUIRED_TOP_LEVEL - set(data))
    require(not missing, "local_inventory.yaml missing top-level fields: " + ", ".join(missing))
    require(data["schema_version"] == 1, "schema_version must be 1")
    require(data["task_id"] == "FINK-MR-01", "task_id must be FINK-MR-01")
    required_string(data, "captured_at", "inventory")
    base_commit = required_string(data, "base_commit", "inventory")
    require(len(base_commit) == 40, "inventory.base_commit must be a full 40-character SHA")

    hardware = mapping_at(data, "hardware", "inventory")
    cpu = mapping_at(hardware, "cpu", "inventory.hardware")
    memory = mapping_at(hardware, "memory", "inventory.hardware")
    disk = mapping_at(hardware, "disk", "inventory.hardware")
    gpu = mapping_at(hardware, "gpu", "inventory.hardware")

    for key in ("architecture", "vendor_id", "model_name", "virtualization", "hypervisor_vendor"):
        required_string(cpu, key, "inventory.hardware.cpu")
    for key in ("logical_cpus", "physical_cores", "sockets", "threads_per_core"):
        required_positive_int(cpu, key, "inventory.hardware.cpu")
    features = cpu.get("acceleration_features")
    require(
        isinstance(features, list) and all(isinstance(item, str) for item in features) and features,
        "inventory.hardware.cpu.acceleration_features must be a non-empty string list",
    )

    for key in ("total", "available_at_capture", "swap_total"):
        required_string(memory, key, "inventory.hardware.memory")
    required_string(disk, "repo_and_tmp_available_at_capture", "inventory.hardware.disk")

    for key in (
        "access_status",
        "nvidia_smi_probe",
        "cuda_toolkit",
        "pci_probe",
        "device_nodes_probe",
        "runtime_assumption",
    ):
        required_string(gpu, key, "inventory.hardware.gpu")
    require(
        isinstance(gpu.get("usable_for_current_runs"), bool),
        "inventory.hardware.gpu.usable_for_current_runs must be boolean",
    )

    software = mapping_at(data, "software", "inventory")
    os_info = mapping_at(software, "os", "inventory.software")
    python_info = mapping_at(software, "python", "inventory.software")
    for key in ("name", "version", "kernel", "environment"):
        required_string(os_info, key, "inventory.software.os")
    for key in ("implementation", "version", "executable", "pip"):
        required_string(python_info, key, "inventory.software.python")

    constraints = mapping_at(data, "local_runtime_constraints", "inventory")
    missing_constraints = sorted(REQUIRED_RUNTIME_CONSTRAINTS - set(constraints))
    require(
        not missing_constraints,
        "local_runtime_constraints missing fields: " + ", ".join(missing_constraints),
    )
    for key in REQUIRED_RUNTIME_CONSTRAINTS - {
        "remote_runtime_api_allowed",
        "max_download_size_gb",
        "offline_environment_flags",
    }:
        required_string(constraints, key, "inventory.local_runtime_constraints")
    require(
        constraints["remote_runtime_api_allowed"] is False,
        "remote_runtime_api_allowed must be false",
    )
    flags = constraints["offline_environment_flags"]
    require(isinstance(flags, dict) and bool(flags), "offline_environment_flags must be mapping")

    policy = mapping_at(candidates, "license_policy", "candidates")
    configured_cap = policy.get("max_download_size_gb")
    require(isinstance(configured_cap, int), "candidates.license_policy.max_download_size_gb missing")
    require(
        constraints["max_download_size_gb"] == configured_cap,
        "local inventory max_download_size_gb must match candidates.yaml",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate the FINK-MR-01 local model-research inventory."
    )
    parser.add_argument(
        "--inventory",
        type=Path,
        default=INVENTORY_PATH,
        help="Path to configs/models/local_inventory.yaml",
    )
    parser.add_argument(
        "--candidates",
        type=Path,
        default=CANDIDATES_PATH,
        help="Path to configs/models/candidates.yaml",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    inventory = load_yaml_mapping(args.inventory)
    candidates = load_yaml_mapping(args.candidates)
    validate_inventory(inventory, candidates)
    constraints = cast(dict[str, Any], inventory["local_runtime_constraints"])
    print(
        "MODEL_RESEARCH_METADATA_OK "
        f"task={inventory['task_id']} "
        f"captured_at={inventory['captured_at']} "
        f"constraints={len(constraints)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

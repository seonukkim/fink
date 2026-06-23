#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import subprocess
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any, cast


REPO_ROOT = Path(__file__).resolve().parents[2]
CANDIDATES_PATH = REPO_ROOT / "configs" / "models" / "candidates.yaml"
DRY_RUN_PATH = REPO_ROOT / "configs" / "models" / "download_size_dry_runs.yaml"

PINNED_REVISION_RE = re.compile(r"^[0-9a-f]{40}$")
REQUIRED_TOP_LEVEL = {
    "schema_version",
    "task_id",
    "captured_at",
    "base_commit",
    "depends_on",
    "human_gate",
    "source_candidates_path",
    "source_candidates_task_id",
    "dry_run_policy",
    "summary",
    "records",
}
REQUIRED_POLICY = {
    "no_weight_download",
    "no_snapshot_download",
    "capture_method",
    "estimated_disk_size_definition",
    "approved_network_gate",
    "refresh_command",
    "model_storage_boundary",
    "tracked_weight_files_at_capture",
    "weight_file_suffixes",
}
REQUIRED_RECORD = {
    "id",
    "group",
    "repo_id",
    "role",
    "license",
    "gated",
    "access_status",
    "revision_ref",
    "exact_revision",
    "revision_source_url",
    "estimated_disk_size_bytes",
    "estimated_disk_size_gb",
    "size_source",
    "dry_run_status",
    "downloaded_weight_files",
    "under_max_download_size_gb",
}


class DryRunRecordError(ValueError):
    """Raised when model download-size dry-run records are incomplete."""


def load_yaml_mapping(path: Path) -> dict[str, Any]:
    try:
        import yaml  # type: ignore[import-untyped]
    except Exception as exc:  # pragma: no cover - environment diagnostic
        raise DryRunRecordError("PyYAML is required to parse dry-run records") from exc

    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise DryRunRecordError(f"{path.relative_to(REPO_ROOT)} must contain a YAML mapping")
    return cast(dict[str, Any], data)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise DryRunRecordError(message)


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


def decimal_bytes_from_gb(value: object) -> int:
    require(isinstance(value, int | float), "file_size_gb must be numeric")
    bytes_value = Decimal(str(value)) * Decimal("1000000000")
    return int(bytes_value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def candidate_entries(candidates: dict[str, Any]) -> dict[str, dict[str, Any]]:
    groups = mapping_at(candidates, "candidates", "candidates")
    entries: dict[str, dict[str, Any]] = {}
    for group_name, group_items in groups.items():
        require(isinstance(group_name, str) and bool(group_name), "candidate groups must be named")
        require(isinstance(group_items, list) and group_items, f"candidates.{group_name} empty")
        for index, item in enumerate(group_items):
            require(isinstance(item, dict), f"candidates.{group_name}[{index}] must be a mapping")
            item = cast(dict[str, Any], item)
            candidate_id = required_string(item, "id", f"candidates.{group_name}[{index}]")
            require(candidate_id not in entries, f"duplicate candidate id: {candidate_id}")
            entries[candidate_id] = {"group": group_name, "item": item}
    return entries


def expected_disk_bytes(metadata: dict[str, Any], path: str) -> int:
    used_storage_bytes = metadata.get("used_storage_bytes")
    if isinstance(used_storage_bytes, int):
        require(used_storage_bytes > 0, f"{path}.used_storage_bytes must be positive")
        return used_storage_bytes
    return decimal_bytes_from_gb(metadata.get("file_size_gb"))


def git_tracked_weight_files(suffixes: list[str]) -> list[str]:
    proc = subprocess.run(
        ["git", "ls-files"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    normalized = tuple(suffix.lower() for suffix in suffixes)
    return sorted(
        file
        for file in proc.stdout.splitlines()
        if file.lower().endswith(normalized)
    )


def validate_dry_run_records(
    dry_run: dict[str, Any], candidates: dict[str, Any]
) -> tuple[int, int]:
    missing_top = sorted(REQUIRED_TOP_LEVEL - set(dry_run))
    require(
        not missing_top,
        "download_size_dry_runs.yaml missing fields: " + ", ".join(missing_top),
    )
    require(dry_run["schema_version"] == 1, "dry-run schema_version must be 1")
    require(dry_run["task_id"] == "FINK-MR-03", "dry-run task_id must be FINK-MR-03")
    base_commit = required_string(dry_run, "base_commit", "dry_run")
    require(
        PINNED_REVISION_RE.fullmatch(base_commit) is not None,
        "base_commit must be a full SHA",
    )
    require(dry_run["depends_on"] == ["FINK-MR-02"], "dry-run depends_on must be FINK-MR-02")
    require(
        dry_run["human_gate"] == "MODEL_METADATA_NETWORK_APPROVED",
        "dry-run human_gate must record MODEL_METADATA_NETWORK_APPROVED",
    )
    require(
        dry_run["source_candidates_path"] == "configs/models/candidates.yaml",
        "dry-run source_candidates_path must point at configs/models/candidates.yaml",
    )
    require(
        dry_run["source_candidates_task_id"] == "FINK-MR-02",
        "dry-run source_candidates_task_id must be FINK-MR-02",
    )

    policy = mapping_at(dry_run, "dry_run_policy", "dry_run")
    missing_policy = sorted(REQUIRED_POLICY - set(policy))
    require(not missing_policy, "dry_run_policy missing fields: " + ", ".join(missing_policy))
    require(policy["no_weight_download"] is True, "dry-run must not download weights")
    require(policy["no_snapshot_download"] is True, "dry-run must not call snapshot_download")
    require(
        policy["approved_network_gate"] == "MODEL_METADATA_NETWORK_APPROVED",
        "dry-run policy must record the approved metadata network gate",
    )
    require(
        isinstance(policy["tracked_weight_files_at_capture"], list)
        and not policy["tracked_weight_files_at_capture"],
        "tracked_weight_files_at_capture must be an empty list",
    )
    suffixes = policy["weight_file_suffixes"]
    require(
        isinstance(suffixes, list)
        and suffixes
        and all(isinstance(item, str) and item.startswith(".") for item in suffixes),
        "weight_file_suffixes must be a non-empty suffix list",
    )
    tracked_weights = git_tracked_weight_files(cast(list[str], suffixes))
    require(
        not tracked_weights,
        "model weight files tracked in Git: " + ", ".join(tracked_weights),
    )

    candidate_map = candidate_entries(candidates)
    candidate_capture = mapping_at(candidates, "hf_metadata_capture", "candidates")
    require(
        candidate_capture.get("task_id") == "FINK-MR-02",
        "source candidates metadata must be from FINK-MR-02",
    )
    license_policy = mapping_at(candidates, "license_policy", "candidates")
    max_download_size_gb = license_policy.get("max_download_size_gb")
    require(isinstance(max_download_size_gb, int), "max_download_size_gb missing")
    max_download_bytes = max_download_size_gb * 1_000_000_000

    records = dry_run.get("records")
    require(isinstance(records, list) and records, "dry-run records must be a non-empty list")
    require(
        len(records) == len(candidate_map),
        "dry-run records must cover every candidate exactly once",
    )
    seen_ids: set[str] = set()
    total_bytes = 0
    largest_id = ""
    largest_bytes = -1
    for index, raw_record in enumerate(records):
        require(isinstance(raw_record, dict), f"records[{index}] must be a mapping")
        record = cast(dict[str, Any], raw_record)
        missing_record = sorted(REQUIRED_RECORD - set(record))
        require(
            not missing_record,
            f"records[{index}] missing fields: " + ", ".join(missing_record),
        )
        record_path = f"records[{index}]"
        candidate_id = required_string(record, "id", record_path)
        require(candidate_id not in seen_ids, f"duplicate dry-run record id: {candidate_id}")
        seen_ids.add(candidate_id)
        require(
            candidate_id in candidate_map,
            f"dry-run record not present in candidates: {candidate_id}",
        )
        candidate = candidate_map[candidate_id]
        item = cast(dict[str, Any], candidate["item"])
        metadata_path = f"candidates.{candidate['group']}.{candidate_id}"
        metadata = mapping_at(item, "hf_metadata", metadata_path)

        require(record["group"] == candidate["group"], f"{candidate_id} group mismatch")
        for key in ("repo_id", "role"):
            require(record[key] == item.get(key), f"{candidate_id} {key} mismatch")
        for key in ("license", "gated", "access_status", "revision_ref", "revision_source_url"):
            require(record[key] == metadata.get(key), f"{candidate_id} {key} mismatch")
        require(record["gated"] is False, f"{candidate_id} must be ungated")
        require(
            record["access_status"] == "public_ungated",
            f"{candidate_id} must be public_ungated",
        )
        require(record["revision_ref"] == "main", f"{candidate_id} revision_ref must be main")

        exact_revision = required_string(record, "exact_revision", record_path)
        require(
            PINNED_REVISION_RE.fullmatch(exact_revision) is not None,
            f"{candidate_id} bad SHA",
        )
        require(
            exact_revision == metadata.get("pinned_revision"),
            f"{candidate_id} exact_revision must match hf_metadata.pinned_revision",
        )

        expected_bytes = expected_disk_bytes(metadata, f"{metadata_path}.hf_metadata")
        require(
            record["estimated_disk_size_bytes"] == expected_bytes,
            f"{candidate_id} estimated_disk_size_bytes mismatch",
        )
        require(
            expected_bytes <= max_download_bytes,
            f"{candidate_id} exceeds max_download_size_gb",
        )
        require(
            record["under_max_download_size_gb"] is True,
            f"{candidate_id} cap flag must be true",
        )
        require(
            record["downloaded_weight_files"] is False,
            f"{candidate_id} must not record downloads",
        )
        require(
            record["dry_run_status"] == "recorded_without_weight_download",
            f"{candidate_id} must be recorded_without_weight_download",
        )
        size_gb = record["estimated_disk_size_gb"]
        require(
            isinstance(size_gb, int | float) and size_gb > 0,
            f"{candidate_id} size GB invalid",
        )

        total_bytes += expected_bytes
        if expected_bytes > largest_bytes:
            largest_bytes = expected_bytes
            largest_id = candidate_id

    summary = mapping_at(dry_run, "summary", "dry_run")
    require(summary.get("candidate_count") == len(records), "summary candidate_count mismatch")
    require(
        summary.get("max_download_size_gb") == max_download_size_gb,
        "summary size cap mismatch",
    )
    require(
        summary.get("total_estimated_disk_size_bytes") == total_bytes,
        "summary total_estimated_disk_size_bytes mismatch",
    )
    require(
        summary.get("largest_candidate_id") == largest_id,
        "summary largest_candidate_id mismatch",
    )
    require(
        summary.get("largest_candidate_estimated_disk_size_bytes") == largest_bytes,
        "summary largest_candidate_estimated_disk_size_bytes mismatch",
    )
    require(
        summary.get("all_candidates_below_max_download_size_gb") is True,
        "summary cap flag invalid",
    )
    require(summary.get("downloaded_weight_files") is False, "summary must record no downloads")
    return len(records), total_bytes


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate FINK-MR-03 model download-size dry-run records."
    )
    parser.add_argument(
        "--dry-run-record",
        type=Path,
        default=DRY_RUN_PATH,
        help="Path to configs/models/download_size_dry_runs.yaml",
    )
    parser.add_argument(
        "--candidates",
        type=Path,
        default=CANDIDATES_PATH,
        help="Path to configs/models/candidates.yaml",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Validate records. Present for command readability; validation is always performed.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    dry_run = load_yaml_mapping(args.dry_run_record)
    candidates = load_yaml_mapping(args.candidates)
    record_count, total_bytes = validate_dry_run_records(dry_run, candidates)
    print(
        "MODEL_SIZE_DRY_RUN_RECORDS_OK "
        f"task={dry_run['task_id']} "
        f"records={record_count} "
        f"total_estimated_disk_size_bytes={total_bytes} "
        "tracked_weight_files=0"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

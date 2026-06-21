#!/usr/bin/env python3
from __future__ import annotations

import argparse
import contextlib
import http.client
import json
import os
import socket
import sys
import tempfile
import urllib.request
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast


REPO_ROOT = Path(__file__).resolve().parents[2]
SHORTLIST_PATH = REPO_ROOT / "configs" / "models" / "open_license_shortlist.yaml"
HUMAN_GATES_PATH = REPO_ROOT / "loop" / "HUMAN_GATES.yaml"
MODEL_PROFILE_GATE = "MODEL_PROFILE_APPROVED"
DEFAULT_PROFILE_ID = "core_local_offline_v1"
DEFAULT_PROFILE_MODEL_IDS = (
    "qwen3_embedding_0_6b",
    "qwen3_reranker_0_6b",
    "qwen3_4b",
)
OPEN_LICENSE_FLOOR = frozenset(
    {"apache-2.0", "mit", "bsd-2-clause", "bsd-3-clause", "isc", "cc0-1.0", "cc-by-4.0"}
)
OFFLINE_ENV_FLAGS = {
    "HF_HUB_OFFLINE": "1",
    "TRANSFORMERS_OFFLINE": "1",
    "HF_DATASETS_OFFLINE": "1",
    "HF_HUB_DISABLE_TELEMETRY": "1",
    "DO_NOT_TRACK": "1",
    "FINK_RUNTIME_REMOTE_API_ALLOWED": "false",
    "FINK_RUNTIME_OFFLINE": "true",
    "FINK_MODEL_DOWNLOAD_ALLOWED": "false",
}
LOCAL_LOAD_MARKERS = (
    "config.json",
    "tokenizer_config.json",
    "preprocessor_config.json",
    "processor_config.json",
    "model_index.json",
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


class OfflineLoadSmokeError(ValueError):
    """Raised when an offline local-load smoke run violates FInk policy."""


class OfflineNetworkAttemptError(RuntimeError):
    """Raised when code attempts network I/O during an offline smoke run."""


@dataclass(frozen=True)
class Candidate:
    id: str
    group: str
    repo_id: str
    role: str
    license: str
    exact_revision: str
    estimated_disk_size_bytes: int


def require(condition: bool, message: str) -> None:
    if not condition:
        raise OfflineLoadSmokeError(message)


def relative(path: Path) -> str:
    try:
        return path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def load_yaml_mapping(path: Path) -> dict[str, Any]:
    try:
        import yaml  # type: ignore[import-untyped]
    except Exception as exc:  # pragma: no cover - environment diagnostic
        raise OfflineLoadSmokeError("PyYAML is required for model smoke tests") from exc

    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    require(isinstance(data, dict), f"{relative(path)} must contain a YAML mapping")
    return cast(dict[str, Any], data)


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


def validate_profile_gate(gates: dict[str, Any], source: Path) -> dict[str, Any]:
    source_name = relative(source)
    gate_map = mapping_at(gates, "gates", source_name)
    gate = mapping_at(gate_map, MODEL_PROFILE_GATE, f"{source_name}.gates")
    status = required_string(gate, "status", f"{source_name}.gates.{MODEL_PROFILE_GATE}")
    require(
        status in {"APPROVED", "RESOLVED"},
        f"{MODEL_PROFILE_GATE} must be APPROVED or RESOLVED, got {status}",
    )
    require(
        required_bool(gate, "approved", f"{source_name}.gates.{MODEL_PROFILE_GATE}") is True,
        f"{MODEL_PROFILE_GATE} must be approved",
    )
    policy = required_string(gate, "policy", f"{source_name}.gates.{MODEL_PROFILE_GATE}")
    require(
        "open_license_floor" in policy,
        f"{MODEL_PROFILE_GATE} policy must include open_license_floor",
    )
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
    require(
        isinstance(max_download_size_gb, int) and max_download_size_gb > 0,
        "summary.max_download_size_gb invalid",
    )
    max_download_bytes = max_download_size_gb * 1_000_000_000

    accepted = shortlist.get("accepted")
    require(
        isinstance(accepted, list) and accepted,
        f"{source_name}.accepted must be a non-empty list",
    )

    candidates: dict[str, Candidate] = {}
    for index, raw_record in enumerate(accepted):
        require(isinstance(raw_record, dict), f"{source_name}.accepted[{index}] must be a mapping")
        record = cast(dict[str, Any], raw_record)
        path = f"{source_name}.accepted[{index}]"
        candidate_id = required_string(record, "id", path)
        require(candidate_id not in candidates, f"duplicate candidate id: {candidate_id}")
        license_id = required_string(record, "license", path).lower()
        require(
            license_id in accepted_license_set,
            f"{candidate_id} license not in accepted_licenses",
        )
        require(
            license_id in OPEN_LICENSE_FLOOR,
            f"{candidate_id} license not in open-license floor",
        )
        require(required_bool(record, "gated", path) is False, f"{candidate_id} is gated")
        require(required_bool(record, "private", path) is False, f"{candidate_id} is private")
        require(required_bool(record, "disabled", path) is False, f"{candidate_id} is disabled")
        require(
            record.get("access_status") == "public_ungated",
            f"{candidate_id} must be public_ungated",
        )
        require(
            record.get("decision") == "accepted_public_open",
            f"{candidate_id} must be accepted_public_open",
        )
        revision = required_string(record, "exact_revision", path)
        require(
            len(revision) == 40 and all(ch in "0123456789abcdef" for ch in revision),
            f"{candidate_id} bad revision",
        )
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

    require(summary.get("accepted_count") == len(candidates), "summary.accepted_count mismatch")
    require(summary.get("downloaded_weight_files") is False, "shortlist must remain metadata-only")
    return candidates, max_download_size_gb


def select_candidates(candidates: dict[str, Candidate], model_ids: list[str]) -> list[Candidate]:
    selected_ids = model_ids or list(DEFAULT_PROFILE_MODEL_IDS)
    selected: list[Candidate] = []
    seen: set[str] = set()
    for model_id in selected_ids:
        require(model_id in candidates, f"unknown or unapproved model id: {model_id}")
        require(model_id not in seen, f"duplicate selected model id: {model_id}")
        seen.add(model_id)
        selected.append(candidates[model_id])
    return selected


def parse_model_path_overrides(items: list[str]) -> dict[str, Path]:
    overrides: dict[str, Path] = {}
    for item in items:
        model_id, separator, raw_path = item.partition("=")
        require(
            separator == "=" and bool(model_id) and bool(raw_path),
            "--model-path must be id=/path",
        )
        require(model_id not in overrides, f"duplicate --model-path for {model_id}")
        overrides[model_id] = Path(raw_path)
    return overrides


def resolve_path(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def is_under(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def require_outside_repo(path: Path, label: str) -> Path:
    resolved = resolve_path(path)
    repo = resolve_path(REPO_ROOT)
    require(not is_under(resolved, repo), f"{label} must be outside the Git repository")
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
        "private model root must be under PRIVATE_ROOT/models",
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


def default_storage_path(candidate: Candidate, storage_mode: str, storage_root: Path) -> Path:
    if storage_mode == "private-root":
        return storage_root / candidate.id / candidate.exact_revision
    escaped_repo = candidate.repo_id.replace("/", "--")
    return storage_root / f"models--{escaped_repo}" / "snapshots" / candidate.exact_revision


def tracked_weight_files() -> list[str]:
    import subprocess

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


@contextlib.contextmanager
def offline_runtime_env() -> Iterator[dict[str, str]]:
    previous = {key: os.environ.get(key) for key in OFFLINE_ENV_FLAGS}
    os.environ.update(OFFLINE_ENV_FLAGS)
    try:
        yield dict(OFFLINE_ENV_FLAGS)
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


class NetworkBlocker:
    def __init__(self) -> None:
        self.attempts: list[str] = []
        self._original_create_connection: Any = None
        self._original_urlopen: Any = None
        self._original_http_connect: Any = None
        self._original_https_connect: Any = None
        self._original_socket_connect: Any = None
        self._original_socket_connect_ex: Any = None

    def __enter__(self) -> NetworkBlocker:
        self._original_create_connection = socket.create_connection
        self._original_urlopen = urllib.request.urlopen
        self._original_http_connect = http.client.HTTPConnection.connect
        self._original_https_connect = http.client.HTTPSConnection.connect
        self._original_socket_connect = socket.socket.connect
        self._original_socket_connect_ex = socket.socket.connect_ex

        def blocked_create_connection(address: object, *args: object, **kwargs: object) -> object:
            self._record(f"socket.create_connection:{address!r}")

        def blocked_urlopen(url: object, *args: object, **kwargs: object) -> object:
            self._record(f"urllib.request.urlopen:{url!r}")

        def blocked_http_connect(connection: object, *args: object, **kwargs: object) -> object:
            self._record(f"http.client.connect:{connection!r}")

        def blocked_socket_connect(sock: object, address: object) -> object:
            self._record(f"socket.connect:{address!r}")

        def blocked_socket_connect_ex(sock: object, address: object) -> object:
            self._record(f"socket.connect_ex:{address!r}")

        socket.create_connection = blocked_create_connection  # type: ignore[assignment]
        urllib.request.urlopen = blocked_urlopen  # type: ignore[assignment]
        http.client.HTTPConnection.connect = blocked_http_connect  # type: ignore[assignment]
        http.client.HTTPSConnection.connect = blocked_http_connect  # type: ignore[assignment]
        socket.socket.connect = blocked_socket_connect  # type: ignore[method-assign]
        socket.socket.connect_ex = blocked_socket_connect_ex  # type: ignore[method-assign]
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        socket.create_connection = self._original_create_connection
        urllib.request.urlopen = self._original_urlopen
        http.client.HTTPConnection.connect = self._original_http_connect
        http.client.HTTPSConnection.connect = self._original_https_connect
        socket.socket.connect = self._original_socket_connect
        socket.socket.connect_ex = self._original_socket_connect_ex

    def _record(self, attempt: str) -> object:
        self.attempts.append(attempt)
        raise OfflineNetworkAttemptError("network access attempted during offline model smoke test")


def load_local_model_metadata(candidate: Candidate, path: Path, load_mode: str) -> dict[str, Any]:
    resolved = require_outside_repo(path, f"model path for {candidate.id}")
    require(resolved.is_dir(), f"{candidate.id} local model directory is missing")
    markers = [marker for marker in LOCAL_LOAD_MARKERS if (resolved / marker).is_file()]
    require(markers, f"{candidate.id} has no local Hugging Face load marker")

    config_model_type: str | None = None
    config_path = resolved / "config.json"
    if config_path.is_file():
        try:
            config_data = json.loads(config_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise OfflineLoadSmokeError(f"{candidate.id} config.json is invalid JSON") from exc
        require(isinstance(config_data, dict), f"{candidate.id} config.json must be a mapping")
        raw_model_type = config_data.get("model_type")
        if isinstance(raw_model_type, str) and raw_model_type:
            config_model_type = raw_model_type

    loader = "json_config"
    if load_mode == "transformers-config":
        try:
            from transformers import AutoConfig  # type: ignore[import-not-found, import-untyped]
        except Exception as exc:  # pragma: no cover - optional integration dependency
            raise OfflineLoadSmokeError(
                "transformers is required for --load-mode transformers-config"
            ) from exc
        loaded_config = AutoConfig.from_pretrained(
            resolved.as_posix(),
            local_files_only=True,
            trust_remote_code=False,
        )
        loader = f"transformers:{loaded_config.__class__.__name__}"

    return {
        "id": candidate.id,
        "group": candidate.group,
        "role": candidate.role,
        "repo_id": candidate.repo_id,
        "license": candidate.license,
        "exact_revision": candidate.exact_revision,
        "local_directory_present": True,
        "load_mode": load_mode,
        "loader": loader,
        "load_markers": markers,
        "config_model_type": config_model_type,
        "private_path_recorded": False,
        "status": "loaded_offline_local",
    }


def run_smoke(
    shortlist_path: Path,
    human_gates_path: Path,
    model_ids: list[str],
    model_path_items: list[str],
    storage_mode: str,
    private_model_root: Path | None,
    load_mode: str,
) -> dict[str, Any]:
    gates = load_yaml_mapping(human_gates_path)
    gate = validate_profile_gate(gates, human_gates_path)
    shortlist = load_yaml_mapping(shortlist_path)
    candidates, max_download_size_gb = validate_shortlist(shortlist, shortlist_path)
    selected = select_candidates(candidates, model_ids)
    require(not tracked_weight_files(), "model weight files tracked in Git")

    overrides = parse_model_path_overrides(model_path_items)
    unknown_overrides = sorted(set(overrides) - {candidate.id for candidate in selected})
    require(
        not unknown_overrides,
        "model-path override not selected: " + ", ".join(unknown_overrides),
    )

    env = dict(os.environ)
    storage_root: Path | None = None
    if len(overrides) != len(selected):
        if storage_mode == "private-root":
            storage_root = private_storage_root(env, private_model_root)
        else:
            storage_root = hf_cache_root(env)

    records: list[dict[str, Any]] = []
    with offline_runtime_env() as runtime_flags:
        with NetworkBlocker() as blocker:
            for candidate in selected:
                path = overrides.get(candidate.id)
                if path is None:
                    require(storage_root is not None, "storage root not resolved")
                    path = default_storage_path(candidate, storage_mode, storage_root)
                records.append(load_local_model_metadata(candidate, path, load_mode))
            require(
                not blocker.attempts,
                "outbound connection attempts blocked: " + ", ".join(blocker.attempts),
            )

    return {
        "task_id": "FINK-MR-06",
        "machine_gate": "model_offline_load_smoke",
        "profile_id": DEFAULT_PROFILE_ID if not model_ids else "custom_cli_selection",
        "human_gate": MODEL_PROFILE_GATE,
        "human_gate_status": gate["status"],
        "human_gate_approved": gate["approved"],
        "storage_mode": storage_mode,
        "load_mode": load_mode,
        "max_download_size_gb": max_download_size_gb,
        "selected_count": len(records),
        "runtime_offline_flags": runtime_flags,
        "outbound_connection_attempts": 0,
        "remote_runtime_api_allowed": False,
        "models": records,
        "status": "offline_load_smoke_passed",
    }


def run_self_test() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="fink-model-smoke-") as tmp:
        root = Path(tmp)
        model_path_items: list[str] = []
        for model_id in DEFAULT_PROFILE_MODEL_IDS:
            model_dir = root / model_id
            model_dir.mkdir(parents=True)
            (model_dir / "config.json").write_text(
                json.dumps({"model_type": "bert", "fink_smoke_fixture": model_id}),
                encoding="utf-8",
            )
            model_path_items.append(f"{model_id}={model_dir.as_posix()}")

        result = run_smoke(
            shortlist_path=SHORTLIST_PATH,
            human_gates_path=HUMAN_GATES_PATH,
            model_ids=[],
            model_path_items=model_path_items,
            storage_mode="private-root",
            private_model_root=None,
            load_mode="metadata",
        )

    with NetworkBlocker() as blocker:
        try:
            socket.create_connection(("127.0.0.1", 9), timeout=0.001)
        except OfflineNetworkAttemptError:
            pass
        else:  # pragma: no cover - defensive
            raise OfflineLoadSmokeError(
                "network blocker self-test did not block socket.create_connection"
            )
        require(bool(blocker.attempts), "network blocker self-test recorded no attempt")

    try:
        require_outside_repo(REPO_ROOT / "models" / "bad", "self-test repo-local path")
    except OfflineLoadSmokeError:
        pass
    else:  # pragma: no cover - defensive
        raise OfflineLoadSmokeError("self-test did not reject a repo-local model path")

    result["self_test"] = True
    result["network_blocker_self_test"] = "blocked_socket_create_connection"
    result["repo_local_path_self_test"] = "rejected"
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run FINK-MR-06 offline local-load smoke tests for approved model profiles."
    )
    parser.add_argument("--shortlist", type=Path, default=SHORTLIST_PATH)
    parser.add_argument("--human-gates", type=Path, default=HUMAN_GATES_PATH)
    parser.add_argument(
        "--model-id",
        action="append",
        default=[],
        help="Approved shortlist id to smoke-load",
    )
    parser.add_argument(
        "--model-path",
        action="append",
        default=[],
        help="Override a selected model path as id=/private/local/path",
    )
    parser.add_argument("--storage", choices=("private-root", "hf-cache"), default="private-root")
    parser.add_argument("--private-model-root", type=Path, default=None)
    parser.add_argument(
        "--load-mode",
        choices=("metadata", "transformers-config"),
        default="metadata",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON output")
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run the offline smoke harness on temp local fixtures",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.self_test:
            result = run_self_test()
        else:
            result = run_smoke(
                shortlist_path=args.shortlist,
                human_gates_path=args.human_gates,
                model_ids=cast(list[str], args.model_id),
                model_path_items=cast(list[str], args.model_path),
                storage_mode=args.storage,
                private_model_root=args.private_model_root,
                load_mode=args.load_mode,
            )
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        else:
            print(
                "MODEL_OFFLINE_LOAD_SMOKE_OK "
                f"profile={result['profile_id']} "
                f"selected={result['selected_count']} "
                f"load_mode={result['load_mode']} "
                "outbound_connection_attempts=0"
            )
        return 0
    except OfflineLoadSmokeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

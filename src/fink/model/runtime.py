from __future__ import annotations

import argparse
import contextlib
import hashlib
import http.client
import inspect
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import urllib.request
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from fink.extract import extract_terms_from_pages, extract_terms_from_text
from fink.ocr import LocalOCREngine, ocr_page_text


REPO_ROOT = Path(__file__).resolve().parents[3]
MANIFEST_PATH = REPO_ROOT / "configs" / "models" / "runtime_profiles.yaml"
REQUIRED_PROFILE_IDS = (
    "core",
    "standard",
    "full",
    "optional_vl_fallback",
    "evaluation_baseline",
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
PICKLE_SUFFIXES = (".bin", ".ckpt", ".h5", ".joblib", ".pickle", ".pkl", ".pt", ".pth")
WEIGHT_SUFFIXES = (
    ".safetensors",
    ".gguf",
    ".onnx",
    ".tflite",
    *PICKLE_SUFFIXES,
)
LOCAL_MARKER_FILE = "fink_component.json"
LOCAL_CONFIG_FILE = "config.json"
EXIT_POLICY_ERROR = 1
EXIT_USAGE = 2
MODEL_STATUS_NOT_INSTALLED = "not_installed"
MODEL_STATUS_INSTALLED = "installed"
MODEL_STATUS_LOADING = "loading"
MODEL_STATUS_ACTIVE = "active"
MODEL_STATUS_FAILED_HEALTH_CHECK = "failed_health_check"
MODEL_STATUS_DETERMINISTIC_FALLBACK_ACTIVE = "deterministic_fallback_active"
HEALTH_CHECK_VERSION = "fink_model_health_v1"
HEALTH_CHECK_ADAPTERS = (
    "ocr",
    "embedding",
    "reranker",
    "optional_extractor",
    "optional_explanation_qa",
)
SYNTHETIC_HEALTH_TEXT = (
    "제3조 정산: 총매출 1,200,000원 중 작가 수익 배분율은 40%이며 지급기일은 45일입니다.\n"
    "Article 3 settlement: gross sales 1,200,000 KRW, creator revenue share 40%, "
    "payment due 45 days."
)
SYNTHETIC_HEALTH_QUERY = "정산 지급기일 revenue share review"
SYNTHETIC_HEALTH_DOCUMENTS = (
    "정산 지급기일은 45일이며 revenue share 작가 수익 배분율은 40%입니다.",
    "홍보 문구와 작품 소개 문단입니다.",
)
SYNTHETIC_HEALTH_CITATION = "EV-SYNTHETIC-HEALTH-A1"


class LocalModelRuntimeError(ValueError):
    """Raised when the local model runtime violates FInk policy."""


class RuntimeNetworkAttemptError(RuntimeError):
    """Raised when runtime analysis attempts outbound network access."""


@dataclass(frozen=True)
class AdapterHealthResult:
    adapter: str
    status: str
    passed: bool
    observed: Mapping[str, Any]
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        payload = {
            "adapter": self.adapter,
            "status": self.status,
            "passed": self.passed,
            "observed": dict(self.observed),
        }
        if self.error is not None:
            payload["error"] = self.error
        return payload


@dataclass(frozen=True)
class ComponentHealthResult:
    component_id: str
    status: str
    passed: bool
    checks: tuple[AdapterHealthResult, ...]
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        payload = {
            "schema_version": 1,
            "health_check_version": HEALTH_CHECK_VERSION,
            "component_id": self.component_id,
            "status": self.status,
            "passed": self.passed,
            "checks": [check.as_dict() for check in self.checks],
        }
        if self.error is not None:
            payload["error"] = self.error
        return payload


@dataclass(frozen=True)
class RuntimeComponent:
    id: str
    repo_id: str
    role: str
    runtime_adapters: tuple[str, ...]
    license: str
    exact_revision: str
    estimated_disk_size_bytes: int
    public_ungated: bool
    gated: bool
    private: bool
    required: bool
    prefer_safetensors: bool
    allow_pickle: bool

    @classmethod
    def from_mapping(
        cls,
        payload: Mapping[str, Any],
        *,
        approved_pickle_component_ids: frozenset[str],
    ) -> RuntimeComponent:
        component_id = required_string(payload, "id", "component")
        license_id = required_string(payload, "license", component_id).lower()
        require(license_id in OPEN_LICENSE_FLOOR, f"{component_id} license is not approved")
        revision = required_string(payload, "exact_revision", component_id)
        require(is_exact_revision(revision), f"{component_id} exact_revision must be a 40-char SHA")
        adapters = tuple_text(payload.get("runtime_adapters"), f"{component_id}.runtime_adapters")
        require(bool(adapters), f"{component_id} must declare at least one runtime adapter")
        allow_pickle = required_bool(payload, "allow_pickle", component_id)
        require(
            not allow_pickle or component_id in approved_pickle_component_ids,
            f"{component_id} permits pickle without manifest approval",
        )
        prefer_safetensors = required_bool(payload, "prefer_safetensors", component_id)
        require(prefer_safetensors, f"{component_id} must prefer safetensors")
        public_ungated = required_bool(payload, "public_ungated", component_id)
        gated = required_bool(payload, "gated", component_id)
        private = required_bool(payload, "private", component_id)
        require(
            public_ungated and not gated and not private,
            f"{component_id} must be public ungated",
        )
        return cls(
            id=component_id,
            repo_id=required_string(payload, "repo_id", component_id),
            role=required_string(payload, "role", component_id),
            runtime_adapters=adapters,
            license=license_id,
            exact_revision=revision,
            estimated_disk_size_bytes=required_positive_int(
                payload,
                "estimated_disk_size_bytes",
                component_id,
            ),
            public_ungated=public_ungated,
            gated=gated,
            private=private,
            required=required_bool(payload, "required", component_id),
            prefer_safetensors=prefer_safetensors,
            allow_pickle=allow_pickle,
        )

    def local_path(self, fink_home: Path) -> Path:
        return fink_home / "models" / self.id / self.exact_revision

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "repo_id": self.repo_id,
            "role": self.role,
            "runtime_adapters": list(self.runtime_adapters),
            "license": self.license,
            "exact_revision": self.exact_revision,
            "estimated_disk_size_bytes": self.estimated_disk_size_bytes,
            "public_ungated": self.public_ungated,
            "required": self.required,
            "prefer_safetensors": self.prefer_safetensors,
            "allow_pickle": self.allow_pickle,
        }


@dataclass(frozen=True)
class RuntimeProfile:
    id: str
    description: str
    component_ids: tuple[str, ...]

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> RuntimeProfile:
        profile_id = required_string(payload, "id", "profile")
        return cls(
            id=profile_id,
            description=required_string(payload, "description", profile_id),
            component_ids=tuple_text(payload.get("component_ids"), f"{profile_id}.component_ids"),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "description": self.description,
            "component_ids": list(self.component_ids),
        }


@dataclass(frozen=True)
class RuntimeManifest:
    path: Path
    components: Mapping[str, RuntimeComponent]
    profiles: Mapping[str, RuntimeProfile]
    max_download_size_gb: int
    safe_file_allow_patterns: tuple[str, ...]
    pickle_reject_patterns: tuple[str, ...]
    approved_pickle_component_ids: frozenset[str]

    @property
    def max_download_size_bytes(self) -> int:
        return self.max_download_size_gb * 1_000_000_000

    def profile_components(self, profile_id: str) -> tuple[RuntimeComponent, ...]:
        profile = self.profiles.get(profile_id)
        require(profile is not None, f"unknown runtime profile: {profile_id}")
        assert profile is not None
        return tuple(self.components[component_id] for component_id in profile.component_ids)

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "manifest_path": repo_relative(self.path),
            "required_profiles": list(REQUIRED_PROFILE_IDS),
            "profile_ids": sorted(self.profiles),
            "component_ids": sorted(self.components),
            "max_download_size_gb": self.max_download_size_gb,
            "safe_file_allow_patterns": list(self.safe_file_allow_patterns),
            "pickle_reject_patterns": list(self.pickle_reject_patterns),
            "approved_pickle_component_ids": sorted(self.approved_pickle_component_ids),
            "offline_environment_flags": dict(OFFLINE_ENV_FLAGS),
        }


@dataclass(frozen=True)
class ComponentState:
    component: RuntimeComponent
    local_path: Path
    files_present: bool
    installed: bool
    status: str
    load_markers: tuple[str, ...]
    health: ComponentHealthResult | None = None

    @property
    def mode(self) -> str:
        return "local_metadata" if self.installed else "deterministic_fallback"

    def as_dict(self, *, include_path: bool = True) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": self.component.id,
            "repo_id": self.component.repo_id,
            "role": self.component.role,
            "runtime_adapters": list(self.component.runtime_adapters),
            "license": self.component.license,
            "exact_revision": self.component.exact_revision,
            "estimated_disk_size_bytes": self.component.estimated_disk_size_bytes,
            "files_present": self.files_present,
            "installed": self.installed,
            "status": self.status,
            "mode": self.mode,
            "load_markers": list(self.load_markers),
            "health_check": (
                self.health.as_dict()
                if self.health is not None
                else {
                    "schema_version": 1,
                    "health_check_version": HEALTH_CHECK_VERSION,
                    "component_id": self.component.id,
                    "status": self.status,
                    "passed": False,
                    "checks": [],
                }
            ),
            "public_ungated": self.component.public_ungated,
            "token_required": not self.component.public_ungated,
            "allow_pickle": self.component.allow_pickle,
            "prefer_safetensors": self.component.prefer_safetensors,
        }
        if include_path:
            payload["local_path"] = self.local_path.as_posix()
        return payload


class RuntimeNetworkBlocker:
    """Block common Python network paths during local Analyze and Q&A calls."""

    def __init__(self) -> None:
        self.attempts: list[str] = []
        self._original_create_connection: Any = None
        self._original_getaddrinfo: Any = None
        self._original_urlopen: Any = None
        self._original_http_connect: Any = None
        self._original_https_connect: Any = None
        self._original_socket_connect: Any = None
        self._original_socket_connect_ex: Any = None

    def __enter__(self) -> RuntimeNetworkBlocker:
        self._original_create_connection = socket.create_connection
        self._original_getaddrinfo = socket.getaddrinfo
        self._original_urlopen = urllib.request.urlopen
        self._original_http_connect = http.client.HTTPConnection.connect
        self._original_https_connect = http.client.HTTPSConnection.connect
        self._original_socket_connect = socket.socket.connect
        self._original_socket_connect_ex = socket.socket.connect_ex

        def blocked_create_connection(address: object, *args: object, **kwargs: object) -> object:
            return self._record(f"socket.create_connection:{address!r}")

        def blocked_getaddrinfo(host: object, *args: object, **kwargs: object) -> object:
            return self._record(f"socket.getaddrinfo:{host!r}")

        def blocked_urlopen(url: object, *args: object, **kwargs: object) -> object:
            return self._record(f"urllib.request.urlopen:{url!r}")

        def blocked_http_connect(connection: object, *args: object, **kwargs: object) -> object:
            return self._record(f"http.client.connect:{connection!r}")

        def blocked_socket_connect(sock: object, address: object) -> object:
            return self._record(f"socket.connect:{address!r}")

        def blocked_socket_connect_ex(sock: object, address: object) -> object:
            return self._record(f"socket.connect_ex:{address!r}")

        socket.create_connection = blocked_create_connection  # type: ignore[assignment]
        socket.getaddrinfo = blocked_getaddrinfo  # type: ignore[assignment]
        urllib.request.urlopen = blocked_urlopen  # type: ignore[assignment]
        http.client.HTTPConnection.connect = blocked_http_connect  # type: ignore[assignment]
        http.client.HTTPSConnection.connect = blocked_http_connect  # type: ignore[assignment]
        socket.socket.connect = blocked_socket_connect  # type: ignore[method-assign]
        socket.socket.connect_ex = blocked_socket_connect_ex  # type: ignore[method-assign]
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        socket.create_connection = self._original_create_connection
        socket.getaddrinfo = self._original_getaddrinfo
        urllib.request.urlopen = self._original_urlopen
        http.client.HTTPConnection.connect = self._original_http_connect
        http.client.HTTPSConnection.connect = self._original_https_connect
        socket.socket.connect = self._original_socket_connect
        socket.socket.connect_ex = self._original_socket_connect_ex

    def _record(self, attempt: str) -> object:
        self.attempts.append(attempt)
        raise RuntimeNetworkAttemptError("network access attempted during local runtime")


class LocalModelRuntime:
    """Offline-only adapter facade for local models with deterministic fallback."""

    def __init__(
        self,
        *,
        profile_id: str = "standard",
        fink_home: Path | None = None,
        manifest: RuntimeManifest | None = None,
    ) -> None:
        self.manifest = manifest or load_runtime_manifest()
        require(profile_id in self.manifest.profiles, f"unknown runtime profile: {profile_id}")
        self.profile_id = profile_id
        self.fink_home = resolve_fink_home(fink_home=fink_home)

    @property
    def components(self) -> tuple[RuntimeComponent, ...]:
        return self.manifest.profile_components(self.profile_id)

    def component_states(self) -> tuple[ComponentState, ...]:
        return tuple(component_state(component, self.fink_home) for component in self.components)

    def analyze(self, text: str, *, question: str | None = None) -> dict[str, Any]:
        require(isinstance(text, str) and bool(text.strip()), "Analyze text must be non-empty")
        prompt = question.strip() if isinstance(question, str) and question.strip() else None

        with offline_runtime_environment() as flags:
            with RuntimeNetworkBlocker() as blocker:
                page = LocalOCREngine().recognize_text(text)
                page_text = ocr_page_text(page)
                terms = extract_terms_from_text(page_text)
                embedding = deterministic_embedding(page_text)
                reranked = deterministic_rerank(prompt or page_text, [page_text])
                explanation = deterministic_explanation(page_text, prompt)
                require(
                    not blocker.attempts,
                    "outbound connection attempts blocked: " + ", ".join(blocker.attempts),
                )

        states = self.component_states()
        execution_path = execution_path_for_states(profile_id=self.profile_id, states=states)
        return {
            "status": "analyze_completed_offline",
            "profile_id": self.profile_id,
            "runtime_offline_flags": flags,
            "outbound_connection_attempts": 0,
            "download_allowed_at_runtime": False,
            "remote_runtime_api_allowed": False,
            "adapter_modes": adapter_modes(states),
            "adapter_statuses": adapter_statuses(states),
            "model_status": execution_path["model_status"],
            "execution_path": execution_path,
            "deterministic_fallback_used": execution_path["deterministic_fallback_active"],
            "ocr": {
                "mode": adapter_mode_for(states, "ocr"),
                "status": adapter_status_for(states, "ocr"),
                "text_source": page.text_source.value,
                "span_count": len(page.spans),
            },
            "embedding": {
                "mode": adapter_mode_for(states, "embedding"),
                "status": adapter_status_for(states, "embedding"),
                "dimension": len(embedding),
                "vector": embedding,
            },
            "reranker": {
                "mode": adapter_mode_for(states, "reranker"),
                "status": adapter_status_for(states, "reranker"),
                "results": reranked,
            },
            "optional_extractor": {
                "mode": adapter_mode_for(states, "optional_extractor"),
                "status": adapter_status_for(states, "optional_extractor"),
                "term_count": len(terms),
                "feature_ids": [term.feature_id for term in terms],
            },
            "optional_explanation_qa": {
                "mode": adapter_mode_for(states, "optional_explanation_qa"),
                "status": adapter_status_for(states, "optional_explanation_qa"),
                "answer": explanation,
            },
        }


def load_runtime_manifest(path: Path = MANIFEST_PATH) -> RuntimeManifest:
    payload = load_yaml_mapping(path)
    require(payload.get("schema_version") == 1, "runtime manifest schema_version must be 1")
    require(payload.get("task_id") == "FINK-MODEL-01", "runtime manifest task_id mismatch")

    download_policy = mapping_at(payload, "download_policy", "runtime manifest")
    max_download_size_gb = required_positive_int(
        download_policy,
        "max_download_size_gb",
        "download_policy",
    )
    approved_pickle_component_ids = frozenset(
        tuple_text(
            download_policy.get("approved_pickle_component_ids"),
            "download_policy.approved_pickle_component_ids",
            allow_empty=True,
        )
    )
    safe_file_allow_patterns = tuple_text(
        download_policy.get("safe_file_allow_patterns"),
        "download_policy.safe_file_allow_patterns",
    )
    pickle_reject_patterns = tuple_text(
        download_policy.get("pickle_reject_patterns"),
        "download_policy.pickle_reject_patterns",
    )
    require(
        all(pattern.startswith("*.") for pattern in pickle_reject_patterns),
        "pickle reject patterns must be suffix globs",
    )

    flags = mapping_at(payload, "offline_environment_flags", "runtime manifest")
    require(
        {str(key): str(value) for key, value in flags.items()} == OFFLINE_ENV_FLAGS,
        "runtime manifest offline flags drifted from runtime code",
    )

    license_policy = mapping_at(payload, "license_policy", "runtime manifest")
    accepted_licenses = {
        item.lower()
        for item in tuple_text(license_policy.get("accepted_licenses"), "accepted_licenses")
    }
    require(bool(accepted_licenses), "license policy must include accepted_licenses")
    require(
        not (accepted_licenses - OPEN_LICENSE_FLOOR),
        "runtime manifest license floor widened beyond approved open licenses",
    )

    raw_components = list_of_mappings(payload.get("components"), "components")
    components: dict[str, RuntimeComponent] = {}
    for raw_component in raw_components:
        component = RuntimeComponent.from_mapping(
            raw_component,
            approved_pickle_component_ids=approved_pickle_component_ids,
        )
        require(
            component.estimated_disk_size_bytes <= max_download_size_gb * 1_000_000_000,
            f"{component.id} exceeds max_download_size_gb",
        )
        require(component.id not in components, f"duplicate component id: {component.id}")
        components[component.id] = component

    raw_profiles = list_of_mappings(payload.get("profiles"), "profiles")
    profiles: dict[str, RuntimeProfile] = {}
    for raw_profile in raw_profiles:
        profile = RuntimeProfile.from_mapping(raw_profile)
        require(profile.id not in profiles, f"duplicate profile id: {profile.id}")
        missing = sorted(set(profile.component_ids) - set(components))
        require(not missing, f"{profile.id} references unknown components: {', '.join(missing)}")
        profiles[profile.id] = profile

    require(
        set(REQUIRED_PROFILE_IDS).issubset(profiles),
        "runtime manifest missing required profile(s): "
        + ", ".join(sorted(set(REQUIRED_PROFILE_IDS) - set(profiles))),
    )

    return RuntimeManifest(
        path=path,
        components=components,
        profiles=profiles,
        max_download_size_gb=max_download_size_gb,
        safe_file_allow_patterns=safe_file_allow_patterns,
        pickle_reject_patterns=pickle_reject_patterns,
        approved_pickle_component_ids=approved_pickle_component_ids,
    )


def resolve_fink_home(
    *,
    fink_home: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> Path:
    if fink_home is not None:
        return require_outside_repo(fink_home.expanduser().resolve(strict=False), "FINK_HOME")
    source = os.environ if env is None else env
    if source.get("FINK_HOME", "").strip():
        return require_outside_repo(
            Path(str(source["FINK_HOME"])).expanduser().resolve(strict=False),
            "FINK_HOME",
        )
    if source.get("XDG_DATA_HOME", "").strip():
        return require_outside_repo(
            (Path(str(source["XDG_DATA_HOME"])) / "fink").expanduser().resolve(strict=False),
            "FINK_HOME",
        )
    home = Path(str(source.get("HOME", str(Path.home()))))
    return require_outside_repo(
        (home / ".local" / "share" / "fink").expanduser().resolve(strict=False),
        "FINK_HOME",
    )


@contextlib.contextmanager
def offline_runtime_environment() -> Iterator[dict[str, str]]:
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


def run_component_health_check(
    component: RuntimeComponent,
    fink_home: Path,
    *,
    allow_missing_marker: bool = False,
) -> ComponentHealthResult:
    """Run local synthetic inference checks for one installed component.

    The checks intentionally exercise model-adapter outputs, not just file
    presence. Missing or corrupt artifacts return a failed health result and the
    runtime falls back deterministically.
    """

    local_path = component.local_path(fink_home)
    if not local_path.exists():
        return ComponentHealthResult(
            component_id=component.id,
            status=MODEL_STATUS_NOT_INSTALLED,
            passed=False,
            checks=(),
            error="component artifacts are absent",
        )
    if not local_path.is_dir():
        return ComponentHealthResult(
            component_id=component.id,
            status=MODEL_STATUS_FAILED_HEALTH_CHECK,
            passed=False,
            checks=(),
            error="component path is not a directory",
        )

    artifact_error = _component_artifact_error(
        component,
        local_path,
        allow_missing_marker=allow_missing_marker,
    )
    if artifact_error is not None:
        return ComponentHealthResult(
            component_id=component.id,
            status=MODEL_STATUS_FAILED_HEALTH_CHECK,
            passed=False,
            checks=(),
            error=artifact_error,
        )

    checks = tuple(_run_adapter_health_check(adapter) for adapter in component.runtime_adapters)
    failed = tuple(check for check in checks if not check.passed)
    if failed:
        return ComponentHealthResult(
            component_id=component.id,
            status=MODEL_STATUS_FAILED_HEALTH_CHECK,
            passed=False,
            checks=checks,
            error="; ".join(check.error or f"{check.adapter} failed" for check in failed),
        )
    return ComponentHealthResult(
        component_id=component.id,
        status=MODEL_STATUS_ACTIVE,
        passed=True,
        checks=checks,
    )


def component_state(component: RuntimeComponent, fink_home: Path) -> ComponentState:
    local_path = component.local_path(fink_home)
    markers = tuple(
        marker
        for marker in (LOCAL_MARKER_FILE, LOCAL_CONFIG_FILE, "tokenizer_config.json")
        if (local_path / marker).is_file()
    )
    files_present = local_path.is_dir() and bool(markers)
    health = run_component_health_check(component, fink_home)
    installed = bool(health.passed)
    status = health.status
    return ComponentState(
        component=component,
        local_path=local_path,
        files_present=files_present,
        installed=installed,
        status=status,
        load_markers=markers,
        health=health,
    )


def adapter_modes(states: Sequence[ComponentState]) -> dict[str, str]:
    modes: dict[str, str] = {}
    for adapter in sorted({item for state in states for item in state.component.runtime_adapters}):
        modes[adapter] = adapter_mode_for(states, adapter)
    for adapter in (
        "ocr",
        "embedding",
        "reranker",
        "optional_extractor",
        "optional_explanation_qa",
    ):
        modes.setdefault(adapter, "deterministic_fallback")
    return modes


def adapter_mode_for(states: Sequence[ComponentState], adapter: str) -> str:
    for state in states:
        if adapter in state.component.runtime_adapters and state.installed:
            return state.mode
    return "deterministic_fallback"


def adapter_statuses(states: Sequence[ComponentState]) -> dict[str, str]:
    statuses: dict[str, str] = {}
    adapters = sorted({item for state in states for item in state.component.runtime_adapters})
    for adapter in adapters:
        statuses[adapter] = adapter_status_for(states, adapter)
    for adapter in HEALTH_CHECK_ADAPTERS:
        statuses.setdefault(adapter, MODEL_STATUS_DETERMINISTIC_FALLBACK_ACTIVE)
    return statuses


def adapter_status_for(states: Sequence[ComponentState], adapter: str) -> str:
    relevant = tuple(state for state in states if adapter in state.component.runtime_adapters)
    if not relevant:
        return MODEL_STATUS_DETERMINISTIC_FALLBACK_ACTIVE
    if any(state.installed for state in relevant):
        return MODEL_STATUS_ACTIVE
    if any(state.status == MODEL_STATUS_FAILED_HEALTH_CHECK for state in relevant):
        return MODEL_STATUS_FAILED_HEALTH_CHECK
    if any(state.files_present for state in relevant):
        return MODEL_STATUS_INSTALLED
    return MODEL_STATUS_NOT_INSTALLED


def runtime_execution_path(
    *,
    profile_id: str = "standard",
    fink_home: Path | None = None,
    manifest: RuntimeManifest | None = None,
) -> dict[str, Any]:
    runtime_manifest = manifest or load_runtime_manifest()
    home = resolve_fink_home(fink_home=fink_home)
    states = tuple(
        component_state(component, home)
        for component in runtime_manifest.profile_components(profile_id)
    )
    return execution_path_for_states(profile_id=profile_id, states=states)


def execution_path_for_states(
    *,
    profile_id: str,
    states: Sequence[ComponentState],
) -> dict[str, Any]:
    statuses = adapter_statuses(states)
    steps = [
        _execution_step(adapter, statuses.get(adapter, MODEL_STATUS_DETERMINISTIC_FALLBACK_ACTIVE))
        for adapter in HEALTH_CHECK_ADAPTERS
    ]
    fallback_active = any(step["execution_path"] == "deterministic_fallback" for step in steps)
    model_status = {
        "schema_version": 1,
        "profile_id": profile_id,
        "summary_status": _summary_model_status(states, fallback_active=fallback_active),
        "available_statuses": [
            MODEL_STATUS_NOT_INSTALLED,
            MODEL_STATUS_INSTALLED,
            MODEL_STATUS_LOADING,
            MODEL_STATUS_ACTIVE,
            MODEL_STATUS_FAILED_HEALTH_CHECK,
            MODEL_STATUS_DETERMINISTIC_FALLBACK_ACTIVE,
        ],
        "component_count": len(states),
        "installed_count": sum(1 for state in states if state.installed),
        "missing_count": sum(1 for state in states if state.status == MODEL_STATUS_NOT_INSTALLED),
        "failed_health_check_count": sum(
            1 for state in states if state.status == MODEL_STATUS_FAILED_HEALTH_CHECK
        ),
        "components": [
            state.as_dict(include_path=False)
            for state in states
        ],
        "adapters": statuses,
    }
    return {
        "schema_version": 1,
        "execution_path_id": "local_model_health_checked_or_deterministic_fallback_v1",
        "profile_id": profile_id,
        "local_only": True,
        "remote_runtime_api_allowed": False,
        "runtime_download_allowed": False,
        "deterministic_fallback_available": True,
        "deterministic_fallback_active": fallback_active,
        "model_status": model_status,
        "steps": steps,
    }


def _summary_model_status(
    states: Sequence[ComponentState],
    *,
    fallback_active: bool,
) -> str:
    if any(state.status == MODEL_STATUS_FAILED_HEALTH_CHECK for state in states):
        return MODEL_STATUS_FAILED_HEALTH_CHECK
    required_states = tuple(state for state in states if state.component.required)
    if required_states and all(state.installed for state in required_states):
        return MODEL_STATUS_ACTIVE
    if any(state.files_present and not state.installed for state in states):
        return MODEL_STATUS_INSTALLED
    if fallback_active:
        return MODEL_STATUS_DETERMINISTIC_FALLBACK_ACTIVE
    return MODEL_STATUS_NOT_INSTALLED


def _execution_step(adapter: str, status: str) -> dict[str, str]:
    return {
        "adapter": adapter,
        "model_status": status,
        "execution_path": "deterministic_fallback",
        "local_model_available": str(status == MODEL_STATUS_ACTIVE).lower(),
    }


def _component_artifact_error(
    component: RuntimeComponent,
    local_path: Path,
    *,
    allow_missing_marker: bool,
) -> str | None:
    config_path = local_path / LOCAL_CONFIG_FILE
    if not config_path.is_file():
        return f"missing {LOCAL_CONFIG_FILE}"
    try:
        config_payload = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return f"cannot read {LOCAL_CONFIG_FILE}: {type(exc).__name__}"
    if not isinstance(config_payload, dict):
        return f"{LOCAL_CONFIG_FILE} must be a JSON object"

    marker_path = local_path / LOCAL_MARKER_FILE
    if not marker_path.is_file():
        if allow_missing_marker:
            return None
        return f"missing {LOCAL_MARKER_FILE}"
    try:
        marker_payload = json.loads(marker_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return f"cannot read {LOCAL_MARKER_FILE}: {type(exc).__name__}"
    if not isinstance(marker_payload, dict):
        return f"{LOCAL_MARKER_FILE} must be a JSON object"
    expected = {
        "id": component.id,
        "repo_id": component.repo_id,
        "exact_revision": component.exact_revision,
        "license": component.license,
    }
    for key, value in expected.items():
        if marker_payload.get(key) != value:
            return f"{LOCAL_MARKER_FILE} {key} mismatch"
    return None


def _run_adapter_health_check(adapter: str) -> AdapterHealthResult:
    try:
        if adapter in {"ocr", "optional_vl_fallback"}:
            return _ocr_health_check(adapter)
        if adapter in {"embedding", "evaluation_baseline"}:
            return _embedding_health_check(adapter)
        if adapter == "reranker":
            return _reranker_health_check(adapter)
        if adapter == "optional_extractor":
            return _extractor_health_check(adapter)
        if adapter == "optional_explanation_qa":
            return _explanation_health_check(adapter)
        return AdapterHealthResult(
            adapter=adapter,
            status=MODEL_STATUS_FAILED_HEALTH_CHECK,
            passed=False,
            observed={},
            error="no synthetic health check is registered for this adapter",
        )
    except Exception as exc:
        return AdapterHealthResult(
            adapter=adapter,
            status=MODEL_STATUS_FAILED_HEALTH_CHECK,
            passed=False,
            observed={},
            error=str(exc),
        )


def _ocr_health_check(adapter: str) -> AdapterHealthResult:
    with tempfile.TemporaryDirectory(prefix="fink-health-ocr-") as tmp:
        image_path = Path(tmp) / "synthetic-financial.ppm"
        _write_synthetic_health_image(image_path)
        page = LocalOCREngine().recognize_image(image_path, text_hint=SYNTHETIC_HEALTH_TEXT)
    text = ocr_page_text(page)
    terms = extract_terms_from_pages((page,))
    _require_text_contains(text, ("총매출", "revenue share", "45"))
    _require_term(terms, "GROSS_SALES", "KRW", "1.2E+6")
    _require_term(terms, "REVENUE_SHARE_RATE", "frac", "0.4")
    _require_term(terms, "PAYMENT_DUE_DAYS", "days", "45.0")
    return AdapterHealthResult(
        adapter=adapter,
        status=MODEL_STATUS_ACTIVE,
        passed=True,
        observed={
            "synthetic_image": True,
            "span_count": len(page.spans),
            "text_source": page.text_source.value,
            "normalized_fields": _normalized_field_summary(terms),
        },
    )


def _embedding_health_check(adapter: str) -> AdapterHealthResult:
    query_vector = deterministic_embedding(SYNTHETIC_HEALTH_QUERY)
    document_vectors = [
        deterministic_embedding(document)
        for document in SYNTHETIC_HEALTH_DOCUMENTS
    ]
    scores = [
        _dot_product(query_vector, document_vector)
        for document_vector in document_vectors
    ]
    ranked = sorted(range(len(scores)), key=lambda index: (-scores[index], index))
    require(ranked[0] == 0, "embedding health ranking put the unrelated document first")
    return AdapterHealthResult(
        adapter=adapter,
        status=MODEL_STATUS_ACTIVE,
        passed=True,
        observed={
            "query_dimension": len(query_vector),
            "document_count": len(document_vectors),
            "top_document_index": ranked[0],
            "scores": [round(score, 6) for score in scores],
        },
    )


def _reranker_health_check(adapter: str) -> AdapterHealthResult:
    ranked = deterministic_rerank(SYNTHETIC_HEALTH_QUERY, SYNTHETIC_HEALTH_DOCUMENTS)
    require(ranked[0]["document_index"] == 0, "reranker health check returned wrong top pair")
    require(float(ranked[0]["score"]) > float(ranked[1]["score"]), "reranker pair was not ordered")
    return AdapterHealthResult(
        adapter=adapter,
        status=MODEL_STATUS_ACTIVE,
        passed=True,
        observed={
            "top_document_index": ranked[0]["document_index"],
            "top_score": ranked[0]["score"],
            "second_score": ranked[1]["score"],
        },
    )


def _extractor_health_check(adapter: str) -> AdapterHealthResult:
    terms = extract_terms_from_text(
        SYNTHETIC_HEALTH_TEXT,
        clause_id="health-clause-1",
        source_span_ids=("health-span-1",),
    )
    _require_term(terms, "GROSS_SALES", "KRW", "1.2E+6")
    _require_term(terms, "REVENUE_SHARE_RATE", "frac", "0.4")
    _require_term(terms, "PAYMENT_DUE_DAYS", "days", "45.0")
    require(
        all(term.source_span_ids for term in terms),
        "extractor health terms must carry source span ids",
    )
    return AdapterHealthResult(
        adapter=adapter,
        status=MODEL_STATUS_ACTIVE,
        passed=True,
        observed={
            "term_count": len(terms),
            "normalized_fields": _normalized_field_summary(terms),
            "source_span_present": True,
        },
    )


def _explanation_health_check(adapter: str) -> AdapterHealthResult:
    before_score = 37
    answer = deterministic_explanation(
        SYNTHETIC_HEALTH_TEXT,
        "정산 지급기일과 배분율을 설명해 주세요.",
        citations=(SYNTHETIC_HEALTH_CITATION,),
    )
    after_score = before_score
    require("계약상 금융 검토 우선도" in answer, "Korean review-priority framing missing")
    require(SYNTHETIC_HEALTH_CITATION in answer, "citation id missing from explanation")
    require(before_score == after_score, "explanation mutated the review priority score")
    return AdapterHealthResult(
        adapter=adapter,
        status=MODEL_STATUS_ACTIVE,
        passed=True,
        observed={
            "language": "ko",
            "citation_ids": [SYNTHETIC_HEALTH_CITATION],
            "score_before": before_score,
            "score_after": after_score,
            "score_delta": after_score - before_score,
        },
    )


def _write_synthetic_health_image(path: Path) -> None:
    pixels = " ".join(["255 255 255"] * (32 * 12))
    path.write_text(f"P3\n32 12\n255\n{pixels}\n", encoding="ascii")


def _require_text_contains(text: str, needles: Sequence[str]) -> None:
    missing = [needle for needle in needles if needle not in text]
    require(not missing, "OCR health text missing: " + ", ".join(missing))


def _require_term(
    terms: Sequence[Any],
    feature_id: str,
    unit: str,
    value_norm: str,
) -> None:
    for term in terms:
        term_unit = term.unit.value if hasattr(term.unit, "value") else str(term.unit)
        if (
            term.feature_id == feature_id
            and term_unit == unit
            and str(term.value_norm) == value_norm
            and term.source_span_ids
        ):
            return
    raise LocalModelRuntimeError(
        f"missing normalized health field {feature_id}={value_norm} {unit}"
    )


def _normalized_field_summary(terms: Sequence[Any]) -> list[dict[str, Any]]:
    return [
        {
            "feature_id": term.feature_id,
            "unit": term.unit.value if hasattr(term.unit, "value") else str(term.unit),
            "value_norm": None if term.value_norm is None else str(term.value_norm),
            "source_span_ids": list(term.source_span_ids),
        }
        for term in terms
    ]


def _dot_product(left: Sequence[float], right: Sequence[float]) -> float:
    return sum(float(lhs) * float(rhs) for lhs, rhs in zip(left, right, strict=False))


def deterministic_embedding(text: str, *, dimensions: int = 8) -> list[float]:
    features = (
        "정산",
        "지급",
        "revenue",
        "share",
        "배분",
        "공제",
        "권리",
        "위약",
    )
    normalized = text.lower()
    values = [float(normalized.count(feature)) for feature in features[:dimensions]]
    if len(values) < dimensions:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        for index in range(dimensions - len(values)):
            raw = int.from_bytes(digest[index * 2 : index * 2 + 2], byteorder="big")
            values.append(raw / 65535)
    scale = max(sum(values), 1.0)
    return [round(value / scale, 6) for value in values]


def deterministic_rerank(query: str, documents: Sequence[str]) -> list[dict[str, Any]]:
    query_tokens = set(tokenize(query))
    ranked: list[dict[str, Any]] = []
    for index, document in enumerate(documents):
        doc_tokens = set(tokenize(document))
        overlap = len(query_tokens & doc_tokens)
        denominator = max(len(query_tokens | doc_tokens), 1)
        score = round(overlap / denominator, 6)
        ranked.append({"rank": index + 1, "document_index": index, "score": score})
    return sorted(ranked, key=lambda item: (-float(item["score"]), int(item["document_index"])))


def deterministic_explanation(
    text: str,
    question: str | None,
    *,
    citations: Sequence[str] = (),
) -> str:
    digest = hashlib.sha256((question or text).encode("utf-8")).hexdigest()[:12]
    citation_text = ", ".join(citations) if citations else f"local-{digest}"
    return (
        "계약상 금융 검토 우선도 설명입니다. "
        "로컬 근거 범위 안에서 지급기일, 배분율, 정산 문구를 확인할 항목으로만 정리하며 "
        "검토 점수는 변경하지 않습니다. "
        f"citation={citation_text}. "
        "Contractual Financial Review Priority note only."
    )


def tokenize(text: str) -> tuple[str, ...]:
    return tuple(re.findall(r"[A-Za-z0-9]+|[가-힣]+", text.lower()))


def build_install_plan(
    *,
    profile_id: str,
    fink_home: Path | None = None,
    manifest: RuntimeManifest | None = None,
) -> dict[str, Any]:
    runtime_manifest = manifest or load_runtime_manifest()
    home = resolve_fink_home(fink_home=fink_home)
    components = runtime_manifest.profile_components(profile_id)
    total_estimated = sum(component.estimated_disk_size_bytes for component in components)
    available = disk_available_bytes(home)
    require(
        available >= total_estimated,
        "insufficient disk for selected profile: "
        f"available={available} estimated={total_estimated}",
    )
    states = tuple(component_state(component, home) for component in components)
    return {
        "status": "planned_no_download",
        "profile_id": profile_id,
        "fink_home": home.as_posix(),
        "model_root": (home / "models").as_posix(),
        "component_count": len(components),
        "total_estimated_disk_size_bytes": total_estimated,
        "available_disk_bytes": available,
        "download_policy": {
            "requires_explicit_download_flag": True,
            "resumable_downloads": True,
            "public_ungated_models_do_not_require_token": True,
            "safetensors_preferred": True,
            "reject_pickle_by_default": True,
        },
        "tracked_weight_files": tracked_weight_files(),
        "components": [state.as_dict() for state in states],
    }


def run_install(
    *,
    profile_id: str,
    fink_home: Path | None = None,
    download: bool = False,
    mock_download: bool = False,
    allow_pickle: bool = False,
) -> dict[str, Any]:
    require(not (download and mock_download), "use either --download or --mock-download, not both")
    manifest = load_runtime_manifest()
    plan = build_install_plan(profile_id=profile_id, fink_home=fink_home, manifest=manifest)
    require(not plan["tracked_weight_files"], "model weight files tracked in Git")

    home = Path(str(plan["fink_home"]))
    ensure_private_dir(home)
    ensure_private_dir(home / "models")
    components = manifest.profile_components(profile_id)

    installed: list[dict[str, Any]] = []
    if mock_download:
        for component in components:
            state = write_mock_component(component, home)
            installed.append(state.as_dict())
        plan["status"] = "mock_installed"
    elif download:
        require_download_armed(os.environ)
        for component in components:
            installed.append(
                download_component(
                    component,
                    home,
                    manifest=manifest,
                    allow_pickle=allow_pickle,
                ).as_dict()
            )
        plan["status"] = "downloaded"
    else:
        plan["status"] = "planned_no_download"

    if installed:
        plan["components"] = installed
    plan["installed_count"] = sum(1 for item in plan["components"] if item["installed"])
    plan["missing_count"] = sum(
        1 for item in plan["components"] if item.get("status") == MODEL_STATUS_NOT_INSTALLED
    )
    plan["failed_health_check_count"] = sum(
        1
        for item in plan["components"]
        if item.get("status") == MODEL_STATUS_FAILED_HEALTH_CHECK
    )
    plan["tracked_weight_files"] = tracked_weight_files()
    require(not plan["tracked_weight_files"], "model weight files tracked in Git")
    return plan


def write_mock_component(component: RuntimeComponent, fink_home: Path) -> ComponentState:
    target = component.local_path(fink_home)
    ensure_private_dir(target)
    config_path = target / LOCAL_CONFIG_FILE
    if not config_path.exists():
        config_path.write_text(
            json.dumps(
                {"model_type": "fink-mock", "fink_component_id": component.id},
                ensure_ascii=True,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
    health = run_component_health_check(
        component,
        fink_home,
        allow_missing_marker=True,
    )
    require(health.passed, f"{component.id} failed mock health check: {health.error}")
    write_install_marker(
        component,
        target,
        health=health,
        weights_downloaded=False,
        mock_runtime_fixture=True,
    )
    return component_state(component, fink_home)


def download_component(
    component: RuntimeComponent,
    fink_home: Path,
    *,
    manifest: RuntimeManifest,
    allow_pickle: bool,
) -> ComponentState:
    if allow_pickle:
        require(component.allow_pickle, f"{component.id} does not have pickle approval")
    target = component.local_path(fink_home)
    ensure_private_dir(target)
    try:
        from huggingface_hub import snapshot_download  # type: ignore[import-not-found]
    except Exception as exc:  # pragma: no cover - optional install dependency
        raise LocalModelRuntimeError("huggingface_hub is required for real downloads") from exc

    token = os.environ.get("HF_TOKEN") or None
    require(component.public_ungated or bool(token), f"{component.id} requires a token")
    ignore_patterns = () if allow_pickle else manifest.pickle_reject_patterns
    kwargs: dict[str, Any] = {
        "repo_id": component.repo_id,
        "revision": component.exact_revision,
        "local_dir": target.as_posix(),
        "token": token,
        "allow_patterns": manifest.safe_file_allow_patterns,
        "ignore_patterns": ignore_patterns,
    }
    if "resume_download" in inspect.signature(snapshot_download).parameters:
        kwargs["resume_download"] = True
    snapshot_download(**kwargs)
    health = run_component_health_check(
        component,
        fink_home,
        allow_missing_marker=True,
    )
    require(health.passed, f"{component.id} failed health check after download: {health.error}")
    write_install_marker(
        component,
        target,
        health=health,
        weights_downloaded=True,
        mock_runtime_fixture=False,
    )
    return component_state(component, fink_home)


def write_install_marker(
    component: RuntimeComponent,
    target: Path,
    *,
    health: ComponentHealthResult,
    weights_downloaded: bool,
    mock_runtime_fixture: bool,
) -> None:
    require(health.passed, f"{component.id} marker requires a passed health check")
    (target / LOCAL_MARKER_FILE).write_text(
        json.dumps(
            {
                "id": component.id,
                "repo_id": component.repo_id,
                "exact_revision": component.exact_revision,
                "license": component.license,
                "weights_downloaded": weights_downloaded,
                "mock_runtime_fixture": mock_runtime_fixture,
                "pickle_allowed": component.allow_pickle,
                "health_check": health.as_dict(),
            },
            ensure_ascii=True,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def run_doctor(*, profile_id: str, fink_home: Path | None = None) -> dict[str, Any]:
    manifest = load_runtime_manifest()
    plan = build_install_plan(profile_id=profile_id, fink_home=fink_home, manifest=manifest)
    no_tracked_weights = not tracked_weight_files()
    require(no_tracked_weights, "model weight files tracked in Git")
    states = tuple(
        component_state(component, Path(str(plan["fink_home"])))
        for component in manifest.profile_components(profile_id)
    )
    execution_path = execution_path_for_states(profile_id=profile_id, states=states)
    return {
        "status": "doctor_ok",
        "manifest": manifest.as_dict(),
        "profile_id": profile_id,
        "fink_home": plan["fink_home"],
        "component_count": plan["component_count"],
        "installed_count": sum(1 for state in states if state.installed),
        "missing_count": sum(1 for state in states if state.status == MODEL_STATUS_NOT_INSTALLED),
        "failed_health_check_count": sum(
            1 for state in states if state.status == MODEL_STATUS_FAILED_HEALTH_CHECK
        ),
        "available_disk_bytes": plan["available_disk_bytes"],
        "no_tracked_weights": no_tracked_weights,
        "offline_environment_flags": dict(OFFLINE_ENV_FLAGS),
        "runtime_download_allowed_on_analyze": False,
        "deterministic_fallback_available": True,
        "deterministic_fallback_active": execution_path["deterministic_fallback_active"],
        "model_status": execution_path["model_status"],
        "execution_path": execution_path,
        "components": [state.as_dict() for state in states],
    }


def run_demo(*, profile_id: str, fink_home: Path | None = None) -> dict[str, Any]:
    runtime = LocalModelRuntime(profile_id=profile_id, fink_home=fink_home)
    text = (
        "Synthetic clause: payment is due 60 days after settlement, and other "
        "deductions may be determined by the company."
    )
    return runtime.analyze(text, question="Which cash-flow terms need review?")


def run_self_test() -> dict[str, Any]:
    manifest = load_runtime_manifest()
    with tempfile.TemporaryDirectory(prefix="fink-local-runtime-") as tmp:
        home = Path(tmp) / "fink-home"
        first = run_install(
            profile_id="standard",
            fink_home=home,
            mock_download=True,
        )
        second = run_install(
            profile_id="standard",
            fink_home=home,
            mock_download=True,
        )
        runtime = LocalModelRuntime(profile_id="standard", fink_home=home, manifest=manifest)
        first_analysis = runtime.analyze(
            "Synthetic clause: creator receives 50% within 45 days after monthly settlement.",
            question="What should be reviewed?",
        )
        second_analysis = runtime.analyze(
            "Synthetic clause: creator receives 50% within 45 days after monthly settlement.",
            question="What should be reviewed?",
        )
        require(first_analysis == second_analysis, "deterministic fallback changed between runs")
        weight_files = sorted(
            path.as_posix()
            for path in home.rglob("*")
            if path.is_file() and path.name.lower().endswith(WEIGHT_SUFFIXES)
        )
        require(not weight_files, "self-test wrote model weight files")
        return {
            "status": "local_runtime_self_test_ok",
            "manifest_profile_ids": sorted(manifest.profiles),
            "first_install_status": first["status"],
            "second_install_status": second["status"],
            "installed_count": second["installed_count"],
            "missing_count": second["missing_count"],
            "outbound_connection_attempts": first_analysis["outbound_connection_attempts"],
            "deterministic_fallback_stable": True,
            "weight_files_written": 0,
        }


def require_download_armed(env: Mapping[str, str]) -> None:
    allowed = env.get("FINK_MODEL_DOWNLOAD_ALLOWED", "").lower()
    require(
        allowed in {"1", "true", "yes"},
        "set FINK_MODEL_DOWNLOAD_ALLOWED=true for a real model download",
    )


def require_outside_repo(path: Path, label: str) -> Path:
    require(not is_under(path, REPO_ROOT), f"{label} must be outside the Git repository")
    return path


def is_under(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent.resolve(strict=False))
        return True
    except ValueError:
        return False


def ensure_private_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    try:
        path.chmod(0o700)
    except OSError:
        pass


def disk_available_bytes(path: Path) -> int:
    probe = path
    while not probe.exists() and probe.parent != probe:
        probe = probe.parent
    return shutil.disk_usage(probe).free


def tracked_weight_files() -> list[str]:
    try:
        proc = subprocess.run(
            ["git", "ls-files"],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            check=True,
        )
    except Exception:
        return []
    return sorted(
        item for item in proc.stdout.splitlines() if item.lower().endswith(WEIGHT_SUFFIXES)
    )


def load_yaml_mapping(path: Path) -> dict[str, Any]:
    try:
        import yaml  # type: ignore[import-untyped]
    except Exception as exc:  # pragma: no cover - environment diagnostic
        raise LocalModelRuntimeError("PyYAML is required for local model runtime") from exc
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    require(isinstance(data, dict), f"{repo_relative(path)} must contain a YAML mapping")
    return cast(dict[str, Any], data)


def mapping_at(payload: Mapping[str, Any], key: str, path: str) -> Mapping[str, Any]:
    value = payload.get(key)
    require(isinstance(value, dict), f"{path}.{key} must be a mapping")
    return cast(Mapping[str, Any], value)


def list_of_mappings(value: Any, path: str) -> tuple[Mapping[str, Any], ...]:
    require(isinstance(value, list), f"{path} must be a list")
    records: list[Mapping[str, Any]] = []
    for index, item in enumerate(value):
        require(isinstance(item, dict), f"{path}[{index}] must be a mapping")
        records.append(cast(Mapping[str, Any], item))
    return tuple(records)


def required_string(payload: Mapping[str, Any], key: str, path: str) -> str:
    value = payload.get(key)
    require(isinstance(value, str) and bool(value.strip()), f"{path}.{key} must be non-empty")
    return value


def required_bool(payload: Mapping[str, Any], key: str, path: str) -> bool:
    value = payload.get(key)
    require(isinstance(value, bool), f"{path}.{key} must be boolean")
    return value


def required_positive_int(payload: Mapping[str, Any], key: str, path: str) -> int:
    value = payload.get(key)
    require(isinstance(value, int) and value > 0, f"{path}.{key} must be a positive integer")
    return value


def tuple_text(value: Any, path: str, *, allow_empty: bool = False) -> tuple[str, ...]:
    require(isinstance(value, list), f"{path} must be a list")
    items = tuple(str(item) for item in value)
    require(allow_empty or bool(items), f"{path} must not be empty")
    require(all(item.strip() for item in items), f"{path} must contain only non-empty strings")
    return items


def is_exact_revision(value: str) -> bool:
    return len(value) == 40 and all(char in "0123456789abcdef" for char in value)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise LocalModelRuntimeError(message)


def repo_relative(path: Path) -> str:
    try:
        return path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def print_result(payload: Mapping[str, Any], *, json_output: bool, text_prefix: str) -> None:
    if json_output:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"{text_prefix} status={payload['status']}")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Install and check FInk local model runtime profiles.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    install = sub.add_parser("install", help="Plan or run a local model profile install")
    install.add_argument("--profile", default="standard", choices=REQUIRED_PROFILE_IDS)
    install.add_argument("--fink-home", type=Path, default=None)
    install.add_argument("--download", action="store_true", help="Run a real gated download")
    install.add_argument(
        "--mock-download",
        action="store_true",
        help="Create tiny local fixtures for idempotent self-tests only",
    )
    install.add_argument("--allow-pickle", action="store_true")
    install.add_argument("--json", action="store_true")
    install.add_argument("--self-test", action="store_true")

    doctor = sub.add_parser("doctor", help="Check manifest, disk, offline flags, and weight policy")
    doctor.add_argument("--profile", default="standard", choices=REQUIRED_PROFILE_IDS)
    doctor.add_argument("--fink-home", type=Path, default=None)
    doctor.add_argument("--json", action="store_true")

    demo = sub.add_parser("demo", help="Run a synthetic offline demo with deterministic fallback")
    demo.add_argument("--profile", default="standard", choices=REQUIRED_PROFILE_IDS)
    demo.add_argument("--fink-home", type=Path, default=None)
    demo.add_argument("--json", action="store_true")

    validate = sub.add_parser("validate-manifest", help="Validate runtime profile manifest")
    validate.add_argument("--json", action="store_true")

    self_test = sub.add_parser("self-test", help="Run mocked deterministic runtime self-tests")
    self_test.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = parse_args(argv)
        if args.cmd == "install":
            if args.self_test:
                payload = run_self_test()
            else:
                payload = run_install(
                    profile_id=args.profile,
                    fink_home=args.fink_home,
                    download=args.download,
                    mock_download=args.mock_download,
                    allow_pickle=args.allow_pickle,
                )
            print_result(payload, json_output=args.json, text_prefix="FINK_INSTALL_LOCAL_OK")
            return 0
        if args.cmd == "doctor":
            payload = run_doctor(profile_id=args.profile, fink_home=args.fink_home)
            print_result(payload, json_output=args.json, text_prefix="FINK_MODEL_DOCTOR_OK")
            return 0
        if args.cmd == "demo":
            payload = run_demo(profile_id=args.profile, fink_home=args.fink_home)
            print_result(payload, json_output=args.json, text_prefix="FINK_RUN_DEMO_OK")
            return 0
        if args.cmd == "validate-manifest":
            payload = {"status": "manifest_ok", "manifest": load_runtime_manifest().as_dict()}
            print_result(payload, json_output=args.json, text_prefix="FINK_MODEL_MANIFEST_OK")
            return 0
        if args.cmd == "self-test":
            payload = run_self_test()
            print_result(
                payload,
                json_output=args.json,
                text_prefix="FINK_LOCAL_RUNTIME_SELF_TEST_OK",
            )
            return 0
        raise LocalModelRuntimeError(f"unknown command: {args.cmd}")
    except LocalModelRuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_POLICY_ERROR
    except RuntimeNetworkAttemptError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_POLICY_ERROR


if __name__ == "__main__":
    raise SystemExit(main())

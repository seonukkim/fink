from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import yaml  # type: ignore[import-untyped]
except Exception as exc:  # pragma: no cover - dependency is declared in pyproject
    raise RuntimeError("PyYAML is required for FInk financial feature bindings") from exc


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG_PATH = REPO_ROOT / "config" / "financial_features.yaml"
DEFAULT_SOURCE_PATH = REPO_ROOT / "data" / "corpus" / "stage-1" / (
    "12_MASTER_FINANCIAL_FEATURES.yaml"
)

EXPECTED_FIM_IDS = frozenset({f"FIM-{idx}" for idx in range(1, 9)})
EXPECTED_CANONICAL_FEATURES = 29
EXPECTED_AUXILIARY_FEATURES = 3
VALID_DTYPES = frozenset({"money", "rate", "days", "months", "count", "bool", "text"})
VALID_UNITS = frozenset({"KRW", "frac", "days", "months", "count", "-"})


class FeatureBindingError(RuntimeError):
    """Raised when the financial feature binding config is incomplete."""


@dataclass(frozen=True)
class FeatureBinding:
    feature_id: str
    is_canonical: bool
    source_section: str
    upstream_type: str
    dtype: str
    unit: str
    label_ko: str
    label_en: str
    score_input: bool
    module_refs: tuple[str, ...]
    category: str

    def as_dict(self) -> dict[str, object]:
        return {
            "feature_id": self.feature_id,
            "is_canonical": self.is_canonical,
            "source_section": self.source_section,
            "upstream_type": self.upstream_type,
            "dtype": self.dtype,
            "unit": self.unit,
            "label_ko": self.label_ko,
            "label_en": self.label_en,
            "score_input": self.score_input,
            "module_refs": list(self.module_refs),
            "category": self.category,
        }


@dataclass(frozen=True)
class FimInputBinding:
    fim_id: str
    input_id: str
    feature_id: str
    binding_role: str
    value_source: str
    component_feature_ids: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, object]:
        return {
            "fim_id": self.fim_id,
            "input_id": self.input_id,
            "feature_id": self.feature_id,
            "binding_role": self.binding_role,
            "value_source": self.value_source,
            "component_feature_ids": list(self.component_feature_ids),
        }


@dataclass(frozen=True)
class FeatureBindingReport:
    config_path: Path
    source_path: Path
    features: tuple[FeatureBinding, ...]
    fim_inputs: tuple[FimInputBinding, ...]

    @property
    def counts(self) -> dict[str, int]:
        canonical = sum(1 for item in self.features if item.is_canonical)
        auxiliary = sum(1 for item in self.features if not item.is_canonical)
        return {
            "canonical_features": canonical,
            "auxiliary_fields": auxiliary,
            "total_features": len(self.features),
            "fim_modules": len({item.fim_id for item in self.fim_inputs}),
            "fim_inputs": len(self.fim_inputs),
        }

    @property
    def module_input_counts(self) -> dict[str, int]:
        return {
            fim_id: sum(1 for item in self.fim_inputs if item.fim_id == fim_id)
            for fim_id in sorted(EXPECTED_FIM_IDS)
        }

    def as_dict(self) -> dict[str, object]:
        return {
            "config_path": self.config_path.as_posix(),
            "source_path": self.source_path.as_posix(),
            "counts": self.counts,
            "module_input_counts": self.module_input_counts,
            "features": [item.as_dict() for item in self.features],
            "fim_inputs": [item.as_dict() for item in self.fim_inputs],
        }


def feature_binding_complete(
    config_path: Path = DEFAULT_CONFIG_PATH,
    source_path: Path = DEFAULT_SOURCE_PATH,
) -> FeatureBindingReport:
    """Load and validate the AQ-03 feature-to-FIM binding."""
    return load_feature_bindings(config_path=config_path, source_path=source_path)


def load_feature_bindings(
    config_path: Path = DEFAULT_CONFIG_PATH,
    source_path: Path = DEFAULT_SOURCE_PATH,
) -> FeatureBindingReport:
    config = _read_yaml_mapping(config_path, "financial feature binding config")
    source = _read_yaml_mapping(source_path, "upstream financial feature source")
    upstream_canonical_map, upstream_auxiliary_map = _upstream_feature_maps(source)
    upstream_canonical = set(upstream_canonical_map)
    upstream_auxiliary = set(upstream_auxiliary_map)

    features = _parse_features(config)
    fim_inputs = _parse_fim_inputs(config)
    feature_ids = {item.feature_id for item in features}
    canonical_ids = {item.feature_id for item in features if item.is_canonical}
    auxiliary_ids = {item.feature_id for item in features if not item.is_canonical}

    _require(
        canonical_ids == upstream_canonical,
        "canonical feature IDs do not match upstream record 12: "
        + _diff_text(canonical_ids, upstream_canonical),
    )
    _require(
        auxiliary_ids == upstream_auxiliary,
        "auxiliary feature IDs do not match upstream record 12: "
        + _diff_text(auxiliary_ids, upstream_auxiliary),
    )
    _require(len(canonical_ids) == EXPECTED_CANONICAL_FEATURES, "canonical count mismatch")
    _require(len(auxiliary_ids) == EXPECTED_AUXILIARY_FEATURES, "auxiliary count mismatch")

    declared_counts = _require_mapping(config.get("counts"), "counts")
    _require_int_count(declared_counts, "canonical_features", len(canonical_ids))
    _require_int_count(declared_counts, "auxiliary_fields", len(auxiliary_ids))
    _require_int_count(declared_counts, "total_features", len(feature_ids))

    for feature in features:
        _require(feature.dtype in VALID_DTYPES, f"{feature.feature_id}: invalid dtype")
        _require(feature.unit in VALID_UNITS, f"{feature.feature_id}: invalid unit")
        _require(feature.module_refs, f"{feature.feature_id}: module_refs must not be empty")
        invalid_refs = sorted(set(feature.module_refs) - EXPECTED_FIM_IDS)
        _require(not invalid_refs, f"{feature.feature_id}: invalid module_refs {invalid_refs}")
        upstream_row = (
            upstream_canonical_map.get(feature.feature_id)
            if feature.is_canonical
            else upstream_auxiliary_map.get(feature.feature_id)
        )
        _require(upstream_row is not None, f"{feature.feature_id}: missing from upstream record 12")
        _require(
            feature.upstream_type == upstream_row.get("type"),
            f"{feature.feature_id}: upstream_type does not match record 12",
        )
        _require(
            feature.label_ko == upstream_row.get("preferred_ko"),
            f"{feature.feature_id}: label_ko does not match record 12",
        )
        _require(
            feature.label_en == upstream_row.get("preferred_en"),
            f"{feature.feature_id}: label_en does not match record 12",
        )
        if feature.is_canonical:
            _require(
                feature.source_section == "canonical_features",
                f"{feature.feature_id}: canonical feature has wrong source_section",
            )
            _require(
                feature.category == upstream_row.get("risk_category"),
                f"{feature.feature_id}: risk_category does not match record 12",
            )
        else:
            _require(
                feature.source_section == "auxiliary_fields",
                f"{feature.feature_id}: auxiliary field has wrong source_section",
            )
            _require(
                feature.category == upstream_row.get("related_category"),
                f"{feature.feature_id}: related_category does not match record 12",
            )
            _require(
                feature.score_input is False,
                f"{feature.feature_id}: auxiliary fields must have score_input=false",
            )

    fim_ids = {item.fim_id for item in fim_inputs}
    _require(
        fim_ids == EXPECTED_FIM_IDS,
        "FIM coverage mismatch: " + _diff_text(fim_ids, EXPECTED_FIM_IDS),
    )
    for item in fim_inputs:
        _require(
            item.feature_id in feature_ids,
            f"{item.fim_id}.{item.input_id}: feature_id {item.feature_id!r} not in record 12",
        )
        missing_components = sorted(set(item.component_feature_ids) - feature_ids)
        _require(
            not missing_components,
            f"{item.fim_id}.{item.input_id}: component_feature_ids not in record 12: "
            + ", ".join(missing_components),
        )

    return FeatureBindingReport(
        config_path=config_path,
        source_path=source_path,
        features=features,
        fim_inputs=fim_inputs,
    )


def _parse_features(config: dict[str, Any]) -> tuple[FeatureBinding, ...]:
    rows = _require_list(config.get("features"), "features")
    records: list[FeatureBinding] = []
    seen: set[str] = set()
    for idx, row in enumerate(rows, start=1):
        item = _require_mapping(row, f"features[{idx}]")
        feature_id = _required_text(item, "feature_id", f"features[{idx}]")
        _require(feature_id not in seen, f"duplicate feature_id: {feature_id}")
        seen.add(feature_id)
        module_refs = tuple(_required_text(ref, "", "module_refs") for ref in item["module_refs"])
        category = str(item.get("risk_category") or item.get("related_category") or "")
        _require(bool(category), f"{feature_id}: missing risk_category/related_category")
        records.append(
            FeatureBinding(
                feature_id=feature_id,
                is_canonical=_required_bool(item, "is_canonical", feature_id),
                source_section=_required_text(item, "source_section", feature_id),
                upstream_type=_required_text(item, "upstream_type", feature_id),
                dtype=_required_text(item, "dtype", feature_id),
                unit=_required_text(item, "unit", feature_id),
                label_ko=_required_text(item, "label_ko", feature_id),
                label_en=_required_text(item, "label_en", feature_id),
                score_input=_required_bool(item, "score_input", feature_id),
                module_refs=module_refs,
                category=category,
            )
        )
    return tuple(records)


def _parse_fim_inputs(config: dict[str, Any]) -> tuple[FimInputBinding, ...]:
    modules = _require_mapping(config.get("fim_input_bindings"), "fim_input_bindings")
    records: list[FimInputBinding] = []
    seen: set[tuple[str, str]] = set()
    for fim_id, module in sorted(modules.items()):
        fim_id = str(fim_id)
        module_map = _require_mapping(module, fim_id)
        inputs = _require_list(module_map.get("inputs"), f"{fim_id}.inputs")
        _require(inputs, f"{fim_id}.inputs must not be empty")
        for idx, row in enumerate(inputs, start=1):
            item = _require_mapping(row, f"{fim_id}.inputs[{idx}]")
            input_id = _required_text(item, "input_id", f"{fim_id}.inputs[{idx}]")
            key = (fim_id, input_id)
            _require(key not in seen, f"duplicate FIM input binding: {fim_id}.{input_id}")
            seen.add(key)
            components = tuple(str(value) for value in item.get("component_feature_ids", ()))
            records.append(
                FimInputBinding(
                    fim_id=fim_id,
                    input_id=input_id,
                    feature_id=_required_text(item, "feature_id", f"{fim_id}.{input_id}"),
                    binding_role=_required_text(item, "binding_role", f"{fim_id}.{input_id}"),
                    value_source=_required_text(item, "value_source", f"{fim_id}.{input_id}"),
                    component_feature_ids=components,
                )
            )
    return tuple(records)


def _upstream_feature_maps(
    source: dict[str, Any],
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    canonical_rows = _require_list(source.get("canonical_features"), "canonical_features")
    auxiliary_rows = _require_list(source.get("auxiliary_fields"), "auxiliary_fields")
    canonical = {
        _required_text(row, "id", "canonical_features"): _require_mapping(
            row, "canonical_features"
        )
        for row in canonical_rows
    }
    auxiliary = {
        _required_text(row, "id", "auxiliary_fields"): _require_mapping(row, "auxiliary_fields")
        for row in auxiliary_rows
    }
    _require(len(canonical) == len(canonical_rows), "duplicate upstream canonical feature id")
    _require(len(auxiliary) == len(auxiliary_rows), "duplicate upstream auxiliary feature id")
    return canonical, auxiliary


def _read_yaml_mapping(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise FeatureBindingError(f"{label} missing: {path}")
    parsed = yaml.safe_load(path.read_text(encoding="utf-8-sig"))
    return _require_mapping(parsed, label)


def _require_mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise FeatureBindingError(f"{label} must be a mapping")
    return value


def _require_list(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise FeatureBindingError(f"{label} must be a list")
    return value


def _required_text(row: Any, key: str, label: str) -> str:
    if key == "":
        value = row
    else:
        mapping = _require_mapping(row, label)
        value = mapping.get(key)
    if not isinstance(value, str) or not value.strip():
        field = "value" if key == "" else key
        raise FeatureBindingError(f"{label}: {field} must be non-empty text")
    return value


def _required_bool(row: dict[str, Any], key: str, label: str) -> bool:
    value = row.get(key)
    if not isinstance(value, bool):
        raise FeatureBindingError(f"{label}: {key} must be boolean")
    return value


def _require_int_count(row: dict[str, Any], key: str, expected: int) -> None:
    value = row.get(key)
    _require(value == expected, f"counts.{key} must be {expected}, got {value!r}")


def _diff_text(actual: set[str], expected: set[str] | frozenset[str]) -> str:
    missing = sorted(set(expected) - actual)
    extra = sorted(actual - set(expected))
    return f"missing={missing}; extra={extra}"


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise FeatureBindingError(message)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate FInk financial feature and FIM input bindings."
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE_PATH)
    parser.add_argument("--json", action="store_true", help="Emit the validation report as JSON.")
    args = parser.parse_args()

    try:
        report = feature_binding_complete(config_path=args.config, source_path=args.source)
    except FeatureBindingError as exc:
        print(f"FEATURE_BINDING_BLOCKED: {exc}")
        raise SystemExit(1) from exc

    if args.json:
        print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2))
    else:
        counts = ", ".join(f"{key}={value}" for key, value in report.counts.items())
        print(f"FEATURE_BINDING_OK {counts}")


if __name__ == "__main__":
    main()

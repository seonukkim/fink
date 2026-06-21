from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, fields, is_dataclass
from pathlib import Path
from time import perf_counter
from typing import Any

try:
    import yaml  # type: ignore[import-untyped]
except Exception as exc:  # pragma: no cover - dependency is declared in pyproject
    raise RuntimeError("PyYAML is required for FInk time exposure config") from exc

from fink.scoring import DEFAULT_SCORING_CONFIG_PATH
from fink.schemas import PathwayLabel, TimeExposure


NOT_LEGAL_ADVICE_DISCLAIMER = (
    "FInk reports Contractual Financial Review Priority only and is not legal advice."
)

_FORBIDDEN_PATHWAY_DURATION_ROOTS = (
    "court",
    "negotiation",
    "dispute",
    "dispute_resolution",
)
_NUMERIC_TIME_FIELD_MARKERS = (
    "days",
    "months",
    "seconds",
    "minutes",
    "duration",
)


class TimeExposureError(ValueError):
    """Raised when time exposure inputs or config violate spec-03 contracts."""


@dataclass(frozen=True)
class HumanReviewTimeCoefficients:
    base_min: float
    per_page_min: float
    per_correction_min: float
    per_flag_min: float
    per_missing_min: float


@dataclass(frozen=True)
class PathwayThresholds:
    high_review_priority_min: int
    mid_review_priority_min: int
    large_payment_delay_days_min: int
    labels: tuple[PathwayLabel, ...]


@dataclass(frozen=True)
class TimeExposureConfig:
    config_path: Path
    scoring_config_version: str
    human_review_time_coefficients: HumanReviewTimeCoefficients
    pathway_thresholds: PathwayThresholds


@dataclass(frozen=True)
class TimeExposureInputs:
    page_count: int
    ocr_corrections_made: int
    num_flagged_clauses: int
    num_missing_financial_inputs: int
    measured_analysis_runtime_seconds: float
    review_priority_score: int
    payment_due_days: int | None = None
    payment_delay_days: int | None = None
    contract_duration_months: int | None = None
    renewal_duration_months: int | None = None
    exclusivity_duration_months: int | None = None
    termination_notice_days: int | None = None
    estimated_months_to_recoup: float | None = None
    material_monetary_exposure_range_present: bool = False
    observed_unpaid_amount_present: bool = False
    uncapped_or_ambiguous_liability_signal_present: bool = False
    broad_ip_or_secondary_rights_transfer_signal_present: bool = False

    def __post_init__(self) -> None:
        for name in (
            "page_count",
            "ocr_corrections_made",
            "num_flagged_clauses",
            "num_missing_financial_inputs",
        ):
            _require_nonnegative_int(getattr(self, name), name)
        _require_score(self.review_priority_score, "review_priority_score")
        _require_nonnegative_number(
            self.measured_analysis_runtime_seconds,
            "measured_analysis_runtime_seconds",
        )
        for name in (
            "payment_due_days",
            "payment_delay_days",
            "contract_duration_months",
            "renewal_duration_months",
            "exclusivity_duration_months",
            "termination_notice_days",
        ):
            value = getattr(self, name)
            if value is not None:
                _require_nonnegative_int(value, name)
        if self.estimated_months_to_recoup is not None:
            _require_nonnegative_number(
                self.estimated_months_to_recoup,
                "estimated_months_to_recoup",
            )
        for name in (
            "material_monetary_exposure_range_present",
            "observed_unpaid_amount_present",
            "uncapped_or_ambiguous_liability_signal_present",
            "broad_ip_or_secondary_rights_transfer_signal_present",
        ):
            _require_bool(getattr(self, name), name)


@dataclass(frozen=True)
class TimeExposureResult:
    time_exposure: TimeExposure
    scoring_config_version: str
    disclaimers: tuple[str, ...]


@dataclass(frozen=True)
class NoDurationNumberTestReport:
    inspected_fields: tuple[str, ...]
    forbidden_numeric_duration_fields: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.forbidden_numeric_duration_fields

    def as_dict(self) -> dict[str, Any]:
        return {
            "inspected_fields": list(self.inspected_fields),
            "forbidden_numeric_duration_fields": list(
                self.forbidden_numeric_duration_fields
            ),
            "ok": self.ok,
        }


@dataclass(frozen=True)
class TimeExposureTestReport:
    scoring_config_version: str
    ac_time_1_typed_fields_categorical_pathway: bool
    ac_time_1_no_duration_number_fields: bool
    ac_time_2_human_review_minutes_from_config: bool
    ac_time_2_runtime_measured: bool
    ac_time_2_not_legal_advice_disclaimer: bool

    @property
    def ok(self) -> bool:
        return (
            self.ac_time_1_typed_fields_categorical_pathway
            and self.ac_time_1_no_duration_number_fields
            and self.ac_time_2_human_review_minutes_from_config
            and self.ac_time_2_runtime_measured
            and self.ac_time_2_not_legal_advice_disclaimer
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "scoring_config_version": self.scoring_config_version,
            "ac_time_1_typed_fields_categorical_pathway": (
                self.ac_time_1_typed_fields_categorical_pathway
            ),
            "ac_time_1_no_duration_number_fields": (
                self.ac_time_1_no_duration_number_fields
            ),
            "ac_time_2_human_review_minutes_from_config": (
                self.ac_time_2_human_review_minutes_from_config
            ),
            "ac_time_2_runtime_measured": self.ac_time_2_runtime_measured,
            "ac_time_2_not_legal_advice_disclaimer": (
                self.ac_time_2_not_legal_advice_disclaimer
            ),
            "ok": self.ok,
        }


class AnalysisRuntimeTimer:
    """Small context manager around perf_counter for analysis runtime measurement."""

    def __init__(self, clock: Callable[[], float] | None = None) -> None:
        self._clock = clock or perf_counter
        self._started_at: float | None = None
        self._ended_at: float | None = None

    def __enter__(self) -> AnalysisRuntimeTimer:
        self._started_at = self._clock()
        self._ended_at = None
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self._ended_at = self._clock()

    @property
    def elapsed_seconds(self) -> float:
        if self._started_at is None:
            raise TimeExposureError("runtime timer has not started")
        ended_at = self._ended_at if self._ended_at is not None else self._clock()
        return measure_runtime_seconds(self._started_at, ended_at)


def load_time_exposure_config(
    config_path: Path | str = DEFAULT_SCORING_CONFIG_PATH,
) -> TimeExposureConfig:
    payload = _read_yaml_mapping(Path(config_path))
    version = _require_text(payload.get("scoring_config_version"), "scoring_config_version")
    return TimeExposureConfig(
        config_path=Path(config_path),
        scoring_config_version=version,
        human_review_time_coefficients=_human_review_time_coefficients(payload),
        pathway_thresholds=_pathway_thresholds(payload),
    )


def measure_runtime_seconds(started_at: float, ended_at: float) -> float:
    _require_number(started_at, "started_at")
    _require_number(ended_at, "ended_at")
    if ended_at < started_at:
        raise TimeExposureError("ended_at must be >= started_at")
    return float(ended_at - started_at)


def estimate_human_review_minutes(
    *,
    page_count: int,
    ocr_corrections_made: int,
    num_flagged_clauses: int,
    num_missing_financial_inputs: int,
    config: TimeExposureConfig | None = None,
) -> float:
    for name, value in (
        ("page_count", page_count),
        ("ocr_corrections_made", ocr_corrections_made),
        ("num_flagged_clauses", num_flagged_clauses),
        ("num_missing_financial_inputs", num_missing_financial_inputs),
    ):
        _require_nonnegative_int(value, name)
    coefficients = (config or load_time_exposure_config()).human_review_time_coefficients
    return float(
        coefficients.base_min
        + coefficients.per_page_min * page_count
        + coefficients.per_correction_min * ocr_corrections_made
        + coefficients.per_flag_min * num_flagged_clauses
        + coefficients.per_missing_min * num_missing_financial_inputs
    )


def select_pathway_label(
    inputs: TimeExposureInputs,
    *,
    config: TimeExposureConfig | None = None,
) -> PathwayLabel:
    thresholds = (config or load_time_exposure_config()).pathway_thresholds
    if (
        inputs.uncapped_or_ambiguous_liability_signal_present
        or inputs.broad_ip_or_secondary_rights_transfer_signal_present
        or inputs.review_priority_score >= thresholds.high_review_priority_min
    ):
        return PathwayLabel.PROFESSIONAL_REVIEW_REQUIRED
    if (
        inputs.material_monetary_exposure_range_present
        or inputs.review_priority_score >= thresholds.mid_review_priority_min
    ):
        return PathwayLabel.NEGOTIATION_REQUIRED
    if (
        inputs.observed_unpaid_amount_present
        or (
            inputs.payment_delay_days is not None
            and inputs.payment_delay_days >= thresholds.large_payment_delay_days_min
        )
    ):
        return PathwayLabel.DISPUTE_PATHWAY_MAY_BE_REQUIRED
    return PathwayLabel.CLARIFICATION_LIKELY_SUFFICIENT


def build_time_exposure(
    inputs: TimeExposureInputs | None = None,
    *,
    page_count: int | None = None,
    ocr_corrections_made: int = 0,
    num_flagged_clauses: int = 0,
    num_missing_financial_inputs: int = 0,
    measured_analysis_runtime_seconds: float | None = None,
    review_priority_score: int | None = None,
    payment_due_days: int | None = None,
    payment_delay_days: int | None = None,
    contract_duration_months: int | None = None,
    renewal_duration_months: int | None = None,
    exclusivity_duration_months: int | None = None,
    termination_notice_days: int | None = None,
    estimated_months_to_recoup: float | None = None,
    material_monetary_exposure_range_present: bool = False,
    observed_unpaid_amount_present: bool = False,
    uncapped_or_ambiguous_liability_signal_present: bool = False,
    broad_ip_or_secondary_rights_transfer_signal_present: bool = False,
    config: TimeExposureConfig | None = None,
) -> TimeExposureResult:
    resolved_config = config or load_time_exposure_config()
    resolved_inputs = inputs or TimeExposureInputs(
        page_count=_require_optional_int(page_count, "page_count"),
        ocr_corrections_made=ocr_corrections_made,
        num_flagged_clauses=num_flagged_clauses,
        num_missing_financial_inputs=num_missing_financial_inputs,
        measured_analysis_runtime_seconds=_require_optional_number(
            measured_analysis_runtime_seconds,
            "measured_analysis_runtime_seconds",
        ),
        review_priority_score=_require_optional_int(
            review_priority_score,
            "review_priority_score",
        ),
        payment_due_days=payment_due_days,
        payment_delay_days=payment_delay_days,
        contract_duration_months=contract_duration_months,
        renewal_duration_months=renewal_duration_months,
        exclusivity_duration_months=exclusivity_duration_months,
        termination_notice_days=termination_notice_days,
        estimated_months_to_recoup=estimated_months_to_recoup,
        material_monetary_exposure_range_present=material_monetary_exposure_range_present,
        observed_unpaid_amount_present=observed_unpaid_amount_present,
        uncapped_or_ambiguous_liability_signal_present=(
            uncapped_or_ambiguous_liability_signal_present
        ),
        broad_ip_or_secondary_rights_transfer_signal_present=(
            broad_ip_or_secondary_rights_transfer_signal_present
        ),
    )
    review_minutes = estimate_human_review_minutes(
        page_count=resolved_inputs.page_count,
        ocr_corrections_made=resolved_inputs.ocr_corrections_made,
        num_flagged_clauses=resolved_inputs.num_flagged_clauses,
        num_missing_financial_inputs=resolved_inputs.num_missing_financial_inputs,
        config=resolved_config,
    )
    return TimeExposureResult(
        time_exposure=TimeExposure(
            measured_analysis_runtime_seconds=(
                resolved_inputs.measured_analysis_runtime_seconds
            ),
            estimated_human_review_minutes=review_minutes,
            pathway_label=select_pathway_label(resolved_inputs, config=resolved_config),
            payment_due_days=resolved_inputs.payment_due_days,
            payment_delay_days=resolved_inputs.payment_delay_days,
            contract_duration_months=resolved_inputs.contract_duration_months,
            renewal_duration_months=resolved_inputs.renewal_duration_months,
            exclusivity_duration_months=resolved_inputs.exclusivity_duration_months,
            termination_notice_days=resolved_inputs.termination_notice_days,
            estimated_months_to_recoup=resolved_inputs.estimated_months_to_recoup,
        ),
        scoring_config_version=resolved_config.scoring_config_version,
        disclaimers=time_disclaimers(),
    )


def time_disclaimers() -> tuple[str, ...]:
    return (NOT_LEGAL_ADVICE_DISCLAIMER,)


def no_duration_number_test(
    inspected_models: Sequence[type[Any]] = (TimeExposure, TimeExposureInputs),
) -> NoDurationNumberTestReport:
    inspected_fields = tuple(_iter_model_fields(inspected_models))
    forbidden = tuple(
        field_name
        for field_name in inspected_fields
        if _is_forbidden_numeric_duration_field(field_name)
    )
    report = NoDurationNumberTestReport(
        inspected_fields=inspected_fields,
        forbidden_numeric_duration_fields=forbidden,
    )
    if not report.ok:
        raise TimeExposureError(f"no_duration_number_test failed: {report.as_dict()}")
    return report


def time_exposure_tests() -> TimeExposureTestReport:
    config = load_time_exposure_config()
    runtime_seconds = measure_runtime_seconds(100.0, 101.25)
    inputs = TimeExposureInputs(
        page_count=4,
        ocr_corrections_made=2,
        num_flagged_clauses=3,
        num_missing_financial_inputs=1,
        measured_analysis_runtime_seconds=runtime_seconds,
        review_priority_score=40,
        payment_due_days=30,
        payment_delay_days=10,
        contract_duration_months=12,
        renewal_duration_months=12,
        exclusivity_duration_months=6,
        termination_notice_days=30,
        estimated_months_to_recoup=4.5,
    )
    result = build_time_exposure(inputs, config=config)
    expected_minutes = estimate_human_review_minutes(
        page_count=inputs.page_count,
        ocr_corrections_made=inputs.ocr_corrections_made,
        num_flagged_clauses=inputs.num_flagged_clauses,
        num_missing_financial_inputs=inputs.num_missing_financial_inputs,
        config=config,
    )
    no_duration_report = no_duration_number_test()
    exposure = result.time_exposure
    report = TimeExposureTestReport(
        scoring_config_version=config.scoring_config_version,
        ac_time_1_typed_fields_categorical_pathway=(
            exposure.payment_due_days == 30
            and exposure.payment_delay_days == 10
            and exposure.contract_duration_months == 12
            and exposure.renewal_duration_months == 12
            and exposure.exclusivity_duration_months == 6
            and exposure.termination_notice_days == 30
            and exposure.estimated_months_to_recoup == 4.5
            and isinstance(exposure.pathway_label, PathwayLabel)
            and exposure.pathway_label is PathwayLabel.NEGOTIATION_REQUIRED
        ),
        ac_time_1_no_duration_number_fields=no_duration_report.ok,
        ac_time_2_human_review_minutes_from_config=(
            exposure.estimated_human_review_minutes == expected_minutes
        ),
        ac_time_2_runtime_measured=(
            exposure.measured_analysis_runtime_seconds == runtime_seconds
            and runtime_seconds == 1.25
        ),
        ac_time_2_not_legal_advice_disclaimer=any(
            "not legal advice" in disclaimer.lower() for disclaimer in result.disclaimers
        ),
    )
    if not report.ok:
        raise TimeExposureError(f"time_exposure_tests failed: {report.as_dict()}")
    return report


def _human_review_time_coefficients(payload: Mapping[str, Any]) -> HumanReviewTimeCoefficients:
    item = _require_mapping(
        payload.get("human_review_time_coefficients"),
        "human_review_time_coefficients",
    )
    return HumanReviewTimeCoefficients(
        base_min=_heuristic_number(item.get("base_min"), "human_review_time.base_min"),
        per_page_min=_heuristic_number(
            item.get("per_page_min"),
            "human_review_time.per_page_min",
        ),
        per_correction_min=_heuristic_number(
            item.get("per_correction_min"),
            "human_review_time.per_correction_min",
        ),
        per_flag_min=_heuristic_number(
            item.get("per_flag_min"),
            "human_review_time.per_flag_min",
        ),
        per_missing_min=_heuristic_number(
            item.get("per_missing_min"),
            "human_review_time.per_missing_min",
        ),
    )


def _pathway_thresholds(payload: Mapping[str, Any]) -> PathwayThresholds:
    item = _require_mapping(payload.get("pathway_thresholds"), "pathway_thresholds")
    _require(item.get("first_match_wins") is True, "pathway_thresholds.first_match_wins")
    labels_payload = item.get("labels")
    if not isinstance(labels_payload, Sequence) or isinstance(labels_payload, (str, bytes)):
        raise TimeExposureError("pathway_thresholds.labels must be a sequence")
    labels = tuple(PathwayLabel(str(label)) for label in labels_payload)
    expected = tuple(PathwayLabel)
    _require(set(labels) == set(expected), "pathway_thresholds.labels must match PathwayLabel")
    high = int(
        _heuristic_number(
            item.get("high_review_priority_min"),
            "pathway_thresholds.high_review_priority_min",
            maximum=100.0,
        )
    )
    mid = int(
        _heuristic_number(
            item.get("mid_review_priority_min"),
            "pathway_thresholds.mid_review_priority_min",
            maximum=100.0,
        )
    )
    delay = int(
        _heuristic_number(
            item.get("large_payment_delay_days_min"),
            "pathway_thresholds.large_payment_delay_days_min",
        )
    )
    _require(mid <= high, "pathway mid threshold must be <= high threshold")
    return PathwayThresholds(
        high_review_priority_min=high,
        mid_review_priority_min=mid,
        large_payment_delay_days_min=delay,
        labels=labels,
    )


def _read_yaml_mapping(path: Path) -> Mapping[str, Any]:
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise TimeExposureError(f"time exposure config not found: {path}") from exc
    return _require_mapping(payload, path.as_posix())


def _heuristic_number(
    payload: Any,
    field_name: str,
    *,
    maximum: float | None = None,
) -> float:
    item = _require_mapping(payload, field_name)
    _require(item.get("heuristic") is True, f"{field_name}.heuristic must be true")
    value = _plain_number(item.get("value"), f"{field_name}.value")
    if maximum is not None and value > maximum:
        raise TimeExposureError(f"{field_name}.value must be <= {maximum}")
    return value


def _plain_number(value: object, field_name: str) -> float:
    _require_number(value, field_name)
    number = float(value)
    if number < 0.0:
        raise TimeExposureError(f"{field_name} must be >= 0")
    return number


def _require_mapping(value: object, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TimeExposureError(f"{field_name} must be a mapping")
    return value


def _require_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TimeExposureError(f"{field_name} must be non-empty text")
    return value.strip()


def _require_optional_int(value: int | None, field_name: str) -> int:
    if value is None:
        raise TimeExposureError(f"{field_name} is required")
    _require_nonnegative_int(value, field_name)
    return value


def _require_optional_number(value: float | None, field_name: str) -> float:
    if value is None:
        raise TimeExposureError(f"{field_name} is required")
    _require_nonnegative_number(value, field_name)
    return float(value)


def _require_number(value: object, field_name: str) -> None:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise TimeExposureError(f"{field_name} must be numeric")


def _require_nonnegative_number(value: object, field_name: str) -> None:
    _require_number(value, field_name)
    if float(value) < 0.0:
        raise TimeExposureError(f"{field_name} must be >= 0")


def _require_nonnegative_int(value: object, field_name: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TimeExposureError(f"{field_name} must be int")
    if value < 0:
        raise TimeExposureError(f"{field_name} must be >= 0")


def _require_score(value: object, field_name: str) -> None:
    _require_nonnegative_int(value, field_name)
    if int(value) > 100:
        raise TimeExposureError(f"{field_name} must be <= 100")


def _require_bool(value: object, field_name: str) -> None:
    if type(value) is not bool:
        raise TimeExposureError(f"{field_name} must be bool")


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise TimeExposureError(message)


def _iter_model_fields(models: Iterable[type[Any]]) -> Iterable[str]:
    for model in models:
        if not is_dataclass(model):
            raise TimeExposureError(f"{model!r} must be a dataclass type")
        for item in fields(model):
            yield f"{model.__name__}.{item.name}"


def _is_forbidden_numeric_duration_field(qualified_field_name: str) -> bool:
    field_name = qualified_field_name.rsplit(".", 1)[-1].lower()
    has_forbidden_root = any(root in field_name for root in _FORBIDDEN_PATHWAY_DURATION_ROOTS)
    has_numeric_time_marker = any(marker in field_name for marker in _NUMERIC_TIME_FIELD_MARKERS)
    return has_forbidden_root and has_numeric_time_marker

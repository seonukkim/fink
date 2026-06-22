from __future__ import annotations

import re
from dataclasses import MISSING, dataclass, field, fields, is_dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Any
from uuid import UUID


class SchemaValidationError(ValueError):
    """Raised when a spec-02 schema instance violates its field contract."""


class PrivacyClass(Enum):
    P0_PUBLIC = "P0_PUBLIC"
    P1_INTERNAL = "P1_INTERNAL"
    P2_PRIVATE_LOCAL = "P2_PRIVATE_LOCAL"
    P3_USER_EPHEMERAL = "P3_USER_EPHEMERAL"


class Provenance(Enum):
    USER = "user"
    OCR = "ocr"
    EXTRACTOR = "extractor"
    CORPUS_14 = "corpus:14"
    DATASET = "dataset"
    DERIVED = "derived"
    CONFIG = "config"
    USER_CONFIG = "user/config"
    EXTRACTOR_USER = "extractor/user"


class BilingualTag(Enum):
    CANONICAL = "canonical"
    KO_PRIMARY = "ko-primary"
    EN_ALIAS = "en-alias"
    KO_EN = "ko/en"
    NOT_APPLICABLE = "n/a"


class Unit(Enum):
    NONE = "-"
    KRW = "KRW"
    FRAC = "frac"
    DAYS = "days"
    MONTHS = "months"
    SECONDS = "seconds"
    MINUTES = "minutes"
    PIXELS = "px"
    COUNT = "count"
    HOURS = "hours"
    KRW_PER_HOUR = "KRW/hour"
    KRW_PER_MONTH = "KRW/month"


class UILocale(Enum):
    KO = "ko"
    EN = "en"


class InputMode(Enum):
    CAMERA = "camera"
    IMAGE = "image"
    PDF = "pdf"
    PASTE = "paste"


class RuntimeProfile(Enum):
    DESKTOP_FULL = "desktop_full"
    MOBILE_LITE = "mobile_lite"


class MimeType(Enum):
    IMAGE = "image/*"
    PDF = "application/pdf"
    TEXT = "text/plain"


class ValidationStatus(Enum):
    ACCEPTED = "accepted"
    REJECTED_UNSUPPORTED = "rejected_unsupported"
    REJECTED_CORRUPT = "rejected_corrupt"
    REJECTED_ENCRYPTED = "rejected_encrypted"
    REJECTED_OVERSIZED = "rejected_oversized"


class TextSource(Enum):
    TEXT_LAYER = "text_layer"
    OCR = "ocr"
    MIXED = "mixed"


class Lang(Enum):
    KO = "ko"
    EN = "en"
    MIXED = "mixed"
    NUM = "num"


class RiskCategory(Enum):
    F1 = "F1"
    F2 = "F2"
    F3 = "F3"
    F4 = "F4"
    F5 = "F5"
    F6 = "F6"
    F7 = "F7"
    F8 = "F8"
    F9 = "F9"
    X1 = "X1"
    X2 = "X2"
    X3 = "X3"
    X4 = "X4"
    X5 = "X5"


class AuthorityTier(Enum):
    A0 = "A0"
    A1 = "A1"
    A2 = "A2"


class VerificationStatus(Enum):
    VERIFIED = "VERIFIED"
    UNVERIFIED = "UNVERIFIED"
    NOT_VERIFIED_CURRENT = "NOT_VERIFIED_CURRENT"


class DetectorType(Enum):
    RULE = "rule"
    MODEL = "model"
    HYBRID = "hybrid"


class FimModule(Enum):
    FIM_1 = "FIM-1"
    FIM_2 = "FIM-2"
    FIM_3 = "FIM-3"
    FIM_4 = "FIM-4"
    FIM_5 = "FIM-5"
    FIM_6 = "FIM-6"
    FIM_7 = "FIM-7"
    FIM_8 = "FIM-8"


class ExposureType(Enum):
    NOMINAL_LEAKAGE = "nominal_leakage"
    PRESENT_VALUE_LOSS = "present_value_loss"
    OPPORTUNITY_COST = "opportunity_cost"
    LIABILITY_EXPOSURE = "liability_exposure"
    DEFERRAL = "deferral"


class PathwayLabel(Enum):
    CLARIFICATION_LIKELY_SUFFICIENT = "clarification_likely_sufficient"
    NEGOTIATION_REQUIRED = "negotiation_required"
    PROFESSIONAL_REVIEW_REQUIRED = "professional_review_required"
    DISPUTE_PATHWAY_MAY_BE_REQUIRED = "dispute_pathway_may_be_required"


class ExportFormat(Enum):
    HTML = "html"
    MD = "md"
    JSON = "json"


class TargetType(Enum):
    OCR_SPAN = "ocr_span"
    TERM = "term"
    SEGMENTATION = "segmentation"
    ASSUMPTION = "assumption"


class Split(Enum):
    DEV = "dev"
    FROZEN_EVAL = "frozen_eval"


class InputKind(Enum):
    CLAUSE_PAIR = "clause_pair"
    CAMERA_OCR = "camera_ocr"
    PASTE = "paste"
    QUERY = "query"


class ExperimentArm(Enum):
    RULE_ONLY = "rule_only"
    MODEL_ONLY = "model_only"
    HYBRID = "hybrid"


class ResultStatus(Enum):
    MEASURED = "measured"
    PLANNED = "planned"
    NA = "NA"


FINANCIAL_RISK_CATEGORIES = frozenset(
    {
        RiskCategory.F1,
        RiskCategory.F2,
        RiskCategory.F3,
        RiskCategory.F4,
        RiskCategory.F5,
        RiskCategory.F6,
        RiskCategory.F7,
        RiskCategory.F8,
        RiskCategory.F9,
    }
)
LOG_EXCLUDED_PRIVACY = frozenset({PrivacyClass.P2_PRIVATE_LOCAL, PrivacyClass.P3_USER_EPHEMERAL})
SCHEMA_METADATA_KEYS = frozenset(
    {"nullable", "unit", "provenance", "bilingual", "privacy", "generated_translation"}
)
UPPER_SNAKE_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
HEX_SHA256_RE = re.compile(r"^[a-fA-F0-9]{64}$")
DATASET_REF_RE = re.compile(r"^DR-\d+$")


def schema_field(
    *,
    privacy: PrivacyClass,
    provenance: Provenance,
    bilingual: BilingualTag,
    unit: Unit = Unit.NONE,
    nullable: bool = False,
    generated_translation: bool = False,
    default: Any = MISSING,
    default_factory: Any = MISSING,
) -> Any:
    """Create a dataclass field with the spec-02 metadata contract attached."""
    metadata = {
        "nullable": nullable,
        "unit": unit,
        "provenance": provenance,
        "bilingual": bilingual,
        "privacy": privacy,
        "generated_translation": generated_translation,
    }
    kwargs: dict[str, Any] = {"metadata": metadata}
    if default is not MISSING:
        kwargs["default"] = default
    if default_factory is not MISSING:
        kwargs["default_factory"] = default_factory
    return field(**kwargs)


class SchemaModel:
    """Base class for schema validation and privacy-aware serialization."""

    def _validate_field_contracts(self) -> None:
        for item in fields(self):
            missing_keys = SCHEMA_METADATA_KEYS - set(item.metadata)
            if missing_keys:
                raise SchemaValidationError(
                    f"{type(self).__name__}.{item.name}: missing metadata {sorted(missing_keys)}"
                )
            if not isinstance(item.metadata["privacy"], PrivacyClass):
                raise SchemaValidationError(f"{type(self).__name__}.{item.name}: bad privacy")
            if getattr(self, item.name) is None and not item.metadata["nullable"]:
                raise SchemaValidationError(f"{type(self).__name__}.{item.name}: may not be null")

    def to_dict(self) -> dict[str, Any]:
        """Serialize all fields for internal use. Do not use this for logs."""
        return _serialize_dataclass(self, log_safe=False)

    def to_log_dict(self) -> dict[str, Any]:
        """Serialize only fields allowed in logs; P2/P3 fields are omitted."""
        return _serialize_dataclass(self, log_safe=True)

    as_log_dict = to_log_dict


def schema_field_metadata(schema_cls: type[SchemaModel]) -> dict[str, dict[str, Any]]:
    return {item.name: dict(item.metadata) for item in fields(schema_cls)}


def default_execution_path() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "execution_path_id": "deterministic_fallback_v1",
        "local_only": True,
        "remote_runtime_api_allowed": False,
        "runtime_download_allowed": False,
        "deterministic_fallback_active": True,
        "model_status": {
            "summary_status": "deterministic_fallback_active",
            "available_statuses": [
                "not_installed",
                "installed",
                "loading",
                "active",
                "failed_health_check",
                "deterministic_fallback_active",
            ],
        },
        "steps": [
            {
                "adapter": "ocr",
                "model_status": "deterministic_fallback_active",
                "execution_path": "deterministic_fallback",
            },
            {
                "adapter": "embedding",
                "model_status": "deterministic_fallback_active",
                "execution_path": "deterministic_fallback",
            },
            {
                "adapter": "reranker",
                "model_status": "deterministic_fallback_active",
                "execution_path": "deterministic_fallback",
            },
            {
                "adapter": "optional_extractor",
                "model_status": "deterministic_fallback_active",
                "execution_path": "deterministic_fallback",
            },
            {
                "adapter": "optional_explanation_qa",
                "model_status": "deterministic_fallback_active",
                "execution_path": "deterministic_fallback",
            },
        ],
    }


@dataclass
class AnalysisRequest(SchemaModel):
    request_id: str = schema_field(
        privacy=PrivacyClass.P3_USER_EPHEMERAL,
        provenance=Provenance.DERIVED,
        bilingual=BilingualTag.NOT_APPLICABLE,
    )
    created_at: datetime = schema_field(
        privacy=PrivacyClass.P3_USER_EPHEMERAL,
        provenance=Provenance.DERIVED,
        bilingual=BilingualTag.NOT_APPLICABLE,
    )
    ui_locale: UILocale = schema_field(
        privacy=PrivacyClass.P1_INTERNAL,
        provenance=Provenance.USER,
        bilingual=BilingualTag.NOT_APPLICABLE,
    )
    input_mode: InputMode = schema_field(
        privacy=PrivacyClass.P3_USER_EPHEMERAL,
        provenance=Provenance.USER,
        bilingual=BilingualTag.NOT_APPLICABLE,
    )
    runtime_profile: RuntimeProfile = schema_field(
        privacy=PrivacyClass.P1_INTERNAL,
        provenance=Provenance.CONFIG,
        bilingual=BilingualTag.NOT_APPLICABLE,
    )
    documents: tuple[UploadedDocument, ...] = schema_field(
        privacy=PrivacyClass.P3_USER_EPHEMERAL,
        provenance=Provenance.USER,
        bilingual=BilingualTag.NOT_APPLICABLE,
    )
    consent_local_only: bool = schema_field(
        privacy=PrivacyClass.P1_INTERNAL,
        provenance=Provenance.USER,
        bilingual=BilingualTag.NOT_APPLICABLE,
    )
    pasted_text: str | None = schema_field(
        privacy=PrivacyClass.P3_USER_EPHEMERAL,
        provenance=Provenance.USER,
        bilingual=BilingualTag.KO_PRIMARY,
        nullable=True,
        default=None,
    )
    scenario_inputs: FinancialScenarioInputs | None = schema_field(
        privacy=PrivacyClass.P3_USER_EPHEMERAL,
        provenance=Provenance.USER,
        bilingual=BilingualTag.NOT_APPLICABLE,
        nullable=True,
        default=None,
    )

    def __post_init__(self) -> None:
        self._validate_field_contracts()
        _coerce_datetime_attr(self, "created_at")
        _coerce_enum_attr(self, "ui_locale", UILocale)
        _coerce_enum_attr(self, "input_mode", InputMode)
        _coerce_enum_attr(self, "runtime_profile", RuntimeProfile)
        _validate_uuid_text(self.request_id, "request_id")
        _validate_bool(self.consent_local_only, "consent_local_only")
        _require(self.consent_local_only, "consent_local_only must be true")
        self.documents = _coerce_tuple(self.documents, "documents")
        for document in self.documents:
            _require_type(document, UploadedDocument, "documents")
        if self.input_mode is InputMode.PASTE:
            _require_nonblank(self.pasted_text, "pasted_text")
            _require(not self.documents, "paste requests must not include uploaded documents")
        else:
            _require(self.pasted_text is None, "pasted_text is only valid for paste input")
            _require(len(self.documents) >= 1, "documents must contain at least one upload")
        if self.scenario_inputs is not None:
            _require_type(self.scenario_inputs, FinancialScenarioInputs, "scenario_inputs")


@dataclass
class UploadedDocument(SchemaModel):
    document_id: str = schema_field(
        privacy=PrivacyClass.P3_USER_EPHEMERAL,
        provenance=Provenance.DERIVED,
        bilingual=BilingualTag.NOT_APPLICABLE,
    )
    filename_hash: str = schema_field(
        privacy=PrivacyClass.P3_USER_EPHEMERAL,
        provenance=Provenance.DERIVED,
        bilingual=BilingualTag.NOT_APPLICABLE,
    )
    mime_type: MimeType = schema_field(
        privacy=PrivacyClass.P3_USER_EPHEMERAL,
        provenance=Provenance.EXTRACTOR,
        bilingual=BilingualTag.NOT_APPLICABLE,
    )
    magic_byte_verified: bool = schema_field(
        privacy=PrivacyClass.P3_USER_EPHEMERAL,
        provenance=Provenance.EXTRACTOR,
        bilingual=BilingualTag.NOT_APPLICABLE,
    )
    is_encrypted: bool = schema_field(
        privacy=PrivacyClass.P3_USER_EPHEMERAL,
        provenance=Provenance.EXTRACTOR,
        bilingual=BilingualTag.NOT_APPLICABLE,
    )
    validation_status: ValidationStatus = schema_field(
        privacy=PrivacyClass.P3_USER_EPHEMERAL,
        provenance=Provenance.EXTRACTOR,
        bilingual=BilingualTag.NOT_APPLICABLE,
    )
    page_count: int = schema_field(
        privacy=PrivacyClass.P3_USER_EPHEMERAL,
        provenance=Provenance.EXTRACTOR,
        bilingual=BilingualTag.NOT_APPLICABLE,
        unit=Unit.COUNT,
    )
    temp_path: str = schema_field(
        privacy=PrivacyClass.P3_USER_EPHEMERAL,
        provenance=Provenance.DERIVED,
        bilingual=BilingualTag.NOT_APPLICABLE,
    )
    bytes_sha256: str = schema_field(
        privacy=PrivacyClass.P3_USER_EPHEMERAL,
        provenance=Provenance.DERIVED,
        bilingual=BilingualTag.NOT_APPLICABLE,
    )
    delete_after: datetime = schema_field(
        privacy=PrivacyClass.P1_INTERNAL,
        provenance=Provenance.CONFIG,
        bilingual=BilingualTag.NOT_APPLICABLE,
    )
    pages: tuple[OCRPage, ...] | None = schema_field(
        privacy=PrivacyClass.P3_USER_EPHEMERAL,
        provenance=Provenance.OCR,
        bilingual=BilingualTag.NOT_APPLICABLE,
        nullable=True,
        default=None,
    )

    def __post_init__(self) -> None:
        self._validate_field_contracts()
        _validate_uuid_text(self.document_id, "document_id")
        _coerce_enum_attr(self, "mime_type", MimeType)
        _coerce_enum_attr(self, "validation_status", ValidationStatus)
        _coerce_datetime_attr(self, "delete_after")
        _validate_bool(self.magic_byte_verified, "magic_byte_verified")
        _validate_bool(self.is_encrypted, "is_encrypted")
        _require(_is_positive_int(self.page_count), "page_count must be >= 1")
        _require_nonblank(self.filename_hash, "filename_hash")
        _require("/" not in self.filename_hash and "\\" not in self.filename_hash, "filename_hash")
        _require_nonblank(self.temp_path, "temp_path")
        _require(HEX_SHA256_RE.match(self.bytes_sha256) is not None, "bytes_sha256 must be sha256")
        if self.mime_type is MimeType.PDF and self.validation_status is ValidationStatus.ACCEPTED:
            _require(self.magic_byte_verified, "accepted PDFs must have verified magic bytes")
            _require(not self.is_encrypted, "encrypted PDFs must be rejected by default")
        if self.pages is not None:
            self.pages = _coerce_tuple(self.pages, "pages")
            for page in self.pages:
                _require_type(page, OCRPage, "pages")


@dataclass
class OCRPage(SchemaModel):
    page_id: str = schema_field(
        privacy=PrivacyClass.P3_USER_EPHEMERAL,
        provenance=Provenance.DERIVED,
        bilingual=BilingualTag.NOT_APPLICABLE,
    )
    page_index: int = schema_field(
        privacy=PrivacyClass.P3_USER_EPHEMERAL,
        provenance=Provenance.USER,
        bilingual=BilingualTag.NOT_APPLICABLE,
        unit=Unit.COUNT,
    )
    rotation_deg: int = schema_field(
        privacy=PrivacyClass.P3_USER_EPHEMERAL,
        provenance=Provenance.USER,
        bilingual=BilingualTag.NOT_APPLICABLE,
    )
    width_px: int = schema_field(
        privacy=PrivacyClass.P3_USER_EPHEMERAL,
        provenance=Provenance.EXTRACTOR,
        bilingual=BilingualTag.NOT_APPLICABLE,
        unit=Unit.PIXELS,
    )
    height_px: int = schema_field(
        privacy=PrivacyClass.P3_USER_EPHEMERAL,
        provenance=Provenance.EXTRACTOR,
        bilingual=BilingualTag.NOT_APPLICABLE,
        unit=Unit.PIXELS,
    )
    spans: tuple[OCRSpan, ...] = schema_field(
        privacy=PrivacyClass.P3_USER_EPHEMERAL,
        provenance=Provenance.OCR,
        bilingual=BilingualTag.NOT_APPLICABLE,
    )
    page_ocr_confidence: float = schema_field(
        privacy=PrivacyClass.P3_USER_EPHEMERAL,
        provenance=Provenance.OCR,
        bilingual=BilingualTag.NOT_APPLICABLE,
        unit=Unit.FRAC,
    )
    text_source: TextSource = schema_field(
        privacy=PrivacyClass.P3_USER_EPHEMERAL,
        provenance=Provenance.EXTRACTOR,
        bilingual=BilingualTag.NOT_APPLICABLE,
    )
    is_user_corrected: bool = schema_field(
        privacy=PrivacyClass.P3_USER_EPHEMERAL,
        provenance=Provenance.DERIVED,
        bilingual=BilingualTag.NOT_APPLICABLE,
    )

    def __post_init__(self) -> None:
        self._validate_field_contracts()
        _require_nonblank(self.page_id, "page_id")
        _require(_is_nonnegative_int(self.page_index), "page_index must be >= 0")
        _require(self.rotation_deg in {0, 90, 180, 270}, "rotation_deg must be 0/90/180/270")
        _require(_is_positive_int(self.width_px), "width_px must be > 0")
        _require(_is_positive_int(self.height_px), "height_px must be > 0")
        self.spans = _coerce_tuple(self.spans, "spans")
        for span in self.spans:
            _require_type(span, OCRSpan, "spans")
            _validate_bbox_within_page(span.bbox, self.width_px, self.height_px, span.span_id)
        _validate_float_attr(self, "page_ocr_confidence", minimum=0.0, maximum=1.0)
        _coerce_enum_attr(self, "text_source", TextSource)
        _validate_bool(self.is_user_corrected, "is_user_corrected")


@dataclass
class OCRSpan(SchemaModel):
    span_id: str = schema_field(
        privacy=PrivacyClass.P3_USER_EPHEMERAL,
        provenance=Provenance.DERIVED,
        bilingual=BilingualTag.NOT_APPLICABLE,
    )
    text: str = schema_field(
        privacy=PrivacyClass.P3_USER_EPHEMERAL,
        provenance=Provenance.OCR,
        bilingual=BilingualTag.KO_PRIMARY,
    )
    bbox: dict[str, int] = schema_field(
        privacy=PrivacyClass.P3_USER_EPHEMERAL,
        provenance=Provenance.OCR,
        bilingual=BilingualTag.NOT_APPLICABLE,
        unit=Unit.PIXELS,
    )
    confidence: float = schema_field(
        privacy=PrivacyClass.P3_USER_EPHEMERAL,
        provenance=Provenance.OCR,
        bilingual=BilingualTag.NOT_APPLICABLE,
        unit=Unit.FRAC,
    )
    lang: Lang = schema_field(
        privacy=PrivacyClass.P3_USER_EPHEMERAL,
        provenance=Provenance.OCR,
        bilingual=BilingualTag.NOT_APPLICABLE,
    )
    corrected_text: str | None = schema_field(
        privacy=PrivacyClass.P3_USER_EPHEMERAL,
        provenance=Provenance.USER,
        bilingual=BilingualTag.KO_PRIMARY,
        nullable=True,
        default=None,
    )

    def __post_init__(self) -> None:
        self._validate_field_contracts()
        _require_nonblank(self.span_id, "span_id")
        _require(isinstance(self.text, str), "text must be str")
        _validate_bbox(self.bbox, "bbox")
        _validate_float_attr(self, "confidence", minimum=0.0, maximum=1.0)
        _coerce_enum_attr(self, "lang", Lang)
        if self.corrected_text is not None:
            _require(isinstance(self.corrected_text, str), "corrected_text must be str")


@dataclass
class Clause(SchemaModel):
    clause_id: str = schema_field(
        privacy=PrivacyClass.P3_USER_EPHEMERAL,
        provenance=Provenance.DERIVED,
        bilingual=BilingualTag.NOT_APPLICABLE,
    )
    clause_index: int = schema_field(
        privacy=PrivacyClass.P3_USER_EPHEMERAL,
        provenance=Provenance.DERIVED,
        bilingual=BilingualTag.NOT_APPLICABLE,
        unit=Unit.COUNT,
    )
    text_ko: str = schema_field(
        privacy=PrivacyClass.P3_USER_EPHEMERAL,
        provenance=Provenance.DERIVED,
        bilingual=BilingualTag.KO_PRIMARY,
    )
    source_span_ids: tuple[str, ...] = schema_field(
        privacy=PrivacyClass.P3_USER_EPHEMERAL,
        provenance=Provenance.DERIVED,
        bilingual=BilingualTag.NOT_APPLICABLE,
    )
    seg_confidence: float = schema_field(
        privacy=PrivacyClass.P3_USER_EPHEMERAL,
        provenance=Provenance.EXTRACTOR,
        bilingual=BilingualTag.NOT_APPLICABLE,
        unit=Unit.FRAC,
    )
    heading_ko: str | None = schema_field(
        privacy=PrivacyClass.P3_USER_EPHEMERAL,
        provenance=Provenance.EXTRACTOR,
        bilingual=BilingualTag.KO_PRIMARY,
        nullable=True,
        default=None,
    )
    text_en_gloss: str | None = schema_field(
        privacy=PrivacyClass.P3_USER_EPHEMERAL,
        provenance=Provenance.DERIVED,
        bilingual=BilingualTag.EN_ALIAS,
        nullable=True,
        generated_translation=True,
        default=None,
    )
    risk_categories: tuple[RiskCategory, ...] | None = schema_field(
        privacy=PrivacyClass.P3_USER_EPHEMERAL,
        provenance=Provenance.DERIVED,
        bilingual=BilingualTag.NOT_APPLICABLE,
        nullable=True,
        default=None,
    )
    canonical_ids: tuple[str, ...] | None = schema_field(
        privacy=PrivacyClass.P3_USER_EPHEMERAL,
        provenance=Provenance.DERIVED,
        bilingual=BilingualTag.CANONICAL,
        nullable=True,
        default=None,
    )

    def __post_init__(self) -> None:
        self._validate_field_contracts()
        _require_nonblank(self.clause_id, "clause_id")
        _require(_is_nonnegative_int(self.clause_index), "clause_index must be >= 0")
        _require_nonblank(self.text_ko, "text_ko")
        self.source_span_ids = _validate_nonempty_text_tuple(
            self.source_span_ids, "source_span_ids"
        )
        _validate_float_attr(self, "seg_confidence", minimum=0.0, maximum=1.0)
        if self.risk_categories is not None:
            self.risk_categories = _coerce_enum_tuple(
                self.risk_categories, RiskCategory, "risk_categories"
            )
        if self.canonical_ids is not None:
            self.canonical_ids = _validate_text_tuple(self.canonical_ids, "canonical_ids")


@dataclass
class ExtractedFinancialTerms(SchemaModel):
    term_id: str = schema_field(
        privacy=PrivacyClass.P3_USER_EPHEMERAL,
        provenance=Provenance.DERIVED,
        bilingual=BilingualTag.NOT_APPLICABLE,
    )
    clause_id: str = schema_field(
        privacy=PrivacyClass.P3_USER_EPHEMERAL,
        provenance=Provenance.DERIVED,
        bilingual=BilingualTag.NOT_APPLICABLE,
    )
    feature_id: str = schema_field(
        privacy=PrivacyClass.P3_USER_EPHEMERAL,
        provenance=Provenance.EXTRACTOR,
        bilingual=BilingualTag.CANONICAL,
    )
    value_raw: str = schema_field(
        privacy=PrivacyClass.P3_USER_EPHEMERAL,
        provenance=Provenance.OCR,
        bilingual=BilingualTag.KO_PRIMARY,
    )
    unit: Unit = schema_field(
        privacy=PrivacyClass.P3_USER_EPHEMERAL,
        provenance=Provenance.EXTRACTOR,
        bilingual=BilingualTag.NOT_APPLICABLE,
    )
    is_open_ended: bool = schema_field(
        privacy=PrivacyClass.P3_USER_EPHEMERAL,
        provenance=Provenance.EXTRACTOR,
        bilingual=BilingualTag.NOT_APPLICABLE,
    )
    extraction_confidence: float = schema_field(
        privacy=PrivacyClass.P3_USER_EPHEMERAL,
        provenance=Provenance.EXTRACTOR,
        bilingual=BilingualTag.NOT_APPLICABLE,
        unit=Unit.FRAC,
    )
    source_span_ids: tuple[str, ...] = schema_field(
        privacy=PrivacyClass.P3_USER_EPHEMERAL,
        provenance=Provenance.DERIVED,
        bilingual=BilingualTag.NOT_APPLICABLE,
    )
    value_norm: Decimal | int | float | None = schema_field(
        privacy=PrivacyClass.P3_USER_EPHEMERAL,
        provenance=Provenance.EXTRACTOR,
        bilingual=BilingualTag.NOT_APPLICABLE,
        nullable=True,
        default=None,
    )

    def __post_init__(self) -> None:
        self._validate_field_contracts()
        _require_nonblank(self.term_id, "term_id")
        _require_nonblank(self.clause_id, "clause_id")
        _require(
            UPPER_SNAKE_RE.match(self.feature_id) is not None,
            "feature_id must be UPPER_SNAKE",
        )
        _require_nonblank(self.value_raw, "value_raw")
        _coerce_enum_attr(self, "unit", Unit)
        _require(self.unit in {Unit.KRW, Unit.FRAC, Unit.DAYS, Unit.MONTHS, Unit.NONE}, "unit")
        _validate_bool(self.is_open_ended, "is_open_ended")
        _validate_float_attr(self, "extraction_confidence", minimum=0.0, maximum=1.0)
        self.source_span_ids = _validate_nonempty_text_tuple(
            self.source_span_ids, "source_span_ids"
        )
        if self.value_norm is None:
            _require(self.is_open_ended, "value_norm may be null only for open-ended/opaque terms")
        elif self.unit is Unit.KRW:
            self.value_norm = _coerce_nonnegative_decimal(self.value_norm, "value_norm")
        elif self.unit is Unit.FRAC:
            self.value_norm = _coerce_fraction(self.value_norm, "value_norm")
        elif self.unit in {Unit.DAYS, Unit.MONTHS}:
            _require(_is_nonnegative_number(self.value_norm), "value_norm must be >= 0")


@dataclass
class EvidenceRecord(SchemaModel):
    evidence_id: str = schema_field(
        privacy=PrivacyClass.P1_INTERNAL,
        provenance=Provenance.CORPUS_14,
        bilingual=BilingualTag.CANONICAL,
    )
    source_id: str = schema_field(
        privacy=PrivacyClass.P1_INTERNAL,
        provenance=Provenance.CORPUS_14,
        bilingual=BilingualTag.NOT_APPLICABLE,
    )
    authority_tier: AuthorityTier = schema_field(
        privacy=PrivacyClass.P1_INTERNAL,
        provenance=Provenance.CORPUS_14,
        bilingual=BilingualTag.NOT_APPLICABLE,
    )
    risk_categories: tuple[RiskCategory, ...] = schema_field(
        privacy=PrivacyClass.P1_INTERNAL,
        provenance=Provenance.CORPUS_14,
        bilingual=BilingualTag.NOT_APPLICABLE,
    )
    verification_status: VerificationStatus = schema_field(
        privacy=PrivacyClass.P1_INTERNAL,
        provenance=Provenance.CORPUS_14,
        bilingual=BilingualTag.NOT_APPLICABLE,
    )
    score_eligible: bool = schema_field(
        privacy=PrivacyClass.P1_INTERNAL,
        provenance=Provenance.DERIVED,
        bilingual=BilingualTag.NOT_APPLICABLE,
    )
    public_export: bool = schema_field(
        privacy=PrivacyClass.P1_INTERNAL,
        provenance=Provenance.CORPUS_14,
        bilingual=BilingualTag.NOT_APPLICABLE,
    )
    article_ref: str | None = schema_field(
        privacy=PrivacyClass.P1_INTERNAL,
        provenance=Provenance.CORPUS_14,
        bilingual=BilingualTag.KO_PRIMARY,
        nullable=True,
        default=None,
    )
    page_ref: str | None = schema_field(
        privacy=PrivacyClass.P1_INTERNAL,
        provenance=Provenance.CORPUS_14,
        bilingual=BilingualTag.NOT_APPLICABLE,
        nullable=True,
        default=None,
    )
    excerpt_ko: str | None = schema_field(
        privacy=PrivacyClass.P2_PRIVATE_LOCAL,
        provenance=Provenance.CORPUS_14,
        bilingual=BilingualTag.KO_PRIMARY,
        nullable=True,
        default=None,
    )
    excerpt_en_gloss: str | None = schema_field(
        privacy=PrivacyClass.P2_PRIVATE_LOCAL,
        provenance=Provenance.CORPUS_14,
        bilingual=BilingualTag.EN_ALIAS,
        nullable=True,
        generated_translation=True,
        default=None,
    )

    def __post_init__(self) -> None:
        self._validate_field_contracts()
        _require_nonblank(self.evidence_id, "evidence_id")
        _require_nonblank(self.source_id, "source_id")
        _coerce_enum_attr(self, "authority_tier", AuthorityTier)
        _coerce_enum_attr(self, "verification_status", VerificationStatus)
        self.risk_categories = _coerce_enum_tuple(
            self.risk_categories, RiskCategory, "risk_categories"
        )
        _require(self.risk_categories, "risk_categories must contain at least one category")
        _validate_bool(self.score_eligible, "score_eligible")
        _validate_bool(self.public_export, "public_export")
        _require(self.score_eligible, "A0-A2 evidence records are score-eligible")
        if self.excerpt_ko is not None:
            _require(_word_count(self.excerpt_ko) < 15, "excerpt_ko must be < 15 words")


@dataclass
class RiskSignal(SchemaModel):
    signal_id: str = schema_field(
        privacy=PrivacyClass.P1_INTERNAL,
        provenance=Provenance.CONFIG,
        bilingual=BilingualTag.CANONICAL,
    )
    clause_id: str = schema_field(
        privacy=PrivacyClass.P3_USER_EPHEMERAL,
        provenance=Provenance.DERIVED,
        bilingual=BilingualTag.NOT_APPLICABLE,
    )
    risk_category: RiskCategory = schema_field(
        privacy=PrivacyClass.P3_USER_EPHEMERAL,
        provenance=Provenance.DERIVED,
        bilingual=BilingualTag.NOT_APPLICABLE,
    )
    detector: DetectorType = schema_field(
        privacy=PrivacyClass.P1_INTERNAL,
        provenance=Provenance.CONFIG,
        bilingual=BilingualTag.NOT_APPLICABLE,
    )
    fired: bool = schema_field(
        privacy=PrivacyClass.P3_USER_EPHEMERAL,
        provenance=Provenance.DERIVED,
        bilingual=BilingualTag.NOT_APPLICABLE,
    )
    score_eligible: bool = schema_field(
        privacy=PrivacyClass.P3_USER_EPHEMERAL,
        provenance=Provenance.DERIVED,
        bilingual=BilingualTag.NOT_APPLICABLE,
    )
    practice_reference: bool = schema_field(
        privacy=PrivacyClass.P3_USER_EPHEMERAL,
        provenance=Provenance.DERIVED,
        bilingual=BilingualTag.NOT_APPLICABLE,
    )
    signal_confidence: float = schema_field(
        privacy=PrivacyClass.P3_USER_EPHEMERAL,
        provenance=Provenance.DERIVED,
        bilingual=BilingualTag.NOT_APPLICABLE,
        unit=Unit.FRAC,
    )
    is_missing_protection: bool = schema_field(
        privacy=PrivacyClass.P3_USER_EPHEMERAL,
        provenance=Provenance.DERIVED,
        bilingual=BilingualTag.NOT_APPLICABLE,
    )
    grounding_evidence_ids: tuple[str, ...] | None = schema_field(
        privacy=PrivacyClass.P3_USER_EPHEMERAL,
        provenance=Provenance.DERIVED,
        bilingual=BilingualTag.NOT_APPLICABLE,
        nullable=True,
        default=None,
    )
    severity_raw: float | None = schema_field(
        privacy=PrivacyClass.P3_USER_EPHEMERAL,
        provenance=Provenance.CONFIG,
        bilingual=BilingualTag.NOT_APPLICABLE,
        unit=Unit.FRAC,
        nullable=True,
        default=None,
    )

    def __post_init__(self) -> None:
        self._validate_field_contracts()
        _require(self.signal_id.startswith("RS-"), "signal_id must start with RS-")
        _require_nonblank(self.clause_id, "clause_id")
        _coerce_enum_attr(self, "risk_category", RiskCategory)
        _coerce_enum_attr(self, "detector", DetectorType)
        _validate_bool(self.fired, "fired")
        _validate_bool(self.score_eligible, "score_eligible")
        _validate_bool(self.practice_reference, "practice_reference")
        _validate_float_attr(self, "signal_confidence", minimum=0.0, maximum=1.0)
        _validate_bool(self.is_missing_protection, "is_missing_protection")
        if self.grounding_evidence_ids is not None:
            self.grounding_evidence_ids = _validate_text_tuple(
                self.grounding_evidence_ids, "grounding_evidence_ids"
            )
        has_evidence = bool(self.grounding_evidence_ids)
        _require(
            self.score_eligible is has_evidence,
            "score_eligible must match presence of A0-A2 grounding evidence ids",
        )
        if self.practice_reference:
            _require(not self.score_eligible, "practice references are never score-eligible")
        if self.severity_raw is not None:
            self.severity_raw = _coerce_fraction(self.severity_raw, "severity_raw")


@dataclass
class ClauseAssessment(SchemaModel):
    clause_id: str = schema_field(
        privacy=PrivacyClass.P3_USER_EPHEMERAL,
        provenance=Provenance.DERIVED,
        bilingual=BilingualTag.NOT_APPLICABLE,
    )
    signals: tuple[RiskSignal, ...] = schema_field(
        privacy=PrivacyClass.P3_USER_EPHEMERAL,
        provenance=Provenance.DERIVED,
        bilingual=BilingualTag.NOT_APPLICABLE,
    )
    category_scores: dict[RiskCategory, float] = schema_field(
        privacy=PrivacyClass.P3_USER_EPHEMERAL,
        provenance=Provenance.DERIVED,
        bilingual=BilingualTag.NOT_APPLICABLE,
    )
    clause_priority: int = schema_field(
        privacy=PrivacyClass.P3_USER_EPHEMERAL,
        provenance=Provenance.DERIVED,
        bilingual=BilingualTag.NOT_APPLICABLE,
    )
    explanation_card_ids: tuple[str, ...] | None = schema_field(
        privacy=PrivacyClass.P3_USER_EPHEMERAL,
        provenance=Provenance.DERIVED,
        bilingual=BilingualTag.NOT_APPLICABLE,
        nullable=True,
        default=None,
    )
    questions: tuple[str, ...] | None = schema_field(
        privacy=PrivacyClass.P3_USER_EPHEMERAL,
        provenance=Provenance.DERIVED,
        bilingual=BilingualTag.KO_PRIMARY,
        nullable=True,
        default=None,
    )
    evidence_ids: tuple[str, ...] | None = schema_field(
        privacy=PrivacyClass.P3_USER_EPHEMERAL,
        provenance=Provenance.DERIVED,
        bilingual=BilingualTag.NOT_APPLICABLE,
        nullable=True,
        default=None,
    )
    monetary_links: tuple[FimModule, ...] | None = schema_field(
        privacy=PrivacyClass.P3_USER_EPHEMERAL,
        provenance=Provenance.DERIVED,
        bilingual=BilingualTag.NOT_APPLICABLE,
        nullable=True,
        default=None,
    )

    def __post_init__(self) -> None:
        self._validate_field_contracts()
        _require_nonblank(self.clause_id, "clause_id")
        self.signals = _coerce_tuple(self.signals, "signals")
        for signal in self.signals:
            _require_type(signal, RiskSignal, "signals")
        self.category_scores = _validate_category_scores(self.category_scores, "category_scores")
        _validate_score_int(self.clause_priority, "clause_priority")
        if self.explanation_card_ids is not None:
            self.explanation_card_ids = _validate_text_tuple(
                self.explanation_card_ids, "explanation_card_ids"
            )
        if self.questions is not None:
            self.questions = _validate_text_tuple(self.questions, "questions")
        if self.evidence_ids is not None:
            self.evidence_ids = _validate_text_tuple(self.evidence_ids, "evidence_ids")
        if self.monetary_links is not None:
            self.monetary_links = _coerce_enum_tuple(
                self.monetary_links, FimModule, "monetary_links"
            )


@dataclass
class FinancialScenarioInputs(SchemaModel):
    annual_discount_rate: float = schema_field(
        privacy=PrivacyClass.P3_USER_EPHEMERAL,
        provenance=Provenance.USER_CONFIG,
        bilingual=BilingualTag.NOT_APPLICABLE,
        unit=Unit.FRAC,
    )
    inputs_are_synthetic: bool = schema_field(
        privacy=PrivacyClass.P1_INTERNAL,
        provenance=Provenance.DERIVED,
        bilingual=BilingualTag.NOT_APPLICABLE,
    )
    sales_low: Decimal | None = schema_field(
        privacy=PrivacyClass.P3_USER_EPHEMERAL,
        provenance=Provenance.USER,
        bilingual=BilingualTag.NOT_APPLICABLE,
        unit=Unit.KRW,
        nullable=True,
        default=None,
    )
    sales_base: Decimal | None = schema_field(
        privacy=PrivacyClass.P3_USER_EPHEMERAL,
        provenance=Provenance.USER,
        bilingual=BilingualTag.NOT_APPLICABLE,
        unit=Unit.KRW,
        nullable=True,
        default=None,
    )
    sales_high: Decimal | None = schema_field(
        privacy=PrivacyClass.P3_USER_EPHEMERAL,
        provenance=Provenance.USER,
        bilingual=BilingualTag.NOT_APPLICABLE,
        unit=Unit.KRW,
        nullable=True,
        default=None,
    )
    creator_hourly_value: Decimal | None = schema_field(
        privacy=PrivacyClass.P3_USER_EPHEMERAL,
        provenance=Provenance.USER,
        bilingual=BilingualTag.NOT_APPLICABLE,
        unit=Unit.KRW_PER_HOUR,
        nullable=True,
        default=None,
    )
    hours_per_unit: float | None = schema_field(
        privacy=PrivacyClass.P3_USER_EPHEMERAL,
        provenance=Provenance.USER,
        bilingual=BilingualTag.NOT_APPLICABLE,
        unit=Unit.HOURS,
        nullable=True,
        default=None,
    )
    unpaid_revision_units: int | None = schema_field(
        privacy=PrivacyClass.P3_USER_EPHEMERAL,
        provenance=Provenance.USER,
        bilingual=BilingualTag.NOT_APPLICABLE,
        unit=Unit.COUNT,
        nullable=True,
        default=None,
    )
    alternative_monthly_revenue: Decimal | None = schema_field(
        privacy=PrivacyClass.P3_USER_EPHEMERAL,
        provenance=Provenance.USER,
        bilingual=BilingualTag.NOT_APPLICABLE,
        unit=Unit.KRW_PER_MONTH,
        nullable=True,
        default=None,
    )
    scenario_probabilities: dict[str, float] | None = schema_field(
        privacy=PrivacyClass.P3_USER_EPHEMERAL,
        provenance=Provenance.USER,
        bilingual=BilingualTag.NOT_APPLICABLE,
        unit=Unit.FRAC,
        nullable=True,
        default=None,
    )
    secondary_rights: tuple[dict[str, Any], ...] | None = schema_field(
        privacy=PrivacyClass.P3_USER_EPHEMERAL,
        provenance=Provenance.USER,
        bilingual=BilingualTag.CANONICAL,
        nullable=True,
        default=None,
    )
    penalty_probability: float | None = schema_field(
        privacy=PrivacyClass.P3_USER_EPHEMERAL,
        provenance=Provenance.USER,
        bilingual=BilingualTag.NOT_APPLICABLE,
        unit=Unit.FRAC,
        nullable=True,
        default=None,
    )

    def __post_init__(self) -> None:
        self._validate_field_contracts()
        _validate_float_attr(self, "annual_discount_rate", minimum=0.0)
        _validate_bool(self.inputs_are_synthetic, "inputs_are_synthetic")
        self.sales_low, self.sales_base, self.sales_high = _validate_optional_money_range(
            self.sales_low, self.sales_base, self.sales_high, "sales"
        )
        if self.creator_hourly_value is not None:
            self.creator_hourly_value = _coerce_nonnegative_decimal(
                self.creator_hourly_value, "creator_hourly_value"
            )
        if self.hours_per_unit is not None:
            self.hours_per_unit = _coerce_nonnegative_float(self.hours_per_unit, "hours_per_unit")
        if self.unpaid_revision_units is not None:
            _require(
                _is_nonnegative_int(self.unpaid_revision_units),
                "unpaid_revision_units must be >= 0",
            )
        if self.alternative_monthly_revenue is not None:
            self.alternative_monthly_revenue = _coerce_nonnegative_decimal(
                self.alternative_monthly_revenue, "alternative_monthly_revenue"
            )
        if self.scenario_probabilities is not None:
            self.scenario_probabilities = {
                _require_nonblank_text(key, "scenario_probabilities key"): _coerce_fraction(
                    value, "scenario_probabilities value"
                )
                for key, value in self.scenario_probabilities.items()
            }
        if self.secondary_rights is not None:
            self.secondary_rights = _coerce_tuple(self.secondary_rights, "secondary_rights")
            for idx, row in enumerate(self.secondary_rights, start=1):
                _validate_secondary_right(row, idx)
        if self.penalty_probability is not None:
            self.penalty_probability = _coerce_fraction(
                self.penalty_probability, "penalty_probability"
            )


@dataclass
class MonetaryExposureEstimate(SchemaModel):
    module: FimModule = schema_field(
        privacy=PrivacyClass.P3_USER_EPHEMERAL,
        provenance=Provenance.DERIVED,
        bilingual=BilingualTag.NOT_APPLICABLE,
    )
    exposure_type: ExposureType = schema_field(
        privacy=PrivacyClass.P3_USER_EPHEMERAL,
        provenance=Provenance.DERIVED,
        bilingual=BilingualTag.NOT_APPLICABLE,
    )
    is_user_input_required: bool = schema_field(
        privacy=PrivacyClass.P3_USER_EPHEMERAL,
        provenance=Provenance.DERIVED,
        bilingual=BilingualTag.NOT_APPLICABLE,
    )
    assumptions: tuple[str, ...] = schema_field(
        privacy=PrivacyClass.P3_USER_EPHEMERAL,
        provenance=Provenance.DERIVED,
        bilingual=BilingualTag.KO_EN,
    )
    low: Decimal | None = schema_field(
        privacy=PrivacyClass.P3_USER_EPHEMERAL,
        provenance=Provenance.DERIVED,
        bilingual=BilingualTag.NOT_APPLICABLE,
        unit=Unit.KRW,
        nullable=True,
        default=None,
    )
    base: Decimal | None = schema_field(
        privacy=PrivacyClass.P3_USER_EPHEMERAL,
        provenance=Provenance.DERIVED,
        bilingual=BilingualTag.NOT_APPLICABLE,
        unit=Unit.KRW,
        nullable=True,
        default=None,
    )
    high: Decimal | None = schema_field(
        privacy=PrivacyClass.P3_USER_EPHEMERAL,
        provenance=Provenance.DERIVED,
        bilingual=BilingualTag.NOT_APPLICABLE,
        unit=Unit.KRW,
        nullable=True,
        default=None,
    )
    uncertainty_flags: tuple[str, ...] | None = schema_field(
        privacy=PrivacyClass.P3_USER_EPHEMERAL,
        provenance=Provenance.DERIVED,
        bilingual=BilingualTag.NOT_APPLICABLE,
        nullable=True,
        default=None,
    )
    nominal_amount: Decimal | None = schema_field(
        privacy=PrivacyClass.P3_USER_EPHEMERAL,
        provenance=Provenance.DERIVED,
        bilingual=BilingualTag.NOT_APPLICABLE,
        unit=Unit.KRW,
        nullable=True,
        default=None,
    )

    def __post_init__(self) -> None:
        self._validate_field_contracts()
        _coerce_enum_attr(self, "module", FimModule)
        _coerce_enum_attr(self, "exposure_type", ExposureType)
        _validate_bool(self.is_user_input_required, "is_user_input_required")
        self.assumptions = _validate_text_tuple(self.assumptions, "assumptions")
        self.low, self.base, self.high = _validate_optional_money_range(
            self.low, self.base, self.high, "monetary exposure"
        )
        if self.is_user_input_required:
            _require(
                self.low is None and self.base is None and self.high is None,
                "required user input must leave exposure range blank",
            )
        if self.uncertainty_flags is not None:
            self.uncertainty_flags = _validate_text_tuple(
                self.uncertainty_flags, "uncertainty_flags"
            )
        if self.nominal_amount is not None:
            self.nominal_amount = _coerce_nonnegative_decimal(
                self.nominal_amount, "nominal_amount"
            )


@dataclass
class TimeExposure(SchemaModel):
    measured_analysis_runtime_seconds: float = schema_field(
        privacy=PrivacyClass.P1_INTERNAL,
        provenance=Provenance.DERIVED,
        bilingual=BilingualTag.NOT_APPLICABLE,
        unit=Unit.SECONDS,
    )
    estimated_human_review_minutes: float = schema_field(
        privacy=PrivacyClass.P3_USER_EPHEMERAL,
        provenance=Provenance.DERIVED,
        bilingual=BilingualTag.NOT_APPLICABLE,
        unit=Unit.MINUTES,
    )
    pathway_label: PathwayLabel = schema_field(
        privacy=PrivacyClass.P3_USER_EPHEMERAL,
        provenance=Provenance.DERIVED,
        bilingual=BilingualTag.KO_EN,
    )
    payment_due_days: int | None = schema_field(
        privacy=PrivacyClass.P3_USER_EPHEMERAL,
        provenance=Provenance.EXTRACTOR,
        bilingual=BilingualTag.NOT_APPLICABLE,
        unit=Unit.DAYS,
        nullable=True,
        default=None,
    )
    payment_delay_days: int | None = schema_field(
        privacy=PrivacyClass.P3_USER_EPHEMERAL,
        provenance=Provenance.EXTRACTOR_USER,
        bilingual=BilingualTag.NOT_APPLICABLE,
        unit=Unit.DAYS,
        nullable=True,
        default=None,
    )
    contract_duration_months: int | None = schema_field(
        privacy=PrivacyClass.P3_USER_EPHEMERAL,
        provenance=Provenance.EXTRACTOR,
        bilingual=BilingualTag.NOT_APPLICABLE,
        unit=Unit.MONTHS,
        nullable=True,
        default=None,
    )
    renewal_duration_months: int | None = schema_field(
        privacy=PrivacyClass.P3_USER_EPHEMERAL,
        provenance=Provenance.EXTRACTOR,
        bilingual=BilingualTag.NOT_APPLICABLE,
        unit=Unit.MONTHS,
        nullable=True,
        default=None,
    )
    exclusivity_duration_months: int | None = schema_field(
        privacy=PrivacyClass.P3_USER_EPHEMERAL,
        provenance=Provenance.EXTRACTOR,
        bilingual=BilingualTag.NOT_APPLICABLE,
        unit=Unit.MONTHS,
        nullable=True,
        default=None,
    )
    termination_notice_days: int | None = schema_field(
        privacy=PrivacyClass.P3_USER_EPHEMERAL,
        provenance=Provenance.EXTRACTOR,
        bilingual=BilingualTag.NOT_APPLICABLE,
        unit=Unit.DAYS,
        nullable=True,
        default=None,
    )
    estimated_months_to_recoup: float | None = schema_field(
        privacy=PrivacyClass.P3_USER_EPHEMERAL,
        provenance=Provenance.DERIVED,
        bilingual=BilingualTag.NOT_APPLICABLE,
        unit=Unit.MONTHS,
        nullable=True,
        default=None,
    )

    def __post_init__(self) -> None:
        self._validate_field_contracts()
        _validate_float_attr(self, "measured_analysis_runtime_seconds", minimum=0.0)
        _validate_float_attr(self, "estimated_human_review_minutes", minimum=0.0)
        _coerce_enum_attr(self, "pathway_label", PathwayLabel)
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
                _require(_is_nonnegative_int(value), f"{name} must be >= 0")
        if self.estimated_months_to_recoup is not None:
            self.estimated_months_to_recoup = _coerce_nonnegative_float(
                self.estimated_months_to_recoup, "estimated_months_to_recoup"
            )


@dataclass
class ConfidenceBreakdown(SchemaModel):
    ocr_confidence: float = schema_field(
        privacy=PrivacyClass.P3_USER_EPHEMERAL,
        provenance=Provenance.OCR,
        bilingual=BilingualTag.NOT_APPLICABLE,
        unit=Unit.FRAC,
    )
    evidence_confidence: float = schema_field(
        privacy=PrivacyClass.P3_USER_EPHEMERAL,
        provenance=Provenance.DERIVED,
        bilingual=BilingualTag.NOT_APPLICABLE,
        unit=Unit.FRAC,
    )
    data_completeness: float = schema_field(
        privacy=PrivacyClass.P3_USER_EPHEMERAL,
        provenance=Provenance.DERIVED,
        bilingual=BilingualTag.NOT_APPLICABLE,
        unit=Unit.FRAC,
    )
    overall_confidence: float = schema_field(
        privacy=PrivacyClass.P3_USER_EPHEMERAL,
        provenance=Provenance.DERIVED,
        bilingual=BilingualTag.NOT_APPLICABLE,
        unit=Unit.FRAC,
    )
    drivers: tuple[str, ...] = schema_field(
        privacy=PrivacyClass.P3_USER_EPHEMERAL,
        provenance=Provenance.DERIVED,
        bilingual=BilingualTag.KO_EN,
    )

    def __post_init__(self) -> None:
        self._validate_field_contracts()
        for name in (
            "ocr_confidence",
            "evidence_confidence",
            "data_completeness",
            "overall_confidence",
        ):
            _validate_float_attr(self, name, minimum=0.0, maximum=1.0)
        self.drivers = _validate_text_tuple(self.drivers, "drivers")


@dataclass
class DocumentAssessment(SchemaModel):
    document_id: str = schema_field(
        privacy=PrivacyClass.P3_USER_EPHEMERAL,
        provenance=Provenance.DERIVED,
        bilingual=BilingualTag.NOT_APPLICABLE,
    )
    review_priority_score: int = schema_field(
        privacy=PrivacyClass.P3_USER_EPHEMERAL,
        provenance=Provenance.DERIVED,
        bilingual=BilingualTag.NOT_APPLICABLE,
    )
    category_scores: dict[RiskCategory, float] = schema_field(
        privacy=PrivacyClass.P3_USER_EPHEMERAL,
        provenance=Provenance.DERIVED,
        bilingual=BilingualTag.NOT_APPLICABLE,
    )
    clause_assessments: tuple[ClauseAssessment, ...] = schema_field(
        privacy=PrivacyClass.P3_USER_EPHEMERAL,
        provenance=Provenance.DERIVED,
        bilingual=BilingualTag.NOT_APPLICABLE,
    )
    monetary_exposures: tuple[MonetaryExposureEstimate, ...] = schema_field(
        privacy=PrivacyClass.P3_USER_EPHEMERAL,
        provenance=Provenance.DERIVED,
        bilingual=BilingualTag.NOT_APPLICABLE,
    )
    time_exposure: TimeExposure = schema_field(
        privacy=PrivacyClass.P3_USER_EPHEMERAL,
        provenance=Provenance.DERIVED,
        bilingual=BilingualTag.NOT_APPLICABLE,
    )
    confidence: ConfidenceBreakdown = schema_field(
        privacy=PrivacyClass.P3_USER_EPHEMERAL,
        provenance=Provenance.DERIVED,
        bilingual=BilingualTag.NOT_APPLICABLE,
    )
    scoring_config_version: str = schema_field(
        privacy=PrivacyClass.P1_INTERNAL,
        provenance=Provenance.CONFIG,
        bilingual=BilingualTag.NOT_APPLICABLE,
    )
    missing_protections: tuple[str, ...] | None = schema_field(
        privacy=PrivacyClass.P3_USER_EPHEMERAL,
        provenance=Provenance.DERIVED,
        bilingual=BilingualTag.KO_EN,
        nullable=True,
        default=None,
    )

    def __post_init__(self) -> None:
        self._validate_field_contracts()
        _validate_uuid_text(self.document_id, "document_id")
        _validate_score_int(self.review_priority_score, "review_priority_score")
        self.category_scores = _validate_category_scores(self.category_scores, "category_scores")
        self.clause_assessments = _coerce_tuple(self.clause_assessments, "clause_assessments")
        for assessment in self.clause_assessments:
            _require_type(assessment, ClauseAssessment, "clause_assessments")
        self.monetary_exposures = _coerce_tuple(self.monetary_exposures, "monetary_exposures")
        for exposure in self.monetary_exposures:
            _require_type(exposure, MonetaryExposureEstimate, "monetary_exposures")
        _require_type(self.time_exposure, TimeExposure, "time_exposure")
        _require_type(self.confidence, ConfidenceBreakdown, "confidence")
        _require_nonblank(self.scoring_config_version, "scoring_config_version")
        if self.missing_protections is not None:
            self.missing_protections = _validate_text_tuple(
                self.missing_protections, "missing_protections"
            )


@dataclass
class AnalysisReport(SchemaModel):
    report_id: str = schema_field(
        privacy=PrivacyClass.P3_USER_EPHEMERAL,
        provenance=Provenance.DERIVED,
        bilingual=BilingualTag.NOT_APPLICABLE,
    )
    request_id: str = schema_field(
        privacy=PrivacyClass.P3_USER_EPHEMERAL,
        provenance=Provenance.DERIVED,
        bilingual=BilingualTag.NOT_APPLICABLE,
    )
    assessment: DocumentAssessment = schema_field(
        privacy=PrivacyClass.P3_USER_EPHEMERAL,
        provenance=Provenance.DERIVED,
        bilingual=BilingualTag.NOT_APPLICABLE,
    )
    disclaimers: tuple[str, ...] = schema_field(
        privacy=PrivacyClass.P0_PUBLIC,
        provenance=Provenance.CONFIG,
        bilingual=BilingualTag.KO_EN,
    )
    generated_text_flag: bool = schema_field(
        privacy=PrivacyClass.P1_INTERNAL,
        provenance=Provenance.DERIVED,
        bilingual=BilingualTag.NOT_APPLICABLE,
    )
    execution_path: dict[str, Any] = schema_field(
        privacy=PrivacyClass.P1_INTERNAL,
        provenance=Provenance.DERIVED,
        bilingual=BilingualTag.NOT_APPLICABLE,
        default_factory=default_execution_path,
    )
    contains_raw_image: bool = schema_field(
        privacy=PrivacyClass.P3_USER_EPHEMERAL,
        provenance=Provenance.CONFIG,
        bilingual=BilingualTag.NOT_APPLICABLE,
        default=False,
    )
    exported_at: datetime | None = schema_field(
        privacy=PrivacyClass.P3_USER_EPHEMERAL,
        provenance=Provenance.DERIVED,
        bilingual=BilingualTag.NOT_APPLICABLE,
        nullable=True,
        default=None,
    )
    export_format: ExportFormat | None = schema_field(
        privacy=PrivacyClass.P1_INTERNAL,
        provenance=Provenance.USER,
        bilingual=BilingualTag.NOT_APPLICABLE,
        nullable=True,
        default=None,
    )

    def __post_init__(self) -> None:
        self._validate_field_contracts()
        _require_nonblank(self.report_id, "report_id")
        _validate_uuid_text(self.request_id, "request_id")
        _require_type(self.assessment, DocumentAssessment, "assessment")
        self.disclaimers = _validate_nonempty_text_tuple(self.disclaimers, "disclaimers")
        normalized = " ".join(self.disclaimers).lower().replace("-", " ")
        _require("review priority" in normalized, "disclaimers must frame review priority")
        _require("not legal advice" in normalized, "disclaimers must include not legal advice")
        _validate_bool(self.generated_text_flag, "generated_text_flag")
        _validate_execution_path(self.execution_path)
        _validate_bool(self.contains_raw_image, "contains_raw_image")
        if self.exported_at is not None:
            _coerce_datetime_attr(self, "exported_at")
        if self.export_format is not None:
            _coerce_enum_attr(self, "export_format", ExportFormat)


@dataclass
class HumanCorrection(SchemaModel):
    correction_id: str = schema_field(
        privacy=PrivacyClass.P3_USER_EPHEMERAL,
        provenance=Provenance.DERIVED,
        bilingual=BilingualTag.NOT_APPLICABLE,
    )
    target_type: TargetType = schema_field(
        privacy=PrivacyClass.P3_USER_EPHEMERAL,
        provenance=Provenance.USER,
        bilingual=BilingualTag.NOT_APPLICABLE,
    )
    target_id: str = schema_field(
        privacy=PrivacyClass.P3_USER_EPHEMERAL,
        provenance=Provenance.USER,
        bilingual=BilingualTag.NOT_APPLICABLE,
    )
    before: str = schema_field(
        privacy=PrivacyClass.P3_USER_EPHEMERAL,
        provenance=Provenance.USER,
        bilingual=BilingualTag.KO_PRIMARY,
    )
    after: str = schema_field(
        privacy=PrivacyClass.P3_USER_EPHEMERAL,
        provenance=Provenance.USER,
        bilingual=BilingualTag.KO_PRIMARY,
    )
    created_at: datetime = schema_field(
        privacy=PrivacyClass.P3_USER_EPHEMERAL,
        provenance=Provenance.DERIVED,
        bilingual=BilingualTag.NOT_APPLICABLE,
    )
    counts_for_review_estimate: bool = schema_field(
        privacy=PrivacyClass.P1_INTERNAL,
        provenance=Provenance.DERIVED,
        bilingual=BilingualTag.NOT_APPLICABLE,
    )

    def __post_init__(self) -> None:
        self._validate_field_contracts()
        _require_nonblank(self.correction_id, "correction_id")
        _coerce_enum_attr(self, "target_type", TargetType)
        _require_nonblank(self.target_id, "target_id")
        _require(isinstance(self.before, str), "before must be str")
        _require(isinstance(self.after, str), "after must be str")
        _coerce_datetime_attr(self, "created_at")
        _validate_bool(self.counts_for_review_estimate, "counts_for_review_estimate")


@dataclass
class EvaluationExample(SchemaModel):
    example_id: str = schema_field(
        privacy=PrivacyClass.P1_INTERNAL,
        provenance=Provenance.DATASET,
        bilingual=BilingualTag.CANONICAL,
    )
    split: Split = schema_field(
        privacy=PrivacyClass.P1_INTERNAL,
        provenance=Provenance.DATASET,
        bilingual=BilingualTag.NOT_APPLICABLE,
    )
    dataset_ref: str = schema_field(
        privacy=PrivacyClass.P1_INTERNAL,
        provenance=Provenance.DATASET,
        bilingual=BilingualTag.NOT_APPLICABLE,
    )
    input_kind: InputKind = schema_field(
        privacy=PrivacyClass.P1_INTERNAL,
        provenance=Provenance.DATASET,
        bilingual=BilingualTag.NOT_APPLICABLE,
    )
    is_synthetic: bool = schema_field(
        privacy=PrivacyClass.P1_INTERNAL,
        provenance=Provenance.DATASET,
        bilingual=BilingualTag.NOT_APPLICABLE,
    )
    is_benign: bool = schema_field(
        privacy=PrivacyClass.P1_INTERNAL,
        provenance=Provenance.DATASET,
        bilingual=BilingualTag.NOT_APPLICABLE,
    )
    gold: dict[str, Any] = schema_field(
        privacy=PrivacyClass.P1_INTERNAL,
        provenance=Provenance.DATASET,
        bilingual=BilingualTag.KO_PRIMARY,
    )
    public_export: bool = schema_field(
        privacy=PrivacyClass.P1_INTERNAL,
        provenance=Provenance.DATASET,
        bilingual=BilingualTag.NOT_APPLICABLE,
    )

    def __post_init__(self) -> None:
        self._validate_field_contracts()
        _require_nonblank(self.example_id, "example_id")
        _coerce_enum_attr(self, "split", Split)
        _require(DATASET_REF_RE.match(self.dataset_ref) is not None, "dataset_ref must be DR-N")
        _coerce_enum_attr(self, "input_kind", InputKind)
        _validate_bool(self.is_synthetic, "is_synthetic")
        _validate_bool(self.is_benign, "is_benign")
        _validate_bool(self.public_export, "public_export")
        _require(self.is_synthetic, "evaluation examples must be synthetic")
        _require(isinstance(self.gold, dict), "gold must be a dict")


@dataclass
class ExperimentResult(SchemaModel):
    experiment_id: str = schema_field(
        privacy=PrivacyClass.P1_INTERNAL,
        provenance=Provenance.DERIVED,
        bilingual=BilingualTag.NOT_APPLICABLE,
    )
    config_hash: str = schema_field(
        privacy=PrivacyClass.P1_INTERNAL,
        provenance=Provenance.DERIVED,
        bilingual=BilingualTag.NOT_APPLICABLE,
    )
    arm: ExperimentArm = schema_field(
        privacy=PrivacyClass.P1_INTERNAL,
        provenance=Provenance.CONFIG,
        bilingual=BilingualTag.NOT_APPLICABLE,
    )
    metric: str = schema_field(
        privacy=PrivacyClass.P1_INTERNAL,
        provenance=Provenance.CONFIG,
        bilingual=BilingualTag.NOT_APPLICABLE,
    )
    value: float = schema_field(
        privacy=PrivacyClass.P1_INTERNAL,
        provenance=Provenance.DERIVED,
        bilingual=BilingualTag.NOT_APPLICABLE,
    )
    split: Split = schema_field(
        privacy=PrivacyClass.P1_INTERNAL,
        provenance=Provenance.CONFIG,
        bilingual=BilingualTag.NOT_APPLICABLE,
    )
    result_status: ResultStatus = schema_field(
        privacy=PrivacyClass.P1_INTERNAL,
        provenance=Provenance.DERIVED,
        bilingual=BilingualTag.NOT_APPLICABLE,
    )
    artifact_path: str | None = schema_field(
        privacy=PrivacyClass.P1_INTERNAL,
        provenance=Provenance.DERIVED,
        bilingual=BilingualTag.NOT_APPLICABLE,
        nullable=True,
        default=None,
    )
    reviewer: str | None = schema_field(
        privacy=PrivacyClass.P1_INTERNAL,
        provenance=Provenance.USER,
        bilingual=BilingualTag.NOT_APPLICABLE,
        nullable=True,
        default=None,
    )

    def __post_init__(self) -> None:
        self._validate_field_contracts()
        _require_nonblank(self.experiment_id, "experiment_id")
        _require(HEX_SHA256_RE.match(self.config_hash) is not None, "config_hash must be sha256")
        _coerce_enum_attr(self, "arm", ExperimentArm)
        _require_nonblank(self.metric, "metric")
        self.value = _coerce_float(self.value, "value")
        _coerce_enum_attr(self, "split", Split)
        _coerce_enum_attr(self, "result_status", ResultStatus)
        if self.result_status in {ResultStatus.PLANNED, ResultStatus.NA}:
            _require(self.value == 0.0, "planned/NA results must not carry measured values")
        if self.artifact_path is not None:
            _require_nonblank(self.artifact_path, "artifact_path")
        if self.reviewer is not None:
            _require_nonblank(self.reviewer, "reviewer")


SCHEMA_CLASSES: tuple[type[SchemaModel], ...] = (
    AnalysisRequest,
    UploadedDocument,
    OCRPage,
    OCRSpan,
    Clause,
    ExtractedFinancialTerms,
    EvidenceRecord,
    RiskSignal,
    ClauseAssessment,
    FinancialScenarioInputs,
    MonetaryExposureEstimate,
    TimeExposure,
    ConfidenceBreakdown,
    DocumentAssessment,
    AnalysisReport,
    HumanCorrection,
    EvaluationExample,
    ExperimentResult,
)


def _serialize_dataclass(obj: SchemaModel, *, log_safe: bool) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for item in fields(obj):
        privacy = item.metadata["privacy"]
        if log_safe and privacy in LOG_EXCLUDED_PRIVACY:
            continue
        result[item.name] = _serialize_value(getattr(obj, item.name), log_safe=log_safe)
    return result


def _serialize_value(value: Any, *, log_safe: bool) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if is_dataclass(value) and isinstance(value, SchemaModel):
        return value.to_log_dict() if log_safe else value.to_dict()
    if isinstance(value, tuple | list):
        return [_serialize_value(item, log_safe=log_safe) for item in value]
    if isinstance(value, dict):
        return {
            _serialize_value(key, log_safe=log_safe): _serialize_value(item, log_safe=log_safe)
            for key, item in value.items()
        }
    return value


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise SchemaValidationError(message)


def _require_type(value: Any, expected: type[Any], name: str) -> None:
    if not isinstance(value, expected):
        raise SchemaValidationError(f"{name} must contain {expected.__name__}")


def _require_nonblank(value: object, name: str) -> None:
    _require(isinstance(value, str) and bool(value.strip()), f"{name} must be non-blank")


def _require_nonblank_text(value: object, name: str) -> str:
    _require_nonblank(value, name)
    return str(value)


def _validate_uuid_text(value: object, name: str) -> None:
    _require_nonblank(value, name)
    try:
        UUID(str(value))
    except ValueError as exc:
        raise SchemaValidationError(f"{name} must be a UUID string") from exc


def _coerce_enum_attr(obj: object, name: str, enum_cls: type[Enum]) -> None:
    setattr(obj, name, _coerce_enum(getattr(obj, name), enum_cls, name))


def _coerce_enum(value: object, enum_cls: type[Enum], name: str) -> Any:
    if isinstance(value, enum_cls):
        return value
    try:
        return enum_cls(value)  # type: ignore[call-arg]
    except ValueError as exc:
        valid_values = [item.value for item in enum_cls]
        raise SchemaValidationError(f"{name} must be one of {valid_values}") from exc


def _coerce_datetime_attr(obj: object, name: str) -> None:
    value = getattr(obj, name)
    if isinstance(value, datetime):
        return
    if isinstance(value, str):
        try:
            setattr(obj, name, datetime.fromisoformat(value))
            return
        except ValueError as exc:
            raise SchemaValidationError(f"{name} must be ISO-8601 datetime") from exc
    raise SchemaValidationError(f"{name} must be datetime")


def _validate_bool(value: object, name: str) -> None:
    _require(type(value) is bool, f"{name} must be bool")


def _coerce_tuple(value: object, name: str) -> tuple[Any, ...]:
    _require(isinstance(value, tuple | list), f"{name} must be a list/tuple")
    return tuple(value)


def _validate_text_tuple(value: object, name: str) -> tuple[str, ...]:
    values = _coerce_tuple(value, name)
    for item in values:
        _require_nonblank(item, name)
    return tuple(str(item) for item in values)


def _validate_nonempty_text_tuple(value: object, name: str) -> tuple[str, ...]:
    values = _validate_text_tuple(value, name)
    _require(len(values) >= 1, f"{name} must not be empty")
    return values


def _validate_execution_path(value: object) -> None:
    _require(isinstance(value, dict), "execution_path must be a mapping")
    _require(value.get("local_only") is True, "execution_path.local_only must be true")
    _require(
        value.get("remote_runtime_api_allowed") is False,
        "execution_path must not allow remote runtime API",
    )
    _require(
        value.get("runtime_download_allowed") is False,
        "execution_path must not allow runtime download",
    )
    _require_nonblank(value.get("execution_path_id"), "execution_path.execution_path_id")
    steps = value.get("steps")
    _require(isinstance(steps, list) and bool(steps), "execution_path.steps must be nonempty")
    for index, step in enumerate(steps):
        _require(isinstance(step, dict), f"execution_path.steps[{index}] must be a mapping")
        _require_nonblank(step.get("adapter"), f"execution_path.steps[{index}].adapter")
        _require_nonblank(
            step.get("execution_path"),
            f"execution_path.steps[{index}].execution_path",
        )
    model_status = value.get("model_status")
    _require(isinstance(model_status, dict), "execution_path.model_status must be a mapping")
    _require_nonblank(
        model_status.get("summary_status"),
        "execution_path.model_status.summary_status",
    )


def _coerce_enum_tuple(value: object, enum_cls: type[Enum], name: str) -> tuple[Any, ...]:
    values = _coerce_tuple(value, name)
    return tuple(_coerce_enum(item, enum_cls, name) for item in values)


def _is_nonnegative_int(value: object) -> bool:
    return type(value) is int and value >= 0


def _is_positive_int(value: object) -> bool:
    return type(value) is int and value > 0


def _coerce_decimal(value: object, name: str) -> Decimal:
    _require(type(value) is not bool, f"{name} must be numeric")
    try:
        decimal = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise SchemaValidationError(f"{name} must be decimal-compatible") from exc
    _require(decimal.is_finite(), f"{name} must be finite")
    return decimal


def _coerce_nonnegative_decimal(value: object, name: str) -> Decimal:
    decimal = _coerce_decimal(value, name)
    _require(decimal >= 0, f"{name} must be >= 0")
    return decimal


def _coerce_float(value: object, name: str) -> float:
    _require(type(value) is not bool, f"{name} must be numeric")
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise SchemaValidationError(f"{name} must be numeric") from exc
    _require(number == number and number not in {float("inf"), float("-inf")}, f"{name} finite")
    return number


def _coerce_nonnegative_float(value: object, name: str) -> float:
    number = _coerce_float(value, name)
    _require(number >= 0, f"{name} must be >= 0")
    return number


def _coerce_fraction(value: object, name: str) -> float:
    number = _coerce_float(value, name)
    _require(0.0 <= number <= 1.0, f"{name} must be in [0,1]")
    return number


def _validate_float_attr(
    obj: object, name: str, *, minimum: float | None = None, maximum: float | None = None
) -> None:
    number = _coerce_float(getattr(obj, name), name)
    if minimum is not None:
        _require(number >= minimum, f"{name} must be >= {minimum}")
    if maximum is not None:
        _require(number <= maximum, f"{name} must be <= {maximum}")
    setattr(obj, name, number)


def _is_nonnegative_number(value: object) -> bool:
    try:
        return _coerce_float(value, "number") >= 0
    except SchemaValidationError:
        return False


def _validate_optional_money_range(
    low: object, base: object, high: object, label: str
) -> tuple[Decimal | None, Decimal | None, Decimal | None]:
    values = (low, base, high)
    if all(value is None for value in values):
        return None, None, None
    _require(
        all(value is not None for value in values),
        f"{label} range must be all set or all null",
    )
    low_dec = _coerce_nonnegative_decimal(low, f"{label}.low")
    base_dec = _coerce_nonnegative_decimal(base, f"{label}.base")
    high_dec = _coerce_nonnegative_decimal(high, f"{label}.high")
    _require(low_dec <= base_dec <= high_dec, f"{label} must satisfy low <= base <= high")
    return low_dec, base_dec, high_dec


def _validate_score_int(value: object, name: str) -> None:
    _require(type(value) is int and 0 <= value <= 100, f"{name} must be int 0-100")


def _validate_category_scores(value: object, name: str) -> dict[RiskCategory, float]:
    _require(isinstance(value, dict), f"{name} must be a mapping")
    scores: dict[RiskCategory, float] = {}
    for raw_key, raw_value in value.items():  # type: ignore[union-attr]
        key = _coerce_enum(raw_key, RiskCategory, name)
        _require(key in FINANCIAL_RISK_CATEGORIES, f"{name} may include F1-F9 only")
        score = _coerce_float(raw_value, name)
        _require(0.0 <= score <= 100.0, f"{name} values must be 0-100")
        scores[key] = score
    _require(set(scores) == FINANCIAL_RISK_CATEGORIES, f"{name} must include every F1-F9")
    return scores


def _validate_bbox(bbox: object, name: str) -> None:
    _require(isinstance(bbox, dict), f"{name} must be dict")
    keys = {"x", "y", "w", "h"}
    _require(set(bbox) == keys, f"{name} must contain x,y,w,h")
    for key in keys:
        _require(_is_nonnegative_int(bbox[key]), f"{name}.{key} must be int >= 0")
    _require(bbox["w"] > 0 and bbox["h"] > 0, f"{name}.w/h must be > 0")


def _validate_bbox_within_page(
    bbox: dict[str, int], page_width: int, page_height: int, span_id: str
) -> None:
    _validate_bbox(bbox, f"{span_id}.bbox")
    _require(bbox["x"] + bbox["w"] <= page_width, f"{span_id}.bbox exceeds page width")
    _require(bbox["y"] + bbox["h"] <= page_height, f"{span_id}.bbox exceeds page height")


def _validate_secondary_right(row: object, idx: int) -> None:
    _require(isinstance(row, dict), f"secondary_rights[{idx}] must be dict")
    _require(set(row) == {"type", "value", "prob"}, f"secondary_rights[{idx}] keys")
    _require_nonblank(row["type"], f"secondary_rights[{idx}].type")
    _coerce_nonnegative_decimal(row["value"], f"secondary_rights[{idx}].value")
    _coerce_fraction(row["prob"], f"secondary_rights[{idx}].prob")


def _word_count(text: str) -> int:
    return len([token for token in text.split() if token])

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from fink.schemas import Clause, ExtractedFinancialTerms, OCRPage, OCRSpan, Unit

MetricValue = Decimal | int | float | None

NUMBER_PATTERN = r"(?:\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)"
RANGE_SEP_PATTERN = r"(?:~|\u2013|-|\bto\b|\bthrough\b|부터|에서)"

MONEY_UNIT_PATTERN = r"(?:억\s*원|만\s*원|천\s*원|원|KRW|krw|won)"
MONEY_SUFFIX_RE = re.compile(
    rf"(?P<number>{NUMBER_PATTERN})\s*(?P<unit>{MONEY_UNIT_PATTERN})",
    re.IGNORECASE,
)
MONEY_PREFIX_RE = re.compile(
    rf"(?P<unit>KRW|krw|\u20a9)\s*(?P<number>{NUMBER_PATTERN})",
    re.IGNORECASE,
)
MONEY_MULTIPLIER_RE = re.compile(
    rf"(?P<number>{NUMBER_PATTERN})\s*"
    r"(?P<multiplier>thousand|million|billion)\s*(?:KRW|krw|won)",
    re.IGNORECASE,
)
MONEY_RANGE_RE = re.compile(
    rf"(?P<low>{NUMBER_PATTERN})\s*{RANGE_SEP_PATTERN}\s*"
    rf"(?P<high>{NUMBER_PATTERN})\s*(?P<unit>{MONEY_UNIT_PATTERN})",
    re.IGNORECASE,
)

PERCENT_RE = re.compile(
    rf"(?P<number>{NUMBER_PATTERN})\s*(?:%|percent|per\s+cent|퍼센트|프로)",
    re.IGNORECASE,
)
PERCENT_RANGE_RE = re.compile(
    rf"(?P<low>{NUMBER_PATTERN})\s*{RANGE_SEP_PATTERN}\s*"
    rf"(?P<high>{NUMBER_PATTERN})\s*(?:%|percent|per\s+cent|퍼센트|프로)",
    re.IGNORECASE,
)

DURATION_RANGE_RE = re.compile(
    rf"(?P<low>{NUMBER_PATTERN})\s*{RANGE_SEP_PATTERN}\s*"
    rf"(?P<high>{NUMBER_PATTERN})\s*"
    r"(?P<unit>business\s+days?|days?|months?|years?|영업일|일|개월|년)",
    re.IGNORECASE,
)
DAY_RE = re.compile(
    rf"(?P<number>{NUMBER_PATTERN})\s*(?P<unit>business\s+days?|days?|영업일|일)"
    r"(?=\s|$|[.,;:)\\\]]|[가-힣])",
    re.IGNORECASE,
)
MONTH_RE = re.compile(
    rf"(?P<number>{NUMBER_PATTERN})\s*(?P<unit>months?|개월)"
    r"(?=\s|$|[.,;:)\\\]]|[가-힣])",
    re.IGNORECASE,
)
YEAR_RE = re.compile(
    rf"(?P<number>{NUMBER_PATTERN})\s*(?P<unit>years?|년)"
    r"(?=\s|$|[.,;:)\\\]]|[가-힣])",
    re.IGNORECASE,
)

DATE_KO_RE = re.compile(
    r"(?P<year>(?:19|20)\d{2})\s*년\s*"
    r"(?P<month>\d{1,2})\s*월\s*(?P<day>\d{1,2})\s*일"
)
DATE_NUMERIC_RE = re.compile(
    r"(?P<year>(?:19|20)\d{2})[./-](?P<month>\d{1,2})[./-](?P<day>\d{1,2})"
)
MONTH_NAMES = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}
MONTH_ALT = "|".join(sorted(MONTH_NAMES, key=len, reverse=True))
DATE_MONTH_NAME_RE = re.compile(
    rf"\b(?P<month>{MONTH_ALT})\.?\s+(?P<day>\d{{1,2}})(?:,\s*|\s+)"
    r"(?P<year>(?:19|20)\d{2})\b",
    re.IGNORECASE,
)
DATE_DAY_MONTH_NAME_RE = re.compile(
    rf"\b(?P<day>\d{{1,2}})\s+(?P<month>{MONTH_ALT})\.?\s+"
    r"(?P<year>(?:19|20)\d{2})\b",
    re.IGNORECASE,
)
DATE_INCOMPLETE_KO_RE = re.compile(
    r"(?P<year>(?:19|20)\d{2})\s*년\s*(?P<month>\d{1,2})\s*월"
    r"(?:\s*(?:중|말|초|경))"
)
DATE_INCOMPLETE_EN_RE = re.compile(
    rf"\b(?P<month>{MONTH_ALT})\.?\s+(?P<year>(?:19|20)\d{{2}})\b",
    re.IGNORECASE,
)

OPAQUE_CONTEXT_RE = re.compile(
    r"(?<![가-힣])약\s*\d|내외|대략|추정|별도\s*(?:정|합의|협의)|"
    r"회사.{0,12}(?:정하는|정한|재량)|"
    r"기타|그\s*밖|등|actual\s+costs?|as\s+determined|to\s+be\s+determined|"
    r"including\s+but\s+not\s+limited|etc\.?|approximately|about|around|"
    r"at\s+least|or\s+more|or\s+less|more\s+than|less\s+than|이상|초과|미만",
    re.IGNORECASE,
)
OPAQUE_PHRASE_RE = re.compile(
    r"(?:기타|그\s*밖|등)[^.。;\n]{0,40}(?:비용|공제|수수료)|"
    r"(?:비용|수수료|공제\s*항목)[^.。;\n]{0,40}(?:별도|협의|회사.{0,12}정)|"
    r"(?:other|additional)[^.。;\n]{0,40}(?:fees|costs|deductions|expenses)|"
    r"(?:fees|costs|deductions|expenses)[^.。;\n]{0,40}"
    r"(?:as\s+determined|to\s+be\s+determined)",
    re.IGNORECASE,
)

MONEY_CONTEXT_RULES = (
    (re.compile(r"minimum\s+guarantee|미니멈|개런티|\bMG\b", re.IGNORECASE), "MINIMUM_GUARANTEE"),
    (re.compile(r"advance|선급금|선불", re.IGNORECASE), "ADVANCE_AMOUNT"),
    (re.compile(r"liability\s+cap|책임\s*상한|손해배상\s*한도", re.IGNORECASE), "LIABILITY_CAP"),
    (re.compile(r"penalt|위약금|손해배상", re.IGNORECASE), "PENALTY_AMOUNT"),
    (re.compile(r"net\s+sales|순매출", re.IGNORECASE), "NET_SALES"),
    (re.compile(r"refund|환불", re.IGNORECASE), "REFUNDS"),
    (re.compile(r"marketing|마케팅", re.IGNORECASE), "MARKETING_COST"),
    (re.compile(r"fixed\s+fee|원고료|고정\s*금|정산금", re.IGNORECASE), "FIXED_FEE"),
    (re.compile(r"gross\s+sales|총매출|매출", re.IGNORECASE), "GROSS_SALES"),
)
PERCENT_CONTEXT_RULES = (
    (
        re.compile(r"translation|번역", re.IGNORECASE),
        "TRANSLATION_RIGHTS_SHARE",
    ),
    (
        re.compile(r"secondary\s+rights?|2차|이차|부가\s*권리", re.IGNORECASE),
        "SECONDARY_RIGHTS_SHARE",
    ),
    (re.compile(r"tax|withholding|원천징수", re.IGNORECASE), "TAX_WITHHOLDING"),
    (
        re.compile(r"payment\s+processing|결제\s*수수료", re.IGNORECASE),
        "PAYMENT_PROCESSING_FEE",
    ),
    (re.compile(r"platform|플랫폼", re.IGNORECASE), "PLATFORM_FEE"),
    (re.compile(r"deduct|공제", re.IGNORECASE), "DEDUCTION_RATE"),
    (re.compile(r"recoup|회수", re.IGNORECASE), "RECOUPMENT_RATE"),
    (
        re.compile(r"revenue\s+share|creator\s+receives|수익\s*배분|배분율|작가\s*몫", re.IGNORECASE),
        "REVENUE_SHARE_RATE",
    ),
)
DAY_CONTEXT_RULES = (
    (re.compile(r"delay|late|지연|연체", re.IGNORECASE), "PAYMENT_DELAY_DAYS"),
    (re.compile(r"termination|notice|해지|통지", re.IGNORECASE), "TERMINATION_NOTICE_DAYS"),
    (re.compile(r"payment|due|지급|기일", re.IGNORECASE), "PAYMENT_DUE_DAYS"),
)
MONTH_CONTEXT_RULES = (
    (re.compile(r"renew|갱신|연장", re.IGNORECASE), "RENEWAL_DURATION_MONTHS"),
    (re.compile(r"exclusive|독점", re.IGNORECASE), "EXCLUSIVITY_DURATION_MONTHS"),
    (re.compile(r"contract|term|기간|계약", re.IGNORECASE), "CONTRACT_DURATION_MONTHS"),
)
DATE_CONTEXT_RULES = (
    (re.compile(r"payment|due|지급|기일", re.IGNORECASE), "PAYMENT_DUE_DATE"),
    (re.compile(r"termination|해지", re.IGNORECASE), "TERMINATION_DATE"),
    (re.compile(r"effective|시행|효력|발효", re.IGNORECASE), "EFFECTIVE_DATE"),
)

METRIC_IDS = {
    "money": "EV-EXACT-MONEY",
    "pct": "EV-EXACT-PCT",
    "date": "EV-EXACT-DATE",
    "duration": "EV-EXACT-DUR",
}


@dataclass(frozen=True)
class _DetectedTerm:
    start: int
    end: int
    feature_id: str
    value_raw: str
    unit: Unit
    value_norm: MetricValue
    is_open_ended: bool
    confidence_scale: float = 1.0


@dataclass(frozen=True)
class ExpectedFinancialTerm:
    """Gold target used by the EV-EXACT harness on synthetic fixtures."""

    feature_id: str
    value_norm: MetricValue
    unit: Unit | str
    is_open_ended: bool = False
    kind: str | None = None


@dataclass(frozen=True)
class ExactMatchMetric:
    metric_id: str
    matched_count: int
    gold_count: int
    predicted_count: int
    precision: float
    recall: float
    f1: float
    exact_match_accuracy: float

    @property
    def value(self) -> float:
        return self.exact_match_accuracy

    def as_dict(self) -> dict[str, int | float | str]:
        return {
            "metric_id": self.metric_id,
            "value": self.value,
            "matched_count": self.matched_count,
            "gold_count": self.gold_count,
            "predicted_count": self.predicted_count,
            "precision": self.precision,
            "recall": self.recall,
            "f1": self.f1,
            "exact_match_accuracy": self.exact_match_accuracy,
        }


@dataclass(frozen=True)
class ExactMatchReport:
    metrics: dict[str, ExactMatchMetric]

    @property
    def ev_exact_money(self) -> float:
        return self.metrics["EV-EXACT-MONEY"].value

    @property
    def ev_exact_pct(self) -> float:
        return self.metrics["EV-EXACT-PCT"].value

    @property
    def ev_exact_date(self) -> float:
        return self.metrics["EV-EXACT-DATE"].value

    @property
    def ev_exact_dur(self) -> float:
        return self.metrics["EV-EXACT-DUR"].value

    def as_dict(self) -> dict[str, dict[str, int | float | str]]:
        return {metric_id: metric.as_dict() for metric_id, metric in self.metrics.items()}


class FinancialTermExtractor:
    """Rule-based financial-term extractor over segmented clauses or OCR pages."""

    def extract_from_clauses(
        self, clauses: Sequence[Clause]
    ) -> tuple[ExtractedFinancialTerms, ...]:
        terms: list[ExtractedFinancialTerms] = []
        for clause in clauses:
            terms.extend(
                _extract_terms_from_text_block(
                    clause.text_ko,
                    clause_id=clause.clause_id,
                    source_span_ids=clause.source_span_ids,
                    confidence=clause.seg_confidence,
                )
            )
        return tuple(terms)

    def extract_from_pages(self, pages: Sequence[OCRPage]) -> tuple[ExtractedFinancialTerms, ...]:
        terms: list[ExtractedFinancialTerms] = []
        for page in sorted(pages, key=lambda item: item.page_index):
            for span in page.spans:
                text = _span_text(span)
                terms.extend(
                    _extract_terms_from_text_block(
                        text,
                        clause_id=f"clause-preview-{_slug_id(span.span_id)}",
                        source_span_ids=(span.span_id,),
                        confidence=span.confidence,
                    )
                )
        return tuple(terms)

    def extract_from_text(
        self,
        text: str,
        *,
        clause_id: str = "clause-text",
        source_span_ids: Sequence[str] = ("text",),
        confidence: float = 1.0,
    ) -> tuple[ExtractedFinancialTerms, ...]:
        return _extract_terms_from_text_block(
            text,
            clause_id=clause_id,
            source_span_ids=tuple(source_span_ids),
            confidence=confidence,
        )


def extract_terms_from_clauses(
    clauses: Sequence[Clause],
) -> tuple[ExtractedFinancialTerms, ...]:
    return FinancialTermExtractor().extract_from_clauses(clauses)


def extract_terms_from_pages(pages: Sequence[OCRPage]) -> tuple[ExtractedFinancialTerms, ...]:
    return FinancialTermExtractor().extract_from_pages(pages)


def extract_terms_from_text(
    text: str,
    *,
    clause_id: str = "clause-text",
    source_span_ids: Sequence[str] = ("text",),
    confidence: float = 1.0,
) -> tuple[ExtractedFinancialTerms, ...]:
    return FinancialTermExtractor().extract_from_text(
        text,
        clause_id=clause_id,
        source_span_ids=source_span_ids,
        confidence=confidence,
    )


def evaluate_exact_matches(
    gold_terms: Sequence[ExpectedFinancialTerm | ExtractedFinancialTerms | Mapping[str, Any]],
    predicted_terms: Sequence[ExpectedFinancialTerm | ExtractedFinancialTerms | Mapping[str, Any]],
) -> ExactMatchReport:
    metrics: dict[str, ExactMatchMetric] = {}
    for kind, metric_id in METRIC_IDS.items():
        gold_counter = Counter(
            _metric_key(term) for term in gold_terms if _term_kind(term) == kind
        )
        predicted_counter = Counter(
            _metric_key(term) for term in predicted_terms if _term_kind(term) == kind
        )
        matched = sum(
            min(gold_count, predicted_counter.get(key, 0))
            for key, gold_count in gold_counter.items()
        )
        gold_count = sum(gold_counter.values())
        predicted_count = sum(predicted_counter.values())
        if predicted_count:
            precision = matched / predicted_count
        else:
            precision = 1.0 if gold_count == 0 else 0.0
        if gold_count:
            recall = matched / gold_count
        else:
            recall = 1.0 if predicted_count == 0 else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        denominator = max(gold_count, predicted_count)
        exact_match_accuracy = matched / denominator if denominator else 1.0
        metrics[metric_id] = ExactMatchMetric(
            metric_id=metric_id,
            matched_count=matched,
            gold_count=gold_count,
            predicted_count=predicted_count,
            precision=precision,
            recall=recall,
            f1=f1,
            exact_match_accuracy=exact_match_accuracy,
        )
    return ExactMatchReport(metrics=metrics)


def exact_match_harness(
    gold_terms: Sequence[ExpectedFinancialTerm | ExtractedFinancialTerms | Mapping[str, Any]],
    predicted_terms: Sequence[ExpectedFinancialTerm | ExtractedFinancialTerms | Mapping[str, Any]],
) -> ExactMatchReport:
    return evaluate_exact_matches(gold_terms, predicted_terms)


def _extract_terms_from_text_block(
    text: str,
    *,
    clause_id: str,
    source_span_ids: Sequence[str],
    confidence: float,
) -> tuple[ExtractedFinancialTerms, ...]:
    if not isinstance(text, str) or not text.strip():
        return ()
    if not clause_id.strip():
        raise ValueError("clause_id must be nonblank")
    span_ids = tuple(source_span_ids)
    if not span_ids or any(not str(item).strip() for item in span_ids):
        raise ValueError("source_span_ids must be nonempty")

    detected = _detect_terms(text)
    terms: list[ExtractedFinancialTerms] = []
    for index, item in enumerate(detected):
        value_norm = None if item.is_open_ended else item.value_norm
        terms.append(
            ExtractedFinancialTerms(
                term_id=f"term-{_slug_id(clause_id)}-{item.feature_id.lower()}-{index}",
                clause_id=clause_id,
                feature_id=item.feature_id,
                value_raw=item.value_raw,
                unit=item.unit,
                is_open_ended=item.is_open_ended,
                extraction_confidence=_clamp_confidence(confidence * item.confidence_scale),
                source_span_ids=span_ids,
                value_norm=value_norm,
            )
        )
    return tuple(terms)


def _detect_terms(text: str) -> tuple[_DetectedTerm, ...]:
    candidates: list[_DetectedTerm] = []
    blocked_spans: list[tuple[int, int]] = []
    date_spans: list[tuple[int, int]] = []

    for match in _iter_exact_date_matches(text):
        value_norm, is_open_ended = _normalized_date(match)
        candidates.append(
            _DetectedTerm(
                match.start(),
                match.end(),
                _feature_from_context(
                    text,
                    match.start(),
                    match.end(),
                    DATE_CONTEXT_RULES,
                    "CONTRACT_DATE",
                ),
                match.group(0).strip(),
                Unit.NONE,
                value_norm,
                is_open_ended,
                0.95 if is_open_ended else 1.0,
            )
        )
        date_spans.append((match.start(), match.end()))

    for match in _iter_incomplete_date_matches(text):
        if _overlaps_any((match.start(), match.end()), date_spans):
            continue
        candidates.append(
            _DetectedTerm(
                match.start(),
                match.end(),
                _feature_from_context(
                    text,
                    match.start(),
                    match.end(),
                    DATE_CONTEXT_RULES,
                    "CONTRACT_DATE",
                ),
                match.group(0).strip(),
                Unit.NONE,
                None,
                True,
                0.85,
            )
        )
        date_spans.append((match.start(), match.end()))

    for match in MONEY_RANGE_RE.finditer(text):
        candidates.append(
            _open_range_term(
                text,
                match,
                _feature_from_context(
                    text,
                    match.start(),
                    match.end(),
                    MONEY_CONTEXT_RULES,
                    "GROSS_SALES",
                ),
                Unit.KRW,
            )
        )
        blocked_spans.append((match.start(), match.end()))

    for match in PERCENT_RANGE_RE.finditer(text):
        candidates.append(
            _open_range_term(
                text,
                match,
                _feature_from_context(
                    text,
                    match.start(),
                    match.end(),
                    PERCENT_CONTEXT_RULES,
                    "REVENUE_SHARE_RATE",
                ),
                Unit.FRAC,
            )
        )
        blocked_spans.append((match.start(), match.end()))

    for match in DURATION_RANGE_RE.finditer(text):
        if _overlaps_any((match.start(), match.end()), date_spans):
            continue
        unit = _duration_unit(match.group("unit"))
        rules = MONTH_CONTEXT_RULES if unit is Unit.MONTHS else DAY_CONTEXT_RULES
        default = "CONTRACT_DURATION_MONTHS" if unit is Unit.MONTHS else "PAYMENT_DUE_DAYS"
        candidates.append(
            _open_range_term(
                text,
                match,
                _feature_from_context(text, match.start(), match.end(), rules, default),
                unit,
            )
        )
        blocked_spans.append((match.start(), match.end()))

    for match in MONEY_MULTIPLIER_RE.finditer(text):
        if _overlaps_any((match.start(), match.end()), blocked_spans):
            continue
        value = _money_value_with_multiplier(match.group("number"), match.group("multiplier"))
        candidates.append(
            _numeric_term(
                text,
                match,
                _feature_from_context(
                    text,
                    match.start(),
                    match.end(),
                    MONEY_CONTEXT_RULES,
                    "GROSS_SALES",
                ),
                Unit.KRW,
                value,
            )
        )

    for pattern in (MONEY_PREFIX_RE, MONEY_SUFFIX_RE):
        for match in pattern.finditer(text):
            if _overlaps_any((match.start(), match.end()), blocked_spans):
                continue
            value = _money_value(match.group("number"), match.group("unit"))
            candidates.append(
                _numeric_term(
                    text,
                    match,
                    _feature_from_context(
                        text,
                        match.start(),
                        match.end(),
                        MONEY_CONTEXT_RULES,
                        "GROSS_SALES",
                    ),
                    Unit.KRW,
                    value,
                )
            )

    for match in PERCENT_RE.finditer(text):
        if _overlaps_any((match.start(), match.end()), blocked_spans):
            continue
        value = _percent_value(match.group("number"))
        candidates.append(
            _numeric_term(
                text,
                match,
                _feature_from_context(
                    text,
                    match.start(),
                    match.end(),
                    PERCENT_CONTEXT_RULES,
                    "REVENUE_SHARE_RATE",
                ),
                Unit.FRAC,
                value,
            )
        )

    for pattern in (DAY_RE, MONTH_RE, YEAR_RE):
        for match in pattern.finditer(text):
            span = (match.start(), match.end())
            if _overlaps_any(span, blocked_spans) or _overlaps_any(span, date_spans):
                continue
            unit = _duration_unit(match.group("unit"))
            rules = MONTH_CONTEXT_RULES if unit is Unit.MONTHS else DAY_CONTEXT_RULES
            default = "CONTRACT_DURATION_MONTHS" if unit is Unit.MONTHS else "PAYMENT_DUE_DAYS"
            value = _duration_value(match.group("number"), match.group("unit"))
            candidates.append(
                _numeric_term(
                    text,
                    match,
                    _feature_from_context(text, match.start(), match.end(), rules, default),
                    unit,
                    value,
                )
            )

    for match in OPAQUE_PHRASE_RE.finditer(text):
        span = (match.start(), match.end())
        if _overlaps_any(span, [(item.start, item.end) for item in candidates]):
            continue
        candidates.append(
            _DetectedTerm(
                match.start(),
                match.end(),
                "OPEN_ENDED_NUMERIC_TERMS",
                match.group(0).strip(),
                Unit.NONE,
                None,
                True,
                0.75,
            )
        )

    return tuple(sorted(candidates, key=lambda item: (item.start, item.end, item.feature_id)))


def _iter_exact_date_matches(text: str) -> tuple[re.Match[str], ...]:
    matches: list[re.Match[str]] = []
    for pattern in (DATE_KO_RE, DATE_NUMERIC_RE, DATE_MONTH_NAME_RE, DATE_DAY_MONTH_NAME_RE):
        matches.extend(pattern.finditer(text))
    return tuple(sorted(matches, key=lambda item: (item.start(), item.end())))


def _iter_incomplete_date_matches(text: str) -> tuple[re.Match[str], ...]:
    matches: list[re.Match[str]] = []
    for pattern in (DATE_INCOMPLETE_KO_RE, DATE_INCOMPLETE_EN_RE):
        matches.extend(pattern.finditer(text))
    return tuple(sorted(matches, key=lambda item: (item.start(), item.end())))


def _normalized_date(match: re.Match[str]) -> tuple[int | None, bool]:
    try:
        year = int(match.group("year"))
        day = int(match.group("day"))
        month_raw = match.group("month")
        month = (
            MONTH_NAMES[month_raw.lower()]
            if month_raw.lower() in MONTH_NAMES
            else int(month_raw)
        )
        return int(date(year, month, day).strftime("%Y%m%d")), False
    except (KeyError, TypeError, ValueError):
        return None, True


def _open_range_term(
    text: str,
    match: re.Match[str],
    feature_id: str,
    unit: Unit,
) -> _DetectedTerm:
    return _DetectedTerm(
        match.start(),
        match.end(),
        feature_id,
        match.group(0).strip(),
        unit,
        None,
        True,
        0.85,
    )


def _numeric_term(
    text: str,
    match: re.Match[str],
    feature_id: str,
    unit: Unit,
    value_norm: Decimal | float,
) -> _DetectedTerm:
    is_open_ended = _is_opaque_value(text, match.start(), match.end(), unit, value_norm)
    return _DetectedTerm(
        match.start(),
        match.end(),
        feature_id,
        match.group(0).strip(),
        unit,
        None if is_open_ended else value_norm,
        is_open_ended,
        0.85 if is_open_ended else 1.0,
    )


def _feature_from_context(
    text: str,
    start: int,
    end: int,
    rules: Sequence[tuple[re.Pattern[str], str]],
    default: str,
) -> str:
    context = _context_window(text, start, end, before=72, after=72)
    for pattern, feature_id in rules:
        if pattern.search(context):
            return feature_id
    return default


def _is_opaque_value(
    text: str,
    start: int,
    end: int,
    unit: Unit,
    value_norm: Decimal | float,
) -> bool:
    if unit is Unit.FRAC:
        try:
            fraction = Decimal(str(value_norm))
        except InvalidOperation:
            return True
        if fraction < Decimal("0") or fraction > Decimal("1"):
            return True
    return OPAQUE_CONTEXT_RE.search(_context_window(text, start, end)) is not None


def _context_window(
    text: str,
    start: int,
    end: int,
    *,
    before: int = 40,
    after: int = 40,
) -> str:
    return text[max(0, start - before) : min(len(text), end + after)]


def _money_value(number: str, unit: str) -> Decimal:
    normalized_unit = re.sub(r"\s+", "", unit).lower()
    multipliers = {
        "원": Decimal("1"),
        "krw": Decimal("1"),
        "won": Decimal("1"),
        "\u20a9": Decimal("1"),
        "천원": Decimal("1000"),
        "만원": Decimal("10000"),
        "억원": Decimal("100000000"),
    }
    multiplier = multipliers.get(normalized_unit, Decimal("1"))
    return (_decimal_number(number) * multiplier).normalize()


def _money_value_with_multiplier(number: str, multiplier: str) -> Decimal:
    multipliers = {
        "thousand": Decimal("1000"),
        "million": Decimal("1000000"),
        "billion": Decimal("1000000000"),
    }
    return (_decimal_number(number) * multipliers[multiplier.lower()]).normalize()


def _percent_value(number: str) -> Decimal:
    return (_decimal_number(number) / Decimal("100")).normalize()


def _duration_value(number: str, unit: str) -> float:
    value = _decimal_number(number)
    normalized_unit = unit.strip().lower()
    if normalized_unit in {"년", "year", "years"}:
        value *= Decimal("12")
    return float(value)


def _duration_unit(unit: str) -> Unit:
    normalized = unit.strip().lower()
    if normalized in {"개월", "month", "months", "년", "year", "years"}:
        return Unit.MONTHS
    return Unit.DAYS


def _decimal_number(value: str) -> Decimal:
    return Decimal(value.replace(",", "").strip())


def _metric_key(
    term: ExpectedFinancialTerm | ExtractedFinancialTerms | Mapping[str, Any],
) -> tuple[str, str, str | None, bool]:
    return (
        _term_feature_id(term),
        _term_unit(term).value,
        _metric_value(_term_value_norm(term)),
        _term_is_open_ended(term),
    )


def _term_kind(
    term: ExpectedFinancialTerm | ExtractedFinancialTerms | Mapping[str, Any],
) -> str | None:
    explicit_kind = _term_optional_attr(term, "kind")
    if explicit_kind is not None:
        return str(explicit_kind)
    unit = _term_unit(term)
    feature_id = _term_feature_id(term)
    if unit is Unit.KRW:
        return "money"
    if unit is Unit.FRAC:
        return "pct"
    if unit in {Unit.DAYS, Unit.MONTHS}:
        return "duration"
    if "DATE" in feature_id:
        return "date"
    return None


def _metric_value(value: MetricValue) -> str | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return str(value.normalize())
    return str(Decimal(str(value)).normalize())


def _term_feature_id(
    term: ExpectedFinancialTerm | ExtractedFinancialTerms | Mapping[str, Any],
) -> str:
    return str(_term_attr(term, "feature_id"))


def _term_unit(
    term: ExpectedFinancialTerm | ExtractedFinancialTerms | Mapping[str, Any],
) -> Unit:
    unit = _term_attr(term, "unit")
    if isinstance(unit, Unit):
        return unit
    return Unit(str(unit))


def _term_value_norm(
    term: ExpectedFinancialTerm | ExtractedFinancialTerms | Mapping[str, Any],
) -> MetricValue:
    value = _term_attr(term, "value_norm")
    if value is None or isinstance(value, Decimal | int | float):
        return value
    return Decimal(str(value))


def _term_is_open_ended(
    term: ExpectedFinancialTerm | ExtractedFinancialTerms | Mapping[str, Any],
) -> bool:
    return bool(_term_attr(term, "is_open_ended"))


def _term_attr(
    term: ExpectedFinancialTerm | ExtractedFinancialTerms | Mapping[str, Any],
    name: str,
) -> Any:
    if isinstance(term, Mapping):
        return term[name]
    return getattr(term, name)


def _term_optional_attr(
    term: ExpectedFinancialTerm | ExtractedFinancialTerms | Mapping[str, Any],
    name: str,
) -> Any | None:
    if isinstance(term, Mapping):
        return term.get(name)
    return getattr(term, name, None)


def _overlaps_any(span: tuple[int, int], spans: Sequence[tuple[int, int]]) -> bool:
    start, end = span
    return any(
        start < existing_end and end > existing_start
        for existing_start, existing_end in spans
    )


def _span_text(span: OCRSpan) -> str:
    return span.corrected_text if span.corrected_text is not None else span.text


def _slug_id(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "-", value).strip("-").lower()
    return slug or "item"


def _clamp_confidence(value: float) -> float:
    return min(max(float(value), 0.0), 1.0)

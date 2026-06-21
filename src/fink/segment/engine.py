from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Sequence

from fink.schemas import Clause, OCRPage, OCRSpan


ARTICLE_RE = re.compile(
    r"^\s*(?:"
    r"제\s*\d+\s*조(?:\s*[({（][^)}）]+[)}）])?"
    r"|(?:Article|Section|Clause)\s+\d+[A-Za-z0-9_.-]*"
    r")\b",
    re.IGNORECASE,
)
SUBCLAUSE_RE = re.compile(
    r"^\s*(?:"
    r"[①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳]"
    r"|\(\s*\d+\s*\)"
    r"|\(\s*[A-Za-z가-힣]\s*\)"
    r"|\d+(?:\.\d+)*[.)]"
    r"|[A-Za-z가-힣][.)]"
    r")\s+"
)


@dataclass(frozen=True)
class BoundaryMarker:
    """Detected marker at the beginning of a clause-like line."""

    kind: str
    text: str


@dataclass(frozen=True)
class _LogicalLine:
    text: str
    source_span_ids: tuple[str, ...]
    confidence: float
    marker: BoundaryMarker | None
    page_index: int
    y_center: float


@dataclass(frozen=True)
class SegmentationMetrics:
    """EV-SEG boundary metric for synthetic/sanitized segmentation fixtures."""

    ev_seg: float
    boundary_precision: float
    boundary_recall: float
    boundary_f1: float
    gold_boundary_count: int
    predicted_boundary_count: int
    matched_boundary_count: int
    tolerance: int = 0

    @property
    def ev_seg_boundary_f1(self) -> float:
        return self.boundary_f1


class ClauseSegmenter:
    """Rule-based clause and sub-clause segmenter over OCR spans.

    The segmenter starts a new clause when a reconstructed OCR line begins with
    a Korean article marker, an English article/section marker, or a common
    numbered/lettered sub-clause marker. Lines without markers continue the
    current clause, preserving source span provenance.
    """

    def __init__(self, *, clause_id_prefix: str = "clause") -> None:
        if not clause_id_prefix.strip():
            raise ValueError("clause_id_prefix must be nonblank")
        self.clause_id_prefix = clause_id_prefix.strip()

    def segment_pages(self, pages: Sequence[OCRPage]) -> tuple[Clause, ...]:
        lines = _logical_lines_from_pages(pages)
        if not lines:
            return ()

        groups: list[list[_LogicalLine]] = []
        current: list[_LogicalLine] = []
        for line in lines:
            starts_new_clause = line.marker is not None and current
            if starts_new_clause:
                groups.append(current)
                current = [line]
            else:
                current.append(line)
        if current:
            groups.append(current)

        return tuple(
            _clause_from_lines(
                group,
                clause_index=idx,
                clause_id=f"{self.clause_id_prefix}-{idx + 1}",
            )
            for idx, group in enumerate(groups)
        )


def segment_pages(
    pages: Sequence[OCRPage], *, clause_id_prefix: str = "clause"
) -> tuple[Clause, ...]:
    """Segment OCR pages into Clause records with source span provenance."""

    return ClauseSegmenter(clause_id_prefix=clause_id_prefix).segment_pages(pages)


def boundary_indices_from_clauses(
    clauses: Sequence[Clause | Sequence[str]], span_order: Sequence[str]
) -> tuple[int, ...]:
    """Return clause-start boundary indices after the first clause.

    Boundaries are expressed as source-span positions in `span_order`, which
    makes the metric independent of private contract text.
    """

    span_positions = {span_id: idx for idx, span_id in enumerate(span_order)}
    boundaries: list[int] = []
    for clause in clauses[1:]:
        source_span_ids = _clause_source_span_ids(clause)
        first_span_id = source_span_ids[0]
        if first_span_id not in span_positions:
            raise ValueError(f"source span id is missing from span_order: {first_span_id}")
        boundaries.append(span_positions[first_span_id])
    return tuple(boundaries)


def evaluate_clause_segmentation(
    gold_clauses: Sequence[Clause | Sequence[str]],
    predicted_clauses: Sequence[Clause | Sequence[str]],
    *,
    span_order: Sequence[str],
    tolerance: int = 0,
) -> SegmentationMetrics:
    """Compute EV-SEG over gold and predicted clause source-span groups."""

    return evaluate_segmentation(
        boundary_indices_from_clauses(gold_clauses, span_order),
        boundary_indices_from_clauses(predicted_clauses, span_order),
        tolerance=tolerance,
    )


def evaluate_segmentation(
    gold_boundaries: Sequence[int],
    predicted_boundaries: Sequence[int],
    *,
    tolerance: int = 0,
) -> SegmentationMetrics:
    """Compute windowed boundary F1 for EV-SEG.

    A predicted boundary matches a gold boundary when its source-span position
    is within `tolerance`. Each predicted boundary can match at most one gold
    boundary.
    """

    if tolerance < 0:
        raise ValueError("tolerance must be >= 0")
    gold = _validate_boundaries(gold_boundaries, "gold_boundaries")
    predicted = list(_validate_boundaries(predicted_boundaries, "predicted_boundaries"))

    matched = 0
    for gold_boundary in gold:
        match_idx = _nearest_boundary_index(gold_boundary, predicted, tolerance)
        if match_idx is not None:
            matched += 1
            predicted.pop(match_idx)

    gold_count = len(gold)
    predicted_count = len(predicted_boundaries)
    if gold_count == 0 and predicted_count == 0:
        precision = 1.0
        recall = 1.0
    else:
        precision = matched / predicted_count if predicted_count else 0.0
        recall = matched / gold_count if gold_count else 0.0
    boundary_f1 = (
        2 * precision * recall / (precision + recall) if precision + recall else 0.0
    )
    return SegmentationMetrics(
        ev_seg=boundary_f1,
        boundary_precision=precision,
        boundary_recall=recall,
        boundary_f1=boundary_f1,
        gold_boundary_count=gold_count,
        predicted_boundary_count=predicted_count,
        matched_boundary_count=matched,
        tolerance=tolerance,
    )


def _logical_lines_from_pages(pages: Sequence[OCRPage]) -> tuple[_LogicalLine, ...]:
    lines: list[_LogicalLine] = []
    for page in sorted(pages, key=lambda item: item.page_index):
        for spans in _span_lines(page):
            text = " ".join(_span_text(span).strip() for span in spans if _span_text(span).strip())
            if not text:
                continue
            confidence = sum(span.confidence for span in spans) / len(spans)
            source_span_ids = tuple(span.span_id for span in spans)
            lines.append(
                _LogicalLine(
                    text=text,
                    source_span_ids=source_span_ids,
                    confidence=confidence,
                    marker=_detect_boundary_marker(text),
                    page_index=page.page_index,
                    y_center=sum(_span_y_center(span) for span in spans) / len(spans),
                )
            )
    return tuple(lines)


def _span_lines(page: OCRPage) -> tuple[tuple[OCRSpan, ...], ...]:
    spans = sorted(page.spans, key=lambda span: (_span_y_center(span), span.bbox["x"]))
    lines: list[list[OCRSpan]] = []
    centers: list[float] = []
    heights: list[float] = []

    for span in spans:
        if not _span_text(span).strip():
            continue
        center = _span_y_center(span)
        height = max(float(span.bbox["h"]), 1.0)
        target_idx = _nearest_line_index(center, height, centers, heights)
        if target_idx is None:
            lines.append([span])
            centers.append(center)
            heights.append(height)
            continue

        lines[target_idx].append(span)
        centers[target_idx] = sum(_span_y_center(item) for item in lines[target_idx]) / len(
            lines[target_idx]
        )
        heights[target_idx] = sum(float(item.bbox["h"]) for item in lines[target_idx]) / len(
            lines[target_idx]
        )

    return tuple(tuple(sorted(line, key=lambda span: span.bbox["x"])) for line in lines)


def _nearest_line_index(
    center: float, height: float, centers: Sequence[float], heights: Sequence[float]
) -> int | None:
    best_idx: int | None = None
    best_distance: float | None = None
    for idx, existing_center in enumerate(centers):
        threshold = max(8.0, min(height, heights[idx]) * 0.65)
        distance = abs(center - existing_center)
        if distance <= threshold and (best_distance is None or distance < best_distance):
            best_idx = idx
            best_distance = distance
    return best_idx


def _clause_from_lines(lines: Sequence[_LogicalLine], *, clause_index: int, clause_id: str) -> Clause:
    text = "\n".join(line.text for line in lines).strip()
    source_span_ids = tuple(
        span_id
        for line in lines
        for span_id in line.source_span_ids
    )
    marker_score = 1.0 if lines[0].marker is not None else 0.55
    mean_confidence = sum(line.confidence for line in lines) / len(lines)
    seg_confidence = _clamp_float((mean_confidence * 0.85) + (marker_score * 0.15))
    return Clause(
        clause_id=clause_id,
        clause_index=clause_index,
        text_ko=text,
        source_span_ids=source_span_ids,
        seg_confidence=seg_confidence,
        heading_ko=lines[0].text if lines[0].marker is not None else None,
    )


def _detect_boundary_marker(text: str) -> BoundaryMarker | None:
    article = ARTICLE_RE.match(text)
    if article is not None:
        return BoundaryMarker(kind="article", text=article.group(0).strip())
    subclause = SUBCLAUSE_RE.match(text)
    if subclause is not None:
        return BoundaryMarker(kind="subclause", text=subclause.group(0).strip())
    return None


def _clause_source_span_ids(clause: Clause | Sequence[str]) -> tuple[str, ...]:
    if isinstance(clause, Clause):
        return clause.source_span_ids
    if isinstance(clause, str):
        raise TypeError("clause source spans must be a sequence, not str")
    source_span_ids = tuple(clause)
    if not source_span_ids:
        raise ValueError("clause source spans must be nonempty")
    return source_span_ids


def _validate_boundaries(boundaries: Sequence[int], name: str) -> tuple[int, ...]:
    validated: list[int] = []
    for boundary in boundaries:
        if not isinstance(boundary, int) or boundary < 0:
            raise ValueError(f"{name} must contain nonnegative integers")
        validated.append(boundary)
    return tuple(sorted(set(validated)))


def _nearest_boundary_index(
    gold_boundary: int, predicted_boundaries: Sequence[int], tolerance: int
) -> int | None:
    best_idx: int | None = None
    best_distance: int | None = None
    for idx, predicted_boundary in enumerate(predicted_boundaries):
        distance = abs(predicted_boundary - gold_boundary)
        if distance <= tolerance and (best_distance is None or distance < best_distance):
            best_idx = idx
            best_distance = distance
    return best_idx


def _span_text(span: OCRSpan) -> str:
    return span.corrected_text if span.corrected_text is not None else span.text


def _span_y_center(span: OCRSpan) -> float:
    return float(span.bbox["y"]) + (float(span.bbox["h"]) / 2.0)


def _clamp_float(value: float) -> float:
    return min(max(float(value), 0.0), 1.0)

"""Clause segmentation helpers for FInk.

The public API consumes shared OCRPage/OCRSpan schema records and returns the
shared Clause schema. It is deterministic and local-only.
"""

from fink.segment.engine import (
    BoundaryMarker,
    ClauseSegmenter,
    SegmentationMetrics,
    boundary_indices_from_clauses,
    evaluate_clause_segmentation,
    evaluate_segmentation,
    segment_pages,
)

__all__ = [
    "BoundaryMarker",
    "ClauseSegmenter",
    "SegmentationMetrics",
    "boundary_indices_from_clauses",
    "evaluate_clause_segmentation",
    "evaluate_segmentation",
    "segment_pages",
]

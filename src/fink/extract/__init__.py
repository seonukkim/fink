"""Financial-term extraction for FInk clauses and OCR pages."""

from fink.extract.engine import (
    ExactMatchMetric,
    ExactMatchReport,
    ExpectedFinancialTerm,
    FinancialTermExtractor,
    evaluate_exact_matches,
    exact_match_harness,
    extract_terms_from_clauses,
    extract_terms_from_pages,
    extract_terms_from_text,
)

__all__ = [
    "ExactMatchMetric",
    "ExactMatchReport",
    "ExpectedFinancialTerm",
    "FinancialTermExtractor",
    "evaluate_exact_matches",
    "exact_match_harness",
    "extract_terms_from_clauses",
    "extract_terms_from_pages",
    "extract_terms_from_text",
]

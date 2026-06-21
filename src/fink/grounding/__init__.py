"""Authority-gated retrieval and grounding for FInk."""

from fink.grounding.authority import (
    AuthorityGroundingError,
    AuthorityRetrievedRecord,
    AuthorityRetrievalBundle,
    ConflictSet,
    SignalEligibility,
    authority_gated_retrieval,
    authority_tag_present,
    conflict_preserved_test,
    eligibility_gate_test,
    evaluate_signal_eligibility,
)

__all__ = [
    "AuthorityGroundingError",
    "AuthorityRetrievedRecord",
    "AuthorityRetrievalBundle",
    "ConflictSet",
    "SignalEligibility",
    "authority_gated_retrieval",
    "authority_tag_present",
    "conflict_preserved_test",
    "eligibility_gate_test",
    "evaluate_signal_eligibility",
]

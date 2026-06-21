"""Authority-gated retrieval and grounding for FInk."""

from fink.grounding.authority import (
    AuthorityGroundingError,
    AuthorityRetrievedRecord,
    AuthorityRetrievalBundle,
    ConflictSet,
    authority_gated_retrieval,
    authority_tag_present,
    conflict_preserved_test,
)

__all__ = [
    "AuthorityGroundingError",
    "AuthorityRetrievedRecord",
    "AuthorityRetrievalBundle",
    "ConflictSet",
    "authority_gated_retrieval",
    "authority_tag_present",
    "conflict_preserved_test",
]

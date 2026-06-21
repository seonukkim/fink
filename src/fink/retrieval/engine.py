from __future__ import annotations

import csv
import json
import math
import re
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


RETRIEVAL_INDEX_SCHEMA_VERSION = 1
DEFAULT_CORPUS_DIR = Path("data/corpus")
DEFAULT_INDEX_PATH = Path("indexes/retrieval_bm25.json")

EVIDENCE_PATH = Path("stage-1/14_MASTER_EVIDENCE_MATRIX.csv")
KNOWLEDGE_CARDS_PATH = Path("stage-1/15_MASTER_KNOWLEDGE_CARDS.jsonl")
CHECKLIST_PATH = Path("stage-1/11_MASTER_CREATOR_CHECKLIST.jsonl")
GLOSSARY_PATH = Path("stage-1/13_MASTER_BILINGUAL_GLOSSARY.csv")

SCORING_AUTHORITY_TIERS = frozenset({"A0", "A1", "A2"})
PRACTICE_AUTHORITY_TIERS = frozenset({"B", "C", "B/C"})
AUTHORITY_SORT_ORDER = {
    "A0": 0,
    "A1": 1,
    "A2": 2,
    "B": 3,
    "C": 4,
    "B/C": 5,
    "D0": 6,
    "M1": 7,
    "M2": 8,
    "M3": 9,
    "R0": 10,
}

TOKEN_RE = re.compile(r"[A-Za-z0-9]+|[가-힣]+")
HANGUL_RE = re.compile(r"^[가-힣]+$")


class RetrievalCorpusError(RuntimeError):
    """Raised when local retrieval corpus records are missing or malformed."""


@dataclass(frozen=True)
class RetrievalChunk:
    """One local retrieval chunk with hierarchy, provenance, and authority metadata."""

    chunk_id: str
    chunk_type: str
    text: str
    title: str = ""
    source_id: str = ""
    source_ids: tuple[str, ...] = ()
    source_class: str = ""
    authority_tier: str = ""
    verification_status: str = "UNVERIFIED"
    risk_categories: tuple[str, ...] = ()
    canonical_id: str = ""
    non_equivalence_caveat: str = ""
    parent_id: str = ""
    hierarchy: tuple[str, ...] = ()
    score_eligible: bool = False
    practice_reference: bool = False
    public_export: bool = False
    generated_translation: bool = False
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.chunk_id.strip():
            raise RetrievalCorpusError("chunk_id must be nonblank")
        if not self.chunk_type.strip():
            raise RetrievalCorpusError(f"{self.chunk_id}: chunk_type must be nonblank")
        if not self.text.strip():
            raise RetrievalCorpusError(f"{self.chunk_id}: text must be nonblank")
        if self.score_eligible and self.authority_tier not in SCORING_AUTHORITY_TIERS:
            raise RetrievalCorpusError(
                f"{self.chunk_id}: score_eligible requires A0/A1/A2 authority"
            )
        if self.practice_reference and self.score_eligible:
            raise RetrievalCorpusError(
                f"{self.chunk_id}: practice references must not be score eligible"
            )
        if self.chunk_type == "glossary_term" and self.score_eligible:
            raise RetrievalCorpusError(
                f"{self.chunk_id}: glossary terms are aliases, not scoring evidence"
            )

    def as_dict(self) -> dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "chunk_type": self.chunk_type,
            "text": self.text,
            "title": self.title,
            "source_id": self.source_id,
            "source_ids": list(self.source_ids),
            "source_class": self.source_class,
            "authority_tier": self.authority_tier,
            "verification_status": self.verification_status,
            "risk_categories": list(self.risk_categories),
            "canonical_id": self.canonical_id,
            "non_equivalence_caveat": self.non_equivalence_caveat,
            "parent_id": self.parent_id,
            "hierarchy": list(self.hierarchy),
            "score_eligible": self.score_eligible,
            "practice_reference": self.practice_reference,
            "public_export": self.public_export,
            "generated_translation": self.generated_translation,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> RetrievalChunk:
        return cls(
            chunk_id=str(payload["chunk_id"]),
            chunk_type=str(payload["chunk_type"]),
            text=str(payload["text"]),
            title=str(payload.get("title", "")),
            source_id=str(payload.get("source_id", "")),
            source_ids=_tuple_text(payload.get("source_ids", ())),
            source_class=str(payload.get("source_class", "")),
            authority_tier=str(payload.get("authority_tier", "")),
            verification_status=str(payload.get("verification_status", "UNVERIFIED")),
            risk_categories=_tuple_text(payload.get("risk_categories", ())),
            canonical_id=str(payload.get("canonical_id", "")),
            non_equivalence_caveat=str(payload.get("non_equivalence_caveat", "")),
            parent_id=str(payload.get("parent_id", "")),
            hierarchy=_tuple_text(payload.get("hierarchy", ())),
            score_eligible=_to_bool(payload.get("score_eligible", False)),
            practice_reference=_to_bool(payload.get("practice_reference", False)),
            public_export=_to_bool(payload.get("public_export", False)),
            generated_translation=_to_bool(payload.get("generated_translation", False)),
            metadata=_mapping(payload.get("metadata", {})),
        )


@dataclass(frozen=True)
class RetrievalCorpus:
    """A local hierarchical corpus assembled from Stage-1 retrieval records."""

    documents: tuple[RetrievalChunk, ...]

    @property
    def counts_by_type(self) -> dict[str, int]:
        counts: Counter[str] = Counter(item.chunk_type for item in self.documents)
        return dict(sorted(counts.items()))

    @property
    def counts_by_authority_tier(self) -> dict[str, int]:
        counts: Counter[str] = Counter(item.authority_tier for item in self.documents)
        return dict(sorted(counts.items()))

    def as_dict(self) -> dict[str, Any]:
        return {
            "counts_by_type": self.counts_by_type,
            "counts_by_authority_tier": self.counts_by_authority_tier,
            "documents": [item.as_dict() for item in self.documents],
        }


@dataclass(frozen=True)
class RetrievalResult:
    """A ranked BM25 retrieval result."""

    rank: int
    score: float
    chunk: RetrievalChunk
    matched_terms: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "rank": self.rank,
            "score": self.score,
            "matched_terms": list(self.matched_terms),
            "chunk": self.chunk.as_dict(),
        }


@dataclass(frozen=True)
class RetrievalCase:
    """One synthetic/sanitized retrieval-gold item for EV-R@k."""

    query_id: str
    query: str
    relevant_chunk_ids: tuple[str, ...]
    risk_categories: tuple[str, ...] = ()
    chunk_types: tuple[str, ...] = ()
    authority_tiers: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.query_id.strip():
            raise ValueError("query_id must be nonblank")
        if not self.query.strip():
            raise ValueError(f"{self.query_id}: query must be nonblank")
        if not self.relevant_chunk_ids:
            raise ValueError(f"{self.query_id}: relevant_chunk_ids must not be empty")


@dataclass(frozen=True)
class RetrievalRecallMetrics:
    """Document/chunk Recall@k metrics for local retrieval evaluation."""

    k_values: tuple[int, ...]
    total_cases: int
    hits_at_k: Mapping[int, int]
    recall_at_k: Mapping[int, float]
    per_query: tuple[dict[str, Any], ...]

    @property
    def ev_r_at_3(self) -> float | None:
        return self.recall_at_k.get(3)

    @property
    def ev_r_at_5(self) -> float | None:
        return self.recall_at_k.get(5)

    def as_dict(self) -> dict[str, Any]:
        return {
            "total_cases": self.total_cases,
            "EV-R@3": self.ev_r_at_3,
            "EV-R@5": self.ev_r_at_5,
            "recall_at_k": {f"R@{key}": value for key, value in self.recall_at_k.items()},
            "hits_at_k": {f"hits@{key}": value for key, value in self.hits_at_k.items()},
            "per_query": list(self.per_query),
        }


@dataclass(frozen=True)
class BilingualQueryPair:
    """One KO/EN query pair for canonical-ID consistency evaluation."""

    query_id: str
    query_ko: str
    query_en: str
    expected_canonical_id: str = ""
    requires_non_equivalence_caveat: bool = False

    def __post_init__(self) -> None:
        if not self.query_id.strip():
            raise ValueError("query_id must be nonblank")
        if not self.query_ko.strip():
            raise ValueError(f"{self.query_id}: query_ko must be nonblank")
        if not self.query_en.strip():
            raise ValueError(f"{self.query_id}: query_en must be nonblank")


@dataclass(frozen=True)
class BilingualConsistencyMetrics:
    """EV-KOEN metrics for KO/EN canonical concept retrieval."""

    k: int
    total_pairs: int
    consistent_pairs: int
    top_k_consistent_pairs: int
    caveat_required_pairs: int
    caveat_present_pairs: int
    english_labeled_evidence_violations: int
    per_query: tuple[dict[str, Any], ...]

    @property
    def ev_koen(self) -> float | None:
        if self.total_pairs == 0:
            return None
        return self.consistent_pairs / self.total_pairs

    @property
    def top_k_consistency(self) -> float | None:
        if self.total_pairs == 0:
            return None
        return self.top_k_consistent_pairs / self.total_pairs

    @property
    def caveat_coverage(self) -> float | None:
        if self.caveat_required_pairs == 0:
            return None
        return self.caveat_present_pairs / self.caveat_required_pairs

    @property
    def english_never_labeled_evidence(self) -> bool:
        return self.english_labeled_evidence_violations == 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "k": self.k,
            "total_pairs": self.total_pairs,
            "EV-KOEN": self.ev_koen,
            "top_k_consistency": self.top_k_consistency,
            "caveat_coverage": self.caveat_coverage,
            "english_never_labeled_evidence": self.english_never_labeled_evidence,
            "english_labeled_evidence_violations": self.english_labeled_evidence_violations,
            "consistent_pairs": self.consistent_pairs,
            "top_k_consistent_pairs": self.top_k_consistent_pairs,
            "caveat_required_pairs": self.caveat_required_pairs,
            "caveat_present_pairs": self.caveat_present_pairs,
            "per_query": list(self.per_query),
        }


class LocalBM25Index:
    """Deterministic local keyword/BM25 retrieval index.

    The index is fully offline. It has no network, remote embedding, or cloud
    retrieval dependency; optional local embedding re-ranking can be layered on
    top by callers without changing the persisted BM25 corpus.
    """

    def __init__(
        self,
        documents: Sequence[RetrievalChunk],
        *,
        k1: float = 1.5,
        b: float = 0.75,
    ) -> None:
        if k1 <= 0:
            raise ValueError("k1 must be > 0")
        if not 0 <= b <= 1:
            raise ValueError("b must be between 0 and 1")
        self.documents = tuple(documents)
        if not self.documents:
            raise RetrievalCorpusError("cannot build an empty retrieval index")
        duplicate_ids = _duplicates(item.chunk_id for item in self.documents)
        if duplicate_ids:
            raise RetrievalCorpusError("duplicate chunk_id values: " + ", ".join(duplicate_ids))
        self.k1 = k1
        self.b = b
        self._tokens = tuple(tokenize(item.text) for item in self.documents)
        self._term_freqs = tuple(Counter(tokens) for tokens in self._tokens)
        self._doc_lengths = tuple(len(tokens) for tokens in self._tokens)
        self._avg_doc_length = sum(self._doc_lengths) / len(self._doc_lengths)
        self._doc_freqs = _document_frequencies(self._tokens)
        self._idf = {
            term: math.log(1 + (len(self.documents) - df + 0.5) / (df + 0.5))
            for term, df in self._doc_freqs.items()
        }

    @classmethod
    def from_corpus_dir(
        cls,
        corpus_dir: Path = DEFAULT_CORPUS_DIR,
        *,
        k1: float = 1.5,
        b: float = 0.75,
    ) -> LocalBM25Index:
        corpus = load_hierarchical_corpus(corpus_dir)
        return cls(corpus.documents, k1=k1, b=b)

    def query(
        self,
        query_text: str,
        *,
        k: int = 5,
        risk_categories: Sequence[str] = (),
        chunk_types: Sequence[str] = (),
        authority_tiers: Sequence[str] = (),
    ) -> tuple[RetrievalResult, ...]:
        if k <= 0:
            raise ValueError("k must be > 0")
        query_terms = tokenize(query_text)
        if not query_terms:
            return ()

        risk_filter = frozenset(risk_categories)
        type_filter = frozenset(chunk_types)
        tier_filter = frozenset(authority_tiers)
        unique_query_terms = tuple(dict.fromkeys(query_terms))
        results: list[tuple[float, RetrievalChunk, tuple[str, ...]]] = []

        for index, chunk in enumerate(self.documents):
            if risk_filter and not risk_filter.intersection(chunk.risk_categories):
                continue
            if type_filter and chunk.chunk_type not in type_filter:
                continue
            if tier_filter and chunk.authority_tier not in tier_filter:
                continue

            score = self._score(index, query_terms)
            if score <= 0:
                continue
            matched_terms = tuple(
                term for term in unique_query_terms if self._term_freqs[index].get(term, 0) > 0
            )
            results.append((score, chunk, matched_terms))

        results.sort(
            key=lambda item: (
                -item[0],
                AUTHORITY_SORT_ORDER.get(item[1].authority_tier, 99),
                item[1].chunk_id,
            )
        )
        return tuple(
            RetrievalResult(
                rank=rank,
                score=score,
                chunk=chunk,
                matched_terms=matched_terms,
            )
            for rank, (score, chunk, matched_terms) in enumerate(results[:k], start=1)
        )

    def save(self, path: Path = DEFAULT_INDEX_PATH) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": RETRIEVAL_INDEX_SCHEMA_VERSION,
            "index_type": "bm25",
            "k1": self.k1,
            "b": self.b,
            "documents": [item.as_dict() for item in self.documents],
        }
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return path

    @classmethod
    def load(cls, path: Path = DEFAULT_INDEX_PATH) -> LocalBM25Index:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("schema_version") != RETRIEVAL_INDEX_SCHEMA_VERSION:
            raise RetrievalCorpusError(f"{path}: unsupported retrieval index schema version")
        if payload.get("index_type") != "bm25":
            raise RetrievalCorpusError(f"{path}: unsupported retrieval index type")
        documents = tuple(RetrievalChunk.from_dict(item) for item in payload["documents"])
        return cls(documents, k1=float(payload.get("k1", 1.5)), b=float(payload.get("b", 0.75)))

    def _score(self, document_index: int, query_terms: Sequence[str]) -> float:
        term_freqs = self._term_freqs[document_index]
        doc_length = self._doc_lengths[document_index]
        denominator_adjustment = self.k1 * (
            1 - self.b + self.b * doc_length / self._avg_doc_length
        )
        score = 0.0
        for term, query_tf in Counter(query_terms).items():
            tf = term_freqs.get(term, 0)
            if tf <= 0:
                continue
            idf = self._idf.get(term, 0.0)
            score += query_tf * idf * (tf * (self.k1 + 1)) / (tf + denominator_adjustment)
        return score


def build_retrieval_index(corpus_dir: Path = DEFAULT_CORPUS_DIR) -> LocalBM25Index:
    """Build the local BM25 retrieval index from the Stage-1 corpus."""

    return LocalBM25Index.from_corpus_dir(corpus_dir)


def load_hierarchical_corpus(corpus_dir: Path = DEFAULT_CORPUS_DIR) -> RetrievalCorpus:
    """Load Stage-1 retrieval records into source/tier/risk/chunk hierarchy."""

    _require_files(corpus_dir, (EVIDENCE_PATH, KNOWLEDGE_CARDS_PATH, CHECKLIST_PATH, GLOSSARY_PATH))
    documents: list[RetrievalChunk] = []
    documents.extend(_evidence_chunks(corpus_dir / EVIDENCE_PATH))
    documents.extend(_knowledge_card_chunks(corpus_dir / KNOWLEDGE_CARDS_PATH))
    documents.extend(_checklist_chunks(corpus_dir / CHECKLIST_PATH))
    documents.extend(_glossary_chunks(corpus_dir / GLOSSARY_PATH))
    return RetrievalCorpus(documents=tuple(documents))


def evaluate_recall_at_k(
    index: LocalBM25Index,
    cases: Sequence[RetrievalCase],
    *,
    k_values: Sequence[int] = (3, 5),
) -> RetrievalRecallMetrics:
    """Compute EV-R@k over synthetic/sanitized retrieval-gold cases."""

    if not cases:
        raise ValueError("cases must not be empty")
    normalized_k = tuple(sorted({int(k) for k in k_values}))
    if not normalized_k or any(k <= 0 for k in normalized_k):
        raise ValueError("k_values must contain positive integers")

    max_k = max(normalized_k)
    hits: Counter[int] = Counter()
    per_query: list[dict[str, Any]] = []
    for case in cases:
        results = index.query(
            case.query,
            k=max_k,
            risk_categories=case.risk_categories,
            chunk_types=case.chunk_types,
            authority_tiers=case.authority_tiers,
        )
        ranked_ids = tuple(item.chunk.chunk_id for item in results)
        relevant = set(case.relevant_chunk_ids)
        row: dict[str, Any] = {
            "query_id": case.query_id,
            "ranked_chunk_ids": list(ranked_ids),
            "relevant_chunk_ids": list(case.relevant_chunk_ids),
        }
        for k in normalized_k:
            hit = bool(relevant.intersection(ranked_ids[:k]))
            if hit:
                hits[k] += 1
            row[f"hit@{k}"] = hit
        per_query.append(row)

    recall = {k: hits[k] / len(cases) for k in normalized_k}
    return RetrievalRecallMetrics(
        k_values=normalized_k,
        total_cases=len(cases),
        hits_at_k=dict(hits),
        recall_at_k=recall,
        per_query=tuple(per_query),
    )


def recall_harness(
    index: LocalBM25Index,
    cases: Sequence[RetrievalCase],
    *,
    k_values: Sequence[int] = (3, 5),
) -> RetrievalRecallMetrics:
    """Named machine-gate wrapper for EV-R@3/R@5 computation."""

    return evaluate_recall_at_k(index, cases, k_values=k_values)


def resolve_canonical_results(
    index: LocalBM25Index,
    query_text: str,
    *,
    k: int = 5,
) -> tuple[RetrievalResult, ...]:
    """Resolve a KO or EN query to unique glossary canonical IDs.

    Korean glossary text is the canonical concept surface. English labels and
    aliases are generated retrieval aids only, so this resolver restricts
    concept lookup to non-scoring glossary chunks.
    """

    if k <= 0:
        raise ValueError("k must be > 0")
    raw_results = index.query(
        query_text,
        k=len(index.documents),
        chunk_types=("glossary_term",),
    )
    seen: set[str] = set()
    selected: list[RetrievalResult] = []
    for result in raw_results:
        canonical_id = result.chunk.canonical_id.strip()
        if not canonical_id or canonical_id in seen:
            continue
        selected.append(result)
        seen.add(canonical_id)
        if len(selected) >= k:
            break
    return tuple(selected)


def resolve_canonical_ids(
    index: LocalBM25Index,
    query_text: str,
    *,
    k: int = 5,
) -> tuple[str, ...]:
    """Return top-k unique canonical IDs for a KO or EN query."""

    return tuple(
        result.chunk.canonical_id
        for result in resolve_canonical_results(index, query_text, k=k)
    )


def evaluate_koen_consistency(
    index: LocalBM25Index,
    pairs: Sequence[BilingualQueryPair],
    *,
    k: int = 1,
) -> BilingualConsistencyMetrics:
    """Compute EV-KOEN over synthetic/sanitized KO/EN paired queries."""

    if not pairs:
        raise ValueError("pairs must not be empty")
    if k <= 0:
        raise ValueError("k must be > 0")

    consistent_pairs = 0
    top_k_consistent_pairs = 0
    caveat_required_pairs = 0
    caveat_present_pairs = 0
    english_labeled_evidence_violations = 0
    per_query: list[dict[str, Any]] = []

    for pair in pairs:
        ko_results = resolve_canonical_results(index, pair.query_ko, k=k)
        en_results = resolve_canonical_results(index, pair.query_en, k=k)
        ko_ids = tuple(result.chunk.canonical_id for result in ko_results)
        en_ids = tuple(result.chunk.canonical_id for result in en_results)
        same_top1 = bool(ko_ids and en_ids and ko_ids[0] == en_ids[0])
        same_top_k = bool(ko_ids and ko_ids == en_ids)
        expected_ok = not pair.expected_canonical_id or (
            ko_ids[:1] == (pair.expected_canonical_id,)
            and en_ids[:1] == (pair.expected_canonical_id,)
        )
        pair_consistent = same_top1 and expected_ok
        if pair_consistent:
            consistent_pairs += 1
        if same_top_k:
            top_k_consistent_pairs += 1

        target_canonical_id = pair.expected_canonical_id or (ko_ids[0] if ko_ids else "")
        caveat_present = None
        if pair.requires_non_equivalence_caveat:
            caveat_required_pairs += 1
            target_chunks = tuple(
                result.chunk
                for result in (*ko_results, *en_results)
                if result.chunk.canonical_id == target_canonical_id
            )
            caveat_present = bool(target_chunks) and all(
                chunk.non_equivalence_caveat.strip() for chunk in target_chunks
            )
            if caveat_present:
                caveat_present_pairs += 1

        english_labeled_evidence = any(
            result.chunk.chunk_type == "evidence"
            or result.chunk.score_eligible
            or not result.chunk.generated_translation
            for result in en_results
        )
        if english_labeled_evidence:
            english_labeled_evidence_violations += 1

        per_query.append(
            {
                "query_id": pair.query_id,
                "query_ko": pair.query_ko,
                "query_en": pair.query_en,
                "expected_canonical_id": pair.expected_canonical_id,
                "ko_canonical_ids": list(ko_ids),
                "en_canonical_ids": list(en_ids),
                "same_top1": same_top1,
                "same_top_k": same_top_k,
                "consistent": pair_consistent,
                "requires_non_equivalence_caveat": pair.requires_non_equivalence_caveat,
                "non_equivalence_caveat_present": caveat_present,
                "english_labeled_evidence": english_labeled_evidence,
            }
        )

    return BilingualConsistencyMetrics(
        k=k,
        total_pairs=len(pairs),
        consistent_pairs=consistent_pairs,
        top_k_consistent_pairs=top_k_consistent_pairs,
        caveat_required_pairs=caveat_required_pairs,
        caveat_present_pairs=caveat_present_pairs,
        english_labeled_evidence_violations=english_labeled_evidence_violations,
        per_query=tuple(per_query),
    )


def koen_consistency_harness(
    index: LocalBM25Index,
    pairs: Sequence[BilingualQueryPair],
    *,
    k: int = 1,
) -> BilingualConsistencyMetrics:
    """Named machine-gate wrapper for EV-KOEN computation."""

    return evaluate_koen_consistency(index, pairs, k=k)


def retrieval_offline_test(
    corpus_dir: Path = DEFAULT_CORPUS_DIR,
    *,
    query: str = "정산 지급 revenue share payment",
) -> tuple[RetrievalResult, ...]:
    """Named machine-gate wrapper that builds and queries without network access."""

    return build_retrieval_index(corpus_dir).query(query, k=3)


def tokenize(text: str) -> tuple[str, ...]:
    """Tokenize Korean/English text for deterministic local keyword retrieval."""

    tokens: list[str] = []
    for match in TOKEN_RE.finditer(text.lower()):
        token = match.group(0)
        tokens.append(token)
        if HANGUL_RE.fullmatch(token):
            tokens.extend(_hangul_ngrams(token))
    return tuple(tokens)


def _evidence_chunks(path: Path) -> tuple[RetrievalChunk, ...]:
    chunks: list[RetrievalChunk] = []
    for row in _read_csv(path):
        evidence_id = _required_text(row, "evidence_id", path)
        source_id = _required_text(row, "source_id", path)
        authority_tier = _required_text(row, "authority_tier", path)
        risk_categories = _split_text(row.get("risk_categories", ""))
        score_eligible = _to_bool(row.get("score_eligible", False))
        text = _join_text(
            evidence_id,
            row.get("article_or_section"),
            row.get("page_or_slide"),
            row.get("short_source_excerpt"),
            row.get("financial_variables"),
            row.get("notes"),
            *risk_categories,
        )
        chunks.append(
            RetrievalChunk(
                chunk_id=evidence_id,
                chunk_type="evidence",
                title=_join_text(row.get("article_or_section"), row.get("page_or_slide")),
                text=text,
                source_id=source_id,
                source_ids=(source_id,),
                source_class=_required_text(row, "source_class", path),
                authority_tier=authority_tier,
                verification_status=str(row.get("verification_status") or "UNVERIFIED"),
                risk_categories=risk_categories,
                parent_id=f"source:{source_id}",
                hierarchy=_hierarchy(authority_tier, (source_id,), risk_categories, evidence_id),
                score_eligible=score_eligible,
                practice_reference=False,
                public_export=_to_bool(row.get("public_export", False)),
                generated_translation=False,
                metadata={
                    "canonical_url": row.get("canonical_url", ""),
                    "supports_protection": _to_bool(row.get("supports_protection", False)),
                    "supports_review_signal": _to_bool(
                        row.get("supports_review_signal", False)
                    ),
                },
            )
        )
    return tuple(chunks)


def _knowledge_card_chunks(path: Path) -> tuple[RetrievalChunk, ...]:
    chunks: list[RetrievalChunk] = []
    for row in _read_jsonl(path):
        card_id = _required_text(row, "card_id", path)
        source_ids = _text_list(row.get("source_ids"))
        authority_tier = str(row.get("authority_tier") or _infer_authority_tier(source_ids))
        risk_categories = _text_list(row.get("risk_categories"))
        public_export = _to_bool(row.get("public_export", False))
        score_eligible = _to_bool(row.get("score_eligible", False))
        _require_practice_reference(card_id, authority_tier, score_eligible, public_export)
        text = _join_text(
            card_id,
            row.get("title_ko"),
            row.get("title_en"),
            row.get("explanation_ko"),
            row.get("explanation_en"),
            row.get("aliases_ko"),
            row.get("aliases_en"),
            row.get("financial_variables"),
            row.get("page_or_slide_references"),
            row.get("conflicts"),
            row.get("notes"),
            *risk_categories,
        )
        chunks.append(
            RetrievalChunk(
                chunk_id=card_id,
                chunk_type="knowledge_card",
                title=_join_text(row.get("title_ko"), row.get("title_en")),
                text=text,
                source_id=source_ids[0] if source_ids else "",
                source_ids=source_ids,
                source_class=authority_tier,
                authority_tier=authority_tier,
                verification_status="UNVERIFIED",
                risk_categories=risk_categories,
                parent_id=f"source:{source_ids[0]}" if source_ids else "",
                hierarchy=_hierarchy(authority_tier, source_ids, risk_categories, card_id),
                score_eligible=False,
                practice_reference=True,
                public_export=public_export,
                generated_translation=_to_bool(row.get("generated_translation", False)),
                metadata={
                    "evidence_ids": _text_list(row.get("evidence_ids")),
                    "evidence_strength": row.get("evidence_strength", ""),
                },
            )
        )
    return tuple(chunks)


def _checklist_chunks(path: Path) -> tuple[RetrievalChunk, ...]:
    chunks: list[RetrievalChunk] = []
    for row in _read_jsonl(path):
        check_id = _required_text(row, "check_id", path)
        source_ids = (
            *_text_list(row.get("educational_source_ids")),
            *_text_list(row.get("practical_source_ids")),
        )
        authority_tier = _infer_authority_tier(source_ids)
        risk_categories = (_required_text(row, "risk_category", path),)
        score_eligible = _to_bool(row.get("score_eligible", False))
        _require_practice_reference(check_id, authority_tier, score_eligible, False)
        text = _join_text(
            check_id,
            row.get("question_ko"),
            row.get("question_en"),
            row.get("positive_protections"),
            row.get("review_signals"),
            row.get("financial_variables"),
            row.get("possible_financial_effects"),
            row.get("notes"),
            *risk_categories,
        )
        chunks.append(
            RetrievalChunk(
                chunk_id=check_id,
                chunk_type="checklist_item",
                title=_join_text(row.get("question_ko"), row.get("question_en")),
                text=text,
                source_id=source_ids[0] if source_ids else "",
                source_ids=source_ids,
                source_class=authority_tier,
                authority_tier=authority_tier,
                verification_status="UNVERIFIED",
                risk_categories=risk_categories,
                parent_id=f"source:{source_ids[0]}" if source_ids else "",
                hierarchy=_hierarchy(authority_tier, source_ids, risk_categories, check_id),
                score_eligible=False,
                practice_reference=True,
                public_export=False,
                generated_translation=True,
                metadata={
                    "official_evidence_ids": _text_list(row.get("official_evidence_ids")),
                    "human_review_required": _to_bool(row.get("human_review_required", False)),
                },
            )
        )
    return tuple(chunks)


def _glossary_chunks(path: Path) -> tuple[RetrievalChunk, ...]:
    chunks: list[RetrievalChunk] = []
    for row in _read_csv(path):
        canonical_id = _required_text(row, "canonical_id", path)
        label_ko = _first_text(row, "preferred_ko", "label_ko")
        label_en = _first_text(row, "preferred_en", "label_en")
        aliases_ko = _split_text(row.get("aliases_ko", ""))
        aliases_en = _split_text(row.get("aliases_en", ""))
        source_ids = _split_text(row.get("source_ids", ""))
        authority_tier = _infer_authority_tier(source_ids)
        risk_categories = (_required_text(row, "risk_category", path),)
        score_eligible = _to_bool(row.get("score_eligible", False))
        _require_practice_reference(canonical_id, authority_tier, score_eligible, False)
        generated_translation = _to_bool(row.get("generated_translation", False))
        if (label_en or aliases_en) and not generated_translation:
            raise RetrievalCorpusError(
                f"{path}: {canonical_id} English labels must be generated aliases, not evidence"
            )
        text = _join_text(
            canonical_id,
            label_ko,
            label_en,
            aliases_ko,
            aliases_en,
            row.get("financial_variable"),
            row.get("notes"),
            *risk_categories,
        )
        chunks.append(
            RetrievalChunk(
                chunk_id=f"GL-{canonical_id}",
                chunk_type="glossary_term",
                title=_join_text(label_ko, label_en),
                text=text,
                source_id=source_ids[0] if source_ids else "",
                source_ids=source_ids,
                source_class=authority_tier,
                authority_tier=authority_tier,
                verification_status="UNVERIFIED",
                risk_categories=risk_categories,
                canonical_id=canonical_id,
                non_equivalence_caveat=str(row.get("non_equivalence_caveat") or "").strip(),
                parent_id=f"source:{source_ids[0]}" if source_ids else "",
                hierarchy=_hierarchy(authority_tier, source_ids, risk_categories, canonical_id),
                score_eligible=False,
                practice_reference=True,
                public_export=False,
                generated_translation=generated_translation,
                metadata={
                    "label_ko": label_ko,
                    "label_en": label_en,
                    "aliases_ko": list(aliases_ko),
                    "aliases_en": list(aliases_en),
                    "merged_src_canonical_ids": _split_text(
                        row.get("merged_src_canonical_ids", "")
                    ),
                },
            )
        )
    return tuple(chunks)


def _read_csv(path: Path) -> tuple[dict[str, str], ...]:
    with path.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        rows = tuple(dict(row) for row in reader)
    if not rows:
        raise RetrievalCorpusError(f"{path}: CSV has no records")
    return rows


def _read_jsonl(path: Path) -> tuple[dict[str, Any], ...]:
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), start=1):
        if not line.strip():
            continue
        payload = json.loads(line)
        if not isinstance(payload, dict):
            raise RetrievalCorpusError(f"{path}:{line_number}: JSONL record is not an object")
        records.append(payload)
    if not records:
        raise RetrievalCorpusError(f"{path}: JSONL has no records")
    return tuple(records)


def _require_files(root: Path, relpaths: Sequence[Path]) -> None:
    missing = [rel.as_posix() for rel in relpaths if not (root / rel).is_file()]
    if missing:
        raise RetrievalCorpusError("missing retrieval corpus files: " + ", ".join(missing))


def _required_text(row: Mapping[str, Any], key: str, path: Path) -> str:
    text = str(row.get(key) or "").strip()
    if not text:
        raise RetrievalCorpusError(f"{path}: {key} is required")
    return text


def _first_text(row: Mapping[str, Any], *keys: str) -> str:
    for key in keys:
        text = str(row.get(key) or "").strip()
        if text:
            return text
    return ""


def _require_practice_reference(
    chunk_id: str,
    authority_tier: str,
    score_eligible: bool,
    public_export: bool,
) -> None:
    if authority_tier not in PRACTICE_AUTHORITY_TIERS:
        raise RetrievalCorpusError(f"{chunk_id}: expected B/C practice authority tier")
    if score_eligible:
        raise RetrievalCorpusError(f"{chunk_id}: B/C practice chunk must not score")
    if public_export:
        raise RetrievalCorpusError(f"{chunk_id}: B/C practice chunk must not be public export")


def _score_eligible_from_tier(authority_tier: str) -> bool:
    return authority_tier in SCORING_AUTHORITY_TIERS


def _infer_authority_tier(source_ids: Sequence[str]) -> str:
    tiers = set()
    for source_id in source_ids:
        prefix = source_id.split("-", 1)[0].strip()
        if prefix:
            tiers.add(prefix)
    if not tiers:
        return "B/C"
    if tiers <= {"B"}:
        return "B"
    if tiers <= {"C"}:
        return "C"
    if tiers <= {"B", "C"}:
        return "B/C"
    if len(tiers) == 1:
        return next(iter(tiers))
    return "/".join(sorted(tiers))


def _hierarchy(
    authority_tier: str,
    source_ids: Sequence[str],
    risk_categories: Sequence[str],
    chunk_id: str,
) -> tuple[str, ...]:
    source_label = "|".join(source_ids) if source_ids else "unknown"
    risk_label = "|".join(risk_categories) if risk_categories else "uncategorized"
    return (
        f"tier:{authority_tier}",
        f"source:{source_label}",
        f"risk:{risk_label}",
        f"chunk:{chunk_id}",
    )


def _join_text(*values: Any) -> str:
    pieces: list[str] = []
    for value in values:
        pieces.extend(_flatten_text(value))
    return " ".join(piece for piece in pieces if piece)


def _flatten_text(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        stripped = value.strip()
        return (stripped,) if stripped else ()
    if isinstance(value, Mapping):
        return tuple(piece for item in value.values() for piece in _flatten_text(item))
    if isinstance(value, Iterable):
        return tuple(piece for item in value for piece in _flatten_text(item))
    text = str(value).strip()
    return (text,) if text else ()


def _text_list(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return _split_text(value)
    if isinstance(value, Iterable):
        return tuple(str(item).strip() for item in value if str(item).strip())
    return (str(value).strip(),) if str(value).strip() else ()


def _split_text(value: Any) -> tuple[str, ...]:
    return tuple(
        item.strip()
        for item in str(value).replace("|", ";").replace(",", ";").split(";")
        if item.strip()
    )


def _tuple_text(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,)
    if isinstance(value, Iterable):
        return tuple(str(item) for item in value)
    return ()


def _mapping(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    normalized = str(value or "").strip().lower()
    if normalized in {"true", "1", "yes", "y"}:
        return True
    if normalized in {"false", "0", "no", "n", ""}:
        return False
    raise RetrievalCorpusError(f"invalid boolean value: {value!r}")


def _duplicates(values: Iterable[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    repeated: set[str] = set()
    for value in values:
        if value in seen:
            repeated.add(value)
        seen.add(value)
    return tuple(sorted(repeated))


def _document_frequencies(tokenized_documents: Sequence[Sequence[str]]) -> Counter[str]:
    frequencies: Counter[str] = Counter()
    for tokens in tokenized_documents:
        frequencies.update(set(tokens))
    return frequencies


def _hangul_ngrams(token: str) -> tuple[str, ...]:
    grams: list[str] = []
    for size in (2, 3):
        if len(token) < size:
            continue
        grams.extend(token[index : index + size] for index in range(0, len(token) - size + 1))
    return tuple(grams)

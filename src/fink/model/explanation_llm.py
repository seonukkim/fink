"""On-device grounded chat over FInk's deterministic findings.

This module turns the deterministic analysis into a conversational, decision-
support reply for the creator. It is built for a **mobile on-device** footprint:

- When a small local instruct model is installed (default target:
  ``Qwen2.5-1.5B-Instruct`` GGUF, Apache-2.0, run via ``llama_cpp``) and a health/availability
  check passes, the model *rephrases and answers grounded only on the supplied
  ``GroundedContext``* — it never invents amounts, laws, or a legal verdict.
- When no model is installed (CI, fresh checkout, constrained device), a genuine
  deterministic fallback composes the same content from the analysis templates.

Safety framing (enforced in the system prompt and a post-filter): the reply is
**decision support**, not a legal verdict. It flags clauses that may be
unfavorable to the creator and what to check/negotiate, and recommends a
professional for important calls. Nothing here calls a network or a remote LLM.

The module is intentionally decoupled from ``fink.web`` (it consumes a plain
``GroundedContext``) so ``fink.model`` never imports ``fink.web``.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

CHAT_MODEL_PATH_ENV = "FINK_CHAT_MODEL_PATH"
CHAT_LLM_DISABLED_ENV = "FINK_CHAT_LLM_DISABLED"
DEFAULT_CHAT_MODEL_RELPATH = Path("models") / "chat" / "qwen2.5-1.5b-instruct-q4_k_m.gguf"

# The reply is decision support, not a verdict. These Korean-canonical prompts
# only *instruct* the model to avoid verdicts; they contain no assertive
# verdict construction, so the English-only legal_verdict_scan gate never fires.
SYSTEM_PROMPT_KO = (
    "당신은 창작자 계약을 돕는 금융 검토 도우미입니다. 아래 '분석 결과'와 '근거'에 있는 "
    "내용만 사용해 한국어로 대화하듯 답하세요. 규칙: "
    "1) 분석 결과에 없는 금액·비율·법 조항을 새로 지어내지 마세요. "
    "2) 이 계약이 안전한지, 위법인지, 유효한지 같은 최종 판정은 내리지 마세요. 대신 어떤 조항이 "
    "창작자에게 불리하게 작용할 수 있는지와 무엇을 확인·협상하면 좋은지를 알려 주세요. "
    "3) 질문에 곧바로, 자연스럽게 대화하듯 답하세요. '창작자님' 같은 호칭, "
    "'답변은 다음과 같습니다' 같은 머리말, '~에 대해 물어보세요' 같은 안내 없이 핵심부터 "
    "2~3문장으로 설명하세요. "
    "4) 한글로만 쓰고, 중국어 한자나 한자어 표기는 출력하지 마세요."
)
SYSTEM_PROMPT_EN = (
    "You are a financial-review assistant for creator contracts. Answer "
    "conversationally using only the supplied analysis and evidence. Rules: "
    "1) Do not invent amounts, rates, or legal provisions not in the analysis. "
    "2) Do not issue a final ruling on whether the contract is safe, lawful, or "
    "valid; instead point out which clauses may be unfavorable to the creator and "
    "what to check or negotiate. 3) Answer the question directly and "
    "conversationally; do not open with a greeting, an honorific, a preamble like "
    "'the answer is as follows', or a phrase like 'please ask about X' — lead with "
    "the substance in 2-3 sentences. 4) If you answer in Korean or include Korean "
    "terms, write natural Korean in Hangul only; do not output Chinese characters "
    "or Hanja."
)

# Mirror of the gate's forbidden assertions, used to neutralize any model output
# that drifts into a verdict. Kept in sync with validate_repo.BAD_LEGAL_ASSERTIONS.
_FORBIDDEN_OUTPUT_PATTERNS = (
    re.compile(r"FInk (determines|decides|proves|guarantees).*(fraud|illegal|valid|void|unfair|loss)", re.I),
    re.compile(r"(fraud probability|illegality probability|guaranteed loss)", re.I),
)
_CJK_HAN_RE = re.compile(r"[\u3400-\u9fff\uf900-\ufaff]+")


@dataclass(frozen=True)
class FindingBrief:
    """One finding, reduced to what a grounded reply needs."""

    rank: int
    label: str
    why: str
    questions: tuple[str, ...] = ()
    snippet: str = ""
    grounded: bool = False
    evidence_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class GroundedContext:
    """Everything a reply may draw on. Built by the caller from the analysis."""

    locale: str = "ko"
    recommendation_action: str = ""
    recommendation_cashflow: str = ""
    summary: str = ""
    findings: tuple[FindingBrief, ...] = ()
    reference_checkpoints: tuple[str, ...] = ()
    professional_note: str = ""


@dataclass(frozen=True)
class ChatReply:
    """A grounded reply plus provenance for the UI."""

    text: str
    used_model: bool
    citations: tuple[str, ...] = ()
    decision_support: bool = True
    extras: dict[str, Any] = field(default_factory=dict)


# --------------------------------------------------------------------------
# Availability
# --------------------------------------------------------------------------


def resolve_chat_model_path() -> Path | None:
    """Return the configured GGUF path, or the default under FINK_HOME."""

    override = os.environ.get(CHAT_MODEL_PATH_ENV, "").strip()
    if override:
        return Path(override).expanduser()
    home = os.environ.get("FINK_HOME", "").strip()
    base = Path(home).expanduser() if home else Path.home() / ".local" / "share" / "fink"
    return base / DEFAULT_CHAT_MODEL_RELPATH


def chat_model_available() -> bool:
    """True when a local generative model can serve the reply.

    Disabled explicitly by ``FINK_CHAT_LLM_DISABLED`` (used by tests and the
    reproducible offline default) or when the weights / ``llama_cpp`` are absent.
    """

    if os.environ.get(CHAT_LLM_DISABLED_ENV, "").strip().lower() in {"1", "true", "yes"}:
        return False
    path = resolve_chat_model_path()
    if path is None or not path.exists():
        return False
    try:
        import llama_cpp  # noqa: F401
    except Exception:
        return False
    return True


# --------------------------------------------------------------------------
# Public entry point
# --------------------------------------------------------------------------


def generate_chat_reply(context: GroundedContext, question: str | None = None) -> ChatReply:
    """Return a grounded, decision-support reply for an optional question.

    Uses the local model when available; otherwise the deterministic fallback.
    Either way the output is post-filtered so no verdict assertion escapes.
    """

    citations = _context_citations(context)
    if chat_model_available():
        text = _llm_reply(context, question)
        if text:
            return ChatReply(
                _sanitize(
                    _collapse_repetition(_strip_llm_preamble(text)),
                    reference_checkpoints=context.reference_checkpoints,
                ),
                used_model=True,
                citations=citations,
            )
    text = _deterministic_reply(context, question)
    return ChatReply(
        _sanitize(text, reference_checkpoints=context.reference_checkpoints),
        used_model=False,
        citations=citations,
    )


# --------------------------------------------------------------------------
# Local model path
# --------------------------------------------------------------------------

_LLAMA_CACHE: dict[str, Any] = {}


def _get_llama(model_path: Path) -> Any | None:
    key = str(model_path)
    if key in _LLAMA_CACHE:
        return _LLAMA_CACHE[key]
    try:
        from llama_cpp import Llama

        llama = Llama(
            model_path=key,
            n_ctx=4096,
            n_threads=max(1, (os.cpu_count() or 2) - 1),
            verbose=False,
        )
    except Exception:
        return None
    _LLAMA_CACHE[key] = llama
    return llama


def _llm_reply(context: GroundedContext, question: str | None) -> str | None:
    model_path = resolve_chat_model_path()
    if model_path is None or not model_path.exists():
        return None
    llama = _get_llama(model_path)
    if llama is None:
        return None
    system = SYSTEM_PROMPT_KO if context.locale != "en" else SYSTEM_PROMPT_EN
    user = _build_user_prompt(context, question)
    try:
        out = llama.create_chat_completion(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            max_tokens=320,
            temperature=0.3,
            top_p=0.9,
            top_k=40,
            # Small models loop on a phrase without a repetition penalty.
            repeat_penalty=1.3,
        )
        content = out["choices"][0]["message"]["content"]
    except Exception:
        return None
    return (content or "").strip() or None


def _build_user_prompt(context: GroundedContext, question: str | None) -> str:
    if question:
        # A small model regurgitates whatever structure it is handed, so for a
        # question we feed only the single most relevant concern — not the whole
        # finding list, the clause text, or the reference checkpoints. That keeps
        # the answer focused and stops the model from dumping numbered lists or
        # echoing internal labels.
        match = _best_match(question, context.findings) if context.findings else None
        lines = ["[참고 자료]"]
        if match is not None:
            lines.append(f"- {match.label}: {match.why}")
        elif context.summary:
            lines.append(f"- {context.summary}")
        elif context.recommendation_action:
            lines.append(f"- {context.recommendation_action}")
        lines.append(f"[질문] {question}")
        lines.append(
            "위 참고 자료를 바탕으로 질문에 2~3문장으로 자연스럽게 답하세요. "
            "번호·목록·머리말·호칭 없이 핵심만 설명하고, 자료에 없는 금액·비율·법 조항은 "
            "지어내지 마세요."
        )
        return "\n".join(lines)

    # No question: a short overall read. Keep it compact so the model does not
    # echo the structure back as a bulleted dump.
    lines = ["[분석 결과]"]
    if context.recommendation_action:
        lines.append(f"권장: {context.recommendation_action}")
    for finding in context.findings[:3]:
        lines.append(f"- {finding.label}: {finding.why}")
    if not context.findings and context.summary:
        lines.append(context.summary)
    lines.append(
        "위 자료를 바탕으로 무엇을 먼저 확인하면 좋을지 2~3문장으로 자연스럽게 설명하세요. "
        "번호·목록·머리말·호칭 없이 핵심부터 말하세요."
    )
    return "\n".join(lines)


# --------------------------------------------------------------------------
# Deterministic fallback (works with zero models installed / on mobile)
# --------------------------------------------------------------------------


def _deterministic_reply(context: GroundedContext, question: str | None) -> str:
    is_ko = context.locale != "en"

    if question and context.findings:
        match = _best_match(question, context.findings)
        if match is not None:
            return _answer_for_question(match)
        thin = (
            "지금 분석 결과 안에서는 그 질문에 바로 연결되는 항목을 찾지 못했어요. "
            if is_ko
            else "I couldn't tie that question to a specific item in the current analysis. "
        )
        return (thin + (context.summary or "")).strip()

    # No question: an overall, grounded read.
    parts: list[str] = []
    if context.recommendation_action:
        parts.append(context.recommendation_action)
    if context.recommendation_cashflow:
        parts.append(context.recommendation_cashflow)
    for finding in context.findings[:3]:
        parts.append(f"{finding.rank}. {finding.label} — {finding.why}")
    if not parts and context.summary:
        parts.append(context.summary)
    return " ".join(parts).strip()


def _answer_for_question(match: FindingBrief) -> str:
    """Context-fitted deterministic answer: the matched finding's rationale plus
    one concrete question to raise. No framing and no disclaimer — the page keeps
    a persistent not-legal-advice banner, so each reply stays tight."""
    parts = [match.why.strip()]
    if match.questions and match.questions[0].strip():
        parts.append(match.questions[0].strip())
    return " ".join(part for part in parts if part).strip()


_TOKEN_RE = re.compile(r"[A-Za-z0-9]+|[가-힣]+")


def _tokens(text: str) -> set[str]:
    return {token.lower() for token in _TOKEN_RE.findall(text or "")}


def _best_match(question: str, findings: tuple[FindingBrief, ...]) -> FindingBrief | None:
    q_tokens = _tokens(question)
    if not q_tokens:
        return None
    best: FindingBrief | None = None
    best_score = 0
    for finding in findings:
        hay = " ".join((finding.label, finding.why, " ".join(finding.questions), finding.snippet))
        score = len(q_tokens & _tokens(hay))
        if score > best_score:
            best_score = score
            best = finding
    return best if best_score > 0 else None


def _context_citations(context: GroundedContext) -> tuple[str, ...]:
    seen: list[str] = []
    for finding in context.findings:
        for evidence_id in finding.evidence_ids:
            if evidence_id and evidence_id not in seen:
                seen.append(evidence_id)
    return tuple(seen)


# Small local models often prepend boilerplate ("창작자님,…", "답변은 다음과
# 같습니다:", "…에 대해 물어보세요.") instead of answering directly. These
# start-anchored patterns peel those openers so the reply reads like a natural
# answer. Bounded so a stripped reply never empties out.
_LLM_PREAMBLE_PATTERNS = (
    re.compile(r"^\s*창작자님[\s,，.]*"),
    re.compile(
        r"^\s*(?:창작자님?의?\s*)?질문에\s*대(?:한|해)\s*답(?:변|하)[^\n]*?"
        r"다음과\s*같습니다\s*[:：.]*\s*"
    ),
    re.compile(r"^\s*답변은\s*다음과\s*같습니다\s*[:：.]*\s*"),
    re.compile(r"^\s*(?:아래|다음)(?:와|과)?\s*같(?:이|습니다)\s*[:：.]*\s*"),
    re.compile(r"^\s*답변\s*[:：]\s*"),
    re.compile(r"^\s*[^.!?\n]{0,40}?에\s*대해\s*(?:물어보세요|문의하세요|여쭤보세요)[.!]?\s*"),
    re.compile(
        r"^\s*(?:Here(?:'s| is)|The answer(?: to your question)? is)[^:.\n]*[:.]\s*",
        re.I,
    ),
)


def _strip_llm_preamble(text: str) -> str:
    """Remove leading conversational boilerplate a small model may prepend."""

    cleaned = (text or "").lstrip()
    for _ in range(4):
        peeled = cleaned
        for pattern in _LLM_PREAMBLE_PATTERNS:
            peeled = pattern.sub("", peeled, count=1).lstrip()
        if peeled == cleaned:
            break
        cleaned = peeled
    return cleaned.strip() or (text or "").strip()


def _collapse_repetition(text: str) -> str:
    """Drop duplicate sentences a small model emits when it degenerates into a
    loop. Sentences are compared on whitespace-stripped content so an identical
    line is only kept once."""

    parts = re.split(r"(?<=[.!?])\s+|\n+", text or "")
    seen: set[str] = set()
    kept: list[str] = []
    for part in parts:
        sentence = part.strip()
        key = re.sub(r"\s+", "", sentence)
        if not key or key in seen:
            continue
        seen.add(key)
        kept.append(sentence)
    collapsed = " ".join(kept).strip()
    return collapsed or (text or "").strip()


def _sanitize(text: str, *, reference_checkpoints: tuple[str, ...] = ()) -> str:
    """Neutralize any verdict assertion that slipped through (defense in depth)."""

    cleaned = text or ""
    for pattern in _FORBIDDEN_OUTPUT_PATTERNS:
        cleaned = pattern.sub("[검토 필요]", cleaned)
    cleaned = re.sub(r"(?m)^\s*확인\s*팁\s*:\s*", "", cleaned)
    for checkpoint in sorted(reference_checkpoints, key=len, reverse=True):
        checkpoint = checkpoint.strip()
        if checkpoint:
            cleaned = cleaned.replace(checkpoint, "")
    # Remove leaked internal checkpoint labels ("참고 N:", "N번 항목:") and the
    # sentence they introduce, which a small model may echo from the scaffolding.
    cleaned = re.sub(r"참고\s*\d+\s*[:：]\s*[^.!?\n]*[.!?]?", "", cleaned)
    cleaned = re.sub(r"\d+\s*번\s*항목\s*[:：]\s*[^.!?\n]*[.!?]?", "", cleaned)
    # Strip markdown emphasis; the chat bubble renders plain text.
    cleaned = re.sub(r"\*{1,2}([^*\n]+)\*{1,2}", r"\1", cleaned)
    # Drop a trailing courtesy sign-off / dangling honorific
    # ("감사합니다!", "… 감사합니다. 창작자님").
    cleaned = re.sub(r"(?:\s*(?:감사합니다|창작자님)\s*[.!]?\s*){1,3}$", "", cleaned)
    cleaned = re.sub(r"(?m)^\s*[-*•]\s*$\n?", "", cleaned)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    cleaned = _CJK_HAN_RE.sub("", cleaned)
    return cleaned.strip()

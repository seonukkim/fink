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
    "3) 중요한 결정은 전문가 확인을 권하세요. "
    "4) 짧고 쉬운 말로, 창작자가 다음에 무엇을 하면 되는지 도와주는 톤으로 말하세요. "
    "5) 자연스러운 한국어를 한글로만 쓰고, 중국어 한자나 한자어 표기를 출력하지 마세요."
)
SYSTEM_PROMPT_EN = (
    "You are a financial-review assistant for creator contracts. Answer "
    "conversationally using only the supplied analysis and evidence. Rules: "
    "1) Do not invent amounts, rates, or legal provisions not in the analysis. "
    "2) Do not issue a final ruling on whether the contract is safe, lawful, or "
    "valid; instead point out which clauses may be unfavorable to the creator and "
    "what to check or negotiate. 3) Recommend a professional for important "
    "decisions. 4) Keep it short, plain, and oriented to the creator's next step. "
    "5) If you answer in Korean or include Korean terms, write natural Korean in "
    "Hangul only; do not output Chinese characters or Hanja."
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
            return ChatReply(_sanitize(text), used_model=True, citations=citations)
    text = _deterministic_reply(context, question)
    return ChatReply(_sanitize(text), used_model=False, citations=citations)


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
            max_tokens=512,
            temperature=0.2,
            top_p=0.9,
        )
        content = out["choices"][0]["message"]["content"]
    except Exception:
        return None
    return (content or "").strip() or None


def _build_user_prompt(context: GroundedContext, question: str | None) -> str:
    lines: list[str] = ["[분석 결과]"]
    if context.recommendation_action:
        lines.append(f"권장: {context.recommendation_action}")
    if context.recommendation_cashflow:
        lines.append(f"현금흐름: {context.recommendation_cashflow}")
    if context.findings:
        lines.append("[확인할 항목]")
        for finding in context.findings:
            ground = "근거 연결됨" if finding.grounded else "확인 필요"
            lines.append(f"{finding.rank}. {finding.label} ({ground}): {finding.why}")
            if finding.questions:
                lines.append(f"   물어볼 말: {finding.questions[0]}")
            if finding.snippet:
                lines.append(f"   조항: {finding.snippet}")
    if context.reference_checkpoints:
        lines.append("[참고 체크포인트]")
        lines.append(
            "아래 항목은 설명하거나 확인할 점을 제안할 때 참고할 수 있는 일반 실무 안내입니다. "
            "공식 근거, 점수, 판정으로 취급하지 마세요."
        )
        for checkpoint in context.reference_checkpoints:
            lines.append(f"- {checkpoint}")
    if question:
        lines.append(f"[창작자 질문] {question}")
        lines.append("질문에 위 내용만 근거로 답하세요.")
    else:
        lines.append("위 내용을 바탕으로 무엇을 먼저 확인하면 좋을지 정리해 주세요.")
    return "\n".join(lines)


# --------------------------------------------------------------------------
# Deterministic fallback (works with zero models installed / on mobile)
# --------------------------------------------------------------------------


def _deterministic_reply(context: GroundedContext, question: str | None) -> str:
    is_ko = context.locale != "en"
    note = context.professional_note or (
        "이 정리는 결정을 돕기 위한 것이고 최종 법적 판단은 아니에요. 중요한 부분은 전문가 확인을 권해요."
        if is_ko
        else "This is decision support, not a final legal judgment; please have a professional confirm important points."
    )

    if question and context.findings:
        match = _best_match(question, context.findings)
        if match is not None:
            parts = [
                (f"“{match.label}” 항목과 관련이 있어 보여요. {match.why}")
                if is_ko
                else (f"This relates to “{match.label}”. {match.why}")
            ]
            if match.questions:
                parts.append(
                    f"상대방에게 “{match.questions[0]}”라고 확인해 보세요."
                    if is_ko
                    else f"You could ask the other side: “{match.questions[0]}”"
                )
            parts.append(note)
            reply = " ".join(parts)
            tip = _best_checkpoint_tip(context.reference_checkpoints, question, match)
            if tip and is_ko:
                reply += f"\n확인 팁: {tip}"
            return reply
        thin = (
            "지금 분석 결과 안에서는 그 질문에 바로 연결되는 항목을 찾지 못했어요. "
            if is_ko
            else "I couldn't tie that question to a specific item in the current analysis. "
        )
        return thin + (context.summary or note)

    # No question: an overall, grounded read.
    parts: list[str] = []
    if context.recommendation_action:
        parts.append(context.recommendation_action)
    if context.recommendation_cashflow:
        parts.append(context.recommendation_cashflow)
    top = context.findings[:3]
    if top:
        parts.append(
            f"서명 전에 먼저 확인하면 좋은 항목 {len(top)}가지를 정리했어요."
            if is_ko
            else f"Here are {len(top)} items worth checking before you sign."
        )
        for finding in top:
            line = f"{finding.rank}. {finding.label} — {finding.why}"
            if finding.questions:
                line += (
                    f" 상대방에게 “{finding.questions[0]}”라고 물어보세요."
                    if is_ko
                    else f" Ask: “{finding.questions[0]}”"
                )
            parts.append(line)
    elif context.summary:
        parts.append(context.summary)
    parts.append(note)
    reply = " ".join(parts)
    tip = _best_checkpoint_tip(context.reference_checkpoints, question, top[0] if top else None)
    if tip and is_ko:
        reply += f"\n확인 팁: {tip}"
    return reply


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


def _best_checkpoint_tip(
    checkpoints: tuple[str, ...],
    question: str | None,
    finding: FindingBrief | None,
) -> str:
    if not checkpoints:
        return ""
    hay = question or ""
    if finding is not None:
        hay = " ".join(
            (hay, finding.label, finding.why, " ".join(finding.questions), finding.snippet)
        )
    wanted = _tokens(hay)
    if not wanted:
        return checkpoints[0]
    best = checkpoints[0]
    best_score = 0
    for checkpoint in checkpoints:
        score = len(wanted & _tokens(checkpoint))
        if score > best_score:
            best_score = score
            best = checkpoint
    return best


def _context_citations(context: GroundedContext) -> tuple[str, ...]:
    seen: list[str] = []
    for finding in context.findings:
        for evidence_id in finding.evidence_ids:
            if evidence_id and evidence_id not in seen:
                seen.append(evidence_id)
    return tuple(seen)


def _sanitize(text: str) -> str:
    """Neutralize any verdict assertion that slipped through (defense in depth)."""

    cleaned = text or ""
    for pattern in _FORBIDDEN_OUTPUT_PATTERNS:
        cleaned = pattern.sub("[검토 필요]", cleaned)
    cleaned = _CJK_HAN_RE.sub("", cleaned)
    return cleaned.strip()

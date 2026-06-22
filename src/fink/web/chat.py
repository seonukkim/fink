"""Bridge from the deterministic analysis to the grounded chat engine.

The web layer parses a chat request, runs the offline analysis once, projects it
into a model-agnostic ``GroundedContext``, and asks ``fink.model.explanation_llm``
for a decision-support reply (local LLM when installed, deterministic fallback
otherwise). This keeps ``fink.model`` free of any ``fink.web`` import.
"""

from __future__ import annotations

from typing import Any

from fink.model.explanation_llm import FindingBrief, GroundedContext, generate_chat_reply
from fink.schemas import UILocale

_PROFESSIONAL_NOTE_KO = (
    "이 정리는 결정을 돕기 위한 것이고 최종 법적 판단은 아니에요. 중요한 부분은 전문가 확인을 권해요."
)
_PROFESSIONAL_NOTE_EN = (
    "This is decision support, not a final legal judgment; please have a professional "
    "confirm important points."
)


def build_grounded_context(result: Any, locale: UILocale) -> GroundedContext:
    """Project a ``LocalAnalysisResult`` into the chat engine's input."""

    is_ko = locale is not UILocale.EN
    guidance_by_category = {item.risk_category: item for item in result.category_guidance}
    briefs: list[FindingBrief] = []
    for finding in result.ranked_findings:
        guidance = guidance_by_category.get(finding.risk_category)
        why = "" if guidance is None else (
            guidance.why_it_matters_ko if is_ko else guidance.why_it_matters_en
        )
        questions = () if guidance is None else (
            guidance.questions_ko if is_ko else guidance.questions_en
        )
        briefs.append(
            FindingBrief(
                rank=finding.rank,
                label=finding.label_ko if is_ko else finding.label_en,
                why=why,
                questions=tuple(questions),
                snippet=finding.snippet,
                grounded=bool(finding.scored),
                evidence_ids=tuple(finding.grounding_evidence_ids),
            )
        )
    action = result.recommended_action
    return GroundedContext(
        locale="ko" if is_ko else "en",
        recommendation_action=action.action_ko if is_ko else action.action_en,
        recommendation_cashflow=action.cash_flow_ko if is_ko else action.cash_flow_en,
        summary=result.nl_summary_ko if is_ko else result.nl_summary_en,
        findings=tuple(briefs),
        professional_note=_PROFESSIONAL_NOTE_KO if is_ko else _PROFESSIONAL_NOTE_EN,
    )


def chat_reply_for_request(
    *, paste_text: str, question: str | None, locale: UILocale
) -> dict[str, Any]:
    """Run the offline analysis and return a grounded chat reply payload."""

    from fink.web.analyze import run_local_analysis

    result = run_local_analysis(pasted_text=paste_text, ui_locale=locale)
    context = build_grounded_context(result, locale)
    reply = generate_chat_reply(context, question)
    return {
        "reply": reply.text,
        "used_model": reply.used_model,
        "citations": list(reply.citations),
        "decision_support": reply.decision_support,
        "local_only": True,
    }

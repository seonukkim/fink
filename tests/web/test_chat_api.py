from __future__ import annotations

from fink.model.explanation_llm import generate_chat_reply
from fink.schemas import UILocale
from fink.web.analyze import run_local_analysis
from fink.web.chat import build_grounded_context, chat_reply_for_request


PASTE_TEXT = "제3조(정산) 회사는 매월 말 정산 후 다음 달 30일 이내에 창작자에게 수익금을 지급한다."
CHECKPOINT_PASTE_TEXT = (
    "제3조(정산) 정산은 매 분기 종료일로부터 90일 이내에 지급하며, 회사는 일반 경비를 공제할 수 있다.\n"
    "제5조(위약금) 계약 위반 시 위약금을 부과한다."
)


def test_chat_reply_returns_decision_support_without_question(monkeypatch) -> None:
    monkeypatch.setenv("FINK_CHAT_LLM_DISABLED", "1")

    payload = chat_reply_for_request(
        paste_text=PASTE_TEXT,
        question=None,
        locale=UILocale.KO,
    )

    assert isinstance(payload["reply"], str)
    assert payload["reply"].strip()
    assert payload["used_model"] is False
    assert payload["decision_support"] is True


def test_grounded_context_includes_reference_checkpoints_for_findings(monkeypatch) -> None:
    monkeypatch.setenv("FINK_CHAT_LLM_DISABLED", "1")

    result = run_local_analysis(
        pasted_text=CHECKPOINT_PASTE_TEXT,
        ui_locale=UILocale.KO,
    )
    categories = {finding.risk_category for finding in result.ranked_findings}
    assert {"F1", "F2"} <= categories

    context = build_grounded_context(result, UILocale.KO)

    assert 0 < len(context.reference_checkpoints) <= 5
    assert any("확인할 것" in item for item in context.reference_checkpoints)
    assert any("정산" in item or "공제" in item for item in context.reference_checkpoints)

    reply = generate_chat_reply(context, "공제 항목은 무엇을 확인해야 하나요?")

    assert reply.used_model is False
    assert reply.decision_support is True
    assert reply.text.strip()
    assert reply.citations


def test_chat_reply_returns_decision_support_with_question(monkeypatch) -> None:
    monkeypatch.setenv("FINK_CHAT_LLM_DISABLED", "1")

    payload = chat_reply_for_request(
        paste_text=PASTE_TEXT,
        question="정산 기한에서 먼저 확인할 점은 무엇인가요?",
        locale=UILocale.KO,
    )

    assert isinstance(payload["reply"], str)
    assert payload["reply"].strip()
    assert payload["used_model"] is False
    assert payload["decision_support"] is True

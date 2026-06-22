from __future__ import annotations

from fink.schemas import UILocale
from fink.web.chat import chat_reply_for_request


PASTE_TEXT = "제3조(정산) 회사는 매월 말 정산 후 다음 달 30일 이내에 창작자에게 수익금을 지급한다."


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

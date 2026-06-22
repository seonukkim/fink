"""The grounded chat engine must work with zero models installed (mobile/CI)."""

from __future__ import annotations

from fink.model.explanation_llm import (
    ChatReply,
    FindingBrief,
    GroundedContext,
    chat_model_available,
    generate_chat_reply,
)


def _context() -> GroundedContext:
    return GroundedContext(
        locale="ko",
        recommendation_action="권장 행동: 몇 가지 항목을 확인한 뒤 서명을 검토하세요.",
        recommendation_cashflow="현금 흐름 영향은 작아 보이지만 확인 후 진행하는 것이 안전합니다.",
        summary="자동 정리 요약입니다.",
        findings=(
            FindingBrief(
                rank=1,
                label="정산명세 보호장치 부재",
                why="정산 명세와 감사 권한이 약하면 공제 내역을 검증하기 어렵습니다.",
                questions=("정산 명세서를 항목별로 받을 수 있나요?",),
                snippet="정산은 분기 종료일로부터 90일 이내 지급",
                grounded=True,
                evidence_ids=("EV-A2-2021-SETTLEMENT",),
            ),
            FindingBrief(
                rank=2,
                label="매출 기준 또는 공제항목 정의 부재",
                why="매출 기준과 공제 항목이 모호하면 실수령액이 줄어들 수 있습니다.",
                questions=("공제 항목을 구체적으로 한정할 수 있나요?",),
                grounded=True,
                evidence_ids=("EV-A1-ASSIGNFULL-02",),
            ),
        ),
        professional_note="중요한 부분은 전문가 확인을 권해요.",
    )


def test_fallback_overall_reply(monkeypatch):
    monkeypatch.setenv("FINK_CHAT_LLM_DISABLED", "1")
    assert chat_model_available() is False
    reply = generate_chat_reply(_context(), None)
    assert isinstance(reply, ChatReply)
    assert reply.used_model is False
    assert reply.decision_support is True
    assert "정산명세 보호장치 부재" in reply.text
    assert "전문가" in reply.text  # professional-confirm cue is present
    assert "EV-A2-2021-SETTLEMENT" in reply.citations


def test_fallback_question_match(monkeypatch):
    monkeypatch.setenv("FINK_CHAT_LLM_DISABLED", "1")
    reply = generate_chat_reply(_context(), "공제 항목은 어떻게 되나요?")
    assert reply.used_model is False
    assert "공제" in reply.text
    assert "전문가" in reply.text


def test_no_verdict_assertions_leak(monkeypatch):
    monkeypatch.setenv("FINK_CHAT_LLM_DISABLED", "1")
    text = generate_chat_reply(_context(), None).text.lower()
    assert "guaranteed loss" not in text
    assert "fraud probability" not in text
    assert "fink determines" not in text

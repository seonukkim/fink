"""The grounded chat engine must work with zero models installed (mobile/CI)."""

from __future__ import annotations

from fink.model.explanation_llm import (
    ChatReply,
    FindingBrief,
    GroundedContext,
    _collapse_repetition,
    _sanitize,
    _strip_llm_preamble,
    chat_model_available,
    generate_chat_reply,
)


def _context() -> GroundedContext:
    return GroundedContext(
        locale="ko",
        recommendation_action="권장: 몇 가지 항목을 확인한 뒤 서명을 검토하세요.",
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
        reference_checkpoints=(
            "정산서가 언제, 어떤 형식으로, 어떤 매출·공제 항목을 나누어 제공되는지 확인할 것.",
            "수수료, 결제비용, 환불, 세금, 마케팅비, 제작비가 각각 공제되는지 확인할 것.",
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
    # The not-legal-advice disclaimer lives in the persistent page banner now,
    # so it is not repeated inside each chat reply.
    assert "전문가 확인을 권해요" not in reply.text
    assert "확인 팁:" not in reply.text
    assert "정산서가 언제, 어떤 형식으로" not in reply.text
    assert "EV-A2-2021-SETTLEMENT" in reply.citations


def test_fallback_question_match(monkeypatch):
    monkeypatch.setenv("FINK_CHAT_LLM_DISABLED", "1")
    reply = generate_chat_reply(_context(), "공제 항목은 어떻게 되나요?")
    assert reply.used_model is False
    assert "공제" in reply.text
    assert "전문가 확인을 권해요" not in reply.text
    assert "확인 팁:" not in reply.text
    assert "수수료, 결제비용, 환불" not in reply.text


def test_no_verdict_assertions_leak(monkeypatch):
    monkeypatch.setenv("FINK_CHAT_LLM_DISABLED", "1")
    text = generate_chat_reply(_context(), None).text.lower()
    assert "guaranteed loss" not in text
    assert "fraud probability" not in text
    assert "fink determines" not in text


def test_sanitize_removes_stray_hanja_idempotently():
    cleaned = _sanitize("會計年度 정산 條項은 확인하세요.")
    assert cleaned == "정산 은 확인하세요."
    assert _sanitize(cleaned) == cleaned


def test_sanitize_removes_raw_reference_checkpoint_lines():
    checkpoint = "정산서가 언제, 어떤 형식으로, 어떤 매출·공제 항목을 나누어 제공되는지 확인할 것."
    cleaned = _sanitize(
        f"확인 팁: {checkpoint}\n- {checkpoint}\n정산 조건을 자연어로 확인하세요.",
        reference_checkpoints=(checkpoint,),
    )

    assert "확인 팁:" not in cleaned
    assert checkpoint not in cleaned
    assert "정산 조건을 자연어로 확인하세요." in cleaned


def test_strip_llm_preamble_removes_creator_address_and_ask_directive():
    text = (
        "창작자님, 정산 투명성과 감사권에 대해 물어보세요. "
        "정산 명세서는 항목별로 받을 수 있어야 합니다."
    )
    out = _strip_llm_preamble(text)
    assert not out.startswith("창작자님")
    assert "에 대해 물어보세요" not in out.split(".")[0]
    assert "정산 명세서는 항목별로 받을 수 있어야 합니다." in out


def test_strip_llm_preamble_removes_answer_preamble():
    text = "창작자의 질문에 대한 답변은 다음과 같습니다: 매출 기준은 매출 항목을 기준으로 합니다."
    out = _strip_llm_preamble(text)
    assert out.startswith("매출 기준은")
    assert "답변은 다음과 같습니다" not in out


def test_strip_llm_preamble_keeps_clean_answer():
    text = "정산 명세와 감사 권한이 약하면 공제 내역을 검증하기 어렵습니다."
    assert _strip_llm_preamble(text) == text


def test_collapse_repetition_drops_looped_sentences():
    looped = (
        "이 조항은 금액을 정의합니다. 추가 금액은 시점에 따라 계산됩니다. "
        "추가 금액은 시점에 따라 계산됩니다. 추가 금액은 시점에 따라 계산됩니다."
    )
    out = _collapse_repetition(looped)
    assert out.count("추가 금액은 시점에 따라 계산됩니다.") == 1
    assert "이 조항은 금액을 정의합니다." in out


def test_sanitize_strips_leaked_internal_labels_and_markdown():
    text = (
        "정산 투명성은 중요합니다. **정산 명세서**를 확인하세요. "
        "참고 1: 정산서가 언제 제공되는지 확인해야 합니다. 감사합니다!"
    )
    cleaned = _sanitize(text)
    assert "참고 1:" not in cleaned
    assert "**" not in cleaned
    assert "정산 명세서를 확인하세요." in cleaned
    assert not cleaned.endswith("감사합니다!")

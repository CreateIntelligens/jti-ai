"""Shared runtime quiz flow helpers for JTI chat endpoints."""

from __future__ import annotations

import logging

from fastapi import HTTPException

from app.schemas.chat import ChatResponse
from app.services.jti.quiz_helpers import _format_options_text
from app.services.session.session_manager_factory import (
    get_conversation_logger,
    get_session_manager,
)
from app.tools.jti.tool_executor import tool_executor

session_manager = get_session_manager()
conversation_logger = get_conversation_logger()
logger = logging.getLogger(__name__)

QUIZ_OPENING = {
    "zh": "簡單四個問題，幫你找到命定保護殼，如果中途想離開，請輸入「中斷」，即可回到問答模式，讓我們開始測驗吧！",
    "en": "Just four questions to find your perfect phone case! If you want to leave midway, type pause to return to chat. Let's begin!",
}


def make_quiz_tts_text(q: dict, q_num: int, language: str) -> str:
    """Build quiz-mode TTS text without options."""
    text = q.get("text", "")
    if language == "en":
        return f"Question {q_num}: {text}"
    return f"第{q_num}題：{text}"


async def execute_quiz_start(
    session_id: str,
    user_message: str = "[API] quiz_start",
) -> ChatResponse:
    """Start a quiz for both direct API and keyword-triggered chat flow."""
    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if session.step.value == "DONE":
        if session.language == "en":
            response_message = (
                "You've already completed the quiz! Please refresh the page to start a new session."
            )
        else:
            response_message = (
                "你已經完成過測驗囉！這次對話只能測驗一次。如果想重新測驗，請重新整理頁面開始新的對話。"
            )

        log_result = conversation_logger.log_conversation(
            session_id=session_id,
            user_message=user_message,
            agent_response=response_message,
            tool_calls=[],
            session_state={
                "step": session.step.value,
                "answers_count": len(session.answers),
                "color_result_id": session.color_result_id,
                "current_question_id": None,
                "language": session.language,
                "selected_questions": session.selected_questions,
            },
            mode="jti",
        )
        final_turn_number = log_result[1] if log_result else None
        return ChatResponse(
            message=response_message,
            session=session.model_dump(),
            tool_calls=[],
            turn_number=final_turn_number,
        )

    tool_result = await tool_executor.execute("start_quiz", {"session_id": session_id})
    updated_session = session_manager.get_session(session_id)

    if not tool_result.get("success"):
        return ChatResponse(
            message=tool_result.get("error", "start_quiz failed"),
            session=updated_session.model_dump() if updated_session else session.model_dump(),
            tool_calls=[],
            error=tool_result.get("error"),
        )

    lang = updated_session.language if updated_session else session.language
    q = tool_result.get("current_question") or (
        updated_session.current_question if updated_session else None
    )
    options_text = _format_options_text(q.get("options", []) if isinstance(q, dict) else [])
    opening = QUIZ_OPENING.get(lang, QUIZ_OPENING["zh"])

    if lang == "en":
        response_message = f"{opening}\n\nQuestion 1: {q.get('text', '')}\n{options_text}"
    else:
        response_message = f"{opening}\n\n第1題：{q.get('text', '')}\n{options_text}"

    tts_text = (
        f"{opening} {make_quiz_tts_text(q, 1, lang)}" if isinstance(q, dict) else None
    )

    log_result = conversation_logger.log_conversation(
        session_id=session_id,
        user_message=user_message,
        agent_response=response_message,
        tool_calls=[{"tool": "start_quiz", "args": {"session_id": session_id}, "result": tool_result}],
        session_state={
            "step": updated_session.step.value if updated_session else session.step.value,
            "answers_count": len(updated_session.answers) if updated_session else len(session.answers),
            "color_result_id": updated_session.color_result_id if updated_session else session.color_result_id,
            "current_question_id": q.get("id") if isinstance(q, dict) else None,
            "language": lang,
            "selected_questions": (
                updated_session.selected_questions if updated_session else session.selected_questions
            ),
        },
        mode="jti",
    )
    final_turn_number = log_result[1] if log_result else None

    return ChatResponse(
        message=response_message,
        tts_text=tts_text,
        session=updated_session.model_dump() if updated_session else session.model_dump(),
        tool_calls=[{"tool": "start_quiz", "args": {"session_id": session_id}}],
        turn_number=final_turn_number,
    )

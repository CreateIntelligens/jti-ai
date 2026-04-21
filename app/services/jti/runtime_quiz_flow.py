"""Shared runtime quiz flow helpers for JTI chat endpoints."""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import HTTPException

from app.schemas.chat import ChatResponse
from app.services.jti.quiz_helpers import (
    _format_options_text,
    _label_options,
    build_session_state,
)
from app.services.tts_text import to_jti_tts_text
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


def extract_option_texts(q: Optional[dict]) -> Optional[list[str]]:
    """Extract labelled option list (e.g. ['A. 簡約', 'B. 可愛']) from a question dict."""
    if not isinstance(q, dict):
        return None
    options = q.get("options", [])
    if not options:
        return None
    return _label_options(options)


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
            session_state=build_session_state(session),
            mode="jti",
        )
        final_turn_number = log_result[1] if log_result else None
        return ChatResponse(
            message=response_message,
            tts_text=to_jti_tts_text(response_message, session.language),
            session=session.model_dump(),
            tool_calls=[],
            turn_number=final_turn_number,
        )

    tool_result = await tool_executor.execute("start_quiz", {"session_id": session_id})
    updated_session = session_manager.get_session(session_id)

    if not tool_result.get("success"):
        error_message = tool_result.get("error", "start_quiz failed")
        fallback_lang = updated_session.language if updated_session else session.language
        return ChatResponse(
            message=error_message,
            tts_text=to_jti_tts_text(error_message, fallback_lang),
            session=updated_session.model_dump() if updated_session else session.model_dump(),
            tool_calls=[],
            error=error_message,
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

    raw_tts_text = (
        f"{opening} {make_quiz_tts_text(q, 1, lang)}" if isinstance(q, dict) else None
    )
    tts_text = to_jti_tts_text(raw_tts_text, lang)

    log_result = conversation_logger.log_conversation(
        session_id=session_id,
        user_message=user_message,
        agent_response=response_message,
        tool_calls=[{"tool": "start_quiz", "args": {"session_id": session_id}, "result": tool_result}],
        session_state=build_session_state(updated_session or session),
        mode="jti",
    )
    final_turn_number = log_result[1] if log_result else None

    return ChatResponse(
        message=response_message,
        tts_text=tts_text,
        options=extract_option_texts(q),
        session=updated_session.model_dump() if updated_session else session.model_dump(),
        tool_calls=[{"tool": "start_quiz", "args": {"session_id": session_id}}],
        turn_number=final_turn_number,
    )

"""Shared runtime quiz flow helpers for JTI chat endpoints."""

from __future__ import annotations

import logging

from fastapi import HTTPException

from app.schemas.chat import ChatResponse
from app.services.jti.quiz_helpers import build_session_state
from app.services.jti.response_assembly import (
    QUIZ_OPENING,
    build_jti_quiz_question_fields,
    build_jti_response_fields,
    extract_option_texts,
)
from app.services.session.session_manager_factory import (
    get_conversation_logger,
    get_session_manager,
)
from app.tools.jti.tool_executor import tool_executor

session_manager = get_session_manager()
conversation_logger = get_conversation_logger()
logger = logging.getLogger(__name__)


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
        response_fields = build_jti_response_fields(response_message, session.language)
        return ChatResponse(
            **response_fields,
            session=session.model_dump(),
            tool_calls=[],
            turn_number=final_turn_number,
        )

    tool_result = await tool_executor.execute("start_quiz", {"session_id": session_id})
    updated_session = session_manager.get_session(session_id)

    if not tool_result.get("success"):
        error_message = tool_result.get("error", "start_quiz failed")
        fallback_lang = updated_session.language if updated_session else session.language
        response_fields = build_jti_response_fields(error_message, fallback_lang)
        return ChatResponse(
            **response_fields,
            session=updated_session.model_dump() if updated_session else session.model_dump(),
            tool_calls=[],
            error=error_message,
        )

    lang = updated_session.language if updated_session else session.language
    q = tool_result.get("current_question") or (
        updated_session.current_question if updated_session else None
    )
    opening = QUIZ_OPENING.get(lang, QUIZ_OPENING["zh"])
    response_fields = build_jti_quiz_question_fields(q, 1, lang, prefix=opening)

    log_result = conversation_logger.log_conversation(
        session_id=session_id,
        user_message=user_message,
        agent_response=response_fields["message"],
        tool_calls=[{"tool": "start_quiz", "args": {"session_id": session_id}, "result": tool_result}],
        session_state=build_session_state(updated_session or session),
        mode="jti",
    )
    final_turn_number = log_result[1] if log_result else None

    return ChatResponse(
        **response_fields,
        options=extract_option_texts(q),
        session=updated_session.model_dump() if updated_session else session.model_dump(),
        tool_calls=[{"tool": "start_quiz", "args": {"session_id": session_id}}],
        turn_number=final_turn_number,
    )

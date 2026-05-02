"""Shared runtime quiz flow helpers for JTI chat endpoints."""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import HTTPException

import app.deps as deps
from app.routers.tts_utils import attach_tts_message_id
from app.schemas.chat import ChatResponse
from app.services.jti.main_agent import main_agent
from app.services.jti.quiz_helpers import (
    _judge_user_choice,
    _pause_quiz_and_respond,
    build_session_state,
)
from app.services.jti.response_assembly import (
    QUIZ_OPENING,
    build_jti_quiz_question_fields,
    build_jti_response_fields,
    extract_option_texts,
)
from app.tools.jti.quiz import get_total_questions
from app.tools.jti.tool_executor import tool_executor

logger = logging.getLogger(__name__)


async def execute_quiz_start(
    session_id: str,
    user_message: str = "[API] quiz_start",
) -> ChatResponse:
    """Start a quiz for both direct API and keyword-triggered chat flow."""
    session_manager = deps.get_jti_session_manager()
    conversation_logger = deps.get_jti_conversation_logger()
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


async def handle_quiz_message(session, request) -> Optional[ChatResponse]:
    """Handle active JTI quiz answers. Return None to continue non-quiz flow."""
    if session.step.value != "QUIZ" or not session.current_question:
        return None

    agent = main_agent
    session_manager = deps.get_jti_session_manager()
    conversation_logger = deps.get_jti_conversation_logger()
    tts_manager = deps.get_jti_tts_job_manager()

    def with_tts(response: ChatResponse, language: str) -> ChatResponse:
        return attach_tts_message_id(response, language, tts_manager)

    q = session.current_question
    total_questions = get_total_questions(session.language)
    current_q_num = len(session.answers) + 1

    if request.message.strip() == "中斷":
        pause_response = ChatResponse(**(await _pause_quiz_and_respond(
            session_id=request.session_id,
            log_user_message=request.message,
            session=session,
        )))
        return with_tts(pause_response, session.language)

    logger.info(f"[測驗進度] 第 {current_q_num}/{total_questions} 題 | 題目: {q.get('text', '')[:30]}...")

    user_choice = await _judge_user_choice(request.message, q)
    logger.info(f"[答題判斷] 使用者回答: '{request.message}' -> 判定選項: {user_choice}")

    if user_choice == "PAUSE":
        pause_response = ChatResponse(**(await _pause_quiz_and_respond(
            session_id=request.session_id,
            log_user_message=request.message,
            session=session,
        )))
        return with_tts(pause_response, session.language)

    if user_choice:
        tool_result = await tool_executor.execute("submit_answer", {
            "session_id": request.session_id,
            "user_choice": user_choice,
        })
        tool_calls = [{"tool": "submit_answer", "args": {"user_choice": user_choice}, "result": tool_result}]

        updated_session = session_manager.get_session(request.session_id)
        logger.info(f"[答題結果] 選項: {user_choice} | 已答: {len(updated_session.answers)}/{total_questions} 題")
        if updated_session.quiz_scores:
            scores_str = " | ".join([f"{k}:{v}" for k, v in sorted(updated_session.quiz_scores.items(), key=lambda x: -x[1])])
            logger.info(f"[當前分數] {scores_str}")

        is_complete = tool_result.get("is_complete")
        next_q = tool_result.get("next_question") if not is_complete else None

        if is_complete:
            response_message = tool_result.get("message", "")
            response_fields = build_jti_response_fields(
                response_message,
                updated_session.language,
                tts_source=tool_result.get("tts_text") or response_message,
            )
            agent.remove_session(request.session_id)
            updated_session.chat_history.append({"role": "assistant", "content": response_message})
            session_manager.update_session(updated_session)
        else:
            q_num = len(updated_session.answers) + 1
            response_fields = build_jti_quiz_question_fields(
                next_q,
                q_num,
                updated_session.language,
            )
            response_message = response_fields["message"]

        log_result = conversation_logger.log_conversation(
            session_id=request.session_id,
            user_message=request.message,
            agent_response=response_message,
            tool_calls=tool_calls,
            session_state=build_session_state(updated_session),
            mode="jti",
        )
        final_turn_number = log_result[1] if log_result else None
        logger.info(f"QUIZ 作答成功: {request.message} -> {user_choice}")

        quiz_result = tool_result.get("quiz_result") or {}
        response_payload = ChatResponse(
            **response_fields,
            options=extract_option_texts(next_q),
            quiz_result_id=quiz_result.get("quiz_id") if is_complete else None,
            session=updated_session.model_dump(),
            tool_calls=[{k: v for k, v in call.items() if k != "result"} for call in tool_calls],
            turn_number=final_turn_number,
        )
        return with_tts(response_payload, updated_session.language)

    hint = "Please choose one of the options!" if session.language == "en" else "請從選項中選一個喜歡的答案喔！"
    response_fields = build_jti_quiz_question_fields(
        q,
        current_q_num,
        session.language,
        prefix=hint,
    )
    response_message = response_fields["message"]

    logger.info(f"QUIZ 無法判斷選項，hardcode 提示: {request.message}")

    if request.turn_number:
        conversation_logger.delete_turns_from(request.session_id, request.turn_number)

    log_result = conversation_logger.log_conversation(
        session_id=request.session_id,
        user_message=request.message,
        agent_response=response_message,
        tool_calls=[],
        session_state=build_session_state(session),
        mode="jti",
    )
    final_turn_number = log_result[1] if log_result else None

    response_payload = ChatResponse(
        **response_fields,
        options=extract_option_texts(q),
        session=session.model_dump(),
        tool_calls=[],
        turn_number=final_turn_number,
    )
    return with_tts(response_payload, session.language)

"""Shared runtime quiz flow helpers for managed-app chat endpoints."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import HTTPException

from app.routers.tts_utils import attach_tts_message_id
from app.schemas.chat import ChatResponse
from app.services.general.quiz_helpers import (
    _judge_user_choice,
    _pause_quiz_and_respond,
    build_session_state,
)
from app.services.general.quiz_response import (
    QUIZ_OPENING,
    build_quiz_question_fields,
    build_quiz_response_fields,
    extract_option_texts,
    resolve_quiz_copy,
)
from app.services.quiz.config import QuizFlowConfig
from app.tools.jti.quiz import get_total_questions
from app.tools.jti.tool_executor import ToolExecutor

logger = logging.getLogger(__name__)

_ALREADY_DONE_COPY = {
    "zh": "你已經完成過測驗囉！這次對話只能測驗一次。如果想重新測驗，請重新整理頁面開始新的對話。",
    "en": "You've already completed the quiz! Please refresh the page to start a new session.",
}
_CHOOSE_OPTION_COPY = {
    "zh": "請從選項中選一個喜歡的答案喔！",
    "en": "Please choose one of the options!",
}


def _attach_tts(
    response: ChatResponse,
    language: str,
    config: QuizFlowConfig,
) -> ChatResponse:
    if not config.tts_manager_getter:
        return response

    tts_manager = config.tts_manager_getter()
    if not tts_manager:
        return response
    return attach_tts_message_id(response, language, tts_manager)


async def _pause_quiz(
    session: Any,
    request: Any,
    config: QuizFlowConfig,
) -> ChatResponse:
    response = await _pause_quiz_and_respond(
        session_id=request.session_id,
        log_user_message=request.message,
        session=session,
        config=config,
    )
    return _attach_tts(ChatResponse(**response), session.language, config)


async def execute_quiz_start(
    session_id: str,
    user_message: str = "[API] quiz_start",
    *,
    config: QuizFlowConfig,
) -> ChatResponse:
    """Start a quiz for both direct API and keyword-triggered chat flow."""
    session_manager = config.session_manager_getter()
    conversation_logger = config.conversation_logger_getter()
    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    language = session.language

    if session.step.value == "DONE":
        response_message = resolve_quiz_copy(
            config,
            "already_done",
            language,
            _ALREADY_DONE_COPY.get(language, _ALREADY_DONE_COPY["zh"]),
        )

        log_result = conversation_logger.log_conversation(
            session_id=session_id,
            user_message=user_message,
            agent_response=response_message,
            tool_calls=[],
            session_state=build_session_state(session),
            mode=config.mode,
        )
        final_turn_number = log_result[1] if log_result else None
        response_fields = build_quiz_response_fields(
            response_message,
            language,
            config=config,
        )
        return ChatResponse(
            **response_fields,
            session=session.model_dump(),
            tool_calls=[],
            turn_number=final_turn_number,
        )

    executor = ToolExecutor(config)
    tool_result = await executor.execute("start_quiz", {"session_id": session_id})
    updated_session = session_manager.get_session(session_id)

    if not tool_result.get("success"):
        error_message = tool_result.get("error", "start_quiz failed")
        fallback_language = updated_session.language if updated_session else session.language
        response_fields = build_quiz_response_fields(
            error_message,
            fallback_language,
            config=config,
        )
        return ChatResponse(
            **response_fields,
            session=updated_session.model_dump() if updated_session else session.model_dump(),
            tool_calls=[],
            error=error_message,
        )

    active_session = updated_session or session
    language = active_session.language
    question = tool_result.get("current_question") or (
        updated_session.current_question if updated_session else None
    )
    opening = resolve_quiz_copy(
        config,
        "opening",
        language,
        QUIZ_OPENING.get(language, QUIZ_OPENING["zh"]),
    )
    response_fields = build_quiz_question_fields(
        question,
        1,
        language,
        prefix=opening,
        config=config,
    )
    tool_args = {"session_id": session_id}
    log_tool_call = {"tool": "start_quiz", "args": tool_args, "result": tool_result}

    log_result = conversation_logger.log_conversation(
        session_id=session_id,
        user_message=user_message,
        agent_response=response_fields["message"],
        tool_calls=[log_tool_call],
        session_state=build_session_state(active_session),
        mode=config.mode,
    )
    final_turn_number = log_result[1] if log_result else None

    return ChatResponse(
        **response_fields,
        options=extract_option_texts(question),
        session=active_session.model_dump(),
        tool_calls=[{"tool": "start_quiz", "args": tool_args}],
        turn_number=final_turn_number,
    )


async def handle_quiz_message(
    session,
    request,
    *,
    config: QuizFlowConfig,
) -> ChatResponse | None:
    """Handle active quiz answers. Return None to continue non-quiz flow."""
    if session.step.value != "QUIZ" or not session.current_question:
        return None

    session_manager = config.session_manager_getter()
    conversation_logger = config.conversation_logger_getter()

    question = session.current_question
    total_questions = get_total_questions(
        session.language,
        store_name=config.store_name,
    )
    current_q_num = len(session.answers) + 1

    if request.message.strip() == "中斷":
        return await _pause_quiz(session, request, config)

    logger.info(
        "[測驗進度] 第 %d/%d 題 | 題目: %s...",
        current_q_num,
        total_questions,
        question.get("text", "")[:30],
    )

    user_choice = await _judge_user_choice(request.message, question)
    logger.info(f"[答題判斷] 使用者回答: '{request.message}' -> 判定選項: {user_choice}")

    if user_choice == "PAUSE":
        return await _pause_quiz(session, request, config)

    executor = ToolExecutor(config)
    if user_choice:
        tool_result = await executor.execute(
            "submit_answer",
            {
                "session_id": request.session_id,
                "user_choice": user_choice,
            },
        )
        updated_session = tool_result.pop(
            "_updated_session",
            None,
        ) or session_manager.get_session(request.session_id)
        tool_calls = [
            {
                "tool": "submit_answer",
                "args": {"user_choice": user_choice},
                "result": tool_result,
            }
        ]
        logger.info(
            "[答題結果] 選項: %s | 已答: %d/%d 題",
            user_choice,
            len(updated_session.answers),
            total_questions,
        )
        if updated_session.quiz_scores:
            scores_str = " | ".join(
                f"{key}:{value}"
                for key, value in sorted(
                    updated_session.quiz_scores.items(),
                    key=lambda item: -item[1],
                )
            )
            logger.info(f"[當前分數] {scores_str}")

        is_complete = tool_result.get("is_complete")
        next_q = tool_result.get("next_question") if not is_complete else None

        if is_complete:
            response_message = tool_result.get("message", "")
            response_fields = build_quiz_response_fields(
                response_message,
                updated_session.language,
                tts_source=tool_result.get("tts_text") or response_message,
                config=config,
            )
            if config.agent:
                config.agent.remove_session(request.session_id)
            updated_session.chat_history.append(
                {"role": "assistant", "content": response_message}
            )
            session_manager.update_session(updated_session)
        else:
            q_num = len(updated_session.answers) + 1
            response_fields = build_quiz_question_fields(
                next_q,
                q_num,
                updated_session.language,
                config=config,
            )
            response_message = response_fields["message"]

        log_result = conversation_logger.log_conversation(
            session_id=request.session_id,
            user_message=request.message,
            agent_response=response_message,
            tool_calls=tool_calls,
            session_state=build_session_state(updated_session),
            mode=config.mode,
        )
        final_turn_number = log_result[1] if log_result else None
        logger.info(f"QUIZ 作答成功: {request.message} -> {user_choice}")

        quiz_result = tool_result.get("quiz_result") or {}
        response_payload = ChatResponse(
            **response_fields,
            options=extract_option_texts(next_q),
            quiz_result_id=quiz_result.get("quiz_id") if is_complete else None,
            session=updated_session.model_dump(),
            tool_calls=[
                {key: value for key, value in call.items() if key != "result"}
                for call in tool_calls
            ],
            turn_number=final_turn_number,
        )
        return _attach_tts(response_payload, updated_session.language, config)

    hint = resolve_quiz_copy(
        config,
        "choose_option",
        session.language,
        _CHOOSE_OPTION_COPY.get(session.language, _CHOOSE_OPTION_COPY["zh"]),
    )

    response_fields = build_quiz_question_fields(
        question,
        current_q_num,
        session.language,
        prefix=hint,
        config=config,
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
        mode=config.mode,
    )
    final_turn_number = log_result[1] if log_result else None

    response_payload = ChatResponse(
        **response_fields,
        options=extract_option_texts(question),
        session=session.model_dump(),
        tool_calls=[],
        turn_number=final_turn_number,
    )
    return _attach_tts(response_payload, session.language, config)

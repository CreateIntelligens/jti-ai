"""Reusable managed-app chat orchestration behind compatibility routers."""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException

from app.models.session import SessionStep
from app.routers.tts_utils import attach_tts_message_id
from app.schemas.chat import (
    ChatRequest,
    ChatResponse,
    CreateSessionRequest,
    CreateSessionResponse,
)
from app.services.general.quiz_helpers import (
    _get_or_rebuild_session,
    build_session_state,
    is_quiz_start_intent,
)
from app.services.general.quiz_runtime import execute_quiz_start, handle_quiz_message
from app.services.quiz.config import QuizFlowConfig


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ManagedChatConfig:
    app: str
    opening_messages: Mapping[str, str]
    session_manager_getter: Callable[[], Any]
    conversation_logger_getter: Callable[[], Any]
    agent: Any
    quiz: QuizFlowConfig
    tts_manager_getter: Callable[[], Any] | None = None


class ManagedChatService:
    """Run a fixed managed app's chat flow with injected persistence/config."""

    def __init__(self, config: ManagedChatConfig) -> None:
        self.config = config

    def _attach_tts(self, response: ChatResponse, language: str) -> ChatResponse:
        if not self.config.tts_manager_getter:
            return response

        manager = self.config.tts_manager_getter()
        if not manager:
            return response
        return attach_tts_message_id(response, language, manager)

    async def create_session(self, request: CreateSessionRequest) -> CreateSessionResponse:
        session_manager = self.config.session_manager_getter()
        if request.previous_session_id:
            self.config.agent.remove_session(request.previous_session_id)
            logger.info(
                "Cleaned up previous %s chat session: %s...",
                self.config.app,
                request.previous_session_id[:8],
            )

        session = session_manager.create_session(language=request.language)
        opening = self.config.opening_messages.get(
            request.language,
            self.config.opening_messages["zh"],
        )
        return CreateSessionResponse(
            session_id=session.session_id,
            opening_message=opening,
        )

    async def send_message(self, request: ChatRequest) -> ChatResponse:
        session_manager = self.config.session_manager_getter()
        conversation_logger = self.config.conversation_logger_getter()
        session = _get_or_rebuild_session(request.session_id, self.config.quiz)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        preserved_selected_questions = (
            deepcopy(session.selected_questions) if session.selected_questions else None
        )

        if request.turn_number is not None:
            deleted_count = conversation_logger.delete_turns_from(
                request.session_id,
                request.turn_number,
            )
            if deleted_count > 0:
                all_logs = conversation_logger.get_session_logs(request.session_id)
                logs = [
                    log
                    for log in all_logs
                    if log.get("mode") == self.config.quiz.mode
                ]
                if logs:
                    session = session_manager.rebuild_session_from_logs(
                        request.session_id,
                        logs,
                    )
                    if not session:
                        raise HTTPException(
                            status_code=500,
                            detail="Failed to rebuild session from logs",
                        )
                else:
                    session.step = SessionStep.WELCOME
                    session.answers = {}
                    session.current_question = None
                    session.current_q_index = 0
                    session.selected_questions = None
                    session.quiz_scores = {}
                    session.quiz_result_id = None
                    session.quiz_result = None
                    session.chat_history = []
                    session = session_manager.update_session(session)

                if logs and session and preserved_selected_questions:
                    session.selected_questions = preserved_selected_questions
                    if session.step == SessionStep.QUIZ:
                        if session.current_q_index < len(preserved_selected_questions):
                            session.current_question = preserved_selected_questions[
                                session.current_q_index
                            ]
                        else:
                            session.current_question = None
                    session = session_manager.update_session(session)

                self.config.agent.remove_session(request.session_id)

        quiz_result = await handle_quiz_message(
            session,
            request,
            config=self.config.quiz,
        )
        if quiz_result:
            return quiz_result

        intent_kwargs = {}
        if self.config.quiz.keywords:
            intent_kwargs["start_keywords"] = self.config.quiz.keywords
        if self.config.quiz.negative_keywords:
            intent_kwargs["negative_keywords"] = self.config.quiz.negative_keywords
        should_start_quiz = is_quiz_start_intent(request.message, **intent_kwargs)
        if should_start_quiz and session.step.value in ("DONE", "WELCOME"):
            if session.step.value == "DONE":
                session.step = SessionStep.WELCOME
                session_manager.update_session(session)
            if request.turn_number:
                conversation_logger.delete_turns_from(
                    request.session_id,
                    request.turn_number,
                )
            quiz_response = await execute_quiz_start(
                request.session_id,
                user_message=request.message,
                config=self.config.quiz,
            )
            return self._attach_tts(quiz_response, session.language)

        result = await self.config.agent.chat(
            session_id=request.session_id,
            user_message=request.message,
        )

        if request.turn_number:
            conversation_logger.delete_turns_from(
                request.session_id,
                request.turn_number,
            )

        log_result = conversation_logger.log_conversation(
            session_id=request.session_id,
            user_message=request.message,
            agent_response=result["message"],
            tool_calls=result.get("tool_calls", []),
            session_state=build_session_state(session),
            mode=self.config.quiz.mode,
            citations=result.get("citations"),
        )
        final_turn_number = log_result[1] if log_result else None

        response = ChatResponse(**result, turn_number=final_turn_number)
        return self._attach_tts(response, session.language)

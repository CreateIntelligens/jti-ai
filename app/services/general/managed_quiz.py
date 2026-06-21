"""Reusable explicit quiz endpoint orchestration for managed apps."""

from __future__ import annotations

from fastapi import HTTPException

from app.models.session import SessionStep
from app.schemas.chat import ChatResponse
from app.services.general.quiz_helpers import (
    _get_or_rebuild_session,
    _pause_quiz_and_respond,
)
from app.services.general.quiz_runtime import execute_quiz_start
from app.services.quiz.config import QuizFlowConfig


class ManagedQuizService:
    """Run explicit quiz actions with an injected managed-app config."""

    def __init__(self, config: QuizFlowConfig) -> None:
        self.config = config

    async def start(self, session_id: str) -> ChatResponse:
        session_manager = self.config.session_manager_getter()
        session = session_manager.get_session(session_id)
        if session and session.step.value == "DONE":
            session.step = SessionStep.WELCOME
            session_manager.update_session(session)
        return await execute_quiz_start(session_id, config=self.config)

    async def pause(self, session_id: str) -> ChatResponse:
        session = _get_or_rebuild_session(session_id, self.config)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        response = await _pause_quiz_and_respond(
            session_id=session_id,
            log_user_message="[API] quiz_pause",
            session=session,
            config=self.config,
        )
        return ChatResponse(**response)

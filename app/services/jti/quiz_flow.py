"""JTI configuration for the shared General quiz runtime."""

from __future__ import annotations

import app.deps as deps
from app.services.general.tts import get_managed_tts_job_manager
from app.services.jti.main_agent import main_agent
from app.services.quiz.config import JTI_STORE_NAME, QuizFlowConfig
from app.services.tts_text import prepare_tts_text


def _get_session_manager():
    return deps.get_jti_session_manager()


def _get_conversation_logger():
    return deps.get_jti_conversation_logger()


def _get_tts_manager():
    return get_managed_tts_job_manager("jti")


JTI_QUIZ_CONFIG = QuizFlowConfig(
    session_manager_getter=_get_session_manager,
    conversation_logger_getter=_get_conversation_logger,
    tts_manager_getter=_get_tts_manager,
    agent=main_agent,
    store_name=JTI_STORE_NAME,
    mode="jti",
    tts_fn=prepare_tts_text,
)

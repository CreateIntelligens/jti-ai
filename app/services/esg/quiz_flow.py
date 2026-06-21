"""ESG configuration for the shared quiz runtime."""

from __future__ import annotations

from typing import Optional

import app.deps as deps
from app.services.esg.main_agent import main_agent
from app.services.quiz.config import ESG_STORE_NAME, QuizFlowConfig

ESG_QUIZ_KEYWORDS = ["測驗", "quiz", "問答"]
ESG_QUIZ_NEGATIVE_KEYWORDS: list[str] = []
ESG_QUIZ_COPY = {
    "opening": {
        "zh": "來測測你對三立永續的了解吧！請選出正確答案：",
        "en": "Test your knowledge of SET's sustainability journey! Pick the correct answer:",
    },
    "already_done": {
        "zh": "你已經作答過囉！想再玩一次請重新整理頁面開始新的對話。",
        "en": "You've already answered! Refresh the page to start a new session.",
    },
}


def _get_session_manager():
    return deps.get_esg_session_manager()


def _get_conversation_logger():
    return deps.get_esg_conversation_logger()


def _no_op_tts(_text: str, _language: str) -> Optional[str]:
    return None


ESG_QUIZ_CONFIG = QuizFlowConfig(
    session_manager_getter=_get_session_manager,
    conversation_logger_getter=_get_conversation_logger,
    agent=main_agent,
    store_name=ESG_STORE_NAME,
    mode="esg",
    copy_templates=ESG_QUIZ_COPY,
    tts_fn=_no_op_tts,
    keywords=ESG_QUIZ_KEYWORDS,
    negative_keywords=ESG_QUIZ_NEGATIVE_KEYWORDS,
)

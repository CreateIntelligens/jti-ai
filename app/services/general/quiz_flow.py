from typing import Optional
from app.services.quiz.config import QuizFlowConfig
from app.services.general.main_agent import main_agent
from app.utils import LazyProxy

deps = LazyProxy("app.deps")


def _no_op_tts(text: str, language: str) -> Optional[str]:
    # General stores have no TTS; returning None suppresses it. Leaving
    # tts_fn=None would instead fall through to the JTI TTS path.
    return None


def build_general_quiz_config(
    store_name: str,
    copy: Optional[dict] = None,
    keywords: Optional[list[str]] = None,
) -> QuizFlowConfig:
    """Build a QuizFlowConfig for a general store session."""
    return QuizFlowConfig(
        session_manager_getter=deps.get_general_chat_session_manager,
        conversation_logger_getter=deps.get_general_conversation_logger,
        agent=main_agent,
        store_name=store_name,
        mode="general",
        copy_templates=copy or {},
        tts_fn=_no_op_tts,
        keywords=keywords or [],
    )

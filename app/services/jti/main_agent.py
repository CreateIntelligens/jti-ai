"""JTI configuration for the shared General managed-agent runtime."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from google.genai import types

import app.deps as deps
from app.models.session import Session
from app.models_config import CHAT_MODEL as _DEFAULT_CHAT_MODEL
from app.services.agent_utils import build_search_knowledge_decl, normalize_language
from app.services.general.managed_agent import ManagedAppAgent, ManagedAppAgentConfig
from app.services.jti.agent_prompts import (
    PERSONA,
    SESSION_STATE_TEMPLATES,
    build_system_instruction,
)
from app.services.jti.runtime_settings import load_runtime_settings_from_prompt_manager
from app.services.tts_text import prepare_tts_text


_SEARCH_KNOWLEDGE_DECL = build_search_knowledge_decl(
    domain_description=(
        "搜尋知識庫，查詢產品資訊、規格、相關活動或其他常見問題。"
        "若使用者一次提出多個獨立主題的問題，請在同一次呼叫中將每個獨立問題各自填入 queries 陣列。"
    ),
    queries_description=(
        "使用者問題拆解後的獨立查詢列表，每一筆應為完整的問題描述（包含上下文）。"
        "Keep query language aligned with the conversation/user question: "
        "English questions use English queries; Chinese questions use Chinese queries. "
        "若使用者只有一個問題，仍以單元素陣列回傳。"
    ),
)

_RAG_TOOL = types.Tool(function_declarations=[_SEARCH_KNOWLEDGE_DECL])


def _store_name_for_language(language: str) -> str:
    return "__jti__en" if normalize_language(language) == "en" else "__jti__"


def _get_session_manager() -> Any:
    return deps.get_jti_session_manager()


def _build_session_state(session: Session) -> str:
    template = SESSION_STATE_TEMPLATES.get(
        session.language,
        SESSION_STATE_TEMPLATES["zh"],
    )
    not_yet = "Not calculated yet" if session.language == "en" else "尚未計算"
    now = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M")
    return template.format(
        step_value=session.step.value,
        answers_count=len(session.answers),
        quiz_result=session.quiz_result_id or not_yet,
        now=now,
    )


def _post_process_chat_result(
    session: Session,
    response_text: str,
    _citations: list[dict] | None,
    _extra_meta: dict[str, Any],
) -> dict[str, Any]:
    return {"tts_text": prepare_tts_text(response_text, session.language)}


def _fallback_message(_language: str) -> str:
    return "AI目前故障 請聯絡"


JTI_AGENT_CONFIG = ManagedAppAgentConfig(
    app="jti",
    model_name=_DEFAULT_CHAT_MODEL,
    session_manager_getter=_get_session_manager,
    persona_map_attr="jti_profiles_by_prompt",
    active_prompt_id_attr="jti_active_prompt_id",
    store_name_for_language=_store_name_for_language,
    rag_source_type="jti_knowledge",
    rag_tool_declaration=_RAG_TOOL,
    persona=PERSONA,
    build_system_instruction=build_system_instruction,
    load_runtime_settings=load_runtime_settings_from_prompt_manager,
    build_session_state=_build_session_state,
    fallback_message=_fallback_message,
    post_process_chat_result=_post_process_chat_result,
)


class MainAgent(ManagedAppAgent):
    """JTI's thin configuration shell over the shared managed-agent runtime."""

    CHAT_MODEL = _DEFAULT_CHAT_MODEL

    def __init__(self) -> None:
        super().__init__(JTI_AGENT_CONFIG)


main_agent = MainAgent()

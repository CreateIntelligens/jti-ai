"""ESG configuration for the shared managed-agent runtime."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from google.genai import types

import app.deps as deps
from app.models.session import Session
from app.models_config import CHAT_MODEL as _DEFAULT_CHAT_MODEL
from app.services.agent_utils import build_search_knowledge_decl, normalize_language
from app.services.esg.agent_prompts import (
    PERSONA,
    SESSION_STATE_TEMPLATES,
    build_system_instruction,
)
from app.services.esg.runtime_settings import load_runtime_settings_from_prompt_manager
from app.services.general.managed_agent import ManagedAppAgent, ManagedAppAgentConfig

_SEARCH_KNOWLEDGE_DECL = build_search_knowledge_decl(
    domain_description=(
        "搜尋 ESG 知識庫，查詢永續、環境、社會責任、公司治理及相關主題。"
        "若使用者一次提出多個獨立問題，請將每個完整問題分別放入 queries 陣列。"
    ),
    queries_description=(
        "使用者問題拆解後的獨立查詢列表，每筆需保留必要上下文，並維持使用者的語言。"
    ),
)
_RAG_TOOL = types.Tool(function_declarations=[_SEARCH_KNOWLEDGE_DECL])


def _store_name_for_language(language: str) -> str:
    return "__esg__en" if normalize_language(language) == "en" else "__esg__"


def _get_session_manager() -> Any:
    return deps.get_esg_session_manager()


def _build_session_state(session: Session) -> str:
    template = SESSION_STATE_TEMPLATES.get(
        session.language,
        SESSION_STATE_TEMPLATES["zh"],
    )
    now = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M")
    return template.format(now=now)


def _fallback_message(language: str) -> str:
    if normalize_language(language) == "en":
        return "The assistant is temporarily unavailable. Please try again later."
    return "目前無法取得回覆，請稍後再試。"


ESG_AGENT_CONFIG = ManagedAppAgentConfig(
    app="esg",
    model_name=_DEFAULT_CHAT_MODEL,
    session_manager_getter=_get_session_manager,
    persona_map_attr="esg_persona_by_prompt",
    active_prompt_id_attr="esg_active_prompt_id",
    store_name_for_language=_store_name_for_language,
    rag_source_type="esg_knowledge",
    rag_tool_declaration=_RAG_TOOL,
    persona=PERSONA,
    build_system_instruction=build_system_instruction,
    load_runtime_settings=load_runtime_settings_from_prompt_manager,
    build_session_state=_build_session_state,
    fallback_message=_fallback_message,
)


class EsgMainAgent(ManagedAppAgent):
    """ESG's fixed-app shell over the shared managed-agent runtime."""

    CHAT_MODEL = _DEFAULT_CHAT_MODEL

    def __init__(self) -> None:
        super().__init__(ESG_AGENT_CONFIG)


main_agent = EsgMainAgent()

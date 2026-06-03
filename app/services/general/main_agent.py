"""
General Knowledge Base Agent

Architecture:
- Inherits BaseAgent → gets Gemini chat session management, function-calling
  RAG tool loop, dual-query RAG, chat history sync, and LRU session cache
  for free.
- Key difference from JTI/HCIoT: store_name is dynamic (per-session),
  not fixed per language.  We override _get_store_name_for_session to
  pull store_name from the Session.metadata dict.
"""

import logging
from datetime import datetime, timezone
from typing import Any

from google.genai import types

import app.deps as deps
from app.models.session import Session
from app.models_config import DEFAULT_RAG_MODEL
from app.services.agent_utils import build_search_knowledge_decl, normalize_language
from app.services.base_agent import BaseAgent
from app.services.general.agent_prompts import (
    PERSONA,
    SESSION_STATE_TEMPLATES,
    build_system_instruction,
)
from app.services.general.runtime_settings import (
    load_runtime_settings_from_prompt_manager,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# RAG function declaration
# ---------------------------------------------------------------------------
_SEARCH_KNOWLEDGE_DECL = build_search_knowledge_decl(
    domain_description=(
        "搜尋知識庫，查詢與使用者問題相關的資料。"
        "若使用者一次提出多個獨立主題的問題，請在同一次呼叫中將每個獨立問題各自填入 queries 陣列。"
    ),
    queries_description=(
        "使用者問題拆解後的獨立查詢列表，每一筆應為完整的問題描述（包含上下文）。"
        "請使用與使用者問題相同的語言撰寫 query；英文問題用英文查詢，中文問題用中文查詢。"
        "若使用者只有一個問題，仍以單元素陣列回傳。"
    ),
)

_RAG_TOOL = types.Tool(function_declarations=[_SEARCH_KNOWLEDGE_DECL])


def _get_session_manager():
    return deps.get_general_chat_session_manager()


def _get_app_rag_tool(managed_app: str | None) -> types.Tool | None:
    if managed_app == "jti":
        from app.services.jti.main_agent import _RAG_TOOL as jti_rag_tool

        return jti_rag_tool
    if managed_app == "hciot":
        from app.services.hciot.main_agent import _RAG_TOOL as hciot_rag_tool

        return hciot_rag_tool
    return None


class MainAgent(BaseAgent):
    """General knowledge-base chat agent.

    Unlike JTI/HCIoT, the store_name is dynamic (comes from session.metadata).
    """

    CHAT_MODEL = DEFAULT_RAG_MODEL

    def __init__(self):
        super().__init__(model_name=self.CHAT_MODEL)

    # --- Required BaseAgent hooks ---

    @property
    def _session_manager(self):
        return _get_session_manager()

    @property
    def _persona_map_attr(self) -> str:
        # General doesn't use persona-per-prompt map
        return "_unused_general_persona"

    @property
    def _active_prompt_id_attr(self) -> str:
        # General uses the shared active_prompt_id field
        return "active_prompt_id"

    @staticmethod
    def _get_store_name_for_language(language: str) -> str:
        # Not meaningful for general (store is dynamic), but provide a sane default
        return "__general__"

    def _get_store_name_for_session(self, session: Session) -> str:
        """Override: pull store_name from session.metadata (set during create)."""
        return session.metadata.get("store_name") or "__general__"

    @staticmethod
    def _is_managed_store_session(session: Session) -> bool:
        """A managed store (the fixed JTI/HCIoT knowledge pages) is keyed by
        language (zh/en) at write time and always carries a non-empty
        managed_language. Dynamic stores — general OR key-mapped — leave it empty
        and are keyed by store_name instead. managed_app truthiness is NOT a valid
        discriminator: dynamic stores carry managed_app="general" (or an app name
        via key mapping) yet still write under the general_knowledge namespace.
        """
        return bool(session.metadata.get("managed_language"))

    def _get_rag_source_type_for_session(self, session: Session) -> list[str]:
        """Dynamic source_type list based on whether the store is managed."""
        if self._is_managed_store_session(session):
            return [f"{session.metadata.get('managed_app')}_knowledge"]
        return ["general_knowledge"]

    def _get_rag_search_language_for_session(self, session: Session) -> str | None:
        """Override: dynamic stores key RAG entries by store_name (not zh/en).

        When the session is bound to a managed app (JTI/HCIoT), defer to
        managed_language so we hit the same index they wrote.
        """
        if self._is_managed_store_session(session):
            managed_lang = session.metadata.get("managed_language")
            return normalize_language(managed_lang) if managed_lang else None
        return session.metadata.get("store_name")

    @property
    def _rag_source_type(self) -> str:
        return "general_knowledge"

    @property
    def _rag_tool_declaration(self) -> types.Tool | None:
        return _RAG_TOOL

    def _get_rag_tool_declaration_for_session(self, session: Session) -> types.Tool | None:
        if self._is_managed_store_session(session):
            return _get_app_rag_tool(session.metadata.get("managed_app")) or _RAG_TOOL
        return _RAG_TOOL

    def _get_default_persona(self, language: str) -> str:
        return PERSONA.get(language, PERSONA["zh"])

    def _build_system_instruction(self, persona, language, response_rule_sections, max_response_chars):
        return build_system_instruction(
            persona=persona, language=language,
            response_rule_sections=response_rule_sections,
            max_response_chars=max_response_chars,
        )

    def _load_runtime_settings(self, prompt_manager, prompt_id, store_name):
        return load_runtime_settings_from_prompt_manager(prompt_manager, prompt_id, store_name=store_name)

    def _load_default_runtime_settings(self):
        return load_runtime_settings_from_prompt_manager(None)

    def _get_session_state(self, session: Session) -> str:
        template = SESSION_STATE_TEMPLATES.get(session.language, SESSION_STATE_TEMPLATES["zh"])
        now = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M")
        return template.format(now=now)

    def _get_question_label(self, language: str) -> str:
        return "User question:" if language == "en" else "使用者問題："

    def _get_chat_fallback_message(self, language: str) -> str:
        return "Sorry, an error occurred. Please try again." if language == "en" else "抱歉，發生錯誤，請稍後再試。"

    # --- Session helpers for router ---

    def create_session(
        self,
        *,
        store_name: str,
        model: str | None = None,
        system_instruction: str | None = None,
        language: str = "zh",
        managed_app: str | None = None,
        managed_language: str | None = None,
    ) -> Session:
        """Create a general-KB Session via the shared session manager.

        Stores store_name and managed_app in session.metadata so
        _get_store_name_for_session and _get_rag_source_type_for_session work.
        """
        sm = self._session_manager
        effective_language = normalize_language(managed_language or language)
        session = sm.create_session(language=effective_language)
        session.metadata = {
            "store_name": store_name,
            "model": model or self.CHAT_MODEL,
            "managed_app": managed_app,
            "managed_language": managed_language,
        }
        if system_instruction:
            session.metadata["system_instruction"] = system_instruction
        sm.update_session(session)
        return session

    def _get_system_instruction(self, session: Session) -> str:
        """Override: use per-session system instruction if stored in metadata."""
        custom = session.metadata.get("system_instruction")
        if custom:
            return custom

        # Fall back to the standard persona + rules pipeline
        return super()._get_system_instruction(session)

    def _get_active_prompt_context(self, language: str = "zh"):
        """Override: general uses per-store prompt, not a fixed store name.

        We can't resolve store_name without a session here, so fall back
        to the default persona.
        """
        try:
            from app import deps
            prompt_manager = getattr(deps, "prompt_manager", None)
        except Exception:
            return None, "__general__", None, None

        return prompt_manager, "__general__", None, None


# Singleton
main_agent = MainAgent()

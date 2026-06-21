"""Configurable fixed-app agent runtime shared by managed applications."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from google.genai import types

from app.models.session import Session
from app.services.base_agent import BaseAgent


@dataclass(frozen=True)
class ManagedAppAgentConfig:
    app: str
    model_name: str
    session_manager_getter: Callable[[], Any]
    persona_map_attr: str
    active_prompt_id_attr: str
    store_name_for_language: Callable[[str], str]
    rag_source_type: str
    rag_tool_declaration: types.Tool | None
    persona: Mapping[str, str]
    build_system_instruction: Callable[..., str]
    load_runtime_settings: Callable[..., Any]
    build_session_state: Callable[[Session], str]
    fallback_message: Callable[[str], str]
    post_process_chat_result: Callable[
        [Session, str, list[dict] | None, dict[str, Any]],
        dict[str, Any],
    ] | None = None
    rag_search_language: Callable[[Session], str | None] | None = None


class ManagedAppAgent(BaseAgent):
    """BaseAgent implementation whose fixed-app differences are injected."""

    def __init__(self, config: ManagedAppAgentConfig) -> None:
        self.config = config
        super().__init__(model_name=config.model_name)

    @property
    def _session_manager(self) -> Any:
        return self.config.session_manager_getter()

    @property
    def _persona_map_attr(self) -> str:
        return self.config.persona_map_attr

    @property
    def _active_prompt_id_attr(self) -> str:
        return self.config.active_prompt_id_attr

    def _get_store_name_for_language(self, language: str) -> str:
        return self.config.store_name_for_language(language)

    @property
    def _rag_source_type(self) -> str:
        return self.config.rag_source_type

    @property
    def _rag_tool_declaration(self) -> types.Tool | None:
        return self.config.rag_tool_declaration

    def _get_default_persona(self, language: str) -> str:
        return self.config.persona.get(language, self.config.persona["zh"])

    def _build_system_instruction(
        self,
        persona: str,
        language: str,
        response_rule_sections: dict,
        max_response_chars: int,
    ) -> str:
        return self.config.build_system_instruction(
            persona=persona,
            language=language,
            response_rule_sections=response_rule_sections,
            max_response_chars=max_response_chars,
        )

    def _load_runtime_settings(self, prompt_manager, prompt_id, store_name) -> Any:
        return self.config.load_runtime_settings(
            prompt_manager,
            prompt_id,
            store_name=store_name,
        )

    def _load_default_runtime_settings(self) -> Any:
        return self.config.load_runtime_settings(None)

    def _get_rag_search_language_for_session(self, session: Session) -> str | None:
        if self.config.rag_search_language is None:
            return super()._get_rag_search_language_for_session(session)
        return self.config.rag_search_language(session)

    def _get_session_state(self, session: Session) -> str:
        return self.config.build_session_state(session)

    def _get_question_label(self, language: str) -> str:
        return "User question:" if language == "en" else "使用者問題："

    def _post_process_chat_result(
        self,
        session: Session,
        response_text: str,
        citations: list[dict] | None,
        extra_meta: dict[str, Any],
    ) -> dict[str, Any]:
        if self.config.post_process_chat_result is None:
            return {}
        return self.config.post_process_chat_result(
            session,
            response_text,
            citations,
            extra_meta,
        )

    def _get_chat_fallback_message(self, language: str) -> str:
        return self.config.fallback_message(language)

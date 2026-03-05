"""
HCIoT main agent - patient education chat flow.
"""

import logging
import os
import time
from typing import Dict

from google.genai import types

from app.models.session import Session
import app.services.gemini_service as _gemini_service
from app.services.agent_utils import (
    extract_response_text,
    normalize_language,
    strip_citations,
)
from app.services.base_agent import BaseAgent
from app.services.gemini_clients import get_client_for_store
from app.services.hciot.agent_prompts import (
    PERSONA,
    SESSION_STATE_TEMPLATES,
    build_intent_prompt,
    build_system_instruction,
)
from app.services.hciot.runtime_settings import (
    HCIOT_STORE_NAME,
    load_runtime_settings_from_prompt_manager,
)
from app.services.session.session_manager_factory import get_hciot_session_manager

session_manager = get_hciot_session_manager()
logger = logging.getLogger(__name__)
FILE_SEARCH_MODEL = "gemini-3.1-flash-lite-preview"


class HciotMainAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            model_name=os.getenv("GEMINI_MODEL_NAME", "gemini-3.1-flash-lite-preview"),
        )

    @property
    def _session_manager(self):
        return session_manager

    @property
    def _persona_map_attr(self) -> str:
        return "hciot_persona_by_prompt"

    @staticmethod
    def _get_store_name_for_language(language: str) -> str:
        return "__hciot__en" if normalize_language(language) == "en" else HCIOT_STORE_NAME

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
        return template.format(step_value=session.step.value)

    @staticmethod
    def _get_file_search_store_name(language: str) -> str | None:
        lang_upper = normalize_language(language).upper()
        store_id = os.getenv(f"HCIOT_STORE_ID_{lang_upper}") or os.getenv("HCIOT_STORE_ID")
        if not store_id:
            return None
        if store_id.startswith("fileSearchStores/"):
            return store_id
        return f"fileSearchStores/{store_id}"

    def _file_search(self, query: str, language: str) -> str | None:
        store_name = self._get_file_search_store_name(language)
        if not store_name:
            logger.warning("未設定 HCIoT 知識庫，跳過 File Search")
            return None

        client = get_client_for_store(store_name)
        for attempt in range(3):
            try:
                response = client.models.generate_content(
                    model=FILE_SEARCH_MODEL,
                    contents=query,
                    config=types.GenerateContentConfig(
                        tools=[
                            types.Tool(
                                file_search=types.FileSearch(file_search_store_names=[store_name])
                            )
                        ],
                        thinking_config=types.ThinkingConfig(thinking_budget=0),
                    ),
                )
                return response.text.strip() if response.text else None
            except Exception as e:
                if "503" in str(e) and attempt < 2:
                    time.sleep(1)
                    continue
                logger.error(f"[HCIoT File Search] 失敗: {e}")
                return None

    def _check_intent_fast(self, query: str, language: str = "zh") -> str:
        try:
            response = _gemini_service.client.models.generate_content(
                model=FILE_SEARCH_MODEL,
                contents=build_intent_prompt(query),
                config=types.GenerateContentConfig(thinking_config=types.ThinkingConfig(thinking_budget=0)),
            )
            res = response.text.strip().upper() if response.text else "YES"
            return "NO" if "NO" in res else "YES"
        except Exception as e:
            logger.error(f"[HCIoT Intent Check] failed: {e}")
            return "YES"

    async def chat(self, session_id: str, user_message: str) -> Dict:
        try:
            if not _gemini_service.client:
                return {"error": "Gemini client not initialized", "message": "系統未正確初始化，請檢查 API Key 設定。"}

            session = session_manager.get_session(session_id)
            if session is None:
                return {"error": "Session not found", "message": "找不到對話記錄，請重新開始。"}

            kb_result = await self._concurrent_intent_and_search(user_message, session.language)

            enriched_message = (
                f"<知識庫查詢結果>\n{kb_result}\n</知識庫查詢結果>\n\n使用者問題：{user_message}"
                if kb_result
                else user_message
            )
            chat_session = self._get_or_create_chat_session(session)
            response = chat_session.send_message(enriched_message)

            if kb_result:
                self._clean_enriched_history(chat_session, user_message)

            final_message = extract_response_text(response)
            if not final_message:
                final_message = "目前無法回應，請稍後再試。"

            final_message = strip_citations(final_message)
            self._sync_history_to_db_background(session_id, user_message, final_message)
            updated_session = session_manager.get_session(session_id)

            return {
                "message": final_message,
                "session": updated_session.model_dump() if updated_session else None,
                "tool_calls": [],
            }
        except Exception as e:
            logger.error(f"HCIoT chat failed: {e}", exc_info=True)
            return {"error": str(e), "message": f"抱歉，發生錯誤：{str(e)}"}


main_agent = HciotMainAgent()

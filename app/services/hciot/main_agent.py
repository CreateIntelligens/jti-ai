"""
HCIoT main agent - patient education chat flow.
"""

import asyncio
import logging
import os
import time
from typing import Dict

from google.genai import types

from app.models.session import Session
import app.services.gemini_service as _gemini_service
from app.services.agent_utils import (
    build_chat_history,
    extract_response_text,
    normalize_language,
    strip_citations,
)
from app.services.gemini_clients import get_client_for_store
from app.services.hciot.agent_prompts import (
    PERSONA,
    SESSION_STATE_TEMPLATES,
    build_intent_prompt,
    build_system_instruction,
)
from app.services.hciot.runtime_settings import (
    HCIOT_STORE_NAME,
    SYSTEM_DEFAULT_PROMPT_ID,
    load_runtime_settings_from_prompt_manager,
)
from app.services.session.session_manager_factory import get_hciot_session_manager

session_manager = get_hciot_session_manager()
logger = logging.getLogger(__name__)
FILE_SEARCH_MODEL = "gemini-2.5-flash-lite-preview-09-2025"


class HciotMainAgent:
    def __init__(self):
        self.model_name = os.getenv("GEMINI_MODEL_NAME", "gemini-2.5-flash-lite-preview-09-2025")
        self._chat_sessions: Dict[str, any] = {}

    def _get_or_create_chat_session(self, session: Session):
        sid = session.session_id
        if sid in self._chat_sessions:
            return self._chat_sessions[sid]

        history = build_chat_history(session.chat_history) if session.chat_history else []

        system_instruction = self._get_system_instruction(session)
        config = types.GenerateContentConfig(
            system_instruction=[types.Part.from_text(text=system_instruction)],
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        )
        chat_session = _gemini_service.client.chats.create(
            model=self.model_name,
            config=config,
            history=history,
        )
        self._chat_sessions[sid] = chat_session
        return chat_session

    def _sync_history_to_db(self, session_id: str, user_message: str, assistant_message: str):
        session = session_manager.get_session(session_id)
        if not session:
            return
        session.chat_history.append({"role": "user", "content": user_message})
        session.chat_history.append({"role": "assistant", "content": assistant_message})
        session_manager.update_session(session)

    def _sync_history_to_db_background(self, session_id: str, user_message: str, assistant_message: str):
        try:
            loop = asyncio.get_running_loop()
            loop.run_in_executor(None, self._sync_history_to_db, session_id, user_message, assistant_message)
        except Exception:
            self._sync_history_to_db(session_id, user_message, assistant_message)

    def remove_session(self, session_id: str):
        self._chat_sessions.pop(session_id, None)

    def remove_all_sessions(self):
        self._chat_sessions.clear()

    @staticmethod
    def _get_store_name_for_language(language: str) -> str:
        return "__hciot__en" if normalize_language(language) == "en" else HCIOT_STORE_NAME

    @staticmethod
    def _get_active_prompt_context(language: str = "zh"):
        prompt_manager = None
        store_name = HciotMainAgent._get_store_name_for_language(language)
        prompt_id = SYSTEM_DEFAULT_PROMPT_ID
        persona = None
        normalized_language = normalize_language(language)
        try:
            from app import deps
            prompt_manager = getattr(deps, "prompt_manager", None)
            if prompt_manager:
                active = prompt_manager.get_active_prompt(store_name)
                if active:
                    prompt_id = active.id
                    persona = active.content
                    store_prompts = prompt_manager._load_store_prompts(store_name)
                    persona_map = getattr(store_prompts, "hciot_persona_by_prompt", None)
                    if isinstance(persona_map, dict):
                        persona_pair = persona_map.get(active.id)
                        if isinstance(persona_pair, dict):
                            value = persona_pair.get(normalized_language)
                            if isinstance(value, str) and value.strip():
                                persona = value
        except Exception:
            prompt_manager = None
        return prompt_manager, store_name, prompt_id, persona

    def _get_system_instruction(self, session: Session) -> str:
        try:
            prompt_manager, store_name, runtime_prompt_id, persona = self._get_active_prompt_context(session.language)
            runtime_settings = load_runtime_settings_from_prompt_manager(
                prompt_manager,
                runtime_prompt_id,
                store_name=store_name,
            )
        except Exception:
            runtime_settings = load_runtime_settings_from_prompt_manager(None)
            persona = None

        if not persona:
            persona = PERSONA.get(session.language, PERSONA["zh"])

        response_rule_sections = runtime_settings.response_rule_sections.get(
            session.language, runtime_settings.response_rule_sections.get("zh")
        )
        sections_payload = (
            response_rule_sections.model_dump()
            if hasattr(response_rule_sections, "model_dump")
            else response_rule_sections
        )
        return build_system_instruction(
            persona=persona,
            language=session.language,
            response_rule_sections=sections_payload,
            max_response_chars=runtime_settings.max_response_chars,
        )

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

    def _check_intent_fast(self, query: str) -> str:
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

            loop = asyncio.get_running_loop()
            t0 = time.time()
            intent_task = asyncio.ensure_future(loop.run_in_executor(None, self._check_intent_fast, user_message))
            search_task = asyncio.ensure_future(loop.run_in_executor(None, self._file_search, user_message, session.language))

            done, _ = await asyncio.wait([intent_task, search_task], return_when=asyncio.FIRST_COMPLETED)

            if intent_task in done and intent_task.result() == "NO":
                kb_result = None
            else:
                await asyncio.gather(intent_task, search_task)
                intent = intent_task.result()
                kb_result = search_task.result() if intent == "YES" else None
                logger.info(f"[HCIoT timing] intent={intent}, total={(time.time()-t0)*1000:.0f}ms")

            enriched_message = (
                f"<知識庫查詢結果>\n{kb_result}\n</知識庫查詢結果>\n\n使用者問題：{user_message}"
                if kb_result
                else user_message
            )
            chat_session = self._get_or_create_chat_session(session)
            response = chat_session.send_message(enriched_message)

            if kb_result and hasattr(chat_session, "_curated_history") and chat_session._curated_history:
                last_user = chat_session._curated_history[-2]
                if last_user.role == "user":
                    last_user.parts = [types.Part.from_text(text=user_message)]

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

"""
Base Agent - 共用的 Gemini chat session 管理邏輯

提供 JTI MainAgent 與 HCIoT HciotMainAgent 共用的：
- Gemini chat session 建立與快取
- MongoDB 歷史同步（含背景非同步寫入）
- session 清除
"""

import asyncio
import logging
import time
from typing import Any, Dict, Optional

from google.genai import types

from app.models.session import Session
import app.services.gemini_service as _gemini_service
from app.services.agent_utils import build_chat_history, normalize_language

logger = logging.getLogger(__name__)


class BaseAgent:
    """Gemini chat session 管理基底類別"""

    def __init__(self, model_name: str):
        self.model_name = model_name
        self._chat_sessions: Dict[str, Any] = {}

    # --- 子類必須實作 ---

    @property
    def _session_manager(self):
        raise NotImplementedError

    @property
    def _persona_map_attr(self) -> str:
        """Attribute name on StorePrompts for persona mapping (e.g. 'jti_persona_by_prompt')."""
        raise NotImplementedError

    @staticmethod
    def _get_store_name_for_language(language: str) -> str:
        raise NotImplementedError

    def _get_default_persona(self, language: str) -> str:
        """Return default persona text when no DB persona is configured."""
        raise NotImplementedError

    def _build_system_instruction(self, persona: str, language: str, response_rule_sections: dict, max_response_chars: int) -> str:
        """Delegate to project-specific build_system_instruction."""
        raise NotImplementedError

    def _load_runtime_settings(self, prompt_manager, prompt_id: str, store_name: str):
        """Delegate to project-specific load_runtime_settings_from_prompt_manager."""
        raise NotImplementedError

    def _load_default_runtime_settings(self):
        """Delegate to project-specific load_runtime_settings_from_prompt_manager(None)."""
        raise NotImplementedError

    # --- 共用 prompt / system instruction 邏輯 ---

    def _get_active_prompt_context(self, language: str = "zh"):
        """取得目前啟用的人物設定資訊（prompt_manager / store_name / prompt_id / persona）。"""
        prompt_manager = None
        store_name = self._get_store_name_for_language(language)
        prompt_id = None  # will be set from runtime_settings default
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
                    persona_map = getattr(store_prompts, self._persona_map_attr, None)
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
        """取得靜態 System Instruction（persona from DB + system rules from code）"""
        try:
            prompt_manager, store_name, runtime_prompt_id, persona = self._get_active_prompt_context(session.language)
            runtime_settings = self._load_runtime_settings(
                prompt_manager, runtime_prompt_id, store_name,
            )
        except Exception:
            runtime_settings = self._load_default_runtime_settings()
            persona = None

        if not persona:
            persona = self._get_default_persona(session.language)

        response_rule_sections = runtime_settings.response_rule_sections.get(
            session.language, runtime_settings.response_rule_sections.get("zh")
        )
        sections_payload = (
            response_rule_sections.model_dump()
            if hasattr(response_rule_sections, "model_dump")
            else response_rule_sections
        )
        return self._build_system_instruction(
            persona=persona,
            language=session.language,
            response_rule_sections=sections_payload,
            max_response_chars=runtime_settings.max_response_chars,
        )

    # --- 共用 session 管理 ---

    def _get_or_create_chat_session(self, session: Session):
        """取得或建立持久 Gemini chat session"""
        sid = session.session_id
        if sid in self._chat_sessions:
            return self._chat_sessions[sid]

        history = build_chat_history(session.chat_history) if session.chat_history else []
        if history:
            logger.info(
                "從歷史恢復 chat session: %d 筆 (session=%s...)",
                len(history), sid[:8],
            )

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
        """將 user/model 訊息同步到 MongoDB"""
        session = self._session_manager.get_session(session_id)
        if not session:
            return
        session.chat_history.append({"role": "user", "content": user_message})
        session.chat_history.append({"role": "assistant", "content": assistant_message})
        self._session_manager.update_session(session)

    def _sync_history_to_db_background(self, session_id: str, user_message: str, assistant_message: str):
        """背景非同步寫入 DB，不阻塞回應"""
        try:
            loop = asyncio.get_running_loop()
            loop.run_in_executor(
                None, self._sync_history_to_db, session_id, user_message, assistant_message,
            )
        except Exception:
            self._sync_history_to_db(session_id, user_message, assistant_message)

    def remove_session(self, session_id: str):
        """清除記憶體中的 chat session"""
        self._chat_sessions.pop(session_id, None)

    def remove_all_sessions(self):
        """清除所有記憶體中的 chat sessions"""
        count = len(self._chat_sessions)
        self._chat_sessions.clear()
        if count > 0:
            logger.info("已清除 %d 個 chat sessions", count)

    @staticmethod
    def _append_to_chat_history(chat_session, user_message: str, model_message: str):
        """將乾淨的 user/model 訊息追加到 SDK chat session 的內部歷史"""
        if hasattr(chat_session, '_curated_history'):
            chat_session._curated_history.append(
                types.Content(role="user", parts=[types.Part.from_text(text=user_message)])
            )
            chat_session._curated_history.append(
                types.Content(role="model", parts=[types.Part.from_text(text=model_message)])
            )

    # --- 子類可覆寫的 intent / file search 方法 ---

    def _check_intent_fast(self, query: str) -> str:
        """快速判斷是否為不相關話題，子類必須覆寫。"""
        raise NotImplementedError

    def _file_search(self, query: str, language: str) -> Optional[str]:
        """用 File Search 查知識庫，子類必須覆寫。"""
        raise NotImplementedError

    async def _concurrent_intent_and_search(self, user_message: str, language: str) -> Optional[str]:
        """
        併發跑 Intent Check + File Search。
        Intent=NO 時快速攔截跳過知識庫；Intent=YES 時使用知識庫結果。
        """
        loop = asyncio.get_running_loop()
        t0 = time.time()

        intent_task = asyncio.ensure_future(
            loop.run_in_executor(None, self._check_intent_fast, user_message))
        search_task = asyncio.ensure_future(
            loop.run_in_executor(None, self._file_search, user_message, language))

        done, _ = await asyncio.wait(
            [intent_task, search_task],
            return_when=asyncio.FIRST_COMPLETED,
        )

        if intent_task in done and intent_task.result() == "NO":
            logger.info(f"[計時] Intent=NO 快速攔截: {(time.time()-t0)*1000:.0f}ms")
            return None

        await asyncio.gather(intent_task, search_task)
        intent = intent_task.result()
        kb_result = search_task.result() if intent == "YES" else None
        logger.info(f"[計時] Intent={intent}, File Search: {(time.time()-t0)*1000:.0f}ms")
        return kb_result

    @staticmethod
    def _clean_enriched_history(chat_session, original_user_message: str):
        """將 enriched_message 替換回乾淨的 user_message，避免 KB 結果累積在歷史中"""
        if hasattr(chat_session, '_curated_history') and chat_session._curated_history:
            last_user = chat_session._curated_history[-2]
            if last_user.role == "user":
                last_user.parts = [types.Part.from_text(text=original_user_message)]

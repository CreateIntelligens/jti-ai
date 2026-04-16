"""
Base Agent - 共用的 Gemini chat session 管理邏輯

提供 JTI MainAgent 與 HCIoT HciotMainAgent 共用的：
- Gemini chat session 建立與快取
- RAG 知識庫查詢
- MongoDB 歷史同步（含背景非同步寫入）
- session 清除
"""

import asyncio
import logging
import time
from typing import Any

from google.genai import types

from app.models.session import Session
import app.services.gemini_service as _gemini_service
from app.services.agent_utils import build_chat_history, normalize_language
from app.services.rag.service import get_rag_pipeline

logger = logging.getLogger(__name__)


class BaseAgent:
    """Gemini chat session 管理基底類別"""


    def __init__(self, model_name: str):
        self.model_name = model_name
        self._chat_sessions: dict[str, Any] = {}

    # --- 子類必須實作 ---

    @property
    def _session_manager(self):
        raise NotImplementedError

    @property
    def _persona_map_attr(self) -> str:
        """Attribute name on StorePrompts for persona mapping."""
        raise NotImplementedError

    @staticmethod
    def _get_store_name_for_language(language: str) -> str:
        raise NotImplementedError

    @property
    def _rag_source_type(self) -> str:
        """Return the source_type for RAG ('jti_knowledge' or 'hciot_knowledge')."""
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
        store_name = self._get_store_name_for_language(language)
        lang = normalize_language(language)

        try:
            from app import deps
            prompt_manager = getattr(deps, "prompt_manager", None)
        except Exception:
            return None, store_name, None, None

        if not prompt_manager:
            return None, store_name, None, None

        active = prompt_manager.get_active_prompt(store_name)
        if not active:
            return prompt_manager, store_name, None, None

        prompt_id = active.id
        persona = active.content

        store_prompts = prompt_manager._load_store_prompts(store_name)
        persona_map = getattr(store_prompts, self._persona_map_attr, None)
        if not isinstance(persona_map, dict):
            return prompt_manager, store_name, prompt_id, persona

        raw_persona = persona_map.get(active.id)
        if not isinstance(raw_persona, dict):
            return prompt_manager, store_name, prompt_id, persona

        # Unified profile map: {prompt_id: {"persona": {...}, ...}}
        # Legacy map: {prompt_id: {"zh": "...", "en": "..."}}
        inner_persona = raw_persona.get("persona")
        persona_pair = inner_persona if isinstance(inner_persona, dict) else raw_persona

        value = persona_pair.get(lang)
        if isinstance(value, str) and value.strip():
            persona = value

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

        lang_key = session.language if session.language in runtime_settings.response_rule_sections else "zh"
        rule_sections = runtime_settings.response_rule_sections[lang_key]
        sections_payload = rule_sections.model_dump() if hasattr(rule_sections, "model_dump") else rule_sections
        return self._build_system_instruction(
            persona=persona,
            language=session.language,
            response_rule_sections=sections_payload,
            max_response_chars=runtime_settings.max_response_chars,
        )

    # --- 共用 session 管理 ---

    def _get_or_create_chat_session(self, session: Session):
        """Get or create a persistent Gemini chat session."""
        sid = session.session_id
        if sid in self._chat_sessions:
            return self._chat_sessions[sid]

        history = build_chat_history(session.chat_history) if session.chat_history else []
        if history:
            logger.info("恢復 chat session: %d 筆 (session=%s...)", len(history), sid[:8])

        config = types.GenerateContentConfig(
            system_instruction=[types.Part.from_text(text=self._get_system_instruction(session))],
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        )

        chat_session = _gemini_service.client.chats.create(
            model=self.model_name, config=config, history=history,
        )
        self._chat_sessions[sid] = chat_session
        return chat_session

    def _sync_history_to_db(self, session_id: str, user_message: str, assistant_message: str, citations: list | None = None):
        """Sync user/assistant messages to MongoDB."""
        session = self._session_manager.get_session(session_id)
        if not session: return

        session.chat_history.append({"role": "user", "content": user_message})
        entry = {"role": "assistant", "content": assistant_message}
        if citations: entry["citations"] = citations
        session.chat_history.append(entry)
        self._session_manager.update_session(session)

    def _sync_history_to_db_background(self, *args, **kwargs):
        """Asynchronously write to DB without blocking response."""
        try:
            asyncio.get_running_loop().run_in_executor(None, lambda: self._sync_history_to_db(*args, **kwargs))
        except Exception:
            self._sync_history_to_db(*args, **kwargs)

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

    # --- 共用 enriched message 組裝 ---

    def _build_enriched_message(self, session_state: str, user_message: str, language: str, kb_result: str | None) -> str:
        """組合 session 狀態、知識庫結果、使用者問題為完整 enriched message"""
        question_label = "User question:" if language == "en" else "使用者問題："
        question_block = f"{question_label} {user_message}"

        if kb_result:
            return (
                f"{session_state}\n\n"
                f"<知識庫查詢結果>\n{kb_result}\n</知識庫查詢結果>\n\n"
                f"{question_block}"
            )
        return f"{session_state}\n\n{question_block}"

    # --- 共用 knowledge search ---

    async def _knowledge_search(self, user_message: str, language: str) -> tuple[str | None, list[dict] | None]:
        """用本地 RAG Pipeline 查知識庫，distance threshold 過濾不相關結果。"""
        loop = asyncio.get_running_loop()
        t0 = time.time()
        try:
            pipeline = get_rag_pipeline()
            kb_text, citations = await loop.run_in_executor(
                None,
                lambda: pipeline.retrieve(
                    user_message,
                    language=normalize_language(language),
                    source_type=self._rag_source_type,
                    top_k=3,
                ),
            )
            logger.info(f"[計時] RAG: {(time.time()-t0)*1000:.0f}ms | 結果: {'有' if kb_text else '無'}")
            return kb_text, citations
        except Exception as e:
            logger.error(f"[RAG] 檢索失敗: {e}")
            return None, None

    @staticmethod
    def _clean_enriched_history(chat_session, original_user_message: str):
        """將 enriched_message 替換回乾淨的 user_message，避免 KB 結果累積在歷史中。
        Walks backwards to skip function_response entries (from tool calling)."""
        if not hasattr(chat_session, '_curated_history') or not chat_session._curated_history:
            return
        for content in reversed(chat_session._curated_history):
            if content.role != "user":
                continue
            if any(hasattr(p, "function_response") and p.function_response for p in content.parts):
                continue
            content.parts = [types.Part.from_text(text=original_user_message)]
            break

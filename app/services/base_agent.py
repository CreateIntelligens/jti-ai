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
from app.services.agent_utils import (
    build_chat_history,
    extract_response_text,
    normalize_language,
    strip_citations,
)
from app.services.rag.service import get_rag_pipeline

logger = logging.getLogger(__name__)


class BaseAgent:
    """Gemini chat session 管理基底類別"""


    def __init__(self, model_name: str):
        self.model_name = model_name
        self._chat_sessions: dict[str, Any] = {}
        self._force_tool_configs: dict[str, types.GenerateContentConfig] = {}

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

    @property
    def _rag_search_language(self) -> str | None:
        """Language to use for RAG search (None means use session.language). 子類可覆寫。"""
        return None

    @property
    def _rag_tool_declaration(self) -> types.Tool | None:
        """Return the RAG tool declaration for this agent, or None if RAG tool is not used."""
        return None

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

    def _make_chat_config(self, session: Session) -> types.GenerateContentConfig:
        tool = self._rag_tool_declaration
        return types.GenerateContentConfig(
            system_instruction=[types.Part.from_text(text=self._get_system_instruction(session))],
            thinking_config=types.ThinkingConfig(thinking_budget=0),
            tools=[tool] if tool else None,
        )

    def _get_force_tool_config(self, session: Session) -> types.GenerateContentConfig:
        """Cached per-session config that forces tool calling."""
        sid = session.session_id
        if sid not in self._force_tool_configs:
            base = self._make_chat_config(session)
            self._force_tool_configs[sid] = types.GenerateContentConfig(
                system_instruction=base.system_instruction,
                thinking_config=base.thinking_config,
                tools=base.tools,
                tool_config=types.ToolConfig(
                    function_calling_config=types.FunctionCallingConfig(mode=types.FunctionCallingConfigMode.ANY),
                ),
            )
        return self._force_tool_configs[sid]

    def _get_or_create_chat_session(self, session: Session):
        """Get or create a persistent Gemini chat session."""
        sid = session.session_id
        cached_session = self._chat_sessions.get(sid)
        if cached_session is not None:
            return cached_session

        history = []
        if session.chat_history:
            history = build_chat_history(session.chat_history)
        if history:
            logger.info("恢復 chat session: %d 筆 (session=%s...)", len(history), sid[:8])

        config = self._make_chat_config(session)

        chat_session = _gemini_service.client.chats.create(
            model=self.model_name, config=config, history=history,
        )
        self._chat_sessions[sid] = chat_session
        return chat_session

    def _sync_history_to_db(self, session_id: str, user_message: str, assistant_message: str, citations: list | None = None):
        """Sync user/assistant messages to MongoDB."""
        session = self._session_manager.get_session(session_id)
        if not session:
            return

        session.chat_history.append({"role": "user", "content": user_message})
        assistant_entry = {"role": "assistant", "content": assistant_message}
        if citations:
            assistant_entry["citations"] = citations
        session.chat_history.append(assistant_entry)
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
        self._force_tool_configs.pop(session_id, None)

    def remove_all_sessions(self):
        """清除所有記憶體中的 chat sessions"""
        count = len(self._chat_sessions)
        self._chat_sessions.clear()
        self._force_tool_configs.clear()
        if count > 0:
            logger.info("已清除 %d 個 chat sessions", count)

    @staticmethod
    def _append_to_chat_history(chat_session, user_message: str, model_message: str):
        """將乾淨的 user/model 訊息追加到 SDK chat session 的內部歷史"""
        curated_history = getattr(chat_session, "_curated_history", None)
        if curated_history is None:
            return

        curated_history.append(
            types.Content(role="user", parts=[types.Part.from_text(text=user_message)])
        )
        curated_history.append(
            types.Content(role="model", parts=[types.Part.from_text(text=model_message)])
        )

    # --- Function-calling loop ---

    _MAX_TOOL_ROUNDS = 2
    _RAG_MAX_CITATIONS = 5

    async def _run_tool_loop(self, chat_session, enriched: str, session: Session, user_message: str):
        """Send enriched message with forced tool call, handle function calling loop.
        Returns (response, citations)."""
        from app.services.gemini_service import gemini_with_retry, run_sync

        force_config = self._get_force_tool_config(session)
        response = await run_sync(gemini_with_retry, lambda: chat_session.send_message(enriched, config=force_config))

        citations = None
        for _ in range(self._MAX_TOOL_ROUNDS):
            fc_part = self._find_function_call(response)
            if fc_part is None:
                break

            tool_name = fc_part.function_call.name
            tool_args = dict(fc_part.function_call.args) if fc_part.function_call.args else {}
            logger.info(f"[Tool Call] {tool_name}({tool_args})")

            if tool_name == "search_knowledge":
                ai_query = tool_args.get("query", user_message)
                kb_text, raw_citations = await self._execute_rag_tool(ai_query, user_message, session)
                if raw_citations:
                    citations = raw_citations
                tool_result = kb_text
            else:
                tool_result = f"Unknown tool: {tool_name}"

            tool_response_part = types.Part.from_function_response(
                name=tool_name,
                response={"result": tool_result},
            )
            response = await run_sync(gemini_with_retry, lambda p=tool_response_part: chat_session.send_message(p))

        self._clean_enriched_history(chat_session, user_message)
        return response, citations

    # --- Function-calling and RAG helpers ---

    @staticmethod
    def _find_function_call(response) -> Any | None:
        """Return the first Part with a function_call, or None."""
        if not response.candidates or not response.candidates[0].content.parts:
            return None
        for part in response.candidates[0].content.parts:
            if hasattr(part, "function_call") and part.function_call and part.function_call.name:
                return part
        return None

    async def _execute_rag_tool(self, ai_query: str, user_message: str, session: Session) -> tuple[str, list[dict] | None]:
        """Run dual RAG search: AI-rewritten query + original user message, merge & dedupe.
        Skips the second query when ai_query matches user_message."""
        loop = asyncio.get_running_loop()
        pipeline = get_rag_pipeline()
        
        # Use _rag_search_language if defined, otherwise session.language
        search_lang = self._rag_search_language or session.language
        search_lang = normalize_language(search_lang)

        ai_future = loop.run_in_executor(
            None,
            lambda: pipeline.retrieve(ai_query, language=search_lang, source_type=self._rag_source_type, top_k=3),
        )

        # Skip duplicate query when AI didn't rewrite
        if ai_query == user_message:
            _, ai_citations = await ai_future
            user_citations = None
        else:
            user_future = loop.run_in_executor(
                None,
                lambda: pipeline.retrieve(user_message, language=search_lang, source_type=self._rag_source_type, top_k=3),
            )
            (_, ai_citations), (_, user_citations) = await asyncio.gather(ai_future, user_future)

        # Merge, dedupe by text, keep the smallest distance per duplicate
        by_text: dict[str, dict] = {}
        for c in (ai_citations or []) + (user_citations or []):
            txt = c.get("text", "")
            if not txt:
                continue
            existing = by_text.get(txt)
            if existing is None or c.get("_distance", 999) < existing.get("_distance", 999):
                by_text[txt] = c

        # Sort by distance (lower = more relevant) and cap to top N
        merged = sorted(by_text.values(), key=lambda c: c.get("_distance", 999))[:self._RAG_MAX_CITATIONS]

        if not merged:
            return "知識庫中沒有找到相關資料。", None

        kb_text = "\n---\n".join(c["text"] for c in merged)
        distances = [f"{c.get('_distance', 999):.3f}" for c in merged]
        logger.info(f"[RAG Dual] ai={len(ai_citations or [])} + user={len(user_citations or [])} → top {len(merged)} | distances={distances}")

        # Strip internal fields before returning to caller
        cleaned = [{k: v for k, v in c.items() if not k.startswith("_")} for c in merged]
        return kb_text, cleaned

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

    # --- 核心對話流程 (Template Method) ---

    def _get_session_state(self, session: Session) -> str:
        """Hook: 取得動態 Session 狀態（會變化的資訊）。"""
        raise NotImplementedError

    def _get_question_label(self, language: str) -> str:
        """Hook: 取得問題提示語標籤。"""
        return "使用者問題："

    def _preprocess_chat_data(self, session: Session, citations: list[dict] | None) -> tuple[list[dict] | None, dict[str, Any]]:
        """Hook: 在回應完成後，處理 citations 之前。"""
        return citations, {}

    def _post_process_chat_result(self, session: Session, response_text: str, citations: list[dict] | None, extra_meta: dict[str, Any]) -> dict[str, Any]:
        """Hook: 在 chat 回應組裝完成後，添加專案特有的欄位 (如 tts_text, image_id)。"""
        return {}

    def _get_chat_fallback_message(self, language: str) -> str:
        """回傳 chat 失敗時的預設訊息。"""
        return "AI目前發生錯誤，請稍後再試。"

    async def chat(self, session_id: str, user_message: str) -> dict[str, Any]:
        """
        統一的對話流程 (Function-calling / RAG 版本)：
        1. 取得 session 並建立 enriched message。
        2. 執行 _run_tool_loop (會自動處理 RAG 工具調用)。
        3. 呼叫 _preprocess_chat_data 處理引用與提取元數據。
        4. 同步歷史至 DB。
        5. 呼叫 _post_process_chat_result 補全結果。
        """
        try:
            from app.services.gemini_service import client as _gemini_client
            if not _gemini_client:
                return {"error": "Gemini client not initialized", "message": "系統未正確初始化，請檢查 API Key 設定。"}

            session = self._session_manager.get_session(session_id)
            if not session:
                return {"error": "Session not found", "message": "找不到對話記錄，請重新開始。"}

            chat_session = self._get_or_create_chat_session(session)
            
            # 組裝原始 enriched message (用於驅動 RAG 判斷)
            q_label = self._get_question_label(session.language)
            enriched = f"{self._get_session_state(session)}\n\n{q_label} {user_message}"
            
            t0 = time.time()
            logger.info(f"[{self.__class__.__name__}] 訊息: {user_message[:50]}...")
            
            # 使用基底類別提供的 tool loop 進行 RAG
            response, citations = await self._run_tool_loop(chat_session, enriched, session, user_message)
            
            logger.info(f"[{self.__class__.__name__}] 流程總耗時: {(time.time()-t0)*1000:.0f}ms")

            # 處理中間數據
            citations, extra_meta = self._preprocess_chat_data(session, citations)

            # 提取文字與同步 DB
            final_text = strip_citations(extract_response_text(response)) or self._get_chat_fallback_message(session.language)
            self._sync_history_to_db_background(session_id, user_message, final_text, citations)

            # 組裝結果
            result = {
                "message": final_text,
                "session": session.model_dump(),
                "tool_calls": [],
                "citations": citations,
            }
            result.update(self._post_process_chat_result(session, final_text, citations, extra_meta))
            return result

        except Exception as e:
            logger.error(f"[{self.__class__.__name__}] chat failed: {e}", exc_info=True)
            return {"error": str(e), "message": f"抱歉，發生錯誤：{str(e)}"}

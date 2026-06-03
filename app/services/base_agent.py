"""
Base Agent - 共用的 Gemini chat session 管理邏輯

提供 JTI / HCIoT / General 各 MainAgent 共用的：
- Gemini chat session 建立與快取
- RAG 知識庫查詢
- MongoDB 歷史同步（含背景非同步寫入）
- session 清除
"""

import asyncio
import logging
import time
from collections import OrderedDict
from typing import Any, cast

_CHAT_SESSION_CACHE_MAX = 128

from google.genai import types

from app.models.session import Session
import app.services.gemini_service as _gemini_service
from app.routers.general.stores import resolve_key_index_for_store
from app.services.agent_utils import (
    build_chat_history,
    extract_response_text,
    normalize_language,
    strip_citations,
)
from app.services.gemini_clients import get_client_by_index
from app.services.rag.service import get_rag_pipeline

logger = logging.getLogger(__name__)


class BaseAgent:
    """Gemini chat session 管理基底類別"""


    def __init__(self, model_name: str):
        self.model_name = model_name
        self._chat_sessions: "OrderedDict[str, Any]" = OrderedDict()

    # --- 子類必須實作 ---

    @property
    def _session_manager(self):
        raise NotImplementedError

    @property
    def _persona_map_attr(self) -> str:
        """Attribute name on StorePrompts for persona mapping."""
        raise NotImplementedError

    @property
    def _active_prompt_id_attr(self) -> str:
        """Attribute name on StorePrompts for the app-specific active prompt id."""
        raise NotImplementedError

    @staticmethod
    def _get_store_name_for_language(language: str) -> str:
        raise NotImplementedError

    def _get_store_name_for_session(self, session: Session) -> str:
        """Resolve the knowledge store name from session context.

        Default: delegate to the static _get_store_name_for_language.
        Override in subclasses (e.g. GeneralAgent) where the store
        is dynamic and comes from the session itself.
        """
        return self._get_store_name_for_language(session.language)

    @property
    def _rag_source_type(self) -> str:
        """Return the source_type for RAG ('jti_knowledge' or 'hciot_knowledge')."""
        raise NotImplementedError

    def _get_rag_source_type_for_session(self, session: Session) -> str:
        """Resolve RAG source_type from session context.

        Default: use the static _rag_source_type property. Override in
        subclasses (e.g. GeneralAgent) where source_type can vary
        per-session (managed app vs. general).
        """
        return self._rag_source_type

    def _get_default_persona(self, language: str) -> str:
        """Return default persona text when no DB persona is configured."""
        raise NotImplementedError

    def _build_system_instruction(self, persona: str, language: str, response_rule_sections: dict, max_response_chars: int) -> str:
        """Delegate to project-specific build_system_instruction."""
        raise NotImplementedError

    def _load_runtime_settings(self, prompt_manager, prompt_id: str | None, store_name: str):
        """Delegate to project-specific load_runtime_settings_from_prompt_manager."""
        raise NotImplementedError

    def _load_default_runtime_settings(self):
        """Delegate to project-specific load_runtime_settings_from_prompt_manager(None)."""
        raise NotImplementedError

    @property
    def _rag_search_language(self) -> str | None:
        """Language to use for RAG search (None means use session.language). 子類可覆寫。"""
        return None

    def _get_rag_search_language_for_session(self, session: Session) -> str | None:
        """Session-aware variant of `_rag_search_language`.

        Default: use the static property. Override in subclasses where the
        language axis used for RAG storage is dynamic (e.g. GeneralAgent
        stores per-store under language=store_name).
        """
        return self._rag_search_language

    @property
    def _rag_tool_declaration(self) -> types.Tool | None:
        """Return the RAG tool declaration for this agent, or None if RAG tool is not used."""
        return None

    def _get_rag_tool_declaration_for_session(self, session: Session) -> types.Tool | None:
        """Return the RAG tool declaration for a specific session."""
        return self._rag_tool_declaration

    # --- 共用 prompt / system instruction 邏輯 ---

    def _get_active_prompt_context(self, language: str = "zh"):
        """取得目前啟用的人物設定資訊（prompt_manager / store_name / prompt_id / persona）。

        Reads from app-specific attrs (_active_prompt_id_attr / _persona_map_attr)
        instead of the shared prompts[] + active_prompt_id used by General.
        """
        store_name = self._get_store_name_for_language(language)
        lang = normalize_language(language)

        try:
            from app import deps
            prompt_manager = getattr(deps, "prompt_manager", None)
        except Exception:
            return None, store_name, None, None

        if not prompt_manager:
            return None, store_name, None, None

        store_prompts = prompt_manager.get_store_prompts(store_name)
        active_id = getattr(store_prompts, self._active_prompt_id_attr, None)
        if not active_id:
            return prompt_manager, store_name, None, None

        persona = None
        persona_map = getattr(store_prompts, self._persona_map_attr, None)
        if isinstance(persona_map, dict):
            raw_persona = persona_map.get(active_id)
            if isinstance(raw_persona, dict):
                # Unified profile map: {prompt_id: {"persona": {...}, ...}}
                # Legacy map: {prompt_id: {"zh": "...", "en": "..."}}
                inner_persona = raw_persona.get("persona")
                persona_pair = inner_persona if isinstance(inner_persona, dict) else raw_persona
                value = persona_pair.get(lang)
                if isinstance(value, str) and value.strip():
                    persona = value

        return prompt_manager, store_name, active_id, persona

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
        tool = self._get_rag_tool_declaration_for_session(session)
        model_name = session.metadata.get("model") or self.model_name
        name_lower = model_name.lower()
        is_thinking_model = "thinking" in name_lower or "gemini-3" in name_lower
        thinking_config = None if is_thinking_model else types.ThinkingConfig(thinking_budget=0)

        return types.GenerateContentConfig(
            system_instruction=[types.Part.from_text(text=self._get_system_instruction(session))],
            thinking_config=thinking_config,
            tools=[tool] if tool else None,
            temperature=0.7,
        )

    def _get_force_tool_config(self, session: Session) -> types.GenerateContentConfig:
        """Per-session config that forces tool calling."""
        base = self._make_chat_config(session)
        return types.GenerateContentConfig(
            system_instruction=base.system_instruction,
            thinking_config=base.thinking_config,
            tools=base.tools,
            temperature=0.7,
            tool_config=types.ToolConfig(
                function_calling_config=types.FunctionCallingConfig(mode=types.FunctionCallingConfigMode.ANY),
            ),
        )

    def _get_or_create_chat_session(self, session: Session, model: str | None = None):
        """Get or create a persistent Gemini chat session."""
        sid = session.session_id
        cached_session = self._chat_sessions.get(sid)
        model_to_use = model or session.metadata.get("model") or self.model_name

        if cached_session is not None:
            cached_model = getattr(cached_session, "_model", getattr(cached_session, "model", None))
            if cached_model:
                cached_model_clean = cached_model.removeprefix("models/").lower()
                target_model_clean = model_to_use.removeprefix("models/").lower()
                if cached_model_clean == target_model_clean:
                    self._chat_sessions.move_to_end(sid)
                    return cached_session

        history = []
        if session.chat_history:
            history = build_chat_history(session.chat_history)
        if history:
            logger.info("恢復/重建 chat session (%s): %d 筆 (session=%s...)", model_to_use, len(history), sid[:8])

        config = self._make_chat_config(session)

        store_name = self._get_store_name_for_session(session)
        client = get_client_by_index(resolve_key_index_for_store(store_name))
        
        # Sync the model selection to DB metadata
        if session.metadata.get("model") != model_to_use:
            session.metadata["model"] = model_to_use
            self._session_manager.update_session(session)

        # Cast: build_chat_history returns list[Content]; the SDK accepts
        # list[Content | dict] but list is invariant so Pyright can't narrow.
        chat_session = client.chats.create(
            model=model_to_use,
            config=config,
            history=cast(list[types.ContentOrDict], history) if history else None,
        )
        self._chat_sessions[sid] = chat_session
        if len(self._chat_sessions) > _CHAT_SESSION_CACHE_MAX:
            self._chat_sessions.popitem(last=False)
        return chat_session

    def _sync_history_to_db(self, session_id: str, user_message: str, assistant_message: str, citations: list | None = None):
        """Sync user/assistant messages to MongoDB."""
        session = self._session_manager.get_session(session_id)
        if not session:
            return

        session.chat_history.append({"role": "user", "content": user_message})
        assistant_entry: dict[str, Any] = {"role": "assistant", "content": assistant_message}
        if citations:
            assistant_entry["citations"] = citations
        session.chat_history.append(assistant_entry)
        self._session_manager.update_session(session)

    def _sync_history_to_db_background(self, *args, **kwargs):
        """Asynchronously write to DB without blocking response.

        Falls back to a sync call when invoked outside an event loop (e.g. from
        scripts, scheduled jobs, or tests).
        """
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            self._sync_history_to_db(*args, **kwargs)
            return
        loop.run_in_executor(None, lambda: self._sync_history_to_db(*args, **kwargs))

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

    async def _send_enriched_with_model_fallback(
        self,
        chat_session,
        enriched: str,
        force_config,
        session: Session,
    ):
        """Send the initial forced-tool message.

        Rebuild the chat session if its bound model is gone.
        """
        from app.models_config import fallback_chain
        from app.services.gemini_service import _is_model_gone, gemini_with_retry, run_sync

        store_name = self._get_store_name_for_session(session)
        client = get_client_by_index(resolve_key_index_for_store(store_name))
        model_to_use = session.metadata.get("model") or self.model_name
        model_chain = fallback_chain(model_to_use, client)
        for model_index, model_name in enumerate(model_chain):
            try:
                response = await run_sync(
                    gemini_with_retry,
                    lambda current_chat_session=chat_session: current_chat_session.send_message(
                        enriched,
                        config=force_config,
                    ),
                )
                return chat_session, response
            except Exception as e:
                if not _is_model_gone(e) or model_index == len(model_chain) - 1:
                    raise

                next_model = model_chain[model_index + 1]
                logger.warning(
                    "[Gemini] chat model %s unavailable; rebuilding session on %s",
                    model_name,
                    next_model,
                )
                session.metadata["model"] = next_model
                self._session_manager.update_session(session)
                self._chat_sessions.pop(session.session_id, None)
                chat_session = self._get_or_create_chat_session(session)

        raise RuntimeError("model fallback send exited unexpectedly")

    async def _run_tool_loop(self, chat_session, enriched: str, session: Session, user_message: str):
        """Send enriched message with forced tool call, handle function calling loop.
        Returns (response, citations)."""
        from app.services.gemini_service import gemini_with_retry, run_sync

        force_config = self._get_force_tool_config(session)
        chat_session, response = await self._send_enriched_with_model_fallback(
            chat_session,
            enriched,
            force_config,
            session,
        )

        citations: list[dict] | None = None
        for _ in range(self._MAX_TOOL_ROUNDS):
            fc_parts = self._find_function_calls(response)
            if not fc_parts:
                break

            results = await asyncio.gather(
                *[self._dispatch_tool_call(fc_part, user_message, session) for fc_part in fc_parts]
            )

            response_parts = []
            for tool_name, tool_result, raw_citations in results:
                citations = self._merge_citations(citations, raw_citations or [])
                response_parts.append(
                    types.Part.from_function_response(
                        name=tool_name,
                        response={"result": tool_result},
                    )
                )

            response = await run_sync(gemini_with_retry, lambda pp=response_parts: chat_session.send_message(pp))

        self._clean_enriched_history(chat_session, user_message)
        return response, citations

    # --- Function-calling and RAG helpers ---

    @staticmethod
    def _find_function_calls(response) -> list:
        """Return all Parts that contain a named function_call."""
        if not response.candidates or not response.candidates[0].content.parts:
            return []
        return [
            part for part in response.candidates[0].content.parts
            if hasattr(part, "function_call") and part.function_call and part.function_call.name
        ]

    async def _dispatch_tool_call(
        self,
        fc_part,
        user_message: str,
        session: Session,
    ) -> tuple[str, str, list[dict] | None]:
        """Execute one model-requested tool call and return a Gemini function response payload."""
        tool_name = fc_part.function_call.name
        tool_args = dict(fc_part.function_call.args) if fc_part.function_call.args else {}

        if tool_name != "search_knowledge":
            logger.info(f"[Tool Call] {tool_name}({tool_args})")
            return tool_name, f"Unknown tool: {tool_name}", None

        queries = self._extract_search_queries(tool_args, fallback=user_message)
        logger.info(f"[Tool Call] search_knowledge(queries={queries})")

        sub_results = await asyncio.gather(
            *[self._execute_rag_tool(query, user_message, session) for query in queries]
        )
        tool_result, citations = self._format_search_results(queries, sub_results)
        return tool_name, tool_result, citations

    @staticmethod
    def _extract_search_queries(tool_args: dict, fallback: str) -> list[str]:
        raw_queries = tool_args.get("queries") or []
        queries = [q.strip() for q in raw_queries if isinstance(q, str) and q.strip()]
        deduped = list(dict.fromkeys(queries))
        return deduped or [fallback]

    def _format_search_results(
        self,
        queries: list[str],
        sub_results: list[tuple[str, list[dict] | None]],
    ) -> tuple[str, list[dict] | None]:
        merged_citations: list[dict] | None = None
        sections: list[str] = []
        for query, (kb_text, raw_citations) in zip(queries, sub_results):
            sections.append(f"[查詢: {query}]\n{kb_text}")
            merged_citations = self._merge_citations(merged_citations, raw_citations or [])
        return "\n\n---\n\n".join(sections), merged_citations

    @staticmethod
    def _merge_citations(existing: list[dict] | None, new: list[dict]) -> list[dict]:
        """Merge two citation lists, deduping by (uri, text) tuple."""
        base = list(existing) if existing else []
        seen = {(c.get("uri"), c.get("text")) for c in base}
        for c in new:
            key = (c.get("uri"), c.get("text"))
            if key not in seen:
                seen.add(key)
                base.append(c)
        return base

    async def _execute_rag_tool(self, ai_query: str, user_message: str, session: Session) -> tuple[str, list[dict] | None]:
        """Run dual RAG search: AI-rewritten query + original user message, merge & dedupe.
        Skips the second query when ai_query matches user_message."""
        loop = asyncio.get_running_loop()
        pipeline = get_rag_pipeline()
        
        # Resolve the language axis used for RAG retrieval. When a subclass
        # overrides this with a non-None value, take it as the storage key
        # verbatim (GeneralAgent stores per-store under language=store_name);
        # otherwise normalize the session language to "zh"/"en".
        search_lang = (
            self._get_rag_search_language_for_session(session)
            or normalize_language(session.language)
        )
        rag_source_type = self._get_rag_source_type_for_session(session)

        ai_future = loop.run_in_executor(
            None,
            lambda q=ai_query, sl=search_lang, rst=rag_source_type: pipeline.retrieve(q, language=sl, source_type=rst, top_k=3),
        )

        # Skip duplicate query when AI didn't rewrite
        if ai_query == user_message:
            _, ai_citations = await ai_future
            user_citations = None
        else:
            user_future = loop.run_in_executor(
                None,
                lambda um=user_message, sl=search_lang, rst=rag_source_type: pipeline.retrieve(um, language=sl, source_type=rst, top_k=3),
            )
            (_, ai_citations), (_, user_citations) = await asyncio.gather(ai_future, user_future)

        # Fuse the two result lists with Reciprocal Rank Fusion.
        # Each ranked list is sorted by its own distance, then every doc gets
        # 1/(k+rank). Distances across queries aren't comparable, ranks are.
        citation_lists = [ai_citations or [], user_citations or []]
        merged = self._rrf_merge(citation_lists, cap=self._RAG_MAX_CITATIONS)

        if not merged:
            return "知識庫中沒有找到相關資料。", None

        kb_text = "\n---\n".join(c["text"] for c in merged)
        scores = [f"{c.get('_rrf_score', 0):.4f}" for c in merged]
        distances = [f"{c.get('_distance', 999):.3f}" for c in merged]
        logger.info(
            f"[RAG Dual] ai={len(ai_citations or [])} + user={len(user_citations or [])} "
            f"→ top {len(merged)} | rrf={scores} | distances={distances}"
        )

        # Strip internal fields before returning to caller
        cleaned = [{k: v for k, v in c.items() if not k.startswith("_")} for c in merged]
        return kb_text, cleaned

    @staticmethod
    def _rrf_merge(
        ranked_lists: list[list[dict]],
        cap: int,
        k: int = 60,
    ) -> list[dict]:
        """Reciprocal Rank Fusion over multiple ranked citation lists.

        For each list, sort by ascending distance (best = rank 1) and award
        1/(k+rank) to every doc. A doc that appears in multiple lists
        accumulates contributions from each. Final order is by total score
        descending; the kept dict is whichever copy had the smallest distance
        (so existing _distance / text / uri stay meaningful).
        """
        scores_by_text: dict[str, float] = {}
        best_doc_by_text: dict[str, dict] = {}
        for ranked_list in ranked_lists:
            ordered_docs = sorted(ranked_list, key=lambda c: c.get("_distance", 999))
            for rank, doc in enumerate(ordered_docs, start=1):
                text = doc.get("text", "")
                if not text:
                    continue
                scores_by_text[text] = scores_by_text.get(text, 0.0) + 1.0 / (k + rank)
                existing = best_doc_by_text.get(text)
                if existing is None or doc.get("_distance", 999) < existing.get("_distance", 999):
                    best_doc_by_text[text] = doc

        scored_docs = [
            {**doc, "_rrf_score": scores_by_text[text]}
            for text, doc in best_doc_by_text.items()
        ]
        return sorted(scored_docs, key=lambda c: c["_rrf_score"], reverse=True)[:cap]

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

    async def chat(self, session_id: str, user_message: str, model: str | None = None) -> dict[str, Any]:
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

            chat_session = self._get_or_create_chat_session(session, model=model)
            
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

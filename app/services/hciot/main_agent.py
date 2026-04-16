"""
HCIoT main agent - patient education chat flow.

Uses Gemini function calling: the model decides when to search the
knowledge base via a `search_knowledge` tool, so the query naturally
includes conversational context.
"""

import asyncio
import logging
import os
import time
from typing import Any

from google.genai import types

from app.models.session import Session
import app.services.gemini_service as _gemini_service
from app.services.gemini_service import gemini_with_retry, run_sync
from app.services.agent_utils import (
    build_chat_history,
    extract_response_text,
    normalize_language,
    strip_citations,
)
from app.services.base_agent import BaseAgent
from app.services.hciot.agent_prompts import (
    PERSONA,
    SESSION_STATE_TEMPLATES,
    build_system_instruction,
)
from app.services.hciot.runtime_settings import (
    HCIOT_STORE_NAME,
    load_runtime_settings_from_prompt_manager,
)
from app.services.hciot.knowledge_store import get_hciot_knowledge_store
from app.services.rag.service import get_rag_pipeline
from app.services.session.session_manager_factory import get_hciot_session_manager

session_manager = get_hciot_session_manager()
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# RAG function declaration for Gemini function calling
# ---------------------------------------------------------------------------
_SEARCH_KNOWLEDGE_DECL = types.FunctionDeclaration(
    name="search_knowledge",
    description="搜尋醫院衛教知識庫，查詢疾病、治療、照護、檢查、藥物、手術、復健等相關資料。",
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "query": types.Schema(
                type=types.Type.STRING,
                description="搜尋查詢語句，必須使用繁體中文，應為完整的問題描述（包含上下文），而非模糊的代名詞。即使使用者用英文提問，query 也必須翻譯成中文。",
            ),
        },
        required=["query"],
    ),
)

_RAG_TOOL = types.Tool(function_declarations=[_SEARCH_KNOWLEDGE_DECL])

_MAX_TOOL_ROUNDS = 2


class HciotMainAgent(BaseAgent):
    CHAT_MODEL = "gemini-3.1-flash-lite-preview"

    def __init__(self):
        super().__init__(model_name=self.CHAT_MODEL)
        self._force_tool_configs: dict[str, types.GenerateContentConfig] = {}

    @property
    def _session_manager(self):
        return session_manager

    @property
    def _persona_map_attr(self) -> str:
        return "hciot_persona_by_prompt"

    @staticmethod
    def _get_store_name_for_language(language: str) -> str:
        return "__hciot__en" if normalize_language(language) == "en" else HCIOT_STORE_NAME

    @property
    def _rag_source_type(self) -> str:
        return "hciot_knowledge"

    def _get_default_persona(self, language: str) -> str:
        return PERSONA.get(language, PERSONA["zh"])

    def _build_system_instruction(self, persona, language, response_rule_sections, max_response_chars):
        return build_system_instruction(
            persona=persona, language=language,
            response_rule_sections=response_rule_sections,
            limit=max_response_chars,
        )

    def _load_runtime_settings(self, prompt_manager, prompt_id, store_name):
        return load_runtime_settings_from_prompt_manager(prompt_manager, prompt_id, store_name=store_name)

    def _load_default_runtime_settings(self):
        return load_runtime_settings_from_prompt_manager(None)

    def _get_session_state(self, session: Session) -> str:
        from datetime import datetime, timezone
        template = SESSION_STATE_TEMPLATES.get(session.language, SESSION_STATE_TEMPLATES["zh"])
        now = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M")
        return template.format(step_value=session.step.value, now=now)

    @staticmethod
    def _extract_image_id(citations: list[dict] | None) -> str | None:
        """Return image_id only if the top-ranked citation carries one."""
        if not citations:
            return None
        return citations[0].get("image_id") or None

    @staticmethod
    def _localize_citations(language: str, citations: list[dict] | None) -> list[dict] | None:
        """Replace filenames with display names from the knowledge store."""
        if not citations:
            return citations
        file_map = {f["name"].lower(): f.get("display_name") or f["name"] for f in get_hciot_knowledge_store().list_files(language) if f.get("name")}

        localized = []
        for c in citations:
            target = dict(c)
            for key in ("title", "uri"):
                raw = (target.get(key) or "").strip()
                name = os.path.basename(raw).lower()
                if name in file_map:
                    target["title"] = file_map[name]
                    break
            localized.append(target)
        return localized

    # ------------------------------------------------------------------
    # Chat config helpers — built once per session, reused every call
    # ------------------------------------------------------------------
    def _make_chat_config(self, session: Session) -> types.GenerateContentConfig:
        return types.GenerateContentConfig(
            system_instruction=[types.Part.from_text(text=self._get_system_instruction(session))],
            thinking_config=types.ThinkingConfig(thinking_budget=0),
            tools=[_RAG_TOOL],
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

    # ------------------------------------------------------------------
    # Override: chat session with RAG tool
    # ------------------------------------------------------------------
    def _get_or_create_chat_session(self, session: Session):
        sid = session.session_id
        if sid in self._chat_sessions:
            return self._chat_sessions[sid]

        history = build_chat_history(session.chat_history) if session.chat_history else []
        if history:
            logger.info("恢復 chat session: %d 筆 (session=%s...)", len(history), sid[:8])

        config = self._make_chat_config(session)
        chat_session = _gemini_service.client.chats.create(
            model=self.model_name, config=config, history=history,
        )
        self._chat_sessions[sid] = chat_session
        return chat_session

    def remove_session(self, session_id: str):
        super().remove_session(session_id)
        self._force_tool_configs.pop(session_id, None)

    def remove_all_sessions(self):
        super().remove_all_sessions()
        self._force_tool_configs.clear()

    # ------------------------------------------------------------------
    # Execute the RAG tool call
    # ------------------------------------------------------------------
    async def _execute_rag_tool(self, ai_query: str, user_message: str) -> tuple[str, list[dict] | None]:
        """Run dual RAG search: AI-rewritten query + original user message, merge & dedupe.
        Skips the second query when ai_query matches user_message."""
        loop = asyncio.get_running_loop()
        pipeline = get_rag_pipeline()
        search_lang = "zh"

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

        # Merge and dedupe by text content
        seen_texts: set[str] = set()
        merged: list[dict] = []
        for c in (ai_citations or []) + (user_citations or []):
            txt = c.get("text", "")
            if txt not in seen_texts:
                seen_texts.add(txt)
                merged.append(c)

        if not merged:
            return "知識庫中沒有找到相關資料。", None

        kb_text = "\n---\n".join(c["text"] for c in merged if c.get("text"))
        logger.info(f"[RAG Dual] ai={len(ai_citations or [])} + user={len(user_citations or [])} → merged={len(merged)}")
        return kb_text, merged

    # ------------------------------------------------------------------
    # Function-calling chat loop
    # ------------------------------------------------------------------
    async def chat(self, session_id: str, user_message: str) -> dict[str, Any]:
        try:
            if not _gemini_service.client:
                return {"error": "Gemini client not initialized", "message": "系統未正確初始化，請檢查 API Key 設定。"}

            session = session_manager.get_session(session_id)
            if not session:
                return {"error": "Session not found", "message": "找不到對話記錄，請重新開始。"}

            chat_session = self._get_or_create_chat_session(session)
            enriched = f"{self._get_session_state(session)}\n\n使用者問題： {user_message}"
            t0 = time.time()

            force_config = self._get_force_tool_config(session)
            response = await run_sync(gemini_with_retry, lambda: chat_session.send_message(enriched, config=force_config))

            citations = None
            for _ in range(_MAX_TOOL_ROUNDS):
                fc_part = self._find_function_call(response)
                if fc_part is None:
                    break

                tool_name = fc_part.function_call.name
                tool_args = dict(fc_part.function_call.args) if fc_part.function_call.args else {}
                logger.info(f"[Tool Call] {tool_name}({tool_args})")

                if tool_name == "search_knowledge":
                    ai_query = tool_args.get("query", user_message)
                    kb_text, raw_citations = await self._execute_rag_tool(ai_query, user_message)
                    if raw_citations:
                        citations = raw_citations
                    tool_result = kb_text
                else:
                    tool_result = f"Unknown tool: {tool_name}"

                tool_response_part = types.Part.from_function_response(
                    name=tool_name,
                    response={"result": tool_result},
                )
                response = await run_sync(gemini_with_retry, lambda: chat_session.send_message(tool_response_part))

            self._clean_enriched_history(chat_session, user_message)

            citations = self._localize_citations(session.language, citations)
            image_id = self._extract_image_id(citations)

            final_message = strip_citations(extract_response_text(response)) or "目前無法回應，請稍後再試。"
            elapsed_ms = (time.time() - t0) * 1000
            logger.info(f"[計時] HCIoT chat 總耗時: {elapsed_ms:.0f}ms (含 tool call + RAG + LLM)")
            self._sync_history_to_db_background(session_id, user_message, final_message, citations)

            return {
                "message": final_message,
                "session": session.model_dump(),
                "tool_calls": [],
                "citations": citations,
                "image_id": image_id,
            }
        except Exception as e:
            logger.error(f"HCIoT chat failed: {e}", exc_info=True)
            return {"error": str(e), "message": f"抱歉，發生錯誤：{str(e)}"}

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _find_function_call(response) -> Any | None:
        """Return the first Part with a function_call, or None."""
        if not response.candidates or not response.candidates[0].content.parts:
            return None
        for part in response.candidates[0].content.parts:
            if hasattr(part, "function_call") and part.function_call and part.function_call.name:
                return part
        return None


main_agent = HciotMainAgent()

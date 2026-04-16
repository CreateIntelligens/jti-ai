"""
Main Agent - 核心對話邏輯

架構：
- 併發跑 Intent Check + RAG Knowledge Search
- Intent=NO（無關話題）→ 跳過知識庫結果，直接讓主 agent 回應（自然婉拒）
- Intent=YES → 帶知識庫結果給主 agent 回應
"""

import logging
import os
import time

from google.genai import types
from app.models.session import Session
from app.services.session.session_manager_factory import get_session_manager
import app.services.gemini_service as _gemini_service
from app.services.gemini_service import gemini_with_retry, run_sync
from app.services.agent_utils import (
    extract_response_text,
    normalize_language,
    strip_citations,
)
from app.services.base_agent import BaseAgent
from app.tools.jti.tool_executor import ToolExecutor
from app.services.jti.agent_prompts import (
    PERSONA,
    SESSION_STATE_TEMPLATES,
    build_system_instruction,
)
from app.services.jti.runtime_settings import (
    load_runtime_settings_from_prompt_manager,
)
from app.services.jti.tts_text import to_tts_text

# 使用工廠函數取得適當的實作（MongoDB 或記憶體）
session_manager = get_session_manager()

logger = logging.getLogger(__name__)

class MainAgent(BaseAgent):
    """主要對話 Agent"""

    # JTI 用固定的 flash-lite，避免較強的 model 自行進行測驗流程
    CHAT_MODEL = "gemini-3.1-flash-lite-preview"

    def __init__(self):
        super().__init__(model_name=self.CHAT_MODEL)

    @property
    def _session_manager(self):
        return session_manager

    @property
    def _persona_map_attr(self) -> str:
        return "jti_profiles_by_prompt"

    # 重用 ToolExecutor 的 _format_options（避免重複定義）
    _format_options_text = staticmethod(ToolExecutor._format_options)

    @staticmethod
    def _get_store_name_for_language(language: str) -> str:
        return "__jti__en" if normalize_language(language) == "en" else "__jti__"

    @property
    def _rag_source_type(self) -> str:
        return "jti_knowledge"

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
        """取得動態 Session 狀態（會變化的資訊）"""
        from datetime import datetime, timezone
        template = SESSION_STATE_TEMPLATES.get(session.language, SESSION_STATE_TEMPLATES["zh"])
        not_yet = "Not calculated yet" if session.language == "en" else "尚未計算"
        now = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M")
        return template.format(
            step_value=session.step.value,
            answers_count=len(session.answers),
            quiz_result=session.quiz_result_id or not_yet,
            now=now,
        )


    async def chat(self, session_id: str, user_message: str) -> dict:
        try:
            if not _gemini_service.client:
                msg = "系統未正確初始化，請檢查 API Key 設定。"
                return {"error": "Gemini client not initialized", "message": msg, "tts_text": to_tts_text(msg, "zh")}

            session = session_manager.get_session(session_id)
            if not session:
                msg = "找不到對話記錄，請重新開始。"
                return {"error": "Session not found", "message": msg, "tts_text": to_tts_text(msg, "zh")}

            t0 = time.time()
            kb_result, citations = await self._knowledge_search(user_message, session.language)

            enriched = self._build_enriched_message(self._get_session_state(session), user_message, session.language, kb_result)
            chat_session = self._get_or_create_chat_session(session)

            logger.info(f"使用者訊息: {user_message[:200]}...")
            t2 = time.time()
            response = await run_sync(gemini_with_retry, lambda: chat_session.send_message(enriched))
            logger.info(f"[計時] 主 Agent: {(time.time()-t2)*1000:.0f}ms | 總計: {(time.time()-t0)*1000:.0f}ms")

            if enriched != user_message:
                self._clean_enriched_history(chat_session, user_message)

            final_message = strip_citations(extract_response_text(response)) or "AI目前故障 請聯絡"
            self._sync_history_to_db_background(session_id, user_message, final_message, citations)

            return {
                "message": final_message,
                "tts_text": to_tts_text(final_message, session.language),
                "session": session.model_dump(),
                "tool_calls": [],
                "citations": citations
            }
        except Exception as e:
            logger.error(f"Chat failed: {e}", exc_info=True)
            msg = f"抱歉，發生錯誤：{str(e)}"
            return {"error": str(e), "message": msg, "tts_text": to_tts_text(msg, "zh")}

    async def chat_with_tool_result(
        self,
        session_id: str,
        user_message: str,
        tool_name: str,
        tool_args: dict,
        tool_result: dict
    ) -> dict:
        """
        當後端已執行工具時，讓 LLM 根據工具結果生成回應
        """
        try:
            session = session_manager.get_session(session_id)
            if not session:
                message = "找不到 session"
                return {
                    "error": "Session not found",
                    "message": message,
                    "tts_text": to_tts_text(message, "zh"),
                }

            # 根據工具結果生成指示
            if "instruction_for_llm" in tool_result:
                instruction = tool_result["instruction_for_llm"]
            elif "quiz_result" in tool_result and tool_result.get("message"):
                instruction = f"""使用者剛完成「尋找命定前蓋」測驗。

{tool_result['message']}

請用友善、鼓勵的語氣回應，包含：
1. 恭喜完成測驗
2. 結果與推薦前蓋"""
            else:
                instruction = "請簡短回應使用者"

            chat_session = self._get_or_create_chat_session(session)
            history = list(chat_session._curated_history) if hasattr(chat_session, '_curated_history') else []

            conversation_parts = list(history)
            conversation_parts.append(
                types.Content(
                    role="user",
                    parts=[types.Part.from_text(text=user_message)]
                )
            )

            system_instruction = self._get_system_instruction(session)
            session_state = self._get_session_state(session)
            config = types.GenerateContentConfig(
                system_instruction=f"{system_instruction}\n\n{session_state}\n\n{instruction}",
                thinking_config=types.ThinkingConfig(thinking_budget=0),
            )

            response = await run_sync(gemini_with_retry, lambda: _gemini_service.client.models.generate_content(
                model=self.model_name,
                contents=conversation_parts,
                config=config,
            ))

            final_message = extract_response_text(response)
            if not final_message:
                final_message = "收到！"

            # 測驗防呆：submit_answer 後若 LLM 回覆漏掉下一題，補上題目與選項避免跳題。
            if (
                tool_name == "submit_answer"
                and isinstance(tool_result, dict)
                and isinstance(tool_result.get("next_question"), dict)
                and not tool_result.get("is_complete")
            ):
                next_question = tool_result["next_question"]
                next_question_text = str(next_question.get("text", "")).strip()
                if next_question_text and next_question_text not in final_message:
                    next_q_index = int(tool_result.get("current_index", 0)) + 1
                    question_prefix = (
                        f"Question {next_q_index}:"
                        if session.language == "en"
                        else f"第{next_q_index}題："
                    )
                    options_text = self._format_options_text(next_question.get("options", []))
                    final_message = (
                        f"{final_message.strip()}\n\n"
                        f"{question_prefix} {next_question_text}\n"
                        f"{options_text}"
                    ).strip()

            self._append_to_chat_history(chat_session, user_message, final_message)
            self._sync_history_to_db_background(session_id, user_message, final_message)

            return {
                "message": final_message,
                "tts_text": to_tts_text(final_message, session.language),
                "session": session.model_dump()
            }

        except Exception as e:
            logger.error(f"chat_with_tool_result failed: {e}", exc_info=True)
            message = "收到！"
            return {
                "error": str(e),
                "message": message,
                "tts_text": to_tts_text(message, "zh"),
            }


# 全域實例
main_agent = MainAgent()

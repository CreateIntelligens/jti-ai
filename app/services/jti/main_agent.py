"""
Main Agent - 核心對話邏輯

架構：
- 每次對話先用 flash-lite 跑 File Search 查知識庫（不帶 system_instruction）
- 把使用者問題 + 知識庫結果送給主 agent（flash-lite）生成回應
"""

import asyncio
import os
import logging
import re
import time
from typing import Dict, List
import google.genai as genai
from google.genai import types
from app.models.session import Session, SessionStep
from app.services.session.session_manager_factory import get_session_manager
from app.services.gemini_service import client as gemini_client
from app.tools.tool_executor import tool_executor, ToolExecutor
from app.services.jti.agent_prompts import (
    SYSTEM_INSTRUCTIONS,
    SESSION_STATE_TEMPLATES,
)

# 使用工廠函數取得適當的實作（MongoDB 或記憶體）
session_manager = get_session_manager()

logger = logging.getLogger(__name__)

# File Search 用 flash-lite（不帶 system_instruction 即可正常 grounding）
FILE_SEARCH_MODEL = "gemini-2.5-flash-lite"


class MainAgent:
    """主要對話 Agent"""

    def __init__(self):
        self.model_name = os.getenv("GEMINI_MODEL_NAME", "gemini-2.5-flash")
        # 持久 chat session：session_id → Gemini ChatSession
        self._chat_sessions: Dict[str, any] = {}

    def _get_or_create_chat_session(self, session: Session):
        """取得或建立持久 Gemini chat session（不帶任何 tool）"""
        sid = session.session_id
        if sid in self._chat_sessions:
            return self._chat_sessions[sid]

        # 從 session.chat_history 恢復歷史
        history = []
        if session.chat_history:
            for msg in session.chat_history:
                role = "user" if msg["role"] == "user" else "model"
                history.append(
                    types.Content(
                        role=role,
                        parts=[types.Part.from_text(text=msg["content"])]
                    )
                )
            logger.info(f"從歷史恢復 chat session: {len(history)} 筆 (session={sid[:8]}...)")

        system_instruction = self._get_system_instruction(session)
        config = types.GenerateContentConfig(
            system_instruction=[types.Part.from_text(text=system_instruction)],
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        )

        chat_session = gemini_client.chats.create(
            model=self.model_name,
            config=config,
            history=history
        )
        self._chat_sessions[sid] = chat_session
        return chat_session

    def _sync_history_to_db(self, session_id: str, user_message: str, assistant_message: str):
        """將 user/model 訊息同步到 MongoDB（不截斷）"""
        session = session_manager.get_session(session_id)
        if not session:
            return
        session.chat_history.append({"role": "user", "content": user_message})
        session.chat_history.append({"role": "assistant", "content": assistant_message})
        session_manager.update_session(session)

    def _sync_history_to_db_background(self, session_id: str, user_message: str, assistant_message: str):
        """背景非同步寫入 DB，不阻塞回應"""
        try:
            loop = asyncio.get_event_loop()
            loop.run_in_executor(None, self._sync_history_to_db, session_id, user_message, assistant_message)
        except Exception:
            self._sync_history_to_db(session_id, user_message, assistant_message)

    def remove_session(self, session_id: str):
        """清除記憶體中的 chat session"""
        self._chat_sessions.pop(session_id, None)

    # 重用 ToolExecutor 的 _format_options（避免重複定義）
    _format_options_text = staticmethod(ToolExecutor._format_options)

    def _get_system_instruction(self, session: Session) -> str:
        """取得靜態 System Instruction（不變的規則）"""
        return SYSTEM_INSTRUCTIONS.get(session.language, SYSTEM_INSTRUCTIONS["zh"])

    def _get_session_state(self, session: Session) -> str:
        """取得動態 Session 狀態（會變化的資訊）"""
        template = SESSION_STATE_TEMPLATES.get(session.language, SESSION_STATE_TEMPLATES["zh"])
        return template.format(
            step_value=session.step.value,
            answers_count=len(session.answers),
            color_result=session.color_result_id or ('Not calculated yet' if session.language == 'en' else '尚未計算')
        )

    def _file_search(self, query: str, language: str) -> str | None:
        """用 flash 跑 File Search 查知識庫"""
        store_env_key = f"GEMINI_FILE_SEARCH_STORE_ID_{language.upper()}"
        store_id = os.getenv(store_env_key) or os.getenv("GEMINI_FILE_SEARCH_STORE_ID")
        if not store_id:
            logger.warning("未設定知識庫，跳過 File Search")
            return None

        store_name = f"fileSearchStores/{store_id}"
        logger.info(f"[File Search] 查詢: {query[:100]}...")

        for attempt in range(3):
            try:
                response = gemini_client.models.generate_content(
                    model=FILE_SEARCH_MODEL,
                    contents=query,
                    config=types.GenerateContentConfig(
                        tools=[
                            types.Tool(
                                file_search=types.FileSearch(
                                    file_search_store_names=[store_name]
                                )
                            )
                        ],
                        thinking_config=types.ThinkingConfig(thinking_budget=0),
                    ),
                )
                result = response.text.strip() if response.text else None
                logger.info(f"[File Search] 結果: {len(result) if result else 0} 字")
                return result
            except Exception as e:
                if "503" in str(e) and attempt < 2:
                    logger.warning(f"[File Search] 503，{attempt+1}/3 次重試...")
                    time.sleep(1)
                    continue
                logger.error(f"[File Search] 失敗: {e}")
                return None

    def _build_function_tools(self, language: str = "zh") -> List[types.Tool]:
        """建立只有 Function Declarations 的 tools（測驗判斷用）"""
        tool_descriptions = {
            "zh": {
                "start_quiz": "開始色彩測驗。⚠️ 重要：僅在使用者明確表達「想要」開始的意願時呼叫（例如：「我想做測驗」「開始吧」）。如果使用者表達否定或拒絕（例如：「不想」「不要」「跳過」），絕對禁止呼叫此工具。",
                "session_id": "Session ID"
            },
            "en": {
                "start_quiz": "Start the color quiz. ⚠️ IMPORTANT: Only call when user explicitly expresses WILLINGNESS to start (e.g., 'I want to take the quiz', 'let's begin'). If user expresses negation or refusal (e.g., 'don't want', 'no', 'skip'), absolutely DO NOT call this tool.",
                "session_id": "Session ID"
            }
        }
        desc = tool_descriptions.get(language, tool_descriptions["zh"])

        return [
            types.Tool(function_declarations=[
                types.FunctionDeclaration(
                    name="start_quiz",
                    description=desc["start_quiz"],
                    parameters={
                        "type": "object",
                        "properties": {
                            "session_id": {
                                "type": "string",
                                "description": desc["session_id"]
                            }
                        },
                        "required": ["session_id"]
                    }
                ),
            ])
        ]

    async def chat(
        self,
        session_id: str,
        user_message: str,
    ) -> Dict:
        """
        處理對話

        流程：
        1. 用 flash-lite 跑 File Search 查知識庫
        2. 把知識庫結果 + user message 送給主 agent 生成回應
        """
        try:
            if not gemini_client:
                return {
                    "error": "Gemini client not initialized",
                    "message": "系統未正確初始化，請檢查 API Key 設定。"
                }

            session = session_manager.get_session(session_id)
            if session is None:
                return {
                    "error": "Session not found",
                    "message": "找不到對話記錄，請重新開始。"
                }

            # 1. File Search
            t0 = time.time()
            kb_result = self._file_search(user_message, session.language)
            t1 = time.time()
            logger.info(f"[計時] File Search: {(t1-t0)*1000:.0f}ms")

            # 2. 組合訊息送給主 agent
            if kb_result:
                enriched_message = f"<知識庫查詢結果>\n{kb_result}\n</知識庫查詢結果>\n\n使用者問題：{user_message}"
            else:
                enriched_message = user_message

            chat_session = self._get_or_create_chat_session(session)

            logger.info(f"使用者訊息: {user_message[:200]}...")
            t2 = time.time()
            response = chat_session.send_message(enriched_message)
            t3 = time.time()
            logger.info(f"[計時] 主 Agent: {(t3-t2)*1000:.0f}ms | 總計: {(t3-t0)*1000:.0f}ms")

            tool_calls_log = []

            # 3. 取得回應
            final_message = ""
            if response.candidates and response.candidates[0].content.parts:
                for part in response.candidates[0].content.parts:
                    if hasattr(part, 'text') and part.text:
                        final_message += part.text

            if not final_message:
                final_message = "AI目前故障 請聯絡"
                logger.warning(f"LLM 未生成任何文本回應，使用者輸入：{user_message[:50]}")

            final_message = re.sub(r'\s*\[cite:\s*[^\]]*\]', '', final_message).strip()

            # 4. 同步 DB（背景）
            self._sync_history_to_db_background(session_id, user_message, final_message)
            updated_session = session_manager.get_session(session_id)

            return {
                "message": final_message,
                "session": updated_session.model_dump() if updated_session else None,
                "tool_calls": tool_calls_log
            }

        except Exception as e:
            logger.error(f"Chat failed: {e}", exc_info=True)
            return {
                "error": str(e),
                "message": f"抱歉，發生錯誤：{str(e)}"
            }

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
                return {"error": "Session not found", "message": "找不到 session"}

            # start_quiz 開場白：用固定文案
            if tool_name == "start_quiz" and tool_result.get("current_question"):
                q = tool_result["current_question"]
                options = q.get("options", [])
                options_text = self._format_options_text(options)

                if session.language == "en":
                    opening = (
                        "Would you like to take a lifestyle color exploration quiz? "
                        "Just five questions to find your perfect phone case. "
                        "If you want to leave midway, just type 'pause' to return to chat. Let's begin!"
                    )
                    question_prefix = "Question 1:"
                else:
                    opening = (
                        "想來做個生活品味色彩探索測驗嗎？ 簡單五個測驗，尋找你的命定手機殼，"
                        "如果中途想離開，請輸入中斷，即可繼續問答，那我們開始測驗吧！"
                    )
                    question_prefix = "第1題："

                message = f"{opening}\n\n{question_prefix} {q.get('text', '')}\n{options_text}"

                chat_session = self._get_or_create_chat_session(session)
                self._append_to_chat_history(chat_session, user_message, message)
                self._sync_history_to_db_background(session_id, user_message, message)

                return {
                    "message": message,
                    "session": session.model_dump(),
                }

            # 根據工具結果生成指示
            if "instruction_for_llm" in tool_result:
                instruction = tool_result["instruction_for_llm"]
            elif tool_name == "start_quiz" and tool_result.get("current_question"):
                q = tool_result["current_question"]
                options = q.get("options", [])
                options_text = self._format_options_text(options)
                instruction = f"""測驗已開始。

	開場白請固定使用以下文字，回覆必須從這行開頭（前面不要加任何字），請逐字輸出不要改寫：
	想來做個生活品味色彩探索測驗嗎？ 簡單五個測驗，尋找你的命定手機殼，如果中途想離開，請輸入中斷，即可繼續問答，那我們開始測驗吧！

	接著請完整顯示第1題與所有選項：

	第1題：{q['text']}
	{options_text}"""
            elif "color_result" in tool_result and tool_result.get("message"):
                instruction = f"""使用者剛完成色彩測驗。

{tool_result['message']}

請用友善、鼓勵的語氣回應，包含：
1. 恭喜完成測驗
2. 色系結果與推薦色"""
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

            response = gemini_client.models.generate_content(
                model=self.model_name,
                contents=conversation_parts,
                config=config
            )

            final_message = ""
            if response.candidates and response.candidates[0].content.parts:
                for part in response.candidates[0].content.parts:
                    if hasattr(part, 'text') and part.text:
                        final_message += part.text

            if not final_message:
                final_message = "收到！"

            self._append_to_chat_history(chat_session, user_message, final_message)
            self._sync_history_to_db_background(session_id, user_message, final_message)

            return {
                "message": final_message,
                "session": session.model_dump()
            }

        except Exception as e:
            logger.error(f"chat_with_tool_result failed: {e}", exc_info=True)
            return {
                "error": str(e),
                "message": "收到！"
            }

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


# 全域實例
main_agent = MainAgent()

"""
Main Agent - 核心對話邏輯

職責：
1. 處理一般對話
2. 判斷使用者意圖
3. 在適當時機呼叫色彩測驗工具
4. 商品問答（可用 RAG）

Agent 擁有的 Tools：
- start_quiz: 開始色彩測驗
- get_question: 取得當前題目
- submit_answer: 提交答案
- calculate_color_result: 計算色系結果
"""

import os
import logging
from typing import Dict, List
import google.genai as genai
from google.genai import types
from app.models.session import Session, SessionStep
from app.services.session.session_manager_factory import get_session_manager
from app.services.gemini_service import client as gemini_client
from app.tools.tool_executor import tool_executor, ToolExecutor
from app.services.jti.agent_prompts import (
    SYSTEM_INSTRUCTIONS,
    SESSION_STATE_TEMPLATES
)

# 使用工廠函數取得適當的實作（MongoDB 或記憶體）
session_manager = get_session_manager()

logger = logging.getLogger(__name__)


import re

class MainAgent:
    """主要對話 Agent"""

    def __init__(self):
        self.model_name = os.getenv("GEMINI_MODEL_NAME", "gemini-2.5-flash")
        # 持久 chat session：session_id → Gemini ChatSession
        self._chat_sessions: Dict[str, Any] = {}

    def _get_or_create_chat_session(self, session: Session):
        """取得或建立持久 Gemini chat session（如有 MongoDB 歷史會自動恢復）"""
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
        file_search_tools = self._build_file_search_tools(language=session.language)
        config = types.GenerateContentConfig(
            tools=file_search_tools,
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
        """將真正的 user/model 訊息同步到 MongoDB（不截斷）"""
        session = session_manager.get_session(session_id)
        if not session:
            return
        session.chat_history.append({"role": "user", "content": user_message})
        session.chat_history.append({"role": "assistant", "content": assistant_message})
        session_manager.update_session(session)

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

    def _build_file_search_tools(self, language: str = "zh") -> List[types.Tool]:
        """建立只有 File Search 的 tools（一般問答用）"""
        store_env_key = f"GEMINI_FILE_SEARCH_STORE_ID_{language.upper()}"
        file_search_store_id = os.getenv(store_env_key)
        if not file_search_store_id:
            file_search_store_id = os.getenv("GEMINI_FILE_SEARCH_STORE_ID")

        if file_search_store_id:
            logger.info(f"使用知識庫: {store_env_key}={file_search_store_id}")
            return [
                types.Tool(
                    file_search=types.FileSearch(
                        file_search_store_names=[f"fileSearchStores/{file_search_store_id}"]
                    )
                )
            ]
        else:
            logger.warning(f"未設定知識庫: {store_env_key}")
            return []

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
        """處理對話（使用持久 Chat Session + File Search）"""
        try:
            if not gemini_client:
                return {
                    "error": "Gemini client not initialized",
                    "message": "系統未正確初始化，請檢查 API Key 設定。"
                }

            # 1. 取得 session
            session = session_manager.get_session(session_id)
            if session is None:
                return {
                    "error": "Session not found",
                    "message": "找不到對話記錄，請重新開始。"
                }

            # 2. 取得或建立持久 chat session
            chat_session = self._get_or_create_chat_session(session)

            # 3. 發送訊息（SDK 自動維護歷史）
            logger.info(f"使用者訊息: {user_message[:200]}...")
            response = chat_session.send_message(user_message)

            # DEBUG: 檢查 File Search grounding
            if response.candidates:
                gm = getattr(response.candidates[0], 'grounding_metadata', None)
                print(f"[DEBUG FILE_SEARCH] grounding_metadata: {gm is not None}")

            tool_calls_log = []

            # 4. 取得最終回應
            final_message = ""
            if response.candidates and response.candidates[0].content.parts:
                for part in response.candidates[0].content.parts:
                    if hasattr(part, 'text') and part.text:
                        final_message += part.text

            if not final_message:
                final_message = "AI目前故障 請聯絡"
                logger.warning(f"LLM 未生成任何文本回應，使用者輸入：{user_message[:50]}")

            # 清除 Gemini File Search 的 citation 標記（例如 [cite: 1, xxx.csv]）
            final_message = re.sub(r'\s*\[cite:\s*[^\]]*\]', '', final_message).strip()

            # 5. 同步到 MongoDB（供重啟恢復用）
            self._sync_history_to_db(session_id, user_message, final_message)
            updated_session = session_manager.get_session(session_id)

            # 6. 對話日誌由 router 層統一記錄，這裡不重複記

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

        使用持久 chat session，但只把真正的 user/model 訊息記進歷史，
        session_state 和 instruction 透過一次性 generate_content 處理，
        再手動將乾淨的 user message 和 model response 追加到 chat session 歷史。
        """
        try:
            session = session_manager.get_session(session_id)
            if not session:
                return {"error": "Session not found", "message": "找不到 session"}

            # start_quiz 開場白：用固定文案避免 LLM 產生不一致文字
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

                # 把乾淨的 user/model 追加到持久 chat session 歷史
                chat_session = self._get_or_create_chat_session(session)
                self._append_to_chat_history(chat_session, user_message, message)
                self._sync_history_to_db(session_id, user_message, message)

                return {
                    "message": message,
                    "session": session.model_dump(),
                }

            # 根據工具結果生成指示
            if "instruction_for_llm" in tool_result:
                instruction = tool_result["instruction_for_llm"]
            elif tool_name == "start_quiz" and tool_result.get("current_question"):
                # 開始測驗，顯示第一題
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

            # 取得持久 chat session 的歷史作為上下文
            chat_session = self._get_or_create_chat_session(session)
            history = list(chat_session._curated_history) if hasattr(chat_session, '_curated_history') else []

            # 歷史 + 乾淨的 user message
            conversation_parts = list(history)
            conversation_parts.append(
                types.Content(
                    role="user",
                    parts=[types.Part.from_text(text=user_message)]
                )
            )

            # 把 session state + instruction 併入 system_instruction
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

            # 提取回應
            final_message = ""
            if response.candidates and response.candidates[0].content.parts:
                for part in response.candidates[0].content.parts:
                    if hasattr(part, 'text') and part.text:
                        final_message += part.text

            if not final_message:
                final_message = "收到！"

            # 把乾淨的 user/model 訊息追加到持久 chat session 歷史
            self._append_to_chat_history(chat_session, user_message, final_message)
            self._sync_history_to_db(session_id, user_message, final_message)

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

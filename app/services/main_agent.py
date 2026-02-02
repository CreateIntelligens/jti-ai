"""
Main Agent - 核心對話邏輯

職責：
1. 處理一般對話
2. 判斷使用者意圖
3. 在適當時機呼叫 MBTI 測驗工具
4. 商品問答（可用 RAG）

Agent 擁有的 Tools：
- start_quiz: 開始 MBTI 測驗
- get_question: 取得當前題目
- submit_answer: 提交答案
- calculate_persona: 計算 MBTI 類型
- recommend_products: 推薦商品
"""

import os
import logging
from typing import Dict, List, Optional
import google.genai as genai
from google.genai import types
from app.models.session import Session, SessionStep
from app.services.session_manager import session_manager
from app.services.gemini_service import client as gemini_client
from app.tools.tool_executor import tool_executor
from app.services.agent_prompts import (
    MAIN_AGENT_SYSTEM_PROMPT_TEMPLATE,
    CURRENT_QUESTION_TEMPLATE
)
from app.services.conversation_logger import conversation_logger

logger = logging.getLogger(__name__)


class MainAgent:
    """主要對話 Agent"""

    def __init__(self):
        self.model_name = os.getenv("GEMINI_MODEL_NAME", "gemini-2.5-flash")

    def _build_system_prompt(self, session: Session) -> str:
        """建立 System Prompt"""
        # 建構當前題目資訊
        current_q_info = ""
        if session.current_question:
            q = session.current_question
            current_q_info = CURRENT_QUESTION_TEMPLATE.format(
                question_id=q.get('id', 'unknown'),
                question_text=q.get('text', ''),
                option_a=q.get('options', [{}])[0].get('text', '') if q.get('options') else '',
                option_b=q.get('options', [{}])[1].get('text', '') if len(q.get('options', [])) > 1 else ''
            )

        # 不再需要在系統提示中包含對話歷史
        # 改用真正的 conversation history（在 chat() 中處理）
        
        return MAIN_AGENT_SYSTEM_PROMPT_TEMPLATE.format(
            session_id=session.session_id,
            step_value=session.step.value,
            answers_count=len(session.answers),
            persona=session.persona or '尚未計算',
            current_q_info=current_q_info
        )

    def _build_tools(self) -> List[types.Tool]:
        """建立 tools"""
        function_declarations = [
            types.FunctionDeclaration(
                name="start_quiz",
                description="開始 MBTI 測驗。當使用者說「MBTI」「測驗」「測試」「遊戲」「玩」或表達想做測驗的意圖時，立即呼叫此工具。不要自己生成問題。",
                parameters={
                    "type": "object",
                    "properties": {
                        "session_id": {
                            "type": "string",
                            "description": "Session ID"
                        }
                    },
                    "required": ["session_id"]
                }
            ),
            types.FunctionDeclaration(
                name="get_question",
                description="取得當前題目。用於顯示下一道題目給使用者。",
                parameters={
                    "type": "object",
                    "properties": {
                        "session_id": {
                            "type": "string",
                            "description": "Session ID"
                        }
                    },
                    "required": ["session_id"]
                }
            ),
            types.FunctionDeclaration(
                name="submit_answer",
                description="提交使用者的答案。當使用者選擇 A 或 B 時呼叫。",
                parameters={
                    "type": "object",
                    "properties": {
                        "session_id": {
                            "type": "string",
                            "description": "Session ID"
                        },
                        "question_id": {
                            "type": "string",
                            "description": "題目 ID，例如 'q1'"
                        },
                        "option_id": {
                            "type": "string",
                            "description": "選項 ID，'a' 或 'b'"
                        }
                    },
                    "required": ["session_id", "question_id", "option_id"]
                }
            ),
            types.FunctionDeclaration(
                name="calculate_persona",
                description="計算 MBTI 類型。當 5 題都回答完畢後呼叫。",
                parameters={
                    "type": "object",
                    "properties": {
                        "session_id": {
                            "type": "string",
                            "description": "Session ID"
                        }
                    },
                    "required": ["session_id"]
                }
            ),
            types.FunctionDeclaration(
                name="recommend_products",
                description="根據 MBTI 類型推薦商品。計算出類型後呼叫。",
                parameters={
                    "type": "object",
                    "properties": {
                        "session_id": {
                            "type": "string",
                            "description": "Session ID"
                        }
                    },
                    "required": ["session_id"]
                }
            ),

        ]

        # 整合 Function Declarations + File Search
        return [
            types.Tool(function_declarations=function_declarations),
            types.Tool(
                file_search=types.FileSearch(
                    file_search_store_names=["fileSearchStores/jti-xgvgfp8g1wsq"]
                )
            )
        ]

    async def chat(
        self,
        session_id: str,
        user_message: str,
        store_id: Optional[str] = None
    ) -> Dict:
        """處理對話"""
        try:
            if not gemini_client:
                return {
                    "error": "Gemini client not initialized",
                    "message": "系統未正確初始化，請檢查 API Key 設定。"
                }

            # 1. 取得或建立 session
            session = session_manager.get_session(session_id)
            if session is None:
                return {
                    "error": "Session not found",
                    "message": "找不到對話記錄，請重新開始。"
                }

            # 2. 建立對話內容（包含歷史對話串）
            system_prompt = self._build_system_prompt(session)
            tools = self._build_tools()

            # 3. 建立完整的對話串（包含歷史）
            conversation_parts = []
            
            # 如果有對話歷史，先加入
            if session.chat_history:
                print(f"[DEBUG] 載入對話歷史: {len(session.chat_history)} 筆")
                logger.info(f"載入對話歷史: {len(session.chat_history)} 筆")
                for msg in session.chat_history[-5:]:  # 最近 5 輪對話
                    role = "user" if msg["role"] == "user" else "model"
                    conversation_parts.append(
                        types.Content(
                            role=role,
                            parts=[types.Part.from_text(text=msg["content"])]
                        )
                    )
                print(f"[DEBUG] conversation_parts 包含 {len(conversation_parts)} 條歷史訊息")
                logger.info(f"conversation_parts 包含 {len(conversation_parts)} 條歷史訊息")
            else:
                print("[DEBUG] 沒有對話歷史（新 session）")
                logger.info("沒有對話歷史（新 session）")
            
            # 加入當前訊息
            # 系統提示總是以強制性指令的形式包含
            # 不使用 [系統提示] 標籤,避免 LLM 誤認為是參考資訊
            if not conversation_parts:
                # 新對話：系統提示 + 使用者訊息
                current_user_message = f"{system_prompt}\n\n使用者說：{user_message}"
            else:
                # 有歷史：直接重申系統提示（作為當前必須遵守的規則）
                current_user_message = f"{system_prompt}\n\n使用者現在說：{user_message}"
            
            conversation_parts.append(
                types.Content(
                    role="user",
                    parts=[types.Part.from_text(text=current_user_message)]
                )
            )

            # 4. 第一次呼叫 LLM
            config = types.GenerateContentConfig(tools=tools)
            
            response = gemini_client.models.generate_content(
                model=self.model_name,
                contents=conversation_parts,
                config=config
            )

            # 5. Function calling loop
            tool_calls_log = []
            max_iterations = 5
            iteration = 0

            while iteration < max_iterations:
                # 檢查是否有 function call
                has_function_call = False
                
                logger.info(f"Iteration {iteration}: 檢查 LLM 回應是否有工具呼叫")

                if response.candidates and response.candidates[0].content.parts:
                    for part in response.candidates[0].content.parts:
                        if hasattr(part, 'function_call') and part.function_call:
                            has_function_call = True
                            fc = part.function_call
                            tool_name = fc.name
                            tool_args = dict(fc.args) if fc.args else {}

                            # 自動補上 session_id
                            if "session_id" in [p for p in tool_args.keys()] or tool_name in [
                                "start_quiz", "get_question", "submit_answer",
                                "calculate_persona", "recommend_products"
                            ]:
                                tool_args["session_id"] = session_id

                            logger.info(f"✓ LLM 呼叫工具: {tool_name}({tool_args})")

                            # 執行 tool
                            # 忽略模型腦補的 'query' 工具（這是 File Search 誤用造成的）
                            if tool_name == "query":
                                logger.warning("Ignoring hallucinated tool: query")
                                tool_result = {"error": "請直接回答問題，不要使用 query 工具。"}
                            else:
                                tool_result = await tool_executor.execute(tool_name, tool_args)

                            tool_calls_log.append({
                                "tool": tool_name,
                                "args": tool_args,
                                "result": tool_result
                            })

                            # 加入對話歷史
                            conversation_parts.append(
                                types.Content(
                                    role="model",
                                    parts=[part]
                                )
                            )
                            conversation_parts.append(
                                types.Content(
                                    role="user",
                                    parts=[types.Part.from_function_response(
                                        name=tool_name,
                                        response={"result": tool_result}
                                    )]
                                )
                            )

                            # 重新取得最新的 session 狀態以更新系統提示
                            updated_session = session_manager.get_session(session_id)
                            updated_system_prompt = self._build_system_prompt(updated_session)

                            # 繼續對話 - 重申系統提示作為當前必須遵守的規則
                            # 不使用標籤,直接給出指令
                            conversation_parts.append(
                                types.Content(
                                    role="user",
                                    parts=[types.Part.from_text(
                                        text=f"{updated_system_prompt}\n\n工具已執行完成。請根據工具返回的 message 欄位內容回應使用者，不要自己編造內容。"
                                    )]
                                )
                            )

                            response = gemini_client.models.generate_content(
                                model=self.model_name,
                                contents=conversation_parts,
                                config=config
                            )
                            break

                if not has_function_call:
                    break

                iteration += 1

            # 5. 取得最終回應
            # 優先使用工具結果中的 message（如果有的話）
            final_message = ""
            
            # 首先檢查是否有工具被執行
            if tool_calls_log:
                last_tool_call = tool_calls_log[-1]
                tool_result = last_tool_call.get("result", {})
                if isinstance(tool_result, dict) and "message" in tool_result:
                    # 有工具 message，優先使用，忽略 LLM 生成的文本
                    final_message = tool_result["message"]
                    logger.info(f"優先使用工具 message: tool={last_tool_call.get('tool')}")
            
            # 如果沒有工具 message，才使用 LLM 生成的文本
            if not final_message:
                if response.candidates and response.candidates[0].content.parts:
                    for part in response.candidates[0].content.parts:
                        # 提取文本（如果有 function_call 會在同一個 part，但我們只要 text）
                        if hasattr(part, 'text') and part.text:
                            final_message += part.text
                
                if not final_message:
                    final_message = "AI目前故障 請聯絡"
                    logger.warning(f"LLM 未生成任何文本回應，使用者輸入：{user_message[:50]}")

            # 6. 保存對話歷史
            session_manager.add_chat_message(session_id, "user", user_message)
            session_manager.add_chat_message(session_id, "assistant", final_message)

            # 7. 記錄對話日誌（用於 debug）
            updated_session = session_manager.get_session(session_id)
            conversation_logger.log_conversation(
                session_id=session_id,
                user_message=user_message,
                agent_response=final_message,
                tool_calls=tool_calls_log,
                session_state={
                    "step": updated_session.step.value if updated_session else None,
                    "answers_count": len(updated_session.answers) if updated_session else 0,
                    "persona": updated_session.persona if updated_session else None,
                    "current_question_id": updated_session.current_question.get("id") if updated_session and updated_session.current_question else None
                } if updated_session else None
            )

            # 8. 回傳結果
            return {
                "message": final_message,
                "session": updated_session.model_dump() if updated_session else None,
                "tool_calls": tool_calls_log
            }

        except Exception as e:
            logger.error(f"Chat failed: {e}", exc_info=True)
            
            # 記錄錯誤到對話日誌
            conversation_logger.log_conversation(
                session_id=session_id,
                user_message=user_message,
                agent_response=f"[ERROR] {str(e)}",
                error=str(e)
            )
            
            return {
                "error": str(e),
                "message": f"抱歉，發生錯誤：{str(e)}"
            }


# 全域實例
main_agent = MainAgent()

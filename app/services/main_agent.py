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
        """建立 System Prompt - 測驗由後端處理，這裡只給 LLM 基本資訊"""
        return MAIN_AGENT_SYSTEM_PROMPT_TEMPLATE.format(
            session_id=session.session_id,
            step_value=session.step.value,
            answers_count=len(session.answers),
            persona=session.persona or '尚未計算'
        )

    def _build_tools(self) -> List[types.Tool]:
        """建立 tools - 只有開始測驗與推薦商品交給 LLM 呼叫"""
        function_declarations = [
            types.FunctionDeclaration(
                name="start_quiz",
                description="開始 MBTI 測驗。使用者表達想開始測驗時呼叫。",
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
                description="根據 MBTI 類型推薦商品。測驗完成後或使用者要求推薦時呼叫。",
                parameters={
                    "type": "object",
                    "properties": {
                        "session_id": {
                            "type": "string",
                            "description": "Session ID"
                        },
                        "max_results": {
                            "type": "integer",
                            "description": "最多推薦幾個商品",
                            "default": 3
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

            logger.info(f"[DEBUG] 發送給 LLM 的完整提示:\n{current_user_message[:500]}...")
            
            conversation_parts.append(
                types.Content(
                    role="user",
                    parts=[types.Part.from_text(text=current_user_message)]
                )
            )

            # 4. 第一次呼叫 LLM
            config = types.GenerateContentConfig(tools=tools)
            no_tool_config = types.GenerateContentConfig()
            
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
                            logger.info(f"[DEBUG] 更新系統提示")
                            logger.info(f"  - current_q_index: {updated_session.current_q_index}")
                            logger.info(f"  - answers: {updated_session.answers}")
                            logger.info(f"  - current_question_id: {updated_session.current_question.get('id') if updated_session.current_question else None}")
                            logger.info(f"  - system_prompt 包含當前題目: {'🎯 當前題目' in updated_system_prompt}")
                            logger.info(f"  - system_prompt 長度: {len(updated_system_prompt)} 字元")
                            if updated_session.current_question:
                                logger.info(f"  - 完整系統提示:\n{updated_system_prompt}")

                            # 繼續對話 - 根據工具返回內容決定如何更新系統提示
                            if "instruction_for_llm" in tool_result:
                                # 有明確指示，直接使用
                                instruction = tool_result['instruction_for_llm']
                            elif "message" in tool_result:
                                # 有預設訊息，請 LLM 用自然語氣回覆並完整保留內容
                                if tool_name == "start_quiz":
                                    instruction = (
                                        "請用自然語氣回應，並在回覆中完整保留題目與選項文字（原封不動）。"
                                        "可在前後加一句友善的引導話：\n"
                                        f"{tool_result['message']}"
                                    )
                                else:
                                    instruction = (
                                        "請用自然語氣回應，並在回覆中完整保留以下內容。"
                                        "可在前後加一句友善的引導話：\n"
                                        f"{tool_result['message']}"
                                    )
                            else:
                                # 沒有明確指示，讓 LLM 自由發揮
                                instruction = "請根據工具執行結果自然回應使用者。"

                            conversation_parts.append(
                                types.Content(
                                    role="user",
                                    parts=[types.Part.from_text(text=f"{updated_system_prompt}\n\n{instruction}")]
                                )
                            )

                            response = gemini_client.models.generate_content(
                                model=self.model_name,
                                contents=conversation_parts,
                                config=no_tool_config
                            )
                            break

                if not has_function_call:
                    break

                iteration += 1

            # 5. 取得最終回應（優先 LLM 產生的文本）
            final_message = ""

            if response.candidates and response.candidates[0].content.parts:
                for part in response.candidates[0].content.parts:
                    if hasattr(part, 'text') and part.text:
                        final_message += part.text

            if not final_message and tool_calls_log:
                # 後備：若 LLM 沒有產生文字，才使用工具 message
                last_tool_call = tool_calls_log[-1]
                tool_result = last_tool_call.get("result", {})
                if isinstance(tool_result, dict) and "message" in tool_result:
                    final_message = tool_result["message"]
                    logger.warning(f"LLM 無文字回應，改用工具 message: tool={last_tool_call.get('tool')}")

            if not final_message:
                final_message = "AI目前故障 請聯絡"
                logger.warning(f"LLM 未生成任何文本回應，使用者輸入：{user_message[:50]}")

            # 6. 保存對話歷史
            updated_session = session_manager.get_session(session_id)
            session_manager.add_chat_message(session_id, "user", user_message)
            session_manager.add_chat_message(session_id, "assistant", final_message)

            # 7. 記錄對話日誌（用於 debug）
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

        用於 QUIZ 流程：後端判斷並呼叫工具，LLM 負責生成自然回應
        """
        try:
            session = session_manager.get_session(session_id)
            if not session:
                return {"error": "Session not found", "message": "找不到 session"}

            # 建立對話上下文
            conversation_parts = []

            # 加入歷史對話（最多 5 筆）
            if session.chat_history:
                recent_history = session.chat_history[-5:]
                for msg in recent_history:
                    # 轉換 role：assistant → model
                    role = "model" if msg["role"] == "assistant" else msg["role"]
                    conversation_parts.append(
                        types.Content(
                            role=role,
                            parts=[types.Part.from_text(text=msg["content"])]
                        )
                    )

            # 根據工具結果生成指示
            if "instruction_for_llm" in tool_result:
                instruction = tool_result["instruction_for_llm"]
            elif tool_name == "start_quiz" and tool_result.get("current_question"):
                # 開始測驗，顯示第一題
                q = tool_result["current_question"]
                instruction = f"""測驗已開始，請用友善的語氣介紹並問第一題。

第1題：{q['text']}
A. {q['options'][0]['text']}
B. {q['options'][1]['text']}

必須完整顯示題目和選項，可以加一句簡短的開場白。"""
            elif "recommend_result" in tool_result:
                # 測驗完成 + 推薦
                persona_id = tool_result.get('persona_result', {}).get('persona_id', 'Unknown')
                recommend_msg = tool_result['recommend_result'].get('message', '')
                instruction = f"""使用者剛完成 MBTI 測驗，類型是 {persona_id}。

{recommend_msg}

請用友善、鼓勵的語氣回應，包含：
1. 恭喜完成測驗
2. MBTI 類型及特質描述
3. 推薦的商品"""
            else:
                instruction = "請簡短回應使用者"

            # 組合：system prompt + 使用者訊息 + 指示
            system_prompt = self._build_system_prompt(session)
            full_prompt = f"""{system_prompt}

使用者說：{user_message}

{instruction}"""

            conversation_parts.append(
                types.Content(
                    role="user",
                    parts=[types.Part.from_text(text=full_prompt)]
                )
            )

            # 呼叫 LLM 生成回應
            response = gemini_client.models.generate_content(
                model=self.model_name,
                contents=conversation_parts
            )

            # 提取回應
            final_message = ""
            if response.candidates and response.candidates[0].content.parts:
                for part in response.candidates[0].content.parts:
                    if hasattr(part, 'text') and part.text:
                        final_message += part.text

            if not final_message:
                final_message = "收到！"

            # 記錄對話（不在這裡記錄，由 API 層記錄）
            # session_manager.add_chat_message(session_id, "user", user_message)
            # session_manager.add_chat_message(session_id, "assistant", final_message)

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


# 全域實例
main_agent = MainAgent()

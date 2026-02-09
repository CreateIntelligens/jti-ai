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
from typing import Dict, List, Optional
import google.genai as genai
from google.genai import types
from app.models.session import Session, SessionStep
from app.services.session_manager_factory import get_session_manager, get_conversation_logger
from app.services.gemini_service import client as gemini_client
from app.tools.tool_executor import tool_executor
from app.services.agent_prompts import (
    MAIN_AGENT_SYSTEM_PROMPT_TEMPLATE,
    SYSTEM_INSTRUCTIONS,
    SESSION_STATE_TEMPLATES,
    CURRENT_QUESTION_TEMPLATE
)

# 使用工廠函數取得適當的實作（MongoDB 或記憶體）
session_manager = get_session_manager()
conversation_logger = get_conversation_logger()

logger = logging.getLogger(__name__)


class MainAgent:
    """主要對話 Agent"""

    def __init__(self):
        self.model_name = os.getenv("GEMINI_MODEL_NAME", "gemini-2.5-flash")

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

    def _build_tools(self, language: str = "zh") -> List[types.Tool]:
        """建立 tools - 只有開始測驗交給 LLM 呼叫"""
        # Tool descriptions 雙語版本
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

        function_declarations = [
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
        ]

        # 整合 Function Declarations + File Search
        tools = [types.Tool(function_declarations=function_declarations)]

        # 根據語言選擇對應的知識庫
        store_env_key = f"GEMINI_FILE_SEARCH_STORE_ID_{language.upper()}"
        file_search_store_id = os.getenv(store_env_key)

        # 向後相容：如果沒有語言專屬的，fallback 到舊的環境變數
        if not file_search_store_id:
            file_search_store_id = os.getenv("GEMINI_FILE_SEARCH_STORE_ID")

        if file_search_store_id:
            print(f"[DEBUG] 使用知識庫: {store_env_key}={file_search_store_id}")
            logger.info(f"使用知識庫: {store_env_key}={file_search_store_id}")
            tools.append(
                types.Tool(
                    file_search=types.FileSearch(
                        file_search_store_names=[f"fileSearchStores/{file_search_store_id}"]
                    )
                )
            )
        else:
            print(f"[DEBUG] ⚠️ 未設定知識庫: {store_env_key}")
            logger.warning(f"未設定知識庫: {store_env_key}")

        return tools

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

            # 2. 準備靜態 system instruction 和動態狀態
            system_instruction = self._get_system_instruction(session)  # 靜態規則（不變）
            session_state = self._get_session_state(session)  # 動態狀態（會變）
            tools = self._build_tools(language=session.language)  # 根據語言選擇知識庫

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

            # 加入當前訊息（包含動態狀態）
            current_message = f"{session_state}\n\n{user_message}"
            conversation_parts.append(
                types.Content(
                    role="user",
                    parts=[types.Part.from_text(text=current_message)]
                )
            )

            logger.info(f"[DEBUG] 使用者訊息: {user_message[:200]}...")

            # 4. 第一次呼叫 LLM（使用靜態 system_instruction）
            config = types.GenerateContentConfig(
                tools=tools,
                system_instruction=system_instruction  # 只包含不變的規則
            )
            no_tool_config = types.GenerateContentConfig(
                system_instruction=system_instruction
            )

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
                                "calculate_color_result"
                            ]:
                                tool_args["session_id"] = session_id

                            logger.info(f"✓ LLM 呼叫工具: {tool_name}({tool_args})")
                            print(f"[DEBUG TOOL] 工具呼叫: {tool_name}, user_message='{user_message}'")

                            # 執行 tool
                            # 忽略模型腦補的 'query' 工具（這是 File Search 誤用造成的）
                            if tool_name == "query":
                                logger.warning("Ignoring hallucinated tool: query")
                                tool_result = {"error": "請直接回答問題，不要使用 query 工具。"}
                            # 後端攔截：檢查 start_quiz 是否應該被阻擋
                            elif tool_name == "start_quiz":
                                # 檢查使用者訊息是否包含拒絕意圖
                                negative_keywords_zh = ["不想", "不要", "不用", "不玩", "跳過", "算了", "不了"]
                                negative_keywords_en = ["don't", "dont", "no ", "not ", "skip", "pass", "never"]
                                user_msg_lower = user_message.lower()

                                has_rejection = (
                                    any(kw in user_message for kw in negative_keywords_zh) or
                                    any(kw in user_msg_lower for kw in negative_keywords_en)
                                )

                                print(f"[DEBUG 攔截檢查] user_message='{user_message}', has_rejection={has_rejection}")

                                if has_rejection:
                                    print(f"[DEBUG] ✅ 攔截 start_quiz！使用者拒絕測驗")
                                    logger.warning(f"後端攔截: 使用者拒絕測驗，不執行 start_quiz")
                                    tool_result = {
                                        "blocked": True,
                                        "message": "使用者表示不想做測驗，請尊重使用者意願，不要開始測驗。"
                                    }
                                else:
                                    print(f"[DEBUG] ❌ 未攔截，執行 start_quiz")
                                    tool_result = await tool_executor.execute(tool_name, tool_args)
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

                            # 重新取得最新的 session 狀態
                            updated_session = session_manager.get_session(session_id)
                            updated_state = self._get_session_state(updated_session)
                            logger.info(f"[DEBUG] 更新狀態")
                            logger.info(f"  - current_q_index: {updated_session.current_q_index}")
                            logger.info(f"  - answers: {updated_session.answers}")
                            logger.info(f"  - current_question_id: {updated_session.current_question.get('id') if updated_session.current_question else None}")

                            # 繼續對話 - 根據工具返回內容決定如何更新
                            if "instruction_for_llm" in tool_result:
                                # 有明確指示，包含更新狀態
                                instruction = f"{updated_state}\n\n{tool_result['instruction_for_llm']}"
                            elif "message" in tool_result:
                                # 有預設訊息，請 LLM 用自然語氣回覆並完整保留內容
                                if tool_name == "start_quiz":
                                    instruction = (
                                        f"{updated_state}\n\n"
                                        "請用自然語氣回應，並在回覆中完整保留題目與選項文字（原封不動）。"
                                        "可在前後加一句友善的引導話：\n"
                                        f"{tool_result['message']}"
                                    )
                                else:
                                    instruction = (
                                        f"{updated_state}\n\n"
                                        "請用自然語氣回應，並在回覆中完整保留以下內容。"
                                        "可在前後加一句友善的引導話：\n"
                                        f"{tool_result['message']}"
                                    )
                            else:
                                # 沒有明確指示，讓 LLM 自由發揮
                                instruction = f"{updated_state}\n\n請根據工具執行結果自然回應使用者。"

                            conversation_parts.append(
                                types.Content(
                                    role="user",
                                    parts=[types.Part.from_text(text=instruction)]
                                )
                            )

                            # system_instruction 保持不變（只有靜態規則）
                            updated_config = types.GenerateContentConfig(
                                system_instruction=system_instruction
                            )

                            response = gemini_client.models.generate_content(
                                model=self.model_name,
                                contents=conversation_parts,
                                config=updated_config
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
                    "color_result_id": updated_session.color_result_id if updated_session else None,
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
                options = q.get("options", [])
                labels = "ABCDE"
                options_text = "\n".join(
                    f"{labels[i]}. {opt.get('text', '')}"
                    for i, opt in enumerate(options)
                )
                instruction = f"""測驗已開始，請用友善的語氣介紹並問第一題。

第1題：{q['text']}
{options_text}

必須完整顯示題目和選項，可以加一句簡短的開場白。"""
            elif "color_result" in tool_result and tool_result.get("message"):
                instruction = f"""使用者剛完成色彩測驗。

{tool_result['message']}

請用友善、鼓勵的語氣回應，包含：
1. 恭喜完成測驗
2. 色系結果與推薦色"""
            else:
                instruction = "請簡短回應使用者"

            # 組合：session state + 使用者訊息 + 指示
            session_state = self._get_session_state(session)
            full_prompt = f"""{session_state}

使用者說：{user_message}

{instruction}"""

            conversation_parts.append(
                types.Content(
                    role="user",
                    parts=[types.Part.from_text(text=full_prompt)]
                )
            )

            # 呼叫 LLM 生成回應（使用靜態 system instruction）
            system_instruction = self._get_system_instruction(session)
            config = types.GenerateContentConfig(
                system_instruction=system_instruction
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

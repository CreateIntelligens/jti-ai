"""
Main Agent - 核心對話邏輯

架構：
- 併發跑 Intent Check + File Search（都用 flash-lite）
- Intent=NO（無關話題）→ 跳過知識庫結果，直接讓主 agent 回應（自然婉拒）
- Intent=YES → 帶知識庫結果給主 agent 回應
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
    PERSONA,
    SYSTEM_INSTRUCTIONS,
    SESSION_STATE_TEMPLATES,
    build_system_instruction,
)

# 使用工廠函數取得適當的實作（MongoDB 或記憶體）
session_manager = get_session_manager()

logger = logging.getLogger(__name__)

# File Search 用 flash-lite（不帶 system_instruction 即可正常 grounding）
FILE_SEARCH_MODEL = "gemini-2.5-flash-lite"


class MainAgent:
    """主要對話 Agent"""

    def __init__(self):
        self.model_name = os.getenv("GEMINI_MODEL_NAME", "gemini-2.5-flash-lite")
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
            loop = asyncio.get_running_loop()
            loop.run_in_executor(None, self._sync_history_to_db, session_id, user_message, assistant_message)
        except Exception:
            self._sync_history_to_db(session_id, user_message, assistant_message)

    def remove_session(self, session_id: str):
        """清除記憶體中的 chat session"""
        self._chat_sessions.pop(session_id, None)

    def remove_all_sessions(self):
        """清除所有記憶體中的 chat sessions（切換 prompt 時使用）"""
        count = len(self._chat_sessions)
        self._chat_sessions.clear()
        if count > 0:
            logger.info(f"已清除 {count} 個 chat sessions")

    # 重用 ToolExecutor 的 _format_options（避免重複定義）
    _format_options_text = staticmethod(ToolExecutor._format_options)

    def _get_system_instruction(self, session: Session) -> str:
        """取得靜態 System Instruction（persona from DB + system rules from code）"""
        persona = None
        try:
            from app import deps
            if deps.prompt_manager:
                active = deps.prompt_manager.get_active_prompt("__jti__")
                if active:
                    persona = active.content
        except Exception:
            pass
        if not persona:
            persona = PERSONA.get(session.language, PERSONA["zh"])
        return build_system_instruction(persona, session.language)

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

    def _check_intent_fast(self, query: str) -> str:
        """快速判斷是否為不相關話題 (File Search 前置過濾)"""
        try:
            prompt = f"""判斷以下使用者語句是否與「JTI傑太日煙、Ploom X加熱菸、菸彈、配件、生活色彩測驗」相關。
如果使用者在詢問完全無關的知識（例如：天氣、美食清單、旅遊景點、寫程式設計問題、政治等），請回覆 NO。
如果是打招呼、表達感謝、日常簡短對話，或是與上述相關的主題，請回覆 YES。

使用者訊息：「{query}」

只能回覆 YES 或 NO："""
            response = gemini_client.models.generate_content(
                model=FILE_SEARCH_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(thinking_config=types.ThinkingConfig(thinking_budget=0)),
            )
            res = response.text.strip().upper() if response.text else "YES"
            logger.info(f"[Intent Check] 結果: {res} | 訊息: '{query[:30]}...'")
            return "NO" if "NO" in res else "YES"
        except Exception as e:
            logger.error(f"[Intent Check] failed: {e}")
            return "YES"

    async def chat(
        self,
        session_id: str,
        user_message: str,
    ) -> Dict:
        """
        處理對話

        流程：
        1. 併發跑 Intent Check + File Search
        2. Intent=NO → 跳過知識庫，直接讓主 agent 自然婉拒
        3. Intent=YES → 帶知識庫結果給主 agent 回應
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

            # 1. 併發執行 Intent Check 和 File Search
            loop = asyncio.get_running_loop()
            t0 = time.time()

            intent_task = asyncio.ensure_future(
                loop.run_in_executor(None, self._check_intent_fast, user_message))
            search_task = asyncio.ensure_future(
                loop.run_in_executor(None, self._file_search, user_message, session.language))

            # 等第一個完成；若 intent 先回 NO 就不等 File Search
            done, _ = await asyncio.wait(
                [intent_task, search_task],
                return_when=asyncio.FIRST_COMPLETED,
            )

            if intent_task in done and intent_task.result() == "NO":
                kb_result = None
                logger.info(f"[計時] Intent=NO 快速攔截: {(time.time()-t0)*1000:.0f}ms")
            else:
                await asyncio.gather(intent_task, search_task)
                intent = intent_task.result()
                kb_result = search_task.result() if intent == "YES" else None
                logger.info(f"[計時] Intent={intent}, File Search: {(time.time()-t0)*1000:.0f}ms")

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

            # 3. 清理 chat session 歷史：把 enriched_message 替換回乾淨的 user_message
            #    避免 KB 結果累積在歷史中淹沒後續的短追問
            if kb_result and hasattr(chat_session, '_curated_history') and chat_session._curated_history:
                last_user = chat_session._curated_history[-2]  # send_message 後倒數第二筆是 user
                if last_user.role == "user":
                    last_user.parts = [types.Part.from_text(text=user_message)]
                    logger.info(f"[歷史清理] 已將 enriched_message 替換回乾淨的 user_message")

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

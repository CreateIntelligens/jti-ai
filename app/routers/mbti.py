"""
MBTI 遊戲 API Endpoints
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
import logging
from app.services.session_manager import session_manager
from app.services.main_agent import main_agent
from app.models.session import GameMode
from app.services.conversation_logger import conversation_logger

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/mbti", tags=["MBTI Game"])


# === Request/Response Models ===

class CreateSessionRequest(BaseModel):
    """建立 session 請求"""
    mode: GameMode = GameMode.MBTI
    language: str = "zh"  # 語言 (zh/en)


class CreateSessionResponse(BaseModel):
    """建立 session 回應"""
    session_id: str
    mode: str
    step: str
    message: str = "測驗已準備好，隨時可以開始！"


class ChatRequest(BaseModel):
    """對話請求"""
    session_id: str = Field(..., description="Session ID")
    message: str = Field(..., description="使用者訊息")
    store_id: Optional[str] = Field(None, description="File Search Store ID（選用）")
    language: Optional[str] = Field(None, description="語言 (zh/en)")


class ChatResponse(BaseModel):
    """對話回應"""
    message: str
    session: Optional[Dict[str, Any]] = None
    tool_calls: Optional[list] = None
    error: Optional[str] = None


class GetSessionResponse(BaseModel):
    """取得 session 回應"""
    session: Dict[str, Any]


# === Endpoints ===

@router.post("/session/new", response_model=CreateSessionResponse)
async def create_session(request: CreateSessionRequest):
    """
    建立新的測驗 session

    這會初始化一個新的 MBTI 測驗流程
    """
    try:
        session = session_manager.create_session(mode=request.mode, language=request.language)

        logger.info(f"Created new session: {session.session_id} (language={request.language})")

        return CreateSessionResponse(
            session_id=session.session_id,
            mode=session.mode.value,
            step=session.step.value,
            message="測驗已準備好，請說「開始測驗」來開始！"
        )

    except Exception as e:
        logger.error(f"Failed to create session: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/session/{session_id}", response_model=GetSessionResponse)
async def get_session(session_id: str):
    """
    取得 session 狀態

    查詢目前測驗的進度和結果
    """
    try:
        session = session_manager.get_session(session_id)

        if session is None:
            raise HTTPException(status_code=404, detail="Session not found")

        return GetSessionResponse(
            session=session.model_dump()
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get session: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    主要對話端點

    流程設計：
    1. WELCOME/一般狀態：走 LLM（可用知識庫）
       - 使用者說「MBTI」「測驗」「玩」→ 開始測驗
       - 其他問題 → 正常回答

    2. QUIZ 狀態（有當前題目）：後端完全接管
       - 先用規則判斷使用者選 A 還是 B（明確 A/B/1/2 或選項文字）
       - 規則無法判斷時，再用 LLM 判斷
       - 判斷成功 → 呼叫 submit_answer，回覆下一題
       - 判斷失敗 → AI 打哈哈 + 重問當前題
       - **不走知識庫，鎖定作答**
    """
    try:
        session = session_manager.get_session(request.session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        # 如果前端傳來 language，更新 session
        if request.language and request.language != session.language:
            session.language = request.language
            logger.info(f"Updated session language: {session.session_id} -> {request.language}")

        from app.tools.tool_executor import tool_executor

        # ========== QUIZ 狀態：後端完全接管 ==========
        if session.step.value == "QUIZ" and session.current_question:
            q = session.current_question
            remaining = 5 - len(session.answers)
            current_q_num = len(session.answers) + 1

            # 格式化當前題目
            current_q_text = f"第{current_q_num}題：{q['text']}\nA. {q['options'][0]['text']}\nB. {q['options'][1]['text']}"

            # 用 LLM 判斷 A/B
            user_choice = await _judge_user_choice(request.message, q)

            if user_choice:
                # ✅ 判斷成功，呼叫 submit_answer
                tool_result = await tool_executor.execute("submit_answer", {
                    "session_id": request.session_id,
                    "user_choice": user_choice
                })

                updated_session = session_manager.get_session(request.session_id)

                # 記錄工具呼叫
                tool_calls = [{"tool": "submit_answer", "args": {"user_choice": user_choice}, "result": tool_result}]

                # 測驗完成時自動推薦商品
                if tool_result.get("is_complete"):
                    recommend_result = await tool_executor.execute("recommend_products", {
                        "session_id": request.session_id
                    })
                    tool_result["recommend_result"] = recommend_result
                    tool_calls.append({"tool": "recommend_products", "args": {}, "result": recommend_result})

                # 交給 main_agent 的 LLM 處理回應（生成評論 + 下一題）
                result = await main_agent.chat_with_tool_result(
                    session_id=request.session_id,
                    user_message=request.message,
                    tool_name="submit_answer",
                    tool_args={"user_choice": user_choice},
                    tool_result=tool_result
                )

                response_message = result["message"]
                updated_session = session_manager.get_session(request.session_id)

                # 記錄到對話日誌
                conversation_logger.log_conversation(
                    session_id=request.session_id,
                    user_message=request.message,
                    agent_response=response_message,
                    tool_calls=tool_calls,
                    session_state={
                        "step": updated_session.step.value,
                        "answers_count": len(updated_session.answers),
                        "persona": updated_session.persona,
                        "current_question_id": updated_session.current_question.get("id") if updated_session.current_question else None
                    }
                )

                logger.info(f"✅ QUIZ 作答成功: {request.message} → {user_choice}")

                response_tool_calls = [
                    {k: v for k, v in call.items() if k != "result"}
                    for call in tool_calls
                ]

                return ChatResponse(
                    message=response_message,
                    session=updated_session.model_dump(),
                    tool_calls=response_tool_calls
                )
            else:
                # ❌ 無法判斷 A/B：用 AI 打哈哈 + 重問當前題
                nudge_instruction = (
                    "使用者回覆不是 A/B 選項，請用一句輕鬆的語氣敷衍回答，"
                    f"並提醒還剩 {remaining} 題，然後重問當前題目：\n\n{current_q_text}"
                )

                nudge_result = await main_agent.chat_with_tool_result(
                    session_id=request.session_id,
                    user_message=request.message,
                    tool_name="quiz_nudge",
                    tool_args={},
                    tool_result={"instruction_for_llm": nudge_instruction}
                )

                response_message = nudge_result["message"]

                # 記錄對話
                session_manager.add_chat_message(request.session_id, "user", request.message)
                session_manager.add_chat_message(request.session_id, "assistant", response_message)

                # 記錄到對話日誌
                conversation_logger.log_conversation(
                    session_id=request.session_id,
                    user_message=request.message,
                    agent_response=response_message,
                    tool_calls=[],
                    session_state={
                        "step": session.step.value,
                        "answers_count": len(session.answers),
                        "persona": session.persona,
                        "current_question_id": session.current_question.get("id") if session.current_question else None
                    }
                )

                logger.info(f"⚠️ QUIZ 無法判斷選項: {request.message}")

                return ChatResponse(
                    message=response_message,
                    session=session.model_dump(),
                    tool_calls=[]
                )

        # ========== 非 QUIZ 狀態 ==========

        # 先用關鍵字判斷是否要開始測驗（不依賴 LLM 呼叫工具）
        start_keywords = ['mbti', '測驗', '心理測驗', '開始', '玩', '試試', '來吧', '好啊', '開始吧', 'quiz', 'start']
        negative_keywords = ['不想', '不要', '不用', '不玩', '跳過', '算了', '不了', "don't", "dont", "no ", "not ", "skip", "pass", "never"]
        msg_lower = request.message.lower()

        # 檢查是否有開始意圖
        has_start_intent = any(kw in msg_lower for kw in start_keywords)
        # 檢查是否有拒絕意圖
        has_rejection = any(kw in msg_lower for kw in negative_keywords) or any(kw in request.message for kw in negative_keywords)

        # 只有在有開始意圖且沒有拒絕時才開始測驗
        should_start_quiz = has_start_intent and not has_rejection

        logger.info(f"[DEBUG] 測驗判斷: has_start={has_start_intent}, has_rejection={has_rejection}, should_start={should_start_quiz}")

        # 如果已完成測驗想再測一次，拒絕
        if should_start_quiz and session.step.value == "DONE":
            response_message = "你已經完成過測驗囉！這次對話只能測驗一次。如果想重新測驗，請重新整理頁面開始新的對話。"

            # 記錄對話
            conversation_logger.log_conversation(
                session_id=request.session_id,
                user_message=request.message,
                agent_response=response_message,
                tool_calls=[],
                session_state={
                    "step": session.step.value,
                    "answers_count": len(session.answers),
                    "persona": session.persona,
                    "current_question_id": None
                }
            )

            return ChatResponse(
                message=response_message,
                session=session.model_dump(),
                tool_calls=[]
            )

        if should_start_quiz and session.step.value == "WELCOME":
            # 直接呼叫 start_quiz，不依賴 LLM
            tool_result = await tool_executor.execute("start_quiz", {
                "session_id": request.session_id
            })

            if tool_result.get("success"):
                # 讓 LLM 生成自然的開場白
                result = await main_agent.chat_with_tool_result(
                    session_id=request.session_id,
                    user_message=request.message,
                    tool_name="start_quiz",
                    tool_args={"session_id": request.session_id},
                    tool_result=tool_result
                )

                updated_session = session_manager.get_session(request.session_id)

                # 記錄對話
                conversation_logger.log_conversation(
                    session_id=request.session_id,
                    user_message=request.message,
                    agent_response=result["message"],
                    tool_calls=[{"tool": "start_quiz", "args": {"session_id": request.session_id}, "result": tool_result}],
                    session_state={
                        "step": updated_session.step.value,
                        "answers_count": len(updated_session.answers),
                        "persona": updated_session.persona,
                        "current_question_id": updated_session.current_question.get("id") if updated_session.current_question else None
                    }
                )

                return ChatResponse(
                    message=result["message"],
                    session=updated_session.model_dump(),
                    tool_calls=[{"tool": "start_quiz", "args": {"session_id": request.session_id}}]
                )

        # 一般對話：走 LLM
        result = await main_agent.chat(
            session_id=request.session_id,
            user_message=request.message,
            store_id=request.store_id
        )

        return ChatResponse(**result)

    except Exception as e:
        logger.error(f"Chat failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


async def _judge_user_choice(user_message: str, question: dict) -> Optional[str]:
    """
    先用規則判斷，判不出時用 LLM 判斷使用者選擇 A 還是 B

    Returns:
        "A", "B", 或 None（無法判斷）
    """
    import os
    from google import genai

    msg = user_message.strip()
    msg_upper = msg.upper()
    msg_lower = msg.lower()

    # 快速判斷：明確的 A/B
    if msg_upper in ['A', 'B']:
        return msg_upper
    if 'A' in msg_upper and 'B' not in msg_upper:
        return 'A'
    if 'B' in msg_upper and 'A' not in msg_upper:
        return 'B'

    # 快速判斷：數字
    if msg in ['1', '一', '第一']:
        return 'A'
    if msg in ['2', '二', '第二']:
        return 'B'

    # 快速判斷：包含選項文字
    options = question.get("options", []) if isinstance(question, dict) else []
    opt_a = options[0].get("text", "") if len(options) > 0 else ""
    opt_b = options[1].get("text", "") if len(options) > 1 else ""

    if opt_a and opt_a.lower() in msg_lower:
        return 'A'
    if opt_b and opt_b.lower() in msg_lower:
        return 'B'

    # 用 LLM 判斷（規則判不出時）
    try:
        client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

        prompt = f"""判斷使用者選擇了哪個選項。

題目：{question.get('text', '')}
A. {opt_a}
B. {opt_b}

使用者回覆：「{user_message}」

規則：
- 如果使用者明確選擇或傾向 A 選項 → 回覆 A
- 如果使用者明確選擇或傾向 B 選項 → 回覆 B
- 如果無法判斷或使用者在問問題/閒聊 → 回覆 X

只回覆一個字母：A、B 或 X"""

        model_name = os.getenv("GEMINI_MODEL_NAME", "gemini-2.0-flash")
        response = client.models.generate_content(
            model=model_name,
            contents=prompt
        )

        result = response.text.strip().upper()

        if result in ['A', 'B']:
            logger.info(f"LLM 判斷: '{user_message}' → {result}")
            return result
        else:
            logger.info(f"LLM 無法判斷: '{user_message}' → {result}")
            return None

    except Exception as e:
        logger.error(f"LLM 判斷失敗: {e}")
        return None


@router.delete("/session/{session_id}")
async def delete_session(session_id: str):
    """
    刪除 session

    清除測驗記錄
    """
    try:
        success = session_manager.delete_session(session_id)

        if not success:
            raise HTTPException(status_code=404, detail="Session not found")

        return {"message": "Session deleted successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete session: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sessions")
async def list_sessions():
    """
    列出所有 sessions（測試用）
    """
    try:
        sessions = session_manager.get_all_sessions()
        return {
            "sessions": [s.model_dump() for s in sessions],
            "total": len(sessions)
        }

    except Exception as e:
        logger.error(f"Failed to list sessions: {e}")
        raise HTTPException(status_code=500, detail=str(e))

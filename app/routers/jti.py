"""
JTI 測驗系統 API Endpoints
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
import logging
from app.services.session.session_manager_factory import get_session_manager, get_conversation_logger
from app.services.jti.main_agent import main_agent
from app.models.session import GameMode

# 使用工廠函數取得適當的實作（MongoDB 或記憶體）
session_manager = get_session_manager()
conversation_logger = get_conversation_logger()

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/jti", tags=["JTI Quiz"])

QUIZ_PAUSE_MESSAGE_ZH = (
    "好呀，那我先幫你暫停測驗，我們回到一般問答。"
    "之後想接著做，請輸入「繼續測驗」。"
)

# === Request/Response Models ===

class CreateSessionRequest(BaseModel):
    """建立 session 請求"""
    mode: GameMode = GameMode.COLOR
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


class QuizActionRequest(BaseModel):
    """測驗控制請求（不透過自然語言判斷）"""
    session_id: str = Field(..., description="Session ID")


class GetSessionResponse(BaseModel):
    """取得 session 回應"""
    session: Dict[str, Any]


# === Endpoints ===

@router.post("/session/new", response_model=CreateSessionResponse)
async def create_session(request: CreateSessionRequest):
    """
    建立新的測驗 session

    這會初始化一個新的色彩測驗流程
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
       - 使用者說「色彩」「顏色」「測驗」「玩」→ 開始測驗
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

        # 記錄用戶訊息
        logger.info(f"[用戶訊息] Session: {request.session_id[:8]}... | 狀態: {session.step.value} | 訊息: '{request.message}'")

        # 如果前端傳來 language，更新 session
        if request.language and request.language != session.language:
            session.language = request.language
            logger.info(f"Updated session language: {session.session_id} -> {request.language}")

        from app.tools.tool_executor import tool_executor

        # ========== QUIZ 狀態：後端完全接管 ==========
        if session.step.value == "QUIZ" and session.current_question:
            from app.tools.quiz import get_total_questions

            q = session.current_question
            total_questions = get_total_questions(session.quiz_id)
            remaining = total_questions - len(session.answers)
            current_q_num = len(session.answers) + 1

            msg = request.message.strip()
            # 使用者想中斷/暫停測驗：回到一般問答（保留進度）
            # 只對明確的「中斷」做規則判斷，其餘意圖交由 _judge_user_choice 的 LLM 輔助判斷，
            # 避免像「我不想太華麗，所以選B」這種作答理由被誤判為想退出測驗。
            if msg == "中斷":
                return _pause_quiz_and_respond(
                    session_id=request.session_id,
                    log_user_message=request.message,
                    session=session,
                )

            # 格式化當前題目
            options_text = _format_options_text(q.get("options", []))
            current_q_text = f"第{current_q_num}題：{q['text']}\n{options_text}"

            # 記錄當前測驗進度
            logger.info(f"[測驗進度] 第 {current_q_num}/{total_questions} 題 | 題目: {q.get('text', '')[:30]}...")

            # 用規則/LLM 判斷選項
            user_choice = await _judge_user_choice(request.message, q)

            logger.info(f"[答題判斷] 使用者回答: '{request.message}' -> 判定選項: {user_choice}")

            if user_choice == "PAUSE":
                return _pause_quiz_and_respond(
                    session_id=request.session_id,
                    log_user_message=request.message,
                    session=session,
                )

            if user_choice:
                # ✅ 判斷成功，呼叫 submit_answer
                tool_result = await tool_executor.execute("submit_answer", {
                    "session_id": request.session_id,
                    "user_choice": user_choice
                })

                updated_session = session_manager.get_session(request.session_id)

                # 記錄答題結果和當前分數
                logger.info(f"[答題結果] 選項: {user_choice} | 已答: {len(updated_session.answers)}/{total_questions} 題")
                if updated_session.color_scores:
                    scores_str = " | ".join([f"{k}:{v}" for k, v in sorted(updated_session.color_scores.items(), key=lambda x: -x[1])])
                    logger.info(f"[當前分數] {scores_str}")

                # 記錄工具呼叫
                tool_calls = [{"tool": "submit_answer", "args": {"user_choice": user_choice}, "result": tool_result}]

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

                # 記錄 AI 回應
                logger.info(f"[AI回應] {response_message[:100]}{'...' if len(response_message) > 100 else ''}")

                # 記錄到對話日誌
                conversation_logger.log_conversation(
                    session_id=request.session_id,
                    user_message=request.message,
                    agent_response=response_message,
                    tool_calls=tool_calls,
                    session_state={
                        "step": updated_session.step.value,
                        "answers_count": len(updated_session.answers),
                        "color_result_id": updated_session.color_result_id,
                        "current_question_id": updated_session.current_question.get("id") if updated_session.current_question else None
                    },
                    mode="jti"
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
                # ❌ 無法判斷選項：用 AI 打哈哈 + 重問當前題
                nudge_instruction = (
                    "使用者回覆不是選項，請用一句輕鬆的語氣敷衍回答，"
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

                # 記錄 AI 回應
                logger.info(f"[AI回應] 無法判斷選項，重問 | {response_message[:80]}...")

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
                        "color_result_id": session.color_result_id,
                        "current_question_id": session.current_question.get("id") if session.current_question else None
                    },
                    mode="jti"
                )

                logger.info(f"⚠️ QUIZ 無法判斷選項: {request.message}")

                return ChatResponse(
                    message=response_message,
                    session=session.model_dump(),
                    tool_calls=[]
                )

        # ========== 非 QUIZ 狀態 ==========

        # 先用關鍵字判斷是否要開始測驗（不依賴 LLM 呼叫工具）
        # 移除單獨的「色彩」「顏色」避免誤判產品諮詢（如「有什麼顏色」）
        start_keywords = ['測驗', '心理測驗', '色彩測驗', '配色測驗', '開始', '玩', '試試', '來吧', '好啊', '開始吧', 'quiz', 'start']
        negative_keywords = ['不想', '不要', '不用', '不玩', '跳過', '算了', '不了', "don't", "dont", "no ", "not ", "skip", "pass", "never"]
        resume_keywords = ['繼續測驗', '繼續', '接著', '接續', '回到測驗', 'continue', 'resume']
        msg_lower = request.message.lower()

        # 檢查是否有開始意圖
        has_start_intent = any(kw in msg_lower for kw in start_keywords)
        wants_resume = any(kw in msg_lower for kw in resume_keywords)
        # 檢查是否有拒絕意圖
        has_rejection = any(kw in msg_lower for kw in negative_keywords) or any(kw in request.message for kw in negative_keywords)

        # 只有在有開始意圖且沒有拒絕時才開始測驗
        should_start_quiz = has_start_intent and not has_rejection

        logger.info(f"[DEBUG] 測驗判斷: has_start={has_start_intent}, has_rejection={has_rejection}, should_start={should_start_quiz}")

        # 若先前暫停過測驗，允許繼續（預設繼續；除非使用者明確說要重新開始）
        paused_quiz = bool(session.metadata.get("paused_quiz")) and bool(session.selected_questions)
        if (
            session.step.value == "WELCOME"
            and paused_quiz
            and not has_rejection
            and (wants_resume or should_start_quiz)
        ):
            return _resume_quiz_and_respond(
                session_id=request.session_id,
                log_user_message=request.message,
                session=session,
                no_progress_message="我這邊沒有找到可接續的測驗進度喔。想重新開始的話請說「開始測驗」。",
                log_progress=True,
            )

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
                        "color_result_id": session.color_result_id,
                        "current_question_id": None
                    },
                mode="jti"
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

                # 記錄 AI 回應
                logger.info(f"[AI回應] 測驗開始 | {result['message'][:80]}...")

                # 記錄對話
                conversation_logger.log_conversation(
                    session_id=request.session_id,
                    user_message=request.message,
                    agent_response=result["message"],
                    tool_calls=[{"tool": "start_quiz", "args": {"session_id": request.session_id}, "result": tool_result}],
                    session_state={
                        "step": updated_session.step.value,
                        "answers_count": len(updated_session.answers),
                        "color_result_id": updated_session.color_result_id,
                        "current_question_id": updated_session.current_question.get("id") if updated_session.current_question else None
                    },
                    mode="jti"
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

        # 記錄 AI 回應
        logger.info(f"[AI回應] 一般對話 | {result['message'][:80]}...")

        return ChatResponse(**result)

    except Exception as e:
        logger.error(f"Chat failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/quiz/start", response_model=ChatResponse)
async def quiz_start(request: QuizActionRequest):
    """
    直接開始測驗（不依賴自然語言判斷）

    用途：
    - 前端按鈕/流程控制
    - curl / 自動化測試
    """
    try:
        session = session_manager.get_session(request.session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        if session.step.value == "DONE":
            response_message = "你已經完成過測驗囉！這次對話只能測驗一次。如果想重新測驗，請重新整理頁面開始新的對話。"
            return ChatResponse(
                message=response_message,
                session=session.model_dump(),
                tool_calls=[],
            )

        from app.tools.tool_executor import tool_executor

        tool_result = await tool_executor.execute("start_quiz", {"session_id": request.session_id})
        updated_session = session_manager.get_session(request.session_id)

        if not tool_result.get("success"):
            return ChatResponse(
                message=tool_result.get("error", "start_quiz failed"),
                session=updated_session.model_dump() if updated_session else session.model_dump(),
                tool_calls=[],
                error=tool_result.get("error"),
            )

        q = tool_result.get("current_question") or (updated_session.current_question if updated_session else None)
        options = q.get("options", []) if isinstance(q, dict) else []
        options_text = _format_options_text(options)

        if updated_session and updated_session.language == "en":
            response_message = f"Let's start.\n\nQuestion 1: {q.get('text', '')}\n{options_text}"
        else:
            response_message = (
                "想來做個生活品味色彩探索測驗嗎？ 簡單五個測驗，尋找你的命定手機殼，"
                "如果中途想離開，請輸入中斷，即可繼續問答，那我們開始測驗吧！\n\n"
                f"第1題：{q.get('text', '')}\n{options_text}"
            )

        conversation_logger.log_conversation(
            session_id=request.session_id,
            user_message="[API] quiz_start",
            agent_response=response_message,
            tool_calls=[{"tool": "start_quiz", "args": {"session_id": request.session_id}, "result": tool_result}],
            session_state={
                "step": updated_session.step.value if updated_session else session.step.value,
                "answers_count": len(updated_session.answers) if updated_session else len(session.answers),
                "color_result_id": updated_session.color_result_id if updated_session else session.color_result_id,
                "current_question_id": q.get("id") if isinstance(q, dict) else None,
            },
            mode="jti",
        )

        return ChatResponse(
            message=response_message,
            session=updated_session.model_dump() if updated_session else session.model_dump(),
            tool_calls=[{"tool": "start_quiz", "args": {"session_id": request.session_id}}],
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"quiz_start failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/quiz/pause", response_model=ChatResponse)
async def quiz_pause(request: QuizActionRequest):
    """
    直接暫停測驗（不依賴自然語言判斷）
    """
    try:
        session = session_manager.get_session(request.session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        return _pause_quiz_and_respond(
            session_id=request.session_id,
            log_user_message="[API] quiz_pause",
            session=session,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"quiz_pause failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/quiz/resume", response_model=ChatResponse)
async def quiz_resume(request: QuizActionRequest):
    """
    直接繼續先前暫停的測驗（不依賴自然語言判斷）
    """
    try:
        session = session_manager.get_session(request.session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        return _resume_quiz_and_respond(
            session_id=request.session_id,
            log_user_message="[API] quiz_resume",
            session=session,
            no_progress_message="我這邊沒有找到可接續的測驗進度喔。想開始測驗的話請呼叫 /api/jti/quiz/start。",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"quiz_resume failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


def _format_options_text(options: list) -> str:
    labels = "ABCDE"
    lines = []
    for idx, opt in enumerate(options):
        label = labels[idx] if idx < len(labels) else str(idx + 1)
        lines.append(f"{label}. {opt.get('text', '')}")
    return "\n".join(lines)


def _pause_quiz_and_respond(session_id: str, log_user_message: str, session: Any) -> ChatResponse:
    updated_session = session_manager.pause_quiz(session_id)
    response_message = QUIZ_PAUSE_MESSAGE_ZH

    conversation_logger.log_conversation(
        session_id=session_id,
        user_message=log_user_message,
        agent_response=response_message,
        tool_calls=[],
        session_state={
            "step": updated_session.step.value if updated_session else session.step.value,
            "answers_count": len(updated_session.answers) if updated_session else len(session.answers),
            "color_result_id": updated_session.color_result_id if updated_session else session.color_result_id,
            "current_question_id": None,
        },
        mode="jti",
    )

    return ChatResponse(
        message=response_message,
        session=updated_session.model_dump() if updated_session else session.model_dump(),
        tool_calls=[],
    )


def _resume_quiz_and_respond(
    session_id: str,
    log_user_message: str,
    session: Any,
    *,
    no_progress_message: str,
    log_progress: bool = False,
) -> ChatResponse:
    updated_session = session_manager.resume_quiz(session_id)
    resumed_q = updated_session.current_question if updated_session else None

    if not resumed_q:
        response_message = no_progress_message
        return ChatResponse(
            message=response_message,
            session=(updated_session.model_dump() if updated_session else session.model_dump()),
            tool_calls=[],
        )

    current_q_num = (updated_session.current_q_index + 1) if updated_session else (len(session.answers) + 1)

    options_text = _format_options_text(resumed_q.get("options", []))
    response_message = f"好呀，我們接著做第{current_q_num}題。\n第{current_q_num}題：{resumed_q.get('text', '')}\n{options_text}"

    conversation_logger.log_conversation(
        session_id=session_id,
        user_message=log_user_message,
        agent_response=response_message,
        tool_calls=[],
        session_state={
            "step": updated_session.step.value if updated_session else session.step.value,
            "answers_count": len(updated_session.answers) if updated_session else len(session.answers),
            "color_result_id": updated_session.color_result_id if updated_session else session.color_result_id,
            "current_question_id": resumed_q.get("id") if isinstance(resumed_q, dict) else None,
        },
        mode="jti",
    )

    if log_progress:
        from app.tools.quiz import get_total_questions

        total_questions = get_total_questions(updated_session.quiz_id) if updated_session else 5
        logger.info(f"✅ QUIZ 繼續測驗: 第 {current_q_num}/{total_questions} 題")

    return ChatResponse(
        message=response_message,
        session=updated_session.model_dump() if updated_session else session.model_dump(),
        tool_calls=[],
    )


async def _judge_user_choice(user_message: str, question: dict) -> Optional[str]:
    """
    先用規則判斷，判不出時用 LLM 判斷使用者選擇哪個選項

    Returns:
        "A"~"E" 或 None（無法判斷）
    """
    import os
    from google import genai

    msg = user_message.strip()
    msg_upper = msg.upper()
    msg_lower = msg.lower()

    options = question.get("options", []) if isinstance(question, dict) else []
    labels = list("ABCDE")[: len(options)]

    # 快速判斷：明確的 A-E
    if msg_upper in labels:
        logger.info(f"[規則判斷] 明確字母: '{user_message}' -> {msg_upper}")
        return msg_upper
    # 只把「獨立字母」當作答案；避免像 "pause" 這種字串含有 A 而誤判為選 A
    import re
    label_hits = [
        label
        for label in labels
        if re.search(rf"(?<![A-Z]){label}(?![A-Z])", msg_upper)
    ]
    if len(label_hits) == 1:
        logger.info(f"[規則判斷] 獨立字母: '{user_message}' -> {label_hits[0]}")
        return label_hits[0]

    # 快速判斷：數字或中文序號
    number_map = {
        "1": 0, "一": 0, "第一": 0,
        "2": 1, "二": 1, "第二": 1,
        "3": 2, "三": 2, "第三": 2,
        "4": 3, "四": 3, "第四": 3,
        "5": 4, "五": 4, "第五": 4,
    }
    if msg in number_map and number_map[msg] < len(options):
        result = labels[number_map[msg]]
        logger.info(f"[規則判斷] 數字/序號: '{user_message}' -> {result}")
        return result
    if msg.isdigit():
        idx = int(msg) - 1
        if 0 <= idx < len(options):
            logger.info(f"[規則判斷] 純數字: '{user_message}' -> {labels[idx]}")
            return labels[idx]
    digit_hits = [d for d in ["1", "2", "3", "4", "5"] if d in msg]
    if len(digit_hits) == 1:
        idx = int(digit_hits[0]) - 1
        if 0 <= idx < len(options):
            logger.info(f"[規則判斷] 包含數字: '{user_message}' -> {labels[idx]}")
            return labels[idx]

    # 快速判斷：包含選項文字
    for idx, opt in enumerate(options):
        text = opt.get("text", "")
        if text and text.lower() in msg_lower:
            logger.info(f"[規則判斷] 匹配選項文字: '{user_message}' -> {labels[idx]} ('{text}')")
            return labels[idx]

    # 用 LLM 判斷（規則判不出時）
    logger.info(f"[LLM判斷] 規則無法判定，呼叫 LLM: '{user_message}'")
    try:
        client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

        prompt = f"""判斷使用者意圖：作答、或是想暫停/中斷測驗。

題目：{question.get('text', '')}
{_format_options_text(options)}

使用者回覆：「{user_message}」

規則：
- 如果使用者明確表示要暫停/中斷/停止/結束/退出測驗 → 回覆 PAUSE
- 如果使用者明確選擇或傾向某選項（即使在解釋理由） → 回覆該選項的字母
- 如果無法判斷或使用者在問問題/閒聊 → 回覆 X

只回覆：A 至 E、PAUSE 或 X"""

        model_name = os.getenv("GEMINI_MODEL_NAME", "gemini-2.0-flash")
        response = client.models.generate_content(
            model=model_name,
            contents=prompt
        )

        result = response.text.strip().upper()

        if result in labels:
            logger.info(f"[LLM判斷] 成功: '{user_message}' -> {result}")
            return result
        if result == "PAUSE":
            logger.info(f"[LLM判斷] 暫停測驗: '{user_message}' -> PAUSE")
            return "PAUSE"
        else:
            logger.info(f"[LLM判斷] 失敗/無法判斷: '{user_message}' -> {result}")
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


@router.get("/conversations")
async def get_conversations(session_id: Optional[str] = None, mode: str = "jti"):
    """
    取得對話歷史

    Query Parameters:
    - session_id: (可選) 指定 Session ID 則只回傳該 session 的對話
    - mode: 對話模式，預設 "jti"

    如果不提供 session_id，則回傳所有 JTI 模式的對話（按 session 分組）
    """
    try:
        if session_id:
            # 查詢特定 session
            conversations = conversation_logger.get_session_logs(session_id)
            conversations = [c for c in conversations if c.get("mode") == mode]

            logger.info(f"Retrieved {len(conversations)} conversations for session {session_id}")

            return {
                "session_id": session_id,
                "mode": mode,
                "conversations": conversations,
                "total": len(conversations)
            }
        else:
            # 查詢所有 JTI 對話
            all_conversations = conversation_logger.get_session_logs_by_mode(mode)

            # 按 session_id 分組
            sessions = {}
            for conv in all_conversations:
                sid = conv.get("session_id")
                if sid not in sessions:
                    sessions[sid] = {
                        "session_id": sid,
                        "conversations": [],
                        "first_message_time": conv.get("timestamp"),
                        "total": 0
                    }
                sessions[sid]["conversations"].append(conv)
                sessions[sid]["total"] += 1

            # 轉換成列表，按時間排序
            session_list = list(sessions.values())
            session_list.sort(key=lambda x: x["first_message_time"], reverse=True)

            logger.info(f"Retrieved {len(all_conversations)} total conversations across {len(session_list)} sessions")

            return {
                "mode": mode,
                "sessions": session_list,
                "total_conversations": len(all_conversations),
                "total_sessions": len(session_list)
            }

    except Exception as e:
        logger.error(f"Failed to get conversations: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/conversations/export")
async def export_conversations(session_ids: Optional[str] = None, mode: str = "jti"):
    """
    匯出對話歷史為 JSON 格式

    Query Parameters:
    - session_ids: (可選) 指定一個或多個 Session ID（用逗號分隔），只匯出指定的 sessions
    - mode: 對話模式，預設 "jti"

    範例:
    - 單個 session: ?session_ids=abc123
    - 多個 sessions: ?session_ids=abc123,def456,ghi789
    - 所有 sessions: 不提供 session_ids 參數

    如果不提供 session_ids，則匯出所有 JTI 模式的對話（按 session 分組）
    """
    try:
        from datetime import datetime

        if session_ids:
            # 解析 session_ids（支援逗號分隔）
            session_id_list = [sid.strip() for sid in session_ids.split(',') if sid.strip()]

            # 收集指定 sessions 的對話
            sessions = []
            total_conversations = 0

            for session_id in session_id_list:
                conversations = conversation_logger.get_session_logs(session_id)
                conversations = [c for c in conversations if c.get("mode") == mode]

                if conversations:
                    sessions.append({
                        "session_id": session_id,
                        "conversations": conversations,
                        "first_message_time": conversations[0].get("timestamp") if conversations else None,
                        "total": len(conversations)
                    })
                    total_conversations += len(conversations)

            # 按時間排序
            sessions.sort(key=lambda x: x["first_message_time"] or "", reverse=True)

            return {
                "exported_at": datetime.utcnow().isoformat(),
                "mode": mode,
                "sessions": sessions,
                "total_conversations": total_conversations,
                "total_sessions": len(sessions)
            }
        else:
            # 匯出所有 JTI 對話
            all_conversations = conversation_logger.get_session_logs_by_mode(mode)

            # 按 session_id 分組
            sessions = {}
            for conv in all_conversations:
                sid = conv.get("session_id")
                if sid not in sessions:
                    sessions[sid] = {
                        "session_id": sid,
                        "conversations": [],
                        "first_message_time": conv.get("timestamp"),
                        "total": 0
                    }
                sessions[sid]["conversations"].append(conv)
                sessions[sid]["total"] += 1

            # 轉換成列表，按時間排序
            session_list = list(sessions.values())
            session_list.sort(key=lambda x: x["first_message_time"], reverse=True)

            return {
                "exported_at": datetime.utcnow().isoformat(),
                "mode": mode,
                "sessions": session_list,
                "total_conversations": len(all_conversations),
                "total_sessions": len(session_list)
            }

    except Exception as e:
        logger.error(f"Failed to export conversations: {e}")
        raise HTTPException(status_code=500, detail=str(e))

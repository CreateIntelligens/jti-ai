"""
JTI 測驗系統 API Endpoints
"""

import os
import re
from datetime import datetime

from fastapi import APIRouter, HTTPException, Depends
from google import genai
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, Dict, Any, List, Union
import logging
from app.services.session.session_manager_factory import get_session_manager, get_conversation_logger
from app.services.jti.main_agent import main_agent
from app.models.session import GameMode
from app.auth import verify_auth, require_admin
from app.tools.tool_executor import tool_executor
from app.tools.quiz import get_total_questions
from app.utils import group_conversations_by_session

# 使用工廠函數取得適當的實作（MongoDB 或記憶體）
session_manager = get_session_manager()
conversation_logger = get_conversation_logger()

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/jti", tags=["JTI Quiz"])

# === Request/Response Models ===

class CreateSessionRequest(BaseModel):
    """建立 session 請求"""
    language: str = "zh"  # 語言 (zh/en)
    previous_session_id: Optional[str] = None  # 舊 session ID，用於清理記憶體


class CreateSessionResponse(BaseModel):
    """建立 session 回應"""
    ok: bool = True
    session_id: str
    message: str = "Session created"


class ChatRequest(BaseModel):
    """對話請求"""
    session_id: str = Field(..., description="Session ID")
    message: str = Field(..., description="使用者訊息")
    turn_number: Optional[int] = Field(None, description="若是重新生成，則指定該訊息的 turn_number（之後的記錄會被刪除）")


class ChatResponse(BaseModel):
    """對話回應"""
    message: str
    session: Optional[Dict[str, Any]] = None
    tool_calls: Optional[list] = None
    turn_number: Optional[int] = None
    error: Optional[str] = None


class QuizActionRequest(BaseModel):
    """測驗控制請求（不透過自然語言判斷）"""
    session_id: str = Field(..., description="Session ID")



class ConversationToolCall(BaseModel):
    """工具呼叫記錄"""
    tool: Optional[str] = None
    tool_name: Optional[str] = None
    args: Dict[str, Any] = Field(default_factory=dict)
    result: Dict[str, Any] = Field(default_factory=dict)
    execution_time_ms: Optional[float] = None

    model_config = ConfigDict(extra="allow")


class ConversationItem(BaseModel):
    """單筆對話記錄"""
    mongo_id: Optional[str] = Field(default=None, alias="_id", description="MongoDB document ID")
    session_id: str
    mode: str
    turn_number: Optional[int] = None
    timestamp: str
    responded_at: Optional[str] = None
    user_message: str
    agent_response: str
    tool_calls: List[ConversationToolCall] = Field(default_factory=list)
    session_snapshot: Optional[Dict[str, Any]] = None
    session_state: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

    model_config = ConfigDict(populate_by_name=True, extra="allow")


class ConversationSessionGroup(BaseModel):
    """按 session 分組的對話"""
    session_id: str
    conversations: List[ConversationItem]
    first_message_time: Optional[str] = None
    total: int


class ConversationSessionSummary(BaseModel):
    """Session 摘要（不含完整對話）"""
    session_id: str
    first_message_time: Optional[str] = None
    last_message_time: Optional[str] = None
    message_count: int
    preview: Optional[str] = None


class ConversationsBySessionResponse(BaseModel):
    """查詢單一 session 對話回應"""
    session_id: str
    mode: str
    conversations: List[ConversationItem]
    total: int


class ConversationsGroupedResponse(BaseModel):
    """查詢多個 sessions 對話回應"""
    mode: str
    sessions: List[ConversationSessionGroup]
    total_conversations: int
    total_sessions: int


class DeleteConversationResponse(BaseModel):
    """刪除對話回應"""
    ok: bool
    deleted_logs: int
    deleted_session: bool


class ExportConversationsResponse(BaseModel):
    """匯出對話回應"""
    exported_at: str
    mode: str
    sessions: List[ConversationSessionGroup]
    total_conversations: int
    total_sessions: int


class GeneralConversationsBySessionResponse(BaseModel):
    """General chat 單一 session 對話查詢回應"""
    session_id: str
    store_name: str
    mode: str
    conversations: List[ConversationItem]
    total: int


class GeneralConversationsResponse(BaseModel):
    """General chat 對話查詢回應（摘要列表）"""
    store_name: str
    mode: str
    sessions: List[ConversationSessionSummary]
    total_conversations: int
    total_sessions: int


class ExportGeneralConversationsResponse(BaseModel):
    """General chat 對話匯出回應"""
    exported_at: str
    store_name: str
    mode: str
    sessions: List[ConversationSessionGroup]
    total_conversations: int
    total_sessions: int


# === Helpers ===

def _get_or_rebuild_session(session_id: str):
    """取得 session，若已過期則嘗試從 conversation logs 重建"""
    session = session_manager.get_session(session_id)
    if session:
        return session

    # 嘗試從 conversation logs 重建
    logs = conversation_logger.get_session_logs(session_id)
    jti_logs = [l for l in logs if l.get("mode") == "jti"]
    if not jti_logs:
        return None

    session = session_manager.rebuild_session_from_logs(session_id, jti_logs)
    if session:
        logger.info(f"Rebuilt expired JTI session from {len(jti_logs)} logs: {session_id[:8]}...")
        # 清除記憶體中的舊 LLM chat session（下次呼叫時會從 chat_history 自動重建）
        main_agent.remove_session(session_id)
    return session


# === Endpoints ===

@router.post("/chat/start", response_model=CreateSessionResponse)
async def create_session(request: CreateSessionRequest, auth: dict = Depends(verify_auth)):
    """
    建立新的 JTI 對話 Session

    回傳 session_id 供後續 /api/jti/chat/message 使用
    """
    try:
        # 清理舊 session 的記憶體 chat session
        if request.previous_session_id:
            main_agent.remove_session(request.previous_session_id)
            logger.info(f"Cleaned up previous chat session: {request.previous_session_id[:8]}...")

        session = session_manager.create_session(mode=GameMode.COLOR, language=request.language)

        logger.info(f"Created new session: {session.session_id} (language={request.language})")

        return CreateSessionResponse(
            session_id=session.session_id,
            message="Session created"
        )

    except Exception as e:
        logger.error(f"Failed to create session: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/chat/message", response_model=ChatResponse)
async def chat(request: ChatRequest, auth: dict = Depends(verify_auth)):
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
        session = _get_or_rebuild_session(request.session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        # 記錄用戶訊息
        logger.info(f"[用戶訊息] Session: {request.session_id[:8]}... | 狀態: {session.step.value} | 訊息: '{request.message}'")

        # ========== 重新生成 / 回滾邏輯 ==========
        if request.turn_number is not None:
            # 1. 刪除該 turn 及之後的 logs
            deleted_count = conversation_logger.delete_turns_from(request.session_id, request.turn_number)
            if deleted_count > 0:
                # 2. 重新讀取剩餘 logs 並重建 session
                logs = conversation_logger.get_session_logs(request.session_id)
                # 若 logs 全空（例如刪除的是第一句話），session 可能回退到初始狀態
                session = session_manager.rebuild_session_from_logs(request.session_id, logs)
                if not session:
                    # 重建失敗（例如 logs 為空）→ 直接用現有 session（rollback 前的）
                    session = _get_or_rebuild_session(request.session_id)
                    if not session:
                        raise HTTPException(status_code=404, detail="Session not found after rollback")

                # 3. 清除 LLM 記憶體快取，確保下次建構時不會混入已刪除的歷史
                main_agent.remove_session(request.session_id)

                logger.info(f"Session {request.session_id[:8]}... rolled back to before turn {request.turn_number}")
            else:
                logger.warning(f"Failed to delete logs from turn {request.turn_number}")

        # ========== QUIZ 狀態：後端完全接管 ==========
        if session.step.value == "QUIZ" and session.current_question:
            q = session.current_question
            total_questions = get_total_questions(session.quiz_id)
            remaining = total_questions - len(session.answers)
            current_q_num = len(session.answers) + 1

            msg = request.message.strip()
            # 使用者想中斷/暫停測驗：回到一般問答（保留進度）
            # 只對明確的「中斷」做規則判斷，其餘意圖交由 _judge_user_choice 的 LLM 輔助判斷，
            # 避免像「我不想太華麗，所以選B」這種作答理由被誤判為想退出測驗。
            if msg == "中斷":
                return await _pause_quiz_and_respond(
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
                return await _pause_quiz_and_respond(
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
                        "current_question_id": updated_session.current_question.get("id") if updated_session.current_question else None,
                        "language": updated_session.language,
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
                # ❌ 無法判斷選項：用 AI 打哈哈 + 程式碼強制附加題目
                nudge_instruction = (
                    "使用者在測驗中回覆了不是選項的內容。"
                    "【嚴格禁止】不要回答使用者的問題，不要提供任何產品資訊或知識。"
                    "只需用一句話（20字以內）敷衍帶過，引導回測驗。"
                    "例如：「哈哈好啦～先做完測驗再聊！」「這個等等再說～先答題吧！」"
                )

                nudge_result = await main_agent.chat_with_tool_result(
                    session_id=request.session_id,
                    user_message=request.message,
                    tool_name="quiz_nudge",
                    tool_args={},
                    tool_result={"instruction_for_llm": nudge_instruction}
                )

                # 程式碼強制附加題目（若 LLM 已自帶題目則不重複）
                nudge_text = nudge_result["message"].strip()
                q_text_key = q.get("text", "")
                if q_text_key and q_text_key in nudge_text:
                    response_message = nudge_text
                else:
                    response_message = f"{nudge_text}\n\n{current_q_text}"

                # 記錄 AI 回應
                logger.info(f"[AI回應] 無法判斷選項，重問 | {response_message[:80]}...")

                # 記錄到對話日誌
                # 對於 QUIZ 錯誤處理回應，我們也需要記錄，並且需要與其他 log_turn 保持一致
                # 但這裡原本是用 log_conversation，它會自動計算 turn_number
                # 為了避免 rollback 後 turn_number 錯亂，我們明確傳入 turn_number
                
                # 如果 request.turn_number 存在，我們先執行刪除
                if request.turn_number:
                     conversation_logger.delete_turns_from(request.session_id, request.turn_number)

                log_result = conversation_logger.log_conversation(
                    session_id=request.session_id,
                    user_message=request.message,
                    agent_response=response_message,
                    tool_calls=[],
                    session_state={
                        "step": session.step.value,
                        "answers_count": len(session.answers),
                        "color_result_id": session.color_result_id,
                        "current_question_id": session.current_question.get("id") if session.current_question else None,
                        "language": session.language,
                    },
                    mode="jti"
                )
                
                final_turn_number = log_result[1] if log_result else None

                logger.info(f"⚠️ QUIZ 無法判斷選項: {request.message}")

                return ChatResponse(
                    message=response_message,
                    session=session.model_dump(),
                    tool_calls=[],
                    turn_number=final_turn_number
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
            # 刪除 rollback 的 logs (如果有的話)
            if request.turn_number:
                conversation_logger.delete_turns_from(request.session_id, request.turn_number)
                
            return _resume_quiz_and_respond(
                session_id=request.session_id,
                log_user_message=request.message,
                session=session,
                no_progress_message="我這邊沒有找到可接續的測驗進度喔。想重新開始的話請說「開始測驗」。",
                log_progress=True,
            )

        # 如果已完成測驗想再測一次，婉拒
        if should_start_quiz and session.step.value == "DONE":
            if session.language == "en":
                response_message = "You've already completed the quiz! Please refresh the page to start a new session if you'd like to retake it."
            else:
                response_message = "你已經完成過測驗囉！如果想重新測驗，請重新整理頁面開始新的對話。"

            # 記錄對話
            if request.turn_number:
                conversation_logger.delete_turns_from(request.session_id, request.turn_number)
            
            log_result = conversation_logger.log_conversation(
                session_id=request.session_id,
                user_message=request.message,
                agent_response=response_message,
                tool_calls=[],
                session_state={
                    "step": session.step.value,
                    "answers_count": len(session.answers),
                    "color_result_id": session.color_result_id,
                    "current_question_id": None,
                    "language": session.language,
                },
                mode="jti"
            )
            
            final_turn_number = log_result[1] if log_result else None

            return ChatResponse(
                message=response_message,
                session=session.model_dump(),
                tool_calls=[],
                turn_number=final_turn_number
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
                # 如果 request.turn_number 存在，我們先執行刪除
                if request.turn_number:
                     conversation_logger.delete_turns_from(request.session_id, request.turn_number)

                log_result = conversation_logger.log_conversation(
                    session_id=request.session_id,
                    user_message=request.message,
                    agent_response=result["message"],
                    tool_calls=[{"tool": "start_quiz", "args": {"session_id": request.session_id}, "result": tool_result}],
                    session_state={
                        "step": updated_session.step.value,
                        "answers_count": len(updated_session.answers),
                        "color_result_id": updated_session.color_result_id,
                        "current_question_id": updated_session.current_question.get("id") if updated_session.current_question else None,
                        "language": updated_session.language,
                    },
                    mode="jti"
                )
                
                final_turn_number = log_result[1] if log_result else None

                return ChatResponse(
                    message=result["message"],
                    session=updated_session.model_dump(),
                    tool_calls=[{"tool": "start_quiz", "args": {"session_id": request.session_id}}],
                    turn_number=final_turn_number
                )

        # 一般對話：走 LLM
        result = await main_agent.chat(
            session_id=request.session_id,
            user_message=request.message,
        )
        
        # 記錄 AI 回應
        logger.info(f"[AI回應] 一般對話 | {result['message'][:80]}...")

        # 記錄對話
        # 如果 request.turn_number 存在，我們先執行刪除
        if request.turn_number:
            conversation_logger.delete_turns_from(request.session_id, request.turn_number)

        log_result = conversation_logger.log_conversation(
            session_id=request.session_id,
            user_message=request.message,
            agent_response=result["message"],
            tool_calls=result.get("tool_calls", []),
            session_state={
                "step": session.step.value,
                "answers_count": len(session.answers),
                "color_result_id": session.color_result_id,
                "current_question_id": session.current_question.get("id") if session.current_question else None,
                "language": session.language,
            },
            mode="jti"
        )
        
        final_turn_number = log_result[1] if log_result else None

        return ChatResponse(**result, turn_number=final_turn_number)

    except Exception as e:
        logger.error(f"Chat failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/quiz/start", response_model=ChatResponse)
async def quiz_start(request: QuizActionRequest, auth: dict = Depends(verify_auth)):
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
            if session.language == "en":
                response_message = "You've already completed the quiz! Please refresh the page to start a new session."
            else:
                response_message = "你已經完成過測驗囉！這次對話只能測驗一次。如果想重新測驗，請重新整理頁面開始新的對話。"
            
            log_result = conversation_logger.log_conversation(
                session_id=request.session_id,
                user_message="[API] quiz_start",
                agent_response=response_message,
                tool_calls=[],
                session_state={
                    "step": session.step.value,
                    "answers_count": len(session.answers),
                    "color_result_id": session.color_result_id,
                    "current_question_id": None,
                    "language": session.language,
                },
                mode="jti"
            )
            
            final_turn_number = log_result[1] if log_result else None
            
            return ChatResponse(
                message=response_message,
                session=session.model_dump(),
                tool_calls=[],
                turn_number=final_turn_number
            )

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

        log_result = conversation_logger.log_conversation(
            session_id=request.session_id,
            user_message="[API] quiz_start",
            agent_response=response_message,
            tool_calls=[{"tool": "start_quiz", "args": {"session_id": request.session_id}, "result": tool_result}],
            session_state={
                "step": updated_session.step.value if updated_session else session.step.value,
                "answers_count": len(updated_session.answers) if updated_session else len(session.answers),
                "color_result_id": updated_session.color_result_id if updated_session else session.color_result_id,
                "current_question_id": q.get("id") if isinstance(q, dict) else None,
                "language": updated_session.language if updated_session else session.language,
            },
            mode="jti",
        )
        
        final_turn_number = log_result[1] if log_result else None

        return ChatResponse(
            message=response_message,
            session=updated_session.model_dump() if updated_session else session.model_dump(),
            tool_calls=[{"tool": "start_quiz", "args": {"session_id": request.session_id}}],
            turn_number=final_turn_number
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"quiz_start failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/quiz/pause", response_model=ChatResponse)
async def quiz_pause(request: QuizActionRequest, auth: dict = Depends(verify_auth)):
    """
    直接暫停測驗（不依賴自然語言判斷）
    """
    try:
        session = _get_or_rebuild_session(request.session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        return await _pause_quiz_and_respond(
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
async def quiz_resume(request: QuizActionRequest, auth: dict = Depends(verify_auth)):
    """
    直接繼續先前暫停的測驗（不依賴自然語言判斷）
    """
    try:
        session = _get_or_rebuild_session(request.session_id)
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


async def _pause_quiz_and_respond(
    session_id: str,
    log_user_message: str,
    session: Any,
    turn_number_hint: Optional[int] = None
) -> ChatResponse:
    updated_session = session_manager.pause_quiz(session_id)

    # 暫停後，將使用者訊息交給 AI 回應
    ai_result = await main_agent.chat(
        session_id=session_id,
        user_message=log_user_message,
    )
    response_message = ai_result.get("message", "收到！")

    if turn_number_hint:
        conversation_logger.delete_turns_from(session_id, turn_number_hint)

    log_result = conversation_logger.log_conversation(
        session_id=session_id,
        user_message=log_user_message,
        agent_response=response_message,
        tool_calls=[],
        session_state={
            "step": updated_session.step.value if updated_session else session.step.value,
            "answers_count": len(updated_session.answers) if updated_session else len(session.answers),
            "color_result_id": updated_session.color_result_id if updated_session else session.color_result_id,
            "current_question_id": None,
            "language": updated_session.language if updated_session else session.language,
        },
        mode="jti",
    )
    
    final_turn_number = log_result[1] if log_result else None

    return ChatResponse(
        message=response_message,
        session=updated_session.model_dump() if updated_session else session.model_dump(),
        tool_calls=[],
        turn_number=final_turn_number
    )


def _resume_quiz_and_respond(
    session_id: str,
    log_user_message: str,
    session: Any,
    *,
    no_progress_message: str,
    log_progress: bool = False,
    turn_number_hint: Optional[int] = None
) -> ChatResponse:
    updated_session = session_manager.resume_quiz(session_id)
    resumed_q = updated_session.current_question if updated_session else None
    
    # 這裡不需要 turn_number_hint，因為 rollback 邏輯在 caller 處理了 (chat_message endpoint)
    # 但為了 robust，log_conversation 會自動正確計算
    if turn_number_hint:
        conversation_logger.delete_turns_from(session_id, turn_number_hint)

    if not resumed_q:
        response_message = no_progress_message
        return ChatResponse(
            message=response_message,
            session=(updated_session.model_dump() if updated_session else session.model_dump()),
            tool_calls=[],
        )

    current_q_num = (updated_session.current_q_index + 1) if updated_session else (len(session.answers) + 1)

    options_text = _format_options_text(resumed_q.get("options", []) if hasattr(resumed_q, 'get') else [])
    # resumed_q might be dict or object, safe get handled above
    
    question_text = resumed_q.get('text', '') if isinstance(resumed_q, dict) else ''
    
    if updated_session and updated_session.language == "en":
        response_message = f"Sure! Let's continue with Question {current_q_num}.\n\nQuestion {current_q_num}: {question_text}\n{options_text}"
    else:
        response_message = f"好呀，我們接著做第{current_q_num}題。\n\n第{current_q_num}題：{question_text}\n{options_text}"

    log_result = conversation_logger.log_conversation(
        session_id=session_id,
        user_message=log_user_message,
        agent_response=response_message,
        tool_calls=[],
        session_state={
            "step": updated_session.step.value if updated_session else session.step.value,
            "answers_count": len(updated_session.answers) if updated_session else len(session.answers),
            "color_result_id": updated_session.color_result_id if updated_session else session.color_result_id,
            "current_question_id": resumed_q.get("id") if isinstance(resumed_q, dict) else None,
            "language": updated_session.language if updated_session else session.language,
        },
        mode="jti",
    )
    
    final_turn_number = log_result[1] if log_result else None

    if log_progress:
        total_questions = get_total_questions(updated_session.quiz_id) if updated_session else 5
        logger.info(f"✅ QUIZ 繼續測驗: 第 {current_q_num}/{total_questions} 題")

    return ChatResponse(
        message=response_message,
        session=updated_session.model_dump() if updated_session else session.model_dump(),
        tool_calls=[],
        turn_number=final_turn_number
    )


async def _judge_user_choice(user_message: str, question: dict) -> Optional[str]:
    """
    先用規則判斷，判不出時用 LLM 判斷使用者選擇哪個選項

    Returns:
        "A"~"E" 或 None（無法判斷）
    """
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

        model_name = os.getenv("GEMINI_MODEL_NAME", "gemini-2.5-flash-lite")
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


@router.get(
    "/history",
    response_model=Union[ConversationsBySessionResponse, ConversationsGroupedResponse],
    response_model_exclude_none=True,
)
async def get_conversations(
    session_id: Optional[str] = None,
    page: int = 1,
    page_size: int = 10,
    auth: dict = Depends(verify_auth)
):
    """
    取得對話歷史

    Query Parameters:
    - session_id: (可選) 指定 Session ID 則只回傳該 session 的對話
    - page: (可選) 頁碼，預設 1
    - page_size: (可選) 每頁筆數，預設 10

    如果不提供 session_id，則回傳所有 JTI 模式的對話（按 session 分組，支援分頁）
    """
    mode = "jti"
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
            # 分頁查詢所有 JTI 對話
            session_ids, total_sessions = conversation_logger.get_paginated_session_ids(
                query={"mode": mode},
                page=page,
                page_size=page_size
            )

            all_conversations = conversation_logger.get_logs_for_sessions(session_ids)
            session_list = group_conversations_by_session(all_conversations)

            logger.info(f"Retrieved {len(all_conversations)} conversations across {len(session_list)} sessions (page {page}, total {total_sessions})")

            return {
                "mode": mode,
                "sessions": session_list,
                "total_conversations": len(all_conversations), # 這是當前頁面的對話總數
                "total_sessions": total_sessions # 這是總 session 數（用於前端分頁）
            }

    except Exception as e:
        logger.error(f"Failed to get conversations: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/history/{session_id}", response_model=DeleteConversationResponse)
async def delete_conversation(session_id: str, auth: dict = Depends(verify_auth)):
    """刪除指定 session 的對話紀錄

    同時刪除：
    - 對話日誌 (conversation logs)
    - JTI session
    - 記憶體中的 chat session
    """

    deleted_logs = conversation_logger.delete_session_logs(session_id)
    deleted_session = session_manager.delete_session(session_id)
    main_agent.remove_session(session_id)

    return {
        "ok": True,
        "deleted_logs": deleted_logs,
        "deleted_session": deleted_session,
    }


@router.get(
    "/history/export",
    response_model=ExportConversationsResponse,
    response_model_exclude_none=True,
)
async def export_conversations(session_ids: Optional[str] = None, auth: dict = Depends(verify_auth)):
    """
    匯出對話歷史為 JSON 格式

    Query Parameters:
    - session_ids: (可選) 指定一個或多個 Session ID（用逗號分隔），只匯出指定的 sessions

    範例:
    - 單個 session: ?session_ids=abc123
    - 多個 sessions: ?session_ids=abc123,def456,ghi789
    - 所有 sessions: 不提供 session_ids 參數

    如果不提供 session_ids，則匯出所有 JTI 模式的對話（按 session 分組）
    """
    mode = "jti"
    try:
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

            session_list = group_conversations_by_session(all_conversations)

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

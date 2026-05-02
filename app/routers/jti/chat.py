"""
JTI Chat API — session management, chat messages, and conversation history.
"""

from copy import deepcopy
from datetime import datetime, timezone, timedelta
from typing import Optional, Union

_TZ_TAIPEI = timezone(timedelta(hours=8))

from fastapi import APIRouter, HTTPException, Depends
import logging

import app.deps as deps
from app.auth import verify_admin, verify_auth
from app.models.session import SessionStep
from app.routers.tts_utils import attach_tts_message_id, register_tts_endpoints
from app.schemas.chat import (
    ChatRequest,
    ChatResponse,
    ConversationsBySessionResponse,
    ConversationsGroupedResponse,
    CreateSessionRequest,
    CreateSessionResponse,
    DeleteConversationRequest,
    DeleteConversationResponse,
    ExportConversationsResponse,
)
from app.services.jti.main_agent import main_agent
from app.services.jti.runtime_quiz_flow import execute_quiz_start, handle_quiz_message
from app.services.jti.tts import to_jti_tts_text

from app.utils import build_date_query, export_sessions_by_ids, group_conversations_by_session
from app.services.jti.quiz_helpers import (
    _get_or_rebuild_session,
    build_session_state,
    is_quiz_start_intent,
)


_OPENING_MESSAGE: dict[str, str] = {
    "zh": "Hello，我是今天的活動大使Lady X，對我說「測驗」即可做「尋找命定前蓋」小遊戲，或想知道關於Ploom X加熱菸更多資訊，都歡迎和我聊聊，很樂意為您解答！",
    "en": "Hi! I'm Lady X. Got any questions, or want to take a quiz?",
}

logger = logging.getLogger(__name__)

runtime_router = APIRouter(prefix="/api/jti", tags=["JTI Chat"], dependencies=[Depends(verify_auth)])
compat_history_router = APIRouter(
    prefix="/api/jti",
    tags=["JTI Conversations"],
    include_in_schema=False,
    dependencies=[Depends(verify_admin)],
)
admin_history_router = APIRouter(
    prefix="/api/jti-admin/conversations",
    tags=["JTI Conversations"],
    dependencies=[Depends(verify_admin)],
)
router = runtime_router

def _get_session_manager():
    return deps.get_jti_session_manager()


def _get_conversation_logger():
    return deps.get_jti_conversation_logger()


def _get_tts_manager():
    return deps.get_jti_tts_job_manager()


register_tts_endpoints(runtime_router, _get_tts_manager, text_formatter=to_jti_tts_text)


# === Endpoints ===

@runtime_router.post("/chat/start", response_model=CreateSessionResponse)
async def create_session(request: CreateSessionRequest):
    """建立新的 JTI 對話 Session"""
    try:
        session_manager = _get_session_manager()
        if request.previous_session_id:
            main_agent.remove_session(request.previous_session_id)
            logger.info(f"Cleaned up previous chat session: {request.previous_session_id[:8]}...")

        session = session_manager.create_session(language=request.language)
        logger.info(f"Created new session: {session.session_id} (language={request.language})")

        opening = _OPENING_MESSAGE.get(request.language, _OPENING_MESSAGE["zh"])
        return CreateSessionResponse(session_id=session.session_id, opening_message=opening)

    except Exception as e:
        logger.error(f"Failed to create session: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@runtime_router.post("/chat/message", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    主要對話端點

    流程設計：
    1. WELCOME/一般狀態：走 LLM（可用知識庫）
       - 使用者說「測驗」「前蓋」「玩」→ 開始測驗
       - 其他問題 → 正常回答

    2. QUIZ 狀態（有當前題目）：後端完全接管
       - 先用規則判斷使用者選 A 還是 B（明確 A/B/1/2 或選項文字）
       - 規則無法判斷時，再用 LLM 判斷
       - 判斷成功 → 呼叫 submit_answer，回覆下一題
       - 判斷失敗 → hardcode 提示 + 重問當前題
       - **不走知識庫，鎖定作答**
    """
    try:
        session_manager = _get_session_manager()
        conversation_logger = _get_conversation_logger()
        session = _get_or_rebuild_session(request.session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        preserved_selected_questions = (
            deepcopy(session.selected_questions) if session.selected_questions else None
        )

        logger.info(f"[用戶訊息] Session: {request.session_id[:8]}... | 狀態: {session.step.value} | 訊息: '{request.message}'")

        # ========== 重新生成 / 回滾邏輯 ==========
        if request.turn_number is not None:
            deleted_count = conversation_logger.delete_turns_from(request.session_id, request.turn_number)
            if deleted_count > 0:
                all_logs = conversation_logger.get_session_logs(request.session_id)
                logs = [l for l in all_logs if l.get("mode") == "jti"]
                if logs:
                    session = session_manager.rebuild_session_from_logs(request.session_id, logs)
                    if not session:
                        raise HTTPException(status_code=500, detail="Failed to rebuild session from logs")
                else:
                    session.step = SessionStep.WELCOME
                    session.answers = {}
                    session.current_question = None
                    session.current_q_index = 0
                    session.selected_questions = None
                    session.quiz_scores = {}
                    session.quiz_result_id = None
                    session.quiz_result = None
                    session.chat_history = []
                    session = session_manager.update_session(session)
                    logger.info(f"Session {request.session_id[:8]}... reset to initial state (no remaining logs)")

                if logs and session and preserved_selected_questions:
                    session.selected_questions = preserved_selected_questions
                    if session.step == SessionStep.QUIZ:
                        if session.current_q_index < len(preserved_selected_questions):
                            session.current_question = preserved_selected_questions[session.current_q_index]
                        else:
                            session.current_question = None
                    session = session_manager.update_session(session)

                main_agent.remove_session(request.session_id)
                logger.info(
                    f"Session {request.session_id[:8]}... rolled back to before turn {request.turn_number} "
                    f"(all_logs={len(all_logs)}, jti_logs={len(logs)}, step={session.step.value}, "
                    f"current_question={'yes' if session.current_question else 'no'})"
                )
            else:
                logger.warning(f"Failed to delete logs from turn {request.turn_number}")

        # ========== QUIZ 狀態：後端完全接管 ==========
        quiz_result = await handle_quiz_message(session, request)
        if quiz_result:
            return quiz_result

        # ========== 非 QUIZ 狀態 ==========
        should_start_quiz = is_quiz_start_intent(request.message)
        logger.info(f"[DEBUG] 測驗判斷: should_start={should_start_quiz}")

        if should_start_quiz and session.step.value in ("DONE", "WELCOME"):
            if session.step.value == "DONE":
                session.step = SessionStep.WELCOME
                session_manager.update_session(session)
            if request.turn_number:
                conversation_logger.delete_turns_from(request.session_id, request.turn_number)
            quiz_response = await execute_quiz_start(request.session_id, user_message=request.message)
            return attach_tts_message_id(quiz_response, session.language, _get_tts_manager())

        # 一般對話：走 LLM
        result = await main_agent.chat(
            session_id=request.session_id,
            user_message=request.message,
        )
        logger.info(f"[AI回應] 一般對話 | {result['message'][:80]}...")

        if request.turn_number:
            conversation_logger.delete_turns_from(request.session_id, request.turn_number)

        log_result = conversation_logger.log_conversation(
            session_id=request.session_id,
            user_message=request.message,
            agent_response=result["message"],
            tool_calls=result.get("tool_calls", []),
            session_state=build_session_state(session),
            mode="jti",
            citations=result.get("citations"),
        )
        final_turn_number = log_result[1] if log_result else None

        response_payload = ChatResponse(**result, turn_number=final_turn_number)
        return attach_tts_message_id(response_payload, session.language, _get_tts_manager())

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Chat failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@compat_history_router.get(
    "/history",
    response_model=Union[ConversationsBySessionResponse, ConversationsGroupedResponse],
    response_model_exclude_none=True,
)
@admin_history_router.get(
    "",
    response_model=Union[ConversationsBySessionResponse, ConversationsGroupedResponse],
    response_model_exclude_none=True,
)
async def get_conversations(
    session_id: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
):
    """取得對話歷史"""
    mode = "jti"
    try:
        conversation_logger = _get_conversation_logger()
        if session_id:
            conversations = conversation_logger.get_session_logs(session_id)
            conversations = [c for c in conversations if c.get("mode") == mode]
            logger.info(f"Retrieved {len(conversations)} conversations for session {session_id}")
            return {"session_id": session_id, "mode": mode, "conversations": conversations, "total": len(conversations)}
        else:
            query = build_date_query(mode, date_from, date_to)
            session_ids, total_sessions = conversation_logger.get_paginated_session_ids(
                query=query, page=1, page_size=100000
            )
            all_conversations = conversation_logger.get_logs_for_sessions(session_ids)
            session_list = group_conversations_by_session(all_conversations)
            logger.info(f"Retrieved {len(all_conversations)} conversations across {len(session_list)} sessions (total {total_sessions})")
            return {"mode": mode, "sessions": session_list, "total_conversations": len(all_conversations), "total_sessions": total_sessions}

    except Exception as e:
        logger.error(f"Failed to get conversations: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@compat_history_router.delete("/history", response_model=DeleteConversationResponse)
@admin_history_router.delete("", response_model=DeleteConversationResponse)
async def delete_conversations(request: DeleteConversationRequest):
    """批量刪除對話紀錄"""
    session_manager = _get_session_manager()
    conversation_logger = _get_conversation_logger()
    total_logs = 0
    deleted_count = 0
    for sid in request.session_ids:
        total_logs += conversation_logger.delete_session_logs(sid)
        if session_manager.delete_session(sid):
            deleted_count += 1
        main_agent.remove_session(sid)

    return {"ok": True, "deleted_count": deleted_count, "deleted_logs": total_logs}


@compat_history_router.get(
    "/history/export",
    response_model=ExportConversationsResponse,
    response_model_exclude_none=True,
)
@admin_history_router.get(
    "/export",
    response_model=ExportConversationsResponse,
    response_model_exclude_none=True,
)
async def export_conversations(
    session_ids: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
):
    """匯出對話歷史為 JSON 格式"""
    mode = "jti"
    try:
        conversation_logger = _get_conversation_logger()
        if session_ids:
            sessions, total_conversations = export_sessions_by_ids(conversation_logger, session_ids, mode)
            return {"exported_at": datetime.now(_TZ_TAIPEI).isoformat(), "mode": mode, "sessions": sessions, "total_conversations": total_conversations, "total_sessions": len(sessions)}

        if date_from or date_to:
            query = build_date_query(mode, date_from, date_to)
            sid_list, _ = conversation_logger.get_paginated_session_ids(query=query, page=1, page_size=100000)
            all_conversations = conversation_logger.get_logs_for_sessions(sid_list)
        else:
            all_conversations = conversation_logger.get_session_logs_by_mode(mode)
        session_list = group_conversations_by_session(all_conversations)
        return {"exported_at": datetime.now(_TZ_TAIPEI).isoformat(), "mode": mode, "sessions": session_list, "total_conversations": len(all_conversations), "total_sessions": len(session_list)}

    except Exception as e:
        logger.error(f"Failed to export conversations: {e}")
        raise HTTPException(status_code=500, detail=str(e))

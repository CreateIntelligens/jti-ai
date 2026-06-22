"""
JTI Chat API — session management, chat messages, and conversation history.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Union

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse

import app.deps as deps
from app.auth import require_app_access, require_history_access, verify_admin
from app.routers.tts_utils import wire_tts
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
from app.services.general.managed_chat import ManagedChatConfig, ManagedChatService
from app.services.jti.main_agent import main_agent
from app.services.jti.quiz_flow import JTI_QUIZ_CONFIG
from app.utils import (
    build_date_query,
    build_history_summary_response,
    count_session_conversations,
    export_sessions_by_ids,
    filter_conversations_by_session_language,
    filter_export_sessions_by_language,
    filter_session_ids_by_language,
    group_conversations_by_session,
    normalize_history_pagination,
    simplified_conversation_sessions,
)

_TZ_TAIPEI = timezone(timedelta(hours=8))

_OPENING_MESSAGE: dict[str, str] = {
    "zh": "Hello，我是今天的活動大使Lady X，對我說「測驗」即可做「尋找命定前蓋」小遊戲，或想知道關於Ploom X加熱菸更多資訊，都歡迎和我聊聊，很樂意為您解答！",
    "en": "Hi! I'm Lady X. Got any questions, or want to take a quiz?",
}

logger = logging.getLogger(__name__)

runtime_router = APIRouter(prefix="/api/jti", tags=["JTI Chat"], dependencies=[Depends(require_app_access("jti"))])
# 讀取/匯出對話歷史：放寬到已登入使用者（user 只能看自己綁定的 app）。
compat_history_router = APIRouter(
    prefix="/api/jti",
    tags=["JTI Conversations"],
    include_in_schema=False,
    dependencies=[Depends(require_history_access("jti"))],
)
admin_history_router = APIRouter(
    prefix="/api/jti-admin/conversations",
    tags=["JTI Conversations"],
    dependencies=[Depends(require_history_access("jti"))],
)
# 刪除對話歷史：維持 admin only。
compat_history_admin_router = APIRouter(
    prefix="/api/jti",
    tags=["JTI Conversations"],
    include_in_schema=False,
    dependencies=[Depends(verify_admin)],
)
admin_history_admin_router = APIRouter(
    prefix="/api/jti-admin/conversations",
    tags=["JTI Conversations"],
    dependencies=[Depends(verify_admin)],
)
router = runtime_router


def _get_session_manager():
    return deps.get_jti_session_manager()


def _get_conversation_logger():
    return deps.get_jti_conversation_logger()


_get_tts_manager = wire_tts(runtime_router, "jti")

chat_service = ManagedChatService(
    ManagedChatConfig(
        app="jti",
        opening_messages=_OPENING_MESSAGE,
        session_manager_getter=_get_session_manager,
        conversation_logger_getter=_get_conversation_logger,
        tts_manager_getter=_get_tts_manager,
        agent=main_agent,
        quiz=JTI_QUIZ_CONFIG,
    )
)


# === Endpoints ===


@runtime_router.post("/chat/start", response_model=CreateSessionResponse)
async def create_session(request: CreateSessionRequest):
    """建立新的 JTI 對話 Session"""
    try:
        return await chat_service.create_session(request)
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
        return await chat_service.send_message(request)
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
    page: int = 1,
    page_size: int = 20,
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
            page, page_size = normalize_history_pagination(page, page_size)
            query = build_date_query(mode, date_from, date_to)
            session_ids, total_sessions = conversation_logger.get_paginated_session_ids(
                query=query, page=page, page_size=page_size
            )
            session_list = conversation_logger.get_session_summaries(session_ids, query=query)
            logger.info(
                "Retrieved %d JTI session summaries on page %d/%d (total %d)",
                len(session_list),
                page,
                page_size,
                total_sessions,
            )
            return build_history_summary_response(
                mode=mode,
                sessions=session_list,
                total_sessions=total_sessions,
                page=page,
                page_size=page_size,
            )

    except Exception as e:
        logger.error(f"Failed to get conversations: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@compat_history_admin_router.delete("/history", response_model=DeleteConversationResponse)
@admin_history_admin_router.delete("", response_model=DeleteConversationResponse)
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
    simple: bool = False,
    language: Optional[str] = None,
):
    """匯出對話歷史為 JSON 格式"""
    mode = "jti"
    try:
        conversation_logger = _get_conversation_logger()
        session_manager = _get_session_manager()

        if session_ids:
            sessions, total_conversations = export_sessions_by_ids(conversation_logger, session_ids, mode)
            if language:
                sessions = filter_export_sessions_by_language(sessions, session_manager, language)
                total_conversations = count_session_conversations(sessions)
            result = {
                "exported_at": datetime.now(_TZ_TAIPEI).isoformat(),
                "mode": mode,
                "sessions": sessions,
                "total_conversations": total_conversations,
                "total_sessions": len(sessions),
            }
        else:
            if date_from or date_to:
                query = build_date_query(mode, date_from, date_to)
                sid_list, _ = conversation_logger.get_paginated_session_ids(query=query, page=1, page_size=100000)
                sid_list = filter_session_ids_by_language(sid_list, session_manager, language)
                all_conversations = conversation_logger.get_logs_for_sessions(sid_list)
            else:
                all_conversations = conversation_logger.get_session_logs_by_mode(mode)
                all_conversations = filter_conversations_by_session_language(
                    all_conversations,
                    session_manager,
                    language,
                )

            session_list = group_conversations_by_session(all_conversations)
            result = {
                "exported_at": datetime.now(_TZ_TAIPEI).isoformat(),
                "mode": mode,
                "sessions": session_list,
                "total_conversations": len(all_conversations),
                "total_sessions": len(session_list),
            }

        if simple:
            return JSONResponse(content=simplified_conversation_sessions(result.get("sessions", [])))

        return result
    except Exception as e:
        logger.error(f"Failed to export conversations: {e}")
        raise HTTPException(status_code=500, detail=str(e))

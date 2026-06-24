"""
HCIoT chat API - session management, messages, and conversation history.
"""

import logging
from datetime import datetime, timedelta, timezone
from time import perf_counter
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse

import app.deps as deps
from app.auth import require_app_access, require_history_access, verify_admin
from app.routers.tts_utils import attach_tts_message_id, wire_tts
from app.services.gemini_service import run_sync
from app.schemas.chat import (
    ChatRequest,
    ChatResponse,
    CreateSessionRequest,
    CreateSessionResponse,
    DeleteConversationRequest,
    DeleteConversationResponse,
    ExportConversationsResponse,
)
from app.services.hciot.main_agent import main_agent
from app.services.hciot.runtime_settings import get_available_tts_characters
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
    "zh": "您好，歡迎來到元復醫院。\n我是元復醫院的智慧AI小元。\n如果您想了解門診資訊、衛教或醫療相關問題，都可以詢問我。\n很高興為您服務。",
    "en": "Hello, welcome to Yuanfu Hospital. I'm Xiao Yuan, the smart AI assistant. Feel free to ask me about outpatient information, health education, or any medical questions. Happy to help!",
}

logger = logging.getLogger(__name__)


runtime_router = APIRouter(prefix="/api/hciot", tags=["HCIoT Chat"], dependencies=[Depends(require_app_access("hciot"))])
# 讀取/匯出對話歷史：放寬到已登入使用者（user 只能看自己綁定的 app）。
compat_history_router = APIRouter(
    prefix="/api/hciot",
    tags=["HCIoT Conversations"],
    include_in_schema=False,
    dependencies=[Depends(require_history_access("hciot"))],
)
admin_history_router = APIRouter(
    prefix="/api/hciot-admin/conversations",
    tags=["HCIoT Conversations"],
    dependencies=[Depends(require_history_access("hciot"))],
)
# 刪除對話歷史：維持 admin only。
compat_history_admin_router = APIRouter(
    prefix="/api/hciot",
    tags=["HCIoT Conversations"],
    include_in_schema=False,
    dependencies=[Depends(verify_admin)],
)
admin_history_admin_router = APIRouter(
    prefix="/api/hciot-admin/conversations",
    tags=["HCIoT Conversations"],
    dependencies=[Depends(verify_admin)],
)
router = runtime_router


def _get_session_manager():
    return deps.get_hciot_session_manager()


def _get_conversation_logger():
    return deps.get_hciot_conversation_logger()


async def _run_db_call(label: str, fn, *args, **kwargs):
    """Run synchronous DB work off the event loop and log its duration."""
    started = perf_counter()
    try:
        return await run_sync(fn, *args, **kwargs)
    finally:
        logger.debug(
            "[HCIoT DB] %s duration_ms=%.1f", label, (perf_counter() - started) * 1000
        )


@runtime_router.get("/tts/characters")
async def get_tts_characters():
    """Return available TTS character voices."""
    return {"characters": get_available_tts_characters()}


_get_tts_manager = wire_tts(runtime_router, "hciot")


@runtime_router.post("/chat/start", response_model=CreateSessionResponse)
async def create_session(request: CreateSessionRequest):
    try:
        session_manager = _get_session_manager()
        if request.previous_session_id:
            main_agent.remove_session(request.previous_session_id)
            logger.info(
                "Cleaned up previous HCIoT session: %s...",
                request.previous_session_id[:8],
            )

        session = await _run_db_call(
            "session.create", session_manager.create_session, request.language
        )
        # Keep /chat/start lazy; the first real message flushes app_mode with the session.
        session.metadata["app_mode"] = "hciot"
        logger.info(
            "Created new HCIoT session (pending): %s (language=%s)",
            session.session_id,
            request.language,
        )
        opening = _OPENING_MESSAGE.get(request.language, _OPENING_MESSAGE["zh"])
        return CreateSessionResponse(session_id=session.session_id, opening_message=opening)
    except Exception as e:
        logger.error("Failed to create HCIoT session: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@runtime_router.post("/chat/message", response_model=ChatResponse)
async def chat(request: ChatRequest):
    try:
        session_manager = _get_session_manager()
        conversation_logger = _get_conversation_logger()
        session = await _run_db_call(
            "session.get.initial", session_manager.get_session, request.session_id
        )
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        logger.info(
            "[用戶訊息] Session: %s... | 訊息: '%s'",
            request.session_id[:8],
            request.message,
        )

        if request.turn_number is not None:
            await _run_db_call(
                "conversation.delete_turns_from",
                conversation_logger.delete_turns_from,
                request.session_id,
                request.turn_number,
            )
            logs = [
                log
                for log in await _run_db_call(
                    "conversation.get_session_logs.rollback",
                    conversation_logger.get_session_logs,
                    request.session_id,
                )
                if log.get("mode") == "hciot"
            ]
            if logs:
                session = await _run_db_call(
                    "session.rebuild_from_logs",
                    session_manager.rebuild_session_from_logs,
                    request.session_id,
                    logs,
                )
                if not session:
                    raise HTTPException(
                        status_code=500,
                        detail="Failed to rebuild session from logs",
                    )
            else:
                session.chat_history = []
                await _run_db_call(
                    "session.update.rollback_empty", session_manager.update_session, session
                )
            main_agent.remove_session(request.session_id)

        result = await main_agent.chat(session_id=request.session_id, user_message=request.message)
        answer = result["message"]
        logger.info("[AI回應] HCIoT | %s...", answer[:80])

        updated_session = await _run_db_call(
            "session.get.after_agent", session_manager.get_session, request.session_id
        )
        language = updated_session.language if updated_session else "zh"
        log_result = await _run_db_call(
            "conversation.log",
            conversation_logger.log_conversation,
            session_id=request.session_id,
            user_message=request.message,
            agent_response=answer,
            tool_calls=result.get("tool_calls", []),
            mode="hciot",
            session_state={"language": language},
            citations=result.get("citations"),
            image_id=result.get("image_id"),
        )
        _, final_turn_number = log_result or (None, None)

        response = ChatResponse(**result, turn_number=final_turn_number)
        return attach_tts_message_id(
            response,
            language,
            _get_tts_manager(),
            character=request.tts_character.strip() if request.tts_character else None,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("HCIoT chat failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@compat_history_router.get("/history")
@admin_history_router.get("")
async def get_conversations(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    session_id: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
):
    mode = "hciot"
    try:
        conversation_logger = _get_conversation_logger()
        # Single-session detail request (used by ConversationHistoryModal resume)
        if session_id:
            logs = await _run_db_call(
                "conversation.get_session_logs.detail",
                conversation_logger.get_session_logs,
                session_id,
            )
            conversations = [c for c in logs if c.get("mode") == mode]
            logger.info(
                "Retrieved %d HCIoT conversations for session %s...",
                len(conversations),
                session_id[:8],
            )
            return {"mode": mode, "conversations": conversations}

        page, page_size = normalize_history_pagination(page, page_size)
        query = build_date_query(mode, date_from, date_to)
        session_ids, total_sessions = await _run_db_call(
            "conversation.get_paginated_session_ids",
            conversation_logger.get_paginated_session_ids,
            query=query,
            page=page,
            page_size=page_size,
        )
        session_list = await _run_db_call(
            "conversation.get_session_summaries",
            conversation_logger.get_session_summaries,
            session_ids,
            query=query,
        )
        logger.info(
            "Retrieved %d HCIoT session summaries on page %d/%d (total %d)",
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
        logger.error("Failed to get HCIoT conversations: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@compat_history_admin_router.delete("/history", response_model=DeleteConversationResponse)
@admin_history_admin_router.delete("", response_model=DeleteConversationResponse)
async def delete_conversations(request: DeleteConversationRequest):
    session_manager = _get_session_manager()
    conversation_logger = _get_conversation_logger()
    total_logs = 0
    deleted_count = 0
    for sid in request.session_ids:
        total_logs += await _run_db_call(
            "conversation.delete_session_logs", conversation_logger.delete_session_logs, sid
        )
        if await _run_db_call("session.delete", session_manager.delete_session, sid):
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
    mode = "hciot"
    try:
        conversation_logger = _get_conversation_logger()
        session_manager = _get_session_manager()

        if session_ids:
            sessions, total_conversations = await _run_db_call(
                "conversation.export_by_ids",
                export_sessions_by_ids,
                conversation_logger,
                session_ids,
                mode,
            )
            if language:
                sessions = await _run_db_call(
                    "session.filter_export_by_language",
                    filter_export_sessions_by_language,
                    sessions,
                    session_manager,
                    language,
                )
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
                sid_list, _ = await _run_db_call(
                    "conversation.get_paginated_session_ids.export",
                    conversation_logger.get_paginated_session_ids,
                    query=query,
                    page=1,
                    page_size=100000,
                )
                sid_list = await _run_db_call(
                    "session.filter_ids_by_language",
                    filter_session_ids_by_language,
                    sid_list,
                    session_manager,
                    language,
                )
                all_conversations = await _run_db_call(
                    "conversation.get_logs_for_sessions",
                    conversation_logger.get_logs_for_sessions,
                    sid_list,
                )
            else:
                all_conversations = await _run_db_call(
                    "conversation.get_session_logs_by_mode",
                    conversation_logger.get_session_logs_by_mode,
                    mode,
                )
                all_conversations = await _run_db_call(
                    "session.filter_conversations_by_language",
                    filter_conversations_by_session_language,
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
            return JSONResponse(
                content=simplified_conversation_sessions(result.get("sessions", []))
            )

        return result
    except Exception as e:
        logger.error("Failed to export HCIoT conversations: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

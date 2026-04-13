"""
HCIoT chat API - session management, messages, and conversation history.
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

_TZ_TAIPEI = timezone(timedelta(hours=8))

from fastapi import APIRouter, Depends, HTTPException

from app.auth import verify_admin, verify_auth
from app.routers.tts_utils import attach_tts_message_id, register_tts_endpoints
from app.schemas.chat import (
    ChatRequest,
    ChatResponse,
    ConversationsGroupedResponse,
    CreateSessionRequest,
    CreateSessionResponse,
    DeleteConversationRequest,
    DeleteConversationResponse,
    ExportConversationsResponse,
)
from app.services.hciot.main_agent import main_agent
from app.services.hciot.runtime_settings import get_available_tts_characters
from app.services.jti.tts_text import to_tts_text
from app.services.session.session_manager_factory import get_hciot_conversation_logger, get_hciot_session_manager
from app.services.tts_jobs import hciot_tts_job_manager as _tts_manager
from app.utils import build_date_query, group_conversations_by_session


_OPENING_MESSAGE: dict[str, str] = {
    "zh": "您好，歡迎來到元復醫院。\n我是元復醫院的智慧AI小元。\n如果您想了解門診資訊、衛教或醫療相關問題，都可以詢問我。\n很高興為您服務。",
    "en": "Hello, welcome to Yuanfu Hospital. I'm Xiao Yuan, the smart AI assistant. Feel free to ask me about outpatient information, health education, or any medical questions. Happy to help!",
}

session_manager = get_hciot_session_manager()
conversation_logger = get_hciot_conversation_logger()
logger = logging.getLogger(__name__)


runtime_router = APIRouter(prefix="/api/hciot", tags=["HCIoT Chat"])
compat_history_router = APIRouter(
    prefix="/api/hciot",
    tags=["HCIoT Conversations"],
    include_in_schema=False,
)
admin_history_router = APIRouter(
    prefix="/api/hciot-admin/conversations",
    tags=["HCIoT Conversations"],
)
router = runtime_router

@runtime_router.get("/tts/characters")
async def get_tts_characters(auth: dict = Depends(verify_auth)):
    """Return available TTS character voices."""
    return {"characters": get_available_tts_characters()}


register_tts_endpoints(runtime_router, _tts_manager)


@runtime_router.post("/chat/start", response_model=CreateSessionResponse)
async def create_session(request: CreateSessionRequest, auth: dict = Depends(verify_auth)):
    try:
        if request.previous_session_id:
            main_agent.remove_session(request.previous_session_id)
            logger.info("Cleaned up previous HCIoT session: %s...", request.previous_session_id[:8])

        session = session_manager.create_session(language=request.language)
        session.metadata["app_mode"] = "hciot"
        session_manager.update_session(session)
        opening = _OPENING_MESSAGE.get(request.language, _OPENING_MESSAGE["zh"])
        return CreateSessionResponse(session_id=session.session_id, opening_message=opening)
    except Exception as e:
        logger.error("Failed to create HCIoT session: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@runtime_router.post("/chat/message", response_model=ChatResponse)
async def chat(request: ChatRequest, auth: dict = Depends(verify_auth)):
    try:
        session = session_manager.get_session(request.session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        if request.turn_number is not None:
            deleted_count = conversation_logger.delete_turns_from(request.session_id, request.turn_number)
            if deleted_count > 0:
                all_logs = conversation_logger.get_session_logs(request.session_id)
                logs = [l for l in all_logs if l.get("mode") == "hciot"]
                if logs:
                    session = session_manager.rebuild_session_from_logs(request.session_id, logs)
                    if not session:
                        raise HTTPException(status_code=500, detail="Failed to rebuild session from logs")
                else:
                    session.chat_history = []
                    session_manager.update_session(session)
                main_agent.remove_session(request.session_id)

        result = await main_agent.chat(session_id=request.session_id, user_message=request.message)

        updated_session = session_manager.get_session(request.session_id)
        language = updated_session.language if updated_session else "zh"
        log_result = conversation_logger.log_conversation(
            session_id=request.session_id,
            user_message=request.message,
            agent_response=result["message"],
            tool_calls=result.get("tool_calls", []),
            mode="hciot",
            citations=result.get("citations"),
            image_id=result.get("image_id"),
        )
        final_turn_number = log_result[1] if log_result else None
        result["tts_text"] = to_tts_text(result["message"], language)
        response = ChatResponse(**result, turn_number=final_turn_number)
        tts_character = request.tts_character.strip() if request.tts_character else None
        return attach_tts_message_id(response, language, _tts_manager, character=tts_character)
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
    auth: dict = Depends(verify_admin),
):
    mode = "hciot"
    try:
        # Single-session detail request (used by ConversationHistoryModal resume)
        if session_id:
            conversations = [c for c in conversation_logger.get_session_logs(session_id) if c.get("mode") == mode]
            return {"mode": mode, "conversations": conversations}

        query = build_date_query(mode, date_from, date_to)
        session_ids, total_sessions = conversation_logger.get_paginated_session_ids(query=query, page=1, page_size=100000)
        all_conversations = conversation_logger.get_logs_for_sessions(session_ids)
        session_list = group_conversations_by_session(all_conversations)
        return {"mode": mode, "sessions": session_list, "total_conversations": len(all_conversations), "total_sessions": total_sessions}
    except Exception as e:
        logger.error("Failed to get HCIoT conversations: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@compat_history_router.delete("/history", response_model=DeleteConversationResponse)
@admin_history_router.delete("", response_model=DeleteConversationResponse)
async def delete_conversations(request: DeleteConversationRequest, auth: dict = Depends(verify_admin)):
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
    auth: dict = Depends(verify_admin),
):
    mode = "hciot"
    try:
        if session_ids:
            session_id_list = [sid.strip() for sid in session_ids.split(",") if sid.strip()]
            sessions = []
            total_conversations = 0
            for session_id in session_id_list:
                conversations = conversation_logger.get_session_logs(session_id)
                conversations = [c for c in conversations if c.get("mode") == mode]
                if conversations:
                    sessions.append({
                        "session_id": session_id,
                        "conversations": conversations,
                        "first_message_time": conversations[0].get("timestamp"),
                        "total": len(conversations),
                    })
                    total_conversations += len(conversations)
            sessions.sort(key=lambda x: x["first_message_time"] or "", reverse=True)
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
        logger.error("Failed to export HCIoT conversations: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

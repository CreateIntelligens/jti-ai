"""
HCIoT chat API - session management, messages, and conversation history.
"""

from datetime import datetime
import logging
from typing import Optional, Union

from fastapi import APIRouter, Depends, HTTPException

from app.auth import verify_admin, verify_auth
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
from app.services.hciot.main_agent import main_agent
from app.services.session.session_manager_factory import get_hciot_conversation_logger, get_hciot_session_manager
from app.utils import group_conversations_by_session

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
                logs = conversation_logger.get_session_logs(request.session_id)
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
        log_result = conversation_logger.log_conversation(
            session_id=request.session_id,
            user_message=request.message,
            agent_response=result["message"],
            tool_calls=result.get("tool_calls", []),
            session_state={
                "step": updated_session.step.value if updated_session else "WELCOME",
                "language": updated_session.language if updated_session else "zh",
            },
            mode="hciot",
            citations=result.get("citations"),
            image_id=result.get("image_id"),
        )
        final_turn_number = log_result[1] if log_result else None
        return ChatResponse(**result, turn_number=final_turn_number)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("HCIoT chat failed: %s", e, exc_info=True)
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
    auth: dict = Depends(verify_admin),
):
    mode = "hciot"
    try:
        if session_id:
            conversations = conversation_logger.get_session_logs(session_id)
            conversations = [c for c in conversations if c.get("mode") == mode]
            return {"session_id": session_id, "mode": mode, "conversations": conversations, "total": len(conversations)}

        query: dict = {"mode": mode}
        if date_from or date_to:
            ts_filter: dict = {}
            if date_from:
                ts_filter["$gte"] = datetime.strptime(date_from, "%Y-%m-%d")
            if date_to:
                ts_filter["$lte"] = datetime.strptime(date_to + " 23:59:59", "%Y-%m-%d %H:%M:%S")
            query["timestamp"] = ts_filter

        session_ids, total_sessions = conversation_logger.get_paginated_session_ids(
            query=query, page=1, page_size=100000
        )
        all_conversations = conversation_logger.get_logs_for_sessions(session_ids)
        session_list = group_conversations_by_session(all_conversations)
        return {
            "mode": mode,
            "sessions": session_list,
            "total_conversations": len(all_conversations),
            "total_sessions": total_sessions,
        }
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
async def export_conversations(session_ids: Optional[str] = None, auth: dict = Depends(verify_admin)):
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
                    sessions.append(
                        {
                            "session_id": session_id,
                            "conversations": conversations,
                            "first_message_time": conversations[0].get("timestamp"),
                            "total": len(conversations),
                        }
                    )
                    total_conversations += len(conversations)
            sessions.sort(key=lambda x: x["first_message_time"] or "", reverse=True)
            return {
                "exported_at": datetime.utcnow().isoformat(),
                "mode": mode,
                "sessions": sessions,
                "total_conversations": total_conversations,
                "total_sessions": len(sessions),
            }

        all_conversations = conversation_logger.get_session_logs_by_mode(mode)
        session_list = group_conversations_by_session(all_conversations)
        return {
            "exported_at": datetime.utcnow().isoformat(),
            "mode": mode,
            "sessions": session_list,
            "total_conversations": len(all_conversations),
            "total_sessions": len(session_list),
        }
    except Exception as e:
        logger.error("Failed to export HCIoT conversations: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

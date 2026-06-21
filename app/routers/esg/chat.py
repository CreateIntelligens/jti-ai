"""ESG chat, quiz-aware messaging, and conversation history APIs."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse

import app.deps as deps
from app.auth import require_app_access, require_history_access, verify_admin
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
from app.services.esg.agent_prompts import WELCOME_TEXT
from app.services.esg.main_agent import main_agent
from app.services.esg.quiz_flow import ESG_QUIZ_CONFIG
from app.services.general.managed_chat import ManagedChatConfig, ManagedChatService
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
_MODE = "esg"
_OPENING_MESSAGES = {
    language: f"{block['title']}\n{block['description']}"
    for language, block in WELCOME_TEXT.items()
}

logger = logging.getLogger(__name__)

runtime_router = APIRouter(
    prefix="/api/esg",
    tags=["ESG Chat"],
    dependencies=[Depends(require_app_access(_MODE))],
)
compat_history_router = APIRouter(
    prefix="/api/esg",
    tags=["ESG Conversations"],
    include_in_schema=False,
    dependencies=[Depends(require_history_access(_MODE))],
)
admin_history_router = APIRouter(
    prefix="/api/esg-admin/conversations",
    tags=["ESG Conversations"],
    dependencies=[Depends(require_history_access(_MODE))],
)
compat_history_admin_router = APIRouter(
    prefix="/api/esg",
    tags=["ESG Conversations"],
    include_in_schema=False,
    dependencies=[Depends(verify_admin)],
)
admin_history_admin_router = APIRouter(
    prefix="/api/esg-admin/conversations",
    tags=["ESG Conversations"],
    dependencies=[Depends(verify_admin)],
)
router = runtime_router


def _get_session_manager():
    return deps.get_esg_session_manager()


def _get_conversation_logger():
    return deps.get_esg_conversation_logger()


chat_service = ManagedChatService(
    ManagedChatConfig(
        app=_MODE,
        opening_messages=_OPENING_MESSAGES,
        session_manager_getter=_get_session_manager,
        conversation_logger_getter=_get_conversation_logger,
        agent=main_agent,
        quiz=ESG_QUIZ_CONFIG,
    )
)


@runtime_router.post("/chat/start", response_model=CreateSessionResponse)
async def create_session(request: CreateSessionRequest):
    try:
        return await chat_service.create_session(request)
    except Exception as exc:
        logger.error("Failed to create ESG session: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@runtime_router.post("/chat/message", response_model=ChatResponse)
async def chat(request: ChatRequest):
    try:
        return await chat_service.send_message(request)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("ESG chat failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@compat_history_router.get(
    "/history",
    response_model=ConversationsBySessionResponse | ConversationsGroupedResponse,
    response_model_exclude_none=True,
)
@admin_history_router.get(
    "",
    response_model=ConversationsBySessionResponse | ConversationsGroupedResponse,
    response_model_exclude_none=True,
)
async def get_conversations(
    session_id: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    page: int = 1,
    page_size: int = 20,
):
    try:
        conversation_logger = _get_conversation_logger()
        if session_id:
            conversations = [
                conversation
                for conversation in conversation_logger.get_session_logs(session_id)
                if conversation.get("mode") == _MODE
            ]
            return {
                "session_id": session_id,
                "mode": _MODE,
                "conversations": conversations,
                "total": len(conversations),
            }

        page, page_size = normalize_history_pagination(page, page_size)
        query = build_date_query(_MODE, date_from, date_to)
        session_ids, total_sessions = conversation_logger.get_paginated_session_ids(
            query=query,
            page=page,
            page_size=page_size,
        )
        sessions = conversation_logger.get_session_summaries(session_ids, query=query)
        return build_history_summary_response(
            mode=_MODE,
            sessions=sessions,
            total_sessions=total_sessions,
            page=page,
            page_size=page_size,
        )
    except Exception as exc:
        logger.error("Failed to get ESG conversations: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@compat_history_admin_router.delete(
    "/history",
    response_model=DeleteConversationResponse,
)
@admin_history_admin_router.delete("", response_model=DeleteConversationResponse)
async def delete_conversations(request: DeleteConversationRequest):
    session_manager = _get_session_manager()
    conversation_logger = _get_conversation_logger()
    deleted_logs = 0
    deleted_sessions = 0

    for session_id in request.session_ids:
        deleted_logs += conversation_logger.delete_session_logs(session_id)
        if session_manager.delete_session(session_id):
            deleted_sessions += 1
        main_agent.remove_session(session_id)

    return {
        "ok": True,
        "deleted_count": deleted_sessions,
        "deleted_logs": deleted_logs,
    }


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
    session_ids: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    simple: bool = False,
    language: str | None = None,
):
    try:
        conversation_logger = _get_conversation_logger()
        session_manager = _get_session_manager()

        if session_ids:
            sessions, total_conversations = export_sessions_by_ids(
                conversation_logger,
                session_ids,
                _MODE,
            )
            if language:
                sessions = filter_export_sessions_by_language(
                    sessions,
                    session_manager,
                    language,
                )
                total_conversations = count_session_conversations(sessions)
        else:
            if date_from or date_to:
                query = build_date_query(_MODE, date_from, date_to)
                ids, _ = conversation_logger.get_paginated_session_ids(
                    query=query,
                    page=1,
                    page_size=100000,
                )
                ids = filter_session_ids_by_language(ids, session_manager, language)
                conversations = conversation_logger.get_logs_for_sessions(ids)
            else:
                conversations = conversation_logger.get_session_logs_by_mode(_MODE)
                conversations = filter_conversations_by_session_language(
                    conversations,
                    session_manager,
                    language,
                )

            sessions = group_conversations_by_session(conversations)
            total_conversations = len(conversations)

        result = {
            "exported_at": datetime.now(_TZ_TAIPEI).isoformat(),
            "mode": _MODE,
            "sessions": sessions,
            "total_conversations": total_conversations,
            "total_sessions": len(sessions),
        }
        if simple:
            return JSONResponse(
                content=simplified_conversation_sessions(result["sessions"])
            )
        return result
    except Exception as exc:
        logger.error("Failed to export ESG conversations: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))

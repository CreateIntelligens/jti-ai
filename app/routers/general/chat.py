"""
General Chat API Endpoints

Thin router layer: HTTP routing + conversation logging.
Core chat logic delegated to GeneralAgent (BaseAgent subclass).
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from app.auth import extract_user_gemini_api_key, verify_auth
from app.routers.general.stores import (
    hash_user_gemini_api_key,
    resolve_store_config,
)
from app.schemas.chat import (
    DeleteConversationRequest,
    DeleteConversationResponse,
    ExportGeneralConversationsResponse,
    GeneralConversationsBySessionResponse,
    GeneralConversationsResponse,
)
from app.models_config import DEFAULT_RAG_MODEL
from app.utils import build_date_query, export_sessions_by_ids, group_conversations_by_session, group_conversations_as_summary
import app.deps as deps
from app.services.general.agent_prompts import (
    DEFAULT_MAX_RESPONSE_CHARS,
    DEFAULT_RESPONSE_RULE_SECTIONS,
    build_system_instruction,
)
from app.services.general.main_agent import main_agent

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chat", tags=["General Chat"])


class ChatStartRequest(BaseModel):
    store_name: Optional[str] = None
    model: str = DEFAULT_RAG_MODEL
    previous_session_id: Optional[str] = None


class ChatMessageRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    turn_number: Optional[int] = None
    model: Optional[str] = None


def _get_conversation_logger():
    # General chat shares the JTI conversation log collection — the logger
    # itself accepts a `mode` per-call so logs from different chat surfaces
    # coexist in the same store. There is no separate general logger.
    return deps.get_jti_conversation_logger()


def _get_session_manager():
    return deps.get_general_chat_session_manager()


def _resolve_request_store(
    req: ChatStartRequest,
    auth: dict,
    owner_key_hash: str | None = None,
) -> str:
    requested = auth.get("store_name") if auth.get("role") == "user" else req.store_name
    config = resolve_store_config(requested, owner_key_hash)
    if config is None:
        raise HTTPException(status_code=404, detail="Knowledge store not found")
    return config.name


def _resolve_active_prompt(store_name: str, auth: dict):
    """Pick the prompt that should drive this chat session."""
    if not deps.prompt_manager:
        return None

    if auth.get("role") == "user" and auth.get("prompt_index") is not None:
        prompts = deps.prompt_manager.list_prompts(store_name)
        prompt_index = auth["prompt_index"]
        if 0 <= prompt_index < len(prompts):
            return prompts[prompt_index]

    return deps.prompt_manager.get_active_prompt(store_name)


def _compose_prompt_system_instruction(prompt, language: str = "zh") -> str:
    """Compose a system instruction from a Prompt's persona + optional sections."""
    sections_by_lang = prompt.response_rule_sections or {}
    sections = sections_by_lang.get(language) or sections_by_lang.get("zh")
    if not sections:
        sections = DEFAULT_RESPONSE_RULE_SECTIONS.get(
            language, DEFAULT_RESPONSE_RULE_SECTIONS["zh"]
        )
    max_chars = (
        prompt.max_response_chars
        if prompt.max_response_chars is not None
        else DEFAULT_MAX_RESPONSE_CHARS
    )
    return build_system_instruction(
        persona=prompt.content,
        language=language,
        response_rule_sections=sections,
        max_response_chars=max_chars,
    )


def _get_system_instruction(store_name: str, auth: dict) -> str | None:
    prompt = _resolve_active_prompt(store_name, auth)
    if prompt is None:
        return None
    return _compose_prompt_system_instruction(prompt)


# === Chat Endpoints ===

@router.post("/start")
def start_chat(req: ChatStartRequest, request: Request, auth: dict = Depends(verify_auth)):
    """Start a generic homepage chat session backed by local RAG."""
    if req.previous_session_id:
        main_agent.remove_session(req.previous_session_id)
        logger.info("Cleaned up previous general session: %s...", req.previous_session_id[:8])

    user_gemini_api_key = extract_user_gemini_api_key(request)
    store_name = _resolve_request_store(
        req,
        auth,
        hash_user_gemini_api_key(user_gemini_api_key),
    )
    system_instruction = _get_system_instruction(store_name, auth)

    # Resolve managed_app / managed_language for RAG source_type routing
    config = resolve_store_config(store_name, hash_user_gemini_api_key(user_gemini_api_key))
    managed_app = config.managed_app if config else None
    managed_language = config.managed_language if config else None

    session = main_agent.create_session(
        store_name=store_name,
        model=req.model,
        system_instruction=system_instruction,
        managed_app=managed_app,
        managed_language=managed_language,
    )
    logger.info(
        "Created new general session: %s (store=%s)",
        session.session_id,
        store_name,
    )

    return {
        "ok": True,
        "prompt_applied": system_instruction is not None,
        "session_id": session.session_id,
    }


@router.post("/message")
async def send_message(req: ChatMessageRequest, request: Request, auth: dict = Depends(verify_auth)):
    """Send a message to a generic homepage chat session."""
    user_gemini_api_key = extract_user_gemini_api_key(request)
    owner_key_hash = hash_user_gemini_api_key(user_gemini_api_key)

    session_manager = _get_session_manager()
    session = None
    if req.session_id and session_manager:
        session = session_manager.get_session(req.session_id)

    if session is None:
        start_req = ChatStartRequest(store_name=auth.get("store_name"))
        store_name = _resolve_request_store(start_req, auth, owner_key_hash)
        config = resolve_store_config(store_name, owner_key_hash)
        session = main_agent.create_session(
            store_name=store_name,
            model=start_req.model,
            system_instruction=_get_system_instruction(store_name, auth),
            managed_app=config.managed_app if config else None,
            managed_language=config.managed_language if config else None,
        )

    if req.turn_number is not None:
        keep_turns = max(req.turn_number - 1, 0)
        if session_manager:
            persisted = session_manager.get_session(session.session_id)
            if persisted:
                persisted.chat_history = persisted.chat_history[: keep_turns * 2]
                session_manager.update_session(persisted)
        main_agent.remove_session(session.session_id)
        try:
            _get_conversation_logger().delete_turns_from(session.session_id, req.turn_number)
        except Exception:
            logger.exception("Failed to truncate general conversation logs")

    logger.info(
        "[用戶訊息] Session: %s... | 訊息: '%s'",
        session.session_id[:8],
        req.message,
    )

    # Core chat: function-calling RAG via BaseAgent
    result = await main_agent.chat(
        session_id=session.session_id,
        user_message=req.message,
        model=req.model,
    )

    answer = result.get("message", "")
    citations = result.get("citations") or []
    logger.info("[AI回應] 一般對話 | %s...", answer[:80])

    log_result = _get_conversation_logger().log_conversation(
        session_id=session.session_id,
        user_message=req.message,
        agent_response=answer,
        tool_calls=result.get("tool_calls", []),
        session_state={"store": session.metadata.get("store_name", "")},
        mode="general",
        citations=citations,
    )
    turn_number = log_result[1] if log_result else None

    return {
        "answer": answer,
        "session_id": session.session_id,
        "turn_number": turn_number,
        "citations": citations,
    }


# === History Endpoints (unchanged) ===

@router.delete("/history", response_model=DeleteConversationResponse)
def delete_general_conversations(request: DeleteConversationRequest, auth: dict = Depends(verify_auth)):
    """批量刪除對話紀錄"""
    conversation_logger = _get_conversation_logger()
    session_manager = _get_session_manager()
    total_logs = 0
    deleted_count = 0
    for sid in request.session_ids:
        total_logs += conversation_logger.delete_session_logs(sid)
        if session_manager and session_manager.delete_session(sid):
            deleted_count += 1
        main_agent.remove_session(sid)

    return {
        "ok": True,
        "deleted_count": deleted_count,
        "deleted_logs": total_logs,
    }


@router.get(
    "/history",
    response_model=GeneralConversationsResponse,
    response_model_exclude_none=True,
)
def get_general_conversations(
    store_name: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    auth: dict = Depends(verify_auth),
):
    """取得 general chat 的對話歷史（session 列表）"""
    try:
        conversation_logger = _get_conversation_logger()
        if not store_name:
            raise HTTPException(status_code=400, detail="未指定知識庫")

        query = build_date_query(
            "general", date_from, date_to,
            extras={"session_snapshot.store": store_name},
        )

        session_ids, total_sessions = conversation_logger.get_paginated_session_ids(
            query=query,
            page=1,
            page_size=100000
        )

        all_conversations = conversation_logger.get_logs_for_sessions(session_ids)

        session_list = group_conversations_as_summary(all_conversations)

        return {
            "store_name": store_name,
            "mode": "general",
            "sessions": session_list,
            "total_conversations": len(all_conversations),
            "total_sessions": total_sessions
        }

    except Exception as e:
        logger.error("Failed to get general conversations: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/history/export",
    response_model=ExportGeneralConversationsResponse,
    response_model_exclude_none=True,
)
def export_general_conversations(
    store_name: Optional[str] = None,
    session_ids: Optional[str] = None,
    auth: dict = Depends(verify_auth),
):
    """匯出 general chat 的對話歷史為 JSON 格式"""
    try:
        conversation_logger = _get_conversation_logger()
        if not store_name:
            raise HTTPException(status_code=400, detail="未指定知識庫")

        if session_ids:
            sessions, total_conversations = export_sessions_by_ids(
                conversation_logger, session_ids, "general", store_filter=store_name,
            )
            return {
                "exported_at": datetime.now(timezone.utc).isoformat(),
                "store_name": store_name,
                "mode": "general",
                "sessions": sessions,
                "total_conversations": total_conversations,
                "total_sessions": len(sessions)
            }
        else:
            all_conversations = conversation_logger.get_session_logs_by_mode("general")

            store_conversations = [
                c for c in all_conversations
                if c.get("session_snapshot", {}).get("store") == store_name
            ]

            session_list = group_conversations_by_session(store_conversations)

            return {
                "exported_at": datetime.now(timezone.utc).isoformat(),
                "store_name": store_name,
                "mode": "general",
                "sessions": session_list,
                "total_conversations": len(store_conversations),
                "total_sessions": len(session_list)
            }

    except Exception as e:
        logger.error("Failed to export general conversations: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/history/{session_id}",
    response_model=GeneralConversationsBySessionResponse,
    response_model_exclude_none=True,
)
def get_general_conversation_detail(
    session_id: str,
    auth: dict = Depends(verify_auth),
):
    """取得指定 session 的完整對話內容"""
    try:
        conversation_logger = _get_conversation_logger()
        conversations = conversation_logger.get_session_logs(session_id)
        conversations = [c for c in conversations if c.get("mode") == "general"]

        store_name = "unknown"
        if conversations:
            store_name = conversations[0].get("session_snapshot", {}).get("store", "unknown")

        logger.info(
            "Retrieved %d general conversations for session %s...",
            len(conversations),
            session_id[:8],
        )

        return {
            "session_id": session_id,
            "store_name": store_name,
            "mode": "general",
            "conversations": conversations,
            "total": len(conversations)
        }

    except Exception as e:
        logger.error("Failed to get general conversation detail: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

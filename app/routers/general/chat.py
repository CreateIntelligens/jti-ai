"""
General Chat API Endpoints
"""

import hashlib
import logging
import os
import uuid
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from google.genai import types
from pydantic import BaseModel

from app.auth import extract_user_gemini_api_key, verify_auth
from app.routers.general.stores import (
    hash_user_gemini_api_key,
    resolve_key_index_for_store,
    resolve_store_config,
)
from app.schemas.chat import (
    DeleteConversationRequest,
    DeleteConversationResponse,
    ExportGeneralConversationsResponse,
    GeneralConversationsBySessionResponse,
    GeneralConversationsResponse,
)
from app.services import gemini_service
from app.services.agent_utils import strip_citations
from app.services.gemini_clients import get_client_by_index, get_client_for_api_key
from app.utils import group_conversations_by_session, group_conversations_as_summary
import app.deps as deps

router = APIRouter(prefix="/api/chat", tags=["General Chat"])
_IN_MEMORY_SESSIONS: dict[str, dict[str, Any]] = {}


class ChatStartRequest(BaseModel):
    store_name: Optional[str] = None
    model: str = os.getenv("GEMINI_MODEL_NAME", "gemini-3.1-flash-lite-preview")
    previous_session_id: Optional[str] = None


class ChatMessageRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    turn_number: Optional[int] = None


def _get_conversation_logger():
    return deps.get_jti_conversation_logger()


def _get_general_session_manager():
    return deps.get_general_chat_session_manager()


def _new_session_id(store_name: str) -> str:
    session_key = f"{store_name}:{uuid.uuid4().hex}"
    return hashlib.sha256(session_key.encode()).hexdigest()


def _get_session(session_id: str) -> dict[str, Any] | None:
    manager = _get_general_session_manager()
    if manager:
        return manager.get_session(session_id)
    return _IN_MEMORY_SESSIONS.get(session_id)


def _create_session(
    *,
    session_id: str,
    store_name: str,
    model: str,
    system_instruction: str | None,
) -> dict[str, Any]:
    manager = _get_general_session_manager()
    if manager:
        return manager.create_session(
            session_id=session_id,
            store_name=store_name,
            model=model,
            system_instruction=system_instruction,
        )

    session = {
        "session_id": session_id,
        "store_name": store_name,
        "model": model,
        "system_instruction": system_instruction,
        "chat_history": [],
    }
    _IN_MEMORY_SESSIONS[session_id] = session
    return session


def _delete_session(session_id: str | None) -> None:
    if not session_id:
        return
    manager = _get_general_session_manager()
    if manager:
        manager.delete_session(session_id)
    _IN_MEMORY_SESSIONS.pop(session_id, None)


def _add_session_message(
    session: dict[str, Any],
    role: str,
    content: str,
    citations: Optional[list[dict[str, Any]]] = None,
) -> None:
    manager = _get_general_session_manager()
    session_id = session["session_id"]
    if manager:
        manager.add_message(session_id, role, content, citations)
        return

    entry: dict[str, Any] = {"role": role, "content": content}
    if citations:
        entry["citations"] = citations
    session.setdefault("chat_history", []).append(entry)


def _truncate_session(session: dict[str, Any], keep_turns: int) -> None:
    manager = _get_general_session_manager()
    session_id = session["session_id"]
    if manager:
        manager.truncate_history(session_id, keep_turns)
        return
    session["chat_history"] = session.get("chat_history", [])[: keep_turns * 2]


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


def _get_system_instruction(store_name: str, auth: dict) -> str | None:
    if not deps.prompt_manager:
        return None

    if auth.get("role") == "user" and auth.get("prompt_index") is not None:
        prompts = deps.prompt_manager.list_prompts(store_name)
        prompt_index = auth["prompt_index"]
        if 0 <= prompt_index < len(prompts):
            return prompts[prompt_index].content

    active_prompt = deps.prompt_manager.get_active_prompt(store_name)
    return active_prompt.content if active_prompt else None


def _format_history(history: list[dict[str, Any]]) -> str:
    lines = []
    for item in history[-8:]:
        role = "使用者" if item.get("role") == "user" else "助理"
        content = str(item.get("content") or "").strip()
        if content:
            lines.append(f"{role}: {content}")
    return "\n".join(lines)


def _extract_response_text(response: Any) -> str:
    text = getattr(response, "text", None)
    if isinstance(text, str):
        return text

    candidates = getattr(response, "candidates", None) or []
    parts = []
    for candidate in candidates:
        content = getattr(candidate, "content", None)
        for part in getattr(content, "parts", None) or []:
            part_text = getattr(part, "text", None)
            if isinstance(part_text, str):
                parts.append(part_text)
    return "\n".join(parts)


def _generate_rag_answer(
    *,
    message: str,
    session: dict[str, Any],
    user_gemini_api_key: str | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    config = resolve_store_config(
        session.get("store_name"),
        hash_user_gemini_api_key(user_gemini_api_key),
    )
    if config is None:
        raise HTTPException(status_code=404, detail="Knowledge store not found")
    if not user_gemini_api_key and not gemini_service.client:
        raise HTTPException(status_code=500, detail="Gemini API key not configured")

    client = (
        get_client_for_api_key(user_gemini_api_key)
        if user_gemini_api_key
        else get_client_by_index(resolve_key_index_for_store(config.name))
    )

    from app.services.rag.service import get_rag_pipeline

    if config.managed_app:
        rag_language = config.managed_language
        rag_source_type = f"{config.managed_app}_knowledge"
        response_language = "English" if config.managed_language == "en" else "繁體中文"
    else:
        rag_language = config.name
        rag_source_type = "general_knowledge"
        response_language = "繁體中文"

    pipeline = get_rag_pipeline()
    kb_text, citations = pipeline.retrieve(
        message,
        language=rag_language,
        source_type=rag_source_type,
        top_k=5,
    )

    history_text = _format_history(session.get("chat_history", []))
    sections = [
        f"請使用{response_language}回答。",
    ]
    if kb_text:
        sections.append(f"<知識庫查詢結果>\n{kb_text}\n</知識庫查詢結果>")
    if history_text:
        sections.append(f"<對話紀錄>\n{history_text}\n</對話紀錄>")
    sections.append(f"使用者問題：{message}")

    config_kwargs: dict[str, Any] = {}
    system_instruction = session.get("system_instruction")
    if system_instruction:
        config_kwargs["system_instruction"] = system_instruction

    response = gemini_service.gemini_with_retry(
        lambda: client.models.generate_content(
            model=session.get("model") or os.getenv("GEMINI_MODEL_NAME", "gemini-3.1-flash-lite-preview"),
            contents="\n\n".join(sections),
            config=types.GenerateContentConfig(
                thinking_config=types.ThinkingConfig(thinking_budget=0),
                **config_kwargs,
            ),
        )
    )
    return strip_citations(_extract_response_text(response)).strip(), citations or []


@router.post("/start")
def start_chat(req: ChatStartRequest, request: Request, auth: dict = Depends(verify_auth)):
    """Start a generic homepage chat session backed by local RAG."""
    if req.previous_session_id:
        _delete_session(req.previous_session_id)
        logging.info("Cleaned up previous general session: %s...", req.previous_session_id[:8])

    user_gemini_api_key = extract_user_gemini_api_key(request)
    store_name = _resolve_request_store(
        req,
        auth,
        hash_user_gemini_api_key(user_gemini_api_key),
    )
    session_id = _new_session_id(store_name)
    system_instruction = _get_system_instruction(store_name, auth)
    _create_session(
        session_id=session_id,
        store_name=store_name,
        model=req.model,
        system_instruction=system_instruction,
    )

    return {
        "ok": True,
        "prompt_applied": system_instruction is not None,
        "session_id": session_id,
    }


@router.post("/message")
def send_message(req: ChatMessageRequest, request: Request, auth: dict = Depends(verify_auth)):
    """Send a message to a generic homepage chat session."""
    user_gemini_api_key = extract_user_gemini_api_key(request)
    owner_key_hash = hash_user_gemini_api_key(user_gemini_api_key)
    session: dict[str, Any] | None = None
    if req.session_id:
        session = _get_session(req.session_id)

    if session is None:
        start_req = ChatStartRequest(store_name=auth.get("store_name"))
        store_name = _resolve_request_store(start_req, auth, owner_key_hash)
        session = _create_session(
            session_id=_new_session_id(store_name),
            store_name=store_name,
            model=start_req.model,
            system_instruction=_get_system_instruction(store_name, auth),
        )

    if req.turn_number is not None:
        keep_turns = max(req.turn_number - 1, 0)
        _truncate_session(session, keep_turns)
        try:
            _get_conversation_logger().delete_turns_from(session["session_id"], req.turn_number)
        except Exception:
            logging.exception("Failed to truncate general conversation logs")

    answer, citations = _generate_rag_answer(
        message=req.message,
        session=session,
        user_gemini_api_key=user_gemini_api_key,
    )
    _add_session_message(session, "user", req.message)
    _add_session_message(session, "model", answer, citations)

    log_result = _get_conversation_logger().log_conversation(
        session_id=session["session_id"],
        user_message=req.message,
        agent_response=answer,
        tool_calls=[],
        session_state={"store": session["store_name"]},
        mode="general",
        citations=citations,
    )
    turn_number = log_result[1] if log_result else None

    return {
        "answer": answer,
        "session_id": session["session_id"],
        "turn_number": turn_number,
        "citations": citations,
    }


@router.delete("/history", response_model=DeleteConversationResponse)
def delete_general_conversations(request: DeleteConversationRequest, auth: dict = Depends(verify_auth)):
    """批量刪除對話紀錄

    Body:
    - session_ids: 要刪除的 session ID 列表

    同時刪除每個 session 的：
    - 對話日誌 (conversation logs)
    - General chat session (MongoDB)
    """
    conversation_logger = _get_conversation_logger()
    general_session_manager = _get_general_session_manager()
    total_logs = 0
    deleted_count = 0
    for sid in request.session_ids:
        total_logs += conversation_logger.delete_session_logs(sid)
        if general_session_manager and general_session_manager.delete_session(sid):
            deleted_count += 1

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
    """
    取得 general chat 的對話歷史（session 列表）

    Query Parameters:
    - store_name: 知識庫名稱（必填）
    - date_from: (可選) 起始日期 YYYY-MM-DD
    - date_to: (可選) 結束日期 YYYY-MM-DD

    回傳該知識庫的所有對話（按 session 分組，含摘要），分頁由前端處理
    """
    try:
        conversation_logger = _get_conversation_logger()
        if not store_name:
            raise HTTPException(status_code=400, detail="未指定知識庫")

        query: dict = {"mode": "general", "session_snapshot.store": store_name}
        if date_from or date_to:
            ts_filter: dict = {}
            if date_from:
                ts_filter["$gte"] = datetime.strptime(date_from, "%Y-%m-%d")
            if date_to:
                ts_filter["$lte"] = datetime.strptime(date_to + " 23:59:59", "%Y-%m-%d %H:%M:%S")
            query["timestamp"] = ts_filter

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
        logging.error(f"Failed to get general conversations: {e}")
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
    """
    匯出 general chat 的對話歷史為 JSON 格式

    Query Parameters:
    - store_name: 知識庫名稱（必填）
    - session_ids: (可選) 指定一個或多個 Session ID（用逗號分隔），只匯出指定的 sessions
    """
    try:
        conversation_logger = _get_conversation_logger()
        if not store_name:
            raise HTTPException(status_code=400, detail="未指定知識庫")

        if session_ids:
            session_id_list = [sid.strip() for sid in session_ids.split(',') if sid.strip()]

            sessions = []
            total_conversations = 0

            for session_id in session_id_list:
                conversations = conversation_logger.get_session_logs(session_id)
                conversations = [
                    c for c in conversations
                    if c.get("mode") == "general" and c.get("session_snapshot", {}).get("store") == store_name
                ]

                if conversations:
                    sessions.append({
                        "session_id": session_id,
                        "conversations": conversations,
                        "first_message_time": conversations[0].get("timestamp") if conversations else None,
                        "total": len(conversations)
                    })
                    total_conversations += len(conversations)

            sessions.sort(key=lambda x: x["first_message_time"] or "", reverse=True)

            return {
                "exported_at": datetime.utcnow().isoformat(),
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
                "exported_at": datetime.utcnow().isoformat(),
                "store_name": store_name,
                "mode": "general",
                "sessions": session_list,
                "total_conversations": len(store_conversations),
                "total_sessions": len(session_list)
            }

    except Exception as e:
        logging.error(f"Failed to export general conversations: {e}")
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
    """
    取得指定 session 的完整對話內容

    Path Parameters:
    - session_id: Session ID
    """
    try:
        conversation_logger = _get_conversation_logger()
        conversations = conversation_logger.get_session_logs(session_id)
        conversations = [c for c in conversations if c.get("mode") == "general"]

        store_name = "unknown"
        if conversations:
            store_name = conversations[0].get("session_snapshot", {}).get("store", "unknown")

        logging.info(f"Retrieved {len(conversations)} general conversations for session {session_id[:8]}...")

        return {
            "session_id": session_id,
            "store_name": store_name,
            "mode": "general",
            "conversations": conversations,
            "total": len(conversations)
        }

    except Exception as e:
        logging.error(f"Failed to get general conversation detail: {e}")
        raise HTTPException(status_code=500, detail=str(e))

"""
General Chat API Endpoints

Thin router layer: HTTP routing + conversation logging.
Core chat logic delegated to GeneralAgent (BaseAgent subclass).
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.auth import extract_user_gemini_api_key, verify_auth
from app.routers.general.stores import (
    hash_user_gemini_api_key,
    resolve_store_config,
    store_config_matches_scope,
)
from app.schemas.chat import (
    DeleteConversationRequest,
    DeleteConversationResponse,
    ExportGeneralConversationsResponse,
    GeneralConversationsBySessionResponse,
    GeneralConversationsResponse,
)
from app.models_config import DEFAULT_RAG_MODEL
from app.utils import (
    build_date_query,
    build_history_summary_response,
    export_sessions_by_ids,
    group_conversations_by_session,
    normalize_history_pagination,
    simplified_conversation_sessions,
)
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
    # General chat 使用獨立的 general_app conversation logger（不再寄生於
    # jti_app）。logger 仍以 mode="general" 標記，與同庫的其他來源區分。
    return deps.get_general_conversation_logger()


def _get_session_manager():
    return deps.get_general_chat_session_manager()


def _resolve_request_store(
    req: ChatStartRequest,
    auth: dict,
    owner_key_hash: str | None = None,
) -> str:
    def resolve_or_404(store_name: str | None):
        config = resolve_store_config(store_name, owner_key_hash)
        if config is None:
            raise HTTPException(status_code=404, detail="Knowledge store not found")
        return config

    if auth.get("role") == "user":
        assigned_store = auth.get("store_name")
        if assigned_store:
            config = resolve_or_404(assigned_store)
            auth_scope = auth.get("scope")
            if auth_scope and not store_config_matches_scope(config, auth_scope):
                raise HTTPException(status_code=403, detail="Access denied")
            return config.name

        auth_scope = auth.get("scope")
        if not auth_scope:
            raise HTTPException(status_code=403, detail="Access denied")
        config = resolve_or_404(req.store_name)
        if not store_config_matches_scope(config, auth_scope):
            raise HTTPException(status_code=403, detail="Access denied")
        return config.name

    return resolve_or_404(req.store_name).name


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
    # English sessions use the English persona when one was imported/saved;
    # otherwise fall back to the (zh) content so older prompts still work.
    persona = prompt.content
    if language == "en" and getattr(prompt, "content_en", None):
        persona = prompt.content_en
    return build_system_instruction(
        persona=persona,
        language=language,
        response_rule_sections=sections,
        max_response_chars=max_chars,
    )


def _get_system_instruction(store_name: str, auth: dict, language: str = "zh") -> str | None:
    prompt = _resolve_active_prompt(store_name, auth)
    if prompt is None:
        return None
    return _compose_prompt_system_instruction(prompt, language=language)


def _app_default_system_instruction(managed_app: str, language: str = "zh") -> str | None:
    """Full system instruction (persona + rule sections) for a managed app.

    When the General entry point opens a managed app's fixed store
    (__jti__ / __hciot__), the session should behave like a chat inside that
    app — same persona and the same response rule sections — rather than the
    generic General assistant. Each app module owns its own
    build_system_instruction (with app-specific safety wrap / headers), so we
    defer to it instead of re-assembling the pieces here.
    """
    if managed_app == "jti":
        from app.services.jti import agent_prompts as app_prompts
    elif managed_app == "hciot":
        from app.services.hciot import agent_prompts as app_prompts
    else:
        return None

    persona = app_prompts.PERSONA.get(language, app_prompts.PERSONA["zh"])
    sections = app_prompts.DEFAULT_RESPONSE_RULE_SECTIONS.get(
        language, app_prompts.DEFAULT_RESPONSE_RULE_SECTIONS["zh"]
    )
    # NB: jti/hciot expose different names for the char-limit kwarg
    # (max_response_chars vs limit); both default to their own
    # DEFAULT_MAX_RESPONSE_CHARS, so we omit it and let each app decide.
    return app_prompts.build_system_instruction(
        persona=persona,
        language=language,
        response_rule_sections=sections,
    )


def _store_topic_label(config) -> str | None:
    """Human-readable subject of a knowledge store, for grounding query rewrites.

    Managed app stores (JTI/HCIoT) already carry that context in their own
    persona, so we only surface this for dynamic/general stores whose display
    name is the only hint of what the store is about.
    """
    if config is None or config.managed_language:
        return None
    label = (config.display_name or "").strip()
    # A bare store_id (e.g. "store_8ad3...") tells the model nothing useful.
    if not label or label == config.name:
        return None
    return label


def _resolve_general_system_instruction(store_name: str, auth: dict, config) -> str | None:
    """Pick the system instruction for a General-entry chat session.

    Priority:
      1. A user-defined prompt for this store (prompt_manager) — always wins, and
         lives entirely in General's own prompt store, so editing it never touches
         the app's own prompt (and vice versa). Only the *defaults* are shared.
      2. No custom prompt + a managed app store (__jti__/__hciot__): borrow that
         app's DEFAULT persona + rule sections, so it behaves like the app.
      3. Otherwise: the generic General prompt, augmented with the store topic so
         terse queries can be expanded.
    """
    language = getattr(config, "managed_language", None) or "zh"
    custom = _get_system_instruction(store_name, auth, language=language)
    if custom is not None:
        return custom

    managed_app = getattr(config, "managed_app", None)
    if config is not None and config.managed_language and managed_app in {"jti", "hciot"}:
        app_instruction = _app_default_system_instruction(managed_app, language)
        if app_instruction is not None:
            return app_instruction

    return _augment_with_store_topic(None, config)


def _augment_with_store_topic(system_instruction: str | None, config) -> str | None:
    """Prepend the store's topic so the agent can expand terse queries.

    General stores are dynamic: a user asking "顏色" gives the model no subject
    to search on. Telling it the store is about e.g. "寶島釣魚" lets the query
    rewrite step add that subject, the way JTI/HCIoT personas already do.
    """
    label = _store_topic_label(config)
    if label is None:
        return system_instruction
    prefix = (
        f"目前知識庫主題：{label}。"
        "當使用者問題過於簡短或籠統時，請結合此主題補上明確的關鍵字後再檢索。"
    )
    if not system_instruction:
        return prefix
    return f"{prefix}\n\n{system_instruction}"


# === Chat Endpoints ===

@router.post("/start")
def start_chat(req: ChatStartRequest, request: Request, auth: dict = Depends(verify_auth)):
    """Start a generic homepage chat session backed by local RAG."""
    if req.previous_session_id:
        main_agent.remove_session(req.previous_session_id)
        logger.info("Cleaned up previous general session: %s...", req.previous_session_id[:8])

    user_gemini_api_key = extract_user_gemini_api_key(request)
    owner_key_hash = hash_user_gemini_api_key(user_gemini_api_key)
    store_name = _resolve_request_store(
        req,
        auth,
        owner_key_hash,
    )
    # Resolve managed_app / managed_language for RAG source_type routing
    config = resolve_store_config(store_name, owner_key_hash)
    managed_app = config.managed_app if config else None
    managed_language = config.managed_language if config else None

    system_instruction = _resolve_general_system_instruction(store_name, auth, config)

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
            system_instruction=_resolve_general_system_instruction(store_name, auth, config),
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
        store_name=session.metadata.get("store_name") or None,
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
    page: int = 1,
    page_size: int = 20,
    auth: dict = Depends(verify_auth),
):
    """取得 general chat 的對話歷史（session 列表）"""
    try:
        conversation_logger = _get_conversation_logger()
        if not store_name:
            raise HTTPException(status_code=400, detail="未指定知識庫")

        # 以 store 過濾：新資料用頂層 store_name（已建 sparse 索引），舊資料退回
        # session_snapshot.store，兩者皆比對以免遺漏歷史（含回填前的紀錄）。
        query = build_date_query(
            "general", date_from, date_to,
            extras={"$or": [
                {"store_name": store_name},
                {"session_snapshot.store": store_name},
            ]},
        )

        page, page_size = normalize_history_pagination(page, page_size)
        session_ids, total_sessions = conversation_logger.get_paginated_session_ids(
            query=query,
            page=page,
            page_size=page_size,
        )

        session_list = conversation_logger.get_session_summaries(session_ids, query=query)

        return build_history_summary_response(
            mode="general",
            sessions=session_list,
            total_sessions=total_sessions,
            page=page,
            page_size=page_size,
            extra={"store_name": store_name},
        )

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
    simple: bool = False,
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
            result = {
                "exported_at": datetime.now(timezone.utc).isoformat(),
                "store_name": store_name,
                "mode": "general",
                "sessions": sessions,
                "total_conversations": total_conversations,
                "total_sessions": len(sessions)
            }
        else:
            all_conversations = conversation_logger.get_session_logs_by_mode("general")

            # 比對頂層 store_name（新資料）或 session_snapshot.store（舊資料），兩者皆可。
            store_conversations = [
                c for c in all_conversations
                if c.get("store_name") == store_name
                or c.get("session_snapshot", {}).get("store") == store_name
            ]

            session_list = group_conversations_by_session(store_conversations)

            result = {
                "exported_at": datetime.now(timezone.utc).isoformat(),
                "store_name": store_name,
                "mode": "general",
                "sessions": session_list,
                "total_conversations": len(store_conversations),
                "total_sessions": len(session_list)
        }

        if simple:
            return JSONResponse(content=simplified_conversation_sessions(result.get("sessions", [])))

        return result

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

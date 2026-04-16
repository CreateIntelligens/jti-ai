"""
General Chat API Endpoints
"""

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends

from app.auth import verify_auth
from app.schemas.chat import (
    DeleteConversationRequest,
    DeleteConversationResponse,
    ExportGeneralConversationsResponse,
    GeneralConversationsBySessionResponse,
    GeneralConversationsResponse,
)
from app.utils import group_conversations_by_session, group_conversations_as_summary
import app.deps as deps

router = APIRouter(prefix="/api/chat", tags=["General Chat"])


@router.delete("/history", response_model=DeleteConversationResponse)
def delete_general_conversations(request: DeleteConversationRequest, auth: dict = Depends(verify_auth)):
    """批量刪除對話紀錄

    Body:
    - session_ids: 要刪除的 session ID 列表

    同時刪除每個 session 的：
    - 對話日誌 (conversation logs)
    - General chat session (MongoDB)
    """
    total_logs = 0
    deleted_count = 0
    for sid in request.session_ids:
        total_logs += deps.conversation_logger.delete_session_logs(sid)
        if deps.general_session_manager and deps.general_session_manager.delete_session(sid):
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

        session_ids, total_sessions = deps.conversation_logger.get_paginated_session_ids(
            query=query,
            page=1,
            page_size=100000
        )

        all_conversations = deps.conversation_logger.get_logs_for_sessions(session_ids)

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
        if not store_name:
            raise HTTPException(status_code=400, detail="未指定知識庫")

        if session_ids:
            session_id_list = [sid.strip() for sid in session_ids.split(',') if sid.strip()]

            sessions = []
            total_conversations = 0

            for session_id in session_id_list:
                conversations = deps.conversation_logger.get_session_logs(session_id)
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
            all_conversations = deps.conversation_logger.get_session_logs_by_mode("general")

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
        conversations = deps.conversation_logger.get_session_logs(session_id)
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

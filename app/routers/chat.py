"""
General Chat API Endpoints
"""

import hashlib
import logging
import os
import re
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from app.auth import verify_auth
from app.core import FileSearchManager
from app.routers import jti  # for response models
from app.utils import group_conversations_by_session, group_conversations_as_summary
import app.deps as deps

router = APIRouter(prefix="/api/chat", tags=["General Chat"])


class ChatStartRequest(BaseModel):
    store_name: Optional[str] = None  # admin 自由選，一般 key 會被強制覆蓋
    model: str = os.getenv("GEMINI_MODEL_NAME", "gemini-2.5-flash")
    previous_session_id: Optional[str] = None  # 舊 session ID，用於清理記憶體


class ChatMessageRequest(BaseModel):
    message: str
    session_id: Optional[str] = None  # 可選：指定 session ID
    turn_number: Optional[int] = None  # 可選：帶此參數時，先截斷到該輪之前再送訊息（重新生成 / 編輯重送）


@router.post("/start")
def start_chat(req: ChatStartRequest, auth: dict = Depends(verify_auth)):
    """
    開始新的對話 Session。

    回傳 session_id 供後續 /api/chat/message 使用，確保對話上下文隔離。

    認證：
    - Admin → 用 request 的 store_name（必填）
    - 一般 Key → 強制用 key 綁定的 store（忽略 request 的 store_name）
    """
    # 清理舊 session 的記憶體
    if req.previous_session_id and req.previous_session_id in deps.user_managers:
        del deps.user_managers[req.previous_session_id]
        logging.info(f"Cleaned up previous session: {req.previous_session_id[:8]}...")

    # 決定 store_name
    if auth["role"] == "admin":
        if not req.store_name:
            raise HTTPException(status_code=400, detail="Admin 必須指定 store_name")
        store_name = req.store_name
    else:
        # 一般 key → 強制用 key 綁定的 store
        store_name = auth["store_name"]

    # 生成 session_id
    session_key = f"{store_name}:{uuid.uuid4().hex[:8]}"
    session_id = hashlib.sha256(session_key.encode()).hexdigest()

    # 取得該 session 專屬的 manager
    mgr = deps._get_or_create_manager(session_id=session_id)

    # 取得啟用的 prompt (如果有)
    system_instruction = None
    if deps.prompt_manager:
        # 一般 key 有指定 prompt_index 時，優先使用
        if auth["role"] == "user" and auth.get("prompt_index") is not None:
            prompts = deps.prompt_manager.list_prompts(store_name)
            if 0 <= auth["prompt_index"] < len(prompts):
                system_instruction = prompts[auth["prompt_index"]].content
                print(f"[Session {session_id[:8]}] 使用 API Key 指定的 Prompt #{auth['prompt_index']}")

        if not system_instruction:
            active_prompt = deps.prompt_manager.get_active_prompt(store_name)
            if active_prompt:
                system_instruction = active_prompt.content
                print(f"[Session {session_id[:8]}] 從 MongoDB 載入 Prompt: {active_prompt.name}")
            else:
                print(f"[Session {session_id[:8]}] Store {store_name} 沒有啟用的 Prompt")

    mgr.start_chat(store_name, req.model, system_instruction=system_instruction)
    print(f"[Session {session_id[:8]}] 開始新對話: store={store_name}, model={req.model}, role={auth['role']}")

    # 持久化到 MongoDB
    if deps.general_session_manager:
        deps.general_session_manager.create_session(
            session_id=session_id,
            store_name=store_name,
            model=req.model,
            system_instruction=system_instruction,
        )

    return {
        "ok": True,
        "prompt_applied": system_instruction is not None,
        "session_id": session_id
    }


@router.post("/message")
def send_message(req: ChatMessageRequest, auth: dict = Depends(verify_auth)):
    """
    發送訊息到指定的對話 Session。

    必須提供 session_id（從 /api/chat/start 取得），以確保使用正確的對話上下文。
    如果沒有提供 session_id，將使用全域 manager（不推薦多用戶場景）。

    可選參數：
    - turn_number: 帶此參數時，先截斷到該輪之前再送訊息（用於重新生成 / 編輯重送）
    """
    # 取得 session_id（用於日誌記錄）
    if req.session_id:
        session_id = req.session_id
    else:
        session_id = uuid.uuid4().hex
        print(f"[警告] /api/chat/message 沒有提供 session_id，使用全域 manager")

    # 如果帶了 turn_number，先執行截斷
    if req.turn_number is not None and req.session_id:
        turn_number = req.turn_number

        # 截斷 MongoDB chat_history
        if deps.general_session_manager:
            deps.general_session_manager.truncate_history(session_id, turn_number - 1)

        # 刪除 conversation_logs
        deleted_count = deps.conversation_logger.delete_turns_from(session_id, turn_number)
        print(f"[Regenerate] Session {session_id[:8]}... turn #{turn_number}: 刪除 {deleted_count} 筆日誌")

        # 清除記憶體中的 chat session，讓它重建
        if session_id in deps.user_managers:
            del deps.user_managers[session_id]

    # 取得該 session 專屬的 manager
    mgr = deps._get_or_create_manager(session_id=req.session_id)

    # 如果 manager 沒有 chat（general_chat_sessions 可能過期），從 conversation_logs 重建
    if req.session_id and not (hasattr(mgr, 'current_store') and mgr.current_store):
        remaining_logs = deps.conversation_logger.get_session_logs(session_id)
        remaining_logs = [l for l in remaining_logs if l.get("mode") == "general"]

        store_name = None
        if remaining_logs:
            store_name = remaining_logs[0].get("session_snapshot", {}).get("store")
        if not store_name:
            store_name = os.getenv("GEMINI_FILE_SEARCH_STORE_ID_ZH", "")

        history = []
        for log in remaining_logs:
            history.append({"role": "user", "content": log["user_message"]})
            history.append({"role": "model", "content": log["agent_response"]})

        system_instruction = None
        if deps.prompt_manager:
            active_prompt = deps.prompt_manager.get_active_prompt(store_name)
            if active_prompt:
                system_instruction = active_prompt.content

        model_name = os.getenv("GEMINI_MODEL_NAME", "gemini-2.5-flash")
        history_contents = FileSearchManager._build_history_contents(history)
        mgr.start_chat(store_name, model_name, system_instruction=system_instruction, history=history_contents)

        if deps.general_session_manager:
            deps.general_session_manager.create_session(
                session_id=session_id, store_name=store_name,
                model=model_name, system_instruction=system_instruction,
            )
            for h in history:
                deps.general_session_manager.add_message(session_id, h["role"], h["content"])

        print(f"[Session] 從 conversation_logs 重建: {session_id[:8]}... (歷史 {len(history)} 則)")

    current_store = mgr.current_store if hasattr(mgr, 'current_store') else 'unknown'

    try:
        response = mgr.send_message(req.message)
        answer = response.text or ""

        # 診斷空回應
        if not answer.strip():
            candidates = response.candidates if hasattr(response, 'candidates') else []
            if candidates:
                c = candidates[0]
                finish = getattr(c, 'finish_reason', 'unknown')
                safety = getattr(c, 'safety_ratings', [])
                parts = c.content.parts if hasattr(c, 'content') and c.content and c.content.parts else []
                print(f"[Session {session_id[:8]}] ⚠️ 空回應診斷: finish_reason={finish}, safety={safety}, parts={len(parts)}")
                for i, p in enumerate(parts):
                    print(f"  part[{i}]: text={repr(getattr(p, 'text', None))[:100]}, thought={bool(getattr(p, 'thought', None))}")
            else:
                print(f"[Session {session_id[:8]}] ⚠️ 空回應: 無 candidates")

        # 清除 Gemini File Search 的 citation 標記
        answer = re.sub(r'\s*\[cite:\s*[^\]]*\]', '', answer).strip()

        # 持久化對話到 MongoDB
        if deps.general_session_manager and session_id:
            deps.general_session_manager.add_message(session_id, "user", req.message)
            deps.general_session_manager.add_message(session_id, "model", answer)

        # 記錄對話日誌
        log_result = deps.conversation_logger.log_conversation(
            session_id=session_id,
            user_message=req.message,
            agent_response=answer,
            tool_calls=[],
            session_state={"store": current_store},
            mode="general"
        )
        result_turn = log_result[1] if log_result else None

        print(f"[Session {session_id[:8]}] 使用者: {req.message[:50]}... | 回應: {answer[:50]}...")

        return {
            "answer": answer,
            "session_id": session_id,
            "turn_number": result_turn,
        }
    except ValueError as e:
        # 記錄錯誤對話
        deps.conversation_logger.log_conversation(
            session_id=session_id,
            user_message=req.message,
            agent_response="",
            tool_calls=[],
            session_state={"store": current_store},
            error=str(e),
            mode="general"
        )
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/history/{session_id}", response_model=jti.DeleteConversationResponse)
def delete_general_conversation(session_id: str, auth: dict = Depends(verify_auth)):
    """刪除指定 session 的對話紀錄

    同時刪除：
    - 對話日誌 (conversation logs)
    - General chat session (MongoDB)
    - 記憶體中的 session manager
    """

    deleted_logs = deps.conversation_logger.delete_session_logs(session_id)

    deleted_session = False
    if deps.general_session_manager:
        deleted_session = deps.general_session_manager.delete_session(session_id)

    # 清除記憶體中的 manager
    if session_id in deps.user_managers:
        del deps.user_managers[session_id]

    return {
        "ok": True,
        "deleted_logs": deleted_logs,
        "deleted_session": deleted_session,
    }


@router.get(
    "/history",
    response_model=jti.GeneralConversationsResponse,
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
        mgr = deps._get_or_create_manager()

        # 決定使用哪個 store
        current_store = store_name if store_name else (mgr.current_store if hasattr(mgr, 'current_store') else None)

        if not current_store:
            raise HTTPException(status_code=400, detail="未指定知識庫或當前無活動知識庫")

        query: dict = {"mode": "general", "session_snapshot.store": current_store}
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
            "store_name": current_store,
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
    response_model=jti.ExportGeneralConversationsResponse,
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

    範例:
    - 單個 session: ?store_name=xxx&session_ids=abc123
    - 多個 sessions: ?store_name=xxx&session_ids=abc123,def456,ghi789
    - 所有 sessions: ?store_name=xxx (不提供 session_ids 參數)

    回傳該知識庫的對話（按 session 分組）供匯出使用
    """
    try:
        mgr = deps._get_or_create_manager()

        # 決定使用哪個 store
        current_store = store_name if store_name else (mgr.current_store if hasattr(mgr, 'current_store') else None)

        if not current_store:
            raise HTTPException(status_code=400, detail="未指定知識庫或當前無活動知識庫")

        if session_ids:
            # 解析 session_ids（支援逗號分隔）
            session_id_list = [sid.strip() for sid in session_ids.split(',') if sid.strip()]

            # 收集指定 sessions 的對話
            sessions = []
            total_conversations = 0

            for session_id in session_id_list:
                conversations = deps.conversation_logger.get_session_logs(session_id)
                # 過濾出屬於這個知識庫的對話
                conversations = [
                    c for c in conversations
                    if c.get("mode") == "general" and c.get("session_snapshot", {}).get("store") == current_store
                ]

                if conversations:
                    sessions.append({
                        "session_id": session_id,
                        "conversations": conversations,
                        "first_message_time": conversations[0].get("timestamp") if conversations else None,
                        "total": len(conversations)
                    })
                    total_conversations += len(conversations)

            # 按時間排序
            sessions.sort(key=lambda x: x["first_message_time"] or "", reverse=True)

            return {
                "exported_at": datetime.utcnow().isoformat(),
                "store_name": current_store,
                "mode": "general",
                "sessions": sessions,
                "total_conversations": total_conversations,
                "total_sessions": len(sessions)
            }
        else:
            # 匯出所有該知識庫的對話
            all_conversations = deps.conversation_logger.get_session_logs_by_mode("general")

            # 篩選出屬於這個知識庫的對話
            store_conversations = [
                c for c in all_conversations
                if c.get("session_snapshot", {}).get("store") == current_store
            ]

            session_list = group_conversations_by_session(store_conversations)

            return {
                "exported_at": datetime.utcnow().isoformat(),
                "store_name": current_store,
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
    response_model=jti.GeneralConversationsBySessionResponse,
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

        # 從對話中推斷 store_name
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

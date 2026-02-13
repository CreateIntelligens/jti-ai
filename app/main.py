"""
Gemini File Search FastAPI 後端
"""

import hashlib
import logging
import os
import re
import shutil
import uuid
import warnings
from pathlib import Path
import time
from datetime import datetime
from typing import Dict, Optional

# 設定 app logger 輸出
logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(name)s %(message)s', datefmt='%Y-%m-%d %H:%M:%S')

# 降低第三方套件的 log 等級（減少雜訊）
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("google").setLevel(logging.WARNING)

# 過濾 Gemini AFC 警告（我們故意使用 Manual Function Calling）
warnings.filterwarnings('ignore', message='.*automatic function calling.*')
warnings.filterwarnings('ignore', message='.*AFC.*')

# 設定 uvicorn 日誌格式（加上時間戳，保留顏色，狀態碼上色）
import uvicorn.logging

# ANSI 顏色碼
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
RESET = "\033[0m"

class TimestampFormatter(uvicorn.logging.ColourizedFormatter):
    """在 uvicorn 原有的彩色格式前加上時間戳，並對狀態碼上色。"""
    def formatMessage(self, record):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        original = super().formatMessage(record)

        # 對 HTTP 狀態碼上色
        msg = original
        if " 200" in msg or " 201" in msg:
            msg = msg.replace(" 200", f" {GREEN}200{RESET}").replace(" 201", f" {GREEN}201{RESET}")
        elif " 404" in msg or " 400" in msg or " 401" in msg or " 403" in msg:
            msg = msg.replace(" 404", f" {RED}404{RESET}").replace(" 400", f" {RED}400{RESET}")
            msg = msg.replace(" 401", f" {RED}401{RESET}").replace(" 403", f" {RED}403{RESET}")
        elif " 500" in msg or " 502" in msg or " 503" in msg:
            msg = msg.replace(" 500", f" {RED}500{RESET}").replace(" 502", f" {RED}502{RESET}")
            msg = msg.replace(" 503", f" {RED}503{RESET}")
        elif " 429" in msg:
            msg = msg.replace(" 429", f" {YELLOW}429{RESET}")

        return f"[{timestamp}] {msg}"

# 覆蓋 uvicorn 的 logger 格式
for logger_name in ("uvicorn", "uvicorn.access", "uvicorn.error"):
    uvicorn_logger = logging.getLogger(logger_name)
    for handler in uvicorn_logger.handlers:
        handler.setFormatter(TimestampFormatter("%(levelprefix)s %(message)s"))

from fastapi import FastAPI, File, HTTPException, UploadFile, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from google.genai.errors import ClientError

from .core import FileSearchManager
from .api_keys import APIKeyManager
from .auth import verify_auth, require_admin, _extract_bearer_token
from .routers import jti
from .services.session.session_manager_factory import get_conversation_logger, get_general_chat_session_manager
from .services.mongo_client import get_mongo_client
from .utils import group_conversations_by_session, group_conversations_as_summary

# 使用工廠函數取得適當的實作（MongoDB 或檔案系統）
conversation_logger = get_conversation_logger()

app = FastAPI(title="Gemini File Search API")

@app.exception_handler(ClientError)
async def gemini_client_error_handler(request: Request, exc: ClientError):
    """處理 Google GenAI Client 錯誤 (例如 429 配額不足)。"""
    error_msg = str(exc)
    print(f"[Gemini API Error] {error_msg}")  # 打印完整錯誤

    if "RESOURCE_EXHAUSTED" in error_msg or "429" in error_msg:
        status_code = 429
        detail = "目前使用量已達上限 (429)，請稍後再試。"
    else:
        status_code = 400
        detail = error_msg

    return JSONResponse(
        status_code=status_code,
        content={"detail": detail},
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

manager: FileSearchManager | None = None
prompt_manager = None
api_key_manager: APIKeyManager | None = None
general_session_manager = None  # GeneralChatSessionManager (MongoDB)
# Session managers: {session_id: FileSearchManager}
user_managers: Dict[str, FileSearchManager] = {}


@app.on_event("startup")
def startup():
    """應用程式啟動時初始化 Manager。"""
    global manager, prompt_manager, api_key_manager, general_session_manager
    try:
        manager = FileSearchManager()
        from .prompts import PromptManager
        prompt_manager = PromptManager()
        api_key_manager = APIKeyManager()
        general_session_manager = get_general_chat_session_manager()
        if general_session_manager:
            print("[Startup] ✅ GeneralChatSessionManager (MongoDB) 已啟用")
        else:
            print("[Startup] ⚠️ GeneralChatSessionManager 未啟用，使用記憶體模式")
    except ValueError as e:
        print(f"警告: {e}")


def _get_or_create_manager(user_api_key: Optional[str] = None, session_id: Optional[str] = None) -> FileSearchManager:
    """
    根據 session_id 或 API Key 取得或建立 Manager

    優先順序：
    1. session_id（多用戶場景）
    2. user_api_key（API Key 場景）
    3. 全域 manager（預設）
    """
    # 1. 如果有 session_id，用 session_id 隔離
    if session_id:
        if session_id not in user_managers:
            if not manager:
                raise HTTPException(status_code=500, detail="未設定 API Key")
            # 複製全域 manager 的 API key 建立新實例
            new_mgr = FileSearchManager(api_key=manager.api_key if hasattr(manager, 'api_key') else None)

            # 嘗試從 MongoDB 恢復 session
            if general_session_manager:
                saved_session = general_session_manager.get_session(session_id)
                if saved_session:
                    history_contents = FileSearchManager._build_history_contents(
                        saved_session.get("chat_history", [])
                    )
                    new_mgr.start_chat(
                        saved_session["store_name"],
                        saved_session.get("model", "gemini-2.5-flash"),
                        system_instruction=saved_session.get("system_instruction"),
                        history=history_contents,
                    )
                    print(f"[Session] 從 MongoDB 恢復 Session: {session_id[:8]}... (歷史 {len(history_contents)} 則)")

            user_managers[session_id] = new_mgr
            if not (general_session_manager and general_session_manager.get_session(session_id)):
                print(f"[Session] 建立新的 Session Manager: {session_id[:8]}...")
        return user_managers[session_id]

    # 2. 如果有 user_api_key，用 API Key hash 隔離
    if user_api_key:
        key_hash = hashlib.sha256(user_api_key.encode()).hexdigest()
        if key_hash not in user_managers:
            try:
                user_managers[key_hash] = FileSearchManager(api_key=user_api_key)
                print(f"[Session] 建立新的 API Key Manager: {key_hash[:8]}...")
            except ValueError as e:
                raise HTTPException(status_code=400, detail=f"無效的 API Key: {e}")
        return user_managers[key_hash]

    # 3. 使用預設的全域 manager
    if not manager:
        raise HTTPException(status_code=500, detail="未設定 API Key")
    return manager


class CreateStoreRequest(BaseModel):
    display_name: str


class QueryRequest(BaseModel):
    store_name: str
    question: str


class ChatStartRequest(BaseModel):
    store_name: Optional[str] = None  # admin 自由選，一般 key 會被強制覆蓋
    model: str = os.getenv("GEMINI_MODEL_NAME", "gemini-2.5-flash")
    previous_session_id: Optional[str] = None  # 舊 session ID，用於清理記憶體


class ChatMessageRequest(BaseModel):
    message: str
    session_id: Optional[str] = None  # 可選：指定 session ID
    turn_number: Optional[int] = None  # 可選：帶此參數時，先截斷到該輪之前再送訊息（重新生成 / 編輯重送）


@app.get("/api/stores")
def list_stores(auth: dict = Depends(verify_auth)):
    """列出所有 Store。（Admin only）"""
    require_admin(auth)
    mgr = _get_or_create_manager()
    stores = mgr.list_stores()
    return [{"name": s.name, "display_name": s.display_name} for s in stores]


@app.post("/api/stores")
def create_store(req: CreateStoreRequest, auth: dict = Depends(verify_auth)):
    """建立新 Store。（Admin only）"""
    require_admin(auth)
    mgr = _get_or_create_manager()
    store_name = mgr.create_store(req.display_name)
    return {"name": store_name}


@app.get("/api/stores/{store_name:path}/files")
def list_files(store_name: str, auth: dict = Depends(verify_auth)):
    """列出 Store 中的檔案。（Admin only）"""
    require_admin(auth)
    mgr = _get_or_create_manager()
    files = mgr.list_files(store_name)
    return [{"name": f.name, "display_name": f.display_name} for f in files]


@app.delete("/api/files/{file_name:path}")
def delete_file(file_name: str, auth: dict = Depends(verify_auth)):
    """刪除檔案。（Admin only）"""
    require_admin(auth)
    mgr = _get_or_create_manager()
    print(f"嘗試刪除檔案: {file_name}")
    mgr.delete_file(file_name)
    return {"ok": True}


@app.post("/api/stores/{store_name:path}/upload")
async def upload_file(store_name: str, file: UploadFile = File(...), auth: dict = Depends(verify_auth)):
    """上傳檔案到 Store。（Admin only）"""
    require_admin(auth)
    mgr = _get_or_create_manager()

    temp_dir = Path("/tmp/gemini-upload")
    temp_dir.mkdir(exist_ok=True)
    ext = Path(file.filename).suffix if file.filename else ""
    safe_filename = f"{uuid.uuid4()}{ext}"
    temp_path = temp_dir / safe_filename

    with open(temp_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    try:
        result = mgr.upload_file(
            store_name, str(temp_path), file.filename, mime_type=None
        )
        return {"name": result}
    finally:
        temp_path.unlink(missing_ok=True)


@app.post("/api/query")
def query(req: QueryRequest, auth: dict = Depends(verify_auth)):
    """查詢 Store (單次)。（Admin only）"""
    require_admin(auth)
    mgr = _get_or_create_manager()
    response = mgr.query(req.store_name, req.question)
    return {"answer": response.text}


@app.post("/api/chat/start")
def start_chat(req: ChatStartRequest, auth: dict = Depends(verify_auth)):
    """
    開始新的對話 Session。

    回傳 session_id 供後續 /api/chat/message 使用，確保對話上下文隔離。

    認證：
    - Admin → 用 request 的 store_name（必填）
    - 一般 Key → 強制用 key 綁定的 store（忽略 request 的 store_name）
    """
    # 清理舊 session 的記憶體
    if req.previous_session_id and req.previous_session_id in user_managers:
        del user_managers[req.previous_session_id]
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
    mgr = _get_or_create_manager(session_id=session_id)

    # 取得啟用的 prompt (如果有)
    system_instruction = None
    if prompt_manager:
        # 一般 key 有指定 prompt_index 時，優先使用
        if auth["role"] == "user" and auth.get("prompt_index") is not None:
            prompts = prompt_manager.list_prompts(store_name)
            if 0 <= auth["prompt_index"] < len(prompts):
                system_instruction = prompts[auth["prompt_index"]].content
                print(f"[Session {session_id[:8]}] 使用 API Key 指定的 Prompt #{auth['prompt_index']}")

        if not system_instruction:
            active_prompt = prompt_manager.get_active_prompt(store_name)
            if active_prompt:
                system_instruction = active_prompt.content
                print(f"[Session {session_id[:8]}] 從 MongoDB 載入 Prompt: {active_prompt.name}")
            else:
                print(f"[Session {session_id[:8]}] Store {store_name} 沒有啟用的 Prompt")

    mgr.start_chat(store_name, req.model, system_instruction=system_instruction)
    print(f"[Session {session_id[:8]}] 開始新對話: store={store_name}, model={req.model}, role={auth['role']}")

    # 持久化到 MongoDB
    if general_session_manager:
        general_session_manager.create_session(
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

@app.post("/api/chat/message")
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
        if general_session_manager:
            general_session_manager.truncate_history(session_id, turn_number - 1)

        # 刪除 conversation_logs
        deleted_count = conversation_logger.delete_turns_from(session_id, turn_number)
        print(f"[Regenerate] Session {session_id[:8]}... turn #{turn_number}: 刪除 {deleted_count} 筆日誌")

        # 清除記憶體中的 chat session，讓它重建
        if session_id in user_managers:
            del user_managers[session_id]

    # 取得該 session 專屬的 manager
    mgr = _get_or_create_manager(session_id=req.session_id)

    # 如果 manager 沒有 chat（general_chat_sessions 可能過期），從 conversation_logs 重建
    if req.session_id and not (hasattr(mgr, 'current_store') and mgr.current_store):
        remaining_logs = conversation_logger.get_session_logs(session_id)
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
        if prompt_manager:
            active_prompt = prompt_manager.get_active_prompt(store_name)
            if active_prompt:
                system_instruction = active_prompt.content

        model_name = os.getenv("GEMINI_MODEL_NAME", "gemini-2.5-flash")
        history_contents = FileSearchManager._build_history_contents(history)
        mgr.start_chat(store_name, model_name, system_instruction=system_instruction, history=history_contents)

        if general_session_manager:
            general_session_manager.create_session(
                session_id=session_id, store_name=store_name,
                model=model_name, system_instruction=system_instruction,
            )
            for h in history:
                general_session_manager.add_message(session_id, h["role"], h["content"])

        print(f"[Session] 從 conversation_logs 重建: {session_id[:8]}... (歷史 {len(history)} 則)")

    current_store = mgr.current_store if hasattr(mgr, 'current_store') else 'unknown'

    try:
        response = mgr.send_message(req.message)
        answer = response.text or ""

        # 清除 Gemini File Search 的 citation 標記
        answer = re.sub(r'\s*\[cite:\s*[^\]]*\]', '', answer).strip()

        # 持久化對話到 MongoDB
        if general_session_manager and session_id:
            general_session_manager.add_message(session_id, "user", req.message)
            general_session_manager.add_message(session_id, "model", answer)

        # 記錄對話日誌
        log_result = conversation_logger.log_conversation(
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
        conversation_logger.log_conversation(
            session_id=session_id,
            user_message=req.message,
            agent_response="",
            tool_calls=[],
            session_state={"store": current_store},
            error=str(e),
            mode="general"
        )
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/api/chat/conversations/{session_id}", response_model=jti.DeleteConversationResponse)
@app.delete("/api/chat/history/{session_id}", response_model=jti.DeleteConversationResponse)
def delete_general_conversation(session_id: str, auth: dict = Depends(verify_auth)):
    """刪除指定 session 的對話紀錄

    同時刪除：
    - 對話日誌 (conversation logs)
    - General chat session (MongoDB)
    - 記憶體中的 session manager
    """

    deleted_logs = conversation_logger.delete_session_logs(session_id)

    deleted_session = False
    if general_session_manager:
        deleted_session = general_session_manager.delete_session(session_id)

    # 清除記憶體中的 manager
    if session_id in user_managers:
        del user_managers[session_id]

    return {
        "ok": True,
        "deleted_logs": deleted_logs,
        "deleted_session": deleted_session,
    }

@app.get(
    "/api/chat/conversations",
    response_model=jti.GeneralConversationsResponse,
    response_model_exclude_none=True,
)
@app.get(
    "/api/chat/history",
    response_model=jti.GeneralConversationsResponse,
    response_model_exclude_none=True,
)
def get_general_conversations(
    store_name: Optional[str] = None,
    auth: dict = Depends(verify_auth),
):
    """
    取得 general chat 的對話歷史（session 列表）

    Query Parameters:
    - store_name: 知識庫名稱（必填）

    回傳該知識庫的所有對話（按 session 分組，含摘要）
    """
    try:
        mgr = _get_or_create_manager()

        # 決定使用哪個 store
        current_store = store_name if store_name else (mgr.current_store if hasattr(mgr, 'current_store') else None)

        if not current_store:
            raise HTTPException(status_code=400, detail="未指定知識庫或當前無活動知識庫")

        # 取得所有 general 模式的對話
        all_conversations = conversation_logger.get_session_logs_by_mode("general")

        # 篩選出屬於這個知識庫的對話
        store_conversations = [
            c for c in all_conversations
            if c.get("session_snapshot", {}).get("store") == current_store
        ]

        session_list = group_conversations_as_summary(store_conversations)

        return {
            "store_name": current_store,
            "mode": "general",
            "sessions": session_list,
            "total_conversations": len(store_conversations),
            "total_sessions": len(session_list)
        }

    except Exception as e:
        logging.error(f"Failed to get general conversations: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get(
    "/api/chat/conversations/export",
    response_model=jti.ExportGeneralConversationsResponse,
    response_model_exclude_none=True,
)
@app.get(
    "/api/chat/history/export",
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
        mgr = _get_or_create_manager()

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
                conversations = conversation_logger.get_session_logs(session_id)
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
            all_conversations = conversation_logger.get_session_logs_by_mode("general")

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

@app.get(
    "/api/chat/conversations/{session_id}",
    response_model=jti.GeneralConversationsBySessionResponse,
    response_model_exclude_none=True,
)
@app.get(
    "/api/chat/history/{session_id}",
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
        conversations = conversation_logger.get_session_logs(session_id)
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


# ========== OpenAI Compatible API ==========

class OpenAIChatMessage(BaseModel):
    role: str
    content: str

# 支援的 Gemini 模型
SUPPORTED_MODELS = ["gemini-2.5-flash", "gemini-3-flash-preview", "gemini-3-pro-preview"]
DEFAULT_MODEL = os.getenv("GEMINI_MODEL_NAME", "gemini-2.5-flash")

class OpenAIChatRequest(BaseModel):
    model: str = DEFAULT_MODEL
    messages: list[OpenAIChatMessage]
    temperature: float | None = None
    max_tokens: int | None = None
    stream: bool = False

class OpenAIChatChoice(BaseModel):
    index: int
    message: OpenAIChatMessage
    finish_reason: str

class OpenAIChatResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: list[OpenAIChatChoice]
    usage: dict


def _get_system_prompt(api_key_info, store_name: str, messages: list) -> Optional[str]:
    """
    根據優先順序決定使用哪個 system prompt:
    1. Request 帶的 system message → 最優先
    2. API Key 指定的 prompt_index → 次之
    3. 知識庫的預設 (active_prompt_id) → 兜底
    4. 都沒有 → None
    """
    # 1. 檢查 request 中的 system message
    system_messages = [msg for msg in messages if msg.role == "system"]
    if system_messages:
        return system_messages[-1].content

    if not prompt_manager:
        return None

    # 2. 檢查 API Key 指定的 prompt_index
    if api_key_info and api_key_info.prompt_index is not None:
        prompts = prompt_manager.list_prompts(store_name)
        if 0 <= api_key_info.prompt_index < len(prompts):
            return prompts[api_key_info.prompt_index].content

    # 3. 使用知識庫預設的 active prompt
    active_prompt = prompt_manager.get_active_prompt(store_name)
    if active_prompt:
        return active_prompt.content

    return None


@app.post("/v1/chat/completions")
async def openai_chat_completions(request: OpenAIChatRequest, raw_request: Request, auth: dict = Depends(verify_auth)):
    """
    OpenAI 兼容的 Chat Completions API

    使用 Authorization: Bearer sk-xxx 驗證，API Key 綁定知識庫
    也接受 Admin Key（需在 request 的 messages 中指定 store，或使用預設知識庫）

    Prompt 優先順序:
    1. Request 帶的 system message
    2. API Key 指定的 prompt_index
    3. 知識庫的預設 prompt
    """
    if not manager:
        raise HTTPException(status_code=500, detail="未設定 Gemini API Key")

    # 決定 store_name 和 api_key_info
    api_key_info = None
    if auth["role"] == "admin":
        # Admin 使用預設中文知識庫（或可從 system message 解析）
        store_name = os.getenv("GEMINI_FILE_SEARCH_STORE_ID_ZH") or os.getenv("GEMINI_FILE_SEARCH_STORE_ID", "")
        if not store_name:
            raise HTTPException(status_code=400, detail="未設定知識庫，請配置 GEMINI_FILE_SEARCH_STORE_ID_ZH")
    else:
        # 一般 key → 從 auth 取得綁定的 store
        if not api_key_manager:
            raise HTTPException(status_code=500, detail="API Key Manager 未初始化")
        token = _extract_bearer_token(raw_request)
        api_key_info = api_key_manager.verify_key(token) if token else None
        store_name = auth["store_name"]

    # 取得最後一條用戶消息
    user_messages = [msg for msg in request.messages if msg.role == "user"]
    if not user_messages:
        raise HTTPException(status_code=400, detail="沒有找到用戶消息")

    last_message = user_messages[-1].content

    # 決定 system prompt
    system_prompt = _get_system_prompt(api_key_info, store_name, request.messages)

    # 驗證 model 並決定實際使用的模型
    warning = None
    if request.model in SUPPORTED_MODELS:
        model_name = request.model
    else:
        model_name = DEFAULT_MODEL
        warning = f"不支援的模型 '{request.model}'，已改用預設模型 '{DEFAULT_MODEL}'。支援的模型: {', '.join(SUPPORTED_MODELS)}"

    try:
        # 使用 query 進行單次 RAG 查詢（不依賴 session）
        response = manager.query(store_name, last_message, system_instruction=system_prompt, model=model_name)

        # 如果有警告，附加到回覆開頭
        answer_text = response.text
        # 清除 Gemini File Search 的 citation 標記
        answer_text = re.sub(r'\s*\[cite:\s*[^\]]*\]', '', answer_text).strip()
        if warning:
            answer_text = f"⚠️ {warning}\n\n{answer_text}"

        result = OpenAIChatResponse(
            id=f"chatcmpl-{uuid.uuid4().hex[:8]}",
            created=int(time.time()),
            model=model_name,  # 返回實際使用的模型
            choices=[
                OpenAIChatChoice(
                    index=0,
                    message=OpenAIChatMessage(
                        role="assistant",
                        content=answer_text
                    ),
                    finish_reason="stop"
                )
            ],
            usage={
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0
            }
        )

        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ========== Prompt Management API ==========

class CreatePromptRequest(BaseModel):
    name: str
    content: str

class UpdatePromptRequest(BaseModel):
    name: Optional[str] = None
    content: Optional[str] = None

class SetActivePromptRequest(BaseModel):
    prompt_id: Optional[str] = None


@app.get("/api/stores/{store_name:path}/prompts")
def list_store_prompts(store_name: str, auth: dict = Depends(verify_auth)):
    """列出 Store 的所有 Prompts（Admin only）"""
    require_admin(auth)
    if not prompt_manager:
        raise HTTPException(status_code=500, detail="Prompt Manager 未初始化")
    
    prompts = prompt_manager.list_prompts(store_name)
    active_prompt = prompt_manager.get_active_prompt(store_name)
    
    return {
        "prompts": [p.model_dump() for p in prompts],
        "active_prompt_id": active_prompt.id if active_prompt else None,
        "max_prompts": prompt_manager.MAX_PROMPTS_PER_STORE
    }


@app.post("/api/stores/{store_name:path}/prompts")
def create_store_prompt(store_name: str, request: CreatePromptRequest, auth: dict = Depends(verify_auth)):
    """建立新的 Prompt（Admin only）"""
    require_admin(auth)
    if not prompt_manager:
        raise HTTPException(status_code=500, detail="Prompt Manager 未初始化")
    
    try:
        prompt = prompt_manager.create_prompt(
            store_name=store_name,
            name=request.name,
            content=request.content
        )
        return prompt.model_dump()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/stores/{store_name:path}/prompts/{prompt_id}")
def get_store_prompt(store_name: str, prompt_id: str, auth: dict = Depends(verify_auth)):
    """取得特定 Prompt（Admin only）"""
    require_admin(auth)
    if not prompt_manager:
        raise HTTPException(status_code=500, detail="Prompt Manager 未初始化")
    
    prompt = prompt_manager.get_prompt(store_name, prompt_id)
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt 不存在")
    
    return prompt.model_dump()


@app.put("/api/stores/{store_name:path}/prompts/{prompt_id}")
def update_store_prompt(store_name: str, prompt_id: str, request: UpdatePromptRequest, auth: dict = Depends(verify_auth)):
    """更新 Prompt（Admin only）"""
    require_admin(auth)
    if not prompt_manager:
        raise HTTPException(status_code=500, detail="Prompt Manager 未初始化")
    
    try:
        prompt = prompt_manager.update_prompt(
            store_name=store_name,
            prompt_id=prompt_id,
            name=request.name,
            content=request.content
        )
        return prompt.model_dump()
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.delete("/api/stores/{store_name:path}/prompts/{prompt_id}")
def delete_store_prompt(store_name: str, prompt_id: str, auth: dict = Depends(verify_auth)):
    """刪除 Prompt（Admin only）"""
    require_admin(auth)
    if not prompt_manager:
        raise HTTPException(status_code=500, detail="Prompt Manager 未初始化")
    
    try:
        prompt_manager.delete_prompt(store_name, prompt_id)
        return {"message": "Prompt 已刪除"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/api/stores/{store_name:path}/prompts/active")
def set_active_store_prompt(store_name: str, request: SetActivePromptRequest, auth: dict = Depends(verify_auth)):
    """設定啟用的 Prompt（Admin only）"""
    require_admin(auth)
    if not prompt_manager:
        raise HTTPException(status_code=500, detail="Prompt Manager 未初始化")
    
    try:
        if request.prompt_id:
            prompt_manager.set_active_prompt(store_name, request.prompt_id)
            return {"message": "已設定啟用的 Prompt", "prompt_id": request.prompt_id}
        else:
            prompt_manager.clear_active_prompt(store_name)
            return {"message": "已取消啟用 Prompt", "prompt_id": None}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/api/stores/{store_name:path}/prompts/active")
def get_active_store_prompt(store_name: str, auth: dict = Depends(verify_auth)):
    """取得當前啟用的 Prompt（Admin only）"""
    require_admin(auth)
    if not prompt_manager:
        raise HTTPException(status_code=500, detail="Prompt Manager 未初始化")
    
    prompt = prompt_manager.get_active_prompt(store_name)
    if not prompt:
        return {"message": "尚未設定啟用的 Prompt", "prompt": None}
    
    return {"prompt": prompt.model_dump()}


@app.delete("/api/stores/{store_name:path}")
def delete_store(store_name: str, auth: dict = Depends(verify_auth)):
    """刪除 Store。（Admin only）"""
    require_admin(auth)
    mgr = _get_or_create_manager()
    mgr.delete_store(store_name)
    return {"ok": True}


# ========== API Key Management ==========

class CreateAPIKeyRequest(BaseModel):
    name: str  # 用途說明
    store_name: str  # 綁定的知識庫
    prompt_index: Optional[int] = None  # 可選指定 prompt


class UpdateAPIKeyRequest(BaseModel):
    name: Optional[str] = None
    prompt_index: Optional[int] = None


@app.get("/api/keys")
def list_api_keys(store_name: Optional[str] = None, auth: dict = Depends(verify_auth)):
    """列出 API Keys，可選篩選特定知識庫（Admin only）"""
    require_admin(auth)
    if not api_key_manager:
        raise HTTPException(status_code=500, detail="API Key Manager 未初始化")

    keys = api_key_manager.list_keys(store_name)
    # 不返回 key_hash
    return [
        {
            "id": k.id,
            "key_prefix": k.key_prefix,
            "name": k.name,
            "store_name": k.store_name,
            "prompt_index": k.prompt_index,
            "created_at": k.created_at,
            "last_used_at": k.last_used_at
        }
        for k in keys
    ]


@app.post("/api/keys")
def create_api_key(request: CreateAPIKeyRequest, auth: dict = Depends(verify_auth)):
    """建立新的 API Key（Admin only）"""
    require_admin(auth)
    if not api_key_manager:
        raise HTTPException(status_code=500, detail="API Key Manager 未初始化")

    api_key, raw_key = api_key_manager.create_key(
        name=request.name,
        store_name=request.store_name,
        prompt_index=request.prompt_index
    )

    return {
        "id": api_key.id,
        "key": raw_key,  # 只有這一次會顯示完整 key
        "key_prefix": api_key.key_prefix,
        "name": api_key.name,
        "store_name": api_key.store_name,
        "prompt_index": api_key.prompt_index,
        "message": "請妥善保存此 API Key，之後無法再次查看完整金鑰"
    }


@app.get("/api/keys/{key_id}")
def get_api_key(key_id: str, auth: dict = Depends(verify_auth)):
    """取得 API Key 資訊（Admin only）"""
    require_admin(auth)
    if not api_key_manager:
        raise HTTPException(status_code=500, detail="API Key Manager 未初始化")

    key = api_key_manager.get_key(key_id)
    if not key:
        raise HTTPException(status_code=404, detail="API Key 不存在")

    return {
        "id": key.id,
        "key_prefix": key.key_prefix,
        "name": key.name,
        "store_name": key.store_name,
        "prompt_index": key.prompt_index,
        "created_at": key.created_at,
        "last_used_at": key.last_used_at
    }


@app.put("/api/keys/{key_id}")
def update_api_key(key_id: str, request: UpdateAPIKeyRequest, auth: dict = Depends(verify_auth)):
    """更新 API Key 設定（Admin only）"""
    require_admin(auth)
    if not api_key_manager:
        raise HTTPException(status_code=500, detail="API Key Manager 未初始化")

    key = api_key_manager.update_key(
        key_id=key_id,
        name=request.name,
        prompt_index=request.prompt_index
    )

    if not key:
        raise HTTPException(status_code=404, detail="API Key 不存在")

    return {
        "id": key.id,
        "key_prefix": key.key_prefix,
        "name": key.name,
        "store_name": key.store_name,
        "prompt_index": key.prompt_index
    }


@app.delete("/api/keys/{key_id}")
def delete_api_key(key_id: str, auth: dict = Depends(verify_auth)):
    """刪除 API Key（Admin only）"""
    require_admin(auth)
    if not api_key_manager:
        raise HTTPException(status_code=500, detail="API Key Manager 未初始化")

    success = api_key_manager.delete_key(key_id)
    if not success:
        raise HTTPException(status_code=404, detail="API Key 不存在")

    return {"message": "API Key 已刪除"}


@app.get("/health")
def health_check():
    """服務健康檢查（不需認證）"""
    checks = {}

    # 1. MongoDB
    try:
        mongo = get_mongo_client()
        checks["mongodb"] = mongo.health_check()
    except Exception:
        checks["mongodb"] = False

    # 2. Gemini API Key
    checks["gemini_api_key"] = bool(os.getenv("GEMINI_API_KEY"))

    # 3. FileSearchManager
    checks["file_search_manager"] = manager is not None

    # 4. API Key Manager
    checks["api_key_manager"] = api_key_manager is not None

    # 5. General Session Manager (MongoDB persistence)
    checks["general_session_manager"] = general_session_manager is not None

    all_ok = all(checks.values())
    status_code = 200 if all_ok else 503

    return JSONResponse(
        status_code=status_code,
        content={
            "status": "ok" if all_ok else "degraded",
            "checks": checks,
        },
    )


@app.get("/")
def index():
    """API 入口。"""
    return {"message": "Gemini File Search API", "docs": "/docs"}


# 引入色彩測驗路由
app.include_router(jti.router)

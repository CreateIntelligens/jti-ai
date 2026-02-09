"""
Gemini File Search FastAPI 後端
"""

import logging
import traceback
import os
import shutil
import uuid
import warnings
from pathlib import Path
from typing import Optional

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
        from datetime import datetime
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

from fastapi import FastAPI, File, HTTPException, UploadFile, Request, Header as FastAPIHeader
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from google.genai.errors import ClientError
from typing import Dict
import hashlib

from .core import FileSearchManager
from .api_keys import APIKeyManager
from .routers import jti
from .services.session_manager_factory import get_conversation_logger

# 使用工廠函數取得適當的實作（MongoDB 或檔案系統）
conversation_logger = get_conversation_logger()

app = FastAPI(title="Gemini File Search API")

@app.exception_handler(ClientError)
async def gemini_client_error_handler(request: Request, exc: ClientError):
    """處理 Google GenAI Client 錯誤 (例如 429 配額不足)。"""
    error_msg = str(exc)
    print(f"[Gemini API Error] {error_msg}")  # 打印完整錯誤

    status_code = 500
    detail = "Google API Error"

    if "RESOURCE_EXHAUSTED" in error_msg or "429" in error_msg:
        status_code = 429
        detail = "目前使用量已達上限 (429)，請稍後再試。"
    else:
        detail = error_msg
        status_code = 400

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
# Session managers: {session_id: FileSearchManager}
user_managers: Dict[str, FileSearchManager] = {}


@app.on_event("startup")
def startup():
    """應用程式啟動時初始化 Manager。"""
    global manager, prompt_manager, api_key_manager
    try:
        manager = FileSearchManager()
        from .prompts import PromptManager
        prompt_manager = PromptManager()
        api_key_manager = APIKeyManager()
    except ValueError as e:
        print(f"警告: {e}")


def _get_or_create_manager(user_api_key: Optional[str] = None) -> FileSearchManager:
    """根據使用者提供的 API Key 取得或建立 Manager"""
    if not user_api_key:
        # 沒有提供 API Key，使用預設的全域 manager
        if not manager:
            raise HTTPException(status_code=500, detail="未設定 API Key")
        return manager
    
    # 使用 API Key 的 hash 作為 session ID
    session_id = hashlib.sha256(user_api_key.encode()).hexdigest()
    
    if session_id not in user_managers:
        try:
            user_managers[session_id] = FileSearchManager(api_key=user_api_key)
            print(f"[Session] 建立新的使用者 Manager: {session_id[:8]}...")
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"無效的 API Key: {e}")
    
    return user_managers[session_id]


class CreateStoreRequest(BaseModel):
    display_name: str


class QueryRequest(BaseModel):
    store_name: str
    question: str


class ChatStartRequest(BaseModel):
    store_name: str
    model: str = os.getenv("GEMINI_MODEL_NAME", "gemini-2.5-flash-lite")


class ChatMessageRequest(BaseModel):
    message: str


@app.get("/api/stores")
def list_stores(x_gemini_api_key: Optional[str] = FastAPIHeader(None)):
    """列出所有 Store。"""
    mgr = _get_or_create_manager(x_gemini_api_key)
    stores = mgr.list_stores()
    return [{"name": s.name, "display_name": s.display_name} for s in stores]


@app.post("/api/stores")
def create_store(req: CreateStoreRequest, x_gemini_api_key: Optional[str] = FastAPIHeader(None)):
    """建立新 Store。"""
    mgr = _get_or_create_manager(x_gemini_api_key)
    store_name = mgr.create_store(req.display_name)
    return {"name": store_name}


@app.get("/api/stores/{store_name:path}/files")
def list_files(store_name: str, x_gemini_api_key: Optional[str] = FastAPIHeader(None)):
    """列出 Store 中的檔案。"""
    mgr = _get_or_create_manager(x_gemini_api_key)
    files = mgr.list_files(store_name)
    return [{"name": f.name, "display_name": f.display_name} for f in files]


import traceback

# ... imports ...

@app.delete("/api/files/{file_name:path}")
def delete_file(file_name: str, x_gemini_api_key: Optional[str] = FastAPIHeader(None)):
    """刪除檔案。"""
    mgr = _get_or_create_manager(x_gemini_api_key)
    try:
        print(f"嘗試刪除檔案: {file_name}")
        mgr.delete_file(file_name)
        return {"ok": True}
    except Exception as e:
        traceback.print_exc()  # Print full traceback to logs
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/stores/{store_name:path}/upload")
async def upload_file(store_name: str, file: UploadFile = File(...), x_gemini_api_key: Optional[str] = FastAPIHeader(None)):
    """上傳檔案到 Store。"""
    mgr = _get_or_create_manager(x_gemini_api_key)

    temp_dir = Path("/tmp/gemini-upload")
    temp_dir.mkdir(exist_ok=True)
    # 使用 UUID + 副檔名，讓 SDK 能偵測 MIME type
    ext = Path(file.filename).suffix if file.filename else ""
    safe_filename = f"{uuid.uuid4()}{ext}"
    temp_path = temp_dir / safe_filename

    with open(temp_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    try:
        # 故意不傳入 file.content_type，讓 core.py 根據副檔名自己判斷正確的 MIME Type
        # 這樣可以避免瀏覽器傳送錯誤的 MIME Type (例如 xlsx 被當成 application/octet-stream)
        result = mgr.upload_file(
            store_name, str(temp_path), file.filename, mime_type=None
        )
        return {"name": result}
    finally:
        temp_path.unlink(missing_ok=True)


@app.post("/api/query")
def query(req: QueryRequest, x_gemini_api_key: Optional[str] = FastAPIHeader(None)):
    """查詢 Store (單次)。"""
    mgr = _get_or_create_manager(x_gemini_api_key)
    response = mgr.query(req.store_name, req.question)
    return {"answer": response.text}


@app.post("/api/chat/start")
def start_chat(req: ChatStartRequest, x_gemini_api_key: Optional[str] = FastAPIHeader(None)):
    """開始新的對話 Session。"""
    mgr = _get_or_create_manager(x_gemini_api_key)

    # 取得 session_id：結合 API key 和 store_name 以隔離不同知識庫的對話
    api_key_part = x_gemini_api_key if x_gemini_api_key else 'system'
    session_key = f"{api_key_part}:{req.store_name}"
    session_id = hashlib.sha256(session_key.encode()).hexdigest()

    # 取得啟用的 prompt (如果有)
    system_instruction = None
    if prompt_manager:
        active_prompt = prompt_manager.get_active_prompt(req.store_name)
        if active_prompt:
            system_instruction = active_prompt.content
            print(f"[DEBUG] 從 MongoDB 載入 Prompt: {active_prompt.name}")
        else:
            print(f"[DEBUG] Store {req.store_name} 沒有啟用的 Prompt")

    mgr.start_chat(req.store_name, req.model, system_instruction=system_instruction)
    return {
        "ok": True,
        "prompt_applied": system_instruction is not None,
        "session_id": session_id
    }

@app.post("/api/chat/message")
def send_message(req: ChatMessageRequest, x_gemini_api_key: Optional[str] = FastAPIHeader(None)):
    """發送訊息到目前對話。"""
    mgr = _get_or_create_manager(x_gemini_api_key)

    # 取得 session_id：結合 API key 和當前 store_name
    api_key_part = x_gemini_api_key if x_gemini_api_key else 'system'
    current_store = mgr.current_store if hasattr(mgr, 'current_store') else 'unknown'
    session_key = f"{api_key_part}:{current_store}"
    session_id = hashlib.sha256(session_key.encode()).hexdigest()

    try:
        response = mgr.send_message(req.message)
        answer = response.text

        # 記錄對話
        conversation_logger.log_conversation(
            session_id=session_id,
            user_message=req.message,
            agent_response=answer,
            tool_calls=[],
            session_state={"store": current_store},
            mode="general"
        )

        return {"answer": answer}
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


@app.get("/api/chat/history")
def get_history(x_gemini_api_key: Optional[str] = FastAPIHeader(None)):
    """取得目前對話紀錄。"""
    mgr = _get_or_create_manager(x_gemini_api_key)
    return mgr.get_history()


@app.get("/api/chat/conversations")
def get_general_conversations(
    store_name: Optional[str] = None,
    x_gemini_api_key: Optional[str] = FastAPIHeader(None)
):
    """
    取得 general chat 的對話歷史

    Query Parameters:
    - store_name: 知識庫名稱（必填）

    回傳該知識庫的所有對話（按 session 分組）
    """
    try:
        mgr = _get_or_create_manager(x_gemini_api_key)

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

        # 按 session_id 分組
        sessions = {}
        for conv in store_conversations:
            sid = conv.get("session_id")
            if sid not in sessions:
                sessions[sid] = {
                    "session_id": sid,
                    "conversations": [],
                    "first_message_time": conv.get("timestamp"),
                    "total": 0
                }
            sessions[sid]["conversations"].append(conv)
            sessions[sid]["total"] += 1

        # 轉換成列表，按時間排序
        session_list = list(sessions.values())
        session_list.sort(key=lambda x: x["first_message_time"], reverse=True)

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


@app.get("/api/chat/conversations/export")
def export_general_conversations(
    store_name: Optional[str] = None,
    session_ids: Optional[str] = None,
    x_gemini_api_key: Optional[str] = FastAPIHeader(None)
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
        from datetime import datetime

        mgr = _get_or_create_manager(x_gemini_api_key)

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

            # 按 session_id 分組
            sessions = {}
            for conv in store_conversations:
                sid = conv.get("session_id")
                if sid not in sessions:
                    sessions[sid] = {
                        "session_id": sid,
                        "conversations": [],
                        "first_message_time": conv.get("timestamp"),
                        "total": 0
                    }
                sessions[sid]["conversations"].append(conv)
                sessions[sid]["total"] += 1

            # 轉換成列表，按時間排序
            session_list = list(sessions.values())
            session_list.sort(key=lambda x: x["first_message_time"], reverse=True)

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


# ========== OpenAI Compatible API ==========

class OpenAIChatMessage(BaseModel):
    role: str
    content: str

# 支援的 Gemini 模型
SUPPORTED_MODELS = ["gemini-2.5-flash-lite", "gemini-3-flash-preview", "gemini-3-pro-preview"]
DEFAULT_MODEL = os.getenv("GEMINI_MODEL_NAME", "gemini-2.5-flash-lite")

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


def _extract_bearer_token(request: Request) -> Optional[str]:
    """從 Authorization header 提取 Bearer token"""
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:]
    return None


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
async def openai_chat_completions(request: OpenAIChatRequest, raw_request: Request):
    """
    OpenAI 兼容的 Chat Completions API

    使用 Authorization: Bearer sk-xxx 驗證，API Key 綁定知識庫

    Prompt 優先順序:
    1. Request 帶的 system message
    2. API Key 指定的 prompt_index
    3. 知識庫的預設 prompt
    """
    if not manager:
        raise HTTPException(status_code=500, detail="未設定 Gemini API Key")

    if not api_key_manager:
        raise HTTPException(status_code=500, detail="API Key Manager 未初始化")

    # 驗證 API Key
    token = _extract_bearer_token(raw_request)
    if not token:
        raise HTTPException(status_code=401, detail="缺少 Authorization header")

    api_key_info = api_key_manager.verify_key(token)
    if not api_key_info:
        raise HTTPException(status_code=401, detail="無效的 API Key")

    store_name = api_key_info.store_name

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
        if warning:
            answer_text = f"⚠️ {warning}\n\n{answer_text}"

        import time
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
    prompt_id: str


@app.get("/api/stores/{store_name:path}/prompts")
def list_store_prompts(store_name: str):
    """列出 Store 的所有 Prompts"""
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
def create_store_prompt(store_name: str, request: CreatePromptRequest):
    """建立新的 Prompt"""
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
def get_store_prompt(store_name: str, prompt_id: str):
    """取得特定 Prompt"""
    if not prompt_manager:
        raise HTTPException(status_code=500, detail="Prompt Manager 未初始化")
    
    prompt = prompt_manager.get_prompt(store_name, prompt_id)
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt 不存在")
    
    return prompt.model_dump()


@app.put("/api/stores/{store_name:path}/prompts/{prompt_id}")
def update_store_prompt(store_name: str, prompt_id: str, request: UpdatePromptRequest):
    """更新 Prompt"""
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
def delete_store_prompt(store_name: str, prompt_id: str):
    """刪除 Prompt"""
    if not prompt_manager:
        raise HTTPException(status_code=500, detail="Prompt Manager 未初始化")
    
    try:
        prompt_manager.delete_prompt(store_name, prompt_id)
        return {"message": "Prompt 已刪除"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/api/stores/{store_name:path}/prompts/active")
def set_active_store_prompt(store_name: str, request: SetActivePromptRequest):
    """設定啟用的 Prompt"""
    if not prompt_manager:
        raise HTTPException(status_code=500, detail="Prompt Manager 未初始化")
    
    try:
        prompt_manager.set_active_prompt(store_name, request.prompt_id)
        return {"message": "已設定啟用的 Prompt", "prompt_id": request.prompt_id}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/api/stores/{store_name:path}/prompts/active")
def get_active_store_prompt(store_name: str):
    """取得當前啟用的 Prompt"""
    if not prompt_manager:
        raise HTTPException(status_code=500, detail="Prompt Manager 未初始化")
    
    prompt = prompt_manager.get_active_prompt(store_name)
    if not prompt:
        return {"message": "尚未設定啟用的 Prompt", "prompt": None}
    
    return {"prompt": prompt.model_dump()}


@app.delete("/api/stores/{store_name:path}")
def delete_store(store_name: str, x_gemini_api_key: Optional[str] = FastAPIHeader(None)):
    """刪除 Store。"""
    mgr = _get_or_create_manager(x_gemini_api_key)
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
def list_api_keys(store_name: Optional[str] = None):
    """列出 API Keys，可選篩選特定知識庫"""
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
def create_api_key(request: CreateAPIKeyRequest):
    """建立新的 API Key"""
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
def get_api_key(key_id: str):
    """取得 API Key 資訊"""
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
def update_api_key(key_id: str, request: UpdateAPIKeyRequest):
    """更新 API Key 設定"""
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
def delete_api_key(key_id: str):
    """刪除 API Key"""
    if not api_key_manager:
        raise HTTPException(status_code=500, detail="API Key Manager 未初始化")

    success = api_key_manager.delete_key(key_id)
    if not success:
        raise HTTPException(status_code=404, detail="API Key 不存在")

    return {"message": "API Key 已刪除"}


@app.get("/")
def index():
    """API 入口。"""
    return {"message": "Gemini File Search API", "docs": "/docs"}


# 引入色彩測驗路由
app.include_router(jti.router)

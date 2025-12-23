"""
Gemini File Search FastAPI 後端
"""

import logging
import traceback
import os
import shutil
import uuid
from pathlib import Path
from typing import Optional

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

from fastapi import FastAPI, File, HTTPException, UploadFile, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from google.genai.errors import ClientError

from .core import FileSearchManager

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


@app.on_event("startup")
def startup():
    """應用程式啟動時初始化 Manager。"""
    global manager, prompt_manager
    try:
        manager = FileSearchManager()
        from .prompts import PromptManager
        prompt_manager = PromptManager()
    except ValueError as e:
        print(f"警告: {e}")


class CreateStoreRequest(BaseModel):
    display_name: str


class QueryRequest(BaseModel):
    store_name: str
    question: str


class ChatStartRequest(BaseModel):
    store_name: str
    model: str = os.getenv("GEMINI_MODEL_NAME", "gemini-2.5-flash")


class ChatMessageRequest(BaseModel):
    message: str


@app.get("/api/stores")
def list_stores():
    """列出所有 Store。"""
    if not manager:
        raise HTTPException(status_code=500, detail="未設定 API Key")
    stores = manager.list_stores()
    return [{"name": s.name, "display_name": s.display_name} for s in stores]


@app.post("/api/stores")
def create_store(req: CreateStoreRequest):
    """建立新 Store。"""
    if not manager:
        raise HTTPException(status_code=500, detail="未設定 API Key")
    store_name = manager.create_store(req.display_name)
    return {"name": store_name}


@app.get("/api/stores/{store_name:path}/files")
def list_files(store_name: str):
    """列出 Store 中的檔案。"""
    if not manager:
        raise HTTPException(status_code=500, detail="未設定 API Key")
    files = manager.list_files(store_name)
    return [{"name": f.name, "display_name": f.display_name} for f in files]


import traceback

# ... imports ...

@app.delete("/api/files/{file_name:path}")
def delete_file(file_name: str):
    """刪除檔案。"""
    if not manager:
        raise HTTPException(status_code=500, detail="未設定 API Key")
    try:
        print(f"嘗試刪除檔案: {file_name}")
        manager.delete_file(file_name)
        return {"ok": True}
    except Exception as e:
        traceback.print_exc()  # Print full traceback to logs
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/stores/{store_name:path}/upload")
async def upload_file(store_name: str, file: UploadFile = File(...)):
    """上傳檔案到 Store。"""
    if not manager:
        raise HTTPException(status_code=500, detail="未設定 API Key")

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
        result = manager.upload_file(
            store_name, str(temp_path), file.filename, mime_type=None
        )
        return {"name": result}
    finally:
        temp_path.unlink(missing_ok=True)


@app.post("/api/query")
def query(req: QueryRequest):
    """查詢 Store (單次)。"""
    if not manager:
        raise HTTPException(status_code=500, detail="未設定 API Key")
    response = manager.query(req.store_name, req.question)
    return {"answer": response.text}


@app.post("/api/chat/start")
def start_chat(req: ChatStartRequest):
    """開始新的對話 Session。"""
    if not manager:
        raise HTTPException(status_code=500, detail="未設定 API Key")
    
    # 取得啟用的 prompt (如果有)
    system_instruction = None
    if prompt_manager:
        active_prompt = prompt_manager.get_active_prompt(req.store_name)
        if active_prompt:
            system_instruction = active_prompt.content
            print(f"[DEBUG] 從 MongoDB 載入 Prompt: {active_prompt.name}")
        else:
            print(f"[DEBUG] Store {req.store_name} 沒有啟用的 Prompt")
    
    manager.start_chat(req.store_name, req.model, system_instruction=system_instruction)
    return {"ok": True, "prompt_applied": system_instruction is not None}

@app.post("/api/chat/message")
def send_message(req: ChatMessageRequest):
    """發送訊息到目前對話。"""
    if not manager:
        raise HTTPException(status_code=500, detail="未設定 API Key")
    try:
        response = manager.send_message(req.message)
        return {"answer": response.text}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/chat/history")
def get_history():
    """取得目前對話紀錄。"""
    if not manager:
        raise HTTPException(status_code=500, detail="未設定 API Key")
    return manager.get_history()


# ========== OpenAI Compatible API ==========

class OpenAIChatMessage(BaseModel):
    role: str
    content: str

class OpenAIChatRequest(BaseModel):
    model: str = "gemini-2.0-flash-exp"
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


@app.post("/v1/chat/completions")
async def openai_chat_completions(request: OpenAIChatRequest):
    """
    OpenAI 兼容的 Chat Completions API
    使用當前 session 的知識庫進行 RAG 查詢
    """
    if not manager:
        raise HTTPException(status_code=500, detail="未設定 API Key")
    
    if not manager.current_store:
        raise HTTPException(status_code=400, detail="請先選擇知識庫 (使用 /api/chat/start)")
    
    # 取得最後一條用戶消息
    user_messages = [msg for msg in request.messages if msg.role == "user"]
    if not user_messages:
        raise HTTPException(status_code=400, detail="沒有找到用戶消息")
    
    last_message = user_messages[-1].content
    
    try:
        # 使用現有的 chat 功能
        result = manager.chat(last_message)
        
        import time
        response = OpenAIChatResponse(
            id=f"chatcmpl-{uuid.uuid4().hex[:8]}",
            created=int(time.time()),
            model=request.model,
            choices=[
                OpenAIChatChoice(
                    index=0,
                    message=OpenAIChatMessage(
                        role="assistant",
                        content=result["answer"]
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
        
        return response
        
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
def delete_store(store_name: str):
    """刪除 Store。"""
    if not manager:
        raise HTTPException(status_code=500, detail="未設定 API Key")
    manager.delete_store(store_name)
    return {"ok": True}


@app.get("/")
def index():
    """API 入口。"""
    return {"message": "Gemini File Search API", "docs": "/docs"}

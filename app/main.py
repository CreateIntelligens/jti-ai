"""
Gemini File Search FastAPI 後端
"""

import logging
import traceback
import os
import shutil
import uuid
from pathlib import Path

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
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
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


@app.on_event("startup")
def startup():
    """應用程式啟動時初始化 Manager。"""
    global manager
    try:
        manager = FileSearchManager()
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


@app.delete("/api/stores/{store_name:path}")
def delete_store(store_name: str):
    """刪除 Store。"""
    if not manager:
        raise HTTPException(status_code=500, detail="未設定 API Key")
    manager.delete_store(store_name)
    return {"ok": True}


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
    manager.start_chat(req.store_name, req.model)
    return {"ok": True}


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


# 靜態檔案
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/")
def index():
    """首頁。"""
    index_file = static_dir / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return {"message": "Gemini File Search API", "docs": "/docs"}

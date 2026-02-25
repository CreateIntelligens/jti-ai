"""
Gemini File Search FastAPI 後端
"""

import logging
import os
import re
import uuid
import warnings
import time
from datetime import datetime
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

from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from google.genai.errors import ClientError

from .auth import verify_auth, _extract_bearer_token
from .routers import jti, jti_prompts
from .routers import chat, stores, prompts, api_keys
from .services.mongo_client import get_mongo_client
import app.deps as deps

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


@app.on_event("startup")
def startup():
    """應用程式啟動時初始化 Manager。"""
    deps.init_managers()


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

    if not deps.prompt_manager:
        return None

    # 2. 檢查 API Key 指定的 prompt_index
    if api_key_info and api_key_info.prompt_index is not None:
        prompts = deps.prompt_manager.list_prompts(store_name)
        if 0 <= api_key_info.prompt_index < len(prompts):
            return prompts[api_key_info.prompt_index].content

    # 3. 使用知識庫預設的 active prompt
    active_prompt = deps.prompt_manager.get_active_prompt(store_name)
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
    if not deps.manager:
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
        if not deps.api_key_manager:
            raise HTTPException(status_code=500, detail="API Key Manager 未初始化")
        token = _extract_bearer_token(raw_request)
        api_key_info = deps.api_key_manager.verify_key(token) if token else None
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
        response = deps.manager.query(store_name, last_message, system_instruction=system_prompt, model=model_name)

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


# ========== Health & Root ==========

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
    checks["file_search_manager"] = deps.manager is not None

    # 4. API Key Manager
    checks["api_key_manager"] = deps.api_key_manager is not None

    # 5. General Session Manager (MongoDB persistence)
    checks["general_session_manager"] = deps.general_session_manager is not None

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


# ========== Include Routers ==========
app.include_router(jti.router)
app.include_router(jti_prompts.router)
app.include_router(chat.router)
app.include_router(prompts.router)  # before stores (more specific path patterns)
app.include_router(stores.router)
app.include_router(api_keys.router)

"""JTAI FastAPI backend (RAG-based)."""

from contextlib import asynccontextmanager
import asyncio
import logging
import os
import time
import uuid
import warnings
from datetime import datetime
from typing import Optional

import uvicorn.logging

# ANSI color codes
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
RESET = "\033[0m"
_NOISY_LOGGERS = ("httpx", "google")
_UVICORN_LOGGERS = ("uvicorn", "uvicorn.access", "uvicorn.error")
_AFC_WARNING_PATTERNS = (".*automatic function calling.*", ".*AFC.*")

# Status code color mapping
_STATUS_COLORS: dict[str, str] = {
    "200": GREEN, "201": GREEN,
    "400": RED, "401": RED, "403": RED, "404": RED,
    "429": YELLOW,
    "500": RED, "502": RED, "503": RED,
}


class TimestampFormatter(uvicorn.logging.ColourizedFormatter):
    """Prepend timestamp to uvicorn's colorized format and colorize status codes."""

    def formatMessage(self, record):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        msg = super().formatMessage(record)

        for code, color in _STATUS_COLORS.items():
            token = f" {code}"
            if token in msg:
                msg = msg.replace(token, f" {color}{code}{RESET}")
                break

        return f"[{timestamp}] {msg}"


def _configure_app_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] %(name)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    for logger_name in _NOISY_LOGGERS:
        logging.getLogger(logger_name).setLevel(logging.WARNING)


def _configure_warning_filters() -> None:
    for message in _AFC_WARNING_PATTERNS:
        warnings.filterwarnings("ignore", message=message)


class _AccessLogNoiseFilter(logging.Filter):
    """Drop noisy access log entries: /health checks and TTS polling 202s."""

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        if "/health" in msg:
            return False
        if "/tts/tts_" in msg and " 202" in msg:
            return False
        return True


def _configure_uvicorn_logging() -> None:
    for logger_name in _UVICORN_LOGGERS:
        uvicorn_logger = logging.getLogger(logger_name)
        for handler in uvicorn_logger.handlers:
            handler.setFormatter(TimestampFormatter("%(levelprefix)s %(message)s"))
    logging.getLogger("uvicorn.access").addFilter(_AccessLogNoiseFilter())


def _configure_runtime() -> None:
    _configure_app_logging()
    _configure_warning_filters()
    _configure_uvicorn_logging()


_configure_runtime()

from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from google.genai import types
from google.genai.errors import ClientError

from .auth import verify_auth, _extract_bearer_token
from .services.agent_utils import strip_citations
from .routers.jti import chat as jti_chat, quiz as jti_quiz, prompts as jti_prompts, knowledge as jti_knowledge, quiz_bank as jti_quiz_bank
from .routers.general import chat, prompts, stores, api_keys, knowledge_admin
from .routers.hciot import chat as hciot_chat, prompts as hciot_prompts, knowledge as hciot_knowledge, images as hciot_images
from .routers.hciot import topics_admin as hciot_topics_admin
from .routers.admin_rag import router as admin_rag_router
from .services.mongo_client import get_mongo_client
import app.deps as deps

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Initialize managers and background backfill on application startup."""
    deps.init_managers()
    
    # Self-Hosted RAG: Parallel backfill
    try:
        from app.services.rag.backfill import get_backfill_service
        asyncio.create_task(_run_rag_backfill(get_backfill_service()))
    except Exception as e:
        logger.error(f"[RAG] Failed to init backfill: {e}")
        
    yield

    # Teardown: release embedding model to avoid semaphore leak warnings
    try:
        from app.services.embedding.service import EmbeddingService
        if EmbeddingService._model is not None:
            EmbeddingService._model = None
            EmbeddingService._instance = None
            logger.info("[Shutdown] Embedding model released.")
    except Exception as e:
        logger.warning(f"[Shutdown] Embedding cleanup failed: {e}")


async def _run_rag_backfill(backfill):
    """Background task to warm up embedding model and index knowledge files."""
    import time as _time
    loop = asyncio.get_running_loop()
    t0 = _time.time()
    try:
        await loop.run_in_executor(None, backfill.embedding_service.encode, "warmup")
    except Exception as e:
        logger.error("[RAG] Embedding warmup failed: %s", e)
        return

    try:
        tasks = [
            loop.run_in_executor(None, backfill.run_backfill, src, lang)
            for src in ["jti", "hciot"] for lang in ["zh", "en"]
        ]
        await asyncio.gather(*tasks)
        total = backfill.lancedb_store.get_stats().get("count", 0)
        elapsed = _time.time() - t0
        logger.info("[RAG] Ready — %d chunks indexed in %.1fs", total, elapsed)
    except Exception as e:
        logger.error("[RAG] Backfill failed: %s", e)



app = FastAPI(title="JTAI API", lifespan=lifespan)

@app.exception_handler(ClientError)
async def gemini_client_error_handler(request: Request, exc: ClientError):
    """Handle Google GenAI client errors (e.g. 429 quota exceeded)."""
    error_msg = str(exc)
    print(f"[Gemini API Error] {error_msg}")

    if "RESOURCE_EXHAUSTED" in error_msg or "429" in error_msg:
        status_code = 429
        detail = "Rate limit exceeded (429). Please try again later."
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


# ========== OpenAI Compatible API ==========

class OpenAIChatMessage(BaseModel):
    role: str
    content: str

# Supported Gemini models
SUPPORTED_MODELS = ["gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-3.1-flash-lite-preview"]
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
    """Resolve system prompt by priority: request > API key > store default."""
    # 1. System message from request (highest priority)
    system_messages = [msg for msg in messages if msg.role == "system"]
    if system_messages:
        return system_messages[-1].content

    if not deps.prompt_manager:
        return None

    # 2. Prompt index specified by API key
    if api_key_info and api_key_info.prompt_index is not None:
        prompts = deps.prompt_manager.list_prompts(store_name)
        if 0 <= api_key_info.prompt_index < len(prompts):
            return prompts[api_key_info.prompt_index].content

    # 3. Store's active prompt (fallback)
    active_prompt = deps.prompt_manager.get_active_prompt(store_name)
    if active_prompt:
        return active_prompt.content

    return None


@app.post("/v1/chat/completions")
async def openai_chat_completions(request: OpenAIChatRequest, raw_request: Request, auth: dict = Depends(verify_auth)):
    """OpenAI-compatible Chat Completions API with knowledge-base-bound API keys."""
    from app.services.rag.service import get_rag_pipeline
    from app.services.gemini_service import client as gemini_client

    if not gemini_client:
        raise HTTPException(status_code=500, detail="Gemini API key not configured")

    # Resolve store_name and api_key_info
    api_key_info = None
    if auth["role"] == "admin":
        store_name = os.getenv("JTI_STORE_ID_ZH", "")
        if not store_name:
            raise HTTPException(status_code=400, detail="Knowledge store not configured (JTI_STORE_ID_ZH)")
    else:
        if not deps.api_key_manager:
            raise HTTPException(status_code=500, detail="API Key Manager not initialized")
        token = _extract_bearer_token(raw_request)
        api_key_info = deps.api_key_manager.verify_key(token) if token else None
        store_name = auth["store_name"]

    # Extract last user message
    user_messages = [msg for msg in request.messages if msg.role == "user"]
    if not user_messages:
        raise HTTPException(status_code=400, detail="No user message found")

    last_message = user_messages[-1].content

    system_prompt = _get_system_prompt(api_key_info, store_name, request.messages)

    # Validate model
    warning = None
    if request.model in SUPPORTED_MODELS:
        model_name = request.model
    else:
        model_name = DEFAULT_MODEL
        warning = f"Unsupported model '{request.model}', using default '{DEFAULT_MODEL}'. Supported: {', '.join(SUPPORTED_MODELS)}"

    try:
        # Use local RAG pipeline for retrieval
        pipeline = get_rag_pipeline()
        kb_text, _citations = pipeline.retrieve(last_message, language="zh", source_type="jti_knowledge", top_k=3)

        # Build prompt with RAG context
        contents = last_message
        if kb_text:
            contents = f"<知識庫查詢結果>\n{kb_text}\n</知識庫查詢結果>\n\n使用者問題： {last_message}"

        config_kwargs = {}
        if system_prompt:
            config_kwargs["system_instruction"] = system_prompt

        response = gemini_client.models.generate_content(
            model=model_name,
            contents=contents,
            config=types.GenerateContentConfig(
                thinking_config=types.ThinkingConfig(thinking_budget=0),
                **config_kwargs,
            ),
        )

        answer_text = strip_citations(response.text)
        if warning:
            answer_text = f"⚠️ {warning}\n\n{answer_text}"

        result = OpenAIChatResponse(
            id=f"chatcmpl-{uuid.uuid4().hex[:8]}",
            created=int(time.time()),
            model=model_name,
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
    """Service health check (no auth required)."""
    checks = {}

    # 1. MongoDB
    try:
        mongo = get_mongo_client()
        checks["mongodb"] = mongo.health_check()
    except Exception:
        checks["mongodb"] = False

    # 2. Gemini API Keys registry
    try:
        from .services.gemini_clients import get_key_count
        checks["gemini_api_key"] = get_key_count() > 0
    except Exception:
        checks["gemini_api_key"] = False

    # 3. API Key Manager
    checks["api_key_manager"] = deps.api_key_manager is not None

    # 4. General Session Manager (MongoDB persistence)
    checks["general_session_manager"] = deps.get_general_chat_session_manager() is not None

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
    """API root."""
    return {"message": "JTAI API", "docs": "/docs"}


# ========== Include Routers ==========
app.include_router(admin_rag_router)
app.include_router(jti_chat.runtime_router)
app.include_router(jti_chat.compat_history_router)
app.include_router(jti_chat.admin_history_router)
app.include_router(jti_quiz.router, prefix="/api/jti")
app.include_router(jti_prompts.router, prefix="/api/jti-admin/prompts")
app.include_router(jti_prompts.router, prefix="/api/jti/prompts", include_in_schema=False)
app.include_router(jti_knowledge.router, prefix="/api/jti-admin/knowledge")
app.include_router(jti_knowledge.router, prefix="/api/jti/knowledge", include_in_schema=False)
app.include_router(jti_quiz_bank.router, prefix="/api/jti-admin/quiz-bank")
app.include_router(jti_quiz_bank.router, prefix="/api/jti/quiz-bank", include_in_schema=False)
app.include_router(hciot_chat.runtime_router)
app.include_router(hciot_chat.compat_history_router)
app.include_router(hciot_chat.admin_history_router)
app.include_router(hciot_prompts.router, prefix="/api/hciot-admin/prompts")
app.include_router(hciot_prompts.router, prefix="/api/hciot/prompts", include_in_schema=False)
app.include_router(hciot_knowledge.router, prefix="/api/hciot-admin/knowledge")
app.include_router(hciot_knowledge.router, prefix="/api/hciot/knowledge", include_in_schema=False)
app.include_router(hciot_images.router, prefix="/api/hciot")
app.include_router(hciot_images.admin_router, prefix="/api/hciot-admin/images")
app.include_router(hciot_topics_admin.public_router, prefix="/api/hciot")
app.include_router(hciot_topics_admin.router, prefix="/api/hciot-admin/topics")
app.include_router(chat.router)
app.include_router(prompts.router)  # before stores (more specific path patterns)
app.include_router(knowledge_admin.router)
app.include_router(stores.router)
app.include_router(api_keys.router)

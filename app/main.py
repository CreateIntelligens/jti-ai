"""ai360 km api FastAPI backend (RAG-based)."""

import asyncio
import logging
import os
import time
import uuid
import warnings
from collections.abc import Callable
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, Optional

import uvicorn.logging

from .logging_config import configure_file_logging

GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
RESET = "\033[0m"
_NOISY_LOGGERS = ("httpx", "google")
_UVICORN_LOGGERS = ("uvicorn", "uvicorn.access", "uvicorn.error")
_AFC_WARNING_PATTERNS = (".*automatic function calling.*", ".*AFC.*")
_RAG_BACKFILL_LOCK_KEY = "rag:backfill:startup"
# Backfill 可能耗時數分鐘；TTL 需涵蓋正常執行時間，也要允許崩潰後復原。
_RAG_BACKFILL_LOCK_TTL_SECONDS = 30 * 60
_RAG_BACKFILL_WAIT_TIMEOUT_SECONDS = 30 * 60
_RAG_BACKFILL_LOCK_POLL_SECONDS = 2
# Redis 不可用時的哨兵：照常索引，但不要去刪別人的鎖。
_RAG_BACKFILL_LOCK_UNHELD_TOKEN = ""
# 只在 value 仍等於自己的 token 時才刪，避免 TTL 過期換手後誤刪新持有者的鎖。
_RELEASE_LOCK_IF_OWNED = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('del', KEYS[1])
end
return 0
"""
_FIXED_RAG_BACKFILL_JOBS = (
    ("jti", "zh"),
    ("jti", "en"),
    ("hciot", "zh"),
    ("hciot", "en"),
    ("esg", "zh"),
    ("esg", "en"),
)

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

    configure_file_logging()


def _configure_warning_filters() -> None:
    for message in _AFC_WARNING_PATTERNS:
        warnings.filterwarnings("ignore", message=message)


class _AccessLogNoiseFilter(logging.Filter):
    """Drop noisy access log entries from polling endpoints and health checks."""

    _QUIET_GET_PATHS = (
        "/api/hciot/topics/",
        "/api/stores",
        "/api/keys/count",
    )

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        if "/health" in msg:
            return False
        if "/tts/tts_" in msg and " 202" in msg:
            return False
        if " 200" in msg and any(f"GET {p} " in msg for p in self._QUIET_GET_PATHS):
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

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from google.genai import types
from google.genai.errors import ClientError
from pydantic import BaseModel

from .auth import _extract_bearer_token, verify_auth
from .services.agent_utils import strip_citations
from .services.model_discovery import get_available_models
from .services.mongo_client import get_mongo_client
from .routers.admin_rag import router as admin_rag_router
from .routers.auth_routes import router as auth_router
from .routers.esg import (
    chat as esg_chat,
    knowledge as esg_knowledge,
    prompts as esg_prompts,
    quiz as esg_quiz,
    quiz_bank as esg_quiz_bank,
)
from .routers.esg import topics_admin as esg_topics_admin
from .routers.general import (
    api_keys,
    chat,
    db_sync,
    models,
    prompts,
    quiz_bank as general_quiz_bank,
    stores,
    users,
)
from .routers.general import images as general_images
from .routers.general import knowledge as general_knowledge
from .routers.general import topics_admin as general_topics
from .routers.hciot import (
    chat as hciot_chat,
    images as hciot_images,
    knowledge as hciot_knowledge,
    prompts as hciot_prompts,
)
from .routers.hciot import topics_admin as hciot_topics_admin
from .routers.jti import (
    chat as jti_chat,
    knowledge as jti_knowledge,
    prompts as jti_prompts,
    quiz as jti_quiz,
    quiz_bank as jti_quiz_bank,
)
from .routers.jti import topics_admin as jti_topics_admin

import app.deps as deps

logger = logging.getLogger(__name__)
_BACKGROUND_TASKS = set()


def _schedule_background_task(coro) -> None:
    task = asyncio.create_task(coro)
    _BACKGROUND_TASKS.add(task)
    task.add_done_callback(_BACKGROUND_TASKS.discard)


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Initialize managers and background backfill on application startup."""
    deps.init_managers()

    _schedule_background_task(_run_module_startup_tasks())

    try:
        from app.services.rag.backfill import get_backfill_service
        _schedule_background_task(_run_rag_backfill(get_backfill_service()))
    except Exception as e:
        logger.error(f"[RAG] Failed to init backfill: {e}")

    yield

    try:
        from app.services.embedding.service import EmbeddingService
        if EmbeddingService.release():
            logger.info("[Shutdown] Embedding model released.")
    except Exception as e:
        logger.warning(f"[Shutdown] Embedding cleanup failed: {e}")

    logger.info("👋 ai360 km api shut down cleanly. Goodbye!")


def _list_general_store_names() -> list[str]:
    try:
        from app.routers.general.stores import get_store_registry

        return [
            store["name"]
            for store in get_store_registry().list_stores(app="general")
            if store.get("name")
        ]
    except Exception as e:
        logger.error("[RAG] Failed to list general stores: %s", e)
        return []


def _build_rag_backfill_jobs(general_store_names: list[str]) -> list[tuple[str, str]]:
    jobs = list(_FIXED_RAG_BACKFILL_JOBS)
    jobs.extend(("general", store_name) for store_name in general_store_names)
    return jobs


async def _run_module_startup_tasks() -> None:
    """Run non-critical app startup work after readiness is unblocked."""
    jobs = (
        ("JTI quiz seed", _run_jti_background_startup),
        ("HCIoT local backup", _run_hciot_background_startup),
    )
    for label, job in jobs:
        await _run_background_startup_job(label, job)


async def _run_background_startup_job(label: str, job: Callable[[], None]) -> None:
    loop = asyncio.get_running_loop()
    started = time.time()
    try:
        await loop.run_in_executor(None, job)
    except Exception as e:
        logger.warning("[Startup] Background %s failed: %s", label, e)
        return
    logger.info(
        "[Startup] Background %s complete in %.1fs",
        label,
        time.time() - started,
    )


def _run_jti_background_startup() -> None:
    from app.services.jti.startup import jti_background_startup

    jti_background_startup()


def _run_hciot_background_startup() -> None:
    from app.services.hciot.startup import hciot_startup

    hciot_startup()


def _build_backfill_lock_client() -> Any | None:
    """Redis client for the cross-process startup-backfill lock, or None.

    uvicorn runs multiple workers as separate processes, so LanceDBStore's
    threading lock cannot serialize them: two workers that both pass the
    fingerprint check before either writes will each index the same file,
    producing exact-duplicate chunks. Redis gives us a lock that spans
    processes. Without it we fall back to letting every worker index (the
    pre-existing behaviour) rather than skipping indexing entirely.
    """
    redis_url = os.getenv("REDIS_URL")
    if not redis_url:
        return None

    try:
        import redis
    except Exception as exc:
        logger.warning("[RAG] Backfill lock disabled: redis package unavailable (%s)", exc)
        return None

    try:
        client = redis.Redis.from_url(
            redis_url,
            decode_responses=True,
            socket_connect_timeout=1,
            socket_timeout=1,
        )
        client.ping()
        return client
    except Exception as exc:
        logger.warning("[RAG] Backfill lock disabled: %s", exc)
        return None


def _acquire_backfill_lock(client: Any) -> str | None:
    """Token of the acquired lock, or None if another worker holds it.

    Returns a sentinel token when Redis itself is unreachable so indexing still
    runs (duplicate chunks beat an unindexed store).
    """
    token = uuid.uuid4().hex
    try:
        acquired = client.set(
            _RAG_BACKFILL_LOCK_KEY,
            token,
            nx=True,
            ex=_RAG_BACKFILL_LOCK_TTL_SECONDS,
        )
    except Exception as exc:
        # A Redis hiccup must not stop indexing — fall back to running it.
        logger.warning("[RAG] Backfill lock unavailable, indexing anyway: %s", exc)
        return _RAG_BACKFILL_LOCK_UNHELD_TOKEN
    return token if acquired else None


def _wait_for_backfill_lock_release(client: Any) -> bool:
    """Return whether this worker observed the current lock being released."""
    deadline = time.time() + _RAG_BACKFILL_WAIT_TIMEOUT_SECONDS
    while time.time() < deadline:
        try:
            if not client.exists(_RAG_BACKFILL_LOCK_KEY):
                return True
        except Exception as exc:
            logger.warning("[RAG] Backfill lock poll failed: %s", exc)
            return False
        time.sleep(_RAG_BACKFILL_LOCK_POLL_SECONDS)
    logger.warning("[RAG] Timed out waiting for the indexing worker to finish")
    return False


def _release_backfill_lock(client: Any, token: str) -> None:
    """Delete the lock only if this worker still holds it.

    A plain DELETE is unsafe: if the backfill outran the TTL, the key may
    already belong to the next worker, and deleting it would let a third worker
    index concurrently. The compare-and-delete runs as one Lua script so the
    check and the delete cannot interleave.
    """
    if token == _RAG_BACKFILL_LOCK_UNHELD_TOKEN:
        return
    try:
        client.eval(_RELEASE_LOCK_IF_OWNED, 1, _RAG_BACKFILL_LOCK_KEY, token)
    except Exception as exc:
        logger.warning("[RAG] Failed to release backfill lock: %s", exc)


async def _run_rag_backfill(backfill: Any) -> None:
    """Background task to warm up embedding model and index knowledge files."""
    loop = asyncio.get_running_loop()
    started_at = time.time()
    try:
        await loop.run_in_executor(None, backfill.embedding_service.encode, "warmup")
    except Exception as exc:
        logger.error("[RAG] Embedding warmup failed: %s", exc)
        return

    lock_client = _build_backfill_lock_client()
    lock_token: str | None = None
    if lock_client is not None:
        while lock_token is None:
            lock_token = await loop.run_in_executor(
                None,
                _acquire_backfill_lock,
                lock_client,
            )
            # 空字串是 Redis 不可用的哨兵，仍要索引。
            if lock_token is not None:
                break

            logger.info("[RAG] Another worker is indexing; waiting for it to finish")
            lock_released = await loop.run_in_executor(
                None,
                _wait_for_backfill_lock_release,
                lock_client,
            )
            if lock_released:
                # 鎖消失可能是成功、失敗或 process 崩潰；重新競爭並跑冪等
                # backfill，才能確保失敗持有者留下的部分索引會被補齊。
                continue

            # Polling 失敗或逾時後再試一次：Redis 故障會回傳 fail-open
            # sentinel；若鎖仍存在，交由目前持有者繼續，且不謊報 ready。
            lock_token = await loop.run_in_executor(
                None,
                _acquire_backfill_lock,
                lock_client,
            )
            if lock_token is None:
                logger.warning(
                    "[RAG] Backfill lock still held after wait; "
                    "startup backfill deferred in this worker"
                )
                return

    try:
        general_store_names = _list_general_store_names()
        for source_type, partition in _build_rag_backfill_jobs(general_store_names):
            await loop.run_in_executor(
                None, backfill.run_backfill, source_type, partition
            )

        total = backfill.lancedb_store.get_stats().get("count", 0)
        elapsed = time.time() - started_at
        logger.info(
            "[RAG] Ready — %d chunks indexed in %.1fs (%d general stores)",
            total,
            elapsed,
            len(general_store_names),
        )
    except Exception as exc:
        logger.error("[RAG] Backfill failed: %s", exc)
    finally:
        # 已處理的失敗要立即釋放，避免其他 worker 等完整段 TTL。
        if lock_client is not None and lock_token is not None:
            _release_backfill_lock(lock_client, lock_token)


app = FastAPI(title="ai360 km api", lifespan=lifespan)


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


from app.models_config import (  # noqa: E402
    DEFAULT_MODEL,
    fallback_chain,
    thinking_config_for_model,
)


class OpenAIChatMessage(BaseModel):
    role: str
    content: str


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
    system_messages = [msg for msg in messages if msg.role == "system"]
    if system_messages:
        return system_messages[-1].content

    if not deps.prompt_manager:
        return None

    if api_key_info and api_key_info.prompt_index is not None:
        prompts = deps.prompt_manager.list_prompts(store_name)
        if 0 <= api_key_info.prompt_index < len(prompts):
            return prompts[api_key_info.prompt_index].content

    active_prompt = deps.prompt_manager.get_active_prompt(store_name)
    if active_prompt:
        return active_prompt.content

    return None


@app.post("/v1/chat/completions")
async def openai_chat_completions(
    request: OpenAIChatRequest, raw_request: Request, auth: dict = Depends(verify_auth)
):
    """OpenAI-compatible Chat Completions API with knowledge-base-bound API keys."""
    from app.services.rag.service import get_rag_pipeline
    from app.services.gemini_service import client as gemini_client, gemini_with_fallback

    if not gemini_client:
        raise HTTPException(status_code=500, detail="Gemini API key not configured")

    api_key_info = None
    if auth["role"] in ("admin", "super_admin"):
        store_name = os.getenv("JTI_STORE_ID_ZH", "")
        if not store_name:
            raise HTTPException(
                status_code=400,
                detail="Knowledge store not configured (JTI_STORE_ID_ZH)",
            )
    else:
        if not deps.api_key_manager:
            raise HTTPException(status_code=500, detail="API Key Manager not initialized")
        token = _extract_bearer_token(raw_request)
        api_key_info = deps.api_key_manager.verify_key(token) if token else None
        store_name = auth["store_name"]

    user_messages = [msg for msg in request.messages if msg.role == "user"]
    if not user_messages:
        raise HTTPException(status_code=400, detail="No user message found")

    last_message = user_messages[-1].content
    system_prompt = _get_system_prompt(api_key_info, store_name, request.messages)

    available_names = {model.name for model in get_available_models(gemini_client)}
    warning = None
    if available_names and request.model not in available_names:
        model_name = DEFAULT_MODEL
        available_list = ", ".join(sorted(available_names))
        warning = (
            f"Unsupported model '{request.model}', using default '{DEFAULT_MODEL}'. "
            f"Available: {available_list}"
        )
    else:
        model_name = request.model

    try:
        pipeline = get_rag_pipeline()
        kb_text, _citations = pipeline.retrieve(
            last_message, language="zh", source_type="jti_knowledge", top_k=3
        )

        contents = last_message
        if kb_text:
            contents = f"<知識庫查詢結果>\n{kb_text}\n</知識庫查詢結果>\n\n使用者問題： {last_message}"

        config_kwargs = {}
        if system_prompt:
            config_kwargs["system_instruction"] = system_prompt

        def generate_with_model(m):
            return gemini_client.models.generate_content(
                model=m,
                contents=contents,
                config=types.GenerateContentConfig(
                    thinking_config=thinking_config_for_model(m),
                    **config_kwargs,
                ),
            )

        response = gemini_with_fallback(
            generate_with_model,
            fallback_chain(model_name, gemini_client),
        )

        answer_text = strip_citations(response.text or "")
        if warning:
            answer_text = f"⚠️ {warning}\n\n{answer_text}"

        result = OpenAIChatResponse(
            id=f"chatcmpl-{uuid.uuid4().hex[:8]}",
            created=int(time.time()),
            model=model_name,
            choices=[
                OpenAIChatChoice(
                    index=0,
                    message=OpenAIChatMessage(role="assistant", content=answer_text),
                    finish_reason="stop",
                )
            ],
            usage={
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
            },
        )

        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
async def health_check():
    """Service health check (no auth required)."""
    checks = {}

    try:
        mongo = get_mongo_client()
        checks["mongodb"] = await asyncio.to_thread(mongo.health_check)
    except Exception:
        checks["mongodb"] = False

    try:
        from .services.gemini_clients import get_key_count
        checks["gemini_api_key"] = get_key_count() > 0
    except Exception:
        checks["gemini_api_key"] = False

    # embedding 掛掉時 RAG 全斷但其他項目都正常，必須納入對外健康狀態
    try:
        from .services.embedding.service import get_embedding_service
        checks["embedding"] = await asyncio.to_thread(
            get_embedding_service().health_check
        )
    except Exception:
        checks["embedding"] = False

    checks["api_key_manager"] = deps.api_key_manager is not None
    checks["general_session_manager"] = deps.get_general_chat_session_manager() is not None

    from .services.mongo_client import is_using_fallback
    on_fallback = is_using_fallback()

    all_ok = all(checks.values())
    status_code = 200 if all_ok else 503

    return JSONResponse(
        status_code=status_code,
        content={
            "status": "ok" if all_ok else "degraded",
            "checks": checks,
            "database_fallback": on_fallback,
        },
    )


@app.get("/")
def index():
    """API root."""
    return {"message": "ai360 km api", "docs": "/docs"}


app.include_router(admin_rag_router)
app.include_router(auth_router)
app.include_router(jti_chat.runtime_router)
app.include_router(jti_chat.compat_history_router)
app.include_router(jti_chat.admin_history_router)
app.include_router(jti_chat.compat_history_admin_router)
app.include_router(jti_chat.admin_history_admin_router)
app.include_router(jti_quiz.router, prefix="/api/jti")
app.include_router(jti_prompts.router, prefix="/api/jti-admin/prompts")
app.include_router(jti_prompts.router, prefix="/api/jti/prompts", include_in_schema=False)
app.include_router(jti_knowledge.router, prefix="/api/jti-admin/knowledge")
app.include_router(jti_knowledge.router, prefix="/api/jti/knowledge", include_in_schema=False)
app.include_router(jti_topics_admin.public_router, prefix="/api/jti")
app.include_router(jti_topics_admin.router, prefix="/api/jti-admin/topics")
app.include_router(jti_quiz_bank.router, prefix="/api/jti-admin/quiz-bank")
app.include_router(jti_quiz_bank.router, prefix="/api/jti/quiz-bank", include_in_schema=False)
app.include_router(hciot_chat.runtime_router)
app.include_router(hciot_chat.compat_history_router)
app.include_router(hciot_chat.admin_history_router)
app.include_router(hciot_chat.compat_history_admin_router)
app.include_router(hciot_chat.admin_history_admin_router)
app.include_router(hciot_prompts.router, prefix="/api/hciot-admin/prompts")
app.include_router(hciot_prompts.router, prefix="/api/hciot/prompts", include_in_schema=False)
app.include_router(hciot_knowledge.router, prefix="/api/hciot-admin/knowledge")
app.include_router(hciot_knowledge.router, prefix="/api/hciot/knowledge", include_in_schema=False)
app.include_router(esg_chat.runtime_router)
app.include_router(esg_chat.compat_history_router)
app.include_router(esg_chat.admin_history_router)
app.include_router(esg_chat.compat_history_admin_router)
app.include_router(esg_chat.admin_history_admin_router)
app.include_router(esg_quiz.router, prefix="/api/esg")
app.include_router(esg_prompts.router, prefix="/api/esg-admin/prompts")
app.include_router(esg_prompts.router, prefix="/api/esg/prompts", include_in_schema=False)
app.include_router(esg_knowledge.router, prefix="/api/esg-admin/knowledge")
app.include_router(esg_knowledge.router, prefix="/api/esg/knowledge", include_in_schema=False)
app.include_router(esg_topics_admin.public_router, prefix="/api/esg")
app.include_router(esg_topics_admin.router, prefix="/api/esg-admin/topics")
app.include_router(esg_quiz_bank.router, prefix="/api/esg-admin/quiz-bank")
app.include_router(esg_quiz_bank.router, prefix="/api/esg/quiz-bank", include_in_schema=False)
app.include_router(hciot_images.router, prefix="/api/hciot")
app.include_router(hciot_images.admin_router, prefix="/api/hciot-admin/images")
app.include_router(hciot_topics_admin.public_router, prefix="/api/hciot")
app.include_router(hciot_topics_admin.router, prefix="/api/hciot-admin/topics")
app.include_router(chat.router)
app.include_router(general_quiz_bank.router)
app.include_router(general_knowledge.router, prefix="/api/general-admin/knowledge")
app.include_router(general_knowledge.router, prefix="/api/general/knowledge", include_in_schema=False)
app.include_router(general_topics.public_router, prefix="/api/general")
app.include_router(general_topics.router, prefix="/api/general-admin")
app.include_router(general_images.router, prefix="/api/general")
app.include_router(general_images.admin_router, prefix="/api/general-admin")
app.include_router(prompts.router)  # before stores (more specific path patterns)
app.include_router(stores.router)
app.include_router(api_keys.router)
app.include_router(models.router)
app.include_router(users.router)
app.include_router(db_sync.router)

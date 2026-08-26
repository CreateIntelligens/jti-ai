import logging
import os
import threading
import time
from typing import Any, List, Literal, Optional, Union

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel


logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


class _HealthCheckFilter(logging.Filter):
    """Drop uvicorn access logs for /health so the 30s healthcheck poll
    doesn't flood the log. Other requests and non-200s still show."""

    def filter(self, record: logging.LogRecord) -> bool:
        return record.getMessage().find("/health") == -1


logging.getLogger("uvicorn.access").addFilter(_HealthCheckFilter())

MODEL_NAME = os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3")
# 釘死權重 revision：與 openVman 共用同一份 BGE-M3 快照，確保向量可互換。
# 若不釘，cache 清掉後重抓可能默默拿到上游新權重，造成新舊向量不相容。
# 更新方式：openVman 換新快照時，把這裡改成相同 SHA 並重算所有既有向量。
MODEL_REVISION = os.getenv(
    "EMBEDDING_MODEL_REVISION",
    "5617a9f61b028005a4858fdac845db406aefb181",
)
BATCH_SIZE = int(os.getenv("EMBEDDING_BATCH_SIZE", "32"))
MAX_LENGTH = int(os.getenv("EMBEDDING_MAX_LENGTH", "8192"))
# 對外 edge 的 Bearer token（與 openVman 表面一致：/health 公開，其餘要驗）。
# 留空 = 不驗證，供 Docker 內網 fallback 模式使用。
SERVICE_TOKEN = os.getenv("EMBEDDING_SERVICE_TOKEN", "").strip()

app = FastAPI(title="embedding-service")

_STARTED_AT = int(time.time())


def _require_token(authorization: Optional[str] = Header(None)) -> None:
    if not SERVICE_TOKEN:
        return
    if authorization != f"Bearer {SERVICE_TOKEN}":
        raise HTTPException(
            status_code=401, detail="invalid or missing bearer token"
        )

_model: Optional[Any] = None


def _resolve_device() -> str:
    env_device = os.getenv("EMBEDDING_DEVICE")
    if env_device:
        return env_device
    try:
        import torch  # lazy: torch import alone costs ~500MB-1GB RSS; only pay it when actually deciding device
        return "cuda" if torch.cuda.is_available() else "cpu"
    except Exception:
        return "cpu"


def _shutdown_loky_executor() -> None:
    """Shut down joblib/loky's reusable process pool if it was started.

    FlagEmbedding pulls in joblib, whose loky backend keeps a reusable
    executor backed by a POSIX semaphore (/dev/shm/sem.loky-*). It is only
    reclaimed by loky's own atexit, which races the multiprocessing
    resource_tracker and triggers a "leaked semaphore" warning. Stopping it
    during teardown reclaims the semaphore deterministically. No-op if loky
    was never used.
    """
    for path in ("joblib.externals.loky", "loky"):
        try:
            module = __import__(path, fromlist=["get_reusable_executor"])
            module.get_reusable_executor().shutdown(wait=True, kill_workers=True)
            return
        except Exception:
            continue


_model_lock = threading.Lock()


def _get_model() -> Any:
    global _model
    if _model is not None:
        return _model
    # 背景預載執行緒與首個請求可能同時進來，鎖住避免模型被載兩份（VRAM x2）。
    with _model_lock:
        if _model is None:
            _load_model_locked()
    return _model


def _load_model_locked() -> None:
    global _model
    from FlagEmbedding import FlagModel
    from huggingface_hub import snapshot_download

    device = _resolve_device()
    logger.info(
        "Loading embedding model %s@%s on %s...",
        MODEL_NAME, MODEL_REVISION[:12], device,
    )
    # 經 snapshot_download 釘 revision（FlagModel 建構子不吃 revision 參數），
    # 已在 cache 時不重新下載。
    model_path = snapshot_download(MODEL_NAME, revision=MODEL_REVISION)
    _model = FlagModel(
        model_path,
        device=device,
        use_fp16=(device == "cuda"),
    )
    logger.info("Embedding model loaded.")


class EmbedRequest(BaseModel):
    texts: List[str]
    input_type: Literal["query", "document"] = "document"


class EmbedResponse(BaseModel):
    vectors: List[List[float]]
    model: str
    embedding_spec: dict
    attempts: List[dict]


# 與 openVman 的 /embed 回應 schema 對齊：backend 依 embedding_spec 做嚴格
# 契約驗證（identity 欄位順序見 backend 的 _validate_response）。
SERVICE_REVISION = "jtai-embedding/1.4.0"


def _build_spec(input_type: str, dimensions: int) -> dict:
    spec = {
        "provider": "bge",
        "model": MODEL_NAME,
        "dimensions": dimensions,
        "dtype": "float32",
        "normalized": True,
        "normalization": "l2",
        "input_semantics": input_type,
        "model_revision": MODEL_REVISION,
        "service_revision": SERVICE_REVISION,
    }
    spec["identity"] = ":".join(
        str(spec[field])
        for field in (
            "provider",
            "model",
            "dimensions",
            "dtype",
            "normalization",
            "input_semantics",
            "model_revision",
        )
    )
    return spec


@app.on_event("startup")
def _on_startup() -> None:
    # 背景預載模型，讓 /health/ready 反映真實就緒狀態（lazy load 會讓 ready
    # 在第一次請求前一直是 false）。失敗不擋啟動，之後請求時會再重試。
    threading.Thread(target=_load_model_safely, daemon=True).start()


def _load_model_safely() -> None:
    try:
        _get_model()
    except Exception:
        logger.exception("Background model preload failed")


@app.on_event("shutdown")
def _on_shutdown() -> None:
    global _model
    model = _model
    if model is None:
        return
    stop_self_pool = getattr(model, "stop_self_pool", None)
    if callable(stop_self_pool):
        stop_self_pool()
    _shutdown_loky_executor()
    _model = None


# ==== 端點表面與 openVman 對齊 ====
# POST /                jtai 格式嵌入（經 nginx 對外為 POST /api/embedding）  Bearer
# POST /v1/embeddings   OpenAI 相容嵌入                                       Bearer
# GET  /v1/models       模型清單                                              Bearer
# GET  /health          存活                                                  公開
# GET  /health/ready    就緒（模型已載入）                                     Bearer


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/health/ready", dependencies=[Depends(_require_token)])
def health_ready() -> dict:
    if _model is None:
        raise HTTPException(status_code=503, detail="model is still loading")
    return {
        "status": "ready",
        "service": "embedding-service",
        "service_revision": SERVICE_REVISION,
        "model": MODEL_NAME,
        "dimension": 1024,
        "normalization": "l2",
        "embedding_spec": _build_spec("document", 1024),
    }


def _encode_texts(texts: List[str], input_type: str) -> List[List[float]]:
    try:
        # BGE-M3's encode() handles both single and batch; input_type is
        # accepted for API symmetry but bge-m3 uses one space for both sides.
        vectors = _get_model().encode(
            texts,
            batch_size=BATCH_SIZE,
            max_length=MAX_LENGTH,
        )
    except Exception as e:
        logger.error("Encoding failed: %s", e)
        raise HTTPException(status_code=500, detail=f"encode failed: {e}")
    return vectors.tolist()


@app.post(
    "/",
    response_model=EmbedResponse,
    dependencies=[Depends(_require_token)],
)
@app.post(
    "/embed",
    response_model=EmbedResponse,
    dependencies=[Depends(_require_token)],
    include_in_schema=False,  # 舊路徑相容別名，遷移期後可移除
)
def embed(req: EmbedRequest) -> EmbedResponse:
    rows = _encode_texts(req.texts, req.input_type) if req.texts else []
    dimensions = len(rows[0]) if rows else 1024
    return EmbedResponse(
        vectors=rows,
        model=MODEL_NAME,
        embedding_spec=_build_spec(req.input_type, dimensions),
        attempts=[{"provider": "bge", "status": "selected"}],
    )


class OpenAIEmbeddingsRequest(BaseModel):
    input: Union[str, List[str]]
    model: Optional[str] = None


@app.post("/v1/embeddings", dependencies=[Depends(_require_token)])
def openai_embeddings(req: OpenAIEmbeddingsRequest) -> dict:
    texts = [req.input] if isinstance(req.input, str) else req.input
    rows = _encode_texts(texts, "document") if texts else []
    return {
        "object": "list",
        "data": [
            {"object": "embedding", "index": i, "embedding": row}
            for i, row in enumerate(rows)
        ],
        "model": MODEL_NAME,
        "usage": {"prompt_tokens": 0, "total_tokens": 0},
    }


@app.get("/v1/models", dependencies=[Depends(_require_token)])
def list_models() -> dict:
    return {
        "object": "list",
        "data": [
            {
                "id": MODEL_NAME,
                "object": "model",
                "created": _STARTED_AT,
                "owned_by": "jtai-bge",
                "dimensions": 1024,
                "identity": _build_spec("document", 1024)["identity"],
            }
        ],
    }

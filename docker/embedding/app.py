import logging
import os
from typing import Any, List, Literal, Optional

from fastapi import FastAPI, HTTPException
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
MODEL_REVISION = os.getenv(
    "EMBEDDING_MODEL_REVISION",
    "5617a9f61b028005a4858fdac845db406aefb181",
)
BATCH_SIZE = int(os.getenv("EMBEDDING_BATCH_SIZE", "32"))
MAX_LENGTH = int(os.getenv("EMBEDDING_MAX_LENGTH", "8192"))

app = FastAPI(title="embedding-service")

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


def _get_model() -> Any:
    global _model
    if _model is None:
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
    return _model


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


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/embed", response_model=EmbedResponse)
def embed(req: EmbedRequest) -> EmbedResponse:
    if not req.texts:
        return EmbedResponse(
            vectors=[],
            model=MODEL_NAME,
            embedding_spec=_build_spec(req.input_type, 1024),
            attempts=[{"provider": "bge", "status": "selected"}],
        )
    try:
        # BGE-M3's encode() handles both single and batch; input_type is
        # accepted for API symmetry but bge-m3 uses one space for both sides.
        vectors = _get_model().encode(
            req.texts,
            batch_size=BATCH_SIZE,
            max_length=MAX_LENGTH,
        )
    except Exception as e:
        logger.error("Encoding failed: %s", e)
        raise HTTPException(status_code=500, detail=f"encode failed: {e}")
    rows = vectors.tolist()
    return EmbedResponse(
        vectors=rows,
        model=MODEL_NAME,
        embedding_spec=_build_spec(req.input_type, len(rows[0])),
        attempts=[{"provider": "bge", "status": "selected"}],
    )

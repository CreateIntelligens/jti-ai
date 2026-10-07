import logging
import os
import threading
import time
from typing import Any, List, Literal, Optional, Union

import numpy as np
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

PROVIDER = "gemma"
MODEL_NAME = os.getenv("EMBEDDING_MODEL", "google/embeddinggemma-2")
# 釘死權重 revision：與 openVman 共用同一份 EmbeddingGemma 2 快照，確保向量可互換。
# 若不釘，cache 清掉後重抓可能默默拿到上游新權重，造成新舊向量不相容。
# 更新方式：openVman 換新快照時，把這裡改成相同 SHA 並重算所有既有向量。
MODEL_REVISION = os.getenv(
    "EMBEDDING_MODEL_REVISION",
    "914f7f89142e33e77833254d9c9b90c3cef7303b",
)
# Matryoshka 可截成 512/256/128，但 backend 的表名與驗證都以維度區分，改了要重建索引。
DIMENSIONS = int(os.getenv("EMBEDDING_DIMENSIONS", "768"))
BATCH_SIZE = int(os.getenv("EMBEDDING_BATCH_SIZE", "16"))
MAX_LENGTH = int(os.getenv("EMBEDDING_MAX_LENGTH", "2048"))
# 與 openVman 相同的單次上限，避免一個請求把 GPU 佔太久。
MAX_TEXTS_PER_REQUEST = 512

# 非對稱模型：查詢與文件要加不同前綴，向量才在同一個空間裡可比。前綴必須與
# openVman 的 gemma provider 逐字一致，否則同一個 identity 算出不同向量。
_QUERY_PREFIXES = {
    "query": "task: question answering | query: ",
    "search_query": "task: search result | query: ",
}
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
    import torch
    from sentence_transformers import SentenceTransformer

    device = _resolve_device()
    logger.info(
        "Loading embedding model %s@%s on %s...",
        MODEL_NAME, MODEL_REVISION[:12], device,
    )
    # 官方說明 fp16 會出 NaN，GPU 上只能用 bf16。
    dtype = torch.bfloat16 if device.startswith("cuda") else torch.float32
    model = SentenceTransformer(
        MODEL_NAME,
        device=device,
        revision=MODEL_REVISION,
        model_kwargs={"torch_dtype": dtype},
    )
    model.max_seq_length = MAX_LENGTH
    _model = model
    logger.info("Embedding model loaded.")


class EmbedRequest(BaseModel):
    texts: List[str]
    input_type: Literal["query", "search_query", "document"] = "document"
    # 文件標題（檔名或主題），只用於 document；沒給就是 title: none。
    titles: Optional[List[str]] = None
    identity: Optional[str] = None
    acceptable_identities: Optional[List[str]] = None


class EmbedResponse(BaseModel):
    vectors: List[List[float]]
    model: str
    embedding_spec: dict
    attempts: List[dict]


# 與 openVman 的 /embed 回應 schema 對齊：backend 依 embedding_spec 做嚴格
# 契約驗證（identity 欄位順序見 backend 的 _validate_response）。
SERVICE_REVISION = "jtai-embedding/2.0.0"


def _build_spec(input_type: str, dimensions: int = DIMENSIONS) -> dict:
    spec = {
        "provider": PROVIDER,
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
        "dimension": DIMENSIONS,
        "normalization": "l2",
        "embedding_spec": _build_spec("document"),
    }


# GPU 推論本來就是獨占資源，序列化對吞吐幾乎沒有額外損失，也避免併發請求
# 同時配置 batch 造成 CUDA OOM。
_encode_lock = threading.Lock()


def _format_inputs(
    texts: List[str],
    input_type: str,
    titles: Optional[List[str]],
) -> List[str]:
    prefix = _QUERY_PREFIXES.get(input_type)
    if prefix is not None:
        return [prefix + text for text in texts]
    names = titles if titles and len(titles) == len(texts) else [""] * len(texts)
    return [
        f"title: {(name or '').strip() or 'none'} | text: {text}"
        for name, text in zip(names, texts)
    ]


def _encode_texts(
    texts: List[str],
    input_type: str,
    titles: Optional[List[str]] = None,
) -> List[List[float]]:
    try:
        with _encode_lock:
            vectors = _get_model().encode(
                _format_inputs(texts, input_type, titles),
                batch_size=BATCH_SIZE,
                convert_to_numpy=True,
                normalize_embeddings=False,
                show_progress_bar=False,
            )
    except Exception as e:
        logger.error("Encoding failed: %s", e)
        raise HTTPException(status_code=500, detail=f"encode failed: {e}")
    # Matryoshka 截短後一定要重新正規化，否則不再是單位向量。
    vectors = np.asarray(vectors[:, :DIMENSIONS], dtype=np.float32)
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    return (vectors / np.clip(norms, 1e-12, None)).tolist()


def _check_identity(req: "EmbedRequest") -> None:
    """呼叫端指定的 identity 必須是我們這個模型，否則拒絕而不是回別的向量。"""
    ours = _build_spec(req.input_type)["identity"]
    wanted = [req.identity] if req.identity else (req.acceptable_identities or [])
    if wanted and ours not in wanted:
        raise HTTPException(
            status_code=422,
            detail=(
                "No configured embedding provider matched requested criteria "
                f"(requested_identity={req.identity!r}, "
                f"acceptable_identities={req.acceptable_identities!r})"
            ),
        )


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
    if len(req.texts) > MAX_TEXTS_PER_REQUEST:
        raise HTTPException(
            status_code=413,
            detail=f"at most {MAX_TEXTS_PER_REQUEST} texts per request",
        )
    if req.titles is not None and len(req.titles) != len(req.texts):
        raise HTTPException(
            status_code=422, detail="titles must match texts in length"
        )
    _check_identity(req)
    rows = (
        _encode_texts(req.texts, req.input_type, req.titles)
        if req.texts else []
    )
    return EmbedResponse(
        vectors=rows,
        model=MODEL_NAME,
        embedding_spec=_build_spec(req.input_type),
        attempts=[{"provider": PROVIDER, "status": "selected"}],
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
                "owned_by": "jtai-gemma",
                "dimensions": DIMENSIONS,
                "identity": _build_spec("document")["identity"],
            }
        ],
    }

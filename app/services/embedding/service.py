import logging
import os
import random
import time
from typing import Any

import httpx
import numpy as np

from app.services.embedding.errors import EmbeddingEncodingError

logger = logging.getLogger(__name__)

# Chunk remote payloads so a large backfill batch doesn't post one huge body.
_REMOTE_CHUNK_SIZE = 64
_REMOTE_TIMEOUT_S = 120.0
# 服務前面的 nginx 會 limit_req，密集檢索（連續問答、backfill）容易撞到 429。
# 這是暫時且可恢復的，單次就放棄會讓整個 RAG 檢索回 0 命中，對使用者等同答不出來。
_RETRY_STATUS = frozenset({429, 503})
_RETRY_ATTEMPTS = 3
_RETRY_BASE_DELAY_S = 0.5
# 對方若有給 Retry-After 就尊重它，但設上限避免被要求睡到整個請求逾時。
_RETRY_AFTER_CAP_S = 10.0
# /health 探測要短 timeout：backend 的 /health 會等它，拖太久會連帶拖慢外部監控。
_HEALTH_TIMEOUT_S = 2.0
_DEFAULT_MODEL = "BAAI/bge-m3"
_DEFAULT_DIMENSIONS = 1024
_SPEC_FIELDS = {
    "dimensions",
    "dtype",
    "identity",
    "input_semantics",
    "model",
    "model_revision",
    "normalization",
    "normalized",
    "provider",
    "service_revision",
}


def _retry_after_seconds(resp: httpx.Response, attempt: int) -> float:
    """退避秒數：優先用對方的 Retry-After，否則指數退避加抖動。

    抖動避免多個 worker 同時撞到限流後又同步重試，再次集體觸發 limit_req。
    """
    raw = resp.headers.get("Retry-After")
    if raw:
        try:
            return min(float(raw), _RETRY_AFTER_CAP_S)
        except ValueError:
            pass
    return _RETRY_BASE_DELAY_S * (2 ** attempt) + random.uniform(0, 0.25)


def _post_with_retry(
    client: httpx.Client,
    url: str,
    *,
    json: dict[str, Any],
    headers: dict[str, str],
) -> httpx.Response:
    """POST，遇到限流/暫時不可用時重試。

    只重試 _RETRY_STATUS（429/503）這類會自行恢復的狀態；4xx/5xx 其餘狀態
    重試也不會變好，直接讓它拋出去。
    """
    last_status: int | None = None
    for attempt in range(_RETRY_ATTEMPTS):
        resp = client.post(url, json=json, headers=headers)
        status = getattr(resp, "status_code", None)
        if status not in _RETRY_STATUS:
            resp.raise_for_status()
            return resp

        last_status = status
        if attempt == _RETRY_ATTEMPTS - 1:
            break
        delay = _retry_after_seconds(resp, attempt)
        logger.warning(
            "Embedding service returned %s, retrying in %.2fs (%d/%d)",
            status,
            delay,
            attempt + 1,
            _RETRY_ATTEMPTS - 1,
        )
        time.sleep(delay)

    logger.error(
        "Embedding service still returning %s after %d attempts",
        last_status,
        _RETRY_ATTEMPTS,
    )
    resp.raise_for_status()
    return resp


class EmbeddingService:
    """HTTP client for the standalone embedding service.

    GPU embedding lives in its own process (see docker/embedding); this class
    only forwards encode requests over HTTP. EMBEDDING_SERVICE_URL is required
    — there is no in-process model fallback.
    """

    _instance: "EmbeddingService | None" = None

    def __init__(
        self,
        service_url: str | None = None,
        service_token: str | None = None,
    ):
        self.service_url = service_url or os.getenv("EMBEDDING_SERVICE_URL")
        if not self.service_url:
            raise EmbeddingEncodingError(
                "EMBEDDING_SERVICE_URL is not set; the embedding service is required."
            )
        self.service_token = (
            service_token
            if service_token is not None
            else os.getenv("EMBEDDING_SERVICE_TOKEN", "")
        ).strip()
        self.expected_model = os.getenv(
            "EMBEDDING_EXPECTED_MODEL",
            os.getenv("EMBEDDING_MODEL", _DEFAULT_MODEL),
        ).strip()
        try:
            self.expected_dimensions = int(
                os.getenv(
                    "EMBEDDING_EXPECTED_DIMENSION",
                    str(_DEFAULT_DIMENSIONS),
                )
            )
        except ValueError as exc:
            raise EmbeddingEncodingError(
                "EMBEDDING_EXPECTED_DIMENSION must be an integer."
            ) from exc

    @classmethod
    def get_instance(cls) -> 'EmbeddingService':
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def release(cls) -> bool:
        """Drop the cached instance. No process-local model to tear down."""
        if cls._instance is None:
            return False
        cls._instance = None
        return True

    def _auth_headers(self) -> dict[str, str]:
        if not self.service_token:
            return {}
        return {"Authorization": f"Bearer {self.service_token}"}

    def health_check(self) -> bool:
        """探測 embedding 服務的 /health，供 backend 對外的 /health 彙整。

        只回 bool、不拋例外：embedding 掛掉時 /health 要能正常回 degraded，
        而不是自己也 500。
        """
        assert self.service_url is not None  # guaranteed by __init__
        url = f"{self.service_url.rstrip('/')}/health"
        try:
            resp = httpx.get(
                url,
                headers=self._auth_headers(),
                timeout=_HEALTH_TIMEOUT_S,
            )
            return resp.status_code == 200
        except httpx.HTTPError:
            return False

    def encode(
        self,
        texts: str | list[str],
        input_type: str = "document"
    ) -> np.ndarray:
        """Encode text(s) into embeddings via the embedding service.

        Returns a 2D float ndarray (rows = inputs) to match the previous
        FlagModel contract; downstream relies on `.ndim > 1` and per-row
        `.tolist()`.
        """
        if isinstance(texts, str):
            texts = [texts]

        assert self.service_url is not None  # guaranteed by __init__
        # jtai 格式嵌入直接 POST 在 base path（openVman 新表面已無 /embed）
        url = self.service_url.rstrip('/')
        vectors: list[list[float]] = []
        headers = self._auth_headers()
        selected_identity: str | None = None
        try:
            with httpx.Client(timeout=_REMOTE_TIMEOUT_S) as client:
                for start in range(0, len(texts), _REMOTE_CHUNK_SIZE):
                    batch = texts[start:start + _REMOTE_CHUNK_SIZE]
                    payload: dict[str, Any] = {
                        "texts": batch,
                        "input_type": input_type,
                    }
                    if selected_identity:
                        payload["identity"] = selected_identity
                    resp = _post_with_retry(
                        client,
                        url,
                        json=payload,
                        headers=headers,
                    )
                    batch_vectors, response_identity = self._validate_response(
                        resp.json(),
                        expected_count=len(batch),
                        input_type=input_type,
                        selected_identity=selected_identity,
                    )
                    vectors.extend(batch_vectors)
                    selected_identity = response_identity or selected_identity
        except httpx.HTTPError as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            detail = f"{type(exc).__name__} HTTP {status}" if status else type(exc).__name__
            logger.error("Remote embedding request failed (%s)", detail)
            raise EmbeddingEncodingError(
                f"Failed to encode texts: {detail}"
            ) from exc
        except (KeyError, TypeError, ValueError) as exc:
            logger.error("Embedding response contract validation failed")
            raise EmbeddingEncodingError(
                f"Failed to encode texts: incompatible response ({exc})"
            ) from exc
        return np.asarray(vectors, dtype=np.float32)

    def _validate_response(
        self,
        data: dict[str, Any],
        *,
        expected_count: int,
        input_type: str,
        selected_identity: str | None,
    ) -> tuple[list[list[float]], str | None]:
        vectors = data["vectors"]
        if not isinstance(vectors, list) or len(vectors) != expected_count:
            raise ValueError("vector count does not match the request")

        spec = data.get("embedding_spec")
        if spec is None:
            if "model" in data or "attempts" in data:
                raise ValueError("partial extended metadata")
            self._validate_vector_dimensions(vectors, self.expected_dimensions)
            return vectors, None

        if not isinstance(spec, dict):
            raise TypeError("embedding_spec must be an object")
        missing_fields = _SPEC_FIELDS.difference(spec)
        if missing_fields:
            raise ValueError(
                "embedding_spec is missing: " + ", ".join(sorted(missing_fields))
            )

        identity = spec["identity"]
        dimensions = spec["dimensions"]
        if not isinstance(identity, str) or not identity.strip():
            raise ValueError("embedding identity is empty")
        if selected_identity and identity != selected_identity:
            raise ValueError("embedding identity changed between chunks")
        canonical_identity = ":".join(
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
        if identity != canonical_identity:
            raise ValueError("embedding identity does not match embedding_spec")
        if spec["model"] != self.expected_model or data.get("model") != spec["model"]:
            raise ValueError("unexpected embedding model")
        if dimensions != self.expected_dimensions:
            raise ValueError("unexpected embedding dimensions")
        if spec["dtype"] != "float32":
            raise ValueError("unexpected embedding data type")
        if spec["normalized"] is not True or spec["normalization"] != "l2":
            raise ValueError("embeddings must be L2-normalized")
        if spec["input_semantics"] != input_type:
            raise ValueError("embedding input semantics do not match the request")
        for field in ("provider", "model_revision", "service_revision"):
            if not isinstance(spec[field], str) or not spec[field].strip():
                raise ValueError(f"embedding_spec.{field} is empty")
        if not isinstance(data.get("attempts"), list):
            raise TypeError("attempts must be a list")

        self._validate_vector_dimensions(vectors, dimensions)
        return vectors, identity

    @staticmethod
    def _validate_vector_dimensions(
        vectors: list[list[float]],
        dimensions: int,
    ) -> None:
        has_invalid_dimensions = any(
            not isinstance(vector, list) or len(vector) != dimensions
            for vector in vectors
        )
        if has_invalid_dimensions:
            raise ValueError("vector dimensions do not match embedding_spec")


def get_embedding_service() -> EmbeddingService:
    return EmbeddingService.get_instance()

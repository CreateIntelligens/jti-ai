import logging
import os
from typing import List, Optional, Union

import httpx
import numpy as np

from app.services.embedding.errors import EmbeddingEncodingError

logger = logging.getLogger(__name__)

# Chunk remote payloads so a large backfill batch doesn't post one huge body.
_REMOTE_CHUNK_SIZE = 64
_REMOTE_TIMEOUT_S = 120.0


class EmbeddingService:
    """HTTP client for the standalone embedding service.

    GPU embedding lives in its own process (see docker/embedding); this class
    only forwards encode requests over HTTP. EMBEDDING_SERVICE_URL is required
    — there is no in-process model fallback.
    """

    _instance: Optional['EmbeddingService'] = None

    def __init__(self, service_url: Optional[str] = None):
        self.service_url = service_url or os.getenv("EMBEDDING_SERVICE_URL")
        if not self.service_url:
            raise EmbeddingEncodingError(
                "EMBEDDING_SERVICE_URL is not set; the embedding service is required."
            )

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

    def encode(
        self,
        texts: Union[str, List[str]],
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
        url = f"{self.service_url.rstrip('/')}/embed"
        vectors: List[List[float]] = []
        try:
            with httpx.Client(timeout=_REMOTE_TIMEOUT_S) as client:
                for start in range(0, len(texts), _REMOTE_CHUNK_SIZE):
                    batch = texts[start:start + _REMOTE_CHUNK_SIZE]
                    resp = client.post(
                        url,
                        json={"texts": batch, "input_type": input_type},
                    )
                    resp.raise_for_status()
                    vectors.extend(resp.json()["vectors"])
        except (httpx.HTTPError, KeyError, ValueError) as e:
            logger.error(f"Remote encoding failed: {e}")
            raise EmbeddingEncodingError(f"Failed to encode texts: {e}")
        return np.asarray(vectors, dtype=np.float32)


def get_embedding_service() -> EmbeddingService:
    return EmbeddingService.get_instance()

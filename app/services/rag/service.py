import logging
import os
import time
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from app.services.embedding.service import get_embedding_service
from app.services.vector_store.lancedb import get_lancedb_store

logger = logging.getLogger(__name__)


class RAGPipeline:
    """Orchestrates the RAG retrieval flow."""

    _DEFAULT_DISTANCE_THRESHOLD = 0.85

    def __init__(self):
        self._embedding_service = None
        self._vector_store = None

    @property
    def embedding_service(self):
        if self._embedding_service is None:
            self._embedding_service = get_embedding_service()
        return self._embedding_service

    @property
    def vector_store(self):
        if self._vector_store is None:
            self._vector_store = get_lancedb_store()
        return self._vector_store

    @property
    def distance_threshold(self) -> float:
        return float(os.getenv("RAG_DISTANCE_THRESHOLD", str(self._DEFAULT_DISTANCE_THRESHOLD)))

    def retrieve(
        self,
        query: str,
        language: str = "zh",
        source_type: Optional[str | List[str]] = None,
        top_k: int = 5,
    ) -> Tuple[Optional[str], Optional[List[Dict[str, Any]]]]:
        """Retrieves relevant context from the local vector store.

        Results with _distance >= DISTANCE_THRESHOLD are filtered out.
        """
        t0 = time.time()
        try:
            query_vector = self.embedding_service.encode(query, input_type="query")
            return self._search_and_format(
                query_vector,
                query,
                language,
                source_type,
                top_k,
                t0,
            )
        except Exception as e:
            logger.error(f"[RAG Pipeline] Retrieval failed: {e}")
            return None, None

    def _search_and_format(
        self,
        query_vector,
        query: str,
        language: str,
        source_type: Optional[str | List[str]],
        top_k: int,
        t0: float,
    ) -> Tuple[Optional[str], Optional[List[Dict[str, Any]]]]:
        """Shared post-embedding path: vector search, threshold filter, format."""
        if isinstance(query_vector, np.ndarray) and query_vector.ndim > 1:
            query_vector = query_vector[0]

        results = self.vector_store.search(
            query_vector, top_k=top_k, language=language, source_type=source_type
        )

        raw_count = len(results)
        threshold = self.distance_threshold
        results = [r for r in results if r.get("_distance", 999) < threshold]

        if not results:
            logger.info(
                "[RAG] No relevant results for '%s...' (all %d above threshold %.3f)",
                query[:30],
                raw_count,
                threshold,
            )
            return None, None

        kb_result = "\n---\n".join(r.get("text", "") for r in results)

        citations = [
            {
                "uri": r.get("metadata", {}).get("path") or r.get("file_id", "unknown"),
                "title": r.get("metadata", {}).get("display_name")
                or r.get("file_id", "Resource"),
                "text": r.get("text", ""),
                "_distance": float(r.get("_distance", 999)),
                **({"image_id": r["image_id"]} if r.get("image_id") else {}),
                **({"url": r["url"]} if r.get("url") else {}),
            }
            for r in results
        ]

        distances = [f"{r['_distance']:.3f}" for r in results]
        logger.info(
            "[RAG] %d/%d results in %.0fms | distances=%s",
            len(results),
            raw_count,
            (time.time() - t0) * 1000,
            distances,
        )
        return kb_result, citations


_rag_pipeline: Optional[RAGPipeline] = None


def get_rag_pipeline() -> RAGPipeline:
    global _rag_pipeline
    if _rag_pipeline is None:
        _rag_pipeline = RAGPipeline()
    return _rag_pipeline

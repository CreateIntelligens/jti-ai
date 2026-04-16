import logging
import os
import time
import numpy as np
from typing import List, Dict, Any, Tuple, Optional

from app.services.embedding.service import get_embedding_service
from app.services.vector_store.lancedb import get_lancedb_store

logger = logging.getLogger(__name__)

class RAGPipeline:
    """Orchestrates the RAG retrieval flow."""
    
    def __init__(self):
        # Using factory functions for lazy initialization
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

    _DEFAULT_DISTANCE_THRESHOLD = 0.85

    @property
    def distance_threshold(self) -> float:
        return float(os.getenv("RAG_DISTANCE_THRESHOLD", str(self._DEFAULT_DISTANCE_THRESHOLD)))

    def retrieve(
        self,
        query: str,
        language: str = "zh",
        source_type: Optional[str] = None,
        top_k: int = 5
    ) -> Tuple[Optional[str], Optional[List[Dict[str, Any]]]]:
        """Retrieves relevant context from the local vector store.

        Results with _distance >= DISTANCE_THRESHOLD are filtered out.
        """
        t0 = time.time()
        try:
            # 1. Embed query
            query_vector = self.embedding_service.encode(query, input_type="query")
            if isinstance(query_vector, np.ndarray) and query_vector.ndim > 1:
                query_vector = query_vector[0]

            # 2. Search
            results = self.vector_store.search(
                query_vector,
                top_k=top_k,
                language=language,
                source_type=source_type
            )

            # 3. Filter by distance threshold
            raw_count = len(results)
            results = [r for r in results if r.get("_distance", 999) < self.distance_threshold]

            if not results:
                logger.info(f"[RAG] No relevant results for '{query[:30]}...' (all {raw_count} above threshold {self.distance_threshold})")
                return None, None

            # 4. Format context and citations
            kb_result = "\n---\n".join([r.get("text", "") for r in results])

            citations = [{
                "uri": r.get("metadata", {}).get("path") or r.get("file_id", "unknown"),
                "title": r.get("metadata", {}).get("display_name") or r.get("file_id", "Resource"),
                "text": r.get("text", ""),
                **({"image_id": r["image_id"]} if r.get("image_id") else {}),
            } for r in results]

            distances = [f"{r['_distance']:.3f}" for r in results]
            logger.info(f"[RAG] {len(results)}/{raw_count} results in {(time.time() - t0)*1000:.0f}ms | distances={distances}")
            return kb_result, citations

        except Exception as e:
            logger.error(f"[RAG Pipeline] Retrieval failed: {e}")
            return None, None

_rag_pipeline: Optional[RAGPipeline] = None

def get_rag_pipeline() -> RAGPipeline:
    global _rag_pipeline
    if _rag_pipeline is None:
        _rag_pipeline = RAGPipeline()
    return _rag_pipeline

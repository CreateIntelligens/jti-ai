import logging
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

    def retrieve(
        self,
        query: str,
        language: str = "zh",
        source_type: Optional[str] = None,
        top_k: int = 5
    ) -> Tuple[Optional[str], Optional[List[Dict[str, Any]]]]:
        """Retrieves relevant context from the local vector store."""
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
            
            if not results:
                logger.info(f"[RAG Pipeline] No results for '{query[:30]}...'")
                return None, None
                
            # 3. Format context and citations
            kb_result = "\n---\n".join([r.get("text", "") for r in results])
            
            citations = [{
                "uri": r.get("metadata", {}).get("path") or r.get("file_id", "unknown"),
                "title": r.get("metadata", {}).get("display_name") or r.get("file_id", "Resource"),
                "text": r.get("text", "")
            } for r in results]
            
            logger.info(f"[RAG Pipeline] Retrieval took {(time.time() - t0)*1000:.0f}ms (k={len(results)})")
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

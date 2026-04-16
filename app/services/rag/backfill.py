import csv
import hashlib
import io
import logging
from typing import List, Dict, Any, Optional

from app.services.rag.chunker import SemanticChunker
from app.services.embedding.service import get_embedding_service
from app.services.vector_store.lancedb import get_lancedb_store
from app.services.vector_store.mongodb_backup import get_mongodb_backup
from app.services.knowledge_store import get_knowledge_store
from app.services.hciot.knowledge_store import get_hciot_knowledge_store

logger = logging.getLogger(__name__)

class BackfillService:
    """Handles incremental document indexing into the local vector store."""
    
    def __init__(self):
        self._chunker = None
        self._embedding_service = None
        self._lancedb_store = None
        self._mongodb_backup = None

    @property
    def chunker(self) -> SemanticChunker:
        if self._chunker is None:
            self._chunker = SemanticChunker()
        return self._chunker

    @property
    def embedding_service(self):
        if self._embedding_service is None:
            self._embedding_service = get_embedding_service()
        return self._embedding_service

    @property
    def lancedb_store(self):
        if self._lancedb_store is None:
            self._lancedb_store = get_lancedb_store()
        return self._lancedb_store

    @property
    def mongodb_backup(self):
        if self._mongodb_backup is None:
            self._mongodb_backup = get_mongodb_backup()
        return self._mongodb_backup

    @staticmethod
    def _normalize_image_id(raw: str) -> str | None:
        """正規化 image_id：去路徑、去副檔名、去 query string。"""
        value = (raw or "").strip()
        if not value:
            return None
        if "=" in value:
            value = value.split("=", 1)[-1].strip()
        # Remove path prefix and extension
        value = value.split("/")[-1].rsplit(".", 1)[0].strip()
        return value or None

    @staticmethod
    def _chunk_csv_by_row(text: str) -> list[tuple[str, str | None]]:
        """CSV 每一行當作一個 chunk。回傳 (chunk_text, image_id) tuples。"""
        reader = csv.DictReader(io.StringIO(text))
        results: list[tuple[str, str | None]] = []
        for row in reader:
            parts = [f"{k}: {v}" for k, v in row.items() if v and v.strip() and k != "img"]
            if not parts:
                continue
            chunk_text = ", ".join(parts)
            image_id = BackfillService._normalize_image_id(row.get("img", ""))
            results.append((chunk_text, image_id))
        return results

    def _compute_fingerprint(self, data: bytes) -> str:
        """Computes SHA256 hash of file content."""
        return hashlib.sha256(data).hexdigest()

    def _get_files_and_data(self, source_type: str, language: str):
        """Yields (filename, display_name, data_bytes) from the correct MongoDB store."""
        if source_type == "hciot":
            store = get_hciot_knowledge_store()
            files = store.list_files(language)
            for f in files:
                filename = f.get("filename") or f.get("name", "")
                if not filename.lower().endswith(('.csv', '.txt', '.md', '.docx')):
                    continue
                doc = store.get_file(language, filename)
                if doc and doc.get("data"):
                    yield filename, f.get("display_name", filename), doc["data"]
        else:
            store = get_knowledge_store()
            files = store.list_files(language, namespace="jti")
            for f in files:
                filename = f.get("filename") or f.get("name", "")
                if not filename.lower().endswith(('.csv', '.txt', '.md', '.docx')):
                    continue
                data = store.get_file_data(language, filename, namespace="jti")
                if data:
                    yield filename, f.get("display_name", filename), data

    def run_backfill(self, source_type: str, language: str):
        """Runs incremental backfill for a specific source and language."""
        try:
            items = list(self._get_files_and_data(source_type, language))
        except Exception as e:
            logger.error(f"[Backfill] Failed to list files for {source_type}/{language}: {e}")
            return

        logger.debug(f"[Backfill] Scanning {len(items)} files in {source_type}/{language}...")

        for filename, display_name, data in items:
            self.index_single_file(
                source_type=source_type,
                language=language,
                filename=filename,
                data=data,
                metadata={"display_name": display_name}
            )

    def delete_from_rag(self, source_type: str, filename: str, language: str | None = None):
        """Removes a file's chunks from the local RAG store."""
        full_source_type = f"{source_type}_knowledge"
        try:
            self.lancedb_store.delete_by_file(filename, full_source_type, source_language=language)
            logger.info(f"[RAG] Removed {filename} from {full_source_type}")
        except Exception as e:
            logger.error(f"[RAG] Failed to delete {filename} from LanceDB: {e}")

    def index_single_file(self, source_type: str, language: str, filename: str, data: bytes, metadata: Optional[Dict] = None):
        """Indexes a single file into the local RAG store. Skips if content is unchanged."""
        full_source_type = f"{source_type}_knowledge"
        fingerprint = self._compute_fingerprint(data)

        existing_fp = self.lancedb_store.get_file_fingerprint(filename, full_source_type, language)
        if existing_fp == fingerprint:
            logger.debug(f"[RAG] Skipping {filename} (fingerprint unchanged)")
            return
        
        try:
            text = data.decode("utf-8", errors="ignore").strip()
            if not text:
                return

            if filename.lower().endswith(".csv"):
                csv_rows = self._chunk_csv_by_row(text)
                chunks_text = [t for t, _ in csv_rows]
                image_ids = [img for _, img in csv_rows]
            else:
                chunks_text = self.chunker.chunk_text(text)
                image_ids = [None] * len(chunks_text)
            if not chunks_text:
                return

            embeddings = self.embedding_service.encode(chunks_text)

            base_metadata = {"path": filename}
            if metadata:
                base_metadata.update(metadata)

            records = [{
                "text": txt,
                "vector": vec.tolist() if hasattr(vec, "tolist") else list(vec),
                "file_id": filename,
                "source_language": language,
                "source_type": full_source_type,
                "chunk_index": i,
                "file_fingerprint": fingerprint,
                "image_id": img_id or "",
                "metadata": base_metadata
            } for i, (txt, vec, img_id) in enumerate(zip(chunks_text, embeddings, image_ids))]
                
            # Atomic Replace in current LanceDB table
            self.lancedb_store.delete_by_file(filename, full_source_type, source_language=language)
            self.lancedb_store.insert_chunks(records)
            self.mongodb_backup.sync_to_mongodb(records)
            
            logger.debug(f"[RAG] Indexed {filename} ({len(records)} chunks)")
        except Exception as e:
            logger.error(f"[RAG] Failed to index {filename}: {e}")


_backfill_service: Optional[BackfillService] = None

def get_backfill_service() -> BackfillService:
    global _backfill_service
    if _backfill_service is None:
        _backfill_service = BackfillService()
    return _backfill_service

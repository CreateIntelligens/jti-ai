import csv
import hashlib
import io
import logging
from typing import Dict, Optional

from app.services.rag.chunker import SemanticChunker
from app.services.embedding.service import get_embedding_service
from app.services.vector_store.lancedb import get_lancedb_store
from app.services.vector_store.mongodb_backup import get_mongodb_backup
from app.services.hciot.knowledge_store import get_hciot_knowledge_store
from app.services.jti.knowledge_store import get_jti_knowledge_store

logger = logging.getLogger(__name__)
_SUPPORTED_KNOWLEDGE_EXTENSIONS = (".csv", ".txt", ".md", ".docx")


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

    # Columns excluded from chunk text — kept in row metadata / citations but
    # not embedded, since they carry no semantic value (or actively dilute it).
    _NON_EMBEDDED_FIELDS = frozenset({"img", "url", "index"})

    @staticmethod
    def _chunk_csv_by_row(text: str, topic_prefix: str = "") -> list[tuple[str, str | None]]:
        """CSV 每一行當作一個 chunk。回傳 (chunk_text, image_id) tuples。
        topic_prefix 會被前綴到每個 chunk_text，讓 embedding 帶有 topic 語意。"""
        reader = csv.DictReader(io.StringIO(text))
        results: list[tuple[str, str | None]] = []
        for row in reader:
            parts = [
                f"{k}: {v}"
                for k, v in row.items()
                if v and v.strip() and k not in BackfillService._NON_EMBEDDED_FIELDS
            ]
            if not parts:
                continue
            body = ", ".join(parts)
            chunk_text = f"{topic_prefix}{body}" if topic_prefix else body
            image_id = BackfillService._normalize_image_id(row.get("img", ""))
            results.append((chunk_text, image_id))
        return results

    @staticmethod
    def _extract_topic_info(doc: dict | None) -> dict[str, str]:
        """Pull topic/category labels out of a doc dict (e.g. from list_files
        or get_file). Empty strings on miss."""
        if not doc:
            return {"topic_id": "", "topic_label_zh": "", "topic_label_en": "", "category_label_zh": "", "category_label_en": ""}
        return {
            "topic_id": doc.get("topic_id") or "",
            "topic_label_zh": doc.get("topic_label_zh") or "",
            "topic_label_en": doc.get("topic_label_en") or "",
            "category_label_zh": doc.get("category_label_zh") or "",
            "category_label_en": doc.get("category_label_en") or "",
        }

    @staticmethod
    def _fetch_topic_info(source_type: str, language: str, filename: str) -> dict[str, str]:
        """Fallback path when caller didn't pre-fetch topic info. Only hciot stores topic metadata."""
        if source_type != "hciot":
            return BackfillService._extract_topic_info(None)
        try:
            doc = get_hciot_knowledge_store().get_file(language, filename)
        except Exception:
            doc = None
        return BackfillService._extract_topic_info(doc)

    @staticmethod
    def _build_topic_prefix(topic_info: dict[str, str], language: str) -> str:
        topic_label = topic_info.get(f"topic_label_{language}") or topic_info.get("topic_label_zh")
        category_label = topic_info.get(f"category_label_{language}") or topic_info.get("category_label_zh")
        if topic_label and category_label:
            return f"【{category_label} / {topic_label}】"
        if topic_label:
            return f"【{topic_label}】"
        if category_label:
            return f"【{category_label}】"
        return ""

    def _compute_fingerprint(self, data: bytes) -> str:
        """Computes SHA256 hash of file content."""
        return hashlib.sha256(data).hexdigest()

    @staticmethod
    def _is_supported_knowledge_file(filename: str) -> bool:
        return filename.lower().endswith(_SUPPORTED_KNOWLEDGE_EXTENSIONS)

    @staticmethod
    def _iter_store_files(store, language: str, fetch_data):
        for file_info in store.list_files(language):
            filename = file_info.get("filename") or file_info.get("name", "")
            if not BackfillService._is_supported_knowledge_file(filename):
                continue

            data = fetch_data(store, language, filename)
            if data:
                yield filename, file_info.get("display_name", filename), data, file_info

    @staticmethod
    def _fetch_hciot_file_data(store, language: str, filename: str) -> bytes | None:
        doc = store.get_file(language, filename)
        if not doc:
            return None
        return doc.get("data")

    @staticmethod
    def _fetch_jti_file_data(store, language: str, filename: str) -> bytes | None:
        return store.get_file_data(language, filename)

    def _get_files_and_data(self, source_type: str, language: str):
        """Yields (filename, display_name, data_bytes) from the correct MongoDB store."""
        if source_type == "hciot":
            store = get_hciot_knowledge_store()
            yield from self._iter_store_files(store, language, self._fetch_hciot_file_data)
            return

        store = get_jti_knowledge_store()
        yield from self._iter_store_files(store, language, self._fetch_jti_file_data)

    def run_backfill(self, source_type: str, language: str, force: bool = False):
        """Runs incremental backfill for a specific source and language."""
        try:
            items = list(self._get_files_and_data(source_type, language))
        except Exception as e:
            logger.error(f"[Backfill] Failed to list files for {source_type}/{language}: {e}")
            return

        logger.debug(f"[Backfill] Scanning {len(items)} files in {source_type}/{language}...")

        for filename, display_name, data, file_info in items:
            self.index_single_file(
                source_type=source_type,
                language=language,
                filename=filename,
                data=data,
                metadata={"display_name": display_name},
                force=force,
                topic_info=BackfillService._extract_topic_info(file_info),
            )

    def delete_from_rag(self, source_type: str, filename: str, language: str | None = None):
        """Removes a file's chunks from the local RAG store."""
        full_source_type = f"{source_type}_knowledge"
        try:
            self.lancedb_store.delete_by_file(filename, full_source_type, source_language=language)
            logger.info(f"[RAG] Removed {filename} from {full_source_type}")
        except Exception as e:
            logger.error(f"[RAG] Failed to delete {filename} from LanceDB: {e}")

    def index_single_file(self, source_type: str, language: str, filename: str, data: bytes, metadata: Optional[Dict] = None, force: bool = False, topic_info: Optional[Dict[str, str]] = None):
        """Indexes a single file into the local RAG store. Skips if content is unchanged unless force=True.
        Pass topic_info if already fetched (e.g. from list_files) to avoid an extra Mongo query."""
        full_source_type = f"{source_type}_knowledge"
        fingerprint = self._compute_fingerprint(data)

        if not force:
            existing_fp = self.lancedb_store.get_file_fingerprint(filename, full_source_type, language)
            if existing_fp == fingerprint:
                logger.debug(f"[RAG] Skipping {filename} (fingerprint unchanged)")
                return
        
        try:
            text = data.decode("utf-8", errors="ignore").strip()
            if not text:
                return

            if topic_info is None:
                topic_info = self._fetch_topic_info(source_type, language, filename)
            topic_prefix = self._build_topic_prefix(topic_info, language)

            if filename.lower().endswith(".csv"):
                csv_rows = self._chunk_csv_by_row(text, topic_prefix=topic_prefix)
                chunks_text = [t for t, _ in csv_rows]
                image_ids = [img for _, img in csv_rows]
            else:
                raw_chunks = self.chunker.chunk_text(text)
                chunks_text = [f"{topic_prefix}{c}" if topic_prefix else c for c in raw_chunks]
                image_ids = [None] * len(chunks_text)
            if not chunks_text:
                return

            embeddings = self.embedding_service.encode(chunks_text)

            # NOTE: topic info is encoded into the chunk text via topic_prefix above.
            # We intentionally do NOT add topic_id as a top-level LanceDB column,
            # because that would require rebuilding the table schema.
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

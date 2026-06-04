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
from app.services.hciot.topic_store import get_hciot_topic_store
from app.services.jti.knowledge_store import get_jti_knowledge_store

logger = logging.getLogger(__name__)
_SUPPORTED_KNOWLEDGE_EXTENSIONS = (".csv", ".txt", ".md", ".docx")


def _knowledge_source_type(source_type: str) -> str:
    return f"{source_type}_knowledge"


class BackfillService:
    """Handles incremental document indexing into the local vector store."""

    # Default text chunking for legacy free-form uploads. QA CSVs still use row
    # chunking through _chunk_csv_by_row.
    _CHUNK_SIZE_TOKENS = 200
    _CHUNK_OVERLAP_TOKENS = 30

    # Larger chunks for non-QA document uploads so paragraphs stay intact.
    _DOC_CHUNK_SIZE_TOKENS = 500
    _DOC_CHUNK_OVERLAP_TOKENS = 80

    # File-backed sources that have an authoritative store to rebuild from and
    # are safe to prune against. `general` is intentionally excluded: it has no
    # source-file registry here (it is dynamic, restored from Mongo via
    # restore_to_lancedb), so pruning it against another store's file list
    # would wipe all its data. Guard against accidental backfill of such types.
    _BACKFILL_SOURCES = ("jti", "hciot")
    _TEST_ORPHAN_PREFIXES = ("test_", "qa_", "QA254-")

    def __init__(self):
        self._chunker: Optional[SemanticChunker] = None
        self._doc_chunker: Optional[SemanticChunker] = None
        self._embedding_service = None
        self._lancedb_store = None
        self._mongodb_backup = None

    @property
    def chunker(self) -> SemanticChunker:
        if self._chunker is None:
            self._chunker = SemanticChunker(
                chunk_size_tokens=self._CHUNK_SIZE_TOKENS,
                chunk_overlap_tokens=self._CHUNK_OVERLAP_TOKENS,
            )
        return self._chunker

    @property
    def doc_chunker(self) -> SemanticChunker:
        """Chunker for the non-QA document channel (larger chunks)."""
        if self._doc_chunker is None:
            self._doc_chunker = SemanticChunker(
                chunk_size_tokens=self._DOC_CHUNK_SIZE_TOKENS,
                chunk_overlap_tokens=self._DOC_CHUNK_OVERLAP_TOKENS,
            )
        return self._doc_chunker

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
    def _chunk_csv_by_row(text: str, topic_prefix: str = "") -> list[tuple[str, str | None, str]]:
        """CSV 每一行當作一個 chunk。回傳 (chunk_text, image_id, url) tuples。
        topic_prefix 會被前綴到每個 chunk_text，讓 embedding 帶有 topic 語意。"""
        reader = csv.DictReader(io.StringIO(text))
        results: list[tuple[str, str | None, str]] = []
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
            url = (row.get("url") or "").strip()
            results.append((chunk_text, image_id, url))
        return results

    @staticmethod
    def _extract_topic_info(doc: dict | None) -> dict[str, str]:
        """Pull topic/category labels out of a doc dict (e.g. from list_files
        or get_file). Empty strings on miss. Labels are flat strings tied to
        the doc's own language partition."""
        if not doc:
            return {"topic_id": "", "topic_label": "", "category_label": ""}
        return {
            "topic_id": doc.get("topic_id") or "",
            "topic_label": doc.get("topic_label") or "",
            "category_label": doc.get("category_label") or "",
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
    def _merge_topic_store_labels(source_type: str, language: str, topic_info: dict[str, str]) -> dict[str, str]:
        """If the doc-level labels are usable, return as-is. Otherwise fall back
        to topic_store, which still keeps bilingual `labels: {zh, en}` /
        `category_labels: {zh, en}` dicts — pick the slot matching `language`."""
        if source_type != "hciot":
            return topic_info

        topic_id = topic_info.get("topic_id") or ""
        if not topic_id:
            return topic_info

        topic_label = topic_info.get("topic_label") or ""
        category_label = topic_info.get("category_label") or ""
        if topic_label and category_label:
            return topic_info

        try:
            topic = get_hciot_topic_store(language).get_topic(topic_id)
        except Exception as e:
            logger.warning(f"[Backfill] Failed to load HCIoT topic labels for {topic_id}/{language}: {e}")
            return topic_info

        if not topic:
            return topic_info

        merged = dict(topic_info)
        labels = topic.get("labels") or {}
        category_labels = topic.get("category_labels") or {}
        store_topic_label = labels.get(language) or ""
        store_category_label = category_labels.get(language) or ""
        if store_topic_label and not merged.get("topic_label"):
            merged["topic_label"] = store_topic_label
        if store_category_label and not merged.get("category_label"):
            merged["category_label"] = store_category_label
        return merged

    @staticmethod
    def _build_topic_prefix(topic_info: dict[str, str]) -> str:
        topic_label = topic_info.get("topic_label") or ""
        category_label = topic_info.get("category_label") or ""
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
    def _extract_file_text(filename: str, data: bytes) -> str:
        if filename.lower().endswith(".docx"):
            from app.routers.knowledge_utils import extract_docx_text

            return extract_docx_text(data).strip()
        return data.decode("utf-8-sig", errors="ignore").strip()

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
        """Yields source files and file metadata from the correct MongoDB store."""
        if source_type == "hciot":
            store = get_hciot_knowledge_store()
            yield from self._iter_store_files(store, language, self._fetch_hciot_file_data)
            return

        store = get_jti_knowledge_store()
        yield from self._iter_store_files(store, language, self._fetch_jti_file_data)

    def run_backfill(self, source_type: str, language: str, force: bool = False):
        """Runs incremental backfill for a specific source and language.
        Always prunes orphans (indexed file_ids absent from the store registry).
        Only supports file-backed sources; dynamic stores (general) are restored
        from Mongo backup instead and must not be backfilled here."""
        if source_type not in self._BACKFILL_SOURCES:
            logger.error(
                "[Backfill] Refusing to backfill unsupported source_type %r "
                "(no source-file registry; would mis-prune). Supported: %s",
                source_type, self._BACKFILL_SOURCES,
            )
            return
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

        live_file_ids = {filename for filename, *_ in items}

        # API-injected stress-test ids have no source-file registry entry.
        self._prune_test_orphans(source_type, language)
        self._prune_orphans(source_type, language, live_file_ids)

    def _prune_test_orphans(self, source_type: str, language: str) -> None:
        """主動偵測並清除前綴型測試/壓測孤兒（如 test_*, qa_*, QA254-*）。"""
        full_source_type = _knowledge_source_type(source_type)
        try:
            indexed = self.lancedb_store.list_file_ids(full_source_type, language)
        except Exception as e:
            logger.error(f"[Backfill] Failed to list file ids from LanceDB for test pruning: {e}")
            indexed = set()

        try:
            indexed |= self.mongodb_backup.list_file_ids(full_source_type, language)
        except Exception as e:
            logger.error(f"[Backfill] Failed to list file ids from MongoDB for test pruning: {e}")

        test_orphans = {
            f_id for f_id in indexed
            if f_id.startswith(self._TEST_ORPHAN_PREFIXES)
        }

        if test_orphans:
            logger.info(f"[Backfill] Proactively pruning {len(test_orphans)} test/qa orphans in {source_type}/{language}")
            for orphan in test_orphans:
                self.delete_from_rag(source_type, orphan, language=language)

    def _prune_orphans(self, source_type: str, language: str, live_files: set[str]) -> None:
        """Remove file_ids from LanceDB / mongodb_backup that aren't in live_files.
        Only safe for file-backed sources after their full store registry has been read."""
        full_source_type = _knowledge_source_type(source_type)
        indexed = self.lancedb_store.list_file_ids(full_source_type, language)
        indexed |= self.mongodb_backup.list_file_ids(full_source_type, language)
        orphans = indexed - live_files
        if not orphans:
            return
        logger.info(f"[Backfill] Pruning {len(orphans)} orphan file_ids in {source_type}/{language}")
        for orphan in orphans:
            self.delete_from_rag(source_type, orphan, language=language)

    def delete_from_rag(self, source_type: str, filename: str, language: str | None = None):
        """Removes a file's chunks from the local RAG store and its mongo mirror."""
        full_source_type = _knowledge_source_type(source_type)
        try:
            self.lancedb_store.delete_by_file(filename, full_source_type, source_language=language)
        except Exception as e:
            logger.error(f"[RAG] Failed to delete {filename} from LanceDB: {e}")
        try:
            self.mongodb_backup.delete_by_file(filename, full_source_type)
        except Exception as e:
            logger.error(f"[RAG] Failed to delete {filename} from mongodb_backup: {e}")
        logger.info(f"[RAG] Removed {filename} from {full_source_type}")

    def index_single_file(
        self,
        source_type: str,
        language: str,
        filename: str,
        data: bytes,
        metadata: Optional[Dict] = None,
        force: bool = False,
        topic_info: Optional[Dict[str, str]] = None,
        force_text_chunking: bool = False,
    ):
        """Indexes a single file into the local RAG store. Skips if content is unchanged unless force=True.
        Pass topic_info if already fetched (e.g. from list_files) to avoid an extra Mongo query."""
        full_source_type = _knowledge_source_type(source_type)
        fingerprint = self._compute_fingerprint(data)

        if not force:
            existing_fp = self.lancedb_store.get_file_fingerprint(filename, full_source_type, language)
            if existing_fp == fingerprint:
                logger.debug(f"[RAG] Skipping {filename} (fingerprint unchanged)")
                return
        
        try:
            filename_lower = filename.lower()
            text = self._extract_file_text(filename, data)
            if not text:
                return

            if topic_info is None:
                topic_info = self._fetch_topic_info(source_type, language, filename)
            topic_info = self._merge_topic_store_labels(source_type, language, topic_info)
            topic_prefix = self._build_topic_prefix(topic_info)

            if filename_lower.endswith(".csv") and not force_text_chunking:
                csv_rows = self._chunk_csv_by_row(text, topic_prefix=topic_prefix)
                chunks_text = [t for t, _, _ in csv_rows]
                image_ids = [img for _, img, _ in csv_rows]
                urls = [u for _, _, u in csv_rows]
            else:
                chunker = self.doc_chunker if force_text_chunking else self.chunker
                raw_chunks = chunker.chunk_text(text)
                chunks_text = [f"{topic_prefix}{c}" if topic_prefix else c for c in raw_chunks]
                image_ids = [None] * len(chunks_text)
                urls = [""] * len(chunks_text)
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
                "url": url or "",
                "metadata": base_metadata
            } for i, (txt, vec, img_id, url) in enumerate(zip(chunks_text, embeddings, image_ids, urls))]
                
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

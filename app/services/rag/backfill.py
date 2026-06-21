import csv
import hashlib
import io
import logging
import threading
from typing import Dict, Optional

from app.services.rag.chunker import SemanticChunker
from app.services.embedding.service import get_embedding_service
from app.services.vector_store.lancedb import get_lancedb_store
from app.services.knowledge_store import get_knowledge_store
from app.services.general.knowledge_store import get_general_knowledge_store
from app.services.hciot.knowledge_store import get_hciot_knowledge_store
from app.services.hciot.topic_store import get_hciot_topic_store
from app.services.jti.knowledge_store import get_jti_knowledge_store

logger = logging.getLogger(__name__)
_SUPPORTED_KNOWLEDGE_EXTENSIONS = (".csv", ".txt", ".md", ".docx")
_GENERAL_NAMESPACE = "general"


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

    # Sources with an authoritative MongoDB-backed store to rebuild from, safe
    # to prune against. `general` is included: its raw files live in the shared
    # knowledge store under namespace="general", keyed by store_name (passed as
    # `language`), so it backfills/reembeds exactly like jti/hciot. `esg` is a
    # fixed managed app whose files live in the shared knowledge store under
    # namespace="esg", partitioned by zh/en like jti/hciot — so its registry is
    # authoritative and pruning is safe. Embedding is a local model, so
    # reembedding on every boot is free — there is no Mongo vector mirror to
    # restore from. Anything not listed here has no source-file registry and
    # must not be backfilled (it would mis-prune and wipe data).
    _BACKFILL_SOURCES = ("jti", "hciot", "general", "esg")
    _TEST_ORPHAN_PREFIXES = ("test_", "qa_", "QA254-")

    def __init__(self):
        self._chunker: Optional[SemanticChunker] = None
        self._doc_chunker: Optional[SemanticChunker] = None
        self._embedding_service = None
        self._lancedb_store = None
        # Per-file locks so concurrent index calls for the same file serialize:
        # without this, two callers both embed and both write, producing
        # duplicate chunks and wasted embedding work.
        self._file_locks: Dict[str, threading.Lock] = {}
        self._file_locks_guard = threading.Lock()

    def _file_lock(self, key: str) -> threading.Lock:
        with self._file_locks_guard:
            return self._file_locks.setdefault(key, threading.Lock())

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
    def _iter_store_files(files, fetch_data):
        for file_info in files:
            filename = file_info.get("filename") or file_info.get("name", "")
            if not BackfillService._is_supported_knowledge_file(filename):
                continue

            data = fetch_data(filename)
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

    @staticmethod
    def _fetch_general_file_data(store, store_name: str, filename: str) -> bytes | None:
        return store.get_file_data(store_name, filename, namespace=_GENERAL_NAMESPACE)

    @staticmethod
    def _general_file_lists(store_name: str):
        """List general files from both coexisting stores, new (per-store QA
        workspace) first then the legacy single-file store, deduped by filename."""
        new_store = get_general_knowledge_store()
        old_store = get_knowledge_store()
        seen: set[str] = set()
        merged: list[dict] = []
        for meta in new_store.list_files(store_name):
            name = meta.get("filename") or meta.get("name", "")
            if name and name not in seen:
                seen.add(name)
                merged.append({**meta, "_source": "new"})
        for meta in old_store.list_files(store_name, namespace=_GENERAL_NAMESPACE):
            name = meta.get("filename") or meta.get("name", "")
            if name and name not in seen:
                seen.add(name)
                merged.append({**meta, "_source": "old"})
        return new_store, old_store, merged

    def _get_files_and_data(self, source_type: str, language: str):
        """Yields source files and file metadata from the correct MongoDB store.
        general partitions by store_name (passed as `language`) under the shared
        knowledge store's "general" namespace; jti/hciot partition by zh/en."""
        if source_type == "general":
            new_store, old_store, files = self._general_file_lists(language)
            # Each file knows which store it came from (`_source`), so fetch from
            # that store directly instead of probing the new store for every file.
            source_by_name = {
                (meta.get("filename") or meta.get("name", "")): meta.get("_source")
                for meta in files
            }

            def fetch_general(filename: str) -> bytes | None:
                if source_by_name.get(filename) == "old":
                    return self._fetch_general_file_data(old_store, language, filename)
                doc = new_store.get_file(language, filename)
                return doc.get("data") if doc else None

            yield from self._iter_store_files(files, fetch_general)
            return

        if source_type == "hciot":
            store = get_hciot_knowledge_store()
            yield from self._iter_store_files(
                store.list_files(language),
                lambda filename: self._fetch_hciot_file_data(store, language, filename),
            )
            return

        if source_type == "esg":
            # ESG is a fixed managed app with a simple file knowledge base under
            # namespace "esg", partitioned by language (zh/en) like hciot/jti.
            from app.services.knowledge_store import get_namespaced_knowledge_store

            store = get_namespaced_knowledge_store("esg")
            yield from self._iter_store_files(
                store.list_files(language),
                lambda filename: self._fetch_hciot_file_data(store, language, filename),
            )
            return

        store = get_jti_knowledge_store()
        yield from self._iter_store_files(
            store.list_files(language),
            lambda filename: self._fetch_jti_file_data(store, language, filename),
        )

    def run_backfill(self, source_type: str, language: str, force: bool = False):
        """Runs incremental backfill for a specific source and language.
        Always prunes orphans (indexed file_ids absent from the store registry).
        Supports jti/hciot (language=zh/en) and general (language=store_name);
        all rebuild from their MongoDB-backed store. Other source_types have no
        source-file registry and are refused to avoid mis-pruning."""
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

        test_orphans = {
            f_id for f_id in indexed
            if f_id.startswith(self._TEST_ORPHAN_PREFIXES)
        }

        if test_orphans:
            logger.info(f"[Backfill] Proactively pruning {len(test_orphans)} test/qa orphans in {source_type}/{language}")
            for orphan in test_orphans:
                self.delete_from_rag(source_type, orphan, language=language)

    def _prune_orphans(self, source_type: str, language: str, live_files: set[str]) -> None:
        """Remove file_ids from LanceDB that aren't in live_files.
        Only safe for file-backed sources after their full store registry has been read."""
        full_source_type = _knowledge_source_type(source_type)
        indexed = self.lancedb_store.list_file_ids(full_source_type, language)
        orphans = indexed - live_files
        if not orphans:
            return
        logger.info(f"[Backfill] Pruning {len(orphans)} orphan file_ids in {source_type}/{language}")
        for orphan in orphans:
            self.delete_from_rag(source_type, orphan, language=language)

    def delete_from_rag(self, source_type: str, filename: str, language: str | None = None):
        """Removes a file's chunks from the local RAG store."""
        full_source_type = _knowledge_source_type(source_type)
        try:
            self.lancedb_store.delete_by_file(filename, full_source_type, source_language=language)
        except Exception as e:
            logger.error(f"[RAG] Failed to delete {filename} from LanceDB: {e}")
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

        # Serialize per (file, source_type, language) so concurrent callers
        # don't both embed and write the same file (the cause of duplicate
        # chunks). The fingerprint re-check happens inside the lock, so a
        # caller that waited sees the freshly-written fingerprint and skips.
        lock_key = f"{full_source_type}::{language}::{filename}"
        with self._file_lock(lock_key):
            if not force:
                existing_fp = self.lancedb_store.get_file_fingerprint(filename, full_source_type, language)
                if existing_fp == fingerprint:
                    logger.debug(f"[RAG] Skipping {filename} (fingerprint unchanged)")
                    return

            self._index_single_file_locked(
                source_type=source_type,
                full_source_type=full_source_type,
                language=language,
                filename=filename,
                data=data,
                metadata=metadata,
                topic_info=topic_info,
                force_text_chunking=force_text_chunking,
                fingerprint=fingerprint,
            )

    def _index_single_file_locked(
        self,
        *,
        source_type: str,
        full_source_type: str,
        language: str,
        filename: str,
        data: bytes,
        metadata: Optional[Dict],
        topic_info: Optional[Dict[str, str]],
        force_text_chunking: bool,
        fingerprint: str,
    ):
        """Embed + atomically replace a file's chunks. Caller holds the file lock."""
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
                
            # Atomic delete-then-insert under the store lock so a concurrent
            # writer can't interleave and double-write this file's chunks.
            self.lancedb_store.replace_file_chunks(
                filename, full_source_type, language, records
            )
            
            logger.debug(f"[RAG] Indexed {filename} ({len(records)} chunks)")
        except Exception as e:
            logger.error(f"[RAG] Failed to index {filename}: {e}")


_backfill_service: Optional[BackfillService] = None

def get_backfill_service() -> BackfillService:
    global _backfill_service
    if _backfill_service is None:
        _backfill_service = BackfillService()
    return _backfill_service

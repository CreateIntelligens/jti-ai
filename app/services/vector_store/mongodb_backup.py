import logging
import os
from typing import List, Dict, Any, Optional, Iterator
from datetime import datetime, timezone
from pymongo import UpdateOne
from app.services.mongo_client import get_mongo_db

logger = logging.getLogger(__name__)

# The vector backup is a single shared mirror of every app's RAG chunks,
# discriminated by the source_type column. It is NOT app-scoped despite the
# default DB name — overridable so deployments can relocate it (e.g. off a
# quota-capped cluster) without touching code.
_DEFAULT_BACKUP_DB = os.getenv("VECTOR_BACKUP_DB", "jti_app")


class MongoDBBackup:
    COLLECTION_NAME = "vector_backup"

    def __init__(self, db_name: str):
        self.db = get_mongo_db(db_name)
        self.collection = self.db[self.COLLECTION_NAME]
        # Index creation can fail when the cluster is over its storage quota
        # (Atlas blocks all writes, including index builds). Tolerate it: the
        # backup is best-effort and must never block LanceDB indexing/cleanup.
        try:
            self.collection.create_index([("file_id", 1), ("chunk_index", 1)], unique=True)
            self.collection.create_index([("source_language", 1), ("source_type", 1)])
        except Exception as e:
            logger.warning(f"Failed to create MongoDB indexes for vector backup: {e}")

    def sync_to_mongodb(self, chunks: List[Dict[str, Any]]):
        """Batch upsert chunks to MongoDB."""
        if not chunks:
            return

        now = datetime.now(timezone.utc)
        operations = []
        for chunk in chunks:
            # We store the vector as a list in MongoDB
            doc = dict(chunk)
            doc["synced_at"] = now
            
            operations.append(
                UpdateOne(
                    {"file_id": chunk["file_id"], "chunk_index": chunk["chunk_index"]},
                    {"$set": doc},
                    upsert=True
                )
            )

        try:
            result = self.collection.bulk_write(operations, ordered=False)
            logger.debug(f"MongoDB Backup Sync: {result.upserted_count} upserted, {result.modified_count} modified")
        except Exception as e:
            logger.error(f"MongoDB Backup Sync failed: {e}")

    def delete_by_file(self, file_id: str, source_type: str):
        try:
            result = self.collection.delete_many({"file_id": file_id, "source_type": source_type})
            logger.info(f"MongoDB Backup Deleted: {result.deleted_count} chunks for {file_id}")
        except Exception as e:
            logger.error(f"MongoDB Backup Delete failed: {e}")

    def list_file_ids(self, source_type: str, source_language: str) -> set[str]:
        """All file_ids currently mirrored under (source_type, source_language)."""
        try:
            return set(self.collection.distinct(
                "file_id",
                {"source_type": source_type, "source_language": source_language},
            ))
        except Exception as e:
            logger.warning(f"MongoDB Backup list_file_ids failed: {e}")
            return set()

    @staticmethod
    def _file_group_pipeline() -> list[dict[str, Any]]:
        return [
            {
                "$group": {
                    "_id": {
                        "file_id": "$file_id",
                        "source_type": "$source_type",
                        "source_language": "$source_language",
                    }
                }
            }
        ]

    def _iter_backup_files(self) -> Iterator[tuple[str, str, str]]:
        for item in self.collection.aggregate(self._file_group_pipeline()):
            meta = item.get("_id") or {}
            file_id = meta.get("file_id")
            source_type = meta.get("source_type")
            source_language = meta.get("source_language")
            if file_id and source_type and source_language:
                yield file_id, source_type, source_language

    def _chunks_for_file(
        self,
        file_id: str,
        source_type: str,
        source_language: str,
    ) -> List[Dict[str, Any]]:
        cursor = self.collection.find({
            "file_id": file_id,
            "source_type": source_type,
            "source_language": source_language,
        })
        chunks = []
        for doc in cursor:
            chunk = dict(doc)
            chunk.pop("_id", None)
            chunk.pop("synced_at", None)
            chunks.append(chunk)
        return chunks

    def restore_to_lancedb(self, lancedb_store) -> int:
        """還原所有 Mongo 有而 LanceDB 沒有的合法檔案對話/知識向量。

        Returns:
            還原的檔案個數。
        """
        logger.info("[RAG Restore] Starting restore from MongoDB backup...")
        try:
            restored_count = 0
            for file_id, source_type, source_language in self._iter_backup_files():
                fingerprint = lancedb_store.get_file_fingerprint(
                    file_id, source_type, source_language
                )
                if fingerprint is not None:
                    continue

                logger.info(
                    f"[RAG Restore] File {file_id} ({source_type}/{source_language}) is missing in LanceDB. Restoring..."
                )

                chunks = self._chunks_for_file(file_id, source_type, source_language)
                if chunks:
                    lancedb_store.insert_chunks(chunks)
                    restored_count += 1
                    logger.info(
                        f"[RAG Restore] Successfully restored {len(chunks)} chunks for file {file_id}"
                    )

            logger.info(f"[RAG Restore] Restore completed. Restored {restored_count} files.")
            return restored_count

        except Exception as e:
            logger.error(f"[RAG Restore] Failed to restore from MongoDB backup: {e}", exc_info=True)
            return 0


_mongodb_backup: Optional[MongoDBBackup] = None


def get_mongodb_backup() -> MongoDBBackup:
    global _mongodb_backup
    if _mongodb_backup is None:
        _mongodb_backup = MongoDBBackup(db_name=_DEFAULT_BACKUP_DB)
    return _mongodb_backup

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from pymongo import UpdateOne
from app.services.mongo_client import get_mongo_db

logger = logging.getLogger(__name__)

class MongoDBBackup:
    COLLECTION_NAME = "vector_backup"

    def __init__(self, db_name: str):
        self.db = get_mongo_db(db_name)
        self.collection = self.db[self.COLLECTION_NAME]
        # Create index for upserts
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

_mongodb_backup: Optional[MongoDBBackup] = None

def get_mongodb_backup() -> MongoDBBackup:
    global _mongodb_backup
    if _mongodb_backup is None:
        _mongodb_backup = MongoDBBackup(db_name="jti_app")
    return _mongodb_backup

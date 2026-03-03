"""HCIoT knowledge file storage with namespace isolation."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from bson.binary import Binary
from pymongo import ReturnDocument

from app.services.mongo_client import get_mongo_db


class HciotKnowledgeStore:
    COLLECTION_NAME = "knowledge_files"
    NAMESPACE = "hciot"

    def __init__(self):
        self.db = get_mongo_db()
        self.collection = self.db[self.COLLECTION_NAME]

    @staticmethod
    def _normalize_language(language: str) -> str:
        return (language or "zh").strip().lower()

    @staticmethod
    def _safe_filename(filename: str) -> str:
        return Path(filename).name

    @staticmethod
    def _to_bytes(data: Any) -> bytes:
        if isinstance(data, Binary):
            return bytes(data)
        if isinstance(data, (bytes, bytearray)):
            return bytes(data)
        return b""

    @staticmethod
    def _metadata_from_doc(doc: dict[str, Any]) -> dict[str, Any]:
        return {
            "name": doc.get("filename", ""),
            "filename": doc.get("filename", ""),
            "display_name": doc.get("display_name", doc.get("filename", "")),
            "content_type": doc.get("content_type", "application/octet-stream"),
            "size": int(doc.get("size", 0)),
            "editable": bool(doc.get("editable", False)),
        }

    def _query(self, language: str, filename: Optional[str] = None) -> dict[str, Any]:
        query: dict[str, Any] = {
            "namespace": self.NAMESPACE,
            "language": self._normalize_language(language),
        }
        if filename is not None:
            query["filename"] = self._safe_filename(filename)
        return query

    def list_files(self, language: str) -> list[dict[str, Any]]:
        cursor = self.collection.find(
            self._query(language),
            {"_id": 0, "filename": 1, "display_name": 1, "size": 1, "editable": 1},
        ).sort("filename", 1)

        return [
            {
                "name": doc.get("filename", ""),
                "display_name": doc.get("display_name", doc.get("filename", "")),
                "size": int(doc.get("size", 0)),
                "editable": bool(doc.get("editable", False)),
            }
            for doc in cursor
        ]

    def get_file(self, language: str, filename: str) -> Optional[dict[str, Any]]:
        doc = self.collection.find_one(self._query(language, filename))
        if not doc:
            return None
        doc.pop("_id", None)
        doc["data"] = self._to_bytes(doc.get("data"))
        return doc

    def insert_file(
        self,
        language: str,
        filename: str,
        data: bytes,
        display_name: Optional[str] = None,
        content_type: str = "application/octet-stream",
        editable: bool = True,
    ) -> dict[str, Any]:
        base_name = self._safe_filename(filename)
        path = Path(base_name)
        stem, suffix = path.stem, path.suffix
        candidate = base_name
        counter = 1

        while self.collection.find_one(self._query(language, candidate), {"_id": 1}):
            candidate = f"{stem}_{counter}{suffix}"
            counter += 1

        now = datetime.now(timezone.utc)
        doc = {
            "namespace": self.NAMESPACE,
            "language": self._normalize_language(language),
            "filename": candidate,
            "display_name": display_name or candidate,
            "content_type": content_type or "application/octet-stream",
            "size": len(data),
            "data": Binary(data),
            "editable": bool(editable),
            "created_at": now,
            "updated_at": now,
        }
        self.collection.insert_one(doc)
        doc.pop("_id", None)
        return self._metadata_from_doc(doc)

    def delete_file(self, language: str, filename: str) -> bool:
        result = self.collection.delete_one(self._query(language, filename))
        return result.deleted_count > 0

    def update_file_content(
        self,
        language: str,
        filename: str,
        new_data: bytes,
    ) -> Optional[dict[str, Any]]:
        updated = self.collection.find_one_and_update(
            self._query(language, filename),
            {
                "$set": {
                    "data": Binary(new_data),
                    "size": len(new_data),
                    "updated_at": datetime.now(timezone.utc),
                }
            },
            return_document=ReturnDocument.AFTER,
        )
        if not updated:
            return None
        updated.pop("_id", None)
        return self._metadata_from_doc(updated)


_knowledge_store: Optional[HciotKnowledgeStore] = None


def get_hciot_knowledge_store() -> HciotKnowledgeStore:
    global _knowledge_store
    if _knowledge_store is None:
        _knowledge_store = HciotKnowledgeStore()
    return _knowledge_store


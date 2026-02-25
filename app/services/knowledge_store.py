"""
MongoDB knowledge file storage service.

Stores JTI knowledge files in collection: knowledge_files
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from bson.binary import Binary
from pymongo import ReturnDocument

from app.services.mongo_client import get_mongo_db

logger = logging.getLogger(__name__)


class KnowledgeStore:
    """Knowledge file storage backed by MongoDB."""

    COLLECTION_NAME = "knowledge_files"

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

    def _metadata_from_doc(self, doc: dict[str, Any]) -> dict[str, Any]:
        return {
            "name": doc.get("filename", ""),
            "filename": doc.get("filename", ""),
            "display_name": doc.get("display_name", doc.get("filename", "")),
            "content_type": doc.get("content_type", "application/octet-stream"),
            "size": int(doc.get("size", 0)),
            "editable": bool(doc.get("editable", False)),
        }

    def list_files(self, language: str) -> list[dict[str, Any]]:
        """List files for a language."""
        lang = self._normalize_language(language)
        cursor = self.collection.find(
            {"language": lang},
            {"_id": 0, "filename": 1, "display_name": 1, "size": 1, "editable": 1},
        ).sort("filename", 1)

        files = []
        for doc in cursor:
            files.append(
                {
                    "name": doc.get("filename", ""),
                    "display_name": doc.get("display_name", doc.get("filename", "")),
                    "size": int(doc.get("size", 0)),
                    "editable": bool(doc.get("editable", False)),
                }
            )
        return files

    def get_file(self, language: str, filename: str) -> Optional[dict[str, Any]]:
        """Get full file document including binary data."""
        lang = self._normalize_language(language)
        safe_name = self._safe_filename(filename)

        doc = self.collection.find_one({"language": lang, "filename": safe_name})
        if not doc:
            return None

        doc.pop("_id", None)
        doc["data"] = self._to_bytes(doc.get("data"))
        return doc

    def get_file_data(self, language: str, filename: str) -> Optional[bytes]:
        """Get file binary data only."""
        lang = self._normalize_language(language)
        safe_name = self._safe_filename(filename)

        doc = self.collection.find_one(
            {"language": lang, "filename": safe_name},
            {"_id": 0, "data": 1},
        )
        if not doc:
            return None
        return self._to_bytes(doc.get("data"))

    def save_file(
        self,
        language: str,
        filename: str,
        data: bytes,
        display_name: Optional[str] = None,
        content_type: str = "application/octet-stream",
        editable: bool = True,
    ) -> dict[str, Any]:
        """Upsert file by language + filename."""
        lang = self._normalize_language(language)
        safe_name = self._safe_filename(filename)
        now = datetime.now(timezone.utc)

        updated = self.collection.find_one_and_update(
            {"language": lang, "filename": safe_name},
            {
                "$set": {
                    "language": lang,
                    "filename": safe_name,
                    "display_name": display_name or safe_name,
                    "content_type": content_type or "application/octet-stream",
                    "size": len(data),
                    "data": Binary(data),
                    "editable": bool(editable),
                    "updated_at": now,
                },
                "$setOnInsert": {"created_at": now},
            },
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )

        if not updated:
            raise RuntimeError("save_file failed: no document returned")

        updated.pop("_id", None)
        return self._metadata_from_doc(updated)

    def insert_file(
        self,
        language: str,
        filename: str,
        data: bytes,
        display_name: Optional[str] = None,
        content_type: str = "application/octet-stream",
        editable: bool = True,
    ) -> dict[str, Any]:
        """Insert new file; if duplicated, append _{n} suffix."""
        lang = self._normalize_language(language)
        base_name = self._safe_filename(filename)
        path = Path(base_name)
        stem, suffix = path.stem, path.suffix
        candidate = base_name
        counter = 1

        while self.collection.find_one(
            {"language": lang, "filename": candidate},
            {"_id": 1},
        ):
            candidate = f"{stem}_{counter}{suffix}"
            counter += 1

        now = datetime.now(timezone.utc)
        doc = {
            "language": lang,
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
        """Delete file by language + filename."""
        lang = self._normalize_language(language)
        safe_name = self._safe_filename(filename)
        result = self.collection.delete_one({"language": lang, "filename": safe_name})
        return result.deleted_count > 0

    def update_file_content(
        self,
        language: str,
        filename: str,
        new_data: bytes,
    ) -> Optional[dict[str, Any]]:
        """Update binary content only."""
        lang = self._normalize_language(language)
        safe_name = self._safe_filename(filename)

        updated = self.collection.find_one_and_update(
            {"language": lang, "filename": safe_name},
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


_knowledge_store: Optional[KnowledgeStore] = None


def get_knowledge_store() -> KnowledgeStore:
    """Return singleton knowledge store."""
    global _knowledge_store
    if _knowledge_store is None:
        _knowledge_store = KnowledgeStore()
    return _knowledge_store

"""
MongoDB knowledge file storage service.

Stores knowledge files in collection: knowledge_files
Supports namespace isolation for JTI and HCIoT knowledge stores.
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
    DEFAULT_NAMESPACE = "jti"

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
    def _normalize_namespace(namespace: str | None) -> str:
        return (namespace or KnowledgeStore.DEFAULT_NAMESPACE).strip().lower()

    def _supports_legacy_fallback(self, namespace: str) -> bool:
        return self._normalize_namespace(namespace) == self.DEFAULT_NAMESPACE

    def _query(self, language: str, filename: str | None = None, namespace: str = "jti") -> dict[str, Any]:
        """Build a standard query filter."""
        q: dict[str, Any] = {
            "namespace": self._normalize_namespace(namespace),
            "language": self._normalize_language(language),
        }
        if filename is not None:
            q["filename"] = self._safe_filename(filename)
        return q

    def _legacy_query(self, language: str, filename: str | None = None) -> dict[str, Any]:
        q: dict[str, Any] = {
            "namespace": {"$exists": False},
            "language": self._normalize_language(language),
        }
        if filename is not None:
            q["filename"] = self._safe_filename(filename)
        return q

    def _find_one_with_legacy_fallback(
        self,
        language: str,
        filename: str,
        namespace: str,
        projection: Optional[dict[str, Any]] = None,
    ) -> Optional[dict[str, Any]]:
        doc = self.collection.find_one(self._query(language, filename, namespace), projection)
        if doc or not self._supports_legacy_fallback(namespace):
            return doc
        return self.collection.find_one(self._legacy_query(language, filename), projection)

    def _filename_exists(self, language: str, filename: str, namespace: str) -> bool:
        if self.collection.find_one(self._query(language, filename, namespace), {"_id": 1}):
            return True
        if self._supports_legacy_fallback(namespace):
            return self.collection.find_one(self._legacy_query(language, filename), {"_id": 1}) is not None
        return False

    def _metadata_from_doc(self, doc: dict[str, Any]) -> dict[str, Any]:
        return {
            "name": doc.get("filename", ""),
            "filename": doc.get("filename", ""),
            "display_name": doc.get("display_name", doc.get("filename", "")),
            "content_type": doc.get("content_type", "application/octet-stream"),
            "size": int(doc.get("size", 0)),
            "editable": bool(doc.get("editable", False)),
            "created_at": doc.get("created_at"),
        }

    def list_files(self, language: str, namespace: str = "jti") -> list[dict[str, Any]]:
        """List files for a language."""
        docs = list(
            self.collection.find(
                self._query(language, namespace=namespace),
                {"_id": 0, "filename": 1, "display_name": 1, "size": 1, "editable": 1, "created_at": 1},
            ).sort("filename", 1)
        )

        if self._supports_legacy_fallback(namespace):
            legacy_docs = self.collection.find(
                self._legacy_query(language),
                {"_id": 0, "filename": 1, "display_name": 1, "size": 1, "editable": 1, "created_at": 1},
            ).sort("filename", 1)
            seen = {doc.get("filename", "") for doc in docs}
            for doc in legacy_docs:
                filename = doc.get("filename", "")
                if filename not in seen:
                    docs.append(doc)
                    seen.add(filename)

        docs.sort(key=lambda doc: doc.get("filename", ""))

        return [self._metadata_from_doc(doc) for doc in docs]

    def get_file(self, language: str, filename: str, namespace: str = "jti") -> Optional[dict[str, Any]]:
        """Get full file document including binary data."""
        doc = self._find_one_with_legacy_fallback(language, filename, namespace)
        if not doc:
            return None

        doc.pop("_id", None)
        doc["data"] = self._to_bytes(doc.get("data"))
        return doc

    def get_file_data(self, language: str, filename: str, namespace: str = "jti") -> Optional[bytes]:
        """Get file binary data only."""
        doc = self._find_one_with_legacy_fallback(
            language,
            filename,
            namespace,
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
        namespace: str = "jti",
    ) -> dict[str, Any]:
        """Upsert file by namespace + language + filename."""
        safe_name = self._safe_filename(filename)
        normalized_namespace = self._normalize_namespace(namespace)
        now = datetime.now(timezone.utc)

        updated = self.collection.find_one_and_update(
            self._query(language, filename, normalized_namespace),
            {
                "$set": {
                    "namespace": normalized_namespace,
                    "language": self._normalize_language(language),
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
        namespace: str = "jti",
    ) -> dict[str, Any]:
        """Insert new file; if duplicated, append _{n} suffix."""
        lang = self._normalize_language(language)
        base_name = self._safe_filename(filename)
        normalized_namespace = self._normalize_namespace(namespace)
        path = Path(base_name)
        stem, suffix = path.stem, path.suffix
        candidate = base_name
        counter = 1

        while self._filename_exists(lang, candidate, normalized_namespace):
            candidate = f"{stem}_{counter}{suffix}"
            counter += 1

        now = datetime.now(timezone.utc)
        doc = {
            "namespace": normalized_namespace,
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

    def delete_file(self, language: str, filename: str, namespace: str = "jti") -> bool:
        """Delete file by namespace + language + filename."""
        normalized_namespace = self._normalize_namespace(namespace)
        result = self.collection.delete_one(self._query(language, filename, normalized_namespace))
        if result.deleted_count == 0 and self._supports_legacy_fallback(normalized_namespace):
            result = self.collection.delete_one(self._legacy_query(language, filename))
        return result.deleted_count > 0

    def delete_by_namespace(self, namespace: str, language: str | None = None) -> int:
        """Delete all files in a namespace (optionally filtered by language)."""
        q: dict[str, Any] = {"namespace": self._normalize_namespace(namespace)}
        if language is not None:
            q["language"] = self._normalize_language(language)
        result = self.collection.delete_many(q)
        return result.deleted_count

    def update_file_content(
        self,
        language: str,
        filename: str,
        new_data: bytes,
        namespace: str = "jti",
    ) -> Optional[dict[str, Any]]:
        """Update binary content only."""
        normalized_namespace = self._normalize_namespace(namespace)
        updated = self.collection.find_one_and_update(
            self._query(language, filename, normalized_namespace),
            {
                "$set": {
                    "data": Binary(new_data),
                    "size": len(new_data),
                    "updated_at": datetime.now(timezone.utc),
                }
            },
            return_document=ReturnDocument.AFTER,
        )
        if not updated and self._supports_legacy_fallback(normalized_namespace):
            updated = self.collection.find_one_and_update(
                self._legacy_query(language, filename),
                {
                    "$set": {
                        "namespace": self.DEFAULT_NAMESPACE,
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

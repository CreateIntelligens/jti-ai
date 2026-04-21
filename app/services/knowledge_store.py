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
    DEFAULT_CONTENT_TYPE = "application/octet-stream"
    FILE_METADATA_PROJECTION = {
        "_id": 0,
        "filename": 1,
        "display_name": 1,
        "size": 1,
        "editable": 1,
        "created_at": 1,
    }

    def __init__(self):
        self.db = get_mongo_db("jti_app")
        self.collection = self.db[self.COLLECTION_NAME]

    @staticmethod
    def _normalize_language(language: str) -> str:
        return (language or "zh").strip().lower()

    @staticmethod
    def _normalize_namespace(namespace: str | None) -> str:
        return (namespace or KnowledgeStore.DEFAULT_NAMESPACE).strip().lower()

    @staticmethod
    def _safe_filename(filename: str) -> str:
        return Path(filename).name

    @staticmethod
    def _to_bytes(data: Any) -> bytes:
        return bytes(data) if isinstance(data, (Binary, bytes, bytearray)) else b""


    def _supports_legacy_fallback(self, namespace: str) -> bool:
        return self._normalize_namespace(namespace) == self.DEFAULT_NAMESPACE

    def _query(self, language: str, filename: str | None = None, namespace: str = "jti") -> dict[str, Any]:
        """Build standard query filter."""
        query = {
            "namespace": self._normalize_namespace(namespace),
            "language": self._normalize_language(language),
        }
        if filename:
            query["filename"] = self._safe_filename(filename)
        return query

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
        query = self._query(language, filename, namespace)
        doc = self.collection.find_one(query, projection)
        if doc or not self._supports_legacy_fallback(namespace):
            return doc
        return self.collection.find_one(self._legacy_query(language, filename), projection)

    def _build_file_fields(
        self,
        *,
        language: str,
        filename: str,
        data: bytes,
        display_name: str | None,
        content_type: str,
        editable: bool,
        namespace: str,
    ) -> dict[str, Any]:
        safe_name = self._safe_filename(filename)
        return {
            "namespace": self._normalize_namespace(namespace),
            "language": self._normalize_language(language),
            "filename": safe_name,
            "display_name": display_name or safe_name,
            "content_type": content_type or self.DEFAULT_CONTENT_TYPE,
            "size": len(data),
            "data": Binary(data),
            "editable": bool(editable),
        }

    @staticmethod
    def _build_content_update_fields(data: bytes, namespace: str | None = None) -> dict[str, Any]:
        update_fields: dict[str, Any] = {
            "data": Binary(data),
            "size": len(data),
            "updated_at": datetime.now(timezone.utc),
        }
        if namespace is not None:
            update_fields["namespace"] = namespace
        return update_fields

    @staticmethod
    def _remove_internal_id(doc: dict[str, Any]) -> dict[str, Any]:
        doc.pop("_id", None)
        return doc

    def _get_unique_filename(self, language: str, filename: str, namespace: str) -> tuple[str, str, str]:
        normalized_language = self._normalize_language(language)
        normalized_namespace = self._normalize_namespace(namespace)
        candidate_path = Path(self._safe_filename(filename))
        stem, suffix = candidate_path.stem, candidate_path.suffix
        candidate = candidate_path.name
        counter = 1

        while self._filename_exists(normalized_language, candidate, normalized_namespace):
            candidate = f"{stem}_{counter}{suffix}"
            counter += 1

        return normalized_language, normalized_namespace, candidate

    def _filename_exists(self, language: str, filename: str, namespace: str) -> bool:
        return self._find_one_with_legacy_fallback(language, filename, namespace, {"_id": 1}) is not None

    def _metadata_from_doc(self, doc: dict[str, Any]) -> dict[str, Any]:
        fname = doc.get("filename", "")
        return {
            "name": fname,
            "filename": fname,
            "display_name": doc.get("display_name", fname),
            "content_type": doc.get("content_type", self.DEFAULT_CONTENT_TYPE),
            "size": int(doc.get("size", 0)),
            "editable": bool(doc.get("editable", False)),
            "created_at": doc.get("created_at"),
        }

    def list_files(self, language: str, namespace: str = "jti", **kwargs: Any) -> list[dict[str, Any]]:
        """List files for a language with legacy fallback for JTI."""
        docs = list(
            self.collection.find(
                self._query(language, namespace=namespace),
                self.FILE_METADATA_PROJECTION,
            ).sort("filename", 1)
        )

        if self._supports_legacy_fallback(namespace):
            seen = {doc.get("filename", "") for doc in docs}
            legacy_docs = self.collection.find(
                self._legacy_query(language), self.FILE_METADATA_PROJECTION
            ).sort("filename", 1)

            docs.extend(doc for doc in legacy_docs if doc.get("filename", "") not in seen)
            docs.sort(key=lambda d: d.get("filename", ""))

        return [self._metadata_from_doc(doc) for doc in docs]

    def get_file(self, language: str, filename: str, namespace: str = "jti") -> Optional[dict[str, Any]]:
        """Get full file document including binary data."""
        doc = self._find_one_with_legacy_fallback(language, filename, namespace)
        if not doc:
            return None

        self._remove_internal_id(doc)
        doc["data"] = self._to_bytes(doc.get("data"))
        return doc

    def get_file_data(self, language: str, filename: str, namespace: str = "jti") -> Optional[bytes]:
        """Get file binary data only."""
        doc = self._find_one_with_legacy_fallback(language, filename, namespace, {"_id": 0, "data": 1})
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
        now = datetime.now(timezone.utc)
        file_fields = self._build_file_fields(
            language=language,
            filename=filename,
            data=data,
            display_name=display_name,
            content_type=content_type,
            editable=editable,
            namespace=namespace,
        )

        updated = self.collection.find_one_and_update(
            self._query(language, filename, file_fields["namespace"]),
            {
                "$set": {
                    **file_fields,
                    "updated_at": now,
                },
                "$setOnInsert": {"created_at": now},
            },
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )

        if not updated:
            raise RuntimeError("save_file failed: no document returned")

        return self._metadata_from_doc(self._remove_internal_id(updated))

    def insert_file(
        self,
        language: str,
        filename: str,
        data: bytes,
        display_name: Optional[str] = None,
        content_type: str = "application/octet-stream",
        editable: bool = True,
        namespace: str = "jti",
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Insert new file; if duplicated, append _{n} suffix."""
        lang, normalized_namespace, candidate = self._get_unique_filename(language, filename, namespace)

        now = datetime.now(timezone.utc)
        doc = {
            **self._build_file_fields(
                language=lang,
                filename=candidate,
                data=data,
                display_name=display_name,
                content_type=content_type,
                editable=editable,
                namespace=normalized_namespace,
            ),
            "created_at": now,
            "updated_at": now,
        }

        self.collection.insert_one(doc)
        return self._metadata_from_doc(self._remove_internal_id(doc))

    def delete_file(self, language: str, filename: str, namespace: str = "jti", **kwargs: Any) -> bool:
        """Delete file by namespace + language + filename."""
        normalized_namespace = self._normalize_namespace(namespace)
        result = self.collection.delete_one(self._query(language, filename, normalized_namespace))
        if result.deleted_count > 0:
            return True

        if self._supports_legacy_fallback(normalized_namespace):
            result = self.collection.delete_one(self._legacy_query(language, filename))
        return result.deleted_count > 0

    def delete_by_namespace(self, namespace: str, language: str | None = None) -> int:
        """Delete all files in a namespace (optionally filtered by language)."""
        query: dict[str, Any] = {"namespace": self._normalize_namespace(namespace)}
        if language is not None:
            query["language"] = self._normalize_language(language)
        result = self.collection.delete_many(query)
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
            {"$set": self._build_content_update_fields(new_data)},
            return_document=ReturnDocument.AFTER,
        )
        if not updated and self._supports_legacy_fallback(normalized_namespace):
            updated = self.collection.find_one_and_update(
                self._legacy_query(language, filename),
                {"$set": self._build_content_update_fields(new_data, namespace=self.DEFAULT_NAMESPACE)},
                return_document=ReturnDocument.AFTER,
            )
        if not updated:
            return None

        return self._metadata_from_doc(self._remove_internal_id(updated))


_knowledge_store: Optional[KnowledgeStore] = None


def get_knowledge_store() -> KnowledgeStore:
    """Return singleton knowledge store."""
    global _knowledge_store
    if _knowledge_store is None:
        _knowledge_store = KnowledgeStore()
    return _knowledge_store

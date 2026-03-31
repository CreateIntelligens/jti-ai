"""HCIoT knowledge file storage with namespace isolation."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

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
    def _normalize_optional_text(value: Any) -> str | None:
        if not isinstance(value, str):
            return None
        normalized = value.strip()
        return normalized or None

    @classmethod
    def _association_metadata(
        cls,
        *,
        topic_id: str | None = None,
        category_labels: dict[str, Any] | None = None,
        topic_labels: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        normalized_topic_id = cls._normalize_optional_text(topic_id)

        category_labels = category_labels or {}
        topic_labels = topic_labels or {}

        category_label_zh = (
            cls._normalize_optional_text(category_labels.get("zh")) if normalized_topic_id else None
        )
        category_label_en = (
            cls._normalize_optional_text(category_labels.get("en")) if normalized_topic_id else None
        )
        topic_label_zh = cls._normalize_optional_text(topic_labels.get("zh")) if normalized_topic_id else None
        topic_label_en = cls._normalize_optional_text(topic_labels.get("en")) if normalized_topic_id else None

        return {
            "topic_id": normalized_topic_id,
            "category_label_zh": category_label_zh,
            "category_label_en": category_label_en,
            "topic_label_zh": topic_label_zh,
            "topic_label_en": topic_label_en,
        }

    @staticmethod
    def _metadata_from_doc(doc: dict[str, Any]) -> dict[str, Any]:
        return {
            "name": doc.get("filename", ""),
            "filename": doc.get("filename", ""),
            "display_name": doc.get("display_name", doc.get("filename", "")),
            "content_type": doc.get("content_type", "application/octet-stream"),
            "size": int(doc.get("size", 0)),
            "editable": bool(doc.get("editable", False)),
            "topic_id": doc.get("topic_id"),
            "category_label_zh": doc.get("category_label_zh"),
            "category_label_en": doc.get("category_label_en"),
            "topic_label_zh": doc.get("topic_label_zh"),
            "topic_label_en": doc.get("topic_label_en"),
            "created_at": doc.get("created_at"),
        }

    def _query(self, language: str, filename: str | None = None) -> dict[str, Any]:
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
            {
                "_id": 0,
                "filename": 1,
                "display_name": 1,
                "content_type": 1,
                "size": 1,
                "editable": 1,
                "topic_id": 1,
                "category_label_zh": 1,
                "category_label_en": 1,
                "topic_label_zh": 1,
                "topic_label_en": 1,
                "created_at": 1,
            },
        ).sort("filename", 1)

        return [self._metadata_from_doc(doc) for doc in cursor]

    def get_file(self, language: str, filename: str) -> dict[str, Any] | None:
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
        display_name: str | None = None,
        content_type: str = "application/octet-stream",
        editable: bool = True,
        topic_id: str | None = None,
        category_labels: dict[str, Any] | None = None,
        topic_labels: dict[str, Any] | None = None,
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
        doc.update(
            self._association_metadata(
                topic_id=topic_id,
                category_labels=category_labels,
                topic_labels=topic_labels,
            )
        )
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
    ) -> dict[str, Any] | None:
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

    def update_file_metadata(
        self,
        language: str,
        filename: str,
        metadata: dict[str, Any],
    ) -> dict[str, Any] | None:
        payload = self._association_metadata(
            topic_id=metadata.get("topic_id"),
            category_labels={
                "zh": metadata.get("category_label_zh"),
                "en": metadata.get("category_label_en"),
            },
            topic_labels={
                "zh": metadata.get("topic_label_zh"),
                "en": metadata.get("topic_label_en"),
            },
        )
        updated = self.collection.find_one_and_update(
            self._query(language, filename),
            {
                "$set": {
                    **payload,
                    "updated_at": datetime.now(timezone.utc),
                }
            },
            return_document=ReturnDocument.AFTER,
        )
        if not updated:
            return None
        updated.pop("_id", None)
        return self._metadata_from_doc(updated)


_knowledge_store: HciotKnowledgeStore | None = None


def get_hciot_knowledge_store() -> HciotKnowledgeStore:
    global _knowledge_store
    if _knowledge_store is None:
        _knowledge_store = HciotKnowledgeStore()
    return _knowledge_store

"""Generic topic store for QA knowledge-base sub-apps.

The base keeps the existing topic document shape intact: topics are isolated by
their Mongo collection and language partition, so no namespace field is added to
queries or persisted documents.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from app.services.mongo_client import get_mongo_db

Topic = dict[str, Any]
Language = Literal["zh", "en"]


class QaKbTopicStoreBase:
    """Flat MongoDB topic store — one document per topic."""

    DB_NAME: str = ""
    COLLECTION_NAME: str = ""
    NAMESPACE: str = ""

    def __init__(self, language: Language = "zh"):
        if not self.DB_NAME:
            raise NotImplementedError(f"{type(self).__name__} must set DB_NAME")
        if not self.COLLECTION_NAME:
            raise NotImplementedError(f"{type(self).__name__} must set COLLECTION_NAME")
        if not self.NAMESPACE:
            raise NotImplementedError(f"{type(self).__name__} must set NAMESPACE")
        self.language = language
        self.db = get_mongo_db(self.DB_NAME)
        self.collection = self.db[self.COLLECTION_NAME]

    def _language_query(self) -> dict[str, Any]:
        return {"language": self.language}

    def _topic_query(self, topic_id: str) -> dict[str, Any]:
        return {"topic_id": topic_id, **self._language_query()}

    def _prepare_payload(self, data: dict, topic_id: str | None = None) -> dict:
        """Strip _id/language and add updated_at timestamp."""
        payload = {key: value for key, value in data.items() if key not in {"_id", "language"}}
        if topic_id:
            payload["topic_id"] = topic_id
        payload["updated_at"] = datetime.now(timezone.utc)
        return payload

    def list_topics(self) -> list[Topic]:
        """Return all topics sorted by order, without MongoDB _id."""
        return list(self.collection.find(self._language_query(), {"_id": 0}).sort("order", 1))

    def get_topic(self, topic_id: str) -> Topic | None:
        return self.collection.find_one(self._topic_query(topic_id), {"_id": 0})

    def list_categories(self) -> list[dict[str, Any]]:
        """Group topics by category prefix into a hierarchical structure."""
        groups: dict[str, dict[str, Any]] = {}
        for topic in self.list_topics():
            topic_id = topic.get("topic_id", "")
            prefix = topic_id.split("/", 1)[0]
            if prefix not in groups:
                groups[prefix] = {
                    "id": prefix,
                    "labels": topic.get("category_labels", {"zh": prefix, "en": prefix}),
                    "topics": [],
                }
            groups[prefix]["topics"].append({**topic, "id": topic_id})

        return sorted(
            groups.values(),
            key=lambda group: min((topic.get("order", 0) for topic in group["topics"]), default=0),
        )

    def upsert_topic(self, topic_id: str, data: dict) -> None:
        """Create or fully replace a topic document."""
        now = datetime.now(timezone.utc)
        payload = self._prepare_payload(data, topic_id)
        query = self._topic_query(topic_id)
        set_on_insert = {"created_at": now, "language": self.language}

        if "order" not in payload:
            updated = self.collection.find_one_and_update(
                query,
                {"$set": payload},
                projection={"_id": 0},
            )
            if updated is not None:
                return
            set_on_insert["order"] = self.collection.count_documents(self._language_query())

        self.collection.find_one_and_update(
            query,
            {"$set": payload, "$setOnInsert": set_on_insert},
            upsert=True,
            projection={"_id": 0},
        )

    def update_topic(self, topic_id: str, data: dict) -> bool:
        """Partially update a topic's fields."""
        payload = self._prepare_payload({key: value for key, value in data.items() if key != "topic_id"})
        if not payload:
            return False

        result = self.collection.update_one(self._topic_query(topic_id), {"$set": payload})
        return result.matched_count > 0

    def delete_topic(self, topic_id: str) -> bool:
        return self.collection.delete_one(self._topic_query(topic_id)).deleted_count > 0

    def reorder_topics(self, topic_ids: list[str]) -> int:
        """Rewrite order for the given topics; untouched topics keep their order."""
        now = datetime.now(timezone.utc)
        updated = 0
        for index, topic_id in enumerate(topic_ids):
            result = self.collection.update_one(
                self._topic_query(topic_id),
                {"$set": {"order": index, "updated_at": now}},
            )
            updated += result.matched_count
        return updated

    def ensure_topic(self, topic_id: str, labels: dict, category_labels: dict) -> None:
        """Create topic if it doesn't exist yet."""
        if self.get_topic(topic_id) is None:
            self.upsert_topic(
                topic_id,
                {
                    "labels": labels,
                    "category_labels": category_labels,
                    "questions": {"zh": [], "en": []},
                    "hidden_questions": {"zh": [], "en": []},
                },
            )

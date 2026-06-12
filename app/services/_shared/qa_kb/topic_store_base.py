"""Generic topic store for QA knowledge-base sub-apps.

The base keeps the existing topic document shape intact: topics are isolated by
their Mongo collection and language partition, so no namespace field is added to
queries or persisted documents.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pymongo import UpdateOne

from app.services.mongo_client import get_mongo_db

Topic = dict[str, Any]
Language = Literal["zh", "en"]


class QaKbTopicStoreBase:
    """Flat MongoDB topic store — one document per topic."""

    DB_NAME: str = ""
    COLLECTION_NAME: str = ""
    CATEGORY_COLLECTION_NAME: str = ""
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
        category_collection_name = self.CATEGORY_COLLECTION_NAME or f"{self.NAMESPACE}_categories"
        self.category_collection = self.db[category_collection_name]

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
        if "hidden" not in payload:
            set_on_insert["hidden"] = False

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
        return self.delete_topics([topic_id]) == 1

    def delete_topics(self, topic_ids: list[str]) -> int:
        """Delete several topics with a single order compaction at the end.

        Callers deleting a whole category must use this instead of issuing
        per-topic deletes in parallel — concurrent per-delete compactions can
        interleave and overwrite each other's renumbering.
        """
        if not topic_ids:
            return 0
        result = self.collection.delete_many({"topic_id": {"$in": topic_ids}, **self._language_query()})
        if result.deleted_count:
            self._compact_topic_orders()
        return result.deleted_count

    def _compact_topic_orders(self) -> None:
        """Renumber topics 0..N-1 so deletions leave no gaps in `order`.

        Inserting before an existing topic bumps later topics' order; without
        compaction those bumped values survive the inserted topic's deletion
        and keep inflating across insert/delete cycles. Relative ordering is
        preserved, so display order never changes. `updated_at` is left
        untouched — renumbering is not a content edit.
        """
        docs = self.collection.find(self._language_query(), {"order": 1}).sort(
            [("order", 1), ("topic_id", 1)]
        )
        operations = [
            UpdateOne({"_id": doc["_id"]}, {"$set": {"order": index}})
            for index, doc in enumerate(docs)
            if doc.get("order") != index
        ]
        if operations:
            self.collection.bulk_write(operations, ordered=False)

    def reorder_topics(self, topic_ids: list[str]) -> int:
        """Rewrite order for the given topics; untouched topics keep their order."""
        if not topic_ids:
            return 0
        now = datetime.now(timezone.utc)
        result = self.collection.bulk_write(
            [
                UpdateOne(
                    self._topic_query(topic_id),
                    {"$set": {"order": index, "updated_at": now}},
                )
                for index, topic_id in enumerate(topic_ids)
            ],
            ordered=False,
        )
        return result.matched_count

    def get_category_meta(self) -> dict[str, dict[str, Any]]:
        """Return category metadata keyed by category id for the active language."""
        docs = self.category_collection.find(self._language_query(), {"_id": 0})
        return {
            str(doc.get("category_id", "")): {key: value for key, value in doc.items() if key != "_id"}
            for doc in docs
            if doc.get("category_id")
        }

    def set_category_hidden(self, category_id: str, hidden: bool) -> bool:
        """Persist presentation-only category visibility metadata."""
        now = datetime.now(timezone.utc)
        payload = {
            "language": self.language,
            "category_id": category_id,
            "hidden": hidden,
            "updated_at": now,
        }
        result = self.category_collection.update_one(
            {"language": self.language, "category_id": category_id},
            {
                "$set": payload,
                "$setOnInsert": {"created_at": now},
            },
            upsert=True,
        )
        return result.matched_count > 0 or result.upserted_id is not None

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
                    "hidden": False,
                },
            )

"""
MongoDB-backed HCIoT topic storage (flat).

Each document in `hciot_topics` represents a single topic:

  {
    "language": "en",
    "topic_id": "ortho-rehab/prp",
    "order": 0,
    "labels": { "zh": "PRP", "en": "PRP Therapy" },
    "category_labels": { "zh": "骨科＋復健科", "en": "Orthopedics & Rehab" },
    "questions": { "zh": [...], "en": [...] }
  }
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from app.services.agent_utils import normalize_language
from app.services.mongo_client import get_mongo_db

Topic = dict[str, Any]
Language = Literal["zh", "en"]


def to_topic_language(language: str | None = None) -> Language:
    return "en" if normalize_language(language) == "en" else "zh"


class HciotTopicStore:
    """Flat MongoDB topic store — one document per topic."""

    COLLECTION = "hciot_topics"

    def __init__(self, language: Language = "zh"):
        self.language = language
        self.db = get_mongo_db("hciot_app")
        self.collection = self.db[self.COLLECTION]

    def _language_query(self) -> dict[str, Any]:
        return {"language": self.language}

    def _topic_query(self, topic_id: str) -> dict[str, Any]:
        return {"topic_id": topic_id, **self._language_query()}

    def _prepare_payload(self, data: dict, topic_id: str | None = None) -> dict:
        """Strip _id and add updated_at timestamp."""
        payload = {k: v for k, v in data.items() if k not in {"_id", "language"}}
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
            tid = topic.get("topic_id", "")
            prefix = tid.split("/", 1)[0]
            if prefix not in groups:
                groups[prefix] = {
                    "id": prefix,
                    "labels": topic.get("category_labels", {"zh": prefix, "en": prefix}),
                    "topics": [],
                }
            groups[prefix]["topics"].append({**topic, "id": tid})

        return sorted(groups.values(), key=lambda g: min((t.get("order", 0) for t in g["topics"]), default=0))

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
        payload = self._prepare_payload({k: v for k, v in data.items() if k != "topic_id"})
        if not payload:
            return False

        result = self.collection.update_one(self._topic_query(topic_id), {"$set": payload})
        return result.matched_count > 0

    def delete_topic(self, topic_id: str) -> bool:
        return self.collection.delete_one(self._topic_query(topic_id)).deleted_count > 0

    def reorder_topics(self, topic_ids: list[str]) -> int:
        """Rewrite the `order` field of the given topics to match list position.

        Only topics present in `topic_ids` are touched; others keep their order.
        Returns the number of topics actually updated.
        """
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


_hciot_topic_stores: dict[Language, HciotTopicStore] = {}


def get_hciot_topic_store(language: str | None = None) -> HciotTopicStore:
    """Return singleton HCIoT topic store."""
    lang = to_topic_language(language)
    if lang not in _hciot_topic_stores:
        _hciot_topic_stores[lang] = HciotTopicStore(lang)
    return _hciot_topic_stores[lang]

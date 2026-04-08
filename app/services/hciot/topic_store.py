"""
MongoDB-backed HCIoT topic storage (flat).

Each document in `hciot_topics` represents a single topic:

  {
    "topic_id": "ortho-rehab/prp",
    "order": 0,
    "labels": { "zh": "PRP", "en": "PRP Therapy" },
    "category_labels": { "zh": "骨科＋復健科", "en": "Orthopedics & Rehab" },
    "questions": { "zh": [...], "en": [...] }
  }
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.services.mongo_client import get_mongo_db

Topic = dict[str, Any]


class HciotTopicStore:
    """Flat MongoDB topic store — one document per topic."""

    COLLECTION = "hciot_topics"

    def __init__(self):
        self.db = get_mongo_db()
        self.collection = self.db[self.COLLECTION]

    def _prepare_payload(self, data: dict, topic_id: str | None = None) -> dict:
        """Strip _id and add updated_at timestamp."""
        payload = {k: v for k, v in data.items() if k != "_id"}
        if topic_id:
            payload["topic_id"] = topic_id
        payload["updated_at"] = datetime.now(timezone.utc)
        return payload

    # ===================== Read =====================

    def list_topics(self) -> list[Topic]:
        """Return all topics sorted by order, without MongoDB _id."""
        return list(self.collection.find({}, {"_id": 0}).sort("order", 1))

    def get_topic(self, topic_id: str) -> Topic | None:
        return self.collection.find_one({"topic_id": topic_id}, {"_id": 0})

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

        # Sort categories by the minimum order of their topics
        return sorted(groups.values(), key=lambda g: min((t.get("order", 0) for t in g["topics"]), default=0))

    # ===================== Write =====================

    def upsert_topic(self, topic_id: str, data: dict) -> None:
        """Create or fully replace a topic document."""
        now = datetime.now(timezone.utc)
        payload = self._prepare_payload(data, topic_id)

        # Preserve order if not provided
        if "order" not in payload:
            existing = self.get_topic(topic_id)
            payload["order"] = existing.get("order", 0) if existing else self.collection.count_documents({})

        self.collection.update_one(
            {"topic_id": topic_id},
            {"$set": payload, "$setOnInsert": {"created_at": now}},
            upsert=True,
        )

    def update_topic(self, topic_id: str, data: dict) -> bool:
        """Partially update a topic's fields."""
        payload = self._prepare_payload({k: v for k, v in data.items() if k != "topic_id"})
        if not payload:
            return False

        result = self.collection.update_one({"topic_id": topic_id}, {"$set": payload})
        return result.matched_count > 0

    def delete_topic(self, topic_id: str) -> bool:
        return self.collection.delete_one({"topic_id": topic_id}).deleted_count > 0

    # ===================== Convenience =====================

    def ensure_topic(self, topic_id: str, labels: dict, category_labels: dict) -> None:
        """Create topic if it doesn't exist yet."""
        if self.get_topic(topic_id) is None:
            self.upsert_topic(topic_id, {
                "labels": labels,
                "category_labels": category_labels,
                "questions": {"zh": [], "en": []},
            })


# --- Singleton ---
_hciot_topic_store: HciotTopicStore | None = None


def get_hciot_topic_store() -> HciotTopicStore:
    """Return singleton HCIoT topic store."""
    global _hciot_topic_store
    if _hciot_topic_store is None:
        _hciot_topic_store = HciotTopicStore()
    return _hciot_topic_store

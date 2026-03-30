"""
MongoDB-backed HCIoT topic storage.

Stores healthcare topic categories in the `hciot_topics` collection.
Each document represents one category with nested topics and questions.

Structure:
  { id, order, labels, topics: [{ id, order, icon, accent, labels, summaries, questions }] }
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from app.services.mongo_client import get_mongo_db

logger = logging.getLogger(__name__)


class HciotTopicStore:
    """MongoDB-backed HCIoT topic storage."""

    COLLECTION = "hciot_topics"

    def __init__(self):
        self.db = get_mongo_db()
        self.collection = self.db[self.COLLECTION]

    # ===================== Category Read =====================

    def list_categories(self) -> list[dict]:
        """Return all categories sorted by order, without MongoDB _id."""
        cursor = self.collection.find({}, {"_id": 0}).sort("order", 1)
        return list(cursor)

    def get_category(self, category_id: str) -> dict | None:
        return self.collection.find_one({"id": category_id}, {"_id": 0})

    # ===================== Category CRUD =====================

    def upsert_category(self, category_id: str, data: dict) -> None:
        now = datetime.now(timezone.utc)
        payload = {k: v for k, v in data.items() if k != "_id"}
        payload["id"] = category_id
        payload["updated_at"] = now
        self.collection.update_one(
            {"id": category_id},
            {"$set": payload, "$setOnInsert": {"created_at": now}},
            upsert=True,
        )

    def delete_category(self, category_id: str) -> bool:
        result = self.collection.delete_one({"id": category_id})
        return result.deleted_count > 0

    def reorder_categories(self, category_ids: list[str]) -> None:
        """Set order field on each category by position in the list."""
        now = datetime.now(timezone.utc)
        for order, cat_id in enumerate(category_ids):
            self.collection.update_one(
                {"id": cat_id},
                {"$set": {"order": order, "updated_at": now}},
            )

    def reorder_topics(self, category_id: str, topic_ids: list[str]) -> bool:
        """Reorder topics within a category by the provided topic_ids list."""
        now = datetime.now(timezone.utc)
        cat = self.get_category(category_id)
        if cat is None:
            return False
        topics_by_id = {t["id"]: t for t in cat.get("topics", [])}
        reordered = []
        for order, tid in enumerate(topic_ids):
            t = topics_by_id.get(tid)
            if t is not None:
                t["order"] = order
                reordered.append(t)
        # Append any topics not mentioned in topic_ids at the end
        mentioned = set(topic_ids)
        for t in cat.get("topics", []):
            if t["id"] not in mentioned:
                t["order"] = len(reordered)
                reordered.append(t)
        self.collection.update_one(
            {"id": category_id},
            {"$set": {"topics": reordered, "updated_at": now}},
        )
        return True

    # ===================== Topic CRUD (nested in category) =====================

    def add_topic(self, category_id: str, topic: dict) -> None:
        now = datetime.now(timezone.utc)
        cat = self.get_category(category_id)
        if cat is None:
            raise ValueError(f"Category '{category_id}' not found")
        topics = cat.get("topics", [])
        topic["order"] = len(topics)
        topics.append(topic)
        self.collection.update_one(
            {"id": category_id},
            {"$set": {"topics": topics, "updated_at": now}},
        )

    def update_topic(self, category_id: str, topic_id: str, data: dict) -> bool:
        now = datetime.now(timezone.utc)
        cat = self.get_category(category_id)
        if cat is None:
            return False
        topics = cat.get("topics", [])
        updated = False
        for t in topics:
            if t.get("id") == topic_id:
                for k, v in data.items():
                    if k not in ("_id", "id"):
                        t[k] = v
                updated = True
                break
        if not updated:
            return False
        self.collection.update_one(
            {"id": category_id},
            {"$set": {"topics": topics, "updated_at": now}},
        )
        return True

    def delete_topic(self, category_id: str, topic_id: str) -> bool:
        now = datetime.now(timezone.utc)
        cat = self.get_category(category_id)
        if cat is None:
            return False
        topics = cat.get("topics", [])
        new_topics = [t for t in topics if t.get("id") != topic_id]
        if len(new_topics) == len(topics):
            return False
        # Re-assign order after deletion
        for order, t in enumerate(new_topics):
            t["order"] = order
        self.collection.update_one(
            {"id": category_id},
            {"$set": {"topics": new_topics, "updated_at": now}},
        )
        return True

    def move_topic(self, from_category_id: str, to_category_id: str, topic_id: str) -> bool:
        """Move a topic from one category to another."""
        now = datetime.now(timezone.utc)
        from_cat = self.get_category(from_category_id)
        to_cat = self.get_category(to_category_id)
        if from_cat is None or to_cat is None:
            return False

        from_topics = from_cat.get("topics", [])
        to_topics = to_cat.get("topics", [])

        topic = next((t for t in from_topics if t.get("id") == topic_id), None)
        if topic is None:
            return False

        from_topics = [t for t in from_topics if t.get("id") != topic_id]
        for order, t in enumerate(from_topics):
            t["order"] = order

        topic["order"] = len(to_topics)
        to_topics.append(topic)

        self.collection.update_one(
            {"id": from_category_id},
            {"$set": {"topics": from_topics, "updated_at": now}},
        )
        self.collection.update_one(
            {"id": to_category_id},
            {"$set": {"topics": to_topics, "updated_at": now}},
        )
        return True


# --- Singleton ---

_hciot_topic_store: HciotTopicStore | None = None


def get_hciot_topic_store() -> HciotTopicStore:
    """Return singleton HCIoT topic store."""
    global _hciot_topic_store
    if _hciot_topic_store is None:
        _hciot_topic_store = HciotTopicStore()
    return _hciot_topic_store

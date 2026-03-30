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

The category prefix is derived from topic_id.split("/", 1)[0].
list_categories() groups topics by this prefix into a hierarchy for the API.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.services.mongo_client import get_mongo_db


def _category_prefix(topic_id: str) -> str:
    """Extract the category portion from a topic_id like 'cat/topic'."""
    return topic_id.split("/", 1)[0]


class HciotTopicStore:
    """Flat MongoDB topic store — one document per topic."""

    COLLECTION = "hciot_topics"

    def __init__(self):
        self.db = get_mongo_db()
        self.collection = self.db[self.COLLECTION]

    # ===================== Read =====================

    def list_topics(self) -> list[dict]:
        """Return all topics sorted by order, without MongoDB _id."""
        cursor = self.collection.find({}, {"_id": 0}).sort("order", 1)
        return list(cursor)

    def get_topic(self, topic_id: str) -> dict | None:
        return self.collection.find_one({"topic_id": topic_id}, {"_id": 0})

    def list_categories(self) -> list[dict]:
        """Group topics by category prefix into a hierarchical structure.

        Returns:
            [{ "id": "ortho-rehab",
               "labels": { "zh": "...", "en": "..." },
               "topics": [{ "id": "ortho-rehab/prp", ... }, ...] }]
        """
        topics = self.list_topics()
        groups: dict[str, dict] = {}
        for topic in topics:
            tid = topic.get("topic_id", "")
            prefix = _category_prefix(tid)
            if prefix not in groups:
                cat_labels = topic.get("category_labels", {"zh": prefix, "en": prefix})
                groups[prefix] = {
                    "id": prefix,
                    "labels": cat_labels,
                    "topics": [],
                }
            # Expose as "id" for frontend compatibility
            entry = {**topic, "id": tid}
            groups[prefix]["topics"].append(entry)
        # Sort categories by the minimum order of their topics
        return sorted(groups.values(), key=lambda g: min((t.get("order", 0) for t in g["topics"]), default=0))

    # ===================== Write =====================

    def upsert_topic(self, topic_id: str, data: dict) -> None:
        """Create or fully replace a topic document."""
        now = datetime.now(timezone.utc)
        payload = {k: v for k, v in data.items() if k != "_id"}
        payload["topic_id"] = topic_id
        payload["updated_at"] = now
        # Preserve order on update if not provided
        if "order" not in payload:
            existing = self.get_topic(topic_id)
            if existing:
                payload["order"] = existing.get("order", 0)
            else:
                max_order = self.collection.count_documents({})
                payload["order"] = max_order
        self.collection.update_one(
            {"topic_id": topic_id},
            {"$set": payload, "$setOnInsert": {"created_at": now}},
            upsert=True,
        )

    def update_topic(self, topic_id: str, data: dict) -> bool:
        """Partially update a topic's fields."""
        now = datetime.now(timezone.utc)
        payload = {k: v for k, v in data.items() if k not in ("_id", "topic_id")}
        if not payload:
            return False
        payload["updated_at"] = now
        result = self.collection.update_one(
            {"topic_id": topic_id},
            {"$set": payload},
        )
        return result.matched_count > 0

    def delete_topic(self, topic_id: str) -> bool:
        result = self.collection.delete_one({"topic_id": topic_id})
        return result.deleted_count > 0

    # ===================== Convenience =====================

    def ensure_topic(self, topic_id: str, labels: dict, category_labels: dict) -> None:
        """Create topic if it doesn't exist yet."""
        if self.get_topic(topic_id) is not None:
            return
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

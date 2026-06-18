"""General per-store image storage in MongoDB (store_name-scoped)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from bson.binary import Binary
from pymongo import ASCENDING

from app.services.mongo_client import get_mongo_db


class GeneralImageStore:
    COLLECTION_NAME = "general_images"

    def __init__(self):
        self.db = get_mongo_db("general_app")
        self.collection = self.db[self.COLLECTION_NAME]
        # Compound unique key: one image_id per store.
        self.collection.create_index(
            [("store_name", ASCENDING), ("image_id", ASCENDING)], unique=True
        )

    @staticmethod
    def _to_bytes(data: Any) -> bytes:
        if isinstance(data, (bytes, bytearray, Binary)):
            return bytes(data)
        return b""

    def get_image(self, store_name: str, image_id: str) -> dict[str, Any] | None:
        doc = self.collection.find_one({"store_name": store_name, "image_id": image_id})
        if not doc:
            return None
        doc["data"] = self._to_bytes(doc.get("data"))
        return doc

    def list_images(self, store_name: str) -> list[dict[str, Any]]:
        cursor = self.collection.find(
            {"store_name": store_name},
            {"_id": 0, "image_id": 1, "content_type": 1, "size": 1},
        ).sort("image_id", 1)
        return [
            {
                "image_id": doc["image_id"],
                "content_type": doc.get("content_type"),
                "size": doc.get("size"),
                "url": f"/api/general/stores/{store_name}/images/{doc['image_id']}",
            }
            for doc in cursor
        ]

    def upsert_image(
        self, store_name: str, image_id: str, data: bytes, content_type: str = "image/png"
    ) -> None:
        now = datetime.now(timezone.utc)
        self.collection.update_one(
            {"store_name": store_name, "image_id": image_id},
            {
                "$set": {
                    "store_name": store_name,
                    "image_id": image_id,
                    "data": Binary(data),
                    "content_type": content_type,
                    "size": len(data),
                    "updated_at": now,
                },
                "$setOnInsert": {"created_at": now},
            },
            upsert=True,
        )

    def image_exists(self, store_name: str, image_id: str) -> bool:
        return (
            self.collection.count_documents(
                {"store_name": store_name, "image_id": image_id}, limit=1
            )
            > 0
        )

    def delete_image(self, store_name: str, image_id: str) -> bool:
        result = self.collection.delete_one(
            {"store_name": store_name, "image_id": image_id}
        )
        return result.deleted_count > 0


_image_store: GeneralImageStore | None = None


def get_general_image_store() -> GeneralImageStore:
    global _image_store
    if _image_store is None:
        _image_store = GeneralImageStore()
    return _image_store

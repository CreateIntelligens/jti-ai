"""HCIoT image storage in MongoDB."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from bson.binary import Binary
from pymongo import ASCENDING

from app.services.mongo_client import get_mongo_db


class HciotImageStore:
    COLLECTION_NAME = "hciot_images"

    def __init__(self):
        self.db = get_mongo_db("hciot_app")
        self.collection = self.db[self.COLLECTION_NAME]
        self.collection.create_index([("image_id", ASCENDING)], unique=True)

    @staticmethod
    def _to_bytes(data: Any) -> bytes:
        if isinstance(data, Binary):
            return bytes(data)
        if isinstance(data, (bytes, bytearray)):
            return bytes(data)
        return b""

    def get_image(self, image_id: str) -> dict[str, Any] | None:
        doc = self.collection.find_one({"image_id": image_id})
        if not doc:
            return None
        doc.pop("_id", None)
        doc["data"] = self._to_bytes(doc.get("data"))
        return doc

    def list_images(self) -> list[dict[str, Any]]:
        cursor = self.collection.find(
            {},
            {
                "_id": 0,
                "image_id": 1,
                "content_type": 1,
                "size": 1,
                "created_at": 1,
            },
        ).sort("image_id", 1)

        result = []
        for doc in cursor:
            result.append({
                "image_id": doc["image_id"],
                "size_bytes": doc.get("size", 0),
                "url": f"/api/hciot/images/{doc['image_id']}",
                "content_type": doc.get("content_type"),
                "created_at": doc.get("created_at")
            })
        return result

    def upsert_image(
        self,
        image_id: str,
        data: bytes,
        content_type: str = "image/jpeg",
    ) -> dict[str, bool]:
        """Insert or replace an image. Returns {success, replaced}.

        replaced=True means an existing image was overwritten.
        created_at is preserved on updates via $setOnInsert.
        """
        try:
            result = self.collection.update_one(
                {"image_id": image_id},
                {
                    "$set": {
                        "image_id": image_id,
                        "data": Binary(data),
                        "content_type": content_type,
                        "size": len(data),
                    },
                    "$setOnInsert": {"created_at": datetime.now(timezone.utc)},
                },
                upsert=True,
            )
            return {"success": True, "replaced": result.upserted_id is None}
        except Exception:
            return {"success": False, "replaced": False}

    def image_exists(self, image_id: str) -> bool:
        return self.collection.count_documents({"image_id": image_id}, limit=1) > 0

    def delete_image(self, image_id: str) -> bool:
        result = self.collection.delete_one({"image_id": image_id})
        return result.deleted_count > 0


_image_store: HciotImageStore | None = None


def get_hciot_image_store() -> HciotImageStore:
    global _image_store
    if _image_store is None:
        _image_store = HciotImageStore()
    return _image_store

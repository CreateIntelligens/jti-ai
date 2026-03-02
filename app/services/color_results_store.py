"""
MongoDB-backed color results storage.

Stores color quiz result definitions in collection: color_results
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from pymongo import ReturnDocument

from app.services.mongo_client import get_mongo_db

logger = logging.getLogger(__name__)


class ColorResultsStore:
    """MongoDB-backed color results storage."""

    COLLECTION_NAME = "color_results"

    def __init__(self):
        self.db = get_mongo_db()
        self.collection = self.db[self.COLLECTION_NAME]

    def list_results(self, language: str) -> list[dict]:
        """List all color results for a language."""
        cursor = self.collection.find(
            {"language": language}, {"_id": 0, "language": 0}
        ).sort("color_id", 1)
        return list(cursor)

    def get_result(self, language: str, color_id: str) -> dict | None:
        """Get a single color result."""
        doc = self.collection.find_one(
            {"language": language, "color_id": color_id},
            {"_id": 0, "language": 0},
        )
        return doc

    def upsert_result(self, language: str, color_id: str, data: dict) -> dict:
        """Upsert a color result."""
        now = datetime.now(timezone.utc)
        update_data = {
            **data,
            "language": language,
            "color_id": color_id,
            "updated_at": now,
        }
        doc = self.collection.find_one_and_update(
            {"language": language, "color_id": color_id},
            {"$set": update_data, "$setOnInsert": {"created_at": now}},
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        doc.pop("_id", None)
        doc.pop("language", None)
        return doc

    def delete_result(self, language: str, color_id: str) -> bool:
        """Delete a color result."""
        result = self.collection.delete_one(
            {"language": language, "color_id": color_id}
        )
        return result.deleted_count > 0

    def bulk_upsert_results(self, language: str, results: dict[str, dict]) -> int:
        """Bulk upsert color results from {color_id: {...}} dict."""
        if not results:
            return 0
        now = datetime.now(timezone.utc)
        count = 0
        for color_id, data in results.items():
            self.collection.update_one(
                {"language": language, "color_id": color_id},
                {
                    "$set": {
                        **data,
                        "language": language,
                        "color_id": color_id,
                        "updated_at": now,
                    },
                    "$setOnInsert": {"created_at": now},
                },
                upsert=True,
            )
            count += 1
        return count

    def get_all_results(self, language: str) -> dict[str, dict]:
        """Return {color_id: {title, color_name, ...}} matching JSON format."""
        results = self.list_results(language)
        out: dict[str, dict] = {}
        for r in results:
            cid = r.pop("color_id", None)
            if cid:
                # Remove internal timestamps
                r.pop("created_at", None)
                r.pop("updated_at", None)
                out[cid] = r
        return out


# --- Singleton ---

_color_results_store: Optional[ColorResultsStore] = None


def get_color_results_store() -> ColorResultsStore:
    """Return singleton color results store."""
    global _color_results_store
    if _color_results_store is None:
        _color_results_store = ColorResultsStore()
    return _color_results_store

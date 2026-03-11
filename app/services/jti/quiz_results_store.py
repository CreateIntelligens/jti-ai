"""
MongoDB-backed quiz results storage with multi-set support.

Stores quiz result definitions in collection: quiz_results
Stores set metadata in collection: quiz_results_metadata
Max 3 sets per language (including default).
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from pymongo import ReturnDocument

from app.services.mongo_client import get_mongo_db

logger = logging.getLogger(__name__)

MAX_QUIZ_SETS = 3
DEFAULT_SET_ID = "default"


class QuizResultsStore:
    """MongoDB-backed quiz results storage with multi-set support."""

    COLLECTION_NAME = "quiz_results"
    METADATA_COLLECTION = "quiz_results_metadata"

    def __init__(self):
        self.db = get_mongo_db()
        self.collection = self.db[self.COLLECTION_NAME]
        self.metadata = self.db[self.METADATA_COLLECTION]

    # ===================== Set Management =====================

    def list_sets(self, language: str) -> list[dict]:
        """List all quiz result sets for a language."""
        cursor = self.metadata.find(
            {"language": language},
            {"_id": 0},
        ).sort("created_at", 1)
        sets = list(cursor)
        for s in sets:
            s["quiz_count"] = self.collection.count_documents(
                {"language": language, "set_id": s.get("set_id")}
            )
        return sets

    def create_set(self, language: str, name: str) -> dict:
        """Create a new quiz result set by copying the default set."""
        count = self.metadata.count_documents({"language": language})
        if count >= MAX_QUIZ_SETS:
            raise ValueError(f"Maximum {MAX_QUIZ_SETS} quiz result sets per language")

        now = datetime.now(timezone.utc)
        set_id = str(uuid.uuid4())[:8]
        doc = {
            "language": language,
            "set_id": set_id,
            "name": name,
            "is_active": False,
            "is_default": False,
            "created_at": now,
            "updated_at": now,
        }
        self.metadata.insert_one(doc)
        doc.pop("_id", None)

        # Copy all quiz result entries from the default set.
        default_results = list(self.collection.find(
            {"language": language, "set_id": DEFAULT_SET_ID},
        ))
        for quiz_result in default_results:
            quiz_result.pop("_id", None)
            quiz_result["set_id"] = set_id
            quiz_result["created_at"] = now
            quiz_result["updated_at"] = now
        if default_results:
            self.collection.insert_many(default_results)

        doc["quiz_count"] = len(default_results)
        return doc

    def delete_set(self, language: str, set_id: str) -> bool:
        """Delete a quiz result set. Cannot delete default."""
        meta = self.metadata.find_one({"language": language, "set_id": set_id})
        if not meta:
            return False
        if meta.get("is_default"):
            raise ValueError("Cannot delete the default set")

        was_active = meta.get("is_active", False)
        self.collection.delete_many({"language": language, "set_id": set_id})
        self.metadata.delete_one({"language": language, "set_id": set_id})

        if was_active:
            self.metadata.update_one(
                {"language": language, "set_id": DEFAULT_SET_ID},
                {"$set": {"is_active": True}},
            )
        return True

    def set_active(self, language: str, set_id: str) -> bool:
        """Set a quiz result set as active, deactivate others."""
        meta = self.metadata.find_one({"language": language, "set_id": set_id})
        if not meta:
            return False
        self.metadata.update_many(
            {"language": language},
            {"$set": {"is_active": False}},
        )
        self.metadata.update_one(
            {"language": language, "set_id": set_id},
            {"$set": {"is_active": True}},
        )
        return True

    def get_active_set_id(self, language: str) -> str:
        """Return the active set_id, or default if none."""
        meta = self.metadata.find_one(
            {"language": language, "is_active": True},
            {"set_id": 1, "_id": 0},
        )
        return meta["set_id"] if meta else DEFAULT_SET_ID

    def get_set_metadata(self, language: str, set_id: str) -> dict | None:
        """Get metadata for a single set."""
        doc = self.metadata.find_one(
            {"language": language, "set_id": set_id},
            {"_id": 0},
        )
        return doc

    def upsert_set_metadata(self, language: str, set_id: str, data: dict) -> dict:
        """Upsert set metadata."""
        now = datetime.now(timezone.utc)
        update_data = {
            k: v for k, v in data.items() if k not in ("_id", "language", "set_id")
        }
        update_data["language"] = language
        update_data["set_id"] = set_id
        update_data["updated_at"] = now
        doc = self.metadata.find_one_and_update(
            {"language": language, "set_id": set_id},
            {"$set": update_data, "$setOnInsert": {"created_at": now}},
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        doc.pop("_id", None)
        return doc

    # ===================== Quiz Results CRUD =====================

    def list_results(self, language: str, set_id: str | None = None) -> list[dict]:
        """List all quiz results for a language and set."""
        if set_id is None:
            set_id = self.get_active_set_id(language)
        cursor = self.collection.find(
            {"language": language, "set_id": set_id},
            {"_id": 0, "language": 0, "set_id": 0},
        ).sort("quiz_id", 1)
        return list(cursor)

    def get_result(self, language: str, quiz_id: str, set_id: str | None = None) -> dict | None:
        """Get a single quiz result."""
        if set_id is None:
            set_id = self.get_active_set_id(language)
        doc = self.collection.find_one(
            {"language": language, "set_id": set_id, "quiz_id": quiz_id},
            {"_id": 0, "language": 0, "set_id": 0},
        )
        return doc

    def upsert_result(self, language: str, quiz_id: str, data: dict, set_id: str | None = None) -> dict:
        """Upsert a quiz result."""
        if set_id is None:
            set_id = self.get_active_set_id(language)
        now = datetime.now(timezone.utc)
        update_data = {
            **data,
            "language": language,
            "set_id": set_id,
            "quiz_id": quiz_id,
            "updated_at": now,
        }
        doc = self.collection.find_one_and_update(
            {"language": language, "set_id": set_id, "quiz_id": quiz_id},
            {"$set": update_data, "$setOnInsert": {"created_at": now}},
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        doc.pop("_id", None)
        doc.pop("language", None)
        doc.pop("set_id", None)
        return doc

    def delete_result(self, language: str, quiz_id: str, set_id: str | None = None) -> bool:
        """Delete a quiz result."""
        if set_id is None:
            set_id = self.get_active_set_id(language)
        result = self.collection.delete_one(
            {"language": language, "set_id": set_id, "quiz_id": quiz_id}
        )
        return result.deleted_count > 0

    def bulk_upsert_results(self, language: str, results: dict[str, dict], set_id: str | None = None) -> int:
        """Bulk upsert quiz results from `{quiz_id: {...}}`."""
        if not results:
            return 0
        if set_id is None:
            set_id = DEFAULT_SET_ID
        now = datetime.now(timezone.utc)
        count = 0
        for quiz_id, data in results.items():
            self.collection.update_one(
                {"language": language, "set_id": set_id, "quiz_id": quiz_id},
                {
                    "$set": {
                        **data,
                        "language": language,
                        "set_id": set_id,
                        "quiz_id": quiz_id,
                        "updated_at": now,
                    },
                    "$setOnInsert": {"created_at": now},
                },
                upsert=True,
            )
            count += 1
        return count

    def replace_all_results(self, language: str, results: dict[str, dict], set_id: str | None = None) -> int:
        """Replace all results in a set (delete then insert)."""
        if set_id is None:
            set_id = DEFAULT_SET_ID
        self.collection.delete_many({"language": language, "set_id": set_id})
        return self.bulk_upsert_results(language, results, set_id)

    def get_all_results(self, language: str, set_id: str | None = None) -> dict[str, dict]:
        """Return `{quiz_id: {...}}` matching the seed JSON format."""
        results = self.list_results(language, set_id)
        out: dict[str, dict] = {}
        for result in results:
            qid = result.pop("quiz_id", None)
            if qid:
                result.pop("created_at", None)
                result.pop("updated_at", None)
                out[qid] = result
        return out


# --- Singleton ---

_quiz_results_store: Optional[QuizResultsStore] = None


def get_quiz_results_store() -> QuizResultsStore:
    """Return the singleton quiz results store."""
    global _quiz_results_store
    if _quiz_results_store is None:
        _quiz_results_store = QuizResultsStore()
    return _quiz_results_store

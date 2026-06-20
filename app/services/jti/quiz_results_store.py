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
from app.services.quiz.config import JTI_STORE_NAME

logger = logging.getLogger(__name__)

MAX_QUIZ_SETS = 3
DEFAULT_SET_ID = "default"


class QuizResultsStore:
    """MongoDB-backed quiz results storage with multi-set support."""

    COLLECTION_NAME = "quiz_results"
    METADATA_COLLECTION = "quiz_results_metadata"

    def __init__(self):
        self.db = get_mongo_db("jti_app")
        self.collection = self.db[self.COLLECTION_NAME]
        self.metadata = self.db[self.METADATA_COLLECTION]
        self._ensure_indexes()

    def _ensure_indexes(self) -> None:
        """確保 metadata / results 的 unique index 含 store_name。

        舊版 unique index 缺 store_name → 第二個 store 用相同 set_id/quiz_id
        會跨 store 撞鍵。先 drop 殘留舊 index,再建含 store_name 的版本。
        """
        try:
            self.metadata.create_index(
                [("store_name", 1), ("language", 1), ("set_id", 1)],
                unique=True,
                name="uniq_store_name_language_set_id",
            )
        except Exception as exc:  # noqa: BLE001 — 啟動期僅記錄,不阻斷
            logger.warning(
                "[QuizResults] 建立 (store_name, language, set_id) unique index 失敗: %s", exc
            )

        # results: 移除舊的 (language, set_id, quiz_id) unique,改含 store_name。
        self._drop_legacy_index(self.collection, "language_1_set_id_1_quiz_id_1")
        try:
            self.collection.create_index(
                [("store_name", 1), ("language", 1), ("set_id", 1), ("quiz_id", 1)],
                unique=True,
                name="uniq_store_name_language_set_id_quiz_id",
            )
        except Exception as exc:  # noqa: BLE001 — 啟動期僅記錄,不阻斷
            logger.warning(
                "[QuizResults] 建立 results unique index 失敗: %s", exc
            )

    @staticmethod
    def _drop_legacy_index(collection, index_name: str) -> None:
        """Drop a legacy index if it exists (idempotent, safe on fresh DBs)."""
        try:
            if index_name in collection.index_information():
                collection.drop_index(index_name)
                logger.info("[QuizResults] 已移除殘留舊 index: %s", index_name)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[QuizResults] 移除舊 index %s 失敗: %s", index_name, exc)

    # ===================== Set Management =====================

    def list_sets(self, language: str, store_name: str = JTI_STORE_NAME) -> list[dict]:
        """List all quiz result sets for a language."""
        cursor = self.metadata.find(
            {"store_name": store_name, "language": language},
            {"_id": 0},
        ).sort("created_at", 1)
        sets = list(cursor)
        for s in sets:
            s["quiz_count"] = self.collection.count_documents(
                {"store_name": store_name, "language": language, "set_id": s.get("set_id")}
            )
        return sets

    def create_set(self, language: str, name: str, store_name: str = JTI_STORE_NAME) -> dict:
        """Create a new quiz result set by copying the default set."""
        count = self.metadata.count_documents({"store_name": store_name, "language": language})
        if count >= MAX_QUIZ_SETS:
            raise ValueError(f"Maximum {MAX_QUIZ_SETS} quiz result sets per language")

        now = datetime.now(timezone.utc)
        set_id = str(uuid.uuid4())[:8]
        doc = {
            "store_name": store_name,
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
            {"store_name": store_name, "language": language, "set_id": DEFAULT_SET_ID},
        ))
        for quiz_result in default_results:
            quiz_result.pop("_id", None)
            quiz_result["store_name"] = store_name
            quiz_result["set_id"] = set_id
            quiz_result["created_at"] = now
            quiz_result["updated_at"] = now
        if default_results:
            self.collection.insert_many(default_results)

        doc["quiz_count"] = len(default_results)
        return doc

    def delete_set(self, language: str, set_id: str, store_name: str = JTI_STORE_NAME) -> bool:
        """Delete a quiz result set. Cannot delete default."""
        meta = self.metadata.find_one({"store_name": store_name, "language": language, "set_id": set_id})
        if not meta:
            return False
        if meta.get("is_default"):
            raise ValueError("Cannot delete the default set")

        was_active = meta.get("is_active", False)
        self.collection.delete_many({"store_name": store_name, "language": language, "set_id": set_id})
        self.metadata.delete_one({"store_name": store_name, "language": language, "set_id": set_id})

        if was_active:
            self.metadata.update_one(
                {"store_name": store_name, "language": language, "set_id": DEFAULT_SET_ID},
                {"$set": {"is_active": True}},
            )
        return True

    def set_active(self, language: str, set_id: str, store_name: str = JTI_STORE_NAME) -> bool:
        """Set a quiz result set as active, deactivate others."""
        meta = self.metadata.find_one({"store_name": store_name, "language": language, "set_id": set_id})
        if not meta:
            return False
        self.metadata.update_many(
            {"store_name": store_name, "language": language},
            {"$set": {"is_active": False}},
        )
        self.metadata.update_one(
            {"store_name": store_name, "language": language, "set_id": set_id},
            {"$set": {"is_active": True}},
        )
        return True

    def get_active_set_id(self, language: str, store_name: str = JTI_STORE_NAME) -> str:
        """Return the active set_id, or default if none."""
        meta = self.metadata.find_one(
            {"store_name": store_name, "language": language, "is_active": True},
            {"set_id": 1, "_id": 0},
        )
        return meta["set_id"] if meta else DEFAULT_SET_ID

    def get_set_metadata(self, language: str, set_id: str, store_name: str = JTI_STORE_NAME) -> dict | None:
        """Get metadata for a single set."""
        doc = self.metadata.find_one(
            {"store_name": store_name, "language": language, "set_id": set_id},
            {"_id": 0},
        )
        return doc

    def upsert_set_metadata(self, language: str, set_id: str, data: dict, store_name: str = JTI_STORE_NAME) -> dict:
        """Upsert set metadata."""
        now = datetime.now(timezone.utc)
        update_data = {
            k: v for k, v in data.items() if k not in ("_id", "store_name", "language", "set_id")
        }
        update_data["store_name"] = store_name
        update_data["language"] = language
        update_data["set_id"] = set_id
        update_data["updated_at"] = now
        doc = self.metadata.find_one_and_update(
            {"store_name": store_name, "language": language, "set_id": set_id},
            {"$set": update_data, "$setOnInsert": {"created_at": now}},
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        doc.pop("_id", None)
        return doc

    # ===================== Quiz Results CRUD =====================

    def list_results(self, language: str, set_id: str | None = None, store_name: str = JTI_STORE_NAME) -> list[dict]:
        """List all quiz results for a language and set."""
        if set_id is None:
            set_id = self.get_active_set_id(language, store_name=store_name)
        cursor = self.collection.find(
            {"store_name": store_name, "language": language, "set_id": set_id},
            {"_id": 0, "store_name": 0, "language": 0, "set_id": 0},
        ).sort("quiz_id", 1)
        return list(cursor)

    def get_result(self, language: str, quiz_id: str, set_id: str | None = None, store_name: str = JTI_STORE_NAME) -> dict | None:
        """Get a single quiz result."""
        if set_id is None:
            set_id = self.get_active_set_id(language, store_name=store_name)
        doc = self.collection.find_one(
            {"store_name": store_name, "language": language, "set_id": set_id, "quiz_id": quiz_id},
            {"_id": 0, "store_name": 0, "language": 0, "set_id": 0},
        )
        return doc

    def upsert_result(self, language: str, quiz_id: str, data: dict, set_id: str | None = None, store_name: str = JTI_STORE_NAME) -> dict:
        """Upsert a quiz result."""
        if set_id is None:
            set_id = self.get_active_set_id(language, store_name=store_name)
        now = datetime.now(timezone.utc)
        update_data = {
            **data,
            "store_name": store_name,
            "language": language,
            "set_id": set_id,
            "quiz_id": quiz_id,
            "updated_at": now,
        }
        doc = self.collection.find_one_and_update(
            {"store_name": store_name, "language": language, "set_id": set_id, "quiz_id": quiz_id},
            {"$set": update_data, "$setOnInsert": {"created_at": now}},
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        doc.pop("_id", None)
        doc.pop("store_name", None)
        doc.pop("language", None)
        doc.pop("set_id", None)
        return doc

    def delete_result(self, language: str, quiz_id: str, set_id: str | None = None, store_name: str = JTI_STORE_NAME) -> bool:
        """Delete a quiz result."""
        if set_id is None:
            set_id = self.get_active_set_id(language, store_name=store_name)
        result = self.collection.delete_one(
            {"store_name": store_name, "language": language, "set_id": set_id, "quiz_id": quiz_id}
        )
        return result.deleted_count > 0

    def bulk_upsert_results(self, language: str, results: dict[str, dict], set_id: str | None = None, store_name: str = JTI_STORE_NAME) -> int:
        """Bulk upsert quiz results from `{quiz_id: {...}}`."""
        if not results:
            return 0
        if set_id is None:
            set_id = DEFAULT_SET_ID
        now = datetime.now(timezone.utc)
        count = 0
        for quiz_id, data in results.items():
            self.collection.update_one(
                {"store_name": store_name, "language": language, "set_id": set_id, "quiz_id": quiz_id},
                {
                    "$set": {
                        **data,
                        "store_name": store_name,
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

    def replace_all_results(self, language: str, results: dict[str, dict], set_id: str | None = None, store_name: str = JTI_STORE_NAME) -> int:
        """Replace all results in a set (delete then insert)."""
        if set_id is None:
            set_id = DEFAULT_SET_ID
        self.collection.delete_many({"store_name": store_name, "language": language, "set_id": set_id})
        return self.bulk_upsert_results(language, results, set_id, store_name=store_name)

    def get_all_results(self, language: str, set_id: str | None = None, store_name: str = JTI_STORE_NAME) -> dict[str, dict]:
        """Return `{quiz_id: {...}}` matching the seed JSON format."""
        results = self.list_results(language, set_id, store_name=store_name)
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
